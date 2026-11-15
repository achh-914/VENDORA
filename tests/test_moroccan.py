"""Moroccan procurement documents: French wording, DH currency and HT/TVA/TTC totals."""

from pathlib import Path

import pytest

from app.agents.extraction import ExtractedClause, ExtractedDocument, ExtractedLine
from app.agents.investigation import find_fee_clause, investigate
from app.agents.matching import currency_code, match_documents
from app.schemas import CaseFile, DiscrepancyType, ProposedAction


def _line(line_no, description, quantity, unit_price, amount):
    return ExtractedLine(
        line_no=line_no,
        description=description,
        quantity=quantity,
        unit_price=unit_price,
        amount=amount,
        page=1,
    )


def _doc(doc_type, doc_id, total, lines, **extra):
    return ExtractedDocument(
        doc_type=doc_type,
        doc_id=doc_id,
        currency="MAD",
        total=total,
        total_page=1,
        lines=lines,
        **extra,
    )


def _po(total=10000.0, **extra):
    lines = [
        _line(1, "Câble réseau Cat6 - bobine", 10, 500.0, 5000.0),
        _line(2, "Prise murale RJ45", 100, 50.0, 5000.0),
    ]
    return _doc("purchase_order", "BC-2026-119", total, lines, **extra)


def _invoice(total, extra_lines=(), **extra):
    lines = [
        _line(1, "CABLE RESEAU CAT6 - Bobine", 10, 500.0, 5000.0),
        _line(2, "Prise murale  RJ45", 100, 50.0, 5000.0),
        *extra_lines,
    ]
    return _doc("invoice", "FA-2026-0452", total, lines, **extra)


def _contract(*clauses):
    return ExtractedDocument(
        doc_type="contract",
        doc_id="CT-2026-07",
        currency="MAD",
        clauses=[ExtractedClause(number=n, text=t, page=2) for n, t in clauses],
    )


FREIGHT_LINE = _line(3, "Frais de transport", 1, 800.0, 800.0)
FRENCH_FREIGHT_CLAUSE = (
    "5.2",
    (
        "Les frais de transport et de livraison sont inclus dans le prix unitaire. "
        "Le Fournisseur ne peut pas facturer séparément le transport, "
        "sauf accord écrit préalable à la commande."
    ),
)


def test_accents_case_and_spaces_do_not_create_false_findings():
    assert match_documents(_invoice(10000.0), _po()) == []


def test_invoice_with_tax_breakdown_matches_a_pre_tax_po():
    invoice = _invoice(12000.0, subtotal=10000.0, tax=2000.0)

    assert match_documents(invoice, _po()) == []


def test_pre_tax_total_is_derived_from_total_and_tax():
    invoice = _invoice(12000.0, tax=2000.0)

    assert match_documents(invoice, _po()) == []


def test_tax_inclusive_gap_is_flagged_with_a_vat_hint():
    findings = match_documents(_invoice(12000.0), _po())

    assert len(findings) == 1
    assert findings[0].type == DiscrepancyType.PRICE_MISMATCH
    assert findings[0].delta == 2000.0
    assert "20% VAT" in findings[0].summary


def test_a_real_gap_after_tax_is_still_flagged_without_a_vat_hint():
    invoice = _invoice(12600.0, subtotal=10500.0, tax=2100.0)

    findings = match_documents(invoice, _po())

    assert len(findings) == 1
    assert findings[0].delta == 500.0
    assert "VAT" not in findings[0].summary


def test_unagreed_fee_with_tax_is_reported_at_its_pre_tax_amount():
    invoice = _invoice(12960.0, [FREIGHT_LINE], subtotal=10800.0, tax=2160.0)

    findings = match_documents(invoice, _po())

    assert [f.type for f in findings] == [DiscrepancyType.UNAGREED_FEE]
    assert findings[0].delta == 800.0
    assert "MAD 800.00" in findings[0].evidence[0].ref


@pytest.mark.parametrize("raw", ["DH", "dh", "Dhs", "MAD", "mad", "درهم"])
def test_dirham_spellings_become_mad(raw):
    assert currency_code(ExtractedDocument(doc_type="invoice", doc_id="X", currency=raw)) == "MAD"


def test_other_currencies_keep_working():
    usd = ExtractedDocument(doc_type="invoice", doc_id="X", currency="$")
    eur = ExtractedDocument(doc_type="invoice", doc_id="X", currency="eur")

    assert (currency_code(usd), currency_code(eur)) == ("USD", "EUR")


def test_french_freight_clause_is_found_and_cited():
    contract = _contract(
        ("5.1", "Le délai de livraison est de quinze jours."),
        FRENCH_FREIGHT_CLAUSE,
    )

    clause = find_fee_clause(contract)

    assert clause is not None and clause.number == "5.2"


def test_french_unagreed_fee_gets_hold_and_supplier_message():
    invoice = _invoice(10800.0, [FREIGHT_LINE])
    finding = match_documents(invoice, _po())[0]

    case = investigate(finding, _contract(FRENCH_FREIGHT_CLAUSE), "FA-2026-0452-01")

    assert case.proposed_action == [
        ProposedAction.HOLD_INVOICE,
        ProposedAction.DRAFT_SUPPLIER_MESSAGE,
    ]
    assert case.evidence[-1].doc == "CT-2026-07"
    assert case.evidence[-1].ref.startswith("clause 5.2")


def test_a_clause_that_only_mentions_delivery_is_not_cited():
    invoice = _invoice(10800.0, [FREIGHT_LINE])
    finding = match_documents(invoice, _po())[0]
    contract = _contract(("5.1", "Le délai de livraison est de quinze jours."))

    case = investigate(finding, contract)

    assert case.proposed_action == [ProposedAction.ESCALATE]
    assert case.notes == []


def test_french_exception_clause_adds_a_check_note():
    finding = match_documents(_invoice(10800.0, [FREIGHT_LINE]), _po())[0]

    case = investigate(finding, _contract(FRENCH_FREIGHT_CLAUSE))

    assert len(case.notes) == 1
    assert "5.2" in case.notes[0] and "agreed in writing" in case.notes[0]


def test_english_exception_clause_adds_a_check_note():
    clause = (
        "4.2",
        (
            "Freight is included in the unit price. The Supplier shall not invoice freight "
            "separately unless agreed in writing before the order is placed."
        ),
    )
    finding = match_documents(_invoice(10800.0, [FREIGHT_LINE]), _po())[0]

    case = investigate(finding, _contract(clause))

    assert len(case.notes) == 1 and "4.2" in case.notes[0]


def test_a_clause_without_exception_adds_no_note():
    clause = ("4.2", "Freight is included in the unit price. The Supplier shall not invoice it.")
    finding = match_documents(_invoice(10800.0, [FREIGHT_LINE]), _po())[0]

    assert investigate(finding, _contract(clause)).notes == []


def test_stored_cases_without_notes_still_load():
    case = CaseFile.model_validate(
        {
            "case_id": "OLD-01",
            "finding": "UNAGREED-FEE",
            "delta": 10.0,
            "evidence": [{"doc": "A", "page": 1, "ref": "x"}],
        }
    )

    assert case.notes == []


def test_french_fixtures_end_to_end():
    folder = Path(__file__).parent / "fixtures" / "ma"
    invoice, po, contract = (
        ExtractedDocument.model_validate_json((folder / f"{name}.json").read_text(encoding="utf-8"))
        for name in ("invoice", "po", "contract")
    )

    findings = match_documents(invoice, po)
    assert [f.type for f in findings] == [DiscrepancyType.UNAGREED_FEE]

    case = investigate(findings[0], contract, "FA-2026-0452-01")
    assert case.delta == 800.0
    assert case.proposed_action == [
        ProposedAction.HOLD_INVOICE,
        ProposedAction.DRAFT_SUPPLIER_MESSAGE,
    ]
    assert [e.doc for e in case.evidence] == ["FA-2026-0452", "BC-2026-119", "CT-2026-07"]
    assert len(case.notes) == 1
