"""Upload API: a customer sends PDFs, reads them, and gets cases for review."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from app import pipeline
from app.agents.extraction import ExtractedDocument
from app.auth import current_tenant
from app.pipeline import UploadError
from app.static_files import page

router = APIRouter()


class AnalyzeIn(BaseModel):
    invoice: ExtractedDocument
    po: ExtractedDocument
    contract: ExtractedDocument


@router.get("/upload", include_in_schema=False)
def upload_page() -> HTMLResponse:
    return page("upload.html")


@router.post("/extract", dependencies=[Depends(current_tenant)])
async def extract(request: Request) -> dict[str, Any]:
    """Read one PDF (sent as the raw request body) and return what was found."""
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > pipeline.MAX_PDF_BYTES:
        raise HTTPException(status_code=413, detail="The file is too large.")
    data = await request.body()
    try:
        document = await run_in_threadpool(pipeline.extract_pdf, data)
    except UploadError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.message) from None
    return document.model_dump(mode="json")


@router.post("/analyze")
def analyze(body: AnalyzeIn, tenant: str = Depends(current_tenant)) -> dict[str, Any]:
    """Match the three documents and queue every discrepancy for human review."""
    cases = pipeline.analyze_documents(body.invoice, body.po, body.contract)
    return {
        "documents": [body.invoice.doc_id, body.po.doc_id, body.contract.doc_id],
        "discrepancies": len(cases),
        "cases": pipeline.store_cases(cases, tenant),
    }
