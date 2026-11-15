"""Generate three synthetic French/MAD sample PDFs: invoice, purchase order, contract.

Needs reportlab (pip install reportlab). Output goes to data/samples_ma/.
The invoice carries one planted error: a "Frais de transport" line that the
purchase order does not have and that the contract forbids (article 5.2).
All names and numbers are invented.
"""

import textwrap
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

OUT = Path("data/samples_ma")
SUPPLIER = "Atlas Réseaux & Télécoms SARL"
BUYER = "Oriental Distribution SARL"
FOOTER = "Document synthétique de démonstration. Aucune donnée réelle."
LINES = [
    ("Câble réseau Cat6 - bobine", 10, 500.00),
    ("Prise murale RJ45", 100, 50.00),
]


def money(value: float) -> str:
    return f"{value:,.2f}".replace(",", " ").replace(".", ",")


class Page:
    def __init__(self, path: Path):
        self.pdf = canvas.Canvas(str(path), pagesize=A4)
        self.y = 800

    def text(self, value, size=10, bold=False, x=50, gap=16):
        self.pdf.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        self.pdf.drawString(x, self.y, value)
        self.y -= gap

    def paragraph(self, value, size=10, width=95):
        for part in textwrap.wrap(value, width):
            self.text(part, size)
        self.y -= 6

    def table_row(self, cells, bold=False):
        xs = (50, 290, 350, 440, 520)
        self.pdf.setFont("Helvetica-Bold" if bold else "Helvetica", 10)
        for x, cell in zip(xs, cells, strict=False):
            if x == 50:
                self.pdf.drawString(x, self.y, cell)
            else:
                self.pdf.drawRightString(x + 40, self.y, cell)
        self.y -= 16

    def totals(self, rows):
        self.y -= 8
        for label, value in rows:
            self.pdf.setFont("Helvetica-Bold" if "TTC" in label else "Helvetica", 10)
            self.pdf.drawString(350, self.y, label)
            self.pdf.drawRightString(560, self.y, value + " MAD")
            self.y -= 16

    def new_page(self):
        self.footer()
        self.pdf.showPage()
        self.y = 800

    def footer(self):
        self.pdf.setFont("Helvetica-Oblique", 8)
        self.pdf.drawString(50, 30, FOOTER)

    def save(self):
        self.footer()
        self.pdf.save()


def document_with_lines(path, title, number, date, lines, vat_rate=0.20):
    page = Page(path)
    page.text(title, 16, bold=True, gap=24)
    page.text(f"N° {number}    Date : {date}", 11)
    page.text(f"Fournisseur : {SUPPLIER}")
    page.text(f"Client : {BUYER}")
    page.text("Devise : MAD (dirham marocain)", gap=24)
    page.table_row(("Désignation", "Qté", "PU HT", "Montant HT"), bold=True)
    for index, (description, quantity, price) in enumerate(lines, start=1):
        page.table_row(
            (
                f"{index}. {description}",
                f"{quantity:g}",
                money(price),
                money(quantity * price),
            )
        )
    subtotal = sum(quantity * price for _, quantity, price in lines)
    vat = round(subtotal * vat_rate, 2)
    page.totals(
        [
            ("Total HT", money(subtotal)),
            (f"TVA {int(vat_rate * 100)} %", money(vat)),
            ("Total TTC", money(subtotal + vat)),
        ]
    )
    page.save()


def contract(path):
    page = Page(path)
    page.text("CONTRAT CADRE D'APPROVISIONNEMENT", 15, bold=True, gap=24)
    page.text("Référence : CT-2026-07", 11)
    page.paragraph(f"Entre {SUPPLIER} (le Fournisseur) et {BUYER} (le Client).")
    page.text("Article 1 - Objet", 11, bold=True)
    page.paragraph("Le Fournisseur livre au Client des équipements réseau selon les commandes.")
    page.new_page()
    page.text("Article 5 - Prix et paiement", 12, bold=True, gap=20)
    page.paragraph(
        "5.1 Les prix unitaires hors taxes sont fixes : câble réseau Cat6 à 500,00 MAD "
        "la bobine, prise murale RJ45 à 50,00 MAD l'unité. Toute modification exige un "
        "avenant signé par les deux parties."
    )
    page.paragraph(
        "5.2 Les frais de transport et de livraison sont inclus dans le prix unitaire. "
        "Le Fournisseur ne peut pas facturer séparément le transport, la manutention ou "
        "toute majoration, sauf accord écrit préalable à la commande."
    )
    page.paragraph("5.3 Le paiement est effectué à 30 jours à compter de la date de facture.")
    page.save()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    document_with_lines(
        OUT / "bc-2026-119.pdf", "BON DE COMMANDE", "BC-2026-119", "03/11/2026", LINES
    )
    invoice_lines = [*LINES, ("Frais de transport", 1, 800.00)]
    document_with_lines(
        OUT / "fa-2026-0452.pdf", "FACTURE", "FA-2026-0452", "12/11/2026", invoice_lines
    )
    contract(OUT / "ct-2026-07.pdf")
    print("written to", OUT)


if __name__ == "__main__":
    main()
