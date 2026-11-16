"""Upload pipeline: read one PDF, then match three documents into cases.

Kept free of web code so it can be tested on its own. A PDF is written to a
temporary file only while the model reads it, and is deleted straight after.
"""

import os
import tempfile
import time
from pathlib import Path
from typing import Any

import anthropic
from google.genai import errors as genai_errors

from app.agents.extraction import ExtractedDocument, extract_document
from app.agents.investigation import investigate
from app.agents.matching import match_documents
from app.schemas import CaseFile
from app.store import STORE, CaseExistsError

MAX_PDF_BYTES = 15 * 1024 * 1024
RETRIES = 3


class UploadError(Exception):
    """A problem the customer can understand. status is the HTTP status to answer with."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


def validate_pdf(data: bytes, limit: int | None = None) -> None:
    limit = MAX_PDF_BYTES if limit is None else limit
    if not data:
        raise UploadError(400, "The file is empty.")
    if len(data) > limit:
        raise UploadError(413, f"The file is too large (maximum {limit // (1024 * 1024)} MB).")
    if not data.startswith(b"%PDF"):
        raise UploadError(415, "Only PDF files are accepted.")


def extraction_configured() -> bool:
    """True when the model key for the chosen provider is set on the server."""
    if os.getenv("VENDORA_PROVIDER", "gemini") == "claude":
        return bool(os.getenv("ANTHROPIC_API_KEY"))
    return bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))


def _is_retryable(exc: Exception) -> bool:
    if isinstance(exc, genai_errors.ServerError):
        return True
    if isinstance(exc, genai_errors.ClientError):
        return exc.code == 429
    return isinstance(
        exc, anthropic.RateLimitError | anthropic.InternalServerError | anthropic.APIConnectionError
    )


def extract_pdf(data: bytes) -> ExtractedDocument:
    """Read one PDF with the model. The PDF is never kept."""
    validate_pdf(data)
    if not extraction_configured():
        raise UploadError(503, "Reading documents is not set up on this server yet.")

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as handle:
        handle.write(data)
        path = Path(handle.name)
    try:
        last_error: Exception | None = None
        for attempt in range(1, RETRIES + 1):
            try:
                return extract_document(path)
            except (genai_errors.APIError, anthropic.APIError) as exc:
                if not _is_retryable(exc):
                    raise UploadError(502, "The AI service refused this request.") from exc
                last_error = exc
                if attempt < RETRIES:
                    time.sleep(attempt)
            except ValueError as exc:
                raise UploadError(422, "Could not read this document. Is it a clear PDF?") from exc
        raise UploadError(503, "The AI service is busy. Try again in a minute.") from last_error
    finally:
        path.unlink(missing_ok=True)


def analyze_documents(
    invoice: ExtractedDocument, po: ExtractedDocument, contract: ExtractedDocument
) -> list[CaseFile]:
    findings = match_documents(invoice, po)
    return [
        investigate(finding, contract, case_id=f"{invoice.doc_id}-{index:02d}")
        for index, finding in enumerate(findings, start=1)
    ]


def store_cases(cases: list[CaseFile], tenant: str) -> list[dict[str, Any]]:
    """Put the cases in this customer's review queue. A repeat upload is not duplicated."""
    results = []
    for case in cases:
        try:
            STORE.add_case(case.model_dump(mode="json"), source="upload", tenant=tenant)
            state = "created"
        except CaseExistsError:
            state = "already_in_queue"
        results.append(
            {
                "case_id": case.case_id,
                "finding": case.finding.value,
                "delta": case.delta,
                "state": state,
            }
        )
    return results
