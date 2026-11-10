from app.agents.extraction import ExtractedDocument, ExtractedLine
from app.agents.matching import match_documents
from app.schemas import DiscrepancyType


def _doc(doc_type, doc_id, total):
    line = ExtractedLine(
        line_no=1,
        description="A-1 - Widget",
        quantity=10,
        unit_price=100.0,
        amount=1000.0,
        page=1,
    )
    return ExtractedDocument(
        doc_type=doc_type, doc_id=doc_id, total=total, total_page=1, lines=[line]
    )


def test_unexplained_total_gap_is_flagged():
    invoice = _doc("invoice", "INV-1", 1200.0)
    po = _doc("purchase_order", "PO-1", 1000.0)

    findings = match_documents(invoice, po)

    assert len(findings) == 1
    assert findings[0].type == DiscrepancyType.PRICE_MISMATCH
    assert findings[0].delta == 200.0
