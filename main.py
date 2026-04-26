"""
Document Processing API
Two endpoints: POST /process-document and GET /result/{job_id}
Background processing via asyncio tasks.
"""

import asyncio
import uuid
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

from database import init_db, create_job, update_job_success, update_job_failure, get_job
from processor import extract_text_from_pdf, classify_document

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database on startup."""
    await init_db()
    yield


app = FastAPI(
    title="Document Processing API",
    description="Upload PDFs for AI-powered classification and field extraction",
    version="1.0.0",
    lifespan=lifespan
)


async def process_document_background(job_id: str, pdf_bytes: bytes):
    """
    Background task that runs after the response is returned.
    Extracts text, calls LLM, updates the database.
    """
    try:
        # Step 1: Extract text from PDF (runs in thread pool to avoid blocking)
        loop = asyncio.get_event_loop()
        text, page_count = await loop.run_in_executor(
            None, extract_text_from_pdf, pdf_bytes
        )

        # Step 2: Classify via Groq LLM (runs in thread pool — it's a sync HTTP call)
        result, processing_time_ms = await loop.run_in_executor(
            None, classify_document, text
        )

        # Step 3: Save success to database
        await update_job_success(
            job_id=job_id,
            document_type=result["document_type"],
            confidence=result["confidence"],
            extracted_fields=result["extracted_fields"],
            page_count=page_count,
            processing_time_ms=processing_time_ms
        )

    except ValueError as e:
        # Known errors: no text extracted, bad LLM response
        await update_job_failure(job_id, str(e))

    except Exception as e:
        # Unexpected errors
        await update_job_failure(job_id, f"Processing failed: {str(e)}")


@app.post("/process-document")
async def process_document(file: UploadFile = File(...)):
    """
    Upload a PDF for processing.
    Returns immediately with a job_id — processing happens in the background.
    """
    # Validate file type
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail="Only PDF files are accepted. Please upload a .pdf file."
        )

    # Read file contents
    pdf_bytes = await file.read()

    if len(pdf_bytes) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    # Generate unique job ID
    job_id = uuid.uuid4().hex[:8]

    # Create database record
    await create_job(job_id)

    # Fire off background processing — this does NOT block the response
    asyncio.create_task(process_document_background(job_id, pdf_bytes))

    return JSONResponse(
        status_code=202,
        content={
            "job_id": job_id,
            "status": "processing"
        }
    )


@app.get("/result/{job_id}")
async def get_result(job_id: str):
    """
    Poll for processing results by job_id.
    Returns current status — processing, complete, or failed.
    """
    job = await get_job(job_id)

    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

    return JSONResponse(content=job)


from fastapi.responses import JSONResponse, HTMLResponse

@app.get("/")
async def root():
    """Serve the frontend."""
    with open("index.html", "r") as f:
        html_content = f.read()
    return HTMLResponse(content=html_content, status_code=200)


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
