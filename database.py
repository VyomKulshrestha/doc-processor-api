"""
SQLite database layer for document processing jobs.
Uses aiosqlite for non-blocking database access.
"""

import aiosqlite
import json
import os

DB_PATH = os.getenv("DB_PATH", "jobs.db")


async def init_db():
    """Create the jobs table if it doesn't exist."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY,
                status TEXT NOT NULL DEFAULT 'processing',
                document_type TEXT,
                confidence REAL,
                extracted_fields TEXT,
                page_count INTEGER,
                processing_time_ms INTEGER,
                error TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.commit()


async def create_job(job_id: str):
    """Insert a new job record with 'processing' status."""
    default_fields = json.dumps({
        "document_date": None,
        "total_amount": None,
        "counterparty": None
    })
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO jobs (job_id, status, extracted_fields)
               VALUES (?, 'processing', ?)""",
            (job_id, default_fields)
        )
        await db.commit()


async def update_job_success(
    job_id: str,
    document_type: str,
    confidence: float,
    extracted_fields: dict,
    page_count: int,
    processing_time_ms: int
):
    """Mark a job as complete with extracted data."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """UPDATE jobs
               SET status = 'complete',
                   document_type = ?,
                   confidence = ?,
                   extracted_fields = ?,
                   page_count = ?,
                   processing_time_ms = ?,
                   error = NULL
               WHERE job_id = ?""",
            (
                document_type,
                confidence,
                json.dumps(extracted_fields),
                page_count,
                processing_time_ms,
                job_id
            )
        )
        await db.commit()


async def update_job_failure(job_id: str, error_message: str):
    """Mark a job as failed with an error message."""
    default_fields = json.dumps({
        "document_date": None,
        "total_amount": None,
        "counterparty": None
    })
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """UPDATE jobs
               SET status = 'failed',
                   document_type = NULL,
                   confidence = NULL,
                   extracted_fields = ?,
                   page_count = NULL,
                   processing_time_ms = NULL,
                   error = ?
               WHERE job_id = ?""",
            (default_fields, error_message, job_id)
        )
        await db.commit()


async def get_job(job_id: str) -> dict | None:
    """Retrieve a job by ID. Returns None if not found."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM jobs WHERE job_id = ?", (job_id,)
        )
        row = await cursor.fetchone()
        if row is None:
            return None

        return {
            "job_id": row["job_id"],
            "status": row["status"],
            "document_type": row["document_type"],
            "confidence": row["confidence"],
            "extracted_fields": json.loads(row["extracted_fields"]) if row["extracted_fields"] else {
                "document_date": None,
                "total_amount": None,
                "counterparty": None
            },
            "page_count": row["page_count"],
            "processing_time_ms": row["processing_time_ms"],
            "error": row["error"]
        }
