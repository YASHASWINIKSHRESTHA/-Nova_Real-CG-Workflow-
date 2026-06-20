"""
Generate 6 additional demo shipments across inbox/incoming/ to populate the queue.

Scenarios:
  ACME_003  incoming  — consignee name typo (ACME IMPORT LTD vs ACME LOGISTICS PTE LTD)
  ACME_004  incoming  — clean docs, should auto-approve
  ACME_005  incoming  — wrong incoterms (DDP not in allowed list)
  ACME_006  incoming  — invoice number bad format (2026-INV-006 instead of INV-XXXX)
  ACME_007  incoming  — gross weight out of tolerance (1200 KG, expected 1000 ± 5%)
  TECHCO_001 incoming — different customer, HS code prefix mismatch

Run: python scripts/generate_more_samples.py
"""
import json
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

INBOX = Path(__file__).parent.parent / "inbox" / "incoming"


def _header(c, title: str, subtitle: str = "") -> None:
    w, h = A4
    c.setFont("Helvetica-Bold", 16)
    c.drawCentredString(w / 2, h - 22 * mm, title)
    if subtitle:
        c.setFont("Helvetica", 9)
        c.drawCentredString(w / 2, h - 30 * mm, subtitle)
    c.line(15 * mm, h - 34 * mm, w - 15 * mm, h - 34 * mm)


def _row(c, y, label, value, color=None):
    c.setFont("Helvetica-Bold", 10)
    c.drawString(20 * mm, y, label + ":")
    if color:
        c.setFillColor(color)
    c.setFont("Helvetica", 10)
    c.drawString(75 * mm, y, value)
    c.setFillColor(colors.black)


def _footer(c, note=""):
    c.setFont("Helvetica", 8)
    c.drawString(20 * mm, 18 * mm, "Date of Issue: 2026-06-18")
    if note:
        c.setFillColor(colors.red)
        c.drawString(20 * mm, 13 * mm, note)
        c.setFillColor(colors.black)
    c.drawString(140 * mm, 18 * mm, "Page 1 of 1")


def make_email(folder: Path, msg_id, from_addr, subject, body, customer, received_at):
    (folder / "email.json").write_text(json.dumps({
        "message_id": msg_id,
        "from": from_addr,
        "to": "cg@gocomet.com",
        "subject": subject,
        "body": body,
        "customer": customer,
        "received_at": received_at,
    }, indent=2), encoding="utf-8")


def make_pdf(folder: Path, filename: str, title: str, subtitle: str, rows: list, note: str = ""):
    c = rl_canvas.Canvas(str(folder / filename), pagesize=A4)
    w, h = A4
    _header(c, title, subtitle)
    y = h - 50 * mm
    step = 11 * mm
    for label, value, *extra in rows:
        color = extra[0] if extra else None
        _row(c, y, label, value, color)
        y -= step
    c.line(15 * mm, y - 3 * mm, w - 15 * mm, y - 3 * mm)
    _footer(c, note)
    c.showPage()
    c.save()
    print(f"  Created: {folder.name}/{filename}")


# ── ACME_003: consignee name typo on invoice ──────────────────────────────────
def make_003():
    folder = INBOX / "shipment_ACME_003"
    folder.mkdir(parents=True, exist_ok=True)
    make_email(folder, "su-acme-2026-003", "exports@acme-supplier.com",
               "Shipment docs — PO 4473 — ACME Logistics",
               "Please find attached docs for PO-4473. FOB Shanghai, HS 8471.30.",
               "Acme Logistics", "2026-06-18T07:15:00")
    make_pdf(folder, "bill_of_lading.pdf", "BILL OF LADING", "ORIGINAL — NON-NEGOTIABLE", [
        ("Consignee",         "ACME LOGISTICS PTE LTD"),
        ("Invoice Number",    "INV-20260003"),
        ("HS Code",           "8471.30"),
        ("Description",       "Printed Circuit Boards and Electronic Components"),
        ("Port of Loading",   "SHANGHAI"),
        ("Port of Discharge", "SINGAPORE"),
        ("Incoterms",         "FOB"),
        ("Gross Weight",      "1005.00 KG"),
    ])
    # Invoice has typo: ACME IMPORT LTD instead of ACME LOGISTICS PTE LTD
    make_pdf(folder, "commercial_invoice.pdf", "COMMERCIAL INVOICE", "", [
        ("Invoice Number",    "INV-20260003"),
        ("Invoice Date",      "2026-06-17"),
        ("Consignee",         "ACME IMPORT LTD", colors.red),   # ← typo
        ("Shipper",           "TECH EXPORT CO LTD, SHANGHAI"),
        ("HS Code",           "8471.30"),
        ("Description",       "Electronic PCB Assemblies"),
        ("Port of Loading",   "SHANGHAI"),
        ("Port of Discharge", "SINGAPORE"),
        ("Incoterms",         "FOB SHANGHAI"),
        ("Gross Weight",      "1005.00 KG"),
        ("Total Amount",      "USD 51,200.00"),
    ], note="NOTE: Consignee name differs from BOL — verify with customer")
    make_pdf(folder, "packing_list.pdf", "PACKING LIST", "", [
        ("Consignee",         "ACME LOGISTICS PTE LTD"),
        ("Invoice Number",    "INV-20260003"),
        ("HS Code",           "8471.30"),
        ("Description",       "Printed Circuit Boards"),
        ("Port of Loading",   "SHANGHAI"),
        ("Port of Discharge", "SINGAPORE"),
        ("Gross Weight",      "1005.00 KG"),
        ("Net Weight",        "960.00 KG"),
        ("Cartons",           "48"),
    ])
    print(f"  OK {folder.name} — consignee name mismatch on invoice")


# ── ACME_004: clean docs ───────────────────────────────────────────────────────
def make_004():
    folder = INBOX / "shipment_ACME_004"
    folder.mkdir(parents=True, exist_ok=True)
    make_email(folder, "su-acme-2026-004", "exports@acme-supplier.com",
               "Shipment docs — PO 4474 — ACME Logistics (CLEAN)",
               "All docs for PO-4474. FOB Ningbo, HS 8473.30. Clean set.",
               "Acme Logistics", "2026-06-18T08:30:00")
    for title, filename, sub in [
        ("BILL OF LADING",    "bill_of_lading.pdf",     "ORIGINAL — NON-NEGOTIABLE"),
        ("COMMERCIAL INVOICE","commercial_invoice.pdf",  ""),
        ("PACKING LIST",      "packing_list.pdf",        ""),
    ]:
        make_pdf(folder, filename, title, sub, [
            ("Consignee",         "ACME LOGISTICS PTE LTD"),
            ("Invoice Number",    "INV-20260004"),
            ("HS Code",           "8473.30"),
            ("Description",       "Electronic Semiconductor Components and PCB Assemblies"),
            ("Port of Loading",   "NINGBO"),
            ("Port of Discharge", "SINGAPORE"),
            ("Incoterms",         "FOB"),
            ("Gross Weight",      "998.00 KG"),
        ])
    print(f"  OK {folder.name} — clean, should auto-approve")


# ── ACME_005: wrong incoterms (DDP not in allowed list) ───────────────────────
def make_005():
    folder = INBOX / "shipment_ACME_005"
    folder.mkdir(parents=True, exist_ok=True)
    make_email(folder, "su-acme-2026-005", "logistics@acme-supplier.com",
               "Shipment docs — PO 4475 — ACME Logistics",
               "Attached docs for PO-4475. DDP Port Klang.",
               "Acme Logistics", "2026-06-18T09:45:00")
    for title, filename, sub in [
        ("BILL OF LADING",    "bill_of_lading.pdf",     "ORIGINAL — NON-NEGOTIABLE"),
        ("COMMERCIAL INVOICE","commercial_invoice.pdf",  ""),
        ("PACKING LIST",      "packing_list.pdf",        ""),
    ]:
        make_pdf(folder, filename, title, sub, [
            ("Consignee",         "ACME LOGISTICS PTE LTD"),
            ("Invoice Number",    "INV-20260005"),
            ("HS Code",           "8471.30"),
            ("Description",       "Electronic PCB Assemblies"),
            ("Port of Loading",   "GUANGZHOU"),
            ("Port of Discharge", "PORT KLANG"),
            ("Incoterms",         "DDP", colors.red),     # ← not in [FOB, CIF, EXW]
            ("Gross Weight",      "1010.00 KG"),
        ], note="NOTE: Incoterms DDP — verify agreed terms (expected FOB/CIF/EXW)" if "INVOICE" in title else "")
    print(f"  OK {folder.name} — incoterms DDP not in allowed list")


# ── ACME_006: invoice number bad format ───────────────────────────────────────
def make_006():
    folder = INBOX / "shipment_ACME_006"
    folder.mkdir(parents=True, exist_ok=True)
    make_email(folder, "su-acme-2026-006", "accounts@acme-supplier.com",
               "Shipment docs — PO 4476 — ACME Logistics",
               "Docs for PO-4476 attached. Please process.",
               "Acme Logistics", "2026-06-18T11:00:00")
    # All docs use a non-standard invoice number format
    for title, filename, sub in [
        ("BILL OF LADING",    "bill_of_lading.pdf",     "ORIGINAL — NON-NEGOTIABLE"),
        ("COMMERCIAL INVOICE","commercial_invoice.pdf",  ""),
        ("PACKING LIST",      "packing_list.pdf",        ""),
    ]:
        make_pdf(folder, filename, title, sub, [
            ("Consignee",         "ACME LOGISTICS PTE LTD"),
            ("Invoice Number",    "2026-INV-006", colors.red),   # ← should match INV-\d{4,}
            ("HS Code",           "8542.31"),
            ("Description",       "Integrated Circuit Boards and Semiconductor Devices"),
            ("Port of Loading",   "SHANGHAI"),
            ("Port of Discharge", "SINGAPORE"),
            ("Incoterms",         "CIF"),
            ("Gross Weight",      "1000.00 KG"),
        ], note="NOTE: Invoice ref 2026-INV-006 — non-standard format" if "INVOICE" in title else "")
    print(f"  OK {folder.name} — invoice number fails regex INV-\\d{{4,}}")


# ── ACME_007: gross weight out of tolerance ────────────────────────────────────
def make_007():
    folder = INBOX / "shipment_ACME_007"
    folder.mkdir(parents=True, exist_ok=True)
    make_email(folder, "su-acme-2026-007", "exports@acme-supplier.com",
               "Shipment docs — PO 4477 — ACME Logistics",
               "Docs for PO-4477. Heavier shipment this cycle.",
               "Acme Logistics", "2026-06-19T06:00:00")
    for title, filename, sub in [
        ("BILL OF LADING",    "bill_of_lading.pdf",     "ORIGINAL — NON-NEGOTIABLE"),
        ("COMMERCIAL INVOICE","commercial_invoice.pdf",  ""),
        ("PACKING LIST",      "packing_list.pdf",        ""),
    ]:
        make_pdf(folder, filename, title, sub, [
            ("Consignee",         "ACME LOGISTICS PTE LTD"),
            ("Invoice Number",    "INV-20260007"),
            ("HS Code",           "8471.30"),
            ("Description",       "PCB Electronic Assemblies and Semiconductor Parts"),
            ("Port of Loading",   "NINGBO"),
            ("Port of Discharge", "SINGAPORE"),
            ("Incoterms",         "FOB"),
            ("Gross Weight",      "1200.00 KG", colors.red),   # ← exceeds 1000 ± 5% tolerance
        ], note="NOTE: Weight 1200 KG exceeds expected 1000 KG ± 5%" if "INVOICE" in title else "")
    print(f"  OK {folder.name} — gross weight 1200 KG > 1000 KG ± 5% tolerance")


# ── TECHCO_001: different customer ────────────────────────────────────────────
def make_techco_001():
    folder = INBOX / "shipment_TECHCO_001"
    folder.mkdir(parents=True, exist_ok=True)
    make_email(folder, "su-techco-2026-001", "shipping@techco-global.com",
               "Shipment docs — TechCo Global — PO TC-0091",
               "Hi CG team, please find attached BOL, invoice and packing list for PO TC-0091.",
               "TechCo Global", "2026-06-19T10:30:00")
    for title, filename, sub in [
        ("BILL OF LADING",    "bill_of_lading.pdf",     "ORIGINAL — NON-NEGOTIABLE"),
        ("COMMERCIAL INVOICE","commercial_invoice.pdf",  ""),
        ("PACKING LIST",      "packing_list.pdf",        ""),
    ]:
        make_pdf(folder, filename, title, sub, [
            ("Consignee",         "TECHCO GLOBAL PTE LTD"),
            ("Invoice Number",    "INV-20260091"),
            ("HS Code",           "8471.60"),
            ("Description",       "Laptop Computers and Input Devices"),
            ("Port of Loading",   "SHANGHAI"),
            ("Port of Discharge", "SINGAPORE"),
            ("Incoterms",         "CIF"),
            ("Gross Weight",      "850.00 KG"),
        ])
    print(f"  OK {folder.name} — different customer TechCo Global")


def main():
    INBOX.mkdir(parents=True, exist_ok=True)
    print("=== Generating additional inbox shipments ===\n")
    make_003()
    make_004()
    make_005()
    make_006()
    make_007()
    make_techco_001()
    print(f"\n6 shipments added to {INBOX}")


if __name__ == "__main__":
    main()
