from app.agents.extraction import ExtractedDocument, ExtractedLine
from app.agents.matching import match_documents
from app.schemas import DiscrepancyType


def _line(description, quantity, unit_price, amount):
    return ExtractedLine(
        line_no=1,
        description=description,
        quantity=quantity,
        unit_price=unit_price,
        amount=amount,
        page=1,
    )


def _doc(doc_type, doc_id, currency, total, lines):
    return ExtractedDocument(
        doc_type=doc_type,
        doc_id=doc_id,
        currency=currency,
        total=total,
        total_page=1,
        lines=lines,
    )


def test_currency_symbol_is_normalized_in_evidence():
    invoice = _doc("invoice", "INV-1", "$", 500.0, [_line("XY-9 - Widget", 1, 500.0, 500.0)])
    po = _doc("purchase_order", "PO-1", "USD", 0.0, [])

    findings = match_documents(invoice, po)

    assert findings[0].type == DiscrepancyType.UNAGREED_FEE
    assert "USD 500.00" in findings[0].evidence[0].ref


def test_price_delta_has_no_float_noise():
    invoice = _doc("invoice", "INV-1", "USD", 3.3, [_line("AB-1 - Part", 3, 1.1, 3.3)])
    po = _doc("purchase_order", "PO-1", "USD", 3.0, [_line("AB-1 - Part", 3, 1.0, 3.0)])

    findings = match_documents(invoice, po)

    assert len(findings) == 1
    assert findings[0].type == DiscrepancyType.PRICE_MISMATCH
    assert findings[0].delta == 0.3
