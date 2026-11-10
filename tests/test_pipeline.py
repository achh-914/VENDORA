from pathlib import Path

from app.agents.extraction import ExtractedDocument
from app.agents.matching import match_documents
from app.schemas import DiscrepancyType

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name):
    return ExtractedDocument.model_validate_json((FIXTURES / name).read_text())


def test_invoice_vs_po_finds_unagreed_freight():
    findings = match_documents(_load("invoice.json"), _load("po.json"))

    assert len(findings) == 1
    finding = findings[0]
    assert finding.type == DiscrepancyType.UNAGREED_FEE
    assert finding.delta == 3000.0
    assert finding.evidence[0].page == 1