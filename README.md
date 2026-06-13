# Nova POC — Governed Trade Document Validation Pipeline

> *"Nova doesn't get to be a confident liar. A wrongly auto-approved HS code = customs hold + contract penalty."*

A POC-scale miniature of GoComet's Nova platform: three-agent, evidence-grounded, crash-recoverable document validation pipeline.

---

## 60-Second Setup

> **Note (Windows):** If C: drive is low on space, create the venv on another drive (e.g., D:).

```bash
# 1. Enter the project directory
cd nova-poc

# 2. Create a Python 3.11 virtual environment
#    Option A — default (requires ~2GB free on C:):
python -m venv .venv && .venv\Scripts\activate

#    Option B — venv on D: drive (if C: is full):
"C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python311\python.exe" -m venv D:\nova_venv

# 3. Install dependencies
D:\nova_venv\Scripts\pip install --no-cache-dir -r requirements.txt
# or from default .venv:
# pip install -r requirements.txt

# 4. Add your OpenAI API key
copy .env.example .env      # Windows
# Edit .env: OPENAI_API_KEY=sk-...

# 5. Generate synthetic sample documents
D:\nova_venv\Scripts\python scripts\generate_samples.py

# 6. (Optional) Generate extra samples for eval
D:\nova_venv\Scripts\python scripts\generate_extra_samples.py

# 7. Run the app
D:\nova_venv\Scripts\streamlit run app.py
# or with default venv: streamlit run app.py
```

Open http://localhost:8501 in your browser.

---

## Project Structure

```
nova-poc/
├── nova/
│   ├── domain/
│   │   └── models.py          # Pydantic typed contract (FieldValue, ExtractedDoc, PipelineState…)
│   ├── infrastructure/
│   │   ├── database.py        # SQLite: shipments, fields, decisions, audit_log, checkpoints
│   │   └── llm.py             # ALL OpenAI calls go here (gpt-4o + gpt-4o-mini)
│   ├── pipeline/
│   │   └── pipeline.py        # LangGraph 7-node graph + checkpoint + resume()
│   ├── query/
│   │   └── query.py           # NL → read-only SQL → grounded answer
│   └── agents/
│       ├── extractor.py       # GPT-4o vision → ExtractedDoc with evidence
│       ├── validator.py       # Deterministic + semantic verdicts
│       └── router.py          # Trust gate → Decision + amendment email
├── config/
│   └── rules.yaml             # Customer rule set (not in prompts)
├── app.py                     # Streamlit UI
├── evals/
│   ├── gold.csv               # 11 labelled docs, ~88 rows (4 unique source files)
│   └── run_eval.py            # per-field P/R + calibration
├── samples/
│   ├── clean_bol.pdf                  # Valid BOL (auto-approves)
│   ├── messy_invoice.jpg              # Invoice with HS code mismatch 9999.99 (triggers amendment)
│   ├── packing_list_001.pdf           # Packing list (EXW, semiconductor ICs)
│   ├── commercial_invoice_002.pdf     # Invoice EXW Hamburg (optical instruments)
│   ├── bol_002.pdf                    # BOL NINGBO→PORT KLANG (EXW, PCBs, ~975 kg)
│   ├── invoice_003.pdf                # Invoice HS 7326.90 mismatch (triggers amendment)
│   └── packing_list_002.pdf           # Packing list GUANGZHOU→SINGAPORE (CIF, ICs)
├── scripts/
│   ├── generate_samples.py            # Creates clean_bol.pdf + messy_invoice.jpg
│   ├── generate_extra_samples.py      # Creates packing_list_001 + commercial_invoice_002
│   └── generate_gold_samples.py       # Creates bol_002 + invoice_003 + packing_list_002
├── tests/
│   └── unit/
│       └── test_router_gate.py    # Deterministic trust-gate tests
└── queries.md                 # Sample NL queries + outputs
```

---

## Architecture

```
  DOC (PDF/img)
       │
       ▼
 ┌──── LangGraph pipeline (checkpointed per node) ──────────────────────────────┐
 │  scope → context(load rules) → schema_route → extractor → validator →        │
 │  router → persist                                                             │
 └──────────────────────────────┬───────────────────────────────────────────────┘
                                 │
        ┌────────────┬───────────┴────────────┐
        ▼            ▼                         ▼
   AUTO-APPROVE  FLAG REVIEW            DRAFT AMENDMENT
   (all pass)    (≥1 uncertain)        (≥1 mismatch)
        └────────────┴───────────┬────────────┘
                                 ▼
                    SQLite store + audit_log
                                 ▼
                    NL query (read-only SQL → grounded answer)

Cross-cutting: trace_id per shipment · Pydantic typed handoffs · GPT-4o / GPT-4o-mini
```

**Three differentiators:**
1. **Evidence grounding** — every field has `source_snippet + source_page`. No snippet → confidence capped ≤ 0.3. Hallucination is structurally hard, not prompt-hopeful.
2. **Crash recovery** — `PipelineState` checkpointed to SQLite after every node. `resume(trace_id)` reloads and continues.
3. **Eval harness** — gold set → per-field precision/recall + calibration (does 0.9 confidence ≈ 90% right?).

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

All tests are deterministic (no LLM calls — router logic mocked where needed).

---

## NL Query Examples

```bash
$env:PYTHONPATH="."; D:\nova_venv\Scripts\python nova\query\query.py "How many shipments were auto-approved?"
$env:PYTHONPATH="."; D:\nova_venv\Scripts\python nova\query\query.py "Which fields had the most mismatches?"
```

See `queries.md` for 4 sample questions with real outputs.

---

## What's NOT built (POC scope — intentional)

| Skipped | Prod path |
|---|---|
| LiteLLM cost gateway | Route through LiteLLM for budget caps + model routing |
| Langfuse tracing | trace_id + JSON logs is enough for one shipment; Langfuse in prod |
| Multi-tenant isolation | One customer's rules in one YAML; OpenFGA + per-tenant packs in prod |
| ClickHouse analytics | SQLite runs on a laptop; ClickHouse is Nova's prod analytical store |

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
