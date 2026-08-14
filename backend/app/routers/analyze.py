"""
Routes for uploading a CV, running analysis, fetching a single result,
and downloading the summary report.
"""
import logging

from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import Response

from app import database
from app.extraction import extract_text, ExtractionError
from app.gemini_analyzer import analyze_cv, GeminiAnalysisError
from app.config import settings
from app.report import generate_text_report, generate_pdf_report

logger = logging.getLogger("cv_analyzer.routes.analyze")

router = APIRouter(prefix="/api", tags=["analysis"])


@router.post("/analyze")
async def analyze_cv_endpoint(
    file: UploadFile = File(...),
    session_id: str = Form(...),
    job_description: str = Form(default=""),
):
    """
    Accepts a PDF/DOCX file + session_id (and optional job_description),
    extracts text, runs Gemini analysis, stores the result, and returns it.
    """
    if not session_id or not session_id.strip():
        raise HTTPException(status_code=400, detail="session_id is required.")

    # --- Basic file validation ---
    file_bytes = await file.read()

    if len(file_bytes) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    if len(file_bytes) > settings.MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"File exceeds the {settings.MAX_FILE_SIZE_MB}MB size limit.",
        )

    if not file.filename:
        raise HTTPException(status_code=400, detail="Uploaded file has no filename.")

    # --- Text extraction ---
    try:
        extracted = extract_text(file.filename, file_bytes)
    except ExtractionError as e:
        raise HTTPException(status_code=422, detail=str(e))

    # --- Gemini analysis ---
    try:
        analysis = analyze_cv(extracted.text, job_description=job_description)
    except GeminiAnalysisError as e:
        raise HTTPException(status_code=502, detail=f"Analysis failed: {e}")

    # --- Persist ---
    record = await database.save_analysis(
        session_id=session_id.strip(),
        filename=file.filename,
        analysis=analysis,
        raw_text_char_count=extracted.char_count,
        job_description_provided=bool(job_description.strip()),
    )

    return record


@router.get("/analysis/{analysis_id}")
async def get_analysis(analysis_id: str):
    record = await database.get_analysis_by_id(analysis_id)
    if not record:
        raise HTTPException(status_code=404, detail="Analysis not found.")
    return record


@router.delete("/analysis/{analysis_id}")
async def delete_analysis(analysis_id: str, session_id: str):
    deleted = await database.delete_analysis(analysis_id, session_id)
    if not deleted:
        raise HTTPException(
            status_code=404, detail="Analysis not found for this session."
        )
    return {"deleted": True}


@router.get("/analysis/{analysis_id}/report")
async def download_report(analysis_id: str, format: str = "pdf"):
    record = await database.get_analysis_by_id(analysis_id)
    if not record:
        raise HTTPException(status_code=404, detail="Analysis not found.")

    safe_name = "".join(
        c for c in record.filename.rsplit(".", 1)[0] if c.isalnum() or c in (" ", "_", "-")
    ).strip() or "cv_report"

    if format == "txt":
        content = generate_text_report(record)
        return Response(
            content=content,
            media_type="text/plain",
            headers={
                "Content-Disposition": f'attachment; filename="{safe_name}_report.txt"'
            },
        )

    # default: pdf
    pdf_bytes = generate_pdf_report(record)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_name}_report.pdf"'
        },
    )
