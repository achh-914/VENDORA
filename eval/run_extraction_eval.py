"""Extraction evaluation (M4, real-model track).

Runs the extraction agent on the three sample PDFs in data/samples and scores
the output against values known from the documents.

Uses the provider chosen by VENDORA_PROVIDER (claude or gemini). Calls a real
model: use synthetic documents only. Run from the project root:

    python eval/run_extraction_eval.py
"""

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.agents.extraction import extract_document

SAMPLES = ROOT / "data" / "samples"

INVOICE_LINES = {1: 9000.0, 2: 3000.0, 3: 3000.0, 4: 3000.0}
PO_LINES = {1: 9000.0, 2: 3000.0, 3: 3000.0}


def _val(value):
    return str(getattr(value, "value", value))


def _close(a, b):
    return a is not None and abs(float(a) - b) < 0.01


def _line_checks(doc, expected):
    checks = []
    by_no = {line.line_no: line for line in doc.lines}
    for no, amount in expected.items():
        line = by_no.get(no)
        checks.append((f"line {no} amount", bool(line) and _close(line.amount, amount)))
        checks.append((f"line {no} page", bool(line) and line.page == 1))
    return checks


def _score_invoice(doc):
    checks = [
        ("doc_type", _val(doc.doc_type) == "invoice"),
        ("doc_id", "2041" in str(doc.doc_id)),
        ("total", _close(doc.total, 18000.0)),
    ]
    checks += _line_checks(doc, INVOICE_LINES)
    freight = {line.line_no: line for line in doc.lines}.get(4)
    checks.append(("line 4 is freight", bool(freight) and "freight" in freight.description.lower()))
    return checks


def _score_po(doc):
    checks = [
        ("doc_type", _val(doc.doc_type) == "purchase_order"),
        ("doc_id", "4471" in str(doc.doc_id)),
        ("total", _close(doc.total, 15000.0)),
    ]
    return checks + _line_checks(doc, PO_LINES)


def _score_contract(doc):
    clauses = {clause.number: clause for clause in doc.clauses}
    checks = [("doc_type", _val(doc.doc_type) == "contract")]
    for number in ("4.1", "4.2", "4.3"):
        clause = clauses.get(number)
        checks.append((f"clause {number} on page 6", bool(clause) and clause.page == 6))
    fee = clauses.get("4.2")
    checks.append(("clause 4.2 text", bool(fee) and "freight" in fee.text.lower()))
    return checks


JOBS = [
    ("inv-2041.pdf", _score_invoice),
    ("po-4471.pdf", _score_po),
    ("msa-acme.pdf", _score_contract),
]


def main():
    total_ok, total_n = 0, 0
    for name, scorer in JOBS:
        print(f"\n{name}")
        try:
            doc = extract_document(SAMPLES / name)
            checks = scorer(doc)
        except Exception as error:  # noqa: BLE001
            print(f"  ERROR: {type(error).__name__}: {error}")
            continue
        ok = sum(1 for _, passed in checks if passed)
        total_ok += ok
        total_n += len(checks)
        print(f"  {ok}/{len(checks)} fields correct")
        for label, passed in checks:
            if not passed:
                print(f"  wrong: {label}")
        time.sleep(2)

    print(f"\nExtraction accuracy: {total_ok}/{total_n}")
    print("Documents: 3 synthetic PDFs (very small sample)")


if __name__ == "__main__":
    main()
