"""Evaluation harness for Matching + Investigation (M4, offline track).

Cases are generated in memory with a fixed seed, so every run is identical.
Each case has a known correct answer, so the score is not a guess.

Run from the project root:  python eval/run_eval.py
"""

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.extraction import ExtractedClause, ExtractedDocument, ExtractedLine
from app.agents.investigation import investigate
from app.agents.matching import match_documents

FEE_CLAUSE_TEXT = (
    "Freight and delivery costs are included in the unit price. "
    "The Supplier shall not invoice freight, handling, or any surcharge separately."
)

CONTRACT = ExtractedDocument(
    doc_type="contract",
    doc_id="MSA-EVAL",
    clauses=[
        ExtractedClause(
            number="3.2",
            text="The Supplier confirms each order within 5 business days.",
            page=1,
        ),
        ExtractedClause(
            number="4.1",
            text="Unit prices are fixed. Prices may only change by written amendment.",
            page=2,
        ),
        ExtractedClause(number="4.2", text=FEE_CLAUSE_TEXT, page=2),
        ExtractedClause(
            number="4.3",
            text="Payment terms are Net 30 from the invoice date.",
            page=2,
        ),
    ],
)

CATALOG = [
    ("SM-200", "Industrial sensor module"),
    ("MB-10", "Mounting bracket"),
    ("CA-5", "Cable assembly"),
    ("PS-12", "Power supply unit"),
    ("FT-7", "Filter cartridge"),
]
FEES = ["Freight surcharge", "Handling fee", "Shipping charge", "Expedite surcharge"]
SCENARIOS = ["clean", "fee", "price", "qty", "dup"]


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
            cases.append(_make_case(rng, scenario, f"{scenario.upper()}-{n:02d}"))
    return cases


def _ftype(finding):
    kind = getattr(finding, "type", None) or getattr(finding, "finding", None)
    return getattr(kind, "value", str(kind))


def _cites_fee_clause(case_file):
    evidence = getattr(case_file, "evidence", None) or []
    return any(
        e.doc == CONTRACT.doc_id and e.page == 2 and "4.2" in e.ref for e in evidence
    )


def evaluate(seed=7, per_scenario=8):
    stats = {"cases": 0, "detect": 0, "delta": 0, "delta_n": 0, "cite": 0, "cite_n": 0}
    by_scenario = {name: [0, 0] for name in SCENARIOS}
    failures = []

    for case in make_cases(seed, per_scenario):
        findings = match_documents(case["invoice"], case["po"])
        got = sorted((_ftype(f), round(float(f.delta), 2)) for f in findings)
        want = sorted(case["expected"])

        stats["cases"] += 1
        by_scenario[case["scenario"]][1] += 1

        if [t for t, _ in got] == [t for t, _ in want]:
            stats["detect"] += 1
            by_scenario[case["scenario"]][0] += 1
        else:
            failures.append((case["id"], want, got))
            continue

        for (_, want_delta), (_, got_delta) in zip(want, got, strict=True):
            stats["delta_n"] += 1
            stats["delta"] += abs(want_delta - got_delta) < 0.01

        for finding in findings:
            if _ftype(finding) != "UNAGREED-FEE":
                continue
            stats["cite_n"] += 1
            result = investigate(finding, CONTRACT, case_id=case["id"])
            stats["cite"] += _cites_fee_clause(result)

    return stats, by_scenario, failures


def _pct(a, b):
    return f"{a}/{b} ({100 * a / b:.1f}%)" if b else "n/a"


def main():
    stats, by_scenario, failures = evaluate()
    print(f"Cases: {stats['cases']}")
    print(f"Discrepancy detection accuracy: {_pct(stats['detect'], stats['cases'])}")
    print(f"Amount (delta) accuracy:        {_pct(stats['delta'], stats['delta_n'])}")
    print(f"Fee clause citation (4.2, p.2): {_pct(stats['cite'], stats['cite_n'])}")
    print("Average cost per case:          $0.00 (offline, no LLM)")
    print("\nBy scenario:")
    for name, (ok, total) in by_scenario.items():
        print(f"  {name:<6} {_pct(ok, total)}")
    if failures:
        print("\nFirst failures (expected vs got):")
        for case_id, want, got in failures[:5]:
            print(f"  {case_id}: expected {want} got {got}")


if __name__ == "__main__":
    main()
