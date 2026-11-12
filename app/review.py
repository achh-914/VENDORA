"""Review dashboard API: list cases, record human decisions, read the audit trail."""

from dataclasses import asdict
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field, field_validator

from app.demo_case import DEMO_CASE
from app.schemas import CaseFile
from app.store import (
    STORE,
    CaseClosedError,
    CaseExistsError,
    CaseNotFoundError,
    CaseRecord,
    Decision,
)

router = APIRouter()
UI_FILE = Path(__file__).parent / "static" / "review.html"


class DecisionIn(BaseModel):
    decision: Decision
    decided_by: str = Field(min_length=1, max_length=80)
    comment: str = Field(default="", max_length=2000)

    @field_validator("decided_by")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            msg = "decided_by must not be blank"
            raise ValueError(msg)
        return value


def _summary(record: CaseRecord) -> dict[str, Any]:
    case = record.case
    return {
        "case_id": case["case_id"],
        "finding": case["finding"],
        "delta": case["delta"],
        "status": record.status,
        "evidence_count": len(case["evidence"]),
        "source": record.source,
        "created_at": record.created_at,
    }


@router.get("/review", include_in_schema=False)
def review_page() -> HTMLResponse:
    return HTMLResponse(UI_FILE.read_text(encoding="utf-8"))


@router.get("/cases")
def list_cases() -> list[dict[str, Any]]:
    return [_summary(record) for record in STORE.all_cases()]


@router.post("/cases", status_code=201)
def create_case(case: CaseFile) -> dict[str, Any]:
    try:
        record = STORE.add_case(case.model_dump(mode="json"), source="api")
    except CaseExistsError:
        raise HTTPException(status_code=409, detail="Case already exists") from None
    return asdict(record)


@router.post("/demo/case", status_code=201)
def create_demo_case() -> dict[str, Any]:
    case = CaseFile.model_validate(DEMO_CASE)
    try:
        record = STORE.add_case(case.model_dump(mode="json"), source="demo")
    except CaseExistsError:
        raise HTTPException(status_code=409, detail="Demo case already exists") from None
    return asdict(record)


@router.get("/cases/{case_id}")
def get_case(case_id: str) -> dict[str, Any]:
    try:
        return asdict(STORE.get(case_id))
    except CaseNotFoundError:
        raise HTTPException(status_code=404, detail="Case not found") from None


@router.get("/cases/{case_id}/audit")
def get_audit(case_id: str) -> dict[str, Any]:
    try:
        STORE.get(case_id)
    except CaseNotFoundError:
        raise HTTPException(status_code=404, detail="Case not found") from None
    events, chain_ok = STORE.events_for(case_id)
    return {"events": [asdict(event) for event in events], "chain_ok": chain_ok}


@router.post("/cases/{case_id}/decision")
def decide(case_id: str, body: DecisionIn) -> dict[str, Any]:
    try:
        record = STORE.decide(case_id, body.decision, body.decided_by, body.comment)
    except CaseNotFoundError:
        raise HTTPException(status_code=404, detail="Case not found") from None
    except CaseClosedError:
        raise HTTPException(status_code=409, detail="Case is already closed") from None
    return asdict(record)
