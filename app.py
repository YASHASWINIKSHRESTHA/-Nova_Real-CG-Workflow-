"""
Nova POC - Streamlit UI v3
GoComet Nova design - dark glassmorphism, animated pipeline stepper, 3D bg parallax.
"""
import base64, sys, tempfile, uuid
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))

from nova.infrastructure import database as db
from nova.pipeline.pipeline import (
    node_setup, node_extractor, node_persist,
    node_router, node_validator,
)
from nova.domain.models import PipelineState
from nova.pipeline import resume
from nova.query import ask

st.set_page_config(
    page_title="Nova - Trade Doc Validator",
    page_icon="N",
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

# ── step definitions ───────────────────────────────────────────────────────────
STEPS = [
    ("1", "Upload",   "upload",   "Document received"),
    ("2", "Extract",  "extract",  "Fields extracted"),
    ("3", "Validate", "validate", "Validation complete"),
    ("4", "Decide",   "decide",   "Routing decision"),
    ("5", "Complete", "complete", "Pipeline finished"),
]
STEP_KEYS = [s[2] for s in STEPS]


def step_idx(key):
    try:
        return STEP_KEYS.index(key)
    except ValueError:
        return 0


# ── stepper HTML ───────────────────────────────────────────────────────────────
def build_stepper(active="upload"):
    ai = step_idx(active)
    parts = ['<div style="display:flex;align-items:center;width:100%;'
             'padding:10px 0 22px 0;gap:4px;">']

    for i, (num, label, key, sub) in enumerate(STEPS):
        idx = step_idx(key)
        is_done   = idx < ai
        is_active = idx == ai

        if is_done:
            card_bg  = "rgba(5,150,105,0.10)"
            card_bdr = "1px dashed rgba(5,150,105,0.45)"
            card_shd = ""
            circ_bg  = GREEN
            circ_col = "#fff"
            lbl_col  = GREEN
            sub_col  = "rgba(5,150,105,0.70)"
            circ_txt = "&#10003;"
            circ_anim= ""
        elif is_active:
            card_bg  = "rgba(21,101,255,0.18)"
            card_bdr = "2px solid " + BLUE
            card_shd = "animation:card-glow 1.8s ease-in-out infinite;"
            circ_bg  = BLUE
            circ_col = "#fff"
            lbl_col  = "#fff"
            sub_col  = "rgba(200,225,255,0.88)"
            circ_txt = num
            circ_anim= "animation:pulse-glow 1.8s ease-in-out infinite;"
        else:
            card_bg  = "rgba(255,255,255,0.06)"
            card_bdr = "1px solid rgba(255,255,255,0.18)"
            card_shd = ""
            circ_bg  = "rgba(255,255,255,0.10)"
            circ_col = "rgba(255,255,255,0.55)"
            lbl_col  = "rgba(255,255,255,0.50)"
            sub_col  = "rgba(255,255,255,0.30)"
            circ_txt = num
            circ_anim= ""

        parts.append(
            '<div style="flex:1;min-width:0;">'
            f'<div style="background:{card_bg};border:{card_bdr};{card_shd}'
            'border-radius:12px;padding:10px 12px;'
            'display:flex;align-items:center;gap:10px;'
            'transition:all 0.4s ease;">'
            f'<div style="width:34px;height:34px;border-radius:50%;background:{circ_bg};'
            'flex-shrink:0;display:flex;align-items:center;justify-content:center;'
            f'font-size:0.90rem;font-weight:700;color:{circ_col};{circ_anim}">'
            f'{circ_txt}</div>'
            '<div style="min-width:0;overflow:hidden;">'
            f'<div style="font-size:0.78rem;font-weight:700;color:{lbl_col};'
            'white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">'
            f'{label}</div>'
            f'<div style="font-size:0.63rem;color:{sub_col};margin-top:1px;'
            'white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">'
            f'{sub}</div>'
            '</div></div></div>'
        )

        if i < len(STEPS) - 1:
            ln = GREEN if is_done else "rgba(255,255,255,0.10)"
            parts.append(
                f'<div style="width:18px;flex-shrink:0;height:2px;background:{ln};'
                'margin-top:27px;border-radius:1px;transition:background 0.5s ease;"></div>'
            )

    parts.append('</div>')
    return ''.join(parts)


# ── background loader ──────────────────────────────────────────────────────────
def bg_b64():
    p = Path(__file__).parent / "assets" / "bg_Img.jpg"
    return base64.b64encode(p.read_bytes()).decode() if p.exists() else ""


# ── global CSS ─────────────────────────────────────────────────────────────────
def inject_css():
    b64 = bg_b64()
    bg  = (f"url('data:image/jpeg;base64,{b64}') top right / cover no-repeat"
           if b64 else
           "linear-gradient(135deg,#05080F 0%,#080E20 50%,#05080F 100%)")

    st.markdown(
        '<link rel="preconnect" href="https://fonts.googleapis.com">'
        '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
        '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">',
        unsafe_allow_html=True,
    )

    st.markdown(f"""<style>
html,body,input,button,textarea,select,
.stApp,[class*="st"],.stMarkdown,p,span,div,label,th,td,a{{
  font-family:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif!important;}}
*{{box-sizing:border-box;}}

html{{background:#05080F!important;min-height:100vh!important;}}
body{{background:transparent!important;min-height:100vh!important;}}

html::before{{content:'';position:fixed;inset:-8%;
  background:{bg};transform-origin:center;
  animation:nova-breathe 22s ease-in-out infinite alternate;
  z-index:-2;will-change:transform;pointer-events:none;perspective:800px;}}

@keyframes nova-breathe{{
  0%  {{transform:scale(1.00) translateZ(0px)   rotateX(0deg)    rotateY(0deg);}}
  25% {{transform:scale(1.03) translateZ(8px)   rotateX(0.4deg)  rotateY(-0.3deg);}}
  50% {{transform:scale(1.05) translateZ(14px)  rotateX(0.6deg)  rotateY(0.2deg);}}
  75% {{transform:scale(1.02) translateZ(6px)   rotateX(-0.2deg) rotateY(0.4deg);}}
  100%{{transform:scale(1.00) translateZ(0px)   rotateX(0deg)    rotateY(0deg);}}}}

html::after{{content:'';position:fixed;inset:0;
  background:radial-gradient(ellipse at 70% 25%,rgba(5,8,20,.20) 0%,rgba(5,8,20,.55) 55%,rgba(5,8,20,.78) 100%);
  z-index:-1;pointer-events:none;}}

.stApp,[data-testid="stAppViewContainer"],[data-testid="stHeader"],
[data-testid="stBottom"],section[data-testid="stSidebar"],
[data-testid="stMain"],[data-testid="stAppViewBlockContainer"],
[data-testid="stSidebarContent"]{{background:transparent!important;}}
[data-testid="stDecoration"]{{display:none!important;}}

section[data-testid="stSidebar"]>div:first-child{{
  background:rgba(5,10,28,0.85)!important;
  backdrop-filter:blur(20px)!important;-webkit-backdrop-filter:blur(20px)!important;
  border-right:1px solid {BLUE_DIM}!important;padding:0!important;}}

.main .block-container{{
  background:rgba(5,10,28,0.68)!important;
  backdrop-filter:blur(16px)!important;-webkit-backdrop-filter:blur(16px)!important;
  border-radius:20px!important;border:1px solid {BLUE_DIM}!important;
  box-shadow:0 0 80px rgba(21,101,255,.08),inset 0 1px 0 rgba(255,255,255,.05)!important;
  padding:1.4rem 2rem 2rem!important;max-width:1400px!important;}}

h1,h2,h3,h4,h5{{color:#fff!important;letter-spacing:-.01em;}}
h1{{background:linear-gradient(90deg,#fff 55%,{BLUE});
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;
  background-clip:text;font-size:2rem!important;font-weight:800!important;}}
.stMarkdown p,.stMarkdown li,[data-testid="stText"]{{
  color:rgba(255,255,255,.90)!important;font-size:.93rem;line-height:1.65;}}
.stCaption,[data-testid="stCaptionContainer"] p{{
  color:rgba(255,255,255,.55)!important;font-size:.80rem!important;}}

[data-baseweb="tab-list"]{{background:rgba(255,255,255,.04)!important;
  border-radius:12px!important;padding:4px!important;
  border:1px solid rgba(255,255,255,.07)!important;gap:4px!important;}}
[data-baseweb="tab"]{{color:rgba(255,255,255,.55)!important;font-weight:500!important;
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
  color:rgba(255,255,255,.72)!important;font-weight:500!important;}}

[data-testid="stAlert"]{{backdrop-filter:blur(10px)!important;
  border-radius:10px!important;border-left-width:4px!important;}}
.stCodeBlock,.stCodeBlock pre,code{{background:rgba(0,0,0,.55)!important;
  border:1px solid rgba(21,101,255,.18)!important;border-radius:8px!important;
  color:rgba(255,255,255,.92)!important;}}

.stTextInput input,.stSelectbox [data-baseweb="select"]>div,textarea{{
  background:rgba(8,15,40,.75)!important;border:1px solid {BLUE_DIM}!important;
  border-radius:10px!important;color:#fff!important;transition:border-color .2s ease!important;}}
.stTextInput input:focus,textarea:focus{{border-color:{BLUE}!important;
  box-shadow:0 0 0 2px {BLUE_GLOW}!important;}}
[data-baseweb="select"] [data-testid="stMarkdownContainer"] p,
[data-baseweb="option"]{{color:rgba(255,255,255,.90)!important;}}

/* ── File Uploader: correct testid is stFileUploaderDropzone (Streamlit 1.58) ── */
[data-testid="stFileUploaderDropzone"]{{
  background:rgba(8,15,40,.58)!important;
  border:2px dashed {BLUE}!important;
  border-radius:14px!important;
  transition:all .25s ease!important;
  padding:20px!important;
}}
[data-testid="stFileUploaderDropzone"]:hover{{
  background:rgba(21,101,255,.08)!important;
  box-shadow:0 0 22px {BLUE_GLOW}!important;
}}
[data-testid="stFileUploaderDropzone"] p,
[data-testid="stFileUploaderDropzone"] span,
[data-testid="stFileUploaderDropzoneInstructions"] span{{
  color:rgba(255,255,255,.82)!important;
}}
/* Hide the hidden native file input to prevent double-upload text */
[data-testid="stFileUploaderDropzoneInput"]{{
  width:0!important;
  height:0!important;
  overflow:hidden!important;
  opacity:0!important;
  position:absolute!important;
  pointer-events:none!important;
}}
/* Style the Upload button nicely - hide the material icon span that shows as text */
[data-testid="stFileUploaderDropzone"] button{{
  background:rgba(21,101,255,.18)!important;
  border:1px solid rgba(21,101,255,.45)!important;
  border-radius:8px!important;
  color:#fff!important;
  font-weight:600!important;
  padding:6px 20px!important;
  font-size:.84rem!important;
}}
[data-testid="stFileUploaderDropzone"] button:hover{{
  background:rgba(21,101,255,.35)!important;
  box-shadow:0 0 12px rgba(21,101,255,.40)!important;
}}
/* Remove the material icon span that duplicates the Upload label */
[data-testid="stFileUploaderDropzone"] [data-testid="stIconMaterial"]{{
  display:none!important;
}}

/* ── Old wrong selector kept for safety (browser ignores unmatched) ── */
[data-testid="stFileUploadDropzone"]{{
  background:rgba(8,15,40,.58)!important;
  border:2px dashed {BLUE}!important;
  border-radius:14px!important;
}}


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

@keyframes pulse-glow{{
  0%  {{box-shadow:0 0 0 0 rgba(21,101,255,0),0 0 10px rgba(21,101,255,.5),0 0 0 3px rgba(21,101,255,.22);}}
  50% {{box-shadow:0 0 0 5px rgba(21,101,255,0),0 0 28px rgba(21,101,255,.85),0 0 0 3px rgba(21,101,255,.50);}}
  100%{{box-shadow:0 0 0 0 rgba(21,101,255,0),0 0 10px rgba(21,101,255,.5),0 0 0 3px rgba(21,101,255,.22);}}}}
@keyframes card-glow{{
  0%,100%{{box-shadow:0 0 0 2px rgba(21,101,255,.22),0 0 18px rgba(21,101,255,.42),inset 0 0 24px rgba(21,101,255,.06);}}
  50%{{box-shadow:0 0 0 5px rgba(21,101,255,.50),0 0 52px rgba(21,101,255,.95),inset 0 0 40px rgba(21,101,255,.16);}}}}
@keyframes step-pop{{from{{opacity:0;transform:scale(.80);}}to{{opacity:1;transform:scale(1);}}}}
@keyframes dot-pulse{{0%,100%{{opacity:1;}}50%{{opacity:.55;}}}}
::placeholder{{color:rgba(180,210,255,.42)!important;}}

/* ── Fix Streamlit file uploader double-label (uploadupload) ─────────── */
/* Hide the outer label that Streamlit renders above the dropzone */
[data-testid="stFileUploader"] > label,
[data-testid="stFileUploader"] > div > label {{
  display:none!important;
}}
/* Tighten the file uploader wrapper */
[data-testid="stFileUploader"] {{
  padding-top:0!important;
}}
/* The internal small-text button inside dropzone */
[data-testid="stFileUploaderDropzone"] small {{
  color:rgba(255,255,255,.50)!important;
  font-size:.72rem!important;
}}

/* ── Sidebar flex layout so System Status never overlaps nav ─────────── */
section[data-testid="stSidebar"] > div:first-child {{
  display:flex!important;
  flex-direction:column!important;
  height:100vh!important;
  overflow:hidden!important;
}}
/* Push nav into flex-grow */
section[data-testid="stSidebar"] [data-testid="stVerticalBlock"] {{
  flex:1!important;
}}

</style>""", unsafe_allow_html=True)


inject_css()


# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════════════════════
def render_sidebar():
    with st.sidebar:
        st.markdown(
            '<div style="padding:26px 20px 18px;border-bottom:1px solid rgba(21,101,255,.20);">'
            '<div style="display:flex;align-items:center;gap:12px;margin-bottom:2px;">'
            '<div style="width:38px;height:38px;border-radius:10px;'
            'background:linear-gradient(135deg,#1565FF,#0A3FCC);'
            'display:flex;align-items:center;justify-content:center;'
            'font-size:1.2rem;font-weight:800;color:#fff;flex-shrink:0;'
            'box-shadow:0 4px 16px rgba(21,101,255,.50);">N</div>'
            '<div><div style="font-size:1.22rem;font-weight:800;color:#fff;line-height:1.1;">Nova</div>'
            '<div style="font-size:.64rem;color:rgba(21,101,255,.90);font-weight:600;'
            'letter-spacing:.06em;text-transform:uppercase;line-height:1.3;">'
            'Governed Trade<br>Document Validator</div></div></div></div>',
            unsafe_allow_html=True,
        )

        nav_items = [
            ("rocket", "Pipeline Runner", "pipeline"),
            ("chat",   "NL Query",        "query"),
            ("scroll", "History",         "history"),
            ("ruler",  "Rules",           "rules"),
            ("gear",   "Settings",        "settings"),
        ]
        emojis = {"rocket": "&#128640;", "chat": "&#128172;", "scroll": "&#128220;",
                  "ruler": "&#128210;", "gear": "&#9881;"}

        if "nav" not in st.session_state:
            st.session_state["nav"] = "pipeline"

        st.markdown('<div style="padding:8px 12px 8px;">', unsafe_allow_html=True)
        for icon, label, key in nav_items:
            active = st.session_state.get("nav") == key
            if active:
                st.markdown(
                    f'<div style="display:flex;align-items:center;gap:10px;'
                    'padding:10px 14px;border-radius:10px;margin-bottom:4px;cursor:pointer;'
                    f'background:rgba(21,101,255,.18);border:1px solid rgba(21,101,255,.38);">'
                    f'<span style="font-size:.95rem;">{emojis[icon]}</span>'
                    f'<span style="color:#fff;font-weight:600;font-size:.88rem;">{label}</span>'
                    '</div>',
                    unsafe_allow_html=True,
                )
            else:
                if st.button(label, key=f"nav_{key}", use_container_width=True):
                    st.session_state["nav"] = key
        st.markdown('</div>', unsafe_allow_html=True)

        st.markdown(
            '<div style="margin:auto 12px 24px 12px;">'
            '<div style="display:flex;align-items:center;gap:10px;padding:10px 14px;'
            'background:rgba(5,150,105,.12);border:1px solid rgba(5,150,105,.30);border-radius:10px;">'
            '<div style="width:8px;height:8px;border-radius:50%;background:#059669;flex-shrink:0;'
            'box-shadow:0 0 8px rgba(5,150,105,.80);animation:dot-pulse 2.4s ease-in-out infinite;"></div>'
            '<div><div style="color:#fff;font-size:.76rem;font-weight:600;">System Status</div>'
            '<div style="color:#059669;font-size:.66rem;font-weight:500;">All systems operational</div>'
            '</div></div></div>',
            unsafe_allow_html=True,
        )


render_sidebar()


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════
def status_badge(status):
    cfg = {
        "match":     ("#057A55", "MATCH"),
        "mismatch":  ("#C81E1E", "MISMATCH"),
        "uncertain": ("#92400E", "UNCERTAIN"),
    }
    bg, lbl = cfg.get(status, ("#374151", status.upper()))
    sym = {"match": "&#10003;", "mismatch": "&#10007;", "uncertain": "?"}.get(status, "")
    return (f'<span style="background:{bg};color:#fff;padding:2px 9px;border-radius:5px;'
            f'font-size:.70rem;font-weight:700;letter-spacing:.05em;white-space:nowrap;">'
            f'{sym} {lbl}</span>')


def action_banner(action):
    cfg = {
        "auto_approve":    ("AUTO APPROVE",    "#064E3B","#059669","rgba(5,150,105,.28)",   "&#10003;"),
        "flag_for_review": ("FLAG FOR REVIEW", "#78350F","#D97706","rgba(217,119,6,.28)",   "&#9888;"),
        "draft_amendment": ("DRAFT AMENDMENT", "#7F1D1D","#EF4444","rgba(239,68,68,.28)",   "&#10007;"),
    }
    label, bg, bdr, glow, icon = cfg.get(
        action, (action.upper(), "#1E293B","#64748B","rgba(100,116,139,.28)","&#8226;"))
    return (f'<div style="background:{bg};border:2px solid {bdr};border-radius:14px;'
            f'padding:14px 24px;text-align:center;box-shadow:0 0 30px {glow};margin:8px 0 12px;">'
            f'<div style="font-size:1.5rem;margin-bottom:3px;">{icon}</div>'
            f'<div style="color:#fff;font-size:1.2rem;font-weight:800;letter-spacing:.10em;">{label}</div>'
            '</div>')


def conf_bar(conf):
    if conf >= 0.85:   fill, label = "#059669","HIGH"
    elif conf >= 0.50: fill, label = "#D97706","MID"
    else:              fill, label = "#EF4444","LOW"
    pct = int(conf * 100)
    return (f'<div style="margin:3px 0 6px;">'
            f'<div style="display:flex;justify-content:space-between;margin-bottom:3px;">'
            f'<span style="color:rgba(200,220,255,.85);font-size:.70rem;font-weight:600;">{label}</span>'
            f'<span style="color:#fff;font-size:.80rem;font-weight:700;">{pct}%</span></div>'
            f'<div style="background:rgba(255,255,255,.10);border-radius:4px;height:7px;overflow:hidden;">'
            f'<div style="background:{fill};width:{pct}%;height:7px;border-radius:4px;'
            'transition:width .4s ease;"></div></div></div>')


def field_row(fname, status, found, reason):
    return (
        '<div style="display:flex;align-items:center;gap:8px;'
        'background:rgba(8,15,40,.52);border:1px solid rgba(21,101,255,.12);'
        'border-radius:9px;padding:8px 12px;margin-bottom:4px;">'
        f'<div style="min-width:140px;color:#fff;font-weight:600;font-size:.82rem;">'
        f'{fname.replace("_"," ").title()}</div>'
        f'{status_badge(status)}'
        f'<div style="min-width:100px;color:rgba(255,255,255,.80);font-family:monospace;'
        f'font-size:.78rem;background:rgba(0,0,0,.25);padding:1px 7px;border-radius:4px;">'
        f'{found or "&#8212;"}</div>'
        f'<div style="color:rgba(200,220,255,.82);font-size:.78rem;flex:1;">{reason}</div>'
        '</div>'
    )


def trace_card(tid):
    return (
        '<div style="background:rgba(8,15,40,.68);border:1px solid rgba(21,101,255,.22);'
        'border-radius:12px;padding:12px 16px;margin-bottom:10px;'
        'display:flex;align-items:center;justify-content:space-between;">'
        '<div>'
        '<div style="color:#7EB5FF;font-size:.65rem;font-weight:700;'
        'letter-spacing:.09em;text-transform:uppercase;margin-bottom:3px;">Trace ID</div>'
        f'<div style="color:#fff;font-family:monospace;font-size:.78rem;word-break:break-all;">{tid}</div>'
        '</div>'
        '<div style="font-size:1.1rem;color:rgba(21,101,255,.70);">&#10064;</div>'
        '</div>'
    )


def recent_row(doc, action, ts):
    col = {"auto_approve":"#059669","flag_for_review":"#D97706","draft_amendment":"#EF4444"}.get(action,"#9CA3AF")
    lbl = {"auto_approve":"auto_approved","flag_for_review":"flag_for_review",
           "draft_amendment":"draft_amendment"}.get(action, action)
    return (
        '<div style="display:flex;align-items:center;gap:10px;padding:9px 14px;'
        'border-bottom:1px solid rgba(255,255,255,.05);">'
        f'<div style="flex:1;color:#fff;font-size:.80rem;font-weight:500;'
        'overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{doc}</div>'
        f'<div style="color:{col};font-size:.68rem;font-weight:700;background:{col}22;'
        f'padding:2px 8px;border-radius:5px;white-space:nowrap;">{lbl}</div>'
        f'<div style="color:rgba(200,220,255,.65);font-size:.68rem;white-space:nowrap;">{ts}</div>'
        '<div style="color:rgba(200,220,255,.55);font-size:.80rem;">&#62;</div>'
        '</div>'
    )


def load_recent(limit=5):
    try:
        import sqlite3, json
        from nova.infrastructure.database import DB_PATH
        conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT s.doc_paths,d.action,s.created_at FROM shipments s "
            "LEFT JOIN decisions d ON s.trace_id=d.trace_id "
            "ORDER BY s.created_at DESC LIMIT ?", (limit,)).fetchall()
        conn.close()
        out = []
        for r in rows:
            paths = json.loads(r["doc_paths"]) if r["doc_paths"] else []
            out.append({"doc": Path(paths[0]).name if paths else "unknown",
                        "action": r["action"] or "pending",
                        "ts": (r["created_at"] or "")[:16].replace("T"," ")})
        return out
    except Exception:
        return []


# ══════════════════════════════════════════════════════════════════════════════
# NAV ROUTING
# ══════════════════════════════════════════════════════════════════════════════
_nav = st.session_state.get("nav", "pipeline")
_page_meta = {
    "pipeline": ("Pipeline Runner",  "AI-powered extraction · Evidence-grounded validation · Governed routing"),
    "query":    ("NL Query",         "Natural language → read-only SQL, run against the live SQLite database."),
    "history":  ("Pipeline History", "Every processed shipment and its validation outcome."),
    "rules":    ("Validation Rules", "Customer rules loaded from config/rules.yaml — never embedded in prompts."),
    "settings": ("Settings",         "System configuration and environment status."),
}
_title, _subtitle = _page_meta.get(_nav, ("Nova", ""))
st.markdown(
    f'<div style="margin-bottom:8px;">'
    f'<h1 style="margin:0 0 2px;">{_title}</h1>'
    f'<p style="color:rgba(200,220,255,.82);font-size:.86rem;margin:0;">{_subtitle}</p></div>',
    unsafe_allow_html=True,
)


# ══════════════════════════════════════════════════════════════════════════════
# PIPELINE RUNNER PAGE
# ══════════════════════════════════════════════════════════════════════════════
if _nav == "pipeline":

    # ── stepper — uses a placeholder so it can update live during execution ──
    active_step = st.session_state.get("pipeline_step", "upload")
    stepper_ph = st.empty()
    stepper_ph.markdown(build_stepper(active_step), unsafe_allow_html=True)
    st.markdown('<div style="height:2px;"></div>', unsafe_allow_html=True)

    # ── layout ───────────────────────────────────────────────────────────────
    col_L, col_R = st.columns([1.15, 1], gap="large")

    with col_L:
        st.markdown(
            '<div style="font-size:.72rem;font-weight:700;color:#7EB5FF;'
            'letter-spacing:.10em;text-transform:uppercase;margin-bottom:8px;">'
            'Upload a trade document</div>',
            unsafe_allow_html=True,
        )
        uploaded = st.file_uploader(
            "PDF / JPG / PNG", type=["pdf","jpg","jpeg","png"],
            label_visibility="collapsed",
        )
        ca, cb, cc = st.columns([2, .12, 1.5])
        with ca:
            run_btn = st.button("Run Pipeline", type="primary",
                                disabled=uploaded is None,
                                use_container_width=True, key="run_btn")
        with cc:
            resume_id = st.text_input("Resume ID", placeholder="paste trace_id to resume",
                                      label_visibility="collapsed", key="resume_inp")
            resume_btn = st.button("Resume from checkpoint",
                                   disabled=not resume_id.strip(),
                                   use_container_width=True, key="resume_btn")

    with col_R:
        right_trace = st.empty()
        right_status = st.empty()
        right_decision = st.empty()
        right_reasoning = st.empty()

    # ── pipeline runner ───────────────────────────────────────────────────────
    def set_step(key):
        st.session_state["pipeline_step"] = key

    def run_pipeline_live(trace_id, doc_paths):
        from nova.pipeline.pipeline import (
            node_setup, node_extractor, node_validator, node_router, node_persist,
        )
        state = PipelineState(trace_id=trace_id, raw_doc_paths=doc_paths).model_dump()

        set_step("extract")
        stepper_ph.markdown(build_stepper("extract"), unsafe_allow_html=True)
        state = node_setup(state)

        set_step("validate")
        stepper_ph.markdown(build_stepper("validate"), unsafe_allow_html=True)
        state = node_extractor(state)

        set_step("decide")
        stepper_ph.markdown(build_stepper("decide"), unsafe_allow_html=True)
        state = node_validator(state)

        set_step("complete")
        stepper_ph.markdown(build_stepper("complete"), unsafe_allow_html=True)
        state = node_router(state)
        state = node_persist(state)
        return PipelineState(**state)

    if run_btn and uploaded:
        sfx  = Path(uploaded.name).suffix
        tmp  = tempfile.NamedTemporaryFile(delete=False, suffix=sfx)
        tmp.write(uploaded.read()); tmp.flush()
        tid  = str(uuid.uuid4())
        st.session_state.update({"last_trace_id": tid,
                                  "pipeline_result": None,
                                  "pipeline_step": "upload"})
        right_trace.markdown(trace_card(tid), unsafe_allow_html=True)
        right_status.markdown(
            '<div style="background:rgba(21,101,255,.10);border:1px solid rgba(21,101,255,.25);'
            'border-radius:10px;padding:8px 14px;margin-bottom:8px;">'
            '<div style="color:#7EB5FF;font-size:.64rem;font-weight:700;'
            'letter-spacing:.09em;text-transform:uppercase;margin-bottom:2px;">Pipeline Status</div>'
            '<div style="color:rgba(255,255,255,.90);font-size:.84rem;font-weight:500;">'
            '&#9203; Running pipeline...</div></div>',
            unsafe_allow_html=True,
        )
        with st.spinner("Running pipeline..."):
            try:
                result = run_pipeline_live(tid, [tmp.name])
                st.session_state["pipeline_result"] = result
            except Exception as e:
                st.error(f"Pipeline error: {e}")
                st.session_state["pipeline_result"] = None
        st.rerun()

    if resume_btn and resume_id.strip():
        with st.spinner("Resuming..."):
            try:
                result = resume(resume_id.strip())
                st.session_state.update({"pipeline_result": result,
                                          "pipeline_step": "complete"})
            except Exception as e:
                st.error(f"Resume error: {e}")
        st.rerun()

    # ── results ───────────────────────────────────────────────────────────────
    result = st.session_state.get("pipeline_result")

    if result and result.extracted:
        # left column: extraction table
        with col_L:
            st.markdown(
                '<div style="font-size:.72rem;font-weight:700;color:#7EB5FF;'
                'letter-spacing:.10em;text-transform:uppercase;margin:14px 0 8px;">'
                'Extraction Results</div>',
                unsafe_allow_html=True,
            )
            fields = result.extracted.field_names()
            hdr = (
                '<table style="width:100%;border-collapse:collapse;">'
                '<thead><tr style="border-bottom:1px solid rgba(255,255,255,.07);">'
                + ''.join(
                    f'<th style="color:#7EB5FF;font-size:.65rem;font-weight:700;'
                    f'letter-spacing:.08em;text-transform:uppercase;padding:7px 10px;text-align:left;">'
                    f'{h}</th>'
                    for h in ["Field", "Extracted Value", "Confidence", "Evidence"]
                )
                + '</tr></thead><tbody>'
            )
            rows_html = ""
            for fn in fields:
                fv = result.extracted.get_field(fn)
                c  = fv.confidence
                cc2 = "#059669" if c >= .85 else ("#D97706" if c >= .50 else "#EF4444")
                rows_html += (
                    f'<tr style="border-bottom:1px solid rgba(255,255,255,.04);">'
                    f'<td style="color:#fff;font-weight:600;font-size:.80rem;padding:7px 10px;'
                    f'white-space:nowrap;">{fn.replace("_"," ").title()}</td>'
                    f'<td style="color:rgba(255,255,255,.82);font-family:monospace;font-size:.78rem;'
                    f'padding:7px 10px;">{fv.value or "&#8212;"}</td>'
                    f'<td style="padding:7px 10px;"><span style="color:{cc2};font-weight:700;'
                    f'font-size:.78rem;">{int(c*100)}%</span></td>'
                    f'<td style="color:rgba(200,220,255,.78);font-size:.72rem;padding:7px 10px;">'
                    f'{"Page " + str(fv.source_page) if fv.source_page else "&#8212;"}</td></tr>'
                )
            st.markdown(
                f'<div style="background:rgba(5,10,28,.60);border:1px solid rgba(21,101,255,.13);'
                f'border-radius:12px;overflow:hidden;">{hdr}{rows_html}</tbody></table></div>',
                unsafe_allow_html=True,
            )
            with st.expander("View full source snippets", expanded=False):
                for fn in fields:
                    fv = result.extracted.get_field(fn)
                    st.markdown(
                        f'<span style="color:rgba(255,255,255,.70);font-weight:600;font-size:.80rem;">'
                        f'{fn.replace("_"," ").title()}</span>', unsafe_allow_html=True)
                    if fv.source_snippet:
                        st.code(fv.source_snippet, language=None)
                    else:
                        st.caption("No snippet - confidence capped at 0.3")

        # right column: trace + decision + reasoning
        with col_R:
            action_label = result.decision.action if result.decision else ""
            status_color = {"auto_approve":"#059669",
                            "flag_for_review":"#D97706",
                            "draft_amendment":"#EF4444"}.get(action_label,"#fff")
            right_trace.markdown(
                trace_card(result.trace_id)
                + f'<div style="background:rgba(5,150,105,.10);border:1px solid rgba(5,150,105,.28);'
                  f'border-radius:10px;padding:8px 14px;margin-bottom:10px;">'
                  f'<div style="color:#7EB5FF;font-size:.64rem;font-weight:700;'
                  f'letter-spacing:.09em;text-transform:uppercase;margin-bottom:2px;">Pipeline Status</div>'
                  f'<div style="color:{status_color};font-size:.84rem;font-weight:600;">'
                  f'Pipeline complete &#8212; {action_label}</div>'
                  f'<div style="color:rgba(200,220,255,.68);font-size:.68rem;margin-top:2px;font-family:monospace;">'
                  f'cost: ${result.cost_usd:.4f}</div></div>',
                unsafe_allow_html=True,
            )
            right_status.empty()

            if result.decision:
                right_decision.markdown(
                    '<div style="font-size:.68rem;font-weight:700;color:#7EB5FF;'
                    'letter-spacing:.10em;text-transform:uppercase;margin-bottom:5px;">Router Decision</div>'
                    + action_banner(result.decision.action),
                    unsafe_allow_html=True,
                )
                right_reasoning.markdown(
                    '<div style="font-size:.68rem;font-weight:700;color:#7EB5FF;'
                    'letter-spacing:.10em;text-transform:uppercase;margin-bottom:5px;">Router Reasoning</div>'
                    '<div style="background:rgba(8,15,40,.62);border:1px solid rgba(21,101,255,.16);'
                    'border-radius:12px;padding:14px 16px;">'
                    f'<div style="color:rgba(255,255,255,.85);font-size:.80rem;line-height:1.7;'
                    f'white-space:pre-wrap;">{result.decision.reasoning}</div></div>',
                    unsafe_allow_html=True,
                )

            if result.validation:
                st.markdown('<div style="height:6px;"></div>', unsafe_allow_html=True)
                st.markdown(
                    '<div style="font-size:.72rem;font-weight:700;color:#7EB5FF;'
                    'letter-spacing:.10em;text-transform:uppercase;margin-bottom:8px;">'
                    'Validation Verdicts</div>',
                    unsafe_allow_html=True,
                )
                verdicts_html = ''.join(
                    field_row(v.field, v.status, v.found or "", v.reason)
                    for v in result.validation.verdicts
                )
                st.markdown(verdicts_html, unsafe_allow_html=True)
                st.metric("Overall Confidence", f"{result.validation.overall_confidence:.0%}")

            if result.decision and result.decision.amendment_email:
                st.markdown(
                    '<div style="font-size:.72rem;font-weight:700;color:#7EB5FF;'
                    'letter-spacing:.10em;text-transform:uppercase;margin:12px 0 6px;">'
                    'Amendment Email</div>',
                    unsafe_allow_html=True,
                )
                st.code(result.decision.amendment_email, language=None)

    # ── bottom bar ────────────────────────────────────────────────────────────
    st.markdown("---")
    bot_L, bot_R = st.columns([1.4, 1], gap="large")

    with bot_L:
        st.markdown(
            '<div style="font-size:.96rem;font-weight:700;color:#fff;margin-bottom:3px;">'
            'Ask anything about your shipments</div>'
            '<div style="font-size:.76rem;color:rgba(200,220,255,.78);margin-bottom:10px;">'
            'Natural language queries run against the live database</div>',
            unsafe_allow_html=True,
        )
        qc, bc = st.columns([5, 1])
        with qc:
            nl_q = st.text_input("NL Question", placeholder="e.g. How many shipments were auto-approved?",
                                  label_visibility="collapsed", key="nl_q")
        with bc:
            nl_btn = st.button("Ask", type="primary", key="nl_btn",
                               use_container_width=True, disabled=not nl_q.strip())

        st.markdown(
            '<div style="display:flex;gap:7px;flex-wrap:wrap;margin-top:5px;">'
            + ''.join(
                f'<span style="background:rgba(21,101,255,.10);border:1px solid rgba(21,101,255,.22);'
                f'color:rgba(200,220,255,.82);font-size:.68rem;padding:3px 9px;border-radius:5px;">{t}</span>'
                for t in ["Show all shipments pending review",
                           "Top 5 suppliers by amendments",
                           "Average confidence by document type"]
            )
            + '</div>',
            unsafe_allow_html=True,
        )

        if nl_btn and nl_q.strip():
            if "qhist" not in st.session_state:
                st.session_state["qhist"] = []
            with st.spinner("Querying..."):
                r = ask(nl_q.strip())
                st.session_state["qhist"].insert(0, r)
                if len(st.session_state["qhist"]) > 5:
                    st.session_state["qhist"] = st.session_state["qhist"][:5]

        for i, qr in enumerate(st.session_state.get("qhist", [])):
            with st.expander(f"Q: {qr['question']}", expanded=(i == 0)):
                st.markdown(
                    '<div style="background:rgba(5,150,105,.10);border-left:3px solid #059669;'
                    'border-radius:0 9px 9px 0;padding:9px 13px;margin-bottom:8px;">'
                    '<div style="color:#7EB5FF;font-size:.66rem;font-weight:700;'
                    'text-transform:uppercase;letter-spacing:.07em;margin-bottom:3px;">Answer</div>'
                    f'<div style="color:rgba(255,255,255,.90);line-height:1.6;">{qr["answer"]}</div>'
                    '</div>',
                    unsafe_allow_html=True,
                )
                if qr.get("sql"):
                    st.code(qr["sql"], language="sql")
                if qr.get("rows"):
                    st.json(qr["rows"][:10])
                st.caption(f'cost: ${qr.get("cost_usd",0):.6f}')

    with bot_R:
        recent = load_recent(5)
        st.markdown(
            '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">'
            '<div style="font-size:.96rem;font-weight:700;color:#fff;">Recent Pipeline Runs</div>'
            '<div style="font-size:.70rem;color:rgba(21,101,255,.85);font-weight:600;">View All &#8250;</div>'
            '</div>',
            unsafe_allow_html=True,
        )
        if recent:
            inner = ''.join(recent_row(r["doc"], r["action"], r["ts"]) for r in recent)
            st.markdown(
                f'<div style="background:rgba(5,10,28,.62);border:1px solid rgba(21,101,255,.13);'
                f'border-radius:12px;overflow:hidden;">{inner}</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<div style="color:rgba(200,220,255,.62);font-size:.80rem;'
                'padding:20px;text-align:center;">No pipeline runs yet</div>',
                unsafe_allow_html=True,
            )


# ══════════════════════════════════════════════════════════════════════════════
# NL QUERY PAGE
# ══════════════════════════════════════════════════════════════════════════════
elif _nav == "query":
    if "query_history" not in st.session_state:
        st.session_state["query_history"] = []

    examples = ["How many shipments were auto-approved?",
                "Show me all flagged shipments",
                "Which fields had the most mismatches?",
                "Total shipments processed?"]
    sel = st.selectbox("Example:", ["-- pick one --"] + examples)
    question = st.text_input(
        "Question",
        value=sel if sel != "-- pick one --" else "",
        key="nl_tab_q",
        placeholder="e.g. How many shipments were auto-approved?",
    )
    ask_btn = st.button("Ask", type="primary", disabled=not question.strip(),
                        key="nl_tab_btn")

    if ask_btn and question.strip():
        with st.spinner("Generating SQL..."):
            r2 = ask(question.strip())
            st.session_state["query_history"].insert(0, r2)
            if len(st.session_state["query_history"]) > 5:
                st.session_state["query_history"] = st.session_state["query_history"][:5]

    for i, qr in enumerate(st.session_state.get("query_history", [])):
        with st.expander(f"Q: {qr['question']}", expanded=(i == 0)):
            st.markdown(
                '<div style="background:rgba(5,150,105,.10);border-left:3px solid #059669;'
                'border-radius:0 9px 9px 0;padding:10px 14px;margin-bottom:10px;">'
                '<div style="color:#7EB5FF;font-size:.68rem;font-weight:700;'
                'text-transform:uppercase;letter-spacing:.06em;margin-bottom:3px;">Answer</div>'
                f'<div style="color:rgba(255,255,255,.92);line-height:1.6;">{qr["answer"]}</div>'
                '</div>',
                unsafe_allow_html=True,
            )
            if qr.get("sql"):
                st.markdown(
                    '<span style="color:#7EB5FF;font-size:.70rem;'
                    'font-weight:700;text-transform:uppercase;">Generated SQL</span>',
                    unsafe_allow_html=True,
                )
                st.code(qr["sql"], language="sql")
            if qr.get("rows"):
                st.caption(f'{len(qr["rows"])} row(s)')
                st.json(qr["rows"][:10])
            st.caption(f'cost: ${qr.get("cost_usd",0):.6f}')


# ══════════════════════════════════════════════════════════════════════════════
# HISTORY PAGE
# ══════════════════════════════════════════════════════════════════════════════
elif _nav == "history":
    import sqlite3 as _sqlite3, json as _json
    from nova.infrastructure.database import DB_PATH as _DB_PATH

    def _load_history():
        try:
            conn = _sqlite3.connect(str(_DB_PATH), check_same_thread=False)
            conn.row_factory = _sqlite3.Row
            rows = conn.execute(
                "SELECT s.trace_id, s.doc_paths, s.status, s.created_at, "
                "d.action, d.reasoning, d.amendment_email "
                "FROM shipments s LEFT JOIN decisions d ON s.trace_id=d.trace_id "
                "ORDER BY s.created_at DESC"
            ).fetchall()
            fields_map = {}
            for r in rows:
                frows = conn.execute(
                    "SELECT field_name,value,confidence FROM fields WHERE trace_id=?",
                    (r["trace_id"],)
                ).fetchall()
                fields_map[r["trace_id"]] = [dict(f) for f in frows]
            conn.close()
            return [dict(r) for r in rows], fields_map
        except Exception as e:
            st.error(f"DB error: {e}")
            return [], {}

    hist_rows, fields_map = _load_history()

    ACTION_COLOR = {
        "auto_approve":    ("#059669", "AUTO APPROVE",    "rgba(5,150,105,.15)"),
        "flag_for_review": ("#D97706", "FLAG FOR REVIEW", "rgba(217,119,6,.15)"),
        "draft_amendment": ("#EF4444", "DRAFT AMENDMENT", "rgba(239,68,68,.15)"),
    }

    if not hist_rows:
        st.markdown(
            '<div style="text-align:center;padding:60px 20px;">'
            '<div style="font-size:2.5rem;margin-bottom:12px;">📭</div>'
            '<div style="color:rgba(200,220,255,.70);font-size:1rem;">'
            'No pipeline runs yet. Go to <b>Pipeline Runner</b> and upload a document.</div>'
            '</div>', unsafe_allow_html=True)
    else:
        st.markdown(
            f'<div style="color:#7EB5FF;font-size:.72rem;font-weight:700;'
            f'letter-spacing:.10em;text-transform:uppercase;margin-bottom:14px;">'
            f'{len(hist_rows)} run{"s" if len(hist_rows)!=1 else ""} found</div>',
            unsafe_allow_html=True)

        for r in hist_rows:
            action   = r["action"] or "pending"
            col, lbl, bg = ACTION_COLOR.get(action, ("#9CA3AF", action.upper(), "rgba(156,163,175,.12)"))
            paths    = _json.loads(r["doc_paths"]) if r["doc_paths"] else []
            doc_name = Path(paths[0]).name if paths else "unknown"
            ts       = (r["created_at"] or "")[:16].replace("T", " ")

            with st.expander(f"  {doc_name}  ·  {lbl}  ·  {ts}", expanded=False):
                c1, c2 = st.columns([1, 1], gap="medium")
                with c1:
                    st.markdown(
                        f'<div style="background:{bg};border:1px solid {col}44;'
                        f'border-radius:10px;padding:10px 14px;margin-bottom:8px;">'
                        f'<div style="color:{col};font-size:.80rem;font-weight:700;">{lbl}</div>'
                        f'<div style="color:rgba(200,220,255,.70);font-size:.68rem;margin-top:3px;'
                        f'font-family:monospace;">{r["trace_id"]}</div>'
                        f'<div style="color:rgba(200,220,255,.55);font-size:.66rem;margin-top:2px;">{ts}</div>'
                        f'</div>', unsafe_allow_html=True)
                    if r.get("reasoning"):
                        st.markdown(
                            '<div style="color:#7EB5FF;font-size:.65rem;font-weight:700;'
                            'letter-spacing:.08em;text-transform:uppercase;margin-bottom:4px;">Reasoning</div>',
                            unsafe_allow_html=True)
                        st.markdown(
                            f'<div style="background:rgba(8,15,40,.60);border:1px solid rgba(21,101,255,.14);'
                            f'border-radius:9px;padding:10px 13px;color:rgba(255,255,255,.85);'
                            f'font-size:.78rem;line-height:1.65;white-space:pre-wrap;">'
                            f'{r["reasoning"]}</div>', unsafe_allow_html=True)
                with c2:
                    flist = fields_map.get(r["trace_id"], [])
                    if flist:
                        st.markdown(
                            '<div style="color:#7EB5FF;font-size:.65rem;font-weight:700;'
                            'letter-spacing:.08em;text-transform:uppercase;margin-bottom:6px;">'
                            'Extracted Fields</div>', unsafe_allow_html=True)
                        for fv in flist:
                            conf = fv["confidence"]
                            cc = "#059669" if conf >= .85 else ("#D97706" if conf >= .50 else "#EF4444")
                            st.markdown(
                                f'<div style="display:flex;justify-content:space-between;'
                                f'align-items:center;padding:4px 10px;margin-bottom:2px;'
                                f'background:rgba(8,15,40,.50);border-radius:6px;">'
                                f'<span style="color:rgba(200,220,255,.80);font-size:.74rem;">'
                                f'{fv["field_name"].replace("_"," ").title()}</span>'
                                f'<span style="color:#fff;font-size:.74rem;font-family:monospace;">'
                                f'{fv["value"] or "—"}</span>'
                                f'<span style="color:{cc};font-size:.70rem;font-weight:700;">'
                                f'{int(conf*100)}%</span>'
                                f'</div>', unsafe_allow_html=True)
                if r.get("amendment_email"):
                    st.markdown(
                        '<div style="color:#7EB5FF;font-size:.65rem;font-weight:700;'
                        'letter-spacing:.08em;text-transform:uppercase;margin:8px 0 4px;">'
                        'Amendment Email</div>', unsafe_allow_html=True)
                    st.code(r["amendment_email"], language=None)


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
        f'<div style="font-size:1.5rem;">🏢</div>'
        f'<div><div style="color:#7EB5FF;font-size:.65rem;font-weight:700;letter-spacing:.10em;'
        f'text-transform:uppercase;">Active Customer Profile</div>'
        f'<div style="color:#fff;font-size:1.05rem;font-weight:700;margin-top:2px;">{customer}</div>'
        f'</div></div>', unsafe_allow_html=True)

    MATCH_ICONS = {
        "exact_ci": "🔤", "prefix": "🔢", "enum": "📋",
        "numeric_tolerance": "⚖️", "regex": "🔍", "semantic": "🧠",
    }

    rules = rules_data.get("rules", {})
    cols = st.columns(2, gap="medium")
    for idx, (field, cfg) in enumerate(rules.items()):
        mtype = cfg.get("match_type", "")
        icon  = MATCH_ICONS.get(mtype, "·")
        with cols[idx % 2]:
            detail_lines = []
            for k, v in cfg.items():
                if k == "match_type":
                    continue
                detail_lines.append(
                    f'<div style="display:flex;justify-content:space-between;padding:4px 0;'
                    f'border-bottom:1px solid rgba(255,255,255,.05);">'
                    f'<span style="color:rgba(200,220,255,.65);font-size:.74rem;">{k.replace("_"," ").title()}</span>'
                    f'<span style="color:#fff;font-size:.74rem;font-family:monospace;">{v}</span>'
                    f'</div>'
                )
            st.markdown(
                f'<div style="background:rgba(8,15,40,.65);border:1px solid rgba(21,101,255,.18);'
                f'border-left:3px solid #1565FF;border-radius:10px;padding:14px 16px;margin-bottom:12px;">'
                f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:10px;">'
                f'<span style="font-size:1.1rem;">{icon}</span>'
                f'<div>'
                f'<div style="color:#fff;font-weight:700;font-size:.88rem;">'
                f'{field.replace("_"," ").title()}</div>'
                f'<div style="color:#7EB5FF;font-size:.68rem;font-weight:600;margin-top:1px;">{mtype}</div>'
                f'</div></div>'
                + "".join(detail_lines) +
                f'</div>', unsafe_allow_html=True)

    st.markdown("---")
    st.markdown(
        '<div style="color:rgba(200,220,255,.60);font-size:.80rem;">'
        '⚙️ Rules are loaded fresh from <code>config/rules.yaml</code> on every pipeline run — '
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
            f'<div style="color:rgba(200,220,255,.80);font-size:.85rem;">{label}</div>'
            f'<div style="color:{status_color};font-family:monospace;font-size:.82rem;'
            f'background:rgba(0,0,0,.30);padding:3px 10px;border-radius:6px;">{value}</div>'
            f'</div>'
        )

    api_key = _os.environ.get("OPENAI_API_KEY", "")
    api_status  = ("sk-…" + api_key[-6:]) if len(api_key) > 10 else "NOT SET"
    api_color   = "#059669" if len(api_key) > 10 else "#EF4444"
    db_exists   = Path(str(_DBPATH)).exists()
    db_color    = "#059669" if db_exists else "#D97706"

    st.markdown(
        '<div style="background:rgba(8,15,40,.68);border:1px solid rgba(21,101,255,.20);'
        'border-radius:14px;overflow:hidden;margin-bottom:18px;">'
        '<div style="padding:12px 16px;border-bottom:1px solid rgba(21,101,255,.15);">'
        '<div style="color:#7EB5FF;font-size:.68rem;font-weight:700;letter-spacing:.10em;'
        'text-transform:uppercase;">Environment</div></div>'
        + _setting_row("OpenAI API Key",    api_status,                        api_color)
        + _setting_row("Extraction Model",  "gpt-4o (vision)",                 "#7EB5FF")
        + _setting_row("Validation Model",  "gpt-4o-mini",                     "#7EB5FF")
        + _setting_row("Orchestration",     "LangGraph",                       "#7EB5FF")
        + _setting_row("Database",          str(_DBPATH),                      db_color)
        + _setting_row("DB Status",         "Ready" if db_exists else "Will be created on first run", db_color)
        + _setting_row("Rules Config",      "config/rules.yaml",               "#7EB5FF")
        + _setting_row("Crash Recovery",    "Checkpoint per node → resume(trace_id)", "#059669")
        + '</div>',
        unsafe_allow_html=True)

    st.markdown(
        '<div style="background:rgba(8,15,40,.68);border:1px solid rgba(21,101,255,.20);'
        'border-radius:14px;overflow:hidden;margin-bottom:18px;">'
        '<div style="padding:12px 16px;border-bottom:1px solid rgba(21,101,255,.15);">'
        '<div style="color:#7EB5FF;font-size:.68rem;font-weight:700;letter-spacing:.10em;'
        'text-transform:uppercase;">Pipeline Limits</div></div>'
        + _setting_row("Max Retries",       "2 per run",                       "#7EB5FF")
        + _setting_row("Supported Formats", "PDF, JPG, JPEG, PNG",             "#7EB5FF")
        + _setting_row("NL Query",          "Read-only SELECT only",           "#7EB5FF")
        + _setting_row("Confidence Threshold", "≥ 0.85 to auto-approve",       "#7EB5FF")
        + _setting_row("Evidence Rule",     "No snippet → confidence ≤ 0.30",  "#7EB5FF")
        + '</div>',
        unsafe_allow_html=True)

    st.markdown(
        '<div style="color:rgba(200,220,255,.55);font-size:.78rem;margin-top:6px;">'
        'To update the OpenAI key, edit <code>.env</code> in the project root and restart the app.</div>',
        unsafe_allow_html=True)
