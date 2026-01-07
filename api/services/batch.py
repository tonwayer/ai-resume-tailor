import re
import zipfile
from io import BytesIO
from typing import List, Literal

from services.jd_extract import fetch_jd_text
from services.pdf import render_resume_pdf
from core.tailor import tailor_text  # we’ll create this

def slugify(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"https?://", "", s)
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s[:60] or "job"

def build_zip(
    base_resume_text: str,
    job_urls: List[str],
    tolerance: int,
    fmt: Literal["pdf", "pdf+txt"],
    provider: Literal["ollama", "deepseek"],
) -> BytesIO:
    zip_buf = BytesIO()
    errors = []

    with zipfile.ZipFile(zip_buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for idx, url in enumerate(job_urls[:10], start=1):
            try:
                jd_text = fetch_jd_text(url)
                resume_txt = tailor_text(base_resume_text, jd_text, tolerance, provider).strip()

                base_name = f"{idx:02d}_{slugify(url)}"
                pdf = render_resume_pdf(resume_txt).getvalue()
                zf.writestr(f"{base_name}.pdf", pdf)

                if fmt == "pdf+txt":
                    zf.writestr(f"{base_name}.txt", resume_txt)

            except Exception as e:
                errors.append(f"{idx:02d} {url} -> {str(e)}")

        zf.writestr("errors.txt", "\n".join(errors) if errors else "OK")
        zf.writestr("base_resume.txt", base_resume_text)

    zip_buf.seek(0)
    return zip_buf
