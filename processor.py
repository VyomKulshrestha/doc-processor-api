"""
Document processing pipeline: PDF extraction + Groq LLM classification.
"""

import io
import json
import os
import time
import pdfplumber
from groq import Groq

GROQ_MODEL = "llama-3.3-70b-versatile"

# System prompt that instructs the LLM to classify and extract fields
SYSTEM_PROMPT = """You are a document classification and field extraction engine.
Given the text content of a document, you must:

1. Classify the document type (e.g., "invoice", "contract", "receipt", "report", "letter", "resume", "tax_form", "bank_statement", "insurance_claim", "purchase_order", "other")
2. Assign a confidence score between 0.0 and 1.0 for your classification
3. Extract three specific fields:
   - document_date: The primary date of the document (format: YYYY-MM-DD). Use the most prominent date — issue date, document date, or statement date.
   - total_amount: The primary monetary amount (as a number, no currency symbols). For invoices this is the total; for contracts the contract value; for receipts the total paid.
   - counterparty: The other party involved (company name, person name, or organization).

Respond ONLY with valid JSON in this exact format, no markdown, no explanation:
{
  "document_type": "invoice",
  "confidence": 0.91,
  "extracted_fields": {
    "document_date": "2024-03-15",
    "total_amount": 4250.00,
    "counterparty": "Acme Corp Ltd"
  }
}

If a field cannot be determined, use null for that field's value.
If the document type is unclear, use "other" with a low confidence score.
"""


def extract_text_from_pdf(pdf_bytes: bytes) -> tuple[str, int]:
    """
    Extract text from PDF bytes using pdfplumber.
    Returns (extracted_text, page_count).
    Raises ValueError if no text can be extracted.
    """
    text_parts = []
    page_count = 0

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        page_count = len(pdf.pages)
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)

    full_text = "\n\n".join(text_parts).strip()

    if not full_text:
        raise ValueError("Could not extract text — PDF appears to be scanned or contains only images")

    return full_text, page_count


def classify_document(text: str) -> tuple[dict, int]:
    """
    Send extracted text to Groq LLM for classification and field extraction.
    Returns (result_dict, processing_time_ms).
    processing_time_ms measures ONLY the LLM call duration.
    """
    client = Groq(api_key=os.getenv("GROQ_API_KEY"))

    # Truncate text to avoid token limits — keep first ~6000 chars
    truncated_text = text[:6000]
    if len(text) > 6000:
        truncated_text += "\n\n[... document truncated for processing ...]"

    # Time only the LLM call
    start = time.perf_counter_ns()

    completion = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Classify this document and extract fields:\n\n{truncated_text}"}
        ],
        temperature=0.1,
        max_tokens=500,
        response_format={"type": "json_object"}
    )

    end = time.perf_counter_ns()
    processing_time_ms = int((end - start) / 1_000_000)

    response_text = completion.choices[0].message.content.strip()

    try:
        result = json.loads(response_text)
    except json.JSONDecodeError as e:
        raise ValueError(f"LLM returned invalid JSON: {e}")

    # Validate and normalize the response structure
    document_type = result.get("document_type", "other")
    confidence = result.get("confidence", 0.0)
    extracted_fields = result.get("extracted_fields", {})

    # Ensure all required fields exist (null if missing)
    normalized_fields = {
        "document_date": extracted_fields.get("document_date"),
        "total_amount": extracted_fields.get("total_amount"),
        "counterparty": extracted_fields.get("counterparty")
    }

    # Clamp confidence to [0, 1]
    confidence = max(0.0, min(1.0, float(confidence)))

    return {
        "document_type": document_type,
        "confidence": round(confidence, 2),
        "extracted_fields": normalized_fields
    }, processing_time_ms
