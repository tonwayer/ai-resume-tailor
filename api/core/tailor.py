from fastapi import HTTPException
from core.policy import policy_for_tolerance
from services.llm import ollama_chat

def contains_education(text: str) -> bool:
    return "education" in (text or "").lower()

def tailor_text(resume_text: str, jd_text: str, tolerance: int) -> str:
    mode, allowed, disallowed = policy_for_tolerance(tolerance)

    system = """You rewrite resumes for humans and ATS systems.

HARD RULES (MUST FOLLOW):
- Do NOT add new companies, roles, degrees, certifications, tools, or programming languages.
- Do NOT add technologies that do not already appear in the base resume.
- Do NOT invent metrics, numbers, percentages, or performance claims.
- Preserve all factual sections present in the original resume (especially EDUCATION and SKILLS).
- Do NOT write bullets that are just keyword lists.

STYLE RULES:
- Each bullet must describe an action + object (+ optional purpose/result).
- Each bullet may include at most 3-5 technologies (no mega-lists).
- Output plain text resume only (no commentary).
"""

    user = f"""MODE: {mode}

ALLOWED ACTIONS:
{allowed}

DISALLOWED ACTIONS:
{disallowed}

BASE RESUME:
{resume_text}

JOB DESCRIPTION:
{jd_text}

TASK:
Rewrite the resume to better match the job description while remaining 100% truthful.

MANDATORY CONSTRAINTS:
- Keep the same employers, job titles, dates, degrees, and certifications.
- Keep EDUCATION section if present in the base resume.
- Keep SKILLS section; you may reorder or lightly rephrase but not expand with new skills.
- Do NOT collapse bullets into keyword-heavy sentences or technology-dump bullets.

FORMATTING:
- Use clear section headers (SUMMARY, EXPERIENCE, EDUCATION, SKILLS).
- Keep 1–2 pages worth of content.

Output ONLY the tailored resume text.
"""

    temp = 0.2 if mode == "creative" else 0.0
    content = ollama_chat(system, user, temperature=temp).strip()

    if contains_education(resume_text) and not contains_education(content):
        raise HTTPException(status_code=400, detail="Tailored output removed EDUCATION section. Regenerate.")

    banned_unless_present = ["Visual Basic", "VB.NET", "C++/CLI", "J#", "JScript.NET"]
    base_low = resume_text.lower()
    out_low = content.lower()
    for term in banned_unless_present:
        if term.lower() in out_low and term.lower() not in base_low:
            raise HTTPException(status_code=400, detail=f"Tailored output contained unsupported term: {term}")

    return content
