# ruff: noqa: UP031, UP032
"""Generate the Vendora evaluation cases.

Each case is a folder with three synthetic PDFs (invoice, PO, contract) and an
expected.json holding the ground truth. Everything here is fictional.

Run from the repo root:
    pip install reportlab
    pip install pdfplumber   # optional, enables the quote check
    python3 eval/generate_cases.py
"""

import json
import re
import sys
from pathlib import Path

try:
    import pdfplumber
except ImportError:
    pdfplumber = None
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

OUT = Path(__file__).parent / "cases"
BUYER = {"name": "Atlas Manufacturing Co.", "address": "12 Industrial Way, Springfield"}
FOOTER = "Synthetic test document for the Vendora evaluation set. Not a real record."

styles = getSampleStyleSheet()
BODY = ParagraphStyle("body", parent=styles["Normal"], fontSize=10, leading=14)
SMALL = ParagraphStyle("small", parent=BODY, fontSize=9, textColor=colors.HexColor("#555555"))
H1 = ParagraphStyle("h1", parent=styles["Title"], fontSize=20, alignment=0, spaceAfter=6)
H2 = ParagraphStyle("h2", parent=styles["Heading3"], fontSize=11, spaceBefore=10, spaceAfter=2)


def money(x):
    return f"${x:,.2f}"


def line_amount(line):
    return round(line[1] * line[2], 2)


def total(lines):
    return round(sum(line_amount(l) for l in lines), 2)


def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(colors.HexColor("#888888"))
    canvas.drawString(0.8 * inch, 0.5 * inch, FOOTER)
    canvas.drawRightString(letter[0] - 0.8 * inch, 0.5 * inch, "Page %d" % doc.page)
    canvas.restoreState()


def build(path, title, story):
    doc = SimpleDocTemplate(
        str(path),
        pagesize=letter,
        title=title,
        author="Vendora synthetic data",
        leftMargin=0.8 * inch,
        rightMargin=0.8 * inch,
        topMargin=0.8 * inch,
        bottomMargin=0.9 * inch,
    )
    doc.build(story, onFirstPage=footer, onLaterPages=footer)


def lines_table(lines):
    rows = [["#", "Description", "Qty", "Unit price", "Amount"]]
    for i, (desc, qty, unit) in enumerate(lines, 1):
        rows.append([str(i), desc, str(qty), money(unit), money(line_amount((desc, qty, unit)))])
    rows.append(["", "", "", "TOTAL", money(total(lines))])
    t = Table(rows, colWidths=[0.35 * inch, 3.2 * inch, 0.7 * inch, 1.2 * inch, 1.3 * inch])
    t.setStyle(
        TableStyle(
            [
                ("FONTSIZE", (0, 0), (-1, -1), 9.5),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (3, -1), (-1, -1), "Helvetica-Bold"),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef1f6")),
                ("LINEBELOW", (0, 0), (-1, -2), 0.4, colors.HexColor("#c8cfdb")),
                ("LINEABOVE", (0, -1), (-1, -1), 0.8, colors.HexColor("#333333")),
                ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return t


def write_invoice(path, c):
    inv = c["invoice"]
    s = [
        Paragraph("INVOICE", H1),
        Paragraph("<b>{}</b>".format(c["supplier"]["name"]), BODY),
        Paragraph(c["supplier"]["address"], SMALL),
        Spacer(1, 8),
        Paragraph("Invoice number: {}".format(inv["number"]), BODY),
        Paragraph("Invoice date: {}".format(inv["date"]), BODY),
        Paragraph("PO reference: {}".format(inv["po_ref"]), BODY),
        Paragraph("Payment terms: {}".format(inv["terms"]), BODY),
        Spacer(1, 6),
        Paragraph("Bill to: {}, {}".format(BUYER["name"], BUYER["address"]), BODY),
        Spacer(1, 12),
        lines_table(inv["lines"]),
    ]
    for note in inv.get("notes", []):
        s += [Spacer(1, 10), Paragraph(note, BODY)]
    build(path, "Invoice " + inv["number"], s)


def write_po(path, c):
    po = c["po"]
    s = [
        Paragraph("PURCHASE ORDER", H1),
        Paragraph("<b>{}</b>".format(BUYER["name"]), BODY),
        Paragraph(BUYER["address"], SMALL),
        Spacer(1, 8),
        Paragraph("PO number: {}".format(po["number"]), BODY),
        Paragraph("PO date: {}".format(po["date"]), BODY),
        Paragraph("Supplier: {}".format(c["supplier"]["name"]), BODY),
        Paragraph("Payment terms: {}".format(po["terms"]), BODY),
        Paragraph("Contract reference: {}".format(c["contract"]["number"]), BODY),
        Spacer(1, 12),
        lines_table(po["lines"]),
    ]
    build(path, "Purchase order " + po["number"], s)


def write_contract(path, c):
    ct = c["contract"]
    s = [
        Paragraph(ct["title"], H1),
        Paragraph("Agreement number: {}".format(ct["number"]), BODY),
        Paragraph("Effective date: {}".format(ct["effective"]), BODY),
        Paragraph(
            "Between {} (Buyer) and {} (Supplier).".format(BUYER["name"], c["supplier"]["name"]),
            BODY,
        ),
    ]
    page = 1
    for cl in ct["clauses"]:
        while cl["page"] > page:
            s.append(PageBreak())
            page += 1
        s += [Paragraph("{}  {}".format(cl["ref"], cl["heading"]), H2), Paragraph(cl["text"], BODY)]
    build(path, ct["title"] + " " + ct["number"], s)


def base_clauses(terms_days=45):
    return [
        dict(
            ref="1.1",
            page=1,
            heading="Scope",
            text="Supplier will supply the goods listed in each Purchase Order issued by Buyer under this Agreement.",
        ),
        dict(
            ref="2.1",
            page=1,
            heading="Term",
            text="This Agreement runs for twelve months from the effective date and renews only by written agreement.",
        ),
    ]


CASES = [
    dict(
        id="case-001",
        slug="price_mismatch",
        difficulty="easy",
        supplier=dict(name="Brightwave Supplies Ltd.", address="48 Harbor Road, Portside"),
        po=dict(
            number="PO-4401",
            date="2026-03-02",
            terms="Net 45",
            lines=[("Hydraulic valve, HV-200", 100, 150.00), ("Mounting kit, MK-10", 100, 12.00)],
        ),
        contract=dict(
            number="MSA-2026-014",
            title="Master Supply Agreement",
            effective="2026-01-15",
            clauses=base_clauses()
            + [
                dict(
                    ref="3.1",
                    page=1,
                    heading="Pricing",
                    text="Unit prices are fixed for the term of this Agreement: Hydraulic valve HV-200 at $150.00 per unit and Mounting kit MK-10 at $12.00 per unit.",
                ),
                dict(
                    ref="7.1",
                    page=2,
                    heading="Payment",
                    text="Payment is due 45 days after receipt of a correct invoice.",
                ),
            ],
        ),
        invoice=dict(
            number="INV-90311",
            date="2026-03-20",
            po_ref="PO-4401",
            terms="Net 45",
            lines=[("Hydraulic valve, HV-200", 100, 165.00), ("Mounting kit, MK-10", 100, 12.00)],
        ),
        expected=dict(
            type="PRICE-MISMATCH",
            delta=1500.00,
            root_cause="The invoice bills the hydraulic valve at $165.00 per unit. The PO and the contract fix the price at $150.00.",
            evidence=[
                dict(doc="invoice.pdf", page=1, locator="line 1, unit price", quote="$165.00"),
                dict(doc="po.pdf", page=1, locator="line 1, unit price", quote="$150.00"),
                dict(
                    doc="contract.pdf",
                    page=1,
                    locator="clause 3.1",
                    quote="Hydraulic valve HV-200 at $150.00 per unit",
                ),
            ],
        ),
    ),
    dict(
        id="case-002",
        slug="unagreed_fee",
        difficulty="medium",
        supplier=dict(name="Halden Industrial Parts Inc.", address="9 Foundry Lane, Eastbridge"),
        po=dict(
            number="PO-4417",
            date="2026-03-09",
            terms="Net 45",
            lines=[("Steel bracket, SB-44", 500, 24.00), ("Fastener pack, FP-08", 500, 6.00)],
        ),
        contract=dict(
            number="MSA-2026-021",
            title="Master Supply Agreement",
            effective="2026-02-01",
            clauses=base_clauses()
            + [
                dict(
                    ref="3.1",
                    page=1,
                    heading="Pricing",
                    text="Unit prices: Steel bracket SB-44 at $24.00 per unit and Fastener pack FP-08 at $6.00 per unit.",
                ),
                dict(
                    ref="4.2",
                    page=2,
                    heading="Delivery costs",
                    text="Delivery is to the Buyer's facility. Freight, handling and insurance are included in the unit prices and may not be invoiced separately.",
                ),
                dict(
                    ref="7.1",
                    page=2,
                    heading="Payment",
                    text="Payment is due 45 days after receipt of a correct invoice.",
                ),
            ],
        ),
        invoice=dict(
            number="INV-55208",
            date="2026-03-28",
            po_ref="PO-4417",
            terms="Net 45",
            lines=[
                ("Steel bracket, SB-44", 500, 24.00),
                ("Fastener pack, FP-08", 500, 6.00),
                ("Freight surcharge", 1, 3000.00),
            ],
        ),
        expected=dict(
            type="UNAGREED-FEE",
            delta=3000.00,
            root_cause="The invoice adds a $3,000.00 freight surcharge. The PO has no freight line, and clause 4.2 says freight is included in the unit prices.",
            evidence=[
                dict(doc="invoice.pdf", page=1, locator="line 3", quote="Freight surcharge"),
                dict(doc="po.pdf", page=1, locator="total, no freight line", quote="$15,000.00"),
                dict(
                    doc="contract.pdf",
                    page=2,
                    locator="clause 4.2",
                    quote="may not be invoiced separately",
                ),
            ],
        ),
    ),
    dict(
        id="case-003",
        slug="qty_variance",
        difficulty="medium",
        supplier=dict(name="Corvane Packaging GmbH", address="21 Werkstrasse, Neustadt"),
        po=dict(
            number="PO-4432",
            date="2026-03-12",
            terms="Net 30",
            lines=[("Corrugated carton, CC-30", 200, 40.00)],
        ),
        contract=dict(
            number="MSA-2025-088",
            title="Supply Agreement",
            effective="2025-11-01",
            clauses=base_clauses()
            + [
                dict(
                    ref="3.1",
                    page=1,
                    heading="Pricing",
                    text="Corrugated carton CC-30 is priced at $40.00 per unit.",
                ),
                dict(
                    ref="5.1",
                    page=1,
                    heading="Quantities",
                    text="Supplier shall invoice only the quantities ordered on the Purchase Order. Quantities above the ordered amount require the Buyer's written approval.",
                ),
                dict(
                    ref="7.1",
                    page=2,
                    heading="Payment",
                    text="Payment is due 30 days after receipt of a correct invoice.",
                ),
            ],
        ),
        invoice=dict(
            number="INV-31744",
            date="2026-04-01",
            po_ref="PO-4432",
            terms="Net 30",
            lines=[("Corrugated carton, CC-30", 250, 40.00)],
        ),
        expected=dict(
            type="QTY-VARIANCE",
            delta=2000.00,
            root_cause="The invoice bills 250 cartons but the PO orders 200. Clause 5.1 requires written approval for quantities above the PO.",
            evidence=[
                dict(doc="invoice.pdf", page=1, locator="line 1, quantity", quote="250"),
                dict(doc="po.pdf", page=1, locator="line 1, quantity", quote="200"),
                dict(
                    doc="contract.pdf",
                    page=1,
                    locator="clause 5.1",
                    quote="require the Buyer's written approval",
                ),
            ],
        ),
    ),
    dict(
        id="case-004",
        slug="duplicate_line",
        difficulty="medium",
        supplier=dict(name="Norvik Electronics Ltd.", address="77 Circuit Street, Northgate"),
        po=dict(
            number="PO-4450",
            date="2026-03-16",
            terms="Net 30",
            lines=[
                ("Control board, CB-7", 40, 60.00),
                ("Wiring harness, WH-3", 40, 35.00),
                ("Display module, DM-2", 20, 120.00),
            ],
        ),
        contract=dict(
            number="MSA-2026-033",
            title="Master Supply Agreement",
            effective="2026-02-10",
            clauses=base_clauses()
            + [
                dict(
                    ref="3.1",
                    page=1,
                    heading="Pricing",
                    text="Control board CB-7 at $60.00, Wiring harness WH-3 at $35.00 and Display module DM-2 at $120.00 per unit.",
                ),
                dict(
                    ref="6.3",
                    page=1,
                    heading="Invoicing",
                    text="Each delivered item is invoiced once. Duplicate invoice lines will be rejected and the Buyer will not pay for them.",
                ),
                dict(
                    ref="7.1",
                    page=2,
                    heading="Payment",
                    text="Payment is due 30 days after receipt of a correct invoice.",
                ),
            ],
        ),
        invoice=dict(
            number="INV-78120",
            date="2026-04-03",
            po_ref="PO-4450",
            terms="Net 30",
            lines=[
                ("Control board, CB-7", 40, 60.00),
                ("Wiring harness, WH-3", 40, 35.00),
                ("Display module, DM-2", 20, 120.00),
                ("Control board, CB-7", 40, 60.00),
            ],
        ),
        expected=dict(
            type="DUPLICATE-LINE",
            delta=2400.00,
            root_cause="Lines 1 and 4 of the invoice are the same item (control board CB-7, 40 units). The PO orders it once, and clause 6.3 says each item is invoiced once.",
            evidence=[
                dict(doc="invoice.pdf", page=1, locator="line 1", quote="Control board, CB-7"),
                dict(doc="invoice.pdf", page=1, locator="line 4", quote="Control board, CB-7"),
                dict(
                    doc="po.pdf",
                    page=1,
                    locator="line 1 (only occurrence)",
                    quote="Control board, CB-7",
                ),
                dict(
                    doc="contract.pdf",
                    page=1,
                    locator="clause 6.3",
                    quote="Each delivered item is invoiced once",
                ),
            ],
        ),
    ),
    dict(
        id="case-005",
        slug="terms_conflict",
        difficulty="hard",
        supplier=dict(name="Valmere Chemicals Ltd.", address="5 Reagent Court, Southfield"),
        po=dict(
            number="PO-4466",
            date="2026-03-20",
            terms="Net 45",
            lines=[("Solvent drum, SD-55", 30, 210.00)],
        ),
        contract=dict(
            number="MSA-2026-040",
            title="Master Supply Agreement",
            effective="2026-02-20",
            clauses=base_clauses()
            + [
                dict(
                    ref="3.1",
                    page=1,
                    heading="Pricing",
                    text="Solvent drum SD-55 is priced at $210.00 per unit.",
                ),
                dict(
                    ref="7.1",
                    page=2,
                    heading="Payment",
                    text="Payment is due 45 days after receipt of a correct invoice. No early-payment surcharge or late-payment interest applies within that period.",
                ),
            ],
        ),
        invoice=dict(
            number="INV-12905",
            date="2026-04-05",
            po_ref="PO-4466",
            terms="Net 15",
            lines=[("Solvent drum, SD-55", 30, 210.00)],
            notes=["Late payment: 2% per month after due date."],
        ),
        expected=dict(
            type="TERMS-CONFLICT",
            delta=0.00,
            root_cause="The amounts match, but the invoice demands payment in 15 days with a late fee. The PO and clause 7.1 give 45 days and allow no late-payment interest.",
            evidence=[
                dict(doc="invoice.pdf", page=1, locator="payment terms", quote="Net 15"),
                dict(
                    doc="invoice.pdf",
                    page=1,
                    locator="note",
                    quote="Late payment: 2% per month after due date.",
                ),
                dict(doc="po.pdf", page=1, locator="payment terms", quote="Net 45"),
                dict(
                    doc="contract.pdf",
                    page=2,
                    locator="clause 7.1",
                    quote="Payment is due 45 days after receipt of a correct invoice",
                ),
            ],
        ),
    ),
]


def norm(s):
    return re.sub(r"\s+", " ", s).strip()


def page_texts(path):
    with pdfplumber.open(path) as pdf:
        return [norm(p.extract_text() or "") for p in pdf.pages]


def verify(c, folder):
    """Fail loudly if the ground truth does not match the generated PDFs."""
    exp = c["expected"]
    diff = round(total(c["invoice"]["lines"]) - total(c["po"]["lines"]), 2)
    assert diff == exp["delta"], "{}: delta {} != {}".format(c["id"], diff, exp["delta"])
    if pdfplumber is None:
        return
    texts = {n: page_texts(folder / n) for n in ("invoice.pdf", "po.pdf", "contract.pdf")}
    for ev in exp["evidence"]:
        pages = texts[ev["doc"]]
        assert ev["page"] <= len(pages), "%s: %s has no page %d" % (c["id"], ev["doc"], ev["page"])
        assert norm(ev["quote"]) in pages[ev["page"] - 1], "%s: quote not on %s p.%d: %r" % (
            c["id"],
            ev["doc"],
            ev["page"],
            ev["quote"],
        )


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = []
    for c in CASES:
        folder = OUT / ("{}_{}".format(c["id"], c["slug"]))
        folder.mkdir(parents=True, exist_ok=True)
        write_invoice(folder / "invoice.pdf", c)
        write_po(folder / "po.pdf", c)
        write_contract(folder / "contract.pdf", c)
        verify(c, folder)
        exp = c["expected"]
        data = {
            "case_id": c["id"],
            "difficulty": c["difficulty"],
            "has_discrepancy": exp["type"] is not None,
            "discrepancy_type": exp["type"],
            "amount_delta": exp["delta"],
            "invoice_total": total(c["invoice"]["lines"]),
            "po_total": total(c["po"]["lines"]),
            "root_cause": exp["root_cause"],
            "evidence": exp["evidence"],
        }
        (folder / "expected.json").write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
        manifest.append(
            {
                "case_id": c["id"],
                "folder": folder.name,
                "type": exp["type"],
                "difficulty": c["difficulty"],
            }
        )
        print("ok", folder.name)
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print("%d cases written to %s" % (len(CASES), OUT))


if __name__ == "__main__":
    sys.exit(main())
