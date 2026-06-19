"""
Generate PRD_part2.pdf for Nova Part 2 CG Operations UI module.
Run: python scripts/generate_prd_part2.py
Output: docs/PRD_part2.pdf
"""
import sys
from pathlib import Path

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable,
    )
    from reportlab.lib.enums import TA_CENTER
except ImportError:
    print("reportlab not installed — run: pip install reportlab")
    sys.exit(1)

OUT = Path(__file__).parent.parent / "docs" / "PRD_part2.pdf"

BLUE  = colors.HexColor("#1565FF")
DARK  = colors.HexColor("#05080F")
GREY  = colors.HexColor("#64748B")
WHITE = colors.white
RED_BG = colors.HexColor("#7F1D1D")
RED_ROW = colors.HexColor("#FEF2F2")
RED_GRID = colors.HexColor("#FECACA")


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

def table_style(header_bg=BLUE, header_fg=WHITE, row_colors=None):
    row_colors = row_colors or [colors.HexColor("#F8FAFC"), WHITE]
    return TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0),  header_bg),
        ("TEXTCOLOR",     (0, 0), (-1, 0),  header_fg),
        ("FONTNAME",      (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, 0),  8.5),
        ("FONTNAME",      (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE",      (0, 1), (-1, -1), 8),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), row_colors),
        ("GRID",          (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ])


def build_prd():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(OUT), pagesize=A4,
        leftMargin=18*mm, rightMargin=18*mm,
        topMargin=14*mm, bottomMargin=14*mm,
    )
    story = []

    # ── Title ──────────────────────────────────────────────────────────────────
    story.append(Paragraph(
        "Nova — Part 2 Product Requirements Document",
        ParagraphStyle("Title", fontSize=18, fontName="Helvetica-Bold",
                       textColor=BLUE, spaceAfter=2, alignment=TA_CENTER),
    ))
    story.append(Paragraph(
        "GoComet DAW · CG Operations UI Module · June 2026",
        ParagraphStyle("Sub", fontSize=9, fontName="Helvetica",
                       textColor=GREY, spaceAfter=6, alignment=TA_CENTER),
    ))
    story.append(HRFlowable(width="100%", thickness=1, color=BLUE, spaceAfter=8))

    # ── Problem ────────────────────────────────────────────────────────────────
    story.append(H2("Problem"))
    story.append(Body(
        "Customs Gateway (CG) operators at GoComet receive raw agent pipeline outputs — "
        "JSON blobs with extracted fields, validation verdicts, and draft emails — with no "
        "structured interface to review, edit, or dispatch. Operators must manually parse "
        "pipeline data, copy amendment emails into email clients, and track reply status in "
        "spreadsheets. This creates review errors, inconsistent reply quality, and no audit "
        "trail for human decisions."
    ))

    # ── Goal ───────────────────────────────────────────────────────────────────
    story.append(H2("Goal"))
    story.append(Body(
        "Deliver a zero-friction CG operator UI that: (1) surfaces pipeline outputs in a "
        "structured 4-state flow, (2) gives operators a single 'Send' control (<b>the agent "
        "never auto-dispatches</b>), (3) makes cross-document discrepancies visible before any "
        "decision, and (4) persists every operator action to the audit log."
    ))
    story.append(Spacer(1, 4))

    # ── Personas ──────────────────────────────────────────────────────────────
    story.append(H2("Personas"))
    persona_data = [
        ["CG Operator", "SU (Supplier)"],
        [
            "• Clear shipments fast without reading every field\n"
            "• Never wrongly approve a cross-doc mismatch\n"
            "• Receive a ready-to-send amendment draft\n"
            "• Full audit trail for disputes",
            "• Know exactly what to fix in one clear reply\n"
            "• Fast approval so cargo isn't delayed\n"
            "• No ambiguity — field name, found value, expected value\n"
            "• Which document had the discrepancy",
        ],
    ]
    pt = Table(persona_data, colWidths=[85*mm, 85*mm])
    pt.setStyle(table_style())
    story.append(pt)
    story.append(Spacer(1, 6))

    # ── 4 UI States ────────────────────────────────────────────────────────────
    story.append(H2("4 UI States per Shipment"))
    states_data = [
        ["State", "Trigger", "CG Sees"],
        ["1. Incoming",
         "SU email in inbox/incoming/",
         "Email metadata, attachment list, "Process Shipment" button"],
        ["2. Verification Result",
         "Pipeline completes",
         "Per-doc field tables + confidence + verdict; cross-doc consistency strip; audit trail"],
        ["3. Discrepancy Detail",
         "Flagged field",
         "Found vs. expected side-by-side; source snippet; cross-doc diff by document"],
        ["4. Draft Reply",
         "Operator moves to reply tab",
         "Editable email draft; "Send (mock)" button — ONLY human action sends"],
    ]
    st_tbl = Table(states_data, colWidths=[38*mm, 42*mm, 90*mm])
    st_tbl.setStyle(table_style())
    story.append(st_tbl)
    story.append(Spacer(1, 6))

    # ── 5-Step Pipeline ────────────────────────────────────────────────────────
    story.append(H2("5-Step Pipeline Wiring"))
    pipeline_data = [
        ["Step", "Node", "What Happens"],
        ["1. Trigger",       "node_ingest_email",      "SU email detected → CG clicks "Process Shipment" → mint trace_id"],
        ["2. Extract all",   "node_extract_all",       "extract() per attachment via ThreadPoolExecutor (parallel, per-doc provenance)"],
        ["3. Cross-validate","node_cross_validate",    "Deterministic: consignee_name · hs_code · invoice_number across docs"],
        ["4. Decide & draft","node_route_shipment",    "Cross-doc gate → Part 1 trust gate → Decision + draft email via GPT-4o-mini"],
        ["5. Store & await", "node_persist + node_await_cg", "SQLite persist; folder stays in processing/; pipeline STOPS — CG must act"],
    ]
    pp = Table(pipeline_data, colWidths=[28*mm, 44*mm, 98*mm])
    pp.setStyle(table_style())
    story.append(pp)
    story.append(Spacer(1, 4))

    # ── Design Guarantees ──────────────────────────────────────────────────────
    story.append(H2("4 Design Guarantees"))
    story.append(Bullet("<b>No auto-send.</b> Pipeline terminates at node_await_cg. Only a CG click dispatches a reply."))
    story.append(Bullet("<b>Cross-doc gate.</b> all_consistent=False forces draft_amendment. No path from inconsistency to auto-approve."))
    story.append(Bullet("<b>Per-attachment provenance.</b> Each doc has its own ExtractedDoc with doc_type. Fields are never merged across documents."))
    story.append(Bullet("<b>Crash-safe.</b> _state.json written to shipment folder after pipeline; state survives page reloads."))
    story.append(Spacer(1, 6))

    # ── Critical Failure Mode ──────────────────────────────────────────────────
    story.append(H2("Critical Failure Mode (prevented by design)"))
    fm_data = [
        ["Failure Mode", "Prevention"],
        [
            "Agent auto-sends a wrong amendment or approval email to SU / customer.",
            "Pipeline halts at node_await_cg with status=pending_cg_review. "
            "The only dispatch path is the "Send (mock)" button in the CG UI — a human click. "
            "No SMTP code exists anywhere in the system. Even if the pipeline LLM "
            "generates a wrong draft, the operator reviews and edits it before sending.",
        ],
    ]
    ft = Table(fm_data, colWidths=[55*mm, 115*mm])
    ft.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0),  RED_BG),
        ("TEXTCOLOR",     (0, 0), (-1, 0),  WHITE),
        ("FONTNAME",      (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, 0),  8.5),
        ("FONTNAME",      (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE",      (0, 1), (-1, -1), 8),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [RED_ROW, WHITE]),
        ("GRID",          (0, 0), (-1, -1), 0.5, RED_GRID),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(ft)
    story.append(Spacer(1, 6))

    # ── Non-Goals ─────────────────────────────────────────────────────────────
    story.append(H2("Explicitly Out of Scope (POC)"))
    story.append(Body(
        "Real IMAP/SMTP integration · Per-customer auth &amp; tenant isolation · "
        "ClickHouse analytics · Feedback/learning loop · Multi-language support · "
        "Production concurrency. "
        "The inbox is folder-based mock; the scored deliverable is the <i>logic</i>: "
        "trigger → multi-doc extraction → cross-validate → draft → human-send → NL query."
    ))

    story.append(Spacer(1, 4))
    story.append(HRFlowable(width="100%", thickness=0.5, color=GREY))
    story.append(Paragraph(
        "Nova Part 2 PRD · GoComet DAW · Yashaswini Kulshrestha · June 2026",
        ParagraphStyle("Footer", fontSize=7, fontName="Helvetica",
                       textColor=GREY, alignment=TA_CENTER, spaceBefore=4),
    ))

    doc.build(story)
    print(f"PRD_part2.pdf generated: {OUT}")


if __name__ == "__main__":
    build_prd()
