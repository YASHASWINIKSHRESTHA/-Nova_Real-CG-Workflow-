"""
Generate PRD.pdf for Nova Part 2 (max 1 page).
Run: python scripts/generate_prd.py
"""
import sys
from pathlib import Path

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable,
    )
    from reportlab.lib.enums import TA_LEFT, TA_CENTER
except ImportError:
    print("reportlab not installed — run: pip install reportlab")
    sys.exit(1)

OUT = Path(__file__).parent.parent / "PRD.pdf"

BLUE  = colors.HexColor("#1565FF")
DARK  = colors.HexColor("#05080F")
GREY  = colors.HexColor("#64748B")
GREEN = colors.HexColor("#059669")
RED   = colors.HexColor("#EF4444")
WHITE = colors.white


def build_prd():
    doc = SimpleDocTemplate(
        str(OUT), pagesize=A4,
        leftMargin=18*mm, rightMargin=18*mm,
        topMargin=14*mm, bottomMargin=14*mm,
    )
    styles = getSampleStyleSheet()

    def H1(text):
        return Paragraph(text, ParagraphStyle(
            "H1", fontSize=16, fontName="Helvetica-Bold",
            textColor=BLUE, spaceAfter=4, spaceBefore=6,
        ))

    def H2(text):
        return Paragraph(text, ParagraphStyle(
            "H2", fontSize=10, fontName="Helvetica-Bold",
            textColor=BLUE, spaceAfter=3, spaceBefore=8,
        ))

    def Body(text):
        return Paragraph(text, ParagraphStyle(
            "Body", fontSize=8.5, fontName="Helvetica",
            textColor=colors.HexColor("#1E293B"), spaceAfter=3, leading=12,
        ))

    def Bullet(text):
        return Paragraph(f"• {text}", ParagraphStyle(
            "Bullet", fontSize=8.5, fontName="Helvetica",
            textColor=colors.HexColor("#1E293B"), spaceAfter=2,
            leftIndent=12, leading=12,
        ))

    def Label(text):
        return Paragraph(text, ParagraphStyle(
            "Label", fontSize=8, fontName="Helvetica-Bold",
            textColor=GREY, spaceAfter=2, spaceBefore=4,
        ))

    story = []

    # ── Title ─────────────────────────────────────────────────────────────────
    story.append(Paragraph(
        "Nova — Part 2 Product Requirements Document",
        ParagraphStyle("Title", fontSize=18, fontName="Helvetica-Bold",
                       textColor=BLUE, spaceAfter=2, alignment=TA_CENTER),
    ))
    story.append(Paragraph(
        "GoComet DAW · CG Trade Document Validation Loop · June 2026",
        ParagraphStyle("Sub", fontSize=9, fontName="Helvetica",
                       textColor=GREY, spaceAfter=6, alignment=TA_CENTER),
    ))
    story.append(HRFlowable(width="100%", thickness=1, color=BLUE, spaceAfter=8))

    # ── Personas ──────────────────────────────────────────────────────────────
    story.append(H2("Personas"))
    persona_data = [
        ["CG Operator", "SU (Supplier)"],
        [
            "Clear shipments fast without manually reading each field.\n"
            "Never wrongly approve a mismatch.\n"
            "Receive a ready-to-send amendment draft — not a blank email.\n"
            "Full audit trail for disputes.",
            "Know exactly what to fix in one clear reply.\n"
            "Fast approval so cargo isn't delayed.\n"
            "No ambiguity — field name, found value, expected value.",
        ],
    ]
    pt = Table(persona_data, colWidths=[85*mm, 85*mm])
    pt.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BLUE),
        ("TEXTCOLOR",  (0, 0), (-1, 0), WHITE),
        ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",   (0, 0), (-1, 0), 8.5),
        ("FONTNAME",   (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE",   (0, 1), (-1, -1), 8),
        ("VALIGN",     (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#F8FAFC"), WHITE]),
        ("GRID",       (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING",  (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(pt)
    story.append(Spacer(1, 6))

    # ── JTBDs ────────────────────────────────────────────────────────────────
    story.append(H2("Jobs To Be Done"))
    story.append(Bullet(
        "<b>JTBD 1 (CG):</b> When an SU email with shipment docs arrives, I want the agent "
        "to validate all attachments — checking each field and cross-checking shared fields "
        "across all documents — and hand me a structured verification result, so I don't "
        "open and read every field myself."
    ))
    story.append(Bullet(
        "<b>JTBD 2 (CG):</b> When a shipment has discrepancies, I want a ready-to-send "
        "amendment draft listing each field's found-vs-expected value (and which document "
        "it came from), so I fix-and-send in one edit instead of typing from scratch."
    ))
    story.append(Spacer(1, 4))

    # ── North-Star Metric ────────────────────────────────────────────────────
    story.append(H2("North-Star Metric"))
    story.append(Body(
        "<b>Median CG validation cycle time per shipment</b> — measured from SU email arrival "
        "to CG sending reply — with incorrect-approval rate held ≈ 0%. "
        "One number a team lead can read on Day 14: does the agent reduce the median cycle "
        "time while keeping the wrong-approval rate near zero?"
    ))
    story.append(Spacer(1, 4))

    # ── Critical Failure Mode ────────────────────────────────────────────────
    story.append(H2("Critical Failure Mode (prevented by design)"))
    fm_data = [
        ["Failure Mode", "Prevention"],
        [
            "Agent auto-sends a wrong amendment or approval email to SU/customer.",
            "Pipeline halts at node_await_cg with status pending_cg_review. "
            "The only dispatch path is the Send button in the CG UI — a human click. "
            "No SMTP code exists anywhere in the system.",
        ],
    ]
    ft = Table(fm_data, colWidths=[60*mm, 110*mm])
    ft.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#7F1D1D")),
        ("TEXTCOLOR",  (0, 0), (-1, 0), WHITE),
        ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",   (0, 0), (-1, 0), 8.5),
        ("FONTNAME",   (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE",   (0, 1), (-1, -1), 8),
        ("VALIGN",     (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#FEF2F2"), WHITE]),
        ("GRID",       (0, 0), (-1, -1), 0.5, colors.HexColor("#FECACA")),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING",  (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(ft)
    story.append(Spacer(1, 6))

    # ── Out of Scope ──────────────────────────────────────────────────────────
    story.append(H2("Explicitly Out of Scope (production-path items)"))
    story.append(Body(
        "Real IMAP/SMTP integration · Per-customer auth & tenant isolation (OpenFGA) · "
        "ClickHouse analytics · Feedback/learning loop · Multi-language document support. "
        "Email plumbing is mocked via a folder-based inbox; the scored deliverable is the "
        "<i>logic</i>: trigger → multi-doc extraction → cross-validate → draft → human-send → query."
    ))

    story.append(Spacer(1, 4))
    story.append(HRFlowable(width="100%", thickness=0.5, color=GREY))
    story.append(Paragraph(
        "Nova Part 2 — GoComet DAW · Yashaswini Kulshrestha · June 2026",
        ParagraphStyle("Footer", fontSize=7, fontName="Helvetica",
                       textColor=GREY, alignment=TA_CENTER, spaceBefore=4),
    ))

    doc.build(story)
    print(f"PRD generated: {OUT}")


if __name__ == "__main__":
    build_prd()
