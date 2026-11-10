"""Evaluation harness for Matching + Investigation (M4, offline track).

Cases are generated in memory with a fixed seed, so every run is identical.
Each case has a known correct answer, so the score is not a guess.

Run from the project root:  python eval/run_eval.py
"""

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.extraction import ExtractedDocument, ExtractedLine
from app.agents.investigation import investigate, parse_clauses
from app.agents.matching import match_documents

CONTRACT_PAGES = [
    "3.2 The Supplier confirms each order within 5 business days.\n",
    (
        "4.1 Unit prices are fixed as listed in Exhibit A. "
        "Prices may only change by written amendment.\n"
        "4.2 Freight and delivery costs are included in the unit price. "
        "The Supplier shall not invoice freight, handling, or any surcharge separately.\n"
        "4.3 Payment terms are Net 30 from the invoice date.\n"
    ),
]

CATALOG = [
    ("SM-200", "Industrial sensor module"),
    ("MB-10", "Mounting bracket"),
    ("CA-5", "Cable assembly"),
    ("PS-12", "Power supply unit"),
    ("FT-7", "Filter cartridge"),
]
FEES = ["Freight surcharge", "Handling fee", "Shipping charge", "Expedite surcharge"]
EXPECTED_CLAUSE = {"UNAGREED-FEE": "4.2", "PRICE-MISMATCH": "4.1"}
SCENARIOS = {
    "clean": None,
    "fee": "UNAGREED-FEE",
    "price": "PRICE-MISMATCH",
    "qty": "QTY-VARIANCE",
    "dup": "DUPLICATE-LINE",
}


def _line(no, description, qty, price):
    return ExtractedLine(
        line_no=no,
        description=description,
        quantity=qty,
        unit_price=price,
        amount=round(qty * price, 2),
        page=1,
    )


def _doc(kind, doc_id, lines):
    total = round(sum(float(line.amount) for line in lines), 2)
    return ExtractedDocument(
        doc_type=kind,
        doc_id=doc_id,
        currency="USD",
        lines=lines,
        total=total,
        total_page=1,
    )


def _make_case(rng, scenario, case_id):
    chosen = rng.sample(CATALOG, rng.randint(2, 4))
    spec = []
    for sku, name in chosen:
        spec.append([f"{sku} - {name}", rng.randint(5, 50) * 10, rng.randint(5, 90)])
    po_lines = [_line(i, d, q, p) for i, (d, q, p) in enumerate(spec, 1)]

    inv = [list(row) for row in spec]
    extra, expected = [], []
    idx = rng.randrange(len(inv))

    if scenario == "fee":
        fee = float(rng.randint(2, 40) * 100)
        extra.append((rng.choice(FEES), 1, fee))
        expected.append(("UNAGREED-FEE", fee))
    elif scenario == "price":
        _, qty, old = inv[idx]
        new = old + rng.randint(1, 10)
        inv[idx][2] = new
        expected.append(("PRICE-MISMATCH", float((new - old) * qty)))
    elif scenario == "qty":
        _, qty, price = inv[idx]
        new_qty = qty + rng.randint(1, 5) * 10
        inv[idx][1] = new_qty
        expected.append(("QTY-VARIANCE", float((new_qty - qty) * price)))
    elif scenario == "dup":
        desc, qty, price = inv[idx]
        extra.append((desc, qty, price))
        expected.append(("DUPLICATE-LINE", float(qty * price)))

    inv_rows = [tuple(row) for row in inv] + extra
    inv_lines = [_line(i, d, q, p) for i, (d, q, p) in enumerate(inv_rows, 1)]
    return {
        "id": case_id,
        "scenario": scenario,
        "po": _doc("purchase_order", "PO-EVAL", po_lines),
        "invoice": _doc("invoice", "INV-EVAL", inv_lines),
        "expected": expected,
    }


def make_cases(seed=7, per_scenario=8):
    rng = random.Random(seed)
    cases = []
    for scenario in SCENARIOS:
        for n in range(1, per_scenario + 1):
            cases.append(_make_
