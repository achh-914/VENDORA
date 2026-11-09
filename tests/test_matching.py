from app.agents.extraction import ExtractedDocument, ExtractedLine
from app.agents.matching import match_documents
from app.schemas import DiscrepancyType


def line(no, description, qty, price, page=1):
    return ExtractedLine(
        line_no=no,
        description=description,
        quantity=qty,
        unit_price=price,
        amount=qty * price,
        page=page,
    )


def doc(doc_type, doc_id, lines, total):
    return ExtractedDocument(
        doc_type=doc_type, doc_id=doc_id, lines=lines, total=total, total_page=1
    )


def po_doc():
    return doc(
        "purchase_order",
        "PO-4471",
        [
            line(1, "SM-200 - Industrial sensor module", 100, 90.0),
            line(2, "MB-10 - Mounting bracket", 200, 15.0),
            line(3, "CA-5 - Cable assembly", 150, 20.0),
        ],
        15000.0,
    )


def base_invoice_lines():
    return [
        line(1, "SM-200 - Industrial sensor module", 100, 90.0),
        line(2, "MB-10 - Mounting bracket", 200, 15.0),
        line(3, "CA-5 - Cable assembly", 150, 20.0),
    ]


def test_unagreed_freight_fee():
    lines = base_invoice_lines() + [line(4, "Freight surcharge", 1, 3000.0)]
    invoice = doc("invoice", "INV-2041", lines, 18000.0)

    findings = match_documents(invoice, po_doc())

    assert len(findings) == 1
    finding = findings[0]
    assert finding.type == DiscrepancyType.UNAGREED_FEE
    assert finding.delta == 3000.0
    assert [e.doc for e in finding.evidence] == ["INV-2041", "PO-4471"]
    assert "Freight surcharge" in finding.evidence[0].ref


def test_price_mismatch():
    lines = base_invoice_lines()
    lines[0] = line(1, "SM-200 - Industrial sensor module", 100, 95.0)
    invoice = doc("invoice", "INV-2041", lines, 15500.0)

    findings = match_documents(invoice, po_doc())

    assert [f.type for f in findings] == [DiscrepancyType.PRICE_MISMATCH]
    assert findings[0].delta == 500.0


def test_quantity_variance():
    lines = base_invoice_lines()
    lines[0] = line(1, "SM-200 - Industrial sensor module", 120, 90.0)
    invoice = doc("invoice", "INV-2041", lines, 16800.0)

    findings = match_documents(invoice, po_doc())

    assert [f.type for f in findings] == [DiscrepancyType.QTY_VARIANCE]
    assert findings[0].delta == 1800.0


def test_duplicate_line():
    lines = base_invoice_lines() + [line(4, "MB-10 - Mounting bracket", 200, 15.0)]
    invoice = doc("invoice", "INV-2041", lines, 18000.0)

    findings = match_documents(invoice, po_doc())

    assert [f.type for f in findings] == [DiscrepancyType.DUPLICATE_LINE]
    assert findings[0].delta == 3000.0


def test_clean_invoice_has_no_findings():
    invoice = doc("invoice", "INV-2041", base_invoice_lines(), 15000.0)
    assert match_documents(invoice, po_doc()) == []
