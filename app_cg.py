"""
Nova CG Operations — Part 2 Streamlit UI
4 states per shipment:
  1. Incoming   — email metadata + attachments + Process button
  2. Verification — field table per doc + cross-doc consistency strip
  3. Discrepancy  — click a flagged field for found/expected + snippets
  4. Draft Reply  — editable draft email + mock Send (agent NEVER auto-sends)
"""
import base64
import json
import sys
import tempfile
import uuid
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))

from nova.infrastructure import database as db
from nova.pipeline.pipeline_cg import run_cg
from nova.pipeline.pipeline import (
    node_setup, node_extractor, node_validator, node_router, node_persist,
)
from nova.pipeline import resume
from nova.domain.models import PipelineState
from nova.inbox import watcher, INBOX
from nova.query import ask

st.set_page_config(
    page_title="GoComet Nova CG — Trade Validator",
    page_icon="G",
    layout="wide",
    initial_sidebar_state="expanded",
)
db.init_db()

# ── brand tokens ───────────────────────────────────────────────────────────────
BLUE      = "#1565FF"
BLUE_DIM  = "rgba(21,101,255,0.28)"
BLUE_GLOW = "rgba(21,101,255,0.55)"
GREEN     = "#059669"
AMBER     = "#D97706"
RED       = "#EF4444"


# ── CSS (same dark-glass theme as Part 1) ─────────────────────────────────────
def bg_b64():
    p = Path(__file__).parent / "assets" / "bg_Img.jpg"
    return base64.b64encode(p.read_bytes()).decode() if p.exists() else ""


def inject_css():
    b64 = bg_b64()
    bg = (f"url('data:image/jpeg;base64,{b64}') center center / cover no-repeat"
          if b64 else
          "linear-gradient(135deg,#05080F 0%,#080E20 50%,#05080F 100%)")

    # Load Inter via <link> — more reliable than @import inside injected <style>
    st.markdown(
        '<link rel="preconnect" href="https://fonts.googleapis.com">'
        '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
        '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">',
        unsafe_allow_html=True,
    )

    st.markdown(f"""<style>
/* ── Font: target text nodes only, not SVG/canvas/Streamlit internals ── */
html,body,input,button,textarea,select,
.stApp,[class*="st"],.stMarkdown,p,span,div,label,th,td,a{{
  font-family:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif!important;}}
*{{box-sizing:border-box;}}

/* ── Parallax CSS variables (updated by JS mousemove handler) ── */
:root{{--nova-px:0px;--nova-py:0px;}}

/* ── Full-page dark canvas fallback ── */
html{{background:#05080F!important;min-height:100vh!important;}}
body{{background:transparent!important;min-height:100vh!important;}}

/* ── Background: oversized by 10% on each side so parallax never exposes edges ── */
html::before{{
  content:'';position:fixed;
  inset:-10%;
  background:{bg};background-size:cover;background-position:center center;
  transform:translateX(var(--nova-px)) translateY(var(--nova-py));
  transition:transform 0.9s cubic-bezier(0.23,1,0.32,1);
  z-index:-2;will-change:transform;pointer-events:none;}}
html::after{{content:'';position:fixed;inset:0;
  background:radial-gradient(ellipse at 70% 25%,rgba(5,8,20,.15) 0%,rgba(5,8,20,.50) 55%,rgba(5,8,20,.75) 100%);
  z-index:-1;pointer-events:none;}}

/* ── Strip every Streamlit container background ── */
.stApp,[data-testid="stAppViewContainer"],[data-testid="stHeader"],
[data-testid="stBottom"],section[data-testid="stSidebar"],
[data-testid="stMain"],[data-testid="stAppViewBlockContainer"],
[data-testid="stSidebarContent"]{{background:transparent!important;}}
[data-testid="stDecoration"]{{display:none!important;}}

/* ── Sidebar ── */
section[data-testid="stSidebar"]>div:first-child{{
  background:rgba(5,10,28,0.90)!important;backdrop-filter:blur(28px)!important;
  -webkit-backdrop-filter:blur(28px)!important;
  border-right:1px solid {BLUE_DIM}!important;
  padding:0!important;}}
section[data-testid="stSidebar"] [data-testid="stVerticalBlock"]{{
  overflow-x:hidden!important;}}
section[data-testid="stSidebar"] button{{
  text-align:left!important;width:100%!important;
  border-radius:10px!important;margin-bottom:2px!important;}}

/* ── Main content ── */
.main .block-container{{
  background:rgba(5,10,28,0.68)!important;backdrop-filter:blur(16px)!important;
  -webkit-backdrop-filter:blur(16px)!important;
  border-radius:20px!important;border:1px solid {BLUE_DIM}!important;
  box-shadow:0 0 80px rgba(21,101,255,.08),inset 0 1px 0 rgba(255,255,255,.05)!important;
  padding:1.4rem 2rem 2rem!important;max-width:1500px!important;}}

/* ── Prevent column overflow without clipping inner text ── */
[data-testid="column"]{{min-width:0!important;}}
.stMarkdown,[data-testid="stMarkdownContainer"]{{min-width:0!important;}}

h1,h2,h3,h4,h5{{color:#fff!important;letter-spacing:-.01em;}}
h1{{background:linear-gradient(90deg,#fff 55%,{BLUE});
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;
  background-clip:text;font-size:1.9rem!important;font-weight:800!important;}}
.stMarkdown p,.stMarkdown li,[data-testid="stText"]{{
  color:rgba(255,255,255,.90)!important;font-size:.93rem;line-height:1.65;}}
.stCaption,[data-testid="stCaptionContainer"] p{{
  color:rgba(255,255,255,.90)!important;font-size:.80rem!important;}}

[data-baseweb="tab-list"]{{background:rgba(255,255,255,.04)!important;
  border-radius:12px!important;padding:4px!important;
  border:1px solid rgba(255,255,255,.07)!important;gap:4px!important;}}
[data-baseweb="tab"]{{color:rgba(255,255,255,.90)!important;font-weight:500!important;
  border-radius:8px!important;transition:all .2s ease!important;}}
[data-baseweb="tab"]:hover{{color:rgba(255,255,255,.88)!important;
  background:rgba(255,255,255,.06)!important;}}
[aria-selected="true"][data-baseweb="tab"]{{background:{BLUE}!important;color:#fff!important;
  border-radius:8px!important;box-shadow:0 2px 14px {BLUE_GLOW}!important;}}

.stExpander{{background:rgba(8,15,40,.68)!important;backdrop-filter:blur(12px)!important;
  border:1px solid {BLUE_DIM}!important;border-left:3px solid {BLUE}!important;
  border-radius:12px!important;margin-bottom:6px!important;transition:all .2s ease!important;}}
.stExpander:hover{{background:rgba(12,22,55,.80)!important;
  border-color:rgba(21,101,255,.50)!important;
  box-shadow:0 4px 20px rgba(21,101,255,.14)!important;}}
.stExpander>details,.stExpander>details>summary,
.stExpander [data-testid="stExpanderDetails"]{{background:transparent!important;}}

[data-testid="metric-container"]{{background:rgba(8,15,40,.75)!important;
  backdrop-filter:blur(12px)!important;border:1px solid {BLUE_DIM}!important;
  border-top:3px solid {BLUE}!important;border-radius:12px!important;
  padding:14px 18px!important;box-shadow:0 4px 16px rgba(21,101,255,.10)!important;}}
[data-testid="metric-container"] [data-testid="stMetricValue"]{{
  color:#fff!important;font-size:1.8rem!important;font-weight:700!important;}}
[data-testid="metric-container"] [data-testid="stMetricLabel"]{{
  color:rgba(255,255,255,.92)!important;font-weight:500!important;}}

[data-testid="stAlert"]{{backdrop-filter:blur(10px)!important;
  border-radius:10px!important;border-left-width:4px!important;}}
.stCodeBlock,.stCodeBlock pre,code{{background:rgba(0,0,0,.55)!important;
  border:1px solid rgba(21,101,255,.18)!important;border-radius:8px!important;
  color:rgba(255,255,255,.92)!important;}}

/* ── File uploader ── */
[data-testid="stFileUploaderDropzone"]{{
  background:rgba(8,15,40,.58)!important;border:2px dashed {BLUE}!important;
  border-radius:14px!important;transition:all .25s ease!important;padding:20px!important;}}
[data-testid="stFileUploaderDropzone"]:hover{{
  background:rgba(21,101,255,.08)!important;box-shadow:0 0 22px {BLUE_GLOW}!important;}}
[data-testid="stFileUploaderDropzone"] p,
[data-testid="stFileUploaderDropzone"] span,
[data-testid="stFileUploaderDropzoneInstructions"] span{{color:rgba(255,255,255,.82)!important;}}
[data-testid="stFileUploaderDropzoneInput"]{{
  width:0!important;height:0!important;overflow:hidden!important;
  opacity:0!important;position:absolute!important;pointer-events:none!important;}}
[data-testid="stFileUploaderDropzone"] button{{
  background:rgba(21,101,255,.18)!important;border:1px solid rgba(21,101,255,.45)!important;
  border-radius:8px!important;color:#fff!important;font-weight:600!important;
  padding:6px 20px!important;font-size:.84rem!important;}}
[data-testid="stFileUploaderDropzone"] button:hover{{
  background:rgba(21,101,255,.35)!important;box-shadow:0 0 12px rgba(21,101,255,.40)!important;}}
[data-testid="stFileUploaderDropzone"] [data-testid="stIconMaterial"]{{display:none!important;}}
[data-testid="stFileUploader"]>label,[data-testid="stFileUploader"]>div>label{{display:none!important;}}
[data-testid="stFileUploader"]{{padding-top:0!important;}}

.stTextInput input,.stSelectbox [data-baseweb="select"]>div,textarea{{
  background:rgba(8,15,40,.75)!important;border:1px solid {BLUE_DIM}!important;
  border-radius:10px!important;color:#fff!important;transition:border-color .2s ease!important;}}
.stTextInput input:focus,textarea:focus{{border-color:{BLUE}!important;
  box-shadow:0 0 0 2px {BLUE_GLOW}!important;}}
[data-baseweb="select"] [data-testid="stMarkdownContainer"] p,
[data-baseweb="option"]{{color:rgba(255,255,255,.90)!important;}}

[data-testid="stBaseButton-primary"]{{background:{BLUE}!important;border:none!important;
  border-radius:10px!important;color:#fff!important;font-weight:700!important;
  letter-spacing:.03em!important;box-shadow:0 4px 18px {BLUE_GLOW}!important;
  transition:all .2s ease!important;}}
[data-testid="stBaseButton-primary"]:hover{{background:#1a75ff!important;
  box-shadow:0 6px 28px rgba(21,101,255,.65)!important;transform:translateY(-1px)!important;}}
[data-testid="stBaseButton-secondary"]{{background:rgba(8,15,40,.72)!important;
  border:1px solid {BLUE_DIM}!important;border-radius:10px!important;
  color:rgba(255,255,255,.88)!important;font-weight:500!important;transition:all .2s ease!important;}}
[data-testid="stBaseButton-secondary"]:hover{{background:rgba(21,101,255,.12)!important;
  border-color:rgba(21,101,255,.55)!important;}}

hr{{border:none!important;border-top:1px solid rgba(21,101,255,.18)!important;margin:1.4rem 0!important;}}
[data-testid="stSpinner"]{{background:rgba(5,10,28,.80)!important;border-radius:10px;
  padding:10px 16px;border:1px solid {BLUE_DIM};}}
[data-testid="stJson"]{{background:rgba(0,0,0,.50)!important;
  border:1px solid {BLUE_DIM}!important;border-radius:10px!important;}}

::-webkit-scrollbar{{width:6px;height:6px;}}
::-webkit-scrollbar-track{{background:rgba(255,255,255,.04);border-radius:3px;}}
::-webkit-scrollbar-thumb{{background:{BLUE_DIM};border-radius:3px;}}
::-webkit-scrollbar-thumb:hover{{background:{BLUE};}}
::placeholder{{color:rgba(255,255,255,.55)!important;}}

@keyframes pulse-glow{{
  0%  {{box-shadow:0 0 0 0 rgba(21,101,255,0),0 0 10px rgba(21,101,255,.5),0 0 0 3px rgba(21,101,255,.22);}}
  50% {{box-shadow:0 0 0 5px rgba(21,101,255,0),0 0 28px rgba(21,101,255,.85),0 0 0 3px rgba(21,101,255,.50);}}
  100%{{box-shadow:0 0 0 0 rgba(21,101,255,0),0 0 10px rgba(21,101,255,.5),0 0 0 3px rgba(21,101,255,.22);}}}}
@keyframes card-glow{{
  0%,100%{{box-shadow:0 0 0 2px rgba(21,101,255,.22),0 0 18px rgba(21,101,255,.42),inset 0 0 24px rgba(21,101,255,.06);}}
  50%{{box-shadow:0 0 0 5px rgba(21,101,255,.50),0 0 52px rgba(21,101,255,.95),inset 0 0 40px rgba(21,101,255,.16);}}}}
@keyframes dot-pulse{{0%,100%{{opacity:1;}}50%{{opacity:.55;}}}}
</style>""", unsafe_allow_html=True)


inject_css()


def inject_parallax_js():
    """Mouse-following parallax: translates the html::before background layer."""
    st.markdown("""
<script>
(function(){
  var ticking = false;
  function onMove(e){
    if(ticking) return;
    ticking = true;
    requestAnimationFrame(function(){
      var cx = window.innerWidth/2, cy = window.innerHeight/2;
      var dx = (e.clientX - cx)/cx;   /* -1 … +1 */
      var dy = (e.clientY - cy)/cy;
      var str = 26;                    /* max px translation */
      /* Setting on <html> so html::before picks it up via var(--nova-px) */
      document.documentElement.style.setProperty('--nova-px', (-dx*str)+'px');
      document.documentElement.style.setProperty('--nova-py', (-dy*str)+'px');
      ticking = false;
    });
  }
  function attach(){ document.addEventListener('mousemove', onMove); }
  if(document.readyState==='loading'){
    document.addEventListener('DOMContentLoaded', attach);
  } else { attach(); }
})();
</script>
""", unsafe_allow_html=True)


inject_parallax_js()


# ── shared HTML helpers ────────────────────────────────────────────────────────

def badge(text: str, bg: str, color: str = "#fff") -> str:
    return (f'<span style="background:{bg};color:{color};padding:2px 8px;border-radius:5px;'
            f'font-size:.68rem;font-weight:700;letter-spacing:.04em;white-space:nowrap;">{text}</span>')


def phase_badge(phase: str, reply_sent: bool = False) -> str:
    if reply_sent:
        return badge("SENT", "rgba(5,150,105,.30)", GREEN)
    cfg = {
        "incoming":   ("NEW",        "rgba(21,101,255,.28)", "#7EB5FF"),
        "processing": ("PROCESSING", "rgba(217,119,6,.28)",  AMBER),
        "processed":  ("PROCESSED",  "rgba(5,150,105,.18)",  GREEN),
    }
    txt, bg, col = cfg.get(phase, ("UNKNOWN", "rgba(100,100,100,.3)", "rgba(255,255,255,.82)"))
    return badge(txt, bg, col)


def action_color(action: str) -> str:
    return {"auto_approve": GREEN, "flag_for_review": AMBER, "draft_amendment": RED}.get(action, "rgba(255,255,255,.82)")


def consistency_icon(status: str) -> str:
    return {"consistent": "&#10003;", "inconsistent": "&#10007;", "insufficient_data": "&#8212;"}.get(status, "?")


def consistency_color(status: str) -> str:
    return {"consistent": GREEN, "inconsistent": RED, "insufficient_data": AMBER}.get(status, "rgba(255,255,255,.82)")


def conf_color(c: float) -> str:
    return GREEN if c >= .85 else (AMBER if c >= .50 else RED)


def verdict_badge(status: str) -> str:
    cfg = {
        "match":     ("rgba(5,150,105,.25)", GREEN, "MATCH &#10003;"),
        "mismatch":  ("rgba(239,68,68,.25)", RED,   "MISMATCH &#10007;"),
        "uncertain": ("rgba(217,119,6,.25)", AMBER, "UNCERTAIN ?"),
    }
    bg, col, lbl = cfg.get(status, ("rgba(100,100,100,.2)", "rgba(255,255,255,.82)", status.upper()))
    return (f'<span style="background:{bg};color:{col};padding:2px 7px;border-radius:5px;'
            f'font-size:.66rem;font-weight:700;">{lbl}</span>')


# ── sidebar ────────────────────────────────────────────────────────────────────
def render_sidebar():
    with st.sidebar:
        st.markdown(
            '<div style="padding:22px 18px 16px;border-bottom:1px solid rgba(21,101,255,.20);">'
            '<div style="display:flex;align-items:center;gap:12px;">'
            '<div style="width:42px;height:42px;border-radius:12px;flex-shrink:0;'
            'background:linear-gradient(135deg,#1565FF 0%,#0A3FCC 60%,#0730A8 100%);'
            'display:flex;align-items:center;justify-content:center;'
            'font-size:1.4rem;font-weight:900;color:#fff;'
            'box-shadow:0 4px 16px rgba(21,101,255,.50);letter-spacing:-.02em;">'
            'G</div>'
            '<div>'
            '<div style="font-size:1.05rem;font-weight:800;color:#fff;letter-spacing:-.01em;">'
            'GoComet <span style="color:#7EB5FF;">Nova</span></div>'
            '<div style="font-size:.60rem;color:rgba(255,255,255,.48);font-weight:500;'
            'letter-spacing:.10em;text-transform:uppercase;margin-top:1px;">CG Operations Platform</div>'
            '</div></div></div>',
            unsafe_allow_html=True,
        )

        if "cg_nav" not in st.session_state:
            st.session_state["cg_nav"] = "inbox"

        nav_items = [
            ("inbox",    "Inbox",    "&#128235;"),
            ("pipeline", "Pipeline", "&#128640;"),
            ("history",  "History",  "&#128220;"),
            ("query",    "NL Query", "&#128172;"),
            ("rules",    "Rules",    "&#128210;"),
            ("settings", "Settings", "&#9881;"),
        ]
        st.markdown('<div style="padding:8px 12px;">', unsafe_allow_html=True)
        for key, label, icon in nav_items:
            active = st.session_state["cg_nav"] == key
            if active:
                st.markdown(
                    f'<div style="display:flex;align-items:center;gap:10px;'
                    'padding:10px 14px;border-radius:10px;margin-bottom:4px;'
                    f'background:rgba(21,101,255,.18);border:1px solid rgba(21,101,255,.38);">'
                    f'<span>{icon}</span>'
                    f'<span style="color:#fff;font-weight:600;font-size:.88rem;">{label}</span>'
                    '</div>',
                    unsafe_allow_html=True,
                )
            else:
                if st.button(label, key=f"nav_{key}", use_container_width=True):
                    st.session_state["cg_nav"] = key
                    st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

        # quick stats from DB
        try:
            _conn = db.get_conn()
            _row = _conn.execute(
                "SELECT COUNT(*) as n, "
                "SUM(CASE WHEN status='auto_approve' THEN 1 ELSE 0 END) as approved, "
                "SUM(CASE WHEN status='draft_amendment' THEN 1 ELSE 0 END) as amended "
                "FROM shipments"
            ).fetchone()
            _crow = _conn.execute(
                "SELECT COALESCE(SUM(cost_usd),0) as total_cost FROM checkpoints"
            ).fetchone()
            _conn.close()
            _n = _row["n"] or 0
            _appr = _row["approved"] or 0
            _amend = _row["amended"] or 0
            _cost = _crow["total_cost"] or 0.0
        except Exception:
            _n = _appr = _amend = 0; _cost = 0.0

        st.markdown(
            f'<div style="padding:8px 14px 4px;">'
            f'<div style="color:rgba(255,255,255,.38);font-size:.58rem;font-weight:700;'
            f'letter-spacing:.10em;text-transform:uppercase;margin-bottom:6px;">Quick Stats</div>'
            f'<div style="display:grid;grid-template-columns:1fr 1fr;gap:5px;">'
            f'<div style="background:rgba(5,150,105,.10);border:1px solid rgba(5,150,105,.22);'
            f'border-radius:7px;padding:6px 9px;">'
            f'<div style="color:#059669;font-size:.90rem;font-weight:700;">{_appr}</div>'
            f'<div style="color:rgba(255,255,255,.55);font-size:.58rem;">Approved</div></div>'
            f'<div style="background:rgba(239,68,68,.10);border:1px solid rgba(239,68,68,.22);'
            f'border-radius:7px;padding:6px 9px;">'
            f'<div style="color:#EF4444;font-size:.90rem;font-weight:700;">{_amend}</div>'
            f'<div style="color:rgba(255,255,255,.55);font-size:.58rem;">Amended</div></div>'
            f'<div style="background:rgba(21,101,255,.10);border:1px solid rgba(21,101,255,.22);'
            f'border-radius:7px;padding:6px 9px;grid-column:1/-1;">'
            f'<div style="color:#7EB5FF;font-size:.90rem;font-weight:700;">${_cost:.4f}</div>'
            f'<div style="color:rgba(255,255,255,.55);font-size:.58rem;">Total API cost · {_n} runs</div>'
            f'</div></div></div>',
            unsafe_allow_html=True,
        )
        st.markdown('<div style="height:8px;"></div>', unsafe_allow_html=True)
        st.markdown(
            '<div style="margin:0 12px 20px 12px;">'
            '<div style="display:flex;align-items:center;gap:10px;padding:10px 14px;'
            'background:rgba(5,150,105,.12);border:1px solid rgba(5,150,105,.30);border-radius:10px;">'
            '<div style="width:8px;height:8px;border-radius:50%;background:#059669;flex-shrink:0;'
            'box-shadow:0 0 8px rgba(5,150,105,.80);animation:dot-pulse 2.4s ease-in-out infinite;"></div>'
            '<div><div style="color:#fff;font-size:.76rem;font-weight:600;">System Status</div>'
            '<div style="color:#059669;font-size:.66rem;">All systems operational</div>'
            '</div></div></div>',
            unsafe_allow_html=True,
        )


render_sidebar()

# ── page header ───────────────────────────────────────────────────────────────
_nav = st.session_state.get("cg_nav", "inbox")
_titles = {
    "inbox":    ("Inbox",           "SU emails with attachments → agent validates → CG reviews and sends"),
    "pipeline": ("Pipeline Runner", "Upload any trade document — extract · validate · route · store."),
    "history":  ("History",         "All processed shipments and their outcomes"),
    "query":    ("NL Query",        "Natural language → read-only SQL against the live database"),
    "rules":    ("Rules",           "Customer validation rules loaded from config/rules.yaml — never embedded in prompts."),
    "settings": ("Settings",        "System configuration and environment status."),
}
_title, _sub = _titles.get(_nav, ("Nova CG", ""))
st.markdown(
    f'<div style="margin-bottom:12px;">'
    f'<h1 style="margin:0 0 2px;">{_title}</h1>'
    f'<p style="color:rgba(255,255,255,.95);font-size:.85rem;margin:0;">{_sub}</p></div>',
    unsafe_allow_html=True,
)


# ══════════════════════════════════════════════════════════════════════════════
# LOAD PIPELINE STATE  (from _state.json written into folder)
# ══════════════════════════════════════════════════════════════════════════════

def load_pipeline_state(folder: Path) -> PipelineState | None:
    state_file = folder / "_state.json"
    if not state_file.exists():
        # try session-state cache
        cached = st.session_state.get("cg_states", {}).get(str(folder))
        return PipelineState(**cached) if cached else None
    try:
        return PipelineState.model_validate_json(state_file.read_text(encoding="utf-8"))
    except Exception:
        return None


# ══════════════════════════════════════════════════════════════════════════════
# RENDER HELPERS — reused across states
# ══════════════════════════════════════════════════════════════════════════════

def render_email_card(email: dict, n_attachments: int, attachment_names: list[str]) -> None:
    st.markdown(
        '<div style="font-size:.70rem;font-weight:700;color:#7EB5FF;'
        'letter-spacing:.09em;text-transform:uppercase;margin-bottom:8px;">Email Metadata</div>',
        unsafe_allow_html=True,
    )
    meta_html = (
        '<div style="background:rgba(8,15,40,.65);border:1px solid rgba(21,101,255,.18);'
        'border-radius:12px;padding:14px 18px;margin-bottom:12px;">'
    )
    for label, val in [
        ("From",     email.get("from", "—")),
        ("To",       email.get("to",   "—")),
        ("Subject",  email.get("subject", "—")),
        ("Customer", email.get("customer", "—")),
        ("Received", email.get("received_at", "—")),
    ]:
        meta_html += (
            f'<div style="display:flex;gap:12px;padding:5px 0;'
            f'border-bottom:1px solid rgba(255,255,255,.05);">'
            f'<div style="min-width:80px;color:#7EB5FF;font-size:.75rem;font-weight:600;">{label}</div>'
            f'<div style="color:rgba(255,255,255,.88);font-size:.80rem;">{val}</div>'
            f'</div>'
        )
    meta_html += '</div>'
    st.markdown(meta_html, unsafe_allow_html=True)

    st.markdown(
        f'<div style="font-size:.70rem;font-weight:700;color:#7EB5FF;'
        f'letter-spacing:.09em;text-transform:uppercase;margin-bottom:8px;">'
        f'Attachments ({n_attachments})</div>',
        unsafe_allow_html=True,
    )
    att_html = '<div style="display:flex;flex-direction:column;gap:6px;">'
    for name in attachment_names:
        att_html += (
            f'<div style="display:flex;align-items:center;gap:10px;padding:8px 14px;'
            f'background:rgba(8,15,40,.58);border:1px solid rgba(21,101,255,.13);border-radius:8px;">'
            f'<span style="font-size:1rem;">&#128196;</span>'
            f'<span style="color:#fff;font-size:.82rem;font-family:monospace;">{name}</span>'
            f'</div>'
        )
    att_html += '</div>'
    st.markdown(att_html, unsafe_allow_html=True)


def render_cross_doc_strip(ps: PipelineState) -> None:
    """Horizontal strip showing cross-doc consistency per shared field."""
    if not ps.cross_doc:
        return
    st.markdown(
        '<div style="font-size:.70rem;font-weight:700;color:#7EB5FF;'
        'letter-spacing:.09em;text-transform:uppercase;margin:14px 0 8px;">'
        'Cross-Document Consistency</div>',
        unsafe_allow_html=True,
    )
    strip_html = '<div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:10px;">'
    for v in ps.cross_doc.verdicts:
        icon  = consistency_icon(v.status)
        color = consistency_color(v.status)
        strip_html += (
            f'<div style="background:rgba(8,15,40,.70);border:1px solid {color}44;'
            f'border-left:3px solid {color};border-radius:8px;padding:8px 14px;">'
            f'<div style="color:{color};font-size:.70rem;font-weight:700;">{icon} {v.status.upper()}</div>'
            f'<div style="color:#fff;font-size:.78rem;font-weight:600;margin-top:2px;">'
            f'{v.field.replace("_"," ").title()}</div>'
            f'<div style="color:rgba(255,255,255,.90);font-size:.65rem;margin-top:2px;">'
            f'{v.reason[:80]}{"…" if len(v.reason) > 80 else ""}</div>'
            f'</div>'
        )
    strip_html += '</div>'
    st.markdown(strip_html, unsafe_allow_html=True)


def render_per_doc_tables(ps: PipelineState) -> None:
    """Field table for each extracted document with its per-doc validation verdicts."""
    if not ps.extracted_docs:
        return

    for i, (doc, validation) in enumerate(zip(ps.extracted_docs, ps.per_doc_validation)):
        doc_path = ps.raw_doc_paths[i] if i < len(ps.raw_doc_paths) else ""
        doc_filename = Path(doc_path).name if doc_path else f"Doc {i+1}"

        st.markdown(
            f'<div style="font-size:.70rem;font-weight:700;color:#7EB5FF;'
            f'letter-spacing:.09em;text-transform:uppercase;margin-top:14px;margin-bottom:6px;">'
            f'&#128196; {doc.doc_type} — {doc_filename}</div>',
            unsafe_allow_html=True,
        )

        verdict_map = {v.field: v for v in validation.verdicts}

        tbl = (
            '<div style="background:rgba(5,10,28,.60);border:1px solid rgba(21,101,255,.13);'
            'border-radius:12px;overflow:hidden;margin-bottom:8px;">'
            '<table style="width:100%;border-collapse:collapse;table-layout:fixed;">'
            '<colgroup>'
            '<col style="width:14%">'   # Field
            '<col style="width:15%">'   # Value
            '<col style="width:16%">'   # Expected
            '<col style="width:6%">'    # Conf
            '<col style="width:12%">'   # Verdict
            '<col style="width:37%">'   # Reason
            '</colgroup>'
            '<thead><tr style="border-bottom:1px solid rgba(255,255,255,.07);">'
        )
        for h in ["Field", "Value", "Expected (Rule)", "Conf", "Verdict", "Reason"]:
            tbl += (f'<th style="color:#7EB5FF;font-size:.63rem;font-weight:700;'
                    f'letter-spacing:.07em;text-transform:uppercase;padding:7px 10px;'
                    f'text-align:left;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">'
                    f'{h}</th>')
        tbl += '</tr></thead><tbody>'

        for fname in doc.field_names():
            fv = doc.get_field(fname)
            verd = verdict_map.get(fname)
            status = verd.status if verd else "uncertain"
            reason = verd.reason if verd else "—"
            cc = conf_color(fv.confidence)
            expected_val = (verd.expected or "—") if verd else "—"
            exp_color = AMBER if (verd and verd.status == "mismatch") else "rgba(255,255,255,.48)"
            tbl += (
                f'<tr style="border-bottom:1px solid rgba(255,255,255,.04);">'
                f'<td style="color:#fff;font-weight:600;font-size:.75rem;padding:6px 10px;'
                f'overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">'
                f'{fname.replace("_"," ").title()}</td>'
                f'<td style="color:rgba(255,255,255,.82);font-family:monospace;font-size:.73rem;'
                f'padding:6px 10px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">'
                f'{fv.value or "—"}</td>'
                f'<td style="color:{exp_color};font-family:monospace;font-size:.68rem;'
                f'padding:6px 10px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" '
                f'title="{expected_val}">'
                f'{expected_val[:24]}{"…" if len(expected_val) > 24 else ""}</td>'
                f'<td style="padding:6px 10px;white-space:nowrap;">'
                f'<span style="color:{cc};font-weight:700;font-size:.74rem;">'
                f'{int(fv.confidence*100)}%</span></td>'
                f'<td style="padding:6px 10px;overflow:hidden;">{verdict_badge(status)}</td>'
                f'<td style="color:rgba(255,255,255,.90);font-size:.70rem;padding:6px 10px;'
                f'overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" '
                f'title="{reason}">'
                f'{reason[:70]}{"…" if len(reason) > 70 else ""}</td>'
                f'</tr>'
            )

        tbl += '</tbody></table></div>'
        st.markdown(tbl, unsafe_allow_html=True)


def render_discrepancy_detail(ps: PipelineState) -> None:
    """Click-open expanders for each flagged field showing found/expected + snippets."""
    if not ps.per_doc_validation:
        st.info("No validation data available.")
        return

    # Collect all mismatches/uncertain across docs
    flagged_fields: dict[str, list] = {}  # fname → list of (doc_type, fv, verdict)
    for doc, validation in zip(ps.extracted_docs, ps.per_doc_validation):
        for v in validation.verdicts:
            if v.status in ("mismatch", "uncertain"):
                if v.field not in flagged_fields:
                    flagged_fields[v.field] = []
                fv = doc.get_field(v.field)
                flagged_fields[v.field].append((doc.doc_type, fv, v))

    # Also flag cross-doc inconsistencies
    cross_flagged: dict[str, "CrossDocVerdict"] = {}
    if ps.cross_doc:
        for cv in ps.cross_doc.verdicts:
            if cv.status == "inconsistent":
                cross_flagged[cv.field] = cv

    all_problem_fields = set(flagged_fields.keys()) | set(cross_flagged.keys())

    if not all_problem_fields:
        st.success("No discrepancies found — all fields passed validation across all documents.")
        return

    # ── Rule Comparison Summary ──────────────────────────────────────────────
    # One row per issue: Field | Doc | Expected (Rule) | Found in Doc | Status
    _summ_rows = []
    for _fn in sorted(all_problem_fields):
        for _dt, _fv, _v in flagged_fields.get(_fn, []):
            _summ_rows.append((_fn, _dt, _v.expected or "—", _fv.value or "—", _v.status))
        if _fn in cross_flagged and not flagged_fields.get(_fn):
            _cv = cross_flagged[_fn]
            _vals = " / ".join(f"{k}: {v}" for k, v in list(_cv.values_by_doc.items())[:3])
            _summ_rows.append((_fn, "cross-doc", "consistent across docs", _vals, "inconsistent"))

    if _summ_rows:
        _stbl = (
            '<div style="background:rgba(5,10,28,.72);border:1px solid rgba(239,68,68,.25);'
            'border-radius:12px;overflow:hidden;margin-bottom:16px;">'
            '<div style="padding:8px 12px;border-bottom:1px solid rgba(239,68,68,.18);'
            'background:rgba(239,68,68,.08);">'
            '<span style="color:#EF4444;font-size:.65rem;font-weight:700;letter-spacing:.08em;'
            'text-transform:uppercase;">Rule Comparison — Expected vs Found</span></div>'
            '<table style="width:100%;border-collapse:collapse;">'
            '<thead><tr style="border-bottom:1px solid rgba(255,255,255,.07);">'
        )
        for _h in ["Field", "Doc", "Expected (Rule)", "Found in Doc", "Status"]:
            _stbl += (
                f'<th style="color:#7EB5FF;font-size:.61rem;font-weight:700;'
                f'letter-spacing:.06em;text-transform:uppercase;'
                f'padding:7px 10px;text-align:left;">{_h}</th>'
            )
        _stbl += '</tr></thead><tbody>'
        for (_fn, _dt, _exp, _fnd, _sts) in _summ_rows:
            _sc = RED if _sts in ("mismatch", "inconsistent") else AMBER
            _stbl += (
                f'<tr style="border-bottom:1px solid rgba(255,255,255,.04);">'
                f'<td style="color:#fff;font-weight:600;font-size:.74rem;'
                f'padding:6px 10px;white-space:nowrap;">'
                f'{_fn.replace("_"," ").title()}</td>'
                f'<td style="color:#7EB5FF;font-size:.72rem;padding:6px 10px;white-space:nowrap;">'
                f'{_dt}</td>'
                f'<td style="color:{AMBER};font-family:monospace;font-size:.72rem;padding:6px 10px;">'
                f'{_exp}</td>'
                f'<td style="color:#fff;font-family:monospace;font-size:.72rem;padding:6px 10px;">'
                f'{_fnd}</td>'
                f'<td style="padding:6px 10px;">{verdict_badge(_sts)}</td>'
                f'</tr>'
            )
        _stbl += '</tbody></table></div>'
        st.markdown(_stbl, unsafe_allow_html=True)

    st.markdown(
        f'<div style="color:#7EB5FF;font-size:.70rem;font-weight:700;'
        f'letter-spacing:.09em;text-transform:uppercase;margin-bottom:10px;">'
        f'{len(all_problem_fields)} field(s) flagged — click for source evidence</div>',
        unsafe_allow_html=True,
    )

    for fname in sorted(all_problem_fields):
        is_cross = fname in cross_flagged
        per_doc_issues = flagged_fields.get(fname, [])
        icon = "&#10007;" if is_cross else "&#9888;"
        label = f"{icon} {fname.replace('_',' ').title()}"
        if is_cross:
            label += " · CROSS-DOC INCONSISTENT"

        with st.expander(label, expanded=False):
            # Cross-doc section
            if is_cross:
                cv = cross_flagged[fname]
                st.markdown(
                    '<div style="background:rgba(239,68,68,.10);border:1px solid rgba(239,68,68,.30);'
                    'border-radius:8px;padding:10px 14px;margin-bottom:10px;">'
                    '<div style="color:#EF4444;font-size:.72rem;font-weight:700;'
                    'text-transform:uppercase;margin-bottom:6px;">Cross-Document Inconsistency</div>'
                    + "".join(
                        f'<div style="display:flex;gap:10px;padding:3px 0;">'
                        f'<span style="min-width:110px;color:#7EB5FF;font-size:.74rem;'
                        f'font-weight:600;">{doc_type}</span>'
                        f'<span style="color:#fff;font-family:monospace;font-size:.74rem;">'
                        f'{val or "— not found —"}</span></div>'
                        for doc_type, val in cv.values_by_doc.items()
                    )
                    + f'<div style="color:rgba(255,255,255,.90);font-size:.72rem;margin-top:8px;">'
                    f'Reason: {cv.reason}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

            # Per-doc section
            for doc_type, fv, v in per_doc_issues:
                status_color = RED if v.status == "mismatch" else AMBER
                st.markdown(
                    f'<div style="background:rgba(8,15,40,.65);border:1px solid rgba(21,101,255,.15);'
                    f'border-radius:8px;padding:10px 14px;margin-bottom:8px;">'
                    f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">'
                    f'<span style="color:#7EB5FF;font-size:.76rem;font-weight:700;">{doc_type}</span>'
                    f'<span style="color:{status_color};font-size:.68rem;font-weight:700;'
                    f'background:{status_color}22;padding:2px 7px;border-radius:4px;">'
                    f'{v.status.upper()}</span>'
                    f'</div>'
                    f'<div style="display:flex;gap:16px;margin-bottom:8px;">'
                    f'<div><div style="color:rgba(255,255,255,.88);font-size:.66rem;">Found</div>'
                    f'<div style="color:#fff;font-family:monospace;font-size:.76rem;">'
                    f'{fv.value or "— not found —"}</div></div>'
                    f'<div><div style="color:rgba(255,255,255,.88);font-size:.66rem;">Expected</div>'
                    f'<div style="color:{AMBER};font-family:monospace;font-size:.76rem;">'
                    f'{v.expected or "—"}</div></div>'
                    f'<div><div style="color:rgba(255,255,255,.88);font-size:.66rem;">Confidence</div>'
                    f'<div style="color:{conf_color(fv.confidence)};font-size:.76rem;font-weight:700;">'
                    f'{int(fv.confidence*100)}%</div></div>'
                    f'</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
                if fv.source_snippet:
                    st.markdown(
                        '<div style="color:rgba(255,255,255,.90);font-size:.68rem;'
                        'margin-bottom:3px;">Source snippet</div>',
                        unsafe_allow_html=True,
                    )
                    st.code(fv.source_snippet, language=None)
                else:
                    st.caption("No source snippet — confidence capped at 0.3")

            if not per_doc_issues and not is_cross:
                st.caption("No per-document issues for this field.")


def render_draft_reply(ps: PipelineState, folder: Path) -> None:
    """State 4: editable draft reply with mock Send button."""
    result_meta = watcher.load_result(folder) or {}
    already_sent = result_meta.get("reply_sent", False)

    # "Agent never auto-sends" banner
    st.markdown(
        '<div style="background:rgba(217,119,6,.12);border:2px solid rgba(217,119,6,.45);'
        'border-radius:12px;padding:12px 18px;margin-bottom:14px;display:flex;'
        'align-items:center;gap:12px;">'
        '<span style="font-size:1.4rem;">&#9888;</span>'
        '<div>'
        '<div style="color:#D97706;font-size:.80rem;font-weight:700;letter-spacing:.04em;">'
        'AGENT NEVER AUTO-SENDS — CG REVIEW REQUIRED</div>'
        '<div style="color:rgba(255,255,255,.92);font-size:.74rem;margin-top:2px;">'
        'Review the draft below, edit as needed, then click Send. '
        'Only a human CG operator can dispatch this reply.</div>'
        '</div></div>',
        unsafe_allow_html=True,
    )

    if already_sent:
        sent_at = result_meta.get("sent_at", "")[:16].replace("T", " ")
        st.success(f"Reply sent by CG operator at {sent_at}.")
        sent_email = result_meta.get("sent_email", "")
        if sent_email:
            st.markdown("**Sent email:**")
            st.code(sent_email, language=None)
        return

    # Determine draft content
    decision = ps.decision
    if decision:
        if decision.action == "auto_approve":
            draft = decision.approval_email or "[Approval email not generated]"
            action_label = "APPROVAL EMAIL"
            action_color_val = GREEN
        else:
            draft = decision.amendment_email or "[Amendment email not generated]"
            action_label = "AMENDMENT REQUEST"
            action_color_val = RED
    else:
        draft = ""
        action_label = "EMAIL"
        action_color_val = BLUE

    st.markdown(
        f'<div style="color:{action_color_val};font-size:.68rem;font-weight:700;'
        f'letter-spacing:.09em;text-transform:uppercase;margin-bottom:6px;">{action_label}</div>',
        unsafe_allow_html=True,
    )

    # Editable textarea — session state key is unique per folder
    state_key = f"draft_{folder.name}"
    if state_key not in st.session_state:
        st.session_state[state_key] = draft

    edited = st.text_area(
        "Edit before sending:",
        value=st.session_state[state_key],
        height=300,
        key=f"textarea_{folder.name}",
        label_visibility="collapsed",
    )
    st.session_state[state_key] = edited

    col_send, col_cancel = st.columns([2, 1])
    with col_send:
        if st.button("Send (mock)", type="primary", key=f"send_{folder.name}",
                     use_container_width=True):
            # Log reply_sent event, mark folder
            watcher.mark_reply_sent(folder, edited)
            db.log_event(ps.trace_id, "reply_sent", {
                "sent_by": "cg_operator",
                "folder": folder.name,
                "action": decision.action if decision else "unknown",
            })
            st.success("Reply marked as sent. Folder updated in processed/.")
            st.rerun()
    with col_cancel:
        if st.button("Reset draft", key=f"reset_{folder.name}", use_container_width=True):
            st.session_state[state_key] = draft
            st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# INBOX PAGE
# ══════════════════════════════════════════════════════════════════════════════
# PIPELINE RUNNER PAGE  (single-doc upload — same agents as Part 1)
# ══════════════════════════════════════════════════════════════════════════════
if _nav == "pipeline":

    STEPS = [
        ("1", "Upload",   "upload",   "Document received"),
        ("2", "Extract",  "extract",  "Fields extracted"),
        ("3", "Validate", "validate", "Validation complete"),
        ("4", "Decide",   "decide",   "Routing decision"),
        ("5", "Complete", "complete", "Pipeline finished"),
    ]
    STEP_KEYS = [s[2] for s in STEPS]

    def _step_idx(key):
        try:
            return STEP_KEYS.index(key)
        except ValueError:
            return 0

    def _build_stepper(active="upload"):
        ai = _step_idx(active)
        parts = ['<div style="display:flex;align-items:center;width:100%;padding:10px 0 22px 0;gap:4px;">']
        for i, (num, label, key, sub) in enumerate(STEPS):
            idx = _step_idx(key)
            is_done   = idx < ai
            is_active = idx == ai
            if is_done:
                card_bg, card_bdr = "rgba(5,150,105,0.10)", "1px dashed rgba(5,150,105,0.45)"
                circ_bg, circ_col, lbl_col = GREEN, "#fff", GREEN
                circ_txt, card_shd = "&#10003;", ""
            elif is_active:
                card_bg, card_bdr = "rgba(21,101,255,0.18)", f"2px solid {BLUE}"
                circ_bg, circ_col, lbl_col = BLUE, "#fff", "#fff"
                circ_txt = num
                card_shd = "animation:card-glow 1.8s ease-in-out infinite;"
            else:
                card_bg, card_bdr = "rgba(255,255,255,0.06)", "1px solid rgba(255,255,255,0.18)"
                circ_bg, circ_col, lbl_col = "rgba(255,255,255,0.10)", "rgba(255,255,255,0.55)", "rgba(255,255,255,0.50)"
                circ_txt, card_shd = num, ""
            parts.append(
                f'<div style="flex:1;min-width:0;">'
                f'<div style="background:{card_bg};border:{card_bdr};{card_shd}'
                f'border-radius:12px;padding:10px 10px;display:flex;align-items:center;gap:8px;">'
                f'<div style="width:30px;height:30px;border-radius:50%;background:{circ_bg};'
                f'flex-shrink:0;display:flex;align-items:center;justify-content:center;'
                f'font-size:.84rem;font-weight:700;color:{circ_col};">{circ_txt}</div>'
                f'<div style="min-width:0;overflow:hidden;">'
                f'<div style="font-size:.76rem;font-weight:700;color:{lbl_col};'
                f'overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{label}</div>'
                f'<div style="font-size:.60rem;color:rgba(255,255,255,.88);margin-top:1px;'
                f'overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{sub}</div>'
                f'</div></div></div>'
            )
            if i < len(STEPS) - 1:
                ln = GREEN if is_done else "rgba(255,255,255,.10)"
                parts.append(f'<div style="width:18px;flex-shrink:0;height:2px;background:{ln};margin-top:27px;border-radius:1px;"></div>')
        parts.append('</div>')
        return ''.join(parts)

    def _status_badge(status):
        cfg = {"match": ("#057A55","MATCH &#10003;"), "mismatch": ("#C81E1E","MISMATCH &#10007;"), "uncertain": ("#92400E","UNCERTAIN ?")}
        bg, lbl = cfg.get(status, ("#374151", status.upper()))
        return (f'<span style="background:{bg};color:#fff;padding:2px 9px;border-radius:5px;'
                f'font-size:.70rem;font-weight:700;">{lbl}</span>')

    def _action_banner(action):
        cfg = {
            "auto_approve":    ("AUTO APPROVE",    "#064E3B","#059669","rgba(5,150,105,.28)","&#10003;"),
            "flag_for_review": ("FLAG FOR REVIEW", "#78350F","#D97706","rgba(217,119,6,.28)","&#9888;"),
            "draft_amendment": ("DRAFT AMENDMENT", "#7F1D1D","#EF4444","rgba(239,68,68,.28)","&#10007;"),
        }
        label, bg, bdr, glow, icon = cfg.get(action, (action.upper(),"#1E293B","#64748B","rgba(100,116,139,.28)","&#8226;"))
        return (f'<div style="background:{bg};border:2px solid {bdr};border-radius:14px;'
                f'padding:14px 24px;text-align:center;box-shadow:0 0 30px {glow};margin:8px 0 12px;">'
                f'<div style="font-size:1.5rem;margin-bottom:3px;">{icon}</div>'
                f'<div style="color:#fff;font-size:1.2rem;font-weight:800;letter-spacing:.10em;">{label}</div>'
                f'</div>')

    active_step = st.session_state.get("pl_step", "upload")
    stepper_ph  = st.empty()
    stepper_ph.markdown(_build_stepper(active_step), unsafe_allow_html=True)

    col_L, col_R = st.columns([1.15, 1], gap="large")

    with col_L:
        st.markdown('<div style="font-size:.72rem;font-weight:700;color:#7EB5FF;'
                    'letter-spacing:.10em;text-transform:uppercase;margin-bottom:8px;">'
                    'Upload a trade document</div>', unsafe_allow_html=True)
        uploaded = st.file_uploader("PDF / JPG / PNG", type=["pdf","jpg","jpeg","png"],
                                    label_visibility="collapsed", key="pl_upload")
        ca, cb, cc = st.columns([2, .12, 1.5])
        with ca:
            run_btn = st.button("Run Pipeline", type="primary", disabled=uploaded is None,
                                use_container_width=True, key="pl_run_btn")
        with cc:
            resume_id = st.text_input("Resume ID", placeholder="paste trace_id to resume",
                                      label_visibility="collapsed", key="pl_resume_inp")
            resume_btn = st.button("Resume from checkpoint", disabled=not resume_id.strip(),
                                   use_container_width=True, key="pl_resume_btn")

    with col_R:
        right_trace    = st.empty()
        right_status   = st.empty()
        right_decision = st.empty()
        right_reasoning = st.empty()

    def _run_pipeline_live(trace_id, doc_paths):
        state = PipelineState(trace_id=trace_id, raw_doc_paths=doc_paths).model_dump()
        st.session_state["pl_step"] = "extract"
        stepper_ph.markdown(_build_stepper("extract"), unsafe_allow_html=True)
        state = node_setup(state)
        st.session_state["pl_step"] = "validate"
        stepper_ph.markdown(_build_stepper("validate"), unsafe_allow_html=True)
        state = node_extractor(state)
        st.session_state["pl_step"] = "decide"
        stepper_ph.markdown(_build_stepper("decide"), unsafe_allow_html=True)
        state = node_validator(state)
        st.session_state["pl_step"] = "complete"
        stepper_ph.markdown(_build_stepper("complete"), unsafe_allow_html=True)
        state = node_router(state); state = node_persist(state)
        return PipelineState(**state)

    if run_btn and uploaded:
        sfx = Path(uploaded.name).suffix
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=sfx)
        tmp.write(uploaded.read()); tmp.flush()
        tid = str(uuid.uuid4())
        st.session_state.update({"pl_last_tid": tid, "pl_result": None, "pl_step": "upload"})
        right_trace.markdown(
            f'<div style="background:rgba(8,15,40,.68);border:1px solid rgba(21,101,255,.22);'
            f'border-radius:12px;padding:12px 16px;margin-bottom:10px;">'
            f'<div style="color:#7EB5FF;font-size:.65rem;font-weight:700;letter-spacing:.09em;'
            f'text-transform:uppercase;margin-bottom:3px;">Trace ID</div>'
            f'<div style="color:#fff;font-family:monospace;font-size:.78rem;word-break:break-all;">{tid}</div>'
            f'</div>', unsafe_allow_html=True)
        with st.spinner("Running pipeline…"):
            try:
                result = _run_pipeline_live(tid, [tmp.name])
                st.session_state["pl_result"] = result
            except Exception as e:
                st.error(f"Pipeline error: {e}")
        st.rerun()

    if resume_btn and resume_id.strip():
        with st.spinner("Resuming from checkpoint…"):
            try:
                result = resume(resume_id.strip())
                st.session_state.update({"pl_result": result, "pl_step": "complete"})
            except Exception as e:
                st.error(f"Resume error: {e}")
        st.rerun()

    result = st.session_state.get("pl_result")
    if result and result.extracted:
        with col_L:
            st.markdown('<div style="font-size:.72rem;font-weight:700;color:#7EB5FF;'
                        'letter-spacing:.10em;text-transform:uppercase;margin:14px 0 8px;">'
                        'Extraction Results</div>', unsafe_allow_html=True)
            fields = result.extracted.field_names()
            hdr = ('<table style="width:100%;border-collapse:collapse;">'
                   '<thead><tr style="border-bottom:1px solid rgba(255,255,255,.07);">'
                   + ''.join(f'<th style="color:#7EB5FF;font-size:.65rem;font-weight:700;'
                              f'letter-spacing:.08em;text-transform:uppercase;padding:7px 10px;'
                              f'text-align:left;">{h}</th>'
                              for h in ["Field","Extracted Value","Confidence","Evidence"])
                   + '</tr></thead><tbody>')
            rows_html = ""
            for fn in fields:
                fv = result.extracted.get_field(fn)
                c = fv.confidence
                cc2 = "#059669" if c >= .85 else ("#D97706" if c >= .50 else "#EF4444")
                rows_html += (
                    f'<tr style="border-bottom:1px solid rgba(255,255,255,.04);">'
                    f'<td style="color:#fff;font-weight:600;font-size:.80rem;padding:7px 10px;white-space:nowrap;">'
                    f'{fn.replace("_"," ").title()}</td>'
                    f'<td style="color:rgba(255,255,255,.82);font-family:monospace;font-size:.78rem;padding:7px 10px;">'
                    f'{fv.value or "&#8212;"}</td>'
                    f'<td style="padding:7px 10px;"><span style="color:{cc2};font-weight:700;font-size:.78rem;">'
                    f'{int(c*100)}%</span></td>'
                    f'<td style="color:rgba(255,255,255,.92);font-size:.72rem;padding:7px 10px;">'
                    f'{"Page " + str(fv.source_page) if fv.source_page else "&#8212;"}</td></tr>'
                )
            st.markdown(
                f'<div style="background:rgba(5,10,28,.60);border:1px solid rgba(21,101,255,.13);'
                f'border-radius:12px;overflow:hidden;">{hdr}{rows_html}</tbody></table></div>',
                unsafe_allow_html=True)
            with st.expander("View full source snippets", expanded=False):
                for fn in fields:
                    fv = result.extracted.get_field(fn)
                    st.markdown(f'<span style="color:rgba(255,255,255,.90);font-weight:600;font-size:.80rem;">'
                                f'{fn.replace("_"," ").title()}</span>', unsafe_allow_html=True)
                    if fv.source_snippet:
                        st.code(fv.source_snippet, language=None)
                    else:
                        st.caption("No snippet — confidence capped at 0.3")

        with col_R:
            action_label = result.decision.action if result.decision else ""
            status_color = {"auto_approve":"#059669","flag_for_review":"#D97706","draft_amendment":"#EF4444"}.get(action_label,"#fff")
            right_trace.markdown(
                f'<div style="background:rgba(8,15,40,.68);border:1px solid rgba(21,101,255,.22);'
                f'border-radius:12px;padding:12px 16px;margin-bottom:10px;">'
                f'<div style="color:#7EB5FF;font-size:.65rem;font-weight:700;letter-spacing:.09em;'
                f'text-transform:uppercase;margin-bottom:3px;">Trace ID</div>'
                f'<div style="color:#fff;font-family:monospace;font-size:.78rem;word-break:break-all;">'
                f'{result.trace_id}</div></div>'
                f'<div style="background:rgba(5,150,105,.10);border:1px solid rgba(5,150,105,.28);'
                f'border-radius:10px;padding:8px 14px;margin-bottom:10px;">'
                f'<div style="color:#7EB5FF;font-size:.64rem;font-weight:700;letter-spacing:.09em;'
                f'text-transform:uppercase;margin-bottom:2px;">Pipeline Status</div>'
                f'<div style="color:{status_color};font-size:.84rem;font-weight:600;">'
                f'Complete &#8212; {action_label}</div>'
                f'<div style="color:rgba(255,255,255,.90);font-size:.68rem;margin-top:2px;font-family:monospace;">'
                f'cost: ${result.cost_usd:.4f}</div></div>',
                unsafe_allow_html=True)
            right_status.empty()
            if result.decision:
                right_decision.markdown(
                    '<div style="font-size:.68rem;font-weight:700;color:#7EB5FF;'
                    'letter-spacing:.10em;text-transform:uppercase;margin-bottom:5px;">Router Decision</div>'
                    + _action_banner(result.decision.action), unsafe_allow_html=True)
                right_reasoning.markdown(
                    '<div style="font-size:.68rem;font-weight:700;color:#7EB5FF;'
                    'letter-spacing:.10em;text-transform:uppercase;margin-bottom:5px;">Router Reasoning</div>'
                    '<div style="background:rgba(8,15,40,.62);border:1px solid rgba(21,101,255,.16);'
                    'border-radius:12px;padding:14px 16px;">'
                    f'<div style="color:rgba(255,255,255,.85);font-size:.80rem;line-height:1.7;white-space:pre-wrap;">'
                    f'{result.decision.reasoning}</div></div>', unsafe_allow_html=True)
            if result.validation:
                st.markdown('<div style="height:6px;"></div>', unsafe_allow_html=True)
                st.markdown('<div style="font-size:.72rem;font-weight:700;color:#7EB5FF;'
                            'letter-spacing:.10em;text-transform:uppercase;margin-bottom:8px;">'
                            'Validation Verdicts</div>', unsafe_allow_html=True)
                verdicts_html = ''.join(
                    f'<div style="display:flex;align-items:center;gap:8px;'
                    f'background:rgba(8,15,40,.52);border:1px solid rgba(21,101,255,.12);'
                    f'border-radius:9px;padding:8px 12px;margin-bottom:4px;">'
                    f'<div style="min-width:140px;color:#fff;font-weight:600;font-size:.82rem;">'
                    f'{v.field.replace("_"," ").title()}</div>'
                    f'{_status_badge(v.status)}'
                    f'<div style="min-width:100px;color:rgba(255,255,255,.80);font-family:monospace;'
                    f'font-size:.78rem;background:rgba(0,0,0,.25);padding:1px 7px;border-radius:4px;">'
                    f'{v.found or "&#8212;"}</div>'
                    f'<div style="color:rgba(255,255,255,.95);font-size:.78rem;flex:1;">{v.reason}</div>'
                    f'</div>'
                    for v in result.validation.verdicts
                )
                st.markdown(verdicts_html, unsafe_allow_html=True)
                st.metric("Overall Confidence", f"{result.validation.overall_confidence:.0%}")
            if result.decision and result.decision.amendment_email:
                st.markdown('<div style="font-size:.72rem;font-weight:700;color:#7EB5FF;'
                            'letter-spacing:.10em;text-transform:uppercase;margin:12px 0 6px;">'
                            'Amendment Email</div>', unsafe_allow_html=True)
                st.code(result.decision.amendment_email, language=None)


# ══════════════════════════════════════════════════════════════════════════════

elif _nav == "inbox":

    # ── Queue Dashboard ──────────────────────────────────────────────────────
    _all_s = watcher.list_all_shipments()
    _q_in   = sum(1 for s in _all_s if s["phase"] == "incoming")
    _q_attn = sum(1 for s in _all_s
                  if s["phase"] == "processed" and not s.get("reply_sent")
                  and s.get("status") in ("draft_amendment", "flag_for_review"))
    _q_appr = sum(1 for s in _all_s if s.get("status") == "auto_approve")
    _q_sent = sum(1 for s in _all_s if s.get("reply_sent"))
    _in_bg   = "rgba(217,119,6,.18)"  if _q_in   else "rgba(217,119,6,.08)"
    _attn_bg = "rgba(239,68,68,.18)"  if _q_attn else "rgba(239,68,68,.08)"
    st.markdown(
        '<div style="display:grid;grid-template-columns:repeat(5,1fr);gap:8px;margin-bottom:16px;">'
        f'<div style="background:rgba(21,101,255,.10);border:1px solid rgba(21,101,255,.25);'
        f'border-radius:10px;padding:10px 14px;">'
        f'<div style="color:#7EB5FF;font-size:1.40rem;font-weight:800;line-height:1;">{len(_all_s)}</div>'
        f'<div style="color:rgba(255,255,255,.85);font-size:.72rem;font-weight:600;margin-top:3px;">Queue Total</div>'
        f'<div style="color:rgba(255,255,255,.45);font-size:.62rem;">all shipments</div></div>'
        f'<div style="background:{_in_bg};border:1px solid rgba(217,119,6,.30);'
        f'border-radius:10px;padding:10px 14px;">'
        f'<div style="color:#D97706;font-size:1.40rem;font-weight:800;line-height:1;">{_q_in}</div>'
        f'<div style="color:rgba(255,255,255,.85);font-size:.72rem;font-weight:600;margin-top:3px;">New Incoming</div>'
        f'<div style="color:rgba(255,255,255,.45);font-size:.62rem;">awaiting processing</div></div>'
        f'<div style="background:{_attn_bg};border:1px solid rgba(239,68,68,.30);'
        f'border-radius:10px;padding:10px 14px;">'
        f'<div style="color:#EF4444;font-size:1.40rem;font-weight:800;line-height:1;">{_q_attn}</div>'
        f'<div style="color:rgba(255,255,255,.85);font-size:.72rem;font-weight:600;margin-top:3px;">Needs Review</div>'
        f'<div style="color:rgba(255,255,255,.45);font-size:.62rem;">CG action required</div></div>'
        f'<div style="background:rgba(5,150,105,.10);border:1px solid rgba(5,150,105,.25);'
        f'border-radius:10px;padding:10px 14px;">'
        f'<div style="color:#059669;font-size:1.40rem;font-weight:800;line-height:1;">{_q_appr}</div>'
        f'<div style="color:rgba(255,255,255,.85);font-size:.72rem;font-weight:600;margin-top:3px;">Auto-Approved</div>'
        f'<div style="color:rgba(255,255,255,.45);font-size:.62rem;">no action needed</div></div>'
        f'<div style="background:rgba(21,101,255,.08);border:1px solid rgba(21,101,255,.20);'
        f'border-radius:10px;padding:10px 14px;">'
        f'<div style="color:#7EB5FF;font-size:1.40rem;font-weight:800;line-height:1;">{_q_sent}</div>'
        f'<div style="color:rgba(255,255,255,.85);font-size:.72rem;font-weight:600;margin-top:3px;">Replies Sent</div>'
        f'<div style="color:rgba(255,255,255,.45);font-size:.62rem;">dispatch complete</div></div>'
        '</div>',
        unsafe_allow_html=True,
    )

    col_list, col_detail = st.columns([1, 2.2], gap="large")

    # ── left panel: shipment list ──────────────────────────────────────────────
    with col_list:
        st.markdown(
            '<div style="font-size:.70rem;font-weight:700;color:#7EB5FF;'
            'letter-spacing:.09em;text-transform:uppercase;margin-bottom:10px;">'
            'Shipments</div>',
            unsafe_allow_html=True,
        )

        if st.button("Refresh Inbox", type="secondary", use_container_width=True):
            st.rerun()

        st.markdown('<div style="height:6px;"></div>', unsafe_allow_html=True)
        _cust_q = st.text_input(
            "customer filter",
            placeholder="Customer name (e.g. Acme Logistics)…",
            key="cg_inbox_cust_filter",
            label_visibility="collapsed",
        )
        if st.button("Find Pending for Customer", key="cg_find_pending",
                     use_container_width=True):
            _qstr = (
                f"Show me everything pending review for {_cust_q.strip()}"
                if _cust_q.strip()
                else "Show me all shipments currently pending CG review"
            )
            st.session_state["cg_prefill_query"] = _qstr
            st.session_state["cg_nav"] = "query"
            st.rerun()
        st.markdown('<div style="height:6px;"></div>', unsafe_allow_html=True)

        shipments = _all_s

        if not shipments:
            st.markdown(
                '<div style="color:rgba(255,255,255,.88);font-size:.80rem;'
                'padding:20px;text-align:center;background:rgba(8,15,40,.50);'
                'border-radius:12px;border:1px solid rgba(21,101,255,.12);">'
                'No shipments found.<br>Add a folder to inbox/incoming/</div>',
                unsafe_allow_html=True,
            )
        else:
            if "cg_selected" not in st.session_state:
                st.session_state["cg_selected"] = None

            def _sort_p(s):
                _ph = s["phase"]
                _st = s.get("status") or ""
                _rs = s.get("reply_sent", False)
                if _ph == "incoming": return (0, s["name"])
                if _st == "draft_amendment" and not _rs: return (1, s["name"])
                if _st == "flag_for_review" and not _rs: return (2, s["name"])
                if _st == "auto_approve" and not _rs: return (3, s["name"])
                return (4, s["name"])

            for s in sorted(shipments, key=_sort_p):
                folder = s["folder"]
                is_selected = st.session_state["cg_selected"] == str(folder)
                border = f"2px solid {BLUE}" if is_selected else "1px solid rgba(21,101,255,.15)"
                bg = "rgba(21,101,255,.14)" if is_selected else "rgba(8,15,40,.55)"
                _s_status = s.get("status") or ""
                _needs_action = (s["phase"] == "processed" and not s.get("reply_sent")
                                 and _s_status in ("draft_amendment", "flag_for_review"))
                if s["phase"] == "incoming":
                    _status_line = (
                        f'<div style="color:#D97706;font-size:.62rem;font-weight:600;margin-top:3px;">'
                        f'NEW — awaiting processing</div>'
                    )
                elif _needs_action:
                    _sc = RED if _s_status == "draft_amendment" else AMBER
                    _sl = "DRAFT AMENDMENT" if _s_status == "draft_amendment" else "FLAG FOR REVIEW"
                    _status_line = (
                        f'<div style="color:{_sc};font-size:.62rem;font-weight:700;margin-top:3px;">'
                        f'&#9888; {_sl} — ACTION REQUIRED</div>'
                    )
                elif _s_status == "auto_approve" and not s.get("reply_sent"):
                    _status_line = (
                        f'<div style="color:#059669;font-size:.62rem;font-weight:600;margin-top:3px;">'
                        f'&#10003; Approved — send reply</div>'
                    )
                elif s.get("reply_sent"):
                    _status_line = (
                        f'<div style="color:rgba(255,255,255,.40);font-size:.62rem;margin-top:3px;">'
                        f'Reply sent &#10003;</div>'
                    )
                else:
                    _status_line = ""

                st.markdown(
                    f'<div style="background:{bg};border:{border};border-radius:10px;'
                    f'padding:10px 14px;margin-bottom:8px;min-width:0;">'
                    f'<div style="display:flex;justify-content:space-between;'
                    f'align-items:center;gap:6px;min-width:0;">'
                    f'<div style="color:#fff;font-size:.80rem;font-weight:600;'
                    f'min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1;">'
                    f'{s["name"]}</div>'
                    f'<div style="flex-shrink:0;">{phase_badge(s["phase"], s["reply_sent"])}</div>'
                    f'</div>'
                    f'<div style="color:rgba(255,255,255,.90);font-size:.70rem;margin-top:4px;'
                    f'overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">'
                    f'{s["customer"]} · {s["n_attachments"]} file(s)</div>'
                    f'{_status_line}'
                    f'</div>',
                    unsafe_allow_html=True,
                )
                if st.button("Select", key=f"sel_{folder.name}_{s['phase']}",
                             use_container_width=True):
                    st.session_state["cg_selected"] = str(folder)
                    st.rerun()

    # ── right panel: state view ────────────────────────────────────────────────
    with col_detail:
        selected_path = st.session_state.get("cg_selected")

        if not selected_path:
            st.markdown(
                '<div style="display:flex;flex-direction:column;align-items:center;'
                'justify-content:center;padding:60px 20px;text-align:center;">'
                '<div style="font-size:3rem;margin-bottom:14px;">&#128235;</div>'
                '<div style="color:rgba(255,255,255,.90);font-size:.96rem;font-weight:600;">'
                'Select a shipment to review</div>'
                '<div style="color:rgba(255,255,255,.82);font-size:.80rem;margin-top:6px;">'
                'New SU emails appear automatically in the inbox list</div>'
                '</div>',
                unsafe_allow_html=True,
            )
        else:
            folder = Path(selected_path)
            phase = folder.parent.name  # incoming / processing / processed
            email = watcher.read_email(folder)
            att_paths = watcher.attachments(folder)
            att_names = [Path(p).name for p in att_paths]

            # ── state header ────────────────────────────────────────────────
            st.markdown(
                f'<div style="font-size:.70rem;font-weight:700;color:#7EB5FF;'
                f'letter-spacing:.09em;text-transform:uppercase;margin-bottom:2px;">'
                f'{folder.name}</div>'
                f'<div style="font-size:.80rem;color:rgba(255,255,255,.92);margin-bottom:12px;">'
                f'{email.get("subject","")}</div>',
                unsafe_allow_html=True,
            )

            # ── STATE 1: INCOMING ────────────────────────────────────────────
            if phase == "incoming":
                render_email_card(email, len(att_names), att_names)

                st.markdown('<div style="height:12px;"></div>', unsafe_allow_html=True)
                st.markdown(
                    '<div style="background:rgba(21,101,255,.10);border:1px solid rgba(21,101,255,.25);'
                    'border-radius:10px;padding:12px 16px;margin-bottom:12px;">'
                    '<div style="color:#7EB5FF;font-size:.72rem;font-weight:700;margin-bottom:4px;">'
                    'Agent status</div>'
                    '<div style="color:rgba(255,255,255,.82);font-size:.82rem;">'
                    '&#9203; Awaiting processing — click below to trigger validation</div>'
                    '</div>',
                    unsafe_allow_html=True,
                )

                if st.button("Process Shipment", type="primary", key="process_btn",
                             use_container_width=True):
                    with st.spinner("Moving to processing queue..."):
                        proc_folder = watcher.mark_processing(folder)
                        st.session_state["cg_selected"] = str(proc_folder)

                    with st.spinner("Running pipeline: extracting → validating → cross-checking → routing…"):
                        try:
                            ps = run_cg(str(proc_folder))
                            # Write state files into folder
                            watcher.save_result(
                                proc_folder,
                                ps.trace_id,
                                ps.decision.action if ps.decision else "pending_cg_review",
                                ps.model_dump_json(),
                            )
                            # Cache in session state
                            if "cg_states" not in st.session_state:
                                st.session_state["cg_states"] = {}
                            st.session_state["cg_states"][str(proc_folder)] = ps.model_dump()

                            done_folder = watcher.mark_processed(proc_folder)
                            st.session_state["cg_selected"] = str(done_folder)
                        except Exception as exc:
                            st.error(f"Pipeline error: {exc}")
                    st.rerun()

            # ── STATE 1b: PROCESSING (still running / stuck) ─────────────────
            elif phase == "processing":
                render_email_card(email, len(att_names), att_names)
                st.markdown('<div style="height:8px;"></div>', unsafe_allow_html=True)
                with st.spinner("Agent processing — extracting, validating, routing…"):
                    pass
                st.info("Pipeline is running. Refresh in a moment.")

            # ── STATES 2 / 3 / 4: PROCESSED ──────────────────────────────────
            elif phase == "processed":
                ps = load_pipeline_state(folder)

                if ps is None:
                    st.warning("Could not load pipeline result. State file missing.")
                else:
                    # Decision banner
                    action = ps.decision.action if ps.decision else "pending"
                    action_cfg = {
                        "auto_approve":    (GREEN,  "AUTO APPROVE &#10003;"),
                        "flag_for_review": (AMBER,  "FLAG FOR REVIEW &#9888;"),
                        "draft_amendment": (RED,    "DRAFT AMENDMENT &#10007;"),
                    }
                    a_color, a_label = action_cfg.get(action, (BLUE, action.upper()))
                    st.markdown(
                        f'<div style="background:{a_color}22;border:2px solid {a_color}66;'
                        f'border-radius:12px;padding:10px 18px;margin-bottom:12px;'
                        f'display:flex;align-items:center;justify-content:space-between;">'
                        f'<div style="color:{a_color};font-size:1rem;font-weight:800;">'
                        f'{a_label}</div>'
                        f'<div style="color:rgba(255,255,255,.90);font-size:.68rem;'
                        f'font-family:monospace;">cost: ${ps.cost_usd:.4f} · '
                        f'trace: {ps.trace_id[:16]}…</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

                    tab_verify, tab_discrep, tab_draft = st.tabs([
                        "Verification Result", "Discrepancy Detail", "Draft Reply",
                    ])

                    # ── TAB 1: VERIFICATION (State 2) ─────────────────────────
                    with tab_verify:
                        render_cross_doc_strip(ps)
                        st.markdown("<hr>", unsafe_allow_html=True)
                        render_per_doc_tables(ps)

                        # ── Pipeline audit trail ────────────────────────────
                        st.markdown("<hr>", unsafe_allow_html=True)
                        st.markdown(
                            '<div style="font-size:.70rem;font-weight:700;color:#7EB5FF;'
                            'letter-spacing:.09em;text-transform:uppercase;margin-bottom:10px;">'
                            '&#128203; Pipeline Audit Trail</div>',
                            unsafe_allow_html=True,
                        )
                        try:
                            _aconn = db.get_conn()
                            _arows = _aconn.execute(
                                "SELECT event_type, payload_json, created_at FROM audit_log "
                                "WHERE trace_id=? ORDER BY created_at ASC",
                                (ps.trace_id,)
                            ).fetchall()
                            _aconn.close()
                        except Exception:
                            _arows = []

                        if _arows:
                            _step_icons = {
                                "email_received":      "&#128235;",
                                "extracted_all":       "&#128269;",
                                "validated_all":       "&#9989;",
                                "cross_validated":     "&#128279;",
                                "routed":              "&#128679;",
                                "pipeline_complete":   "&#9989;",
                                "cg_pipeline_complete":"&#9989;",
                                "scope":               "&#128203;",
                                "extractor":           "&#128269;",
                                "validator":           "&#9989;",
                                "router":              "&#128679;",
                                "persist":             "&#128190;",
                                "reply_sent":          "&#128232;",
                            }
                            trail_html = '<div style="display:flex;flex-direction:column;gap:4px;">'
                            for row in _arows:
                                icon = _step_icons.get(row["event_type"], "&#9679;")
                                ts_short = (row["created_at"] or "")[:19].replace("T", " ")
                                try:
                                    _p = json.loads(row["payload_json"] or "{}")
                                    detail = ", ".join(f"{k}:{v}" for k, v in list(_p.items())[:3])
                                except Exception:
                                    detail = ""
                                trail_html += (
                                    f'<div style="display:flex;align-items:flex-start;gap:10px;'
                                    f'background:rgba(8,15,40,.50);border:1px solid rgba(21,101,255,.10);'
                                    f'border-radius:7px;padding:7px 12px;">'
                                    f'<span style="font-size:.85rem;flex-shrink:0;">{icon}</span>'
                                    f'<div style="flex:1;min-width:0;">'
                                    f'<div style="display:flex;justify-content:space-between;">'
                                    f'<span style="color:#fff;font-size:.76rem;font-weight:600;">'
                                    f'{row["event_type"].replace("_"," ").title()}</span>'
                                    f'<span style="color:rgba(255,255,255,.45);font-size:.65rem;'
                                    f'font-family:monospace;">{ts_short}</span></div>'
                                    f'<div style="color:rgba(255,255,255,.82);font-size:.66rem;'
                                    f'margin-top:1px;overflow:hidden;text-overflow:ellipsis;'
                                    f'white-space:nowrap;">{detail}</div>'
                                    f'</div></div>'
                                )
                            trail_html += '</div>'
                            st.markdown(trail_html, unsafe_allow_html=True)
                        else:
                            st.caption("No audit events found for this trace.")

                    # ── TAB 2: DISCREPANCY (State 3) ──────────────────────────
                    with tab_discrep:
                        render_discrepancy_detail(ps)

                    # ── TAB 3: DRAFT REPLY (State 4) ──────────────────────────
                    with tab_draft:
                        render_draft_reply(ps, folder)


# ══════════════════════════════════════════════════════════════════════════════
# HISTORY PAGE
# ══════════════════════════════════════════════════════════════════════════════
elif _nav == "history":
    import sqlite3 as _sl

    def _load_history():
        try:
            conn = db.get_conn()
            rows = conn.execute(
                "SELECT s.trace_id, s.doc_paths, s.status, s.customer, s.created_at, "
                "d.action, d.reasoning, d.amendment_email "
                "FROM shipments s LEFT JOIN decisions d ON s.trace_id=d.trace_id "
                "ORDER BY s.created_at DESC"
            ).fetchall()
            conn.close()
            return [dict(r) for r in rows]
        except Exception as e:
            st.error(f"DB error: {e}")
            return []

    hist = _load_history()
    if not hist:
        st.info("No shipments processed yet. Run the pipeline on a shipment in the Inbox tab first.")
    else:
        # ── Analytics KPIs ──────────────────────────────────────────────────────
        _total   = len(hist)
        _approve = sum(1 for r in hist if r.get("action") == "auto_approve")
        _amend   = sum(1 for r in hist if r.get("action") == "draft_amendment")
        _flag    = sum(1 for r in hist if r.get("action") == "flag_for_review")
        _appr_pct = int(100 * _approve / _total) if _total else 0
        _amend_pct = int(100 * _amend / _total) if _total else 0

        kpi_html = (
            '<div style="display:grid;grid-template-columns:repeat(4,1fr);'
            'gap:10px;margin-bottom:20px;">'
        )
        for label, val, sub, col, bg in [
            ("Total Processed", str(_total), "all shipments", "#7EB5FF", "rgba(21,101,255,.10)"),
            ("Auto-Approved",   f"{_approve} ({_appr_pct}%)", "no issues found", "#059669", "rgba(5,150,105,.10)"),
            ("Amendments",      f"{_amend} ({_amend_pct}%)", "corrections requested", "#EF4444", "rgba(239,68,68,.10)"),
            ("Flagged Review",  str(_flag), "human review needed", "#D97706", "rgba(217,119,6,.10)"),
        ]:
            kpi_html += (
                f'<div style="background:{bg};border:1px solid {col}33;border-radius:12px;'
                f'padding:14px 16px;">'
                f'<div style="color:{col};font-size:1.45rem;font-weight:800;'
                f'letter-spacing:-.02em;line-height:1;">{val}</div>'
                f'<div style="color:rgba(255,255,255,.85);font-size:.74rem;'
                f'font-weight:600;margin-top:4px;">{label}</div>'
                f'<div style="color:rgba(255,255,255,.45);font-size:.64rem;margin-top:2px;">{sub}</div>'
                f'</div>'
            )
        kpi_html += '</div>'
        st.markdown(kpi_html, unsafe_allow_html=True)

        st.markdown(
            f'<div style="color:#7EB5FF;font-size:.72rem;font-weight:700;'
            f'letter-spacing:.09em;text-transform:uppercase;margin-bottom:14px;">'
            f'Shipment Log</div>',
            unsafe_allow_html=True,
        )
        for r in hist:
            action = r["action"] or r["status"] or "pending"
            a_color = action_color(action)
            ts = (r["created_at"] or "")[:16].replace("T", " ")
            paths = json.loads(r["doc_paths"]) if r["doc_paths"] else []

            with st.expander(
                f'  {r["customer"] or "Unknown"}  ·  {action.upper()}  ·  {ts}',
                expanded=False,
            ):
                c1, c2 = st.columns(2, gap="medium")
                with c1:
                    st.markdown(
                        f'<div style="color:{a_color};font-size:.82rem;font-weight:700;">'
                        f'{action.upper()}</div>'
                        f'<div style="color:rgba(255,255,255,.88);font-size:.68rem;'
                        f'font-family:monospace;margin-top:4px;">{r["trace_id"]}</div>'
                        f'<div style="color:rgba(255,255,255,.88);font-size:.66rem;">'
                        f'Customer: {r.get("customer","—")} · {ts}</div>',
                        unsafe_allow_html=True,
                    )
                    if r.get("reasoning"):
                        st.markdown(
                            f'<div style="background:rgba(8,15,40,.60);border:1px solid rgba(21,101,255,.14);'
                            f'border-radius:8px;padding:10px 13px;margin-top:8px;'
                            f'color:rgba(255,255,255,.82);font-size:.76rem;line-height:1.6;">'
                            f'{r["reasoning"]}</div>',
                            unsafe_allow_html=True,
                        )
                with c2:
                    docs_html = "".join(
                        f'<div style="color:rgba(255,255,255,.92);font-size:.74rem;'
                        f'padding:3px 0;font-family:monospace;">&#128196; {Path(p).name}</div>'
                        for p in paths
                    )
                    if docs_html:
                        st.markdown(
                            f'<div style="color:#7EB5FF;font-size:.65rem;font-weight:700;'
                            f'text-transform:uppercase;margin-bottom:4px;">Documents</div>'
                            + docs_html,
                            unsafe_allow_html=True,
                        )
                    if r.get("amendment_email"):
                        st.markdown(
                            '<div style="color:#7EB5FF;font-size:.65rem;font-weight:700;'
                            'text-transform:uppercase;margin:8px 0 4px;">Draft Email</div>',
                            unsafe_allow_html=True,
                        )
                        st.code(r["amendment_email"][:400] + ("…" if len(r["amendment_email"]) > 400 else ""),
                                language=None)


# ══════════════════════════════════════════════════════════════════════════════
# NL QUERY PAGE
# ══════════════════════════════════════════════════════════════════════════════
elif _nav == "query":
    if "cg_query_hist" not in st.session_state:
        st.session_state["cg_query_hist"] = []

    # Pre-fill from "Find Pending for Customer" shortcut in Inbox
    _prefill = st.session_state.pop("cg_prefill_query", "")
    if _prefill:
        st.markdown(
            f'<div style="background:rgba(21,101,255,.12);border:1px solid rgba(21,101,255,.30);'
            f'border-radius:9px;padding:8px 14px;margin-bottom:10px;'
            f'color:#7EB5FF;font-size:.76rem;">'
            f'&#128279; Query pre-filled from Inbox shortcut</div>',
            unsafe_allow_html=True,
        )

    examples = [
        "Show me everything pending review for Acme Logistics",
        "How many shipments had cross-document mismatches this week?",
        "Which supplier sent the most amendment-triggering docs?",
        "What is the average confidence across all shipments?",
        "List all shipments with hs_code inconsistency",
    ]
    sel = st.selectbox("Example questions:", ["— pick one —"] + examples, key="cg_q_sel")
    question = st.text_input(
        "Your question:",
        value=_prefill or (sel if sel != "— pick one —" else ""),
        key="cg_q_input",
        placeholder="e.g. Show everything pending review for Acme Logistics",
    )
    ask_btn = st.button("Ask", type="primary", disabled=not question.strip(), key="cg_ask")

    if ask_btn and question.strip():
        with st.spinner("Generating SQL and querying…"):
            result = ask(question.strip())
            st.session_state["cg_query_hist"].insert(0, result)
            if len(st.session_state["cg_query_hist"]) > 8:
                st.session_state["cg_query_hist"] = st.session_state["cg_query_hist"][:8]

    for i, qr in enumerate(st.session_state.get("cg_query_hist", [])):
        with st.expander(f"Q: {qr['question']}", expanded=(i == 0)):
            st.markdown(
                '<div style="background:rgba(5,150,105,.10);border-left:3px solid #059669;'
                'border-radius:0 9px 9px 0;padding:9px 13px;margin-bottom:8px;">'
                '<div style="color:#7EB5FF;font-size:.66rem;font-weight:700;'
                'text-transform:uppercase;margin-bottom:3px;">Answer</div>'
                f'<div style="color:rgba(255,255,255,.90);line-height:1.6;">{qr["answer"]}</div>'
                '</div>',
                unsafe_allow_html=True,
            )
            if qr.get("sql"):
                st.code(qr["sql"], language="sql")
            if qr.get("rows"):
                st.caption(f'{len(qr["rows"])} row(s)')
                st.json(qr["rows"][:10])
            st.caption(f'cost: ${qr.get("cost_usd", 0):.6f}')


# ══════════════════════════════════════════════════════════════════════════════
# RULES PAGE
# ══════════════════════════════════════════════════════════════════════════════
elif _nav == "rules":
    import yaml as _yaml

    rules_path = Path(__file__).parent / "config" / "rules.yaml"
    try:
        with open(rules_path) as _f:
            rules_data = _yaml.safe_load(_f)
    except Exception as e:
        st.error(f"Could not load rules.yaml: {e}")
        rules_data = {}

    customer = rules_data.get("customer", "Unknown")
    st.markdown(
        f'<div style="background:rgba(21,101,255,.10);border:1px solid rgba(21,101,255,.28);'
        f'border-radius:12px;padding:12px 18px;margin-bottom:18px;display:flex;align-items:center;gap:12px;">'
        f'<div style="font-size:1.5rem;">&#127962;</div>'
        f'<div><div style="color:#7EB5FF;font-size:.65rem;font-weight:700;letter-spacing:.10em;'
        f'text-transform:uppercase;">Active Customer Profile</div>'
        f'<div style="color:#fff;font-size:1.05rem;font-weight:700;margin-top:2px;">{customer}</div>'
        f'</div></div>', unsafe_allow_html=True)

    MATCH_ICONS = {
        "exact_ci": "&#128292;", "prefix": "&#128290;", "enum": "&#128203;",
        "numeric_tolerance": "&#9878;", "regex": "&#128269;", "semantic": "&#129504;",
    }

    rules = rules_data.get("rules", {})
    cols = st.columns(2, gap="medium")
    for idx, (field, cfg) in enumerate(rules.items()):
        mtype = cfg.get("match_type", "")
        icon = MATCH_ICONS.get(mtype, "·")
        with cols[idx % 2]:
            detail_lines = []
            for k, v in cfg.items():
                if k == "match_type":
                    continue
                detail_lines.append(
                    f'<div style="display:flex;justify-content:space-between;padding:4px 0;'
                    f'border-bottom:1px solid rgba(255,255,255,.05);">'
                    f'<span style="color:rgba(255,255,255,.90);font-size:.74rem;">{k.replace("_"," ").title()}</span>'
                    f'<span style="color:#fff;font-size:.74rem;font-family:monospace;">{v}</span>'
                    f'</div>'
                )
            st.markdown(
                f'<div style="background:rgba(8,15,40,.65);border:1px solid rgba(21,101,255,.18);'
                f'border-left:3px solid {BLUE};border-radius:10px;padding:14px 16px;margin-bottom:12px;">'
                f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:10px;">'
                f'<span style="font-size:1.1rem;">{icon}</span>'
                f'<div>'
                f'<div style="color:#fff;font-weight:700;font-size:.88rem;">'
                f'{field.replace("_"," ").title()}</div>'
                f'<div style="color:#7EB5FF;font-size:.68rem;font-weight:600;margin-top:1px;">{mtype}</div>'
                f'</div></div>'
                + "".join(detail_lines)
                + f'</div>', unsafe_allow_html=True)

    st.markdown("---")
    st.markdown(
        '<div style="color:rgba(255,255,255,.88);font-size:.80rem;">'
        '&#9881; Rules are loaded fresh from <code>config/rules.yaml</code> on every pipeline run — '
        'edit the file and re-run without restarting the app.</div>',
        unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# SETTINGS PAGE
# ══════════════════════════════════════════════════════════════════════════════
elif _nav == "settings":
    import os as _os
    from nova.infrastructure.database import DB_PATH as _DBPATH

    def _setting_row(label, value, status_color="#059669"):
        return (
            f'<div style="display:flex;align-items:center;justify-content:space-between;'
            f'padding:12px 16px;border-bottom:1px solid rgba(255,255,255,.05);">'
            f'<div style="color:rgba(255,255,255,.92);font-size:.85rem;">{label}</div>'
            f'<div style="color:{status_color};font-family:monospace;font-size:.82rem;'
            f'background:rgba(0,0,0,.30);padding:3px 10px;border-radius:6px;">{value}</div>'
            f'</div>'
        )

    api_key = _os.environ.get("OPENAI_API_KEY", "")
    api_status = ("sk-…" + api_key[-6:]) if len(api_key) > 10 else "NOT SET"
    api_color  = GREEN if len(api_key) > 10 else RED
    db_exists  = Path(str(_DBPATH)).exists()
    db_color   = GREEN if db_exists else AMBER

    st.markdown(
        '<div style="background:rgba(8,15,40,.68);border:1px solid rgba(21,101,255,.20);'
        'border-radius:14px;overflow:hidden;margin-bottom:18px;">'
        '<div style="padding:12px 16px;border-bottom:1px solid rgba(21,101,255,.15);">'
        '<div style="color:#7EB5FF;font-size:.68rem;font-weight:700;letter-spacing:.10em;'
        'text-transform:uppercase;">Environment</div></div>'
        + _setting_row("OpenAI API Key",     api_status,                             api_color)
        + _setting_row("Extraction Model",   "gpt-4o (vision)",                      "#7EB5FF")
        + _setting_row("Validation Model",   "gpt-4o-mini",                          "#7EB5FF")
        + _setting_row("Orchestration",      "LangGraph",                            "#7EB5FF")
        + _setting_row("Database",           str(_DBPATH),                           db_color)
        + _setting_row("DB Status",          "Ready" if db_exists else "Will be created on first run", db_color)
        + _setting_row("Rules Config",       "config/rules.yaml",                    "#7EB5FF")
        + _setting_row("Inbox",              "inbox/incoming/ (folder-based mock)",  "#7EB5FF")
        + _setting_row("Crash Recovery",     "Checkpoint per node → resume(trace_id)", GREEN)
        + _setting_row("Agent Auto-Send",    "DISABLED — CG operator must click Send", GREEN)
        + '</div>',
        unsafe_allow_html=True)

    st.markdown(
        '<div style="background:rgba(8,15,40,.68);border:1px solid rgba(21,101,255,.20);'
        'border-radius:14px;overflow:hidden;margin-bottom:18px;">'
        '<div style="padding:12px 16px;border-bottom:1px solid rgba(21,101,255,.15);">'
        '<div style="color:#7EB5FF;font-size:.68rem;font-weight:700;letter-spacing:.10em;'
        'text-transform:uppercase;">Pipeline Limits</div></div>'
        + _setting_row("Max Retries",           "2 per run",                         "#7EB5FF")
        + _setting_row("Supported Formats",     "PDF, JPG, JPEG, PNG",               "#7EB5FF")
        + _setting_row("NL Query",              "Read-only SELECT only",             "#7EB5FF")
        + _setting_row("Confidence Threshold",  "≥ 0.85 to auto-approve",            "#7EB5FF")
        + _setting_row("Evidence Rule",         "No snippet → confidence ≤ 0.30",    "#7EB5FF")
        + _setting_row("Cross-Doc Check",       "consignee_name · hs_code · invoice_number", "#7EB5FF")
        + '</div>',
        unsafe_allow_html=True)

    st.markdown(
        '<div style="color:rgba(255,255,255,.88);font-size:.78rem;margin-top:6px;">'
        'To update the OpenAI key, edit <code>.env</code> in the project root and restart the app.</div>',
        unsafe_allow_html=True)
