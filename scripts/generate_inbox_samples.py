"""
Generate synthetic trade document PDFs for the two demo inbox shipments.

Shipment ACME_001 (clean — all 3 docs agree):
  bill_of_lading.pdf       — HS 8471.30, consignee ACME LOGISTICS PTE LTD
  commercial_invoice.pdf   — HS 8471.30, same consignee
  packing_list.pdf         — HS 8471.30, same consignee

Shipment ACME_002 (cross-doc HS code mismatch):
  bill_of_lading.pdf       — HS 8471.30
  commercial_invoice.pdf   — HS 9999.99  ← deliberate mismatch
  packing_list.pdf         — HS 8471.30

Run: python scripts/generate_inbox_samples.py
"""
import sys
from pathlib import Path

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas as rl_canvas
    from reportlab.lib import colors
except ImportError:
    print("reportlab not installed — run: pip install reportlab")
    sys.exit(1)

INBOX = Path(__file__).parent.parent / "inbox"


# ── helpers ───────────────────────────────────────────────────────────────────

def _header(c, title: str, subtitle: str = "") -> None:
    w, h = A4
    c.setFont("Helvetica-Bold", 16)
    c.drawCentredString(w / 2, h - 22 * mm, title)
    if subtitle:
        c.setFont("Helvetica", 9)
        c.drawCentredString(w / 2, h - 30 * mm, subtitle)
    c.line(15 * mm, h - 34 * mm, w - 15 * mm, h - 34 * mm)


def _row(c, y: float, label: str, value: str, color=None) -> None:
    c.setFont("Helvetica-Bold", 10)
    c.drawString(20 * mm, y, label + ":")
    if color:
        c.setFillColor(color)
    c.setFont("Helvetica", 10)
    c.drawString(75 * mm, y, value)
    c.setFillColor(colors.black)


def _footer(c, note: str = "") -> None:
    c.setFont("Helvetica", 8)
    c.drawString(20 * mm, 18 * mm, "Date of Issue: 2026-06-13")
    if note:
        c.setFillColor(colors.red)
        c.drawString(20 * mm, 13 * mm, note)
        c.setFillColor(colors.black)
    c.drawString(140 * mm, 18 * mm, "Page 1 of 1")


# ── ACME_001 docs (all consistent, clean) ─────────────────────────────────────

def make_bol_001(out_path: Path) -> None:
    c = rl_canvas.Canvas(str(out_path), pagesize=A4)
    w, h = A4
    _header(c, "BILL OF LADING", "ORIGINAL — NON-NEGOTIABLE")
    y = h - 50 * mm
    step = 12 * mm
    rows = [
        ("Consignee",           "ACME LOGISTICS PTE LTD"),
        ("Invoice Number",      "INV-20260001"),
        ("HS Code",             "8471.30"),
        ("Description",         "Printed Circuit Boards and Electronic Components"),
        ("Port of Loading",     "SHANGHAI"),
        ("Port of Discharge",   "SINGAPORE"),
        ("Incoterms",           "FOB"),
        ("Gross Weight",        "985.00 KG"),
        ("Packages",            "42 CARTONS"),
    ]
    for label, value in rows:
        _row(c, y, label, value)
        y -= step
    c.line(15 * mm, y - 3 * mm, w - 15 * mm, y - 3 * mm)
    _footer(c)
    c.showPage()
    c.save()
    print(f"Created: {out_path}")


def make_invoice_001(out_path: Path) -> None:
    c = rl_canvas.Canvas(str(out_path), pagesize=A4)
    w, h = A4
    _header(c, "COMMERCIAL INVOICE")
    y = h - 50 * mm
    step = 12 * mm
    rows = [
        ("Invoice Number",      "INV-20260001"),
        ("Invoice Date",        "2026-06-12"),
        ("Consignee",           "ACME LOGISTICS PTE LTD"),
        ("Shipper",             "TECH EXPORT CO LTD, SHANGHAI"),
        ("HS Code",             "8471.30"),
        ("Description",         "Electronic PCB Assemblies and Semiconductor Devices"),
        ("Port of Loading",     "SHANGHAI"),
        ("Port of Discharge",   "SINGAPORE"),
        ("Incoterms",           "FOB SHANGHAI"),
        ("Gross Weight",        "985.00 KG"),
        ("Total Amount",        "USD 48,500.00"),
    ]
    for label, value in rows:
        _row(c, y, label, value)
        y -= step
    c.line(15 * mm, y - 3 * mm, w - 15 * mm, y - 3 * mm)
    _footer(c)
    c.showPage()
    c.save()
    print(f"Created: {out_path}")


def make_packing_001(out_path: Path) -> None:
    c = rl_canvas.Canvas(str(out_path), pagesize=A4)
    w, h = A4
    _header(c, "PACKING LIST")
    y = h - 50 * mm
    step = 12 * mm
    rows = [
        ("Consignee",           "ACME LOGISTICS PTE LTD"),
        ("Invoice Number",      "INV-20260001"),
        ("HS Code",             "8471.30"),
        ("Description",         "Printed Circuit Boards — Electronic Components"),
        ("Port of Loading",     "SHANGHAI"),
        ("Port of Discharge",   "SINGAPORE"),
        ("Gross Weight",        "985.00 KG"),
        ("Net Weight",          "940.00 KG"),
        ("Cartons",             "42"),
        ("Dimensions",          "60x40x30 CM each"),
    ]
    for label, value in rows:
        _row(c, y, label, value)
        y -= step
    c.line(15 * mm, y - 3 * mm, w - 15 * mm, y - 3 * mm)
    _footer(c)
    c.showPage()
    c.save()
    print(f"Created: {out_path}")


# ── ACME_002 docs (HS code mismatch on invoice) ───────────────────────────────

def make_bol_002(out_path: Path) -> None:
    c = rl_canvas.Canvas(str(out_path), pagesize=A4)
    w, h = A4
    _header(c, "BILL OF LADING", "ORIGINAL — NON-NEGOTIABLE")
    y = h - 50 * mm
    step = 12 * mm
    rows = [
        ("Consignee",           "ACME LOGISTICS PTE LTD"),
        ("Invoice Number",      "INV-20260002"),
        ("HS Code",             "8471.30"),
        ("Description",         "Electronic PCB Assemblies — Semiconductor Parts"),
        ("Port of Loading",     "GUANGZHOU"),
        ("Port of Discharge",   "SINGAPORE"),
        ("Incoterms",           "FOB"),
        ("Gross Weight",        "1020.00 KG"),
        ("Packages",            "56 CARTONS"),
    ]
    for label, value in rows:
        _row(c, y, label, value)
        y -= step
    c.line(15 * mm, y - 3 * mm, w - 15 * mm, y - 3 * mm)
    _footer(c)
    c.showPage()
    c.save()
    print(f"Created: {out_path}")


def make_invoice_002_mismatch(out_path: Path) -> None:
    """Invoice with deliberate HS code mismatch: 9999.99 instead of 8471.30."""
    c = rl_canvas.Canvas(str(out_path), pagesize=A4)
    w, h = A4
    _header(c, "COMMERCIAL INVOICE")
    y = h - 50 * mm
    step = 12 * mm

    _row(c, y, "Invoice Number",   "INV-20260002");     y -= step
    _row(c, y, "Invoice Date",     "2026-06-12");        y -= step
    _row(c, y, "Consignee",        "ACME LOGISTICS PTE LTD"); y -= step
    _row(c, y, "Shipper",          "GUANGZHOU PARTS CO LTD"); y -= step
    # Deliberate mismatch
    _row(c, y, "HS Code",          "9999.99", color=colors.red); y -= step
    _row(c, y, "Description",      "Electronic Parts and Semiconductor Devices"); y -= step
    _row(c, y, "Port of Loading",  "GUANGZHOU"); y -= step
    _row(c, y, "Port of Discharge","SINGAPORE"); y -= step
    _row(c, y, "Incoterms",        "FOB GUANGZHOU"); y -= step
    _row(c, y, "Gross Weight",     "1020.00 KG"); y -= step
    _row(c, y, "Total Amount",     "USD 62,300.00"); y -= step

    c.line(15 * mm, y - 3 * mm, w - 15 * mm, y - 3 * mm)
    _footer(c, note="NOTE: HS Code 9999.99 — verify against BOL (8471.30)")
    c.showPage()
    c.save()
    print(f"Created: {out_path}")


def make_packing_002(out_path: Path) -> None:
    c = rl_canvas.Canvas(str(out_path), pagesize=A4)
    w, h = A4
    _header(c, "PACKING LIST")
    y = h - 50 * mm
    step = 12 * mm
    rows = [
        ("Consignee",           "ACME LOGISTICS PTE LTD"),
        ("Invoice Number",      "INV-20260002"),
        ("HS Code",             "8471.30"),
        ("Description",         "Electronic PCB Assemblies — Semiconductor Parts"),
        ("Port of Loading",     "GUANGZHOU"),
        ("Port of Discharge",   "SINGAPORE"),
        ("Gross Weight",        "1020.00 KG"),
        ("Net Weight",          "975.00 KG"),
        ("Cartons",             "56"),
        ("Dimensions",          "55x38x28 CM each"),
    ]
    for label, value in rows:
        _row(c, y, label, value)
        y -= step
    c.line(15 * mm, y - 3 * mm, w - 15 * mm, y - 3 * mm)
    _footer(c)
    c.showPage()
    c.save()
    print(f"Created: {out_path}")


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    folder_001 = INBOX / "incoming" / "shipment_ACME_001"
    folder_002 = INBOX / "incoming" / "shipment_ACME_002"
    folder_001.mkdir(parents=True, exist_ok=True)
    folder_002.mkdir(parents=True, exist_ok=True)

    print("=== Generating shipment_ACME_001 (clean — all consistent) ===")
    make_bol_001(folder_001 / "bill_of_lading.pdf")
    make_invoice_001(folder_001 / "commercial_invoice.pdf")
    make_packing_001(folder_001 / "packing_list.pdf")

    print("\n=== Generating shipment_ACME_002 (HS code mismatch on invoice) ===")
    make_bol_002(folder_002 / "bill_of_lading.pdf")
    make_invoice_002_mismatch(folder_002 / "commercial_invoice.pdf")
    make_packing_002(folder_002 / "packing_list.pdf")

    print("\nInbox sample PDFs generated successfully.")
    print(f"Drop into: {INBOX / 'incoming'}")


if __name__ == "__main__":
    main()
