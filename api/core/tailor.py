from core.prompting import DEFAULT_SYSTEM_PROMPT, build_default_user_prompt, render_custom_prompt
from fastapi import HTTPException
from core.policy import policy_for_tolerance
from services.llm import llm_chat

def contains_education(text: str) -> bool:
    return "education" in (text or "").lower()

def tailor_text(
        resume_text: str,
        jd_text: str,
        tolerance: int,
        provider: str,
        model: str | None = None,
        prompt_mode: str = "default",
        custom_prompt: str | None = None
    ) -> str:
    mode, allowed, disallowed = policy_for_tolerance(tolerance)
    vars = {
        "MODE": mode,
        "RESUME": resume_text,
        "JD": jd_text,
        "ALLOWED": "\n".join(allowed),
        "DISALLOWED": "\n".join(disallowed),
    }
    
    system = DEFAULT_SYSTEM_PROMPT
    if prompt_mode == "custom":
        user = render_custom_prompt(custom_prompt, vars)
    else:
        user = build_default_user_prompt(mode, resume_text, jd_text)
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
