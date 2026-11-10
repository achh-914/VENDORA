from app.agents.extraction import ExtractedDocument, ExtractedLine
from app.agents.matching import match_documents


def test_item_missing_from_po_is_flagged():
    invoice = ExtractedDocument(
        doc_type="invoice",
        doc_id="INV-1",
        total=500.0,
        total_page=1,
        lines=[
            ExtractedLine(
                line_no=1,
                description="XY-9 - Extra widget",
                quantity=1,
                unit_price=500.0,
                amount=500.0,
                page=1,
            )
        ],
    )
    po = ExtractedDocument(
        doc_type="purchase_order", doc_id="PO-1", total=0.0, total_page=1, lines=[]
    )

    findings = match_documents(invoice, po)

    assert len(findings) == 1
    assert findings[0].delta == 500.0
