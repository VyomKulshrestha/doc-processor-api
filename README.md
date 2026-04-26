# Document Processing API

A FastAPI backend that accepts PDF uploads, classifies documents using Groq's LLM, extracts key fields, and returns results via async polling.

## Architecture

```
POST /process-document
  → Read PDF bytes
  → Generate job_id, save to SQLite as "processing"
  → Return { job_id, status: "processing" } immediately (HTTP 202)
  → Fire asyncio.create_task() for background work:
      → Extract text (pdfplumber, in thread pool)
      → Classify + extract fields (Groq LLM, in thread pool)
      → Update SQLite row with results

GET /result/{job_id}
  → Query SQLite
  → Return current status (processing | complete | failed)
```

## Setup

```bash
# Clone
git clone https://github.com/YOUR_USERNAME/doc-processor-api.git
cd doc-processor-api

# Install
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env and add your Groq API key

# Run
python main.py
```

## API Usage

### Upload a PDF
```bash
curl -X POST https://YOUR_URL/process-document \
  -F "file=@invoice.pdf"
```

Response:
```json
{
  "job_id": "a3f8c2d1",
  "status": "processing"
}
```

### Poll for results
```bash
curl https://YOUR_URL/result/a3f8c2d1
```

Response (complete):
```json
{
  "job_id": "a3f8c2d1",
  "status": "complete",
  "document_type": "invoice",
  "confidence": 0.91,
  "extracted_fields": {
    "document_date": "2024-03-15",
    "total_amount": 4250.00,
    "counterparty": "Acme Corp Ltd"
  },
  "page_count": 3,
  "processing_time_ms": 1820,
  "error": null
}
```

## Tech Stack

- **FastAPI** — async Python web framework
- **pdfplumber** — PDF text extraction
- **Groq** (`llama-3.3-70b-versatile`) — document classification + field extraction
- **SQLite** (via aiosqlite) — job storage
- **Docker** — containerized deployment

## Notes

**Groq model:** `llama-3.3-70b-versatile` — chosen for its strong instruction-following on structured JSON output, fast inference on Groq's hardware, and generous free-tier rate limits. Good balance of quality and speed for document classification.

**Background processing:** Uses `asyncio.create_task()` to fire off the processing pipeline after returning the HTTP response. The blocking calls (PDF parsing, Groq API) run in FastAPI's default thread pool via `run_in_executor()` so they don't block the event loop.

**What would break under production load:** The SQLite database — it uses file-level locking, so concurrent writes from multiple background tasks will serialize and eventually bottleneck. Under heavy load, `database is locked` errors would start appearing.

**For 100 concurrent uploads:** Replace SQLite with PostgreSQL and swap `asyncio.create_task()` for a proper job queue (Celery + Redis or arq) with dedicated worker processes. This decouples the API server from processing, lets you scale workers independently, and survives server restarts without losing in-flight jobs.
