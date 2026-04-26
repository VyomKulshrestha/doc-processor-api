# Document Processing API — Submission

## Live URL

`https://doc-processor-api.onrender.com`

*(Replace with your actual Render URL after deployment)*

## Curl Commands

### 1. Upload a PDF and get a job_id
```bash
curl -X POST https://doc-processor-api.onrender.com/process-document \
  -F "file=@invoice.pdf"
```

### 2. Poll for the result
```bash
curl https://doc-processor-api.onrender.com/result/{job_id}
```

## GitHub Repo

https://github.com/VyomKulshrestha/doc-processor-api

## Note

I used Groq's `llama-3.3-70b-versatile` because it reliably follows structured JSON output instructions, runs fast on Groq's LPU hardware (~500ms inference), and is available on their free tier. Background processing is handled via `asyncio.create_task()` — the POST endpoint creates a database record, fires off the PDF extraction and LLM call as a detached coroutine, and returns the job_id immediately without waiting. The specific thing that would break under real production load is the SQLite database: it uses file-level locking, so concurrent background tasks writing results would serialize and eventually throw "database is locked" errors. If this needed to handle 100 concurrent uploads, I would replace SQLite with PostgreSQL and swap `asyncio.create_task()` for a proper job queue like Celery with Redis, which decouples API serving from processing and lets workers scale independently.
