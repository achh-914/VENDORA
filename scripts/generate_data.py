"""Generate synthetic procurement cases with known discrepancies."""

import json
import random
from collections import Counter
from pathlib import Path

VENDORS = ["ABC Supplies", "Global Tech", "Metro Goods", "Delta Supply", "Nord Logistics"]
ITEMS = [
    ("Laptop stand", 40.0),
    ("USB-C cable", 8.5),
    ("Office chair", 120.0),
    ("Monitor", 210.0),
    ("Toner", 65.0),
]
PLAN = ["clean"] * 10 + ["price_mismatch"] * 7 + ["quantity_mismatch"] * 7 + ["extra_charge"] * 6


def total(lines, shipping):
    return round(sum(x["qty"] * x["unit_price"] for x in lines) + shipping, 2)


def make_case(i, kind, rng):
    vendor = rng.choice(VENDORS)
    item, price = rng.choice(ITEMS)
    qty = rng.randint(5, 50)
    po_lines = [{"item": item, "qty": qty, "unit_price": price}]
    inv_lines = [dict(po_lines[0])]
    inv_shipping = 0.0
    if kind == "price_mismatch":
        inv_lines[0]["unit_price"] = round(price * rng.choice([1.05, 1.10, 1.20]), 2)
    elif kind == "quantity_mismatch":
        inv_lines[0]["qty"] = qty + rng.randint(1, 5)
    elif kind == "extra_charge":
        inv_shipping = float(rng.choice([150, 250, 400]))
    return {
        "case_id": f"CASE-{i:03d}",
        "purchase_order": {
            "po_id": f"PO-{1000 + i}",
            "vendor": vendor,
            "lines": po_lines,
            "shipping": 0.0,
            "total": total(po_lines, 0.0),
        },
        "contract": {
            "vendor": vendor,
            "pricing_clause": f"{item}: {price:.2f} per unit",
            "shipping_clause": "Shipping is not charged unless agreed in writing",
        },
        "invoice": {
            "invoice_id": f"INV-{2000 + i}",
            "po_id": f"PO-{1000 + i}",
            "vendor": vendor,
            "lines": inv_lines,
            "shipping": inv_shipping,
            "total": total(inv_lines, inv_shipping),
        },
        "expected_issue": kind,
    }


def main():
    rng = random.Random(42)
    plan = PLAN[:]
    rng.shuffle(plan)
    cases = [make_case(i + 1, kind, rng) for i, kind in enumerate(plan)]
    out = Path("data/cases.json")
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(cases, indent=2), encoding="utf-8")
    print(f"Wrote {len(cases)} cases to {out}")
    print(dict(Counter(c["expected_issue"] for c in cases)))


if __name__ == "__main__":
    main()
