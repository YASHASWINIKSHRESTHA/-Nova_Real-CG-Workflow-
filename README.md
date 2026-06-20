# Nova POC — Governed Trade Document Validation Pipeline

> *"Nova doesn't get to be a confident liar. A wrongly auto-approved HS code is a customs hold plus a contract penalty — so the system is built so that nothing reaches the customer without evidence and a human click."*

A POC-scale, runnable miniature of GoComet's **Nova** platform: a multi-agent, evidence-grounded, crash-recoverable trade-document validation pipeline with a CG-operator UI. Built for the Full-Stack AI Engineer Day-at-Work assignment.

The thesis of this build is not "a smarter prompt." It is **separation of concerns plus refusal to trust the model where correctness matters**: extraction, validation, cross-document consistency, and *sending* are four distinct stages; the high-stakes ones are deterministic; the LLM is never the judge of a verdict; and the agent has no code path to send a reply on its own.

| | |
|---|---|
| **Part 1** | Single-document pipeline: `extractor → validator → router → persist`, plus crash-safe checkpointing and a natural-language query layer over the stored results. |
| **Part 2** | Adds the missing trigger and the real CG workflow: an SU-email inbox watcher, multi-document handling, deterministic **cross-document** consistency, and a CG Operations UI with four states (Incoming → Verification → Discrepancy → Draft Reply). |

---

## Table of Contents

1. [The Problem & The Approach](#1-the-problem--the-approach)
2. [Quick Start — Part 2 (CG Operations UI)](#2-quick-start--part-2-cg-operations-ui)
3. [Full Setup (Mac / Linux / Windows)](#3-full-setup-mac--linux--windows)
4. [Guided Demo Script (what to click, what you'll see)](#4-guided-demo-script)
5. [Architecture](#5-architecture)
6. [The Five Trust Guarantees (USP)](#6-the-five-trust-guarantees-usp)
7. [Project Structure](#7-project-structure)
8. [Data Model & Storage](#8-data-model--storage)
9. [Running Each Piece (CLI)](#9-running-each-piece-cli)
10. [Crash-Recovery Demo](#10-crash-recovery-demo)
11. [Evals & Tests](#11-evals--tests)
12. [Natural-Language Query Layer](#12-natural-language-query-layer)
13. [Stack & Why Each Choice](#13-stack--why-each-choice)
14. [POC Scope — What's Intentionally Not Built](#14-poc-scope--what-is-intentionally-not-built)
15. [Cost, Latency & Observability Notes](#15-cost-latency--observability-notes)
16. [Troubleshooting](#16-troubleshooting)
17. [Submission Checklist](#17-submission-checklist)

---

## 1. The Problem & The Approach

In global trade, every shipment generates a stack of documents — Bill of Lading, Commercial Invoice, Packing List. Today a CG (Cargo / Control Group) operator opens every supplier email, reads every field in every attachment, mentally checks each value against customer-specific rules that live in someone's head, and types amendment emails by hand. Two to four email round-trips per shipment is normal; each cycle adds 4–24 hours of delay, and there is no audit trail when a dispute arises.

The three-party process — **SU sends → CG validates → Customer receives** — is correct and stays exactly as is. What does *not* need to exist is a human reading every field and typing every amendment.

Nova automates the boring 80% (extract, validate, decide) and routes only the exceptions to a human. The design rule throughout: **surface uncertainty, never hide it; a silent auto-approval of a wrong field is the single worst outcome, so the system is built to make that structurally impossible.**

---

## 2. Quick Start — Part 2 (CG Operations UI)

```bash
cd nova-poc

# 1. Create & activate a Python 3.11 virtual environment
python -m venv .venv
source .venv/bin/activate            # Mac / Linux
# .venv\Scripts\activate             # Windows PowerShell

# 2. Install dependencies
pip install --no-cache-dir -r requirements.txt

# 3. Add your OpenAI API key
cp .env.example .env                 # Mac / Linux   (Windows: copy .env.example .env)
# then edit .env and set OPENAI_API_KEY=sk-...

# 4. Reset the inbox to a clean, reproducible demo state
#    (creates ACME_001 = clean, ACME_002 = HS-code mismatch)
python scripts/reset_inbox.py

# 5. Launch the CG Operations UI
streamlit run app_cg.py
```

Open **http://localhost:8501**. Jump to the [Guided Demo Script](#4-guided-demo-script) for the exact click-path.

> **Why `reset_inbox.py` first?** It guarantees the two canonical demo shipments exist in a clean state — one fully consistent, one with a deliberate cross-document HS-code mismatch — so the discrepancy path is reproducible on a fresh checkout regardless of any prior run.

---

## 3. Full Setup (Mac / Linux / Windows)

```bash
# 1. Enter the project directory
cd nova-poc

# 2. Create a Python 3.11 virtual environment
python -m venv .venv

# 3. Activate it
source .venv/bin/activate            # Mac / Linux
# .venv\Scripts\activate             # Windows PowerShell

# 4. Install dependencies (downloads ~2 GB incl. torch-free wheels; ~2 min)
pip install --no-cache-dir -r requirements.txt

# 5. Add your OpenAI API key
cp .env.example .env                 # Mac / Linux
# copy .env.example .env             # Windows
# Edit .env: OPENAI_API_KEY=sk-...

# 6. Generate synthetic sample documents
python scripts/generate_samples.py           # Part 1 single-doc samples
python scripts/reset_inbox.py                 # Part 2 inbox (clean + mismatch shipments)

# 7. Run an app
streamlit run app_cg.py              # Part 2 — CG Operations UI  (recommended)
# streamlit run app.py               # Part 1 — single-doc pipeline
```

> **Windows with limited C: drive space** — create the venv on another drive:
> ```powershell
> "C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python311\python.exe" -m venv D:\nova_venv
> D:\nova_venv\Scripts\activate
> ```
> then use `D:\nova_venv\Scripts\pip`, `D:\nova_venv\Scripts\streamlit`, etc. throughout.

**Requirements** (`requirements.txt`): `openai`, `langgraph`, `langchain-core`, `langsmith`, `pydantic v2`, `pymupdf`, `pyyaml`, `streamlit`, `python-dotenv`, `reportlab`, `Pillow`, `pytest`. Python **3.11** recommended.

---

## 4. Guided Demo Script

After `streamlit run app_cg.py`, the UI presents one shipment at a time through four states. The fastest 2-minute walkthrough:

**A. The clean shipment (auto-approvable, but still human-gated)**
1. **Incoming** tab — `shipment_ACME_001` appears with its three attachments (BOL + Invoice + Packing List) and a **Process Shipment** button.
2. Click **Process Shipment** — the pipeline fires: extract each attachment → validate each field → cross-validate shared fields → route.
3. **Verification Result** tab — a per-document field table (value · confidence · verdict) plus a **cross-doc consistency strip** showing consignee / HS code / invoice number all agree (green).
4. **Draft Reply** tab — a pre-filled **approval** email. Edit if you like, then **Send (mock)** — the shipment folder moves to `inbox/processed/`.

**B. The mismatch shipment (the important one)**
1. Back to **Incoming** → select `shipment_ACME_002` → **Process Shipment**.
2. **Verification Result** tab — the cross-doc strip flags `hs_code` as **CROSS-DOC INCONSISTENT**.
3. **Discrepancy Detail** tab — click the flagged field: it shows **found vs expected**, the **verbatim source snippet** from each document, and the cross-doc diff (BOL = `8471.30`, Invoice = `9999.99`, Packing List = `8471.30`).
4. **Draft Reply** tab — a pre-filled **amendment** email listing the discrepancy by field · found · expected · source document. One edit and it is send-ready. **Send (mock)** dispatches and archives the shipment.

**C. The hand-off (query layer)**
- **NL Query** tab — ask *"Show me everything pending review for Acme Logistics"* or *"How many shipments were auto-approved?"* and get a grounded answer from the SQLite store.

> **The agent never auto-sends.** The pipeline halts at `node_await_cg` (status `pending_cg_review`). Only the operator's **Send** click dispatches a reply. This is enforced by the graph topology, not by a prompt instruction — see [§6](#6-the-five-trust-guarantees-usp).

**Additional sample shipments** (`ACME_003`–`007`, `TECHCO_001`) ship in `inbox/incoming/` to give the NL query layer a realistic multi-customer dataset (two customers, varied HS codes). Run `python scripts/reset_inbox.py` at any time to return to the clean two-shipment demo state.

---

## 5. Architecture

### Part 1 — Single-document pipeline

```
  DOC (PDF / image)
       │
       ▼
 ┌──── LangGraph pipeline · checkpointed after every node ─────────────────────┐
 │  setup (doc-type hint + load rules) → extractor → validator → router        │
 │                                                              → persist        │
 └──────────────────────────────┬──────────────────────────────────────────────┘
                                 │
        ┌────────────┬───────────┴────────────┐
        ▼            ▼                         ▼
   AUTO-APPROVE   FLAG REVIEW           DRAFT AMENDMENT
   (all match)    (≥1 uncertain)        (≥1 mismatch)
        └────────────┴───────────┬────────────┘
                                 ▼
                      SQLite store  +  NL query
```

### Part 2 — CG multi-document email loop

```
  SU email  (a folder in inbox/incoming/, with N attachments + email.json)
       │
       ▼  [ CG clicks "Process Shipment" ]
  node_ingest_email     → mint trace_id · log email_received · load attachments
       │
       ▼
  node_extract_all      → extractor once per attachment (ThreadPool) → list[ExtractedDoc]
       │
       ▼
  node_validate_all     → validator per doc → list[ValidationResult]
       │
       ▼
  node_cross_validate   → DETERMINISTIC cross-doc check → CrossDocResult
       │                   (consignee_name · hs_code · invoice_number must agree
       │                    across all docs; required fields present per doc type)
       ▼
  node_route_shipment   → cross-doc gate + Part 1 trust gate → Decision + draft email
       │                   inconsistent  ⇒  draft_amendment  (CANNOT map to approve)
       ▼
  node_persist_shipment → shipments · fields(+doc_type) · cross_doc_checks · decisions · audit_log
       │
       ▼
  node_await_cg         → status = pending_cg_review   ◀── PIPELINE STOPS HERE
       │
       ▼  [ CG reviews Verification + Discrepancy, edits the draft, clicks Send ]
  audit_log: reply_sent → shipment folder moves to inbox/processed/
       │
       ▼
  NL query:  "Show pending review for Acme Logistics"
```

The CG pipeline is a **7-node LangGraph DAG** with a typed state object; the Part 1 pipeline is a **6-node DAG**. Every node writes a checkpoint to SQLite on completion, so `resume(trace_id)` rebuilds the partial graph from the next uncompleted node.

---

## 6. The Five Trust Guarantees (USP)

These are the design decisions that distinguish this build. Each maps to a specific file and function so it can be verified, not just claimed.

**1 — Hallucination is blocked structurally, not by prompt-begging.**
`domain/models.py · FieldValue.cap_confidence_without_snippet` caps confidence at **≤ 0.3** for any field the model returns without a verbatim `source_snippet`. The validator then turns anything **< 0.85** into `uncertain`, and the router blocks auto-approve on *any* uncertain field. A field the model invented therefore has no evidence → it can never clear the gate. Silent approval is made impossible by construction.

**2 — The decision is deterministic; the LLM is not the judge.**
`agents/validator.py` checks **7 of 8 fields** against `config/rules.yaml` with pure-Python match types (`exact_ci`, `prefix`, `enum`, `numeric_tolerance`, `regex`); the LLM is used only for vision extraction and one semantic goods-description check. `agents/router.py · route()/_classify()` is plain code: all-match → approve, any uncertain → flag, any mismatch → amend. Same input → same verdict, every run. *This is the answer to "why three agents, not one prompt."*

**3 — The cross-document gate has no bypass.**
`agents/cross_validator.py` deterministically compares the three shared fields across all attachments and checks required fields per document type. `agents/router.py · route_shipment()` forces `draft_amendment` whenever `all_consistent == False` — even if every per-document verdict individually passes. Values are keyed `doc_type[i]` so two documents of the same type cannot overwrite each other (a real collision bug, now fixed and covered by a test).

**4 — Crash-safe, without re-billing the expensive call.**
`infrastructure/database.py · save_checkpoint()/resume()` writes a checkpoint at the *end* of each node. `resume(trace_id)` skips completed nodes, so a crash after extraction does not re-run the GPT-4o vision call. **Honest limit:** a crash *inside* a node, after its LLM call but before its checkpoint, re-runs that one node — stated plainly rather than over-claimed.

**5 — Explainable and queryable end-to-end.**
Every field keeps its snippet and page, every verdict carries a reason string, every decision carries reasoning text — all persisted to SQLite. `query/query.py` turns plain-English questions into **SELECT-only** SQL (any non-SELECT statement is rejected) and answers from the real rows, so any dispute traces back to the exact document text.

---

## 7. Project Structure

```
nova-poc/
├── nova/
│   ├── domain/
│   │   └── models.py          # Pydantic v2: FieldValue, ExtractedDoc, ValidationResult,
│   │   │                      #   CrossDocResult, Decision, PipelineState, ShipmentState
│   ├── infrastructure/
│   │   ├── database.py        # SQLite: shipments · fields · decisions · audit_log ·
│   │   │                      #   checkpoints · cross_doc_checks  (+ save_checkpoint/resume)
│   │   └── llm.py             # ALL OpenAI calls funnel through here (gpt-4o + gpt-4o-mini)
│   ├── pipeline/
│   │   ├── pipeline.py        # Part 1: 6-node LangGraph DAG + checkpoint + resume()
│   │   ├── pipeline_cg.py     # Part 2: 7-node CG DAG, terminates at node_await_cg
│   │   └── multidoc.py        # extract_all(): Part 1 extractor per attachment (ThreadPool)
│   ├── query/
│   │   └── query.py           # NL → function-call → SELECT-only SQL → grounded answer
│   ├── inbox/
│   │   └── watcher.py         # Mock SU inbox: poll_once · mark_processing · mark_processed
│   └── agents/
│       ├── extractor.py       # GPT-4o vision → ExtractedDoc with per-field evidence
│       ├── validator.py       # 6 deterministic match types + 1 semantic check
│       ├── router.py          # Trust gate + route_shipment() (cross-doc aware) + draft emails
│       └── cross_validator.py # Deterministic cross-doc consistency + required-field check
├── config/
│   └── rules.yaml             # One customer's rule set — kept OUT of prompts
├── app.py                     # Part 1 Streamlit UI (single-doc)
├── app_cg.py                  # Part 2 CG Operations UI — 4 states per shipment
├── inbox/
│   ├── incoming/              # SU "emails" awaiting processing (folder = one shipment)
│   ├── processing/            # Lock state while a pipeline run is in flight
│   └── processed/             # Archived after the CG operator sends a reply
├── docs/
│   ├── implementation.md      # Full technical write-up (architecture, failure modes,
│   │                          #   cost, latency, observability, what-I'd-do-with-a-week)
│   └── queries.md             # Sample NL queries with the real SQL + live outputs
├── evals/
│   ├── gold.csv               # Labelled extraction set (~88 field rows)
│   └── run_eval.py            # Per-field precision/recall + confidence calibration
├── samples/                   # Part 1 single-doc samples (clean_bol.pdf, messy_invoice.jpg, …)
├── scripts/
│   ├── generate_samples.py            # Part 1 samples
│   ├── generate_inbox_samples.py      # Part 2 inbox shipments
│   ├── generate_gold_samples.py       # Eval gold set
│   └── reset_inbox.py                 # Reproducible clean demo state (run before demos)
├── tests/unit/
│   ├── test_router_gate.py    # 13 Part 1 trust-gate tests
│   └── test_cross_doc.py      # 4 Part 2 cross-doc gate tests
├── pyproject.toml
├── requirements.txt
└── .env.example
```

---

## 8. Data Model & Storage

All verified output lands in a single SQLite database (`nova.db`) with six tables:

| Table | Holds |
|---|---|
| `shipments` | One row per shipment: trace_id, customer, status, timestamps |
| `fields` | One row per extracted field: value, confidence, source_snippet, page, **doc_type** |
| `decisions` | Router outcome per shipment: action, reasoning text |
| `cross_doc_checks` | Per shared-field consistency verdict with the per-doc values |
| `audit_log` | Append-only event trail: email_received → … → reply_sent |
| `checkpoints` | Per-node pipeline state for crash recovery |

Typed Pydantic v2 models gate every handoff between agents, so malformed LLM output **fails loud** at the boundary instead of silently propagating.

---

## 9. Running Each Piece (CLI)

```bash
# Part 1 single-doc pipeline on one document
PYTHONPATH=. python nova/pipeline/pipeline.py samples/clean_bol.pdf

# Part 2 CG pipeline against the inbox (headless)
PYTHONPATH=. python nova/pipeline/pipeline_cg.py

# Natural-language query
PYTHONPATH=. python nova/query/query.py "How many shipments were auto-approved?"
```

*(On Windows PowerShell, prefix with `$env:PYTHONPATH="."; ` and use backslashes.)*

---

## 10. Crash-Recovery Demo

```bash
PYTHONPATH=. python nova/pipeline/pipeline.py samples/clean_bol.pdf --crash
```

```
=== Nova Pipeline Demo ===
trace_id: <uuid>
--- Phase 1: run through extraction, then simulate a crash ---
[pipeline] Partial run complete at step=validator, cost=$0.0123
[CRASH] Pipeline crashed after extraction. Checkpoint saved at step=validator
--- Phase 2: resume from checkpoint ---
[pipeline] Resuming trace_id=<uuid> from step=validator
=== Resumed Pipeline Complete ===
Action: auto_approve   (or draft_amendment for a messy doc)
```

The resumed run does **not** re-call the GPT-4o extractor — it reads the checkpointed `ExtractedDoc` and continues from validation.

---

## 11. Evals & Tests

```bash
# Extraction eval: per-field precision/recall + calibration over the gold set
PYTHONPATH=. python evals/run_eval.py

# Unit tests — 17 total, all deterministic (no live LLM calls)
pytest tests/unit/ -v
```

- `tests/unit/test_router_gate.py` — 13 tests covering the Part 1 trust gate (approve / flag / amend boundaries, confidence thresholds).
- `tests/unit/test_cross_doc.py` — 4 tests covering the Part 2 cross-doc gate, including *"an inconsistent shipment cannot be auto-approved"* and the `doc_type[i]` collision case.

The eval gold set is synthetic and self-generated, so the calibration numbers are a sanity check on the pipeline wiring rather than a claim about real-world trade documents.

---

## 12. Natural-Language Query Layer

A non-engineer can ask plain-English questions over the verified store; the layer compiles them to **read-only** SQL (any non-SELECT is rejected) and answers from real rows.

```bash
PYTHONPATH=. python nova/query/query.py "Which fields had the most mismatches?"
PYTHONPATH=. python nova/query/query.py "Show me everything pending review for Acme Logistics"
```

See `docs/queries.md` for worked examples with the generated SQL and live output.

---

## 13. Stack & Why Each Choice

| Layer | Choice | Why |
|---|---|---|
| Orchestration | **LangGraph** | Explicit, checkpointable state machine; mirrors Nova's real orchestrator |
| Vision LLM | **GPT-4o** | Strongest field + evidence extraction from mixed PDF/scan input |
| Text LLM | **GPT-4o-mini** | Cheap and sufficient for validation helpers + NL→SQL |
| Schema | **Pydantic v2** | Typed handoffs; invalid model output fails loud at the boundary |
| Storage | **SQLite** | Laptop-runnable, zero-config. Prod path: ClickHouse |
| UI | **Streamlit** | One file, real state, no frontend build step |

---

## 14. POC Scope — What Is Intentionally Not Built

| Skipped here | Production path |
|---|---|
| Real IMAP/SMTP | Folder-based mock inbox; prod polls Gmail API or Exchange |
| Per-customer auth | One `rules.yaml`; prod: per-customer rule packs behind OpenFGA |
| Cost gateway | Route through LiteLLM for budget caps + model routing |
| Hosted tracing | trace_id + structured JSON logs here; Langfuse/LangSmith in prod |
| Analytical store | SQLite on a laptop; ClickHouse for Nova's prod analytics |
| Feedback loop | CG edits are logged but not yet fed back to improve extraction rules |

These are deliberate boundaries, not gaps — the trigger, multi-doc handling, cross-doc consistency, human-gated send, and query hand-off (the things being evaluated) are all fully wired.

---

## 15. Cost, Latency & Observability Notes

- **Cost per document** is dominated by the single GPT-4o vision extraction call (roughly a few cents per page); validation, routing, and NL query run on GPT-4o-mini or pure Python and are negligible by comparison. The control lever is the extractor: cache by document hash, down-route clean machine-generated PDFs to text extraction, and reserve vision for scans.
- **Latency** — the slowest hop is also the vision extraction. Part 2 runs attachments through a `ThreadPoolExecutor`, so a 3-document shipment extracts roughly in the time of its slowest single document rather than the sum.
- **Observability** — every shipment carries a `trace_id` threaded through the `audit_log` (email_received → extracted → validated → routed → reply_sent). In production this maps onto a per-customer dashboard keyed on trace_id; see `docs/implementation.md` for the full trace-and-dashboard story.

---

## 16. Troubleshooting

| Symptom | Fix |
|---|---|
| `OPENAI_API_KEY` not found | Copy `.env.example` → `.env` and set the key; restart the app. |
| Streamlit shows no shipments | Run `python scripts/reset_inbox.py` to (re)create the demo inbox. |
| `ModuleNotFoundError: nova` | Run from the `nova-poc/` directory, or set `PYTHONPATH=.`. |
| Inbox looks stale after a demo | `python scripts/reset_inbox.py` returns to the clean two-shipment state. |
| Want a fresh database | Delete `nova.db`; it is recreated on the next run. |

---

## 17. Submission Checklist

### Part 1
- [x] **Extractor agent** — GPT-4o vision, 8 fields, `source_snippet` required per field
- [x] **Validator agent** — 6 match types (`exact_ci`, `prefix`, `enum`, `numeric_tolerance`, `regex`, `semantic`), rules in `config/rules.yaml`
- [x] **Router agent** — deterministic trust gate (all-match → approve, uncertain → flag, mismatch → amend) with LLM-drafted amendment email
- [x] **Storage** — SQLite 6-table schema, `persist_results()`, append-only `audit_log`
- [x] **NL query** — function-calling → SELECT-only SQL → grounded answer
- [x] **Crash recovery** — `save_checkpoint()` after every node, `resume(trace_id)` rebuilds the partial graph
- [x] **LangGraph pipeline** — 6-node DAG, typed `PipelineState`, checkpointed
- [x] **Technical write-up** — `docs/implementation.md`
- [x] **Sample documents** — `samples/clean_bol.pdf`, `samples/messy_invoice.jpg`, + extras
- [x] **Unit tests** — `tests/unit/test_router_gate.py` (13)
- [x] **Eval harness** — `evals/run_eval.py` + `evals/gold.csv`
- [x] **NL query examples** — `docs/queries.md`
- [ ] **Demo video (2–3 min)** — clean_bol.pdf → auto_approve; messy_invoice.jpg → draft_amendment + crash-recovery

### Part 2
- [x] **CG Operations UI** — `app_cg.py`, 4 states per shipment (Incoming → Verification → Discrepancy → Draft Reply)
- [x] **Trigger** — folder-based mock SU inbox, `nova/inbox/watcher.py`
- [x] **Multi-doc extraction** — `nova/pipeline/multidoc.py` (ThreadPool, per-doc provenance)
- [x] **Cross-document consistency** — `nova/agents/cross_validator.py` (3 shared fields + per-doc-type required fields, deterministic)
- [x] **CG pipeline** — `nova/pipeline/pipeline_cg.py` (7 nodes, terminates at `node_await_cg`)
- [x] **Agent never auto-sends** — pipeline halts at `node_await_cg`; Send requires a CG click
- [x] **Sample shipments** — clean + HS-mismatch pair via `reset_inbox.py`, plus a multi-customer set in `inbox/incoming/`
- [x] **Unit tests** — `tests/unit/test_cross_doc.py` (4)
- [x] **Inbox reset script** — `scripts/reset_inbox.py`
- [x] **PRD** — single page (submitted separately as PDF)
- [ ] **Demo video (2 min)** — ACME_001 trigger → verify → approve → send; ACME_002 trigger → discrepancy → draft → edit → send

---

*Built for the GoComet Nova Full-Stack AI Engineer Day-at-Work assignment.*
