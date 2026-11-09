"""Matching agent: compares an invoice with its purchase order.

Plain Python, no LLM. Numbers are computed, never guessed.
"""

from pydantic import BaseModel

from app.agents.extraction import ExtractedDocument, ExtractedLine
from app.schemas import DiscrepancyType, Evidence

FEE_WORDS = ("freight", "shipping", "handling", "surcharge", "delivery", "fee")


class Finding(BaseModel):
    type: DiscrepancyType
    delta: float
    summary: str
    evidence: list[Evidence]


def _key(line: ExtractedLine) -> str:
    return line.description.split(" - ")[0].strip().lower()


def _is_fee(line: ExtractedLine) -> bool:
    return any(word in line.description.lower() for word in FEE_WORDS)


def _invoice_evidence(invoice: ExtractedDocument, line: ExtractedLine) -> Evidence:
    ref = f"line {line.line_no}: {line.description}, ${line.amount:,.2f}"
    return Evidence(doc=invoice.doc_id, page=line.page, ref=ref)


def _po_evidence(po: ExtractedDocument, line: ExtractedLine | None = None) -> Evidence:
    if line is not None:
        ref = f"line {line.line_no}: {line.description}, ${line.amount:,.2f}"
        return Evidence(doc=po.doc_id, page=line.page, ref=ref)
    ref = "no matching line"
    if po.total is not None:
        ref += f", total ${po.total:,.2f}"
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
    if inv_price is not None and po_price is not None and abs(inv_price - po_price) > 0.005:
        qty = inv_line.quantity if inv_line.quantity is not None else 1
        findings.append(
            Finding(
                type=DiscrepancyType.PRICE_MISMATCH,
                delta=round((inv_price - po_price) * qty, 2),
                summary=f"Unit price for '{inv_line.description}' differs from the PO",
                evidence=evidence,
            )
        )

    inv_qty, po_qty = inv_line.quantity, po_line.quantity
    if inv_qty is not None and po_qty is not None and abs(inv_qty - po_qty) > 1e-9:
        unit = po_price or inv_price or 0.0
        findings.append(
            Finding(
                type=DiscrepancyType.QTY_VARIANCE,
                delta=round((inv_qty - po_qty) * unit, 2),
                summary=f"Billed quantity for '{inv_line.description}' differs from the PO",
                evidence=evidence,
            )
        )
    return findings


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
                    delta=round(line.amount, 2),
                    summary=f"'{line.description}' is billed more than once",
                    evidence=[_invoice_evidence(invoice, line)],
                )
            )
            continue
        seen.add(key)

        po_line = po_lines.get(key)
        if po_line is None:
            if _is_fee(line):
                findings.append(
                    Finding(
                        type=DiscrepancyType.UNAGREED_FEE,
                        delta=round(line.amount, 2),
                        summary=f"'{line.description}' is not in the purchase order",
                        evidence=[_invoice_evidence(invoice, line), _po_evidence(po)],
                    )
                )
            continue

        findings.extend(_compare_lines(invoice, po, line, po_line))

    return findings
