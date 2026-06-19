# Nova POC — Governed Trade Document Validation Pipeline

> *"Nova doesn't get to be a confident liar. A wrongly auto-approved HS code = customs hold + contract penalty."*

A POC-scale miniature of GoComet's Nova platform: multi-agent, evidence-grounded, crash-recoverable document validation pipeline with a CG operator UI.

**Part 1** — single-doc pipeline (extractor → validator → router → persist → NL query).
**Part 2** — adds the SU-email trigger, multi-document handling, cross-document consistency, and a CG operator UI with 4 states (Incoming → Verification → Discrepancy → Draft Reply).

---

## Quick Start — Part 2 (CG Operations UI)

```bash
# 1. Generate inbox sample PDFs (BOL + Invoice + Packing List for 2 shipments)
python scripts/generate_inbox_samples.py

# 2. Add your OpenAI key to .env
copy .env.example .env    # edit and set OPENAI_API_KEY=sk-...

# 3. Launch the CG UI
streamlit run app_cg.py
```

Open http://localhost:8501 in your browser.

**Demo flow:**
1. Inbox tab — two shipments appear (ACME_001 clean, ACME_002 with HS code mismatch)
2. Click **ACME_001** → Select → **Process Shipment** — pipeline fires (extraction + validation + cross-check + routing)
3. **Verification Result** tab — per-doc field table + cross-doc consistency strip (all green)
4. Click **ACME_002** → Select → **Process Shipment**
5. **Discrepancy Detail** tab — `hs_code` flagged as CROSS-DOC INCONSISTENT (BOL: 8471.30, INVOICE: 9999.99)
6. **Draft Reply** tab — pre-filled amendment email, edit it, click **Send (mock)** — folder moves to processed/
7. NL Query tab — *"Show me everything pending review for Acme Logistics"*

> **The agent never auto-sends.** Only the CG operator's Send click dispatches a reply.

---

## Setup (Mac / Linux / Windows)

```bash
# 1. Enter the project directory
cd nova-poc

# 2. Create a Python 3.11 virtual environment
python -m venv .venv

# 3. Activate it
source .venv/bin/activate          # Mac / Linux
# .venv\Scripts\activate           # Windows PowerShell

# 4. Install dependencies (~2 GB, takes ~2 min)
pip install --no-cache-dir -r requirements.txt

# 5. Add your OpenAI API key
cp .env.example .env               # Mac / Linux
# copy .env.example .env           # Windows
# Edit .env: OPENAI_API_KEY=sk-...

# 6. Generate synthetic sample documents
python scripts/generate_samples.py
python scripts/generate_inbox_samples.py   # Part 2 inbox samples

# 7. Run the app
streamlit run app.py               # Part 1 single-doc pipeline
# streamlit run app_cg.py          # Part 2 CG operations UI
```

Open http://localhost:8501 in your browser.

> **Windows with low C: drive space:** create the venv on another drive:
> `"C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python311\python.exe" -m venv D:\nova_venv`
> then activate with `D:\nova_venv\Scripts\activate` and use `D:\nova_venv\Scripts\pip` / `D:\nova_venv\Scripts\streamlit` throughout.

---

## Project Structure

```
nova-poc/
├── nova/
│   ├── domain/
│   │   └── models.py          # Pydantic types: FieldValue, ExtractedDoc, CrossDocResult, PipelineState…
│   ├── infrastructure/
│   │   ├── database.py        # SQLite: shipments, fields, decisions, audit_log, cross_doc_checks, checkpoints
│   │   └── llm.py             # ALL OpenAI calls go here (gpt-4o + gpt-4o-mini)
│   ├── pipeline/
│   │   ├── pipeline.py        # Part 1: LangGraph single-doc pipeline + checkpoint + resume()
│   │   ├── pipeline_cg.py     # Part 2: CG pipeline (ingest→extract_all→validate_all→cross_validate→route→persist→await_cg)
│   │   └── multidoc.py        # extract_all(): run Part 1 extractor once per attachment
│   ├── query/
│   │   └── query.py           # NL → read-only SQL → grounded answer (schema extended for Part 2)
│   ├── inbox/
│   │   └── watcher.py         # Mock SU inbox: poll_once, mark_processing, mark_processed, save_result
│   └── agents/
│       ├── extractor.py       # GPT-4o vision → ExtractedDoc with evidence (unchanged)
│       ├── validator.py       # Deterministic + semantic verdicts (unchanged)
│       ├── router.py          # Trust gate + route_shipment() (Part 2: cross-doc aware)
│       └── cross_validator.py # Deterministic cross-doc consistency check (Part 2)
├── config/
│   └── rules.yaml             # Customer rule set (not in prompts)
├── app.py                     # Part 1 Streamlit UI (single-doc)
├── app_cg.py                  # Part 2 CG Operations UI — 4 states per shipment
├── inbox/
│   ├── incoming/
│   │   ├── shipment_ACME_001/ # Clean 3-doc set (BOL + Invoice + Packing List — all consistent)
│   │   └── shipment_ACME_002/ # HS code mismatch: BOL=8471.30, INVOICE=9999.99
│   ├── processing/            # Folder moved here while pipeline runs (lock)
│   └── processed/             # Folder moved here after pipeline + CG sends reply
├── docs/
│   ├── PRD.pdf                    # Part 1 PRD (3-5 pages) — agents, trust gate, query layer
│   ├── PRD_part2.md               # Part 2 PRD (1 page) — CG UI module, 4 states, 5-step wiring
│   ├── queries.md                 # 4 sample NL queries with real SQL + live outputs
│   └── implementation.md          # Full technical write-up (20 sections)
├── evals/
│   ├── gold.csv               # 11 labelled docs, ~88 rows
│   └── run_eval.py            # per-field P/R + calibration
├── samples/                   # Part 1 single-doc samples (path locked by generate scripts)
├── scripts/
│   ├── generate_samples.py
│   ├── generate_extra_samples.py
│   ├── generate_gold_samples.py
│   ├── generate_inbox_samples.py  # Part 2: creates BOL+Invoice+PackingList for both shipments
│   └── generate_prd.py            # Generates PRD.pdf → docs/PRD.pdf
├── tests/
│   └── unit/
│       ├── test_router_gate.py    # 13 Part 1 trust-gate tests
│       └── test_cross_doc.py     # 4 Part 2 cross-doc gate tests
├── pyproject.toml             # Project metadata and packaging
└── .env.example               # Environment variable template
```

---

## Architecture

### Part 1 — Single-doc pipeline
```
  DOC (PDF/img)
       │
       ▼
 ┌──── LangGraph pipeline (checkpointed per node) ────────────────────────────┐
 │  setup(hint+load rules) → extractor → validator → router → persist         │
 └──────────────────────────────┬─────────────────────────────────────────────┘
                                 │
        ┌────────────┬───────────┴────────────┐
        ▼            ▼                         ▼
   AUTO-APPROVE  FLAG REVIEW            DRAFT AMENDMENT
   (all pass)    (≥1 uncertain)        (≥1 mismatch)
        └────────────┴───────────┬────────────┘
                                 ▼
                    SQLite store + NL query
```

### Part 2 — CG multi-doc email loop
```
  SU email (folder in inbox/incoming/)
       │
       ▼  [CG clicks "Process Shipment"]
  node_ingest_email    → mint trace_id · log email_received · load attachments
       │
       ▼
  node_extract_all     → extract() once per attachment → list[ExtractedDoc]
       │
       ▼
  node_validate_all    → validate() per doc → list[ValidationResult]
       │
       ▼
  node_cross_validate  → deterministic cross-doc check → CrossDocResult
       │                  (consignee_name · hs_code · invoice_number must agree)
       ▼
  node_route_shipment  → cross-doc gate + Part 1 trust gate → Decision + draft email
       │                  inconsistent → draft_amendment (CANNOT be silently approved)
       ▼
  node_persist_shipment → shipments · fields(+doc_type) · cross_doc_checks · decisions
       │
       ▼
  node_await_cg        → status = pending_cg_review ← PIPELINE STOPS HERE
       │
       ▼ [CG reviews Verification + Discrepancy tabs, edits draft, clicks Send]
  audit_log reply_sent → folder → inbox/processed/
       │
       ▼
  NL query: "Show pending review for Acme Logistics"
```

**Four design guarantees (Part 2):**
1. **No auto-send** — pipeline terminates at `node_await_cg`; only a human Send click dispatches.
2. **Cross-doc gate** — `all_consistent == False` forces `draft_amendment`; cannot map to approve.
3. **Per-attachment provenance** — each doc has its own `ExtractedDoc` with `doc_type`; no merging.
4. **Crash-safe** — checkpoint is written at the *end* of each node (after its LLM call), so `resume()` picks up at the next uncompleted node. A crash *within* a node before its checkpoint is written will re-run that node; a crash *after* a node checkpoints will not.

---

## Running the Pipeline

**Full run (UI):**
```bash
streamlit run app.py
# Tab 1: upload a PDF/image → Run Pipeline
# Tab 2: NL query box
```

**Full run (CLI):**
```bash
# Windows PowerShell:
$env:PYTHONPATH="."; D:\nova_venv\Scripts\python nova\pipeline\pipeline.py samples\clean_bol.pdf
# or with default .venv:
$env:PYTHONPATH="."; python nova\pipeline\pipeline.py samples\clean_bol.pdf
```

---

## Crash-Recovery Demo

```bash
# Run with a simulated mid-pipeline crash, then resume:
$env:PYTHONPATH="."; D:\nova_venv\Scripts\python nova\pipeline\pipeline.py samples\clean_bol.pdf --crash

# Output:
# === Nova Pipeline Demo ===
# trace_id: <uuid>
# --- Phase 1: Running pipeline through extraction, then simulating crash ---
# [pipeline] Partial run complete at step=validator, cost=$0.012345
# [CRASH] Pipeline crashed after extraction. Checkpoint saved at step=validator
# [pipeline] trace_id=<uuid> is checkpointed and recoverable.
# --- Phase 2: Resuming from checkpoint ---
# [pipeline] Resuming trace_id=<uuid> from step=validator
# === Resumed Pipeline Complete ===
# Action: auto_approve (or draft_amendment for messy doc)
```

---

## Run Evals

```bash
$env:PYTHONPATH="."; D:\nova_venv\Scripts\python evals\run_eval.py
```

Prints:
- Per-field extraction accuracy (precision/recall over gold set)
- Calibration report: does confidence bucket match actual accuracy?

---

## Run Tests

```bash
D:\nova_venv\Scripts\pytest tests/unit/ -v
# or with default .venv:
# pytest tests/unit/ -v
```

All 17 tests are deterministic (no LLM calls — router logic mocked where needed).

---

## NL Query Examples

```bash
$env:PYTHONPATH="."; D:\nova_venv\Scripts\python nova\query\query.py "How many shipments were auto-approved?"
$env:PYTHONPATH="."; D:\nova_venv\Scripts\python nova\query\query.py "Which fields had the most mismatches?"
```

See `docs/queries.md` for 4 sample questions with real outputs.

---

## What's NOT built (POC scope — intentional)

| Skipped | Prod path |
|---|---|
| Real IMAP/SMTP | Mock folder-based inbox; prod would poll via Gmail API or Exchange |
| Per-customer auth | One `rules.yaml`; prod: per-customer rule packs via OpenFGA |
| LiteLLM cost gateway | Route through LiteLLM for budget caps + model routing |
| Langfuse tracing | trace_id + JSON logs is enough for POC; Langfuse in prod |
| ClickHouse analytics | SQLite runs on a laptop; ClickHouse is Nova's prod analytical store |
| Feedback/learning loop | CG edits logged but not fed back to improve extraction rules |

---

## Stack

| Layer | Choice | Why |
|---|---|---|
| Orchestration | LangGraph | Nova's actual orchestrator; explicit checkpointable state machine |
| Vision LLM | GPT-4o | Best field+evidence extraction |
| Text LLM | GPT-4o-mini | Cheap; enough for validation + NL query |
| Schema | Pydantic v2 | Typed handoffs; invalid LLM output fails loud |
| Storage | SQLite | Laptop-runnable. Prod: ClickHouse |
| UI | Streamlit | One file, real state, zero frontend overhead |

---

## Submission Checklist

### Part 1
- [x] Extractor agent — GPT-4o vision, 8 fields, `source_snippet` required
- [x] Validator agent — 6 match types (exact_ci, prefix, enum, numeric_tolerance, regex, semantic), rules in `config/rules.yaml`
- [x] Router agent — deterministic trust gate (all-match→approve, uncertain→flag, mismatch→amend), amendment email via LLM
- [x] Storage — SQLite 6-table schema, `persist_results()`, `audit_log`
- [x] NL query — function-calling → SELECT-only SQL → grounded answer
- [x] Crash recovery — `save_checkpoint()` after every node, `resume(trace_id)` rebuilds partial graph
- [x] LangGraph pipeline — 5-node DAG, typed `PipelineState`, checkpointed
- [x] Part 1 PRD — `docs/PRD.pdf`
- [x] Technical write-up — `docs/implementation.md` (20 sections)
- [x] Sample documents — `samples/clean_bol.pdf`, `samples/messy_invoice.jpg` + 5 more
- [x] Unit tests — `tests/unit/test_router_gate.py` (13 tests)
- [x] Eval harness — `evals/run_eval.py` + `evals/gold.csv`
- [x] NL query examples — `docs/queries.md` (4 questions with real SQL + outputs)
- [ ] **Demo video (2-3 min)** — record: upload clean_bol.pdf → auto_approve; upload messy_invoice.jpg → draft_amendment + crash recovery demo

### Part 2
- [x] Part 2 PRD — `docs/PRD_part2.md`
- [x] CG Operations UI — `app_cg.py` with 4 states per shipment
- [x] Multi-doc extraction — `nova/pipeline/multidoc.py` (ThreadPoolExecutor, per-doc provenance)
- [x] Cross-document consistency — `nova/agents/cross_validator.py` (deterministic, 3 shared fields + per-doc-type required fields)
- [x] CG pipeline — `nova/pipeline/pipeline_cg.py` (7 nodes, terminates at `node_await_cg`)
- [x] Agent never auto-sends — pipeline stops at `node_await_cg`, Send requires CG click
- [x] 2 sample shipments — `inbox/incoming/shipment_ACME_001` (clean), `shipment_ACME_002` (HS mismatch)
- [x] Mock SU inbox — `nova/inbox/watcher.py` folder-based with phase tracking
- [x] Unit tests — `tests/unit/test_cross_doc.py` (4 cross-doc gate tests)
- [x] Inbox reset script — `scripts/reset_inbox.py` (reproducible clean demo state)
- [x] Combined implementation write-up — `docs/implementation.md` (26 sections, Part 1 + Part 2, design decisions)
- [ ] **Demo video (2 min)** — record: ACME_001 trigger→verify→approve→send; ACME_002 trigger→discrepancy→draft→edit→send
