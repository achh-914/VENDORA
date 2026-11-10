"""Evaluate issue detection on the synthetic dataset (ground truth is hidden from the detector)."""
import json
from collections import Counter, defaultdict
from pathlib import Path

KINDS = ["clean", "price_mismatch", "quantity_mismatch", "extra_charge"]


def detect(case):
    """Baseline detector. Replace the body with a call to your own matching code.
    It only receives the documents, never 'expected_issue'."""
    po, inv = case["purchase_order"], case["invoice"]
    po_line, inv_line = po["lines"][0], inv["lines"][0]
    if inv_line["unit_price"] != po_line["unit_price"]:
        return "price_mismatch"
    if inv_line["qty"] != po_line["qty"]:
        return "quantity_mismatch"
    if inv["shipping"] != po["shipping"]:
        return "extra_charge"
    return "clean"


def main():
    cases = json.loads(Path("data/cases.json").read_text(encoding="utf-8"))
    total, correct, wrong = defaultdict(int), defaultdict(int), Counter()
    for c in cases:
        truth = c["expected_issue"]
        visible = {k: v for k, v in c.items() if k != "expected_issue"}
        pred = detect(visible)
        total[truth] += 1
        if pred == truth:
            correct[truth] += 1
        else:
            wrong[(truth, pred)] += 1
    print("| Type | Cases | Correct | Wrong |")
    print("|---|---|---|---|")
    for k in KINDS:
        print(f"| {k} | {total[k]} | {correct[k]} | {total[k] - correct[k]} |")
    n, ok = sum(total.values()), sum(correct.values())
    print(f"\nOverall: {ok}/{n} correct ({100 * ok / n:.0f}%)")
    for (t, p), m in wrong.items():
        print(f"Mistake: expected {t}, got {p} ({m})")


if __name__ == "__main__":
    main()
