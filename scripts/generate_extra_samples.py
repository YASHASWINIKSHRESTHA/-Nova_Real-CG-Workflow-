"""
Generate additional synthetic trade document samples for gold set expansion:
  samples/packing_list_001.pdf  — Packing list with mixed-confidence fields
  samples/commercial_invoice_002.pdf — Second invoice (EXW, Hamburg, different HS)
Run once: python scripts/generate_extra_samples.py
"""
import sys
from pathlib import Path

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas as rl_canvas
except ImportError:
    print("reportlab not installed — run: pip install reportlab")
    sys.exit(1)

SAMPLES_DIR = Path(__file__).parent.parent / "samples"
SAMPLES_DIR.mkdir(exist_ok=True)


# ──────────────────────────────────────────────
# Packing List (PDF)
# ──────────────────────────────────────────────

def make_packing_list():
    out = SAMPLES_DIR / "packing_list_001.pdf"
    c = rl_canvas.Canvas(str(out), pagesize=A4)
    w, h = A4

    def row(y, label, value):
        c.setFont("Helvetica-Bold", 10)
        c.drawString(20 * mm, y, label + ":")
        c.setFont("Helvetica", 10)
        c.drawString(80 * mm, y, value)

    # Header
    c.setFont("Helvetica-Bold", 16)
    c.drawCentredString(w / 2, h - 25 * mm, "PACKING LIST")
    c.setFont("Helvetica", 9)
    c.drawCentredString(w / 2, h - 33 * mm, "EXPORT DOCUMENT — KEEP WITH SHIPMENT")
    c.line(15 * mm, h - 38 * mm, w - 15 * mm, h - 38 * mm)

    y = h - 52 * mm
    step = 12 * mm

    row(y, "Consignee",           "MERIDIAN FREIGHT SOLUTIONS SDN BHD")
    y -= step
    row(y, "Invoice Number",      "INV-20240201")
    y -= step
    row(y, "HS Code",             "8542.31")
    y -= step
    row(y, "Description of Goods","Semiconductor Integrated Circuits — Grade A")
    y -= step
    row(y, "Port of Loading",     "NINGBO, CHINA")
    y -= step
    row(y, "Port of Discharge",   "PORT KLANG, MALAYSIA")
    y -= step
    row(y, "Incoterms",           "EXW")
    y -= step
    row(y, "Gross Weight",        "320.50 KG")
    y -= step
    row(y, "Net Weight",          "298.00 KG")
    y -= step
    row(y, "Number of Cartons",   "18 CTNS")
    y -= step
    row(y, "Marks & Numbers",     "N/M")

    c.line(15 * mm, y - 5 * mm, w - 15 * mm, y - 5 * mm)

    # Packing table header
    y -= 18 * mm
    c.setFont("Helvetica-Bold", 9)
    c.drawString(20 * mm, y, "CTN NO.")
    c.drawString(50 * mm, y, "DESCRIPTION")
    c.drawString(110 * mm, y, "QTY")
    c.drawString(140 * mm, y, "G.W.(KG)")
    c.drawString(170 * mm, y, "CBM")
    c.line(15 * mm, y - 2 * mm, w - 15 * mm, y - 2 * mm)

    c.setFont("Helvetica", 9)
    packing_rows = [
        ("1-6",  "IC Chips Type A (SOIC-8)",        "600 PCS", "107.00", "0.42"),
        ("7-12", "IC Chips Type B (QFP-64)",         "300 PCS", "108.00", "0.45"),
        ("13-18","IC Chips Type C (BGA-256)",        "150 PCS", "105.50", "0.41"),
    ]
    y -= 8 * mm
    for ctn, desc, qty, gw, cbm in packing_rows:
        c.drawString(20 * mm, y, ctn)
        c.drawString(50 * mm, y, desc)
        c.drawString(110 * mm, y, qty)
        c.drawString(140 * mm, y, gw)
        c.drawString(170 * mm, y, cbm)
        y -= 10 * mm

    c.line(15 * mm, y - 2 * mm, w - 15 * mm, y - 2 * mm)
    y -= 10 * mm
    c.setFont("Helvetica-Bold", 9)
    c.drawString(20 * mm, y, "TOTAL: 18 CTNS")
    c.drawString(140 * mm, y, "320.50")
    c.drawString(170 * mm, y, "1.28")

    c.setFont("Helvetica", 8)
    c.drawString(20 * mm, 20 * mm, "Date: 2024-02-01  |  Prepared by: Export Dept")
    c.drawString(w / 2, 20 * mm, "Page 1 of 1")

    c.showPage()
    c.save()
    print(f"Created: {out}")


# ──────────────────────────────────────────────
# Commercial Invoice #2 (PDF)  — EXW Hamburg
# ──────────────────────────────────────────────

def make_commercial_invoice_002():
    out = SAMPLES_DIR / "commercial_invoice_002.pdf"
    c = rl_canvas.Canvas(str(out), pagesize=A4)
    w, h = A4

    def row(y, label, value):
        c.setFont("Helvetica-Bold", 10)
        c.drawString(20 * mm, y, label + ":")
        c.setFont("Helvetica", 10)
        c.drawString(80 * mm, y, value)

    # Header
    c.setFont("Helvetica-Bold", 18)
    c.drawCentredString(w / 2, h - 22 * mm, "COMMERCIAL INVOICE")
    c.setFont("Helvetica-Bold", 9)
    c.drawCentredString(w / 2, h - 30 * mm, "ORIGINAL")
    c.line(15 * mm, h - 35 * mm, w - 15 * mm, h - 35 * mm)

    # Seller block
    c.setFont("Helvetica-Bold", 10)
    c.drawString(20 * mm, h - 46 * mm, "SELLER:")
    c.setFont("Helvetica", 9)
    c.drawString(20 * mm, h - 53 * mm, "BERLIN TRADE & EXPORT GMBH")
    c.drawString(20 * mm, h - 59 * mm, "14 Industriestrasse, 10115 Berlin, Germany")
    c.drawString(20 * mm, h - 65 * mm, "VAT: DE123456789")

    # Buyer block
    c.setFont("Helvetica-Bold", 10)
    c.drawString(110 * mm, h - 46 * mm, "BUYER / CONSIGNEE:")
    c.setFont("Helvetica", 9)
    c.drawString(110 * mm, h - 53 * mm, "DELTA IMPORT CORPORATION")
    c.drawString(110 * mm, h - 59 * mm, "55 Trade Park, Mumbai 400001, India")

    c.line(15 * mm, h - 72 * mm, w - 15 * mm, h - 72 * mm)

    y = h - 84 * mm
    step = 12 * mm

    row(y, "Invoice Number",      "INV-20240302")
    y -= step
    row(y, "Invoice Date",        "2024-03-02")
    y -= step
    row(y, "HS Code",             "9013.80")
    y -= step
    row(y, "Description of Goods","Optical Instruments and Laser Components")
    y -= step
    row(y, "Port of Loading",     "HAMBURG, GERMANY")
    y -= step
    row(y, "Port of Discharge",   "NHAVA SHEVA (JNPT), INDIA")
    y -= step
    row(y, "Incoterms",           "EXW HAMBURG")
    y -= step
    row(y, "Gross Weight",        "215.00 KG")
    y -= step
    row(y, "Net Weight",          "198.50 KG")
    y -= step
    row(y, "Currency",            "EUR")

    c.line(15 * mm, y - 5 * mm, w - 15 * mm, y - 5 * mm)

    # Line items table
    y -= 18 * mm
    c.setFont("Helvetica-Bold", 9)
    for col, text in [(20, "ITEM"), (60, "DESCRIPTION"), (120, "QTY"), (145, "UNIT PRICE"), (175, "AMOUNT")]:
        c.drawString(col * mm, y, text)
    c.line(15 * mm, y - 2 * mm, w - 15 * mm, y - 2 * mm)

    c.setFont("Helvetica", 9)
    items = [
        ("1", "Laser Diode Module 650nm",  "50 PCS",  "EUR 28.00",  "EUR 1,400.00"),
        ("2", "Beam Splitter Cube 25mm",   "30 PCS",  "EUR 45.00",  "EUR 1,350.00"),
        ("3", "Collimating Lens Assembly", "20 SETS",  "EUR 62.00",  "EUR 1,240.00"),
    ]
    y -= 8 * mm
    for item_no, desc, qty, up, amt in items:
        c.drawString(20 * mm, y, item_no)
        c.drawString(60 * mm, y, desc)
        c.drawString(120 * mm, y, qty)
        c.drawString(145 * mm, y, up)
        c.drawString(175 * mm, y, amt)
        y -= 10 * mm

    c.line(15 * mm, y - 2 * mm, w - 15 * mm, y - 2 * mm)
    y -= 10 * mm
    c.setFont("Helvetica-Bold", 10)
    c.drawString(140 * mm, y, "TOTAL: EUR 3,990.00")

    c.setFont("Helvetica", 8)
    c.drawString(20 * mm, 20 * mm, "Date of Issue: 2024-03-02  |  Authorised Signatory: _____________")
    c.drawString(w / 2 + 20 * mm, 20 * mm, "Page 1 of 1")

    c.showPage()
    c.save()
    print(f"Created: {out}")


if __name__ == "__main__":
    make_packing_list()
    make_commercial_invoice_002()
    print("Extra samples generated successfully.")
