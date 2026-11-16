"""Matching agent: compares an invoice with its purchase order.

Plain Python, no LLM. Numbers are computed with Decimal, never guessed.
"""

import re
import unicodedata
from decimal import ROUND_HALF_UP, Decimal

from pydantic import BaseModel

from app.agents.extraction import ExtractedDocument, ExtractedLine
from app.schemas import DiscrepancyType, Evidence

SKU_RE = re.compile(r"^\s*([A-Za-z]{1,6}-\d+[A-Za-z0-9-]*)")
CURRENCY_SYMBOLS = {
    "$": "USD",
    "€": "EUR",
    "£": "GBP",
    "¥": "JPY",
    "₹": "INR",
    "₺": "TRY",
    "ZŁ": "PLN",
    "KČ": "CZK",
    "RMB": "CNY",
    "DH": "MAD",
    "DHS": "MAD",
    "MAD": "MAD",
    "درهم": "MAD",
}
VAT_RATES = (Decimal("0.20"), Decimal("0.14"), Decimal("0.10"), Decimal("0.07"))  # Morocco
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


def currency_code(doc: ExtractedDocument) -> str:
    """Return a clean currency code: '$' -> USD, 'DH' or 'Dhs' -> MAD."""
    raw = (doc.currency or "").strip()
    return CURRENCY_SYMBOLS.get(raw) or CURRENCY_SYMBOLS.get(raw.upper()) or raw.upper()


_currency = currency_code


def _norm(text: str) -> str:
    """Lowercase, drop accents and collapse spaces: 'Câble  Réseau' -> 'cable reseau'."""
    folded = unicodedata.normalize("NFKD", text)
    plain = "".join(ch for ch in folded if not unicodedata.combining(ch))
    return " ".join(plain.casefold().split())


def _fmt(amount, currency: str) -> str:
    return f"{currency} {_d(amount):,.2f}".strip()


def _key(line: ExtractedLine) -> str:
    text = _norm(line.description)
    match = SKU_RE.match(text)
    if match:
        return match.group(1)
    return text


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


def _comparable_total(doc: ExtractedDocument) -> tuple[Decimal | None, str]:
    """Total used to compare documents: before tax (HT) when the document says so."""
    if doc.subtotal is not None:
        return _d(doc.subtotal), "total before tax"
    if doc.tax is not None and doc.total is not None:
        return _d(doc.total) - _d(doc.tax), "total before tax"
    if doc.total is not None:
        return _d(doc.total), "total"
    return None, "total"


def _vat_hint(residual: Decimal, base: Decimal) -> str:
    """Point out a gap that equals a VAT rate: one document may include tax."""
    for rate in VAT_RATES:
        taxed = base * rate
        inside = base - base / (1 + rate)
        if abs(residual - taxed) <= CENT or abs(residual + inside) <= CENT:
            return f" (the gap matches {int(rate * 100)}% VAT: check if one document includes tax)"
    return ""


def _reconcile_totals(
    invoice: ExtractedDocument, po: ExtractedDocument, findings: list[Finding]
) -> list[Finding]:
    """Flag a total gap that the line-level findings do not explain."""
    inv_total, inv_label = _comparable_total(invoice)
    po_total, po_label = _comparable_total(po)
    if inv_total is None or po_total is None:
        return []
    explained = sum((_d(f.delta) for f in findings), Decimal(0))
    residual = inv_total - po_total - explained
    if abs(residual) < Decimal("0.005"):
        return []
    inv_ref = f"{inv_label} {_fmt(inv_total, _currency(invoice))}"
    po_ref = f"{po_label} {_fmt(po_total, _currency(po))}"
    summary = "Invoice total gap vs the PO is not explained by the line items"
    return [
        Finding(
            type=DiscrepancyType.PRICE_MISMATCH,
            delta=_money(residual),
            summary=summary + _vat_hint(residual, po_total),
            evidence=[
                Evidence(doc=invoice.doc_id, page=invoice.total_page or 1, ref=inv_ref),
                Evidence(doc=po.doc_id, page=po.total_page or 1, ref=po_ref),
            ],
        )
    ]


def _currency_mismatch(invoice: ExtractedDocument, po: ExtractedDocument) -> Finding | None:
    """Different currencies: amounts cannot be compared, so no line is checked."""
    inv_cur, po_cur = _currency(invoice), _currency(po)
    if not inv_cur or not po_cur or inv_cur == po_cur:
        return None
    return Finding(
        type=DiscrepancyType.CURRENCY_MISMATCH,
        delta=0.0,
        summary=(
            f"The invoice is in {inv_cur} but the PO is in {po_cur}: "
            "amounts were not compared. Check the agreed currency or exchange rate."
        ),
        evidence=[
            Evidence(doc=invoice.doc_id, page=invoice.total_page or 1, ref=f"currency {inv_cur}"),
            Evidence(doc=po.doc_id, page=po.total_page or 1, ref=f"currency {po_cur}"),
        ],
    )


def match_documents(invoice: ExtractedDocument, po: ExtractedDocument) -> list[Finding]:
    """Compare invoice lines against PO lines and return the discrepancies."""
    po_lines: dict[str, ExtractedLine] = {}
    for line in po.lines:
        po_lines.setdefault(_key(line), line)

    mismatch = _currency_mismatch(invoice, po)
    if mismatch:
        return [mismatch]

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
