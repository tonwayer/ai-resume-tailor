from fastapi import HTTPException
from core.policy import policy_for_tolerance
from services.llm import deepseek_chat, llm_chat, ollama_chat

def contains_education(text: str) -> bool:
    return "education" in (text or "").lower()

def tailor_text(resume_text: str, jd_text: str, tolerance: int, provider: str, model: str | None = None) -> str:
    mode, allowed, disallowed = policy_for_tolerance(tolerance)
    system = """You rewrite resumes for humans and ATS systems.

GLOBAL HARD RULES (ALWAYS):
- Do NOT add new employers, job titles, employment dates, degrees, or certifications.
- Do NOT invent numbers/metrics (%, $, latency numbers, user counts, revenue, etc).
- Do NOT copy sentences verbatim from the Job Description.
- Do NOT output commentary or explanations. Output only the resume text.
- Do NOT decrease number of bullets
- Do NOT ommit employers or education or dates, certifications or any internship experices

TRUTHFULNESS:
- Treat employers/titles/dates/education as fixed facts.
- You may rewrite wording, reorder content, and reframe responsibilities to match the JD.
- If you add skills/keywords, they must be plausible for the role and consistent with the candidate's seniority, but avoid claiming highly specific tools/processes that contradict the base resume.

STYLE RULES (ALWAYS):
- Keep clean sections: SUMMARY, EXPERIENCE, EDUCATION, SKILLS.
- Each bullet must be action + object (+ optional purpose/result).
- Avoid keyword-dump bullets. Max 4 technologies per bullet.

MODE RULES:
1) CONSERVATIVE
   - Keep the resume very close to the original.
   - Do NOT add new bullets.
   - Do NOT add new skill categories/sections.
   - Only small edits: tighten wording, reorder within a section, minor keyword insertions.
   - Only add skills that already appear somewhere in the base resume.

2) BALANCED
   - Moderate edits.
   - You MAY add up to 2 new "main skills" (high-level skills) that appear in the JD even if not in the base resume,
     BUT they must be generic and plausible (e.g., "CI/CD", "Performance tuning", "System design").
   - You MAY add up to 4 additional bullets total across all roles.
   - New bullets must be generic responsibilities consistent with existing role scope; do NOT name brand-new tools in new bullets.

3) CREATIVE
   - Aggressive alignment to the JD while keeping fixed facts (employers/titles/dates/education).
   - You MAY rewrite most bullets and the summary heavily.
   - You MAY add JD keywords and skills broadly in SKILLS and bullets, but:
     - Do NOT paste JD sentences; paraphrase.
     - Do NOT invent metrics.
     - Do NOT add niche tools unless they are common/expected for the role AND do not contradict the base resume.
"""
    user = f"""MODE: {mode}
 
BASE RESUME (source of fixed facts):
{resume_text}

JOB DESCRIPTION (target):
{jd_text}

TASK:
Generate a tailored resume that matches the JD according to MODE RULES.

OUTPUT REQUIREMENTS:
- Preserve these facts exactly: employers, dates, degree(s), university name(s).
- Keep sections in this order: SUMMARY, EXPERIENCE, EDUCATION, SKILLS.
- Do NOT include any extra headers like "Tailored Resume" or "Here is...".
- NO "Here is the rewritten resume:" please!
- Do NOT copy JD sentences; use your own wording.
- Keep the resume realistic and consistent.

SPECIAL MODE INSTRUCTIONS:
- If MODE=CONSERVATIVE: keep wording close to base; do not add bullets; skills must already exist in base.
- If MODE=BALANCED: allow up to 2 new generic skills; allow up to 2 new bullets total without adding new tools.
- If MODE=CREATIVE: add most of key words from JD to resume through bullets and skills section. you can even update job titles. rewrite aggressively to match JD; you may add many JD keywords/skills, but keep it believable; no metrics.
- If MODE=EVIL: only keep employers/dates/education! You can do whatever to match resume to JD. rewrite all the bullets!

Output ONLY the resume text.
"""
    if mode == "evil":
        temp = 0.5
    elif mode == "creative":
        temp = 0.3
    elif mode == "conservative":
        temp = 0.1
    else:
        temp = 0.0

    content = llm_chat(provider, system, user, temperature=temp, model=model).strip()

    if contains_education(resume_text) and not contains_education(content):
        raise HTTPException(status_code=400, detail="Tailored output removed EDUCATION section. Regenerate.")

    return content

