"""
Generate synthetic trade document samples:
  samples/clean_bol.pdf   — valid Bill of Lading (all 8 fields correct)
  samples/messy_invoice.jpg — Invoice image with a deliberate HS code mismatch
Run once: python scripts/generate_samples.py
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

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("Pillow not installed — run: pip install Pillow")
    sys.exit(1)

SAMPLES_DIR = Path(__file__).parent.parent / "samples"
SAMPLES_DIR.mkdir(exist_ok=True)


# ──────────────────────────────────────────────
# Clean BOL (PDF)
# ──────────────────────────────────────────────

def make_clean_bol():
    out = SAMPLES_DIR / "clean_bol.pdf"
    c = rl_canvas.Canvas(str(out), pagesize=A4)
    w, h = A4

    def row(y, label, value):
        c.setFont("Helvetica-Bold", 10)
        c.drawString(20 * mm, y, label + ":")
        c.setFont("Helvetica", 10)
        c.drawString(75 * mm, y, value)

    # Header
    c.setFont("Helvetica-Bold", 16)
    c.drawCentredString(w / 2, h - 25 * mm, "BILL OF LADING")
    c.setFont("Helvetica", 9)
    c.drawCentredString(w / 2, h - 33 * mm, "ORIGINAL — NON-NEGOTIABLE")

    c.line(15 * mm, h - 38 * mm, w - 15 * mm, h - 38 * mm)

    y = h - 50 * mm
    step = 12 * mm

    row(y, "Shipper / Exporter",   "TECH EXPORT CO LTD, 88 Pudong Ave, Shanghai, China")
    y -= step
    row(y, "Consignee",             "ACME LOGISTICS PTE LTD")
    y -= step
    row(y, "Notify Party",          "SAME AS CONSIGNEE")
    y -= step
    row(y, "Invoice Number",        "INV-20240115")
    y -= step
    row(y, "HS Code",               "8471.30")
    y -= step
    row(y, "Description of Goods",  "Printed Circuit Boards and Electronic Components")
    y -= step
    row(y, "Port of Loading",       "SHANGHAI")
    y -= step
    row(y, "Port of Discharge",     "SINGAPORE")
    y -= step
    row(y, "Incoterms",             "FOB")
    y -= step
    row(y, "Gross Weight",          "980.00 KG")
    y -= step
    row(y, "Measurement",           "4.200 CBM")
    y -= step
    row(y, "Number of Packages",    "42 CARTONS")

    c.line(15 * mm, y - 5 * mm, w - 15 * mm, y - 5 * mm)

    y -= 20 * mm
    c.setFont("Helvetica-Bold", 9)
    c.drawString(20 * mm, y, "Freight Charges:")
    c.setFont("Helvetica", 9)
    c.drawString(75 * mm, y, "PREPAID")

    y -= 12 * mm
    c.setFont("Helvetica", 8)
    c.drawString(20 * mm, y,
        "SHIPPED ON BOARD in apparent good order and condition unless otherwise noted herein.")

    # Footer
    c.setFont("Helvetica", 8)
    c.drawString(20 * mm, 20 * mm, "Date of Issue: 2024-01-15")
    c.drawString(w / 2, 20 * mm, "Page 1 of 1")

    c.showPage()
    c.save()
    print(f"Created: {out}")


# ──────────────────────────────────────────────
# Messy Invoice (JPEG with HS code mismatch)
# ──────────────────────────────────────────────

def make_messy_invoice():
    out = SAMPLES_DIR / "messy_invoice.jpg"
    W, H = 1240, 1754  # A4 at 150 DPI
    img = Image.new("RGB", (W, H), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

    try:
        font_title = ImageFont.truetype("arial.ttf", 48)
        font_bold = ImageFont.truetype("arialbd.ttf", 32)
        font = ImageFont.truetype("arial.ttf", 28)
        font_small = ImageFont.truetype("arial.ttf", 22)
    except OSError:
        font_title = ImageFont.load_default()
        font_bold = font_title
        font = font_title
        font_small = font_title

    # Title
    draw.text((W // 2, 80), "COMMERCIAL INVOICE", font=font_title, fill=(0, 0, 0), anchor="mm")
    draw.line([(60, 130), (W - 60, 130)], fill=(0, 0, 0), width=3)

    y = 170
    step = 55

    def field(label, value, color=(0, 0, 0)):
        nonlocal y
        draw.text((80, y), label + ":", font=font_bold, fill=(80, 80, 80))
        draw.text((480, y), value, font=font, fill=color)
        y += step

    field("Invoice No",         "INV-20240116")
    field("Invoice Date",       "2024-01-16")
    field("Consignee",          "ACME LOGISTICS PTE LTD")
    field("Shipper",            "GUANGZHOU PARTS CO., LTD")
    field("Port of Loading",    "GUANGZHOU, CHINA")
    field("Port of Discharge",  "SINGAPORE")
    field("Incoterms",          "CIF SINGAPORE")
    # Deliberate HS code mismatch — 9999.99 is not in allowed_prefixes
    field("HS Code",            "9999.99", color=(180, 0, 0))
    field("Description",        "Electronic Parts and Semiconductor Devices")
    field("Gross Weight",       "1050.00 KG")

    draw.line([(60, y + 10), (W - 60, y + 10)], fill=(0, 0, 0), width=2)

    y += 30
    draw.text((80, y), "NOTE: HS Code 9999.99 requires manual verification",
              font=font_small, fill=(200, 0, 0))

    y += 60
    draw.text((80, y), "Authorised Signature: ___________________", font=font_small, fill=(100, 100, 100))
    draw.text((80, H - 80), "Page 1 of 1  |  COPY — NOT ORIGINAL", font=font_small, fill=(150, 150, 150))

    img.save(str(out), "JPEG", quality=85)
    print(f"Created: {out}")


if __name__ == "__main__":
    make_clean_bol()
    make_messy_invoice()
    print("Samples generated successfully.")
