"""
Generate 3 additional synthetic trade documents to expand the eval gold set:
  samples/bol_002.pdf           — BOL: NINGBO→PORT KLANG, EXW, PCBs, weight ≈1000 kg
  samples/invoice_003.pdf       — Invoice: HS code mismatch (7326.90), SHANGHAI→SINGAPORE
  samples/packing_list_002.pdf  — Packing list: GUANGZHOU→SINGAPORE, CIF, semiconductor ICs

Run: python scripts/generate_gold_samples.py
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
# BOL #2  (valid, should auto-approve)
# ──────────────────────────────────────────────
def make_bol_002():
    out = SAMPLES_DIR / "bol_002.pdf"
    c = rl_canvas.Canvas(str(out), pagesize=A4)
    w, h = A4

    def row(y, label, value):
        c.setFont("Helvetica-Bold", 10)
        c.drawString(20 * mm, y, label + ":")
        c.setFont("Helvetica", 10)
        c.drawString(75 * mm, y, value)

    c.setFont("Helvetica-Bold", 16)
    c.drawCentredString(w / 2, h - 25 * mm, "BILL OF LADING")
    c.setFont("Helvetica", 9)
    c.drawCentredString(w / 2, h - 33 * mm, "ORIGINAL — NON-NEGOTIABLE")
    c.line(15 * mm, h - 38 * mm, w - 15 * mm, h - 38 * mm)

    y = h - 50 * mm
    step = 12 * mm

    row(y, "Shipper / Exporter",   "NINGBO TECH EXPORTS CO LTD, 22 Jiangnan Rd, Ningbo, China")
    y -= step
    row(y, "Consignee",             "ACME LOGISTICS PTE LTD")
    y -= step
    row(y, "Notify Party",          "SAME AS CONSIGNEE")
    y -= step
    row(y, "Invoice Number",        "INV-20240220")
    y -= step
    row(y, "HS Code",               "8473.30")
    y -= step
    row(y, "Description of Goods",  "Printed Circuit Boards — Computer Peripherals")
    y -= step
    row(y, "Port of Loading",       "NINGBO")
    y -= step
    row(y, "Port of Discharge",     "PORT KLANG")
    y -= step
    row(y, "Incoterms",             "EXW")
    y -= step
    row(y, "Gross Weight",          "975.00 KG")
    y -= step
    row(y, "Measurement",           "5.100 CBM")
    y -= step
    row(y, "Number of Packages",    "55 CARTONS")

    c.line(15 * mm, y - 5 * mm, w - 15 * mm, y - 5 * mm)
    y -= 20 * mm
    c.setFont("Helvetica-Bold", 9)
    c.drawString(20 * mm, y, "Freight Charges:")
    c.setFont("Helvetica", 9)
    c.drawString(75 * mm, y, "COLLECT")
    y -= 12 * mm
    c.setFont("Helvetica", 8)
    c.drawString(20 * mm, y,
        "SHIPPED ON BOARD in apparent good order and condition unless otherwise noted herein.")
    c.setFont("Helvetica", 8)
    c.drawString(20 * mm, 20 * mm, "Date of Issue: 2024-02-20")
    c.drawString(w / 2, 20 * mm, "Page 1 of 1")
    c.showPage()
    c.save()
    print(f"Created: {out}")


# ──────────────────────────────────────────────
# Invoice #3 (HS code mismatch — should trigger draft_amendment)
# ──────────────────────────────────────────────
def make_invoice_003():
    out = SAMPLES_DIR / "invoice_003.pdf"
    c = rl_canvas.Canvas(str(out), pagesize=A4)
    w, h = A4

    def row(y, label, value, bold_value=False):
        c.setFont("Helvetica-Bold", 10)
        c.drawString(20 * mm, y, label + ":")
        c.setFont("Helvetica-Bold" if bold_value else "Helvetica", 10)
        c.drawString(80 * mm, y, value)

    c.setFont("Helvetica-Bold", 18)
    c.drawCentredString(w / 2, h - 22 * mm, "COMMERCIAL INVOICE")
    c.setFont("Helvetica-Bold", 9)
    c.drawCentredString(w / 2, h - 30 * mm, "COPY — NOT FOR CUSTOMS")
    c.line(15 * mm, h - 35 * mm, w - 15 * mm, h - 35 * mm)

    c.setFont("Helvetica-Bold", 10)
    c.drawString(20 * mm, h - 46 * mm, "SELLER:")
    c.setFont("Helvetica", 9)
    c.drawString(20 * mm, h - 53 * mm, "SHANGHAI PARTS TRADING CO LTD")
    c.drawString(20 * mm, h - 59 * mm, "99 Pudong New Area, Shanghai 200120, China")

    c.setFont("Helvetica-Bold", 10)
    c.drawString(110 * mm, h - 46 * mm, "BUYER / CONSIGNEE:")
    c.setFont("Helvetica", 9)
    c.drawString(110 * mm, h - 53 * mm, "ACME LOGISTICS PTE LTD")
    c.drawString(110 * mm, h - 59 * mm, "12 Harbour Front Walk, Singapore 098633")

    c.line(15 * mm, h - 65 * mm, w - 15 * mm, h - 65 * mm)

    y = h - 78 * mm
    step = 12 * mm

    row(y, "Invoice Number",      "INV-20240318")
    y -= step
    row(y, "Invoice Date",        "2024-03-18")
    y -= step
    # Deliberate wrong HS code — 7326.90 (steel articles) not in allowed prefixes
    row(y, "HS Code",             "7326.90", bold_value=True)
    y -= step
    row(y, "Description of Goods","Electronic Components and PCB Assemblies")
    y -= step
    row(y, "Port of Loading",     "SHANGHAI")
    y -= step
    row(y, "Port of Discharge",   "SINGAPORE")
    y -= step
    row(y, "Incoterms",           "FOB")
    y -= step
    row(y, "Gross Weight",        "1020.00 KG")
    y -= step
    row(y, "Currency",            "USD")

    y -= 8 * mm
    c.setFont("Helvetica", 8)
    c.setFillColorRGB(0.7, 0, 0)
    c.drawString(20 * mm, y, "NOTE: HS Code 7326.90 pending reclassification — verify with customs broker.")
    c.setFillColorRGB(0, 0, 0)

    c.setFont("Helvetica", 8)
    c.drawString(20 * mm, 20 * mm, "Date of Issue: 2024-03-18  |  Authorised Signatory: _____________")
    c.drawString(w / 2 + 20 * mm, 20 * mm, "Page 1 of 1")
    c.showPage()
    c.save()
    print(f"Created: {out}")


# ──────────────────────────────────────────────
# Packing List #2  (GUANGZHOU→SINGAPORE, CIF)
# ──────────────────────────────────────────────
def make_packing_list_002():
    out = SAMPLES_DIR / "packing_list_002.pdf"
    c = rl_canvas.Canvas(str(out), pagesize=A4)
    w, h = A4

    def row(y, label, value):
        c.setFont("Helvetica-Bold", 10)
        c.drawString(20 * mm, y, label + ":")
        c.setFont("Helvetica", 10)
        c.drawString(80 * mm, y, value)

    c.setFont("Helvetica-Bold", 16)
    c.drawCentredString(w / 2, h - 25 * mm, "PACKING LIST")
    c.setFont("Helvetica", 9)
    c.drawCentredString(w / 2, h - 33 * mm, "EXPORT DOCUMENT — FOR CUSTOMS USE")
    c.line(15 * mm, h - 38 * mm, w - 15 * mm, h - 38 * mm)

    y = h - 52 * mm
    step = 12 * mm

    row(y, "Consignee",           "ACME LOGISTICS PTE LTD")
    y -= step
    row(y, "Invoice Number",      "INV-20240410")
    y -= step
    row(y, "HS Code",             "8542.39")
    y -= step
    row(y, "Description of Goods","Semiconductor Integrated Circuits — Mixed Grade")
    y -= step
    row(y, "Port of Loading",     "GUANGZHOU")
    y -= step
    row(y, "Port of Discharge",   "SINGAPORE")
    y -= step
    row(y, "Incoterms",           "CIF")
    y -= step
    row(y, "Gross Weight",        "1050.00 KG")
    y -= step
    row(y, "Net Weight",          "1010.00 KG")
    y -= step
    row(y, "Number of Cartons",   "24 CTNS")
    y -= step
    row(y, "Marks & Numbers",     "ACME/SIN/2024-04")

    c.line(15 * mm, y - 5 * mm, w - 15 * mm, y - 5 * mm)

    y -= 18 * mm
    c.setFont("Helvetica-Bold", 9)
    c.drawString(20 * mm, y, "CTN NO.")
    c.drawString(50 * mm, y, "DESCRIPTION")
    c.drawString(115 * mm, y, "QTY")
    c.drawString(142 * mm, y, "G.W.(KG)")
    c.drawString(170 * mm, y, "CBM")
    c.line(15 * mm, y - 2 * mm, w - 15 * mm, y - 2 * mm)

    c.setFont("Helvetica", 9)
    packing_rows = [
        ("1-8",   "IC SOIC-16 Mixed Lot A",  "800 PCS", "350.00", "0.56"),
        ("9-16",  "IC QFN-32 Mixed Lot B",    "600 PCS", "350.00", "0.54"),
        ("17-24", "IC BGA-144 Mixed Lot C",   "400 PCS", "350.00", "0.52"),
    ]
    y -= 8 * mm
    for ctn, desc, qty, gw, cbm in packing_rows:
        c.drawString(20 * mm, y, ctn)
        c.drawString(50 * mm, y, desc)
        c.drawString(115 * mm, y, qty)
        c.drawString(142 * mm, y, gw)
        c.drawString(170 * mm, y, cbm)
        y -= 10 * mm

    c.line(15 * mm, y - 2 * mm, w - 15 * mm, y - 2 * mm)
    y -= 10 * mm
    c.setFont("Helvetica-Bold", 9)
    c.drawString(20 * mm, y, "TOTAL: 24 CTNS")
    c.drawString(142 * mm, y, "1050.00")
    c.drawString(170 * mm, y, "1.62")

    c.setFont("Helvetica", 8)
    c.drawString(20 * mm, 20 * mm, "Date: 2024-04-10  |  Prepared by: Export Dept")
    c.drawString(w / 2, 20 * mm, "Page 1 of 1")
    c.showPage()
    c.save()
    print(f"Created: {out}")


if __name__ == "__main__":
    make_bol_002()
    make_invoice_003()
    make_packing_list_002()
    print("Gold expansion samples generated successfully.")
