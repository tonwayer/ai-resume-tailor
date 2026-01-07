from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from schemas import (
    TailorRequest,
    TailorResponse,
    ExtractJdRequest,
    ExtractJdResponse,
    PdfRequest,
    BatchZipRequest,
)

from core.tailor import tailor_text
from services.jd_extract import fetch_jd_text
from services.pdf import render_resume_pdf
from services.batch import build_zip

router = APIRouter()

@router.get("/health")
def health():
    return {"ok": True}

@router.post("/tailor", response_model=TailorResponse)
def tailor(req: TailorRequest):
    try:
        out = tailor_text(req.resume_text, req.jd_text, req.tolerance, req.provider)
        return TailorResponse(tailored_resume=out)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/extract_jd", response_model=ExtractJdResponse)
def extract_jd(req: ExtractJdRequest):
    try:
        return ExtractJdResponse(jd_text=fetch_jd_text(req.url))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/resume_pdf")
def resume_pdf(req: PdfRequest):
    try:
        pdf_buf = render_resume_pdf(req.resume_text)
        filename = (req.filename or "tailored_resume.pdf").replace("\n", "").replace("\r", "")
        headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
        return StreamingResponse(pdf_buf, media_type="application/pdf", headers=headers)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/batch_zip")
def batch_zip(req: BatchZipRequest):
    try:
        zip_buf = build_zip(
            base_resume_text=req.base_resume_text,
            job_urls=req.job_urls,
            tolerance=req.tolerance,
            fmt=req.format,
            provider=req.provider
        )
        headers = {"Content-Disposition": 'attachment; filename="tailored_resumes.zip"'}
        return StreamingResponse(zip_buf, media_type="application/zip", headers=headers)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
