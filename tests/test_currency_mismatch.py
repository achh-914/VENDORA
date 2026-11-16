from app.agents.extraction import ExtractedDocument, ExtractedLine
from app.agents.investigation import investigate
from app.agents.matching import currency_code, match_documents
from app.schemas import DiscrepancyType, ProposedAction


def _doc(doc_type, doc_id, currency, total=100.0):
    line = ExtractedLine(
        line_no=1,
        description="A-1 - Widget",
        quantity=1,
        unit_price=total,
        amount=total,
        page=1,
    )
    return ExtractedDocument(
        doc_type=doc_type,
        doc_id=doc_id,
        currency=currency,
        total=total,
        total_page=1,
        lines=[line],
    )


def _contract():
    return ExtractedDocument(doc_type="contract", doc_id="C-1", clauses=[])


def test_different_currencies_are_flagged_not_compared():
    invoice = _doc("invoice", "INV-1", "EUR", 100.0)
    po = _doc("purchase_order", "PO-1", "USD", 90.0)

    findings = match_documents(invoice, po)

    assert len(findings) == 1
    assert findings[0].type == DiscrepancyType.CURRENCY_MISMATCH
    assert "EUR" in findings[0].summary
    assert "USD" in findings[0].summary


def test_symbol_and_code_of_same_currency_do_not_clash():
    invoice = _doc("invoice", "INV-1", "$", 100.0)
    po = _doc("purchase_order", "PO-1", "USD", 100.0)

    assert match_documents(invoice, po) == []


def test_missing_currency_is_not_a_mismatch():
    invoice = _doc("invoice", "INV-1", None, 100.0)
    po = _doc("purchase_order", "PO-1", "USD", 100.0)

    assert match_documents(invoice, po) == []


def test_currency_mismatch_goes_to_a_human():
    invoice = _doc("invoice", "INV-1", "EUR")
    po = _doc("purchase_order", "PO-1", "USD")
    finding = match_documents(invoice, po)[0]

    case = investigate(finding, _contract())

    assert case.proposed_action == [ProposedAction.ESCALATE]
    assert case.requires_human_approval is True


def test_more_currency_symbols():
    cases = {"₹": "INR", "¥": "JPY", "zł": "PLN", "CHF": "CHF", "aed": "AED"}
    for raw, code in cases.items():
        assert currency_code(_doc("invoice", "I", raw)) == code
