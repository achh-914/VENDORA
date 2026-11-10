"""Matching agent: compares an invoice with its purchase order.

Plain Python, no LLM. Numbers are computed with Decimal, never guessed.
"""

import re
from decimal import ROUND_HALF_UP, Decimal

from pydantic import BaseModel

from app.agents.extraction import ExtractedDocument, ExtractedLine
from app.schemas import DiscrepancyType, Evidence

SKU_RE = re.compile(r"^\s*([A-Za-z]{1,6}-\d+[A-Za-z0-9-]*)")
CURRENCY_SYMBOLS = {"$": "USD", "€": "EUR", "£": "GBP"}
CENT = Decimal("0.01")


class Finding(BaseModel):
    type: DiscrepancyType
    delta: float
    summary: str
    evidence: list[Evidence]


def _d(value) -> Decimal:
    return Decimal(str(value))


def _money(value: Decimal) -> float:
    return float(value.quantize(CENT, rounding=ROUND_HALF_UP))


def _currency(doc: ExtractedDocument) -> str:
    raw = (doc.currency or "").strip()
    return CURRENCY_SYMBOLS.get(raw, raw.upper())


def _fmt(amount, currency: str) -> str:
    return f"{currency} {_d(amount):,.2f}".strip()


def _key(line: ExtractedLine) -> str:
    match = SKU_RE.match(line.description)
    if match:
        return match.group(1).lower()
    return " ".join(line.description.lower().split())


def _invoice_evidence(invoice: ExtractedDocument, line: ExtractedLine) -> Evidence:
    amount = _fmt(line.amount, _currency(invoice))
    ref = f"line {line.line_no}: {line.description}, {amount}"
    return Evidence(doc=invoice.doc_id, page=line.page, ref=ref)


def _po_evidence(po: ExtractedDocument, line: ExtractedLine | None = None) -> Evidence:
    currency = _currency(po)
    if line is not None:
        amount = _fmt(line.amount, currency)
        ref = f"line {line.line_no}: {line.description}, {amount}"
        return Evidence(doc=po.doc_id, page=line.page, ref=ref)
    ref = "no matching line"
    if po.total is not None:
        ref += f", total {_fmt(po.total, currency)}"
    return Evidence(doc=po.doc_id, page=po.total_page or 1, ref=ref)


def _compare_lines(
    invoice: ExtractedDocument,
    po: ExtractedDocument,
    inv_line: ExtractedLine,
    po_line: ExtractedLine,
) -> list[Finding]:
    findings = []
    evidence = [_invoice_evidence(invoice, inv_line), _po_evidence(po, po_line)]

    inv_price, po_price = inv_line.unit_price, po_line.unit_price
    if inv_price is not None and po_price is not None and _d(inv_price) != _d(po_price):
        qty = _d(inv_line.quantity) if inv_line.quantity is not None else Decimal(1)
        findings.append(
            Finding(
                type=DiscrepancyType.PRICE_MISMATCH,
                delta=_money((_d(inv_price) - _d(po_price)) * qty),
                summary=f"Unit price for '{inv_line.description}' differs from the PO",
                evidence=evidence,
            )
        )

    inv_qty, po_qty = inv_line.quantity, po_line.quantity
    if inv_qty is not None and po_qty is not None and _d(inv_qty) != _d(po_qty):
        unit = _d(po_price or inv_price or 0)
        findings.append(
            Finding(
                type=DiscrepancyType.QTY_VARIANCE,
                delta=_money((_d(inv_qty) - _d(po_qty)) * unit),
                summary=f"Billed quantity for '{inv_line.description}' differs from the PO",
                evidence=evidence,
            )
        )
    return findings


def _reconcile_totals(
    invoice: ExtractedDocument, po: ExtractedDocument, findings: list[Finding]
) -> list[Finding]:
    """Flag a total gap that the line-level findings do not explain."""
    if invoice.total is None or po.total is None:
        return []
    explained = sum((_d(f.delta) for f in findings), Decimal(0))
    residual = _d(invoice.total) - _d(po.total) - explained
    if abs(residual) < Decimal("0.005"):
        return []
    inv_ref = f"total {_fmt(invoice.total, _currency(invoice))}"
    po_ref = f"total {_fmt(po.total, _currency(po))}"
    return [
        Finding(
            type=DiscrepancyType.PRICE_MISMATCH,
            delta=_money(residual),
            summary="Invoice total gap vs the PO is not explained by the line items",
            evidence=[
                Evidence(doc=invoice.doc_id, page=invoice.total_page or 1, ref=inv_ref),
                Evidence(doc=po.doc_id, page=po.total_page or 1, ref=po_ref),
            ],
        )
    ]


def match_documents(invoice: ExtractedDocument, po: ExtractedDocument) -> list[Finding]:
    """Compare invoice lines against PO lines and return the discrepancies."""
    po_lines: dict[str, ExtractedLine] = {}
    for line in po.lines:
        po_lines.setdefault(_key(line), line)

    findings: list[Finding] = []
    seen: set[str] = set()

    for line in invoice.lines:
        key = _key(line)

        if key in seen:
            findings.append(
                Finding(
                    type=DiscrepancyType.DUPLICATE_LINE,
                    delta=_money(_d(line.amount)),
                    summary=f"'{line.description}' is billed more than once",
                    evidence=[_invoice_evidence(invoice, line)],
                )
            )
            continue
        seen.add(key)

        po_line = po_lines.get(key)
        if po_line is None:
            findings.append(
                Finding(
                    type=DiscrepancyType.UNAGREED_FEE,
                    delta=_money(_d(line.amount)),
                    summary=f"'{line.description}' is not in the purchase order",
                    evidence=[_invoice_evidence(invoice, line), _po_evidence(po)],
                )
            )
            continue

        findings.extend(_compare_lines(invoice, po, line, po_line))

    findings.extend(_reconcile_totals(invoice, po, findings))
    return findings
