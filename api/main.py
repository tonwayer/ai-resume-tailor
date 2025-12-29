from typing import List, Optional, Literal, Tuple
import ast
import json
import requests
import re
from io import BytesIO
import zipfile


from fastapi.responses import StreamingResponse
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.units import inch


from bs4 import BeautifulSoup
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# =========================
# Config
# =========================
OLLAMA_URL = "http://localhost:11434/api/chat"
OLLAMA_MODEL = "llama3.1:8b"

WEB_ORIGINS = ["http://localhost:3000", "http://127.0.0.1:3000"]

# =========================
# App
# =========================
app = FastAPI(title="AI Resume Tailor API", version="0.2")

app.add_middleware(
    CORSMiddleware,
    allow_origins=WEB_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================
# Schemas
# =========================
class ParseRequest(BaseModel):
    resume_text: str = Field(min_length=50)
    jd_text: str = Field(min_length=50)
    tolerance: int = Field(ge=0, le=100)

class ResumeExperience(BaseModel):
    company: Optional[str] = None
    role: Optional[str] = None
    dates: Optional[str] = None
    bullets: List[str] = Field(default_factory=list)

class ResumeJSON(BaseModel):
    summary: Optional[str] = None
    skills: List[str] = Field(default_factory=list)
    experience: List[ResumeExperience] = Field(default_factory=list)
    education: List[str] = Field(default_factory=list)

class JdJSON(BaseModel):
    title: Optional[str] = None
    must_have: List[str] = Field(default_factory=list)
    nice_to_have: List[str] = Field(default_factory=list)
    responsibilities: List[str] = Field(default_factory=list)
    keywords: List[str] = Field(default_factory=list)

class ParseResponse(BaseModel):
    resume_json: ResumeJSON
    jd_json: JdJSON

class PlanItem(BaseModel):
    jd_requirement: str
    evidence: List[str] = Field(default_factory=list)  # short snippets from resume
    keywords_to_add: List[str] = Field(default_factory=list)  # MUST already exist in resume text
    action: Literal["keep", "rewrite", "expand", "add_skill_only"] = "rewrite"

class TailorPlan(BaseModel):
    tolerance: int
    mode: Literal["conservative", "balanced", "creative"]
    allowed: List[str] = Field(default_factory=list)
    disallowed: List[str] = Field(default_factory=list)
    missing_must_haves: List[str] = Field(default_factory=list)
    items: List[PlanItem] = Field(default_factory=list)
    global_keywords: List[str] = Field(default_factory=list)  # MUST already exist in resume text

class TailorRequest(BaseModel):
    resume_text: str = Field(min_length=50)
    jd_text: str = Field(min_length=50)
    tolerance: int = Field(ge=0, le=100)
    plan: Optional[TailorPlan] = None

class TailorResponse(BaseModel):
    tailored_resume: str

class ExtractJdRequest(BaseModel):
    url: str = Field(min_length=10)

class ExtractJdResponse(BaseModel):
    jd_text: str

class PdfRequest(BaseModel):
    resume_text: str = Field(min_length=50)
    filename: Optional[str] = "tailored_resume.pdf"

class BatchZipRequest(BaseModel):
    base_resume_text: str = Field(min_length=50)
    job_urls: List[str] = Field(min_items=1, max_items=10)
    tolerance: int = Field(ge=0, le=100)
    format: Literal["pdf", "pdf+txt"] = "pdf"


# =========================
# Helpers
# =========================
def tolerance_profile(t: int) -> Literal["conservative", "balanced", "creative"]:
    if t < 30:
        return "conservative"
    if t < 70:
        return "balanced"
    return "creative"

def policy_for_tolerance(t: int) -> Tuple[Literal["conservative", "balanced", "creative"], List[str], List[str]]:
    mode = tolerance_profile(t)

    if mode == "conservative":
        allowed = [
            "reorder_sections",
            "rewrite_summary_light",
            "rewrite_bullets_light",
            "add_keywords_only_if_already_implied",
        ]
        disallowed = [
            "add_new_roles",
            "add_new_projects",
            "add_metrics_not_in_resume",
            "claim_tools_not_in_resume",
        ]
    elif mode == "balanced":
        allowed = [
            "reorder_sections",
            "rewrite_summary",
            "rewrite_bullets",
            "insert_keywords_into_existing_bullets",
            "add_skills_section_keywords_if_reasonable",
        ]
        disallowed = [
            "add_new_roles",
            "add_new_employers",
            "add_new_degrees",
            "add_new_certifications",
            "invent_metrics",
            "invent_new_technologies",
        ]
    else:  # creative
        allowed = [
            "rewrite_summary_strong",
            "rewrite_bullets_strong",
            "expand_bullets_with_reasonable_details",
            "add_skills_keywords_section",
        ]
        disallowed = [
            "add_new_roles",
            "add_new_employers",
            "add_new_degrees",
            "add_new_certifications",
            "invent_metrics_or_specific_numbers",
            "invent_new_technologies",
        ]

    return mode, allowed, disallowed

def extract_json_strict(text: str) -> dict:
    """
    Ollama/Llama sometimes wraps JSON with extra text.
    We try:
      1) json.loads
      2) parse substring from first '{' to last '}'
      3) ast.literal_eval as fallback (handles single quotes) then verify dict
    """
    try:
        return json.loads(text)
    except Exception:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("Model did not return a JSON object.")

    candidate = text[start : end + 1]

    try:
        return json.loads(candidate)
    except Exception:
        parsed = ast.literal_eval(candidate)
        if not isinstance(parsed, dict):
            raise ValueError("Model did not return a JSON object.")
        return parsed

def contains_education(text: str) -> bool:
    return "education" in text.lower()

def normalize_text(s: str) -> str:
    return (s or "").lower()

def resume_contains_term(resume_text: str, term: str) -> bool:
    return term.lower() in resume_text.lower()

def clean_text(s: str) -> str:
    s = re.sub(r"\s+", " ", s)
    return s.strip()

def extract_visible_text_from_html(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")

    # remove junk
    for tag in soup(["script", "style", "noscript", "svg", "nav", "footer", "header", "form"]):
        tag.decompose()

    # prefer main/article content if present
    main = soup.find("main") or soup.find("article") or soup.body
    text = main.get_text(separator="\n") if main else soup.get_text(separator="\n")

    # cleanup lines
    lines = [clean_text(line) for line in text.split("\n")]
    lines = [line for line in lines if len(line) >= 3]

    # de-duplicate repeated nav items
    dedup = []
    seen = set()
    for line in lines:
        key = line.lower()
        if key in seen:
            continue
        seen.add(key)
        dedup.append(line)

    return "\n".join(dedup)

SECTION_HEADERS = {
    "SUMMARY", "EDUCATION", "EXPERIENCE", "SKILLS", "PROJECTS", "CERTIFICATIONS", "AWARDS"
}

def render_resume_pdf(resume_text: str) -> BytesIO:
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=LETTER)
    width, height = LETTER

    # margins
    left = 0.75 * inch
    right = 0.75 * inch
    top = 0.75 * inch
    bottom = 0.75 * inch

    # typography
    font_body = "Helvetica"
    font_bold = "Helvetica-Bold"
    body_size = 10.5
    header_size = 12.5
    leading = 13.5

    # layout
    y = height - top
    max_width = width - left - right

    def new_page():
        nonlocal y
        c.showPage()
        y = height - top

    def ensure_space(lines_needed: int = 1):
        nonlocal y
        if y - (leading * lines_needed) <= bottom:
            new_page()

    def wrap_text(text: str, font: str, size: float, avail_width: float) -> list[str]:
        words = text.split()
        if not words:
            return [""]
        lines: list[str] = []
        cur = words[0]
        for w in words[1:]:
            test = cur + " " + w
            if c.stringWidth(test, font, size) <= avail_width:
                cur = test
            else:
                lines.append(cur)
                cur = w
        lines.append(cur)
        return lines

    def draw_line(text: str, font: str, size: float, x: float, avail_width: float):
        nonlocal y
        c.setFont(font, size)
        for line in wrap_text(text, font, size, avail_width):
            ensure_space(1)
            c.drawString(x, y, line)
            y -= leading

    def draw_blank(lines: int = 1):
        nonlocal y
        ensure_space(lines)
        y -= leading * lines

    def is_section_header(line: str) -> bool:
        s = line.strip()
        return s.isupper() and s in SECTION_HEADERS

    def is_bullet(line: str) -> bool:
        s = line.lstrip()
        return s.startswith("•") or s.startswith("-") or s.startswith("*")

    # Parse lines
    lines = resume_text.splitlines()
    i = 0
    while i < len(lines):
        raw = lines[i].rstrip("\n")
        line = raw.rstrip()

        # blank line
        if line.strip() == "":
            draw_blank(0.5)
            i += 1
            continue

        # SECTION HEADER
        if is_section_header(line):
            # extra top space between sections
            draw_blank(0.3)
            ensure_space(2)
            c.setFont(font_bold, header_size)
            c.drawString(left, y, line.strip())
            y -= leading * 1.1

            # divider line
            c.setLineWidth(0.6)
            c.line(left, y + 4, width - right, y + 4)
            y -= leading * 0.5

            # Special handling: 2-column SKILLS block if present
            if line.strip() == "SKILLS":
                # Collect consecutive non-empty lines until next section header
                block: list[str] = []
                j = i + 1
                while j < len(lines):
                    nxt = lines[j].rstrip()
                    if nxt.strip() == "":
                        # keep going but don't include empties in skills block
                        j += 1
                        continue
                    if is_section_header(nxt):
                        break
                    block.append(nxt.strip())
                    j += 1

                if block:
                    # Flatten skill items. Supports:
                    # - "• Category: item, item"
                    # - "Category: item, item"
                    # - "item, item"
                    items: list[str] = []
                    for b in block:
                        b2 = b.lstrip("•").strip()
                        # if "Category: ..." keep the whole line as an item
                        items.append(b2)

                    # Draw in 2 columns
                    col_gap = 0.4 * inch
                    col_w = (max_width - col_gap) / 2
                    x1 = left
                    x2 = left + col_w + col_gap

                    # Render as wrapped lines in two columns, balancing by index
                    # (simple approach; good enough for MVP)
                    left_items = items[0::2]
                    right_items = items[1::2]

                    # Measure how many wrapped lines will be used, to ensure space
                    def count_wrapped(it_list: list[str], avail: float) -> int:
                        n = 0
                        for it in it_list:
                            n += len(wrap_text(it, font_body, body_size, avail))
                        return n

                    needed = max(count_wrapped(left_items, col_w), count_wrapped(right_items, col_w)) + 1
                    ensure_space(needed)

                    # Draw left column
                    y_start = y
                    y_left = y_start
                    c.setFont(font_body, body_size)
                    for it in left_items:
                        for wline in wrap_text(it, font_body, body_size, col_w):
                            if y_left - leading <= bottom:
                                new_page()
                                y_start = y
                                y_left = y_start
                            c.drawString(x1, y_left, wline)
                            y_left -= leading

                    # Draw right column
                    y_right = y_start
                    for it in right_items:
                        for wline in wrap_text(it, font_body, body_size, col_w):
                            if y_right - leading <= bottom:
                                new_page()
                                y_start = y
                                y_right = y_start
                            c.drawString(x2, y_right, wline)
                            y_right -= leading

                    # Move y down by the max used
                    y = min(y_left, y_right) - leading * 0.3

                i = j
                continue

            i += 1
            continue

        # BULLETS (indent nicely)
        if is_bullet(line):
            bullet_indent = 0.18 * inch
            text_indent = 0.35 * inch
            bullet_char = "•"
            bullet_text = line.lstrip()
            # normalize bullet marker
            bullet_text = bullet_text.lstrip("•-*").strip()

            ensure_space(1)
            c.setFont(font_body, body_size)
            c.drawString(left + bullet_indent, y, bullet_char)

            # wrap bullet content with hanging indent
            avail = max_width - text_indent
            wrapped = wrap_text(bullet_text, font_body, body_size, avail)
            if wrapped:
                c.drawString(left + text_indent, y, wrapped[0])
                y -= leading
                for cont in wrapped[1:]:
                    ensure_space(1)
                    c.drawString(left + text_indent, y, cont)
                    y -= leading
            else:
                y -= leading

            i += 1
            continue

        # Name line (first non-empty line) -> slightly bigger + bold
        if i == 0:
            ensure_space(2)
            c.setFont(font_bold, 14)
            c.drawString(left, y, line.strip())
            y -= leading * 1.3
            i += 1
            continue

        # If line looks like role/company heading -> bold
        # heuristic: short-ish line without bullet and not a section header
        if len(line) <= 60 and ("|" in line or "Developer" in line or "Engineer" in line):
            draw_line(line.strip(), font_bold, body_size, left, max_width)
            i += 1
            continue

        # Normal line
        draw_line(line.strip(), font_body, body_size, left, max_width)
        i += 1

    c.save()
    buf.seek(0)
    return buf

def slugify(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"https?://", "", s)
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s[:60] or "job"

def fetch_jd_text(url: str) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
    }
    r = requests.get(url, headers=headers, timeout=25)
    if r.status_code != 200:
        raise ValueError(f"fetch failed status={r.status_code}")
    jd_text = extract_visible_text_from_html(r.text)
    if len(jd_text) < 200:
        raise ValueError("extracted text too short")
    return jd_text


# =========================
# LLM Client (Ollama)
# =========================
def ollama_chat(system: str, user: str, temperature: float = 0.0) -> str:
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "options": {"temperature": temperature},
        "stream": False,
    }

    r = requests.post(OLLAMA_URL, json=payload, timeout=180)
    if r.status_code != 200:
        raise HTTPException(status_code=500, detail=f"Ollama error: {r.text}")

    data = r.json()
    return data["message"]["content"]

# =========================
# Core logic (internal)
# =========================
def build_plan_internal(req: ParseRequest) -> TailorPlan:
    mode, allowed, disallowed = policy_for_tolerance(req.tolerance)

    system = """You are an expert resume strategist.

CRITICAL RULES (MUST FOLLOW):
- The resume is a factual document. Do NOT invent or assume experience.
- Only use evidence that appears verbatim or very clearly implied in the RESUME TEXT.
- NEVER suggest technologies, programming languages, tools, certifications, or degrees that are NOT present in the RESUME TEXT.
- If a JD requirement mentions skills not present in the resume, mark them as missing.
- Output VALID JSON ONLY. No explanations, no markdown.

Definitions:
- Evidence = short exact phrases or bullets copied or lightly paraphrased from the resume.
- keywords_to_add = terms that ALREADY APPEAR somewhere in the resume text (case-insensitive match).
"""

    # IMPORTANT: f-string + literal JSON braces must be doubled: {{ }}
    user = f"""MODE: {mode}

TASK:
Create a resume tailoring plan that maps Job Description requirements to factual evidence in the resume.

RESUME TEXT:
{req.resume_text}

JOB DESCRIPTION TEXT:
{req.jd_text}

IMPORTANT CONSTRAINTS:
- If a JD requirement references skills or technologies NOT present in the resume, list them ONLY in missing_must_haves.
- Do NOT attempt to "help" by assuming senior-level knowledge.
- Do NOT suggest legacy or adjacent technologies unless they explicitly appear in the resume.
- Evidence MUST come directly from the resume text.
- keywords_to_add MUST be words/phrases that appear in the RESUME TEXT.

RETURN JSON WITH EXACT SHAPE:
{{
  "tolerance": {req.tolerance},
  "mode": "{mode}",
  "allowed": {allowed},
  "disallowed": {disallowed},
  "missing_must_haves": [],
  "items": [
    {{
      "jd_requirement": "",
      "evidence": [],
      "keywords_to_add": [],
      "action": "keep"
    }}
  ],
  "global_keywords": []
}}

GUIDELINES:
- Use "keep" if the resume already clearly satisfies the requirement.
- Use "rewrite" if wording can be improved without adding new facts.
- Use "expand" ONLY if expanding details already present in resume.
- Use "add_skill_only" ONLY if the skill exists elsewhere in resume but not in a bullet (and it appears in the resume).
- Limit items to 6–10 total.
"""

    content = ollama_chat(system, user, temperature=0.0)
    parsed = extract_json_strict(content)

    plan = TailorPlan(**parsed)

    # Extra safety: enforce "keywords_to_add must appear in resume"
    resume_low = req.resume_text.lower()
    for item in plan.items:
        item.keywords_to_add = [k for k in item.keywords_to_add if k and k.lower() in resume_low]
    plan.global_keywords = [k for k in plan.global_keywords if k and k.lower() in resume_low]

    return plan

def parse_internal(req: ParseRequest) -> ParseResponse:
    mode = tolerance_profile(req.tolerance)

    system = (
        "You extract structured data from text.\n"
        "Rules:\n"
        "- Do NOT add new facts. Only extract what's present.\n"
        "- If missing, use null or empty arrays.\n"
        "- Return JSON ONLY. No markdown. No commentary.\n"
    )

    user = f"""MODE: {mode}
TASK: Extract two JSON objects: resume_json and jd_json.

RESUME TEXT:
{req.resume_text}

JOB DESCRIPTION TEXT:
{req.jd_text}

Return exactly this JSON shape:
{{
  "resume_json": {{
    "summary": null,
    "skills": [],
    "experience": [
      {{"company": null, "role": null, "dates": null, "bullets": []}}
    ],
    "education": []
  }},
  "jd_json": {{
    "title": null,
    "must_have": [],
    "nice_to_have": [],
    "responsibilities": [],
    "keywords": []
  }}
}}
"""

    content = ollama_chat(system, user, temperature=0.0)
    parsed = extract_json_strict(content)

    resume_json = ResumeJSON(**(parsed.get("resume_json") or {}))
    jd_json = JdJSON(**(parsed.get("jd_json") or {}))
    return ParseResponse(resume_json=resume_json, jd_json=jd_json)

def tailor_internal(req: TailorRequest) -> TailorResponse:
    mode, allowed, disallowed = policy_for_tolerance(req.tolerance)

    plan_obj = req.plan
    if plan_obj is None:
        plan_obj = build_plan_internal(ParseRequest(
            resume_text=req.resume_text,
            jd_text=req.jd_text,
            tolerance=req.tolerance,
        ))

    system = """You rewrite resumes for humans and ATS systems.


HARD RULES (MUST FOLLOW):
- Do NOT add new companies, roles, degrees, certifications, tools, or programming languages.
- Do NOT add technologies that do not already appear in the base resume.
- Do NOT invent metrics, numbers, percentages, or performance claims.
- Preserve all factual sections present in the original resume (especially EDUCATION and SKILLS).
- Do NOT write bullets that are just keyword lists.

STYLE RULES:
- Each bullet must describe an action + object (+ optional purpose/result).
- Each bullet may include at most 3–5 technologies (no mega-lists).
- Bullets should be concise and readable by a human recruiter.

OUTPUT:
- Plain text resume only.
- No JSON, no explanations, no commentary.
- No need other words that explains like it is rewrote resume, updated resume
- No "Here is the rewritten resume:" please!
"""

    plan_json = plan_obj.model_dump_json()

    user = f"""MODE: {mode}

ALLOWED ACTIONS:
{allowed}

DISALLOWED ACTIONS:
{disallowed}

BASE RESUME:
{req.resume_text}

JOB DESCRIPTION:
{req.jd_text}

TAILORING PLAN (JSON):
{plan_json}

TASK:
Rewrite the resume to better match the job description while remaining 100% truthful.

MANDATORY CONSTRAINTS:
- Keep the same employers, job titles, dates, degrees, and certifications.
- Keep EDUCATION section if present in the base resume.
- Keep SKILLS section; you may reorder or lightly rephrase but not expand with new skills.
- Rewrite bullets to align with JD language using ONLY evidence in the resume.
- Do NOT collapse bullets into keyword-heavy sentences or technology-dump bullets.

FORMATTING:
- Use clear section headers (SUMMARY, EXPERIENCE, EDUCATION, SKILLS).
- Keep 1–2 pages worth of content.
- Prefer clarity over keyword density.

Output ONLY the tailored resume text.
"""

    temp = 0.2 if mode == "creative" else 0.0
    content = ollama_chat(system, user, temperature=temp).strip()

    # Simple guard: if base has EDUCATION, output must have it
    if contains_education(req.resume_text) and not contains_education(content):
        raise HTTPException(status_code=400, detail="Tailored output removed EDUCATION section. Regenerate.")

    # Guard: block classic fake .NET language stuffing unless present in base resume
    banned_unless_present = ["Visual Basic", "VB.NET", "C++/CLI", "J#", "JScript.NET"]
    base_low = req.resume_text.lower()
    out_low = content.lower()
    for term in banned_unless_present:
        if term.lower() in out_low and term.lower() not in base_low:
            raise HTTPException(status_code=400, detail=f"Tailored output contained unsupported term: {term}")

    return TailorResponse(tailored_resume=content)

# =========================
# Routes (thin)
# =========================
@app.get("/health")
def health():
    return {"ok": True}

@app.post("/parse", response_model=ParseResponse)
def parse(req: ParseRequest):
    try:
        return parse_internal(req)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/plan", response_model=TailorPlan)
def plan(req: ParseRequest):
    try:
        return build_plan_internal(req)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/tailor", response_model=TailorResponse)
def tailor(req: TailorRequest):
    try:
        return tailor_internal(req)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/extract_jd", response_model=ExtractJdResponse)
def extract_jd(req: ExtractJdRequest):
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
        }
        r = requests.get(req.url, headers=headers, timeout=20)
        if r.status_code != 200:
            raise HTTPException(status_code=400, detail=f"Failed to fetch URL (status={r.status_code})")

        jd_text = extract_visible_text_from_html(r.text)

        # simple guard
        if len(jd_text) < 200:
            raise HTTPException(status_code=400, detail="Extracted text too short. Try pasting JD directly.")

        return ExtractJdResponse(jd_text=jd_text)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/resume_pdf")
def resume_pdf(req: PdfRequest):
    pdf_buf = render_resume_pdf(req.resume_text)
    filename = req.filename or "tailored_resume.pdf"

    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"'
    }
    return StreamingResponse(pdf_buf, media_type="application/pdf", headers=headers)

@app.post("/batch_zip")
def batch_zip(req: BatchZipRequest):
    # Safety: cap links
    urls = req.job_urls[:10]

    zip_buf = BytesIO()
    errors = []

    with zipfile.ZipFile(zip_buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for idx, url in enumerate(urls, start=1):
            try:
                jd_text = fetch_jd_text(url)

                # Generate tailored resume (no plan needed)
                out = tailor_internal(TailorRequest(
                    resume_text=req.base_resume_text,
                    jd_text=jd_text,
                    tolerance=req.tolerance,
                    plan=None,
                ))
                resume_txt = out.tailored_resume.strip()

                base_name = f"{idx:02d}_{slugify(url)}"

                if req.format in ("pdf", "pdf+txt"):
                    pdf = render_resume_pdf(resume_txt).getvalue()
                    zf.writestr(f"{base_name}.pdf", pdf)

                if req.format == "pdf+txt":
                    zf.writestr(f"{base_name}.txt", resume_txt)

            except Exception as e:
                errors.append(f"{idx:02d} {url} -> {str(e)}")

        # Always include errors file (even if empty)
        zf.writestr("errors.txt", "\n".join(errors) if errors else "OK")

        # (optional) include the input resume for traceability
        zf.writestr("base_resume.txt", req.base_resume_text)

    zip_buf.seek(0)
    headers = {"Content-Disposition": 'attachment; filename="tailored_resumes.zip"'}
    return StreamingResponse(zip_buf, media_type="application/zip", headers=headers)

