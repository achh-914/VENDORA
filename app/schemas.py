from enum import StrEnum

from pydantic import BaseModel, Field


class DiscrepancyType(StrEnum):
    PRICE_MISMATCH = "PRICE-MISMATCH"
    UNAGREED_FEE = "UNAGREED-FEE"
    QTY_VARIANCE = "QTY-VARIANCE"
    DUPLICATE_LINE = "DUPLICATE-LINE"
    TERMS_CONFLICT = "TERMS-CONFLICT"


class ProposedAction(StrEnum):
    HOLD_INVOICE = "HOLD_INVOICE"
    DRAFT_SUPPLIER_MESSAGE = "DRAFT_SUPPLIER_MESSAGE"
    ESCALATE = "ESCALATE"


class Evidence(BaseModel):
    doc: str
    page: int = Field(ge=1)
    ref: str


class CaseFile(BaseModel):
    case_id: str
    finding: DiscrepancyType
    delta: float
    evidence: list[Evidence] = Field(min_length=1)
    proposed_action: list[ProposedAction] = []
    requires_human_approval: bool = True
