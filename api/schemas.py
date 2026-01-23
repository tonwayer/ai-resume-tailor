from typing import List, Optional, Literal, Tuple

from pydantic import BaseModel, Field


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
    provider: Literal["ollama", "deepseek"] = "ollama"
    model: Optional[str] = None

    prompt_mode: Literal["default", "custom"] = "default"
    custom_prompt: Optional[str] = None

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
    provider: Literal["ollama", "deepseek"] = "ollama"
    model: Optional[str] = None

    prompt_mode: Literal["default", "custom"] = "default"
    custom_prompt: Optional[str] = None
