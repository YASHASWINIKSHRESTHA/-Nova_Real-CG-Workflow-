# Nova POC — Complete Implementation Document (Part 1 + Part 2)

## Table of Contents

**Part 1 — Single-Doc Pipeline**
1. [Project Purpose & Problem Statement](#1-project-purpose--problem-statement)
2. [High-Level Architecture](#2-high-level-architecture)
3. [Technology Stack Choices & Rationale](#3-technology-stack-choices--rationale)
4. [Production Folder Structure & SOLID Principles](#4-production-folder-structure--solid-principles)
5. [Domain Layer — Models](#5-domain-layer--models)
6. [Infrastructure Layer — LLM Client](#6-infrastructure-layer--llm-client)
7. [Infrastructure Layer — Database](#7-infrastructure-layer--database)
8. [Agent Layer — Extractor](#8-agent-layer--extractor)
9. [Agent Layer — Validator](#9-agent-layer--validator)
10. [Agent Layer — Router](#10-agent-layer--router)
11. [Pipeline Layer — LangGraph Orchestration](#11-pipeline-layer--langgraph-orchestration)
12. [Query Layer — Natural Language to SQL](#12-query-layer--natural-language-to-sql)
13. [Configuration — rules.yaml](#13-configuration--rulesyaml)
14. [Crash Recovery & Checkpointing](#14-crash-recovery--checkpointing)

**Part 2 — CG Operations Module**
15. [Part 2 Overview — CG UI Module](#15-part-2-overview--cg-ui-module)
16. [Part 2 — CG Pipeline (7 Nodes)](#16-part-2--cg-pipeline-7-nodes)
17. [Part 2 — Multi-Document Extraction](#17-part-2--multi-document-extraction)
18. [Part 2 — Cross-Document Validation](#18-part-2--cross-document-validation)
19. [Part 2 — CG Operations UI](#19-part-2--cg-operations-ui)
20. [Part 2 — Mock SU Inbox](#20-part-2--mock-su-inbox)

**Testing & Evaluation**
21. [Streamlit UIs (app.py and app_cg.py)](#21-streamlit-uis)
22. [Testing Strategy](#22-testing-strategy)
23. [Evaluation Harness](#23-evaluation-harness)

**Architecture**
24. [End-to-End Data Flow](#24-end-to-end-data-flow)
25. [Design Decisions & Known Limitations](#25-design-decisions--known-limitations)
26. [What Would Change in Production](#26-what-would-change-in-production)

---

## 1. Project Purpose & Problem Statement

### What GoComet Nova Does

GoComet is a freight intelligence platform. One of its core real-world workflows is **trade document validation** — when a shipment is created, suppliers submit documents like Bills of Lading (BOL), Commercial Invoices, and Packing Lists. These documents must be validated against the customer's contracted rules before the shipment can proceed.

This is currently a manual, slow, error-prone process. A human reviewer opens each document, checks each field (consignee name, HS code, port of loading, incoterms, etc.) against what the customer's contract says it should be, flags mismatches, and either approves or sends an amendment request back to the supplier.

### What This POC Demonstrates

This project is a **proof-of-concept miniature of Nova**, GoComet's real platform, built across two parts:

**Part 1** automates the core review loop for a single document:
1. **Extract** — use a vision LLM to read the document and extract 8 key trade fields, with confidence score and verbatim source snippet for every field
2. **Validate** — check each extracted field against customer rules (in YAML, not in prompts)
3. **Route** — apply a deterministic trust gate: auto-approve, flag for human review, or draft an amendment email
4. **Persist** — record everything to SQLite with a full audit trail

**Part 2** adds the supplier email loop and a structured CG operator UI:
1. **Ingest** — a mock SU email lands in a folder-based inbox
2. **Multi-doc extraction** — extract from each attachment in parallel (BOL, Invoice, Packing List)
3. **Cross-doc validation** — deterministic consistency check across all attachments
4. **CG operator UI** — structured 4-state interface (Incoming → Verification → Discrepancy → Draft Reply)
5. **Human-in-the-loop** — the agent NEVER auto-dispatches; only a CG click sends the reply

The core thesis that must never be violated:
- Every field carries `value + confidence + source_snippet + source_page` — no claim without evidence
- If there is no source snippet, confidence is capped at 0.3 — the LLM cannot claim certainty it cannot point to
- The router never silently approves — it always explains why
- Rules live in `config/rules.yaml`, never embedded in prompts
- The pipeline is checkpointed after every node — crash recovery from any point

---

## 2. High-Level Architecture

### Part 1 — Single-Doc Pipeline

```
User (browser)
     │
     ▼
app.py  ─── Streamlit UI (Pipeline Runner tab, NL Query tab)
     │
     ├──► nova/pipeline/pipeline.py  ─── LangGraph 7-node DAG
     │         │
     │         ├── node_scope        ─── detect doc type from filename
     │         ├── node_context      ─── load rules.yaml
     │         ├── node_schema_route ─── confirm 8-field schema
     │         ├── node_extractor    ─── GPT-4o vision → ExtractedDoc
     │         ├── node_validator    ─── deterministic + GPT-4o-mini
     │         ├── node_router       ─── trust gate + amendment email
     │         └── node_persist      ─── SQLite write + audit_log
     │
     └──► nova/query/query.py  ─── NL → GPT-4o-mini function-calling → SELECT → answer
```

### Part 2 — CG Multi-Doc Email Loop

```
SU email (folder in inbox/incoming/)
     │
     ▼  [CG clicks "Process Shipment"]
app_cg.py  ─── Streamlit 4-state CG Operations UI
     │
     └──► nova/pipeline/pipeline_cg.py  ─── LangGraph 7-node CG DAG
               │
               ├── node_ingest_email    ─── mint trace_id · log email_received · load attachments
               ├── node_extract_all     ─── extract() per attachment via ThreadPoolExecutor
               ├── node_validate_all    ─── validate() per doc
               ├── node_cross_validate  ─── deterministic cross-doc check (3 shared fields)
               ├── node_route_shipment  ─── cross-doc gate + Part 1 trust gate → Decision + draft
               ├── node_persist_shipment── shipments · fields(+doc_type) · cross_doc_checks · decisions
               └── node_await_cg        ─── status=pending_cg_review ← PIPELINE STOPS HERE

     [CG reviews Verification/Discrepancy/Draft tabs, clicks "Send (mock)"]
               │
               └── audit_log reply_sent → folder → inbox/processed/
```

---

## 3. Technology Stack Choices & Rationale

### Python 3.11
The minimum version that ships `tomllib` in stdlib, has full `match/case` support, and significantly improved `asyncio`. All libraries in this stack (LangGraph, Pydantic v2, PyMuPDF) have first-class 3.11 support with no known issues.

### LangGraph (not plain LangChain)
LangGraph is a graph-based orchestration framework specifically designed for **stateful, multi-agent workflows**. Key reasons over alternatives:

- **State machine semantics** — a `StateGraph` with named nodes and edges is the right mental model for a pipeline with distinct stages. Plain function calls don't enforce stage ordering or make the DAG visible.
- **Type-safe state passing** — each node receives the full pipeline state as a dict, processes it, and returns the updated dict. The state is always `PipelineState`, so there are no silent field drops between stages.
- **Built-in interrupt/resume** — LangGraph is designed for exactly the checkpoint-and-resume pattern this pipeline uses.
- **LangSmith auto-instrumentation** — every node and LLM call is automatically traced to LangSmith when env vars are set.

Why not Prefect, Airflow, or Celery? Those are designed for data pipelines with retries, scheduling, and distributed workers — overkill for a single-request, synchronous, per-document pipeline on a laptop.

### OpenAI API (direct, not via LangChain)
All LLM calls go through `nova/infrastructure/llm.py`, talking directly to the OpenAI API:
- **No abstraction layer** — direct API calls mean you see exactly what's sent and received
- **Cost tracking** — the API response includes `usage.prompt_tokens` and `usage.completion_tokens`; we compute cost per call and accumulate it in `PipelineState.cost_usd`
- **Two models for two purposes** — `gpt-4o` (vision) for extraction; `gpt-4o-mini` (text) for validation semantic check and amendment email

### Pydantic v2
- **Type enforcement at the boundary** — LLM JSON goes straight into `ExtractedDoc(**data)`; bad output fails loud
- **Model validators** — `cap_confidence_without_snippet` on `FieldValue` enforces the core thesis at the type level
- **JSON serialization** — `model_dump_json()` makes checkpoint serialization trivial

### SQLite (via stdlib `sqlite3`)
Zero infrastructure, ACID guarantees, single-writer model matches Streamlit's single-user model. Production: replace `database.py` with PostgreSQL-backed module; all agents unaffected.

### Streamlit
Fastest path from Python logic to a running web interface. No HTML, no JavaScript, no REST API, no frontend build step.

### PyMuPDF (`fitz`)
Used to render PDF pages to PNG images in memory before sending to the vision model. PDFs cannot be sent directly to GPT-4o — they must be rasterized. PyMuPDF is the fastest pure-Python PDF renderer.

---

## 4. Production Folder Structure & SOLID Principles

### SOLID Applied to Folder Structure

**Single Responsibility Principle (S)**
Every sub-package has exactly one reason to change:
- `nova/domain/` — when the business data model changes
- `nova/agents/` — when the AI logic for extraction, validation, routing, or cross-validation changes
- `nova/infrastructure/` — when the external systems change (swap SQLite for Postgres, swap OpenAI)
- `nova/pipeline/` — when the orchestration DAG changes
- `nova/query/` — when the NL querying capability changes
- `nova/inbox/` — when the SU inbox mechanism changes (mock folder → real IMAP)
- `config/` — when customer rules change

**Open/Closed Principle (O)**
Adding a new agent (say, a language detector) means adding one file to `nova/agents/` and one node to the pipeline. Nothing else changes. Adding PostgreSQL support means adding `nova/infrastructure/postgres.py` without touching any agent.

**Liskov Substitution Principle (L)**
`nova/domain/models.py` has zero imports from `nova/infrastructure/`. You can swap the database or LLM provider and the domain models remain valid.

**Interface Segregation Principle (I)**
`database.py` and `llm.py` are separate modules. An agent that only calls the LLM does not get pulled into the database interface.

**Dependency Inversion Principle (D)**
High-level modules (`pipeline`, `agents`) depend on abstractions (`domain.models`) not on concrete infrastructure. Agents have no knowledge of how data is persisted.

---

## 5. Domain Layer — Models

**File:** `nova/domain/models.py`

### FieldValue — Atomic Evidence Unit

```python
class FieldValue(BaseModel):
    value: Optional[str]
    confidence: float  # 0.0–1.0
    source_snippet: Optional[str]
    source_page: Optional[int]

    @model_validator(mode="after")
    def cap_confidence_without_snippet(self):
        if self.source_snippet is None and self.confidence > 0.3:
            self.confidence = 0.3
```

The critical validator enforces the core architectural thesis at the type level: an LLM cannot assign itself confidence above 30% on a field it cannot point to in the document. The cap of 0.3 means the router will always see it as "uncertain" (auto-approve threshold is 0.85), preventing silent hallucination approvals.

### ExtractedDoc
Contains eight `FieldValue` fields plus a `doc_type` string. The `doc_type` is critical in Part 2: it is the label applied by the extractor and used by the cross-validator to determine which required-field check applies. `field_names()` and `get_field(name)` allow the validator to iterate over fields without a giant if/else chain.

### CrossDocVerdict and CrossDocResult (Part 2)
- `CrossDocVerdict` — one per shared field: `field`, `status` (consistent/inconsistent/insufficient_data), `values_by_doc` dict (doc label → value), `reason` string
- `CrossDocResult` — list of verdicts plus `all_consistent: bool`. If `all_consistent == False`, the CG pipeline route is forced to `draft_amendment` — there is no path from inconsistency to auto-approve.

### Decision
- `action`: one of `auto_approve`, `flag_for_review`, `draft_amendment`
- `reasoning`: always populated — the router never makes a silent decision
- `amendment_email`: only populated for `draft_amendment`

### PipelineState
The single state object flowing through every LangGraph node. Accumulates data as the pipeline progresses. Part 2 extends it with `email_meta`, `attachments`, `all_docs` (list of ExtractedDoc), `all_validations`, `cross_doc_result`, and `inbox_folder`.

---

## 6. Infrastructure Layer — LLM Client

**File:** `nova/infrastructure/llm.py`

All OpenAI API calls go through exactly two public functions: `call_vision` and `call_text`. A third utility `parse_json_response` handles stripping markdown fences from LLM outputs.

### Centralised LLM Gateway
By routing all LLM calls through one module: cost tracking is consistent, logging is consistent, model selection is explicit, and swapping providers means changing one file.

### call_vision
Takes a list of images (file paths or raw PNG bytes from the PDF renderer) and a prompt. Encodes each image as base64 data URI and sends them all in a single `user` message. Returns `(raw_text, cost_usd)`. Uses `detail: "high"` — trade documents have small text (HS codes, invoice numbers) that requires high resolution.

### call_text
Takes a prompt, optional system message, optional tool definitions, and optional tool_choice. The function-calling path: if `tools` are provided and the model responds with a tool call, the function returns the tool call arguments as a JSON string. This is how the NL query module gets structured SQL back.

### Cost Tracking
```python
_COST = {
    "gpt-4o":      {"input": 5.00,  "output": 15.00},
    "gpt-4o-mini": {"input": 0.15,  "output": 0.60},
}
cost = (tokens_in * rate_in + tokens_out * rate_out) / 1_000_000
```
Cost is returned from every LLM call and accumulated into `PipelineState.cost_usd`. After a full pipeline run, the UI shows the exact dollar cost.

---

## 7. Infrastructure Layer — Database

**File:** `nova/infrastructure/database.py`

Uses Python's built-in `sqlite3` module. The database file is `nova.db` at the project root.

### Why SQLite?
1. **Zero infrastructure** — no server process, no Docker, no connection string
2. **ACID guarantees** — SQLite's write-ahead logging ensures checkpoint saves are atomic
3. **Single-writer model is fine** — Streamlit is single-user, single-process

### Schema — Six Tables

**shipments** — one row per pipeline run. Tracks `trace_id`, document paths, final status.

**fields** — one row per extracted field per run. Stores value, confidence, source snippet, page, and (Part 2) `doc_type`. Every field decision is auditable.

**decisions** — one row per run. Stores action, reasoning text, amendment email if drafted.

**audit_log** — append-only event log. Columns: `trace_id`, `event_type`, `payload_json`, `created_at`. Every pipeline node writes a row when it completes.

**checkpoints** — one row per trace_id (upserted). Stores the full serialized `PipelineState` as JSON after each node. Enables crash recovery.

**cross_doc_checks** (Part 2) — one row per field per shipment. Stores the cross-doc verdict, status, values_by_doc JSON, and reason string. Queryable via the NL interface.

---

## 8. Agent Layer — Extractor

**File:** `nova/agents/extractor.py`

### PDF Rendering
PDFs cannot be sent directly to GPT-4o. They are rendered to PNG images in memory:
```python
def _render_pdf_pages(pdf_path: str, dpi: int = 150) -> list[bytes]:
    doc = fitz.open(pdf_path)
    for page in doc:
        pix = page.get_pixmap(matrix=fitz.Matrix(dpi/72, dpi/72))
        yield pix.tobytes("png")
```
No temp files. 150 DPI default; 300 DPI on retry for low-quality documents.

### The Extraction Prompt
The prompt: lists all 8 fields with names and descriptions; specifies exact JSON schema with nested `{value, confidence, source_snippet, source_page}`; says "source_snippet MUST be verbatim text found in the document"; says "If you cannot find a field, set value=null, confidence=0.1, source_snippet=null"; says "Never fabricate values."

### Retry Logic
After the first extraction attempt, counts fields with `source_snippet=None`. If more than 4 of 8 lack snippets, the document is re-rendered at 300 DPI and re-sent. Limited to one retry to prevent infinite loops.

### Why GPT-4o for Extraction?
Trade documents have small fonts, misaligned table columns, stamps overlapping text, multiple languages. GPT-4o-mini has significantly worse OCR accuracy on dense, messy documents.

---

## 9. Agent Layer — Validator

**File:** `nova/agents/validator.py`

### Rules are NOT in Prompts
Rules for each customer live in `config/rules.yaml`, loaded fresh every pipeline run. Why? Auditability (human-readable), customer configurability (edit YAML, no code change), determinism (most checks are pure Python, not LLM), and token efficiency.

### Six Match Types

**exact_ci** — case-insensitive exact string match. Used for `consignee_name`.

**prefix** — field value must start with one of the allowed prefixes (after removing spaces and dots). Used for `hs_code` — rule defines allowed chapter prefixes (e.g. `8471`, `8473`); extracted value `8471.30` matches because it starts with `8471`.

**enum** — value must be in a set of allowed values. Used for `port_of_loading`, `port_of_discharge`, `incoterms`.

**numeric_tolerance** — parse a numeric value, compare to expected value within a percentage tolerance. Used for `gross_weight` — rule says 1000 kg ±5%, so 985 kg is a match but 1200 kg is a mismatch.

**regex** — field must match a regular expression. Used for `invoice_number` — pattern `INV-\d{4,}`.

**semantic** — the only match type that calls the LLM. Used for `description_of_goods`. Rule defines expected keywords; GPT-4o-mini answers: "Does this description relate to these concepts?"

### Confidence Enforcement
Even if extraction says "match", if extractor confidence was 0.60, the verdict becomes `uncertain`. A low-confidence match is not actionable — it needs human review.

---

## 10. Agent Layer — Router

**File:** `nova/agents/router.py`

### Gate Logic
```python
def _classify(verdicts):
    if any(v.status == "mismatch" for v in verdicts):
        return "draft_amendment"
    if any(v.status == "uncertain" for v in verdicts):
        return "flag_for_review"
    return "auto_approve"
```

Deliberately simple and deterministic. Mismatch beats uncertain — provably wrong needs correction, not just review. The only path to `auto_approve` is all 8 fields `match` with confidence ≥ 0.85.

### Amendment Email Generation
Only when action is `draft_amendment` does the router make an LLM call. `auto_approve` and `flag_for_review` generate their reasoning text deterministically, without any LLM.

### Part 2 Extension
In `pipeline_cg.py`, the router receives the `CrossDocResult` before applying the Part 1 trust gate. If `all_consistent == False`, it immediately returns `draft_amendment` without even evaluating individual field verdicts. Inconsistency across documents cannot be auto-approved regardless of individual confidence levels.

---

## 11. Pipeline Layer — LangGraph Orchestration

**File:** `nova/pipeline/pipeline.py`

### The Seven Nodes
```
scope → context → schema_route → extractor → validator → router → persist
```

- **node_scope** — detects document type from filename; logs the guess
- **node_context** — loads `config/rules.yaml`; logs customer name
- **node_schema_route** — pass-through in POC; exists because production Nova has this step
- **node_extractor** — calls `extract()`; returns populated `extracted` field
- **node_validator** — calls `validate()`; returns populated `validation` field
- **node_router** — calls `route()`; returns populated `decision` field
- **node_persist** — writes to SQLite (shipment record, all fields, decision, audit event)

### Public API
- `run(trace_id, doc_paths)` — full 7-node graph from scratch
- `resume(trace_id)` — loads last checkpoint, rebuilds partial graph of remaining nodes, runs it
- `run_partial(trace_id, doc_paths)` — runs through extractor then stops (crash recovery demo)

---

## 12. Query Layer — Natural Language to SQL

**File:** `nova/query/query.py`

### Three-Step Process

**Step 1: Generate SQL via Function Calling**
Question + full schema description + `run_query(sql, explanation)` tool definition → forced tool call → structured SQL. Function calling guarantees structured JSON; regular prompts produce markdown-wrapped SQL.

**Step 2: Safety Check**
```python
def _is_safe_select(sql: str) -> bool:
    stripped = sql.strip().upper()
    if not stripped.startswith("SELECT"):
        return False
    for kw in ["INSERT","UPDATE","DELETE","DROP","CREATE","ALTER","ATTACH","PRAGMA"]:
        if re.search(r"\b" + kw + r"\b", stripped):
            return False
    return True
```
The NL query interface is **read-only**. No question, no matter how phrased, can result in a write.

**Step 3: Execute and Explain**
SQL executed against `nova.db`. Raw rows (up to 20) sent back to GPT-4o-mini with the original question → natural language answer that cites actual values.

---

## 13. Configuration — rules.yaml

**File:** `config/rules.yaml`

Defines validation rules for Acme Logistics. Loaded at the `context` node of every pipeline run — not at startup, not hardcoded. Rules are data; the code that interprets them is logic.

**Note on gross_weight rule:** The current rule hardcodes `expected_kg: 1000.0`. In production, the expected weight comes from the PO/contract system and would be passed as context at runtime, not defined as a constant. This is a known POC simplification — the validation logic itself (numeric tolerance check) is production-ready; only the data source would change.

---

## 14. Crash Recovery & Checkpointing

### The Problem
LLM calls are slow and cost money. A pipeline run processing a multi-page PDF through GPT-4o takes 10–30 seconds and costs $0.03–$0.10. Losing that work to a crash is unacceptable.

### The Solution
After every node completes, the full `PipelineState` is serialized and upserted into `checkpoints`:
```python
def _checkpoint(ps: PipelineState) -> None:
    db.save_checkpoint(ps.trace_id, ps.step, ps.model_dump_json(), ps.cost_usd)
```

### Crash-Safety Guarantee (Precisely Stated)
Checkpoints are written **after** a node completes, not before. This means:
- A crash **after** a node checkpoints: the next `resume()` skips that node and starts at the next one. The expensive LLM call is not repeated.
- A crash **during** a node (e.g., after the GPT-4o vision call but before the checkpoint write): that node will re-run on resume. This means the GPT-4o call bills twice for that node.

This is exactly-once delivery at the **node** level, not at the **LLM call** level. The README states this correctly: "A crash within a node before its checkpoint is written will re-run that node." No claim of exactly-once billing across all crashes.

### Resuming
```python
checkpoint = db.load_checkpoint(trace_id)
state_data = json.loads(checkpoint["state_json"])
current_step = checkpoint["step"]
```
The resume function identifies which step completed last and builds a partial graph containing only the remaining nodes. The extracted data is already in the state JSON — the expensive GPT-4o vision call is not repeated.

---

## 15. Part 2 Overview — CG UI Module

**Problem:** CG operators currently receive raw pipeline JSON with no structured interface. They must manually parse pipeline data, copy amendment emails into email clients, and track status in spreadsheets.

**Solution:** A zero-friction CG operator UI that surfaces pipeline outputs in a structured 4-state flow, gives operators a single "Send" control (agent never auto-dispatches), makes cross-document discrepancies visible before any decision, and persists every operator action to the audit log.

### 4 UI States per Shipment

| State | Trigger | CG Sees |
|-------|---------|---------|
| **1. Incoming** | SU email in `inbox/incoming/` | Email metadata, attachment list, "Process Shipment" button |
| **2. Verification Result** | Pipeline completes | Per-doc field tables + cross-doc consistency strip + pipeline audit trail |
| **3. Discrepancy Detail** | Flagged field clicked | Found vs. expected side-by-side; source snippet; cross-doc diff |
| **4. Draft Reply** | Operator moves to reply tab | Editable email draft; "Send (mock)" button — only human action sends |

### Four Design Guarantees
1. **No auto-send** — pipeline terminates at `node_await_cg`; only a human Send click dispatches
2. **Cross-doc gate** — `all_consistent == False` forces `draft_amendment`; no path to approve
3. **Per-attachment provenance** — each doc has its own `ExtractedDoc` with `doc_type`; no field merging across docs
4. **Crash-safe** — `_state.json` written to shipment folder after pipeline completes; state persists across page reloads

---

## 16. Part 2 — CG Pipeline (7 Nodes)

**File:** `nova/pipeline/pipeline_cg.py`

```
node_ingest_email → node_extract_all → node_validate_all → node_cross_validate
    → node_route_shipment → node_persist_shipment → node_await_cg
```

**node_ingest_email** — mints `trace_id`, logs `email_received` to `audit_log`, loads attachment paths from the shipment folder, stores email metadata.

**node_extract_all** — runs `extract()` once per attachment via `ThreadPoolExecutor` (see §17). Each attachment gets its own `ExtractedDoc`.

**node_validate_all** — runs `validate()` per doc. Each `ExtractedDoc` gets its own `ValidationResult`.

**node_cross_validate** — runs `cross_validate(docs)` deterministically across all docs (see §18). No LLM in this path.

**node_route_shipment** — applies the cross-doc gate first: if `all_consistent == False`, returns `draft_amendment` immediately without evaluating individual verdicts. Otherwise applies Part 1 trust gate across all ValidationResults combined.

**node_persist_shipment** — writes to SQLite: one row in `shipments`, rows in `fields` (tagged with `doc_type`), rows in `cross_doc_checks`, one row in `decisions`.

**node_await_cg** — sets `status = pending_cg_review`. Pipeline terminates here. The CG operator's `Send (mock)` click triggers a separate code path that logs `reply_sent` to `audit_log` and moves the folder to `inbox/processed/`.

---

## 17. Part 2 — Multi-Document Extraction

**File:** `nova/pipeline/multidoc.py`

```python
def extract_all(attachment_paths: list[str]) -> list[ExtractedDoc]:
    with ThreadPoolExecutor(max_workers=len(attachment_paths)) as pool:
        futures = {pool.submit(extract, [path]): path for path in attachment_paths}
        results = []
        for future in as_completed(futures):
            results.append(future.result())
    return results
```

**Why parallel?** Each `extract()` call is an independent GPT-4o vision call. Running them sequentially would take 3× longer for a 3-document shipment with no benefit. Thread parallelism is safe here because `extract()` is stateless — it takes paths and returns an `ExtractedDoc`.

**Per-doc provenance:** Each `ExtractedDoc` carries a `doc_type` label (BOL, INVOICE, PACKING_LIST). Fields are never merged across documents. The cross-validator compares fields doc-by-doc; the UI shows field tables per document so the CG operator can see exactly which document contributed each value.

**Why not merge into one extraction?** Merging would lose provenance. If `hs_code` on the BOL is `8471.30` and on the invoice is `9999.99`, merging would pick one and silently drop the other. The per-attachment approach makes the mismatch visible.

---

## 18. Part 2 — Cross-Document Validation

**File:** `nova/agents/cross_validator.py`

### Shared Fields and Why Only Three

```python
_SHARED_FIELDS = ["consignee_name", "hs_code", "invoice_number"]
```

These three fields are the only ones that must agree across **all** document types in a shipment:
- `consignee_name` — all documents must refer to the same legal entity
- `hs_code` — customs classification must be consistent; BOL/Invoice disagreement triggers customs holds
- `invoice_number` — links BOL to the commercial transaction

Fields deliberately **not** in the shared set:
- `port_of_loading` / `port_of_discharge` — legitimately differ by doc type (e.g. BOL shows actual ports, invoice shows contracted ports)
- `gross_weight` — can legitimately differ between BOL (measured at loading) and packing list (declared weight)
- `incoterms` — may be abbreviated differently on each doc (e.g. "FOB" vs "FOB SHANGHAI")

This is a **design choice**, not an omission.

### Per-Doc-Type Required Fields

In addition to cross-doc consistency, the validator enforces that certain fields must be present on specific document types:

```python
_REQUIRED_BY_DOC_TYPE = {
    "commercial_invoice": ["invoice_number", "hs_code", "consignee_name"],
    "bill_of_lading":    ["hs_code", "consignee_name"],
    "packing_list":      ["consignee_name"],
}
```

A missing required field (e.g., `invoice_number` is `None` on the commercial invoice) generates a `CrossDocVerdict` with `status="inconsistent"` and `field="missing_required_field"`. This prevents a silent pass where an invoice without an invoice number appears consistent.

Note: the packing list does not require `invoice_number` — it is common trade practice for packing lists to carry a shipper reference, not the invoice number. Only the commercial invoice is the source of truth for that field.

### Insufficient Data Handling

For single-attachment shipments (1 doc), every shared field will have `len(present_normalised) < 2`, resulting in `status="insufficient_data"`. The `all_consistent` flag remains `True` in this case — there is nothing to be inconsistent *about*. This means the cross-doc safety net does nothing for single-document emails.

This is correct by design: cross-doc validation only makes sense when there are multiple documents to compare. A single-doc shipment falls back entirely to the Part 1 single-doc trust gate (extraction confidence + rule matching). This is stated as a design decision, not a gap.

---

## 19. Part 2 — CG Operations UI

**File:** `app_cg.py`

### Tab Structure

**Inbox tab** — polls `inbox/incoming/` for shipment folders. Each folder with an `email.json` renders as a card showing: sender, subject, received_at, attachment list (BOL/Invoice/Packing List), and a "Process Shipment" button. If `_state.json` exists in the folder, it was previously processed and the card shows its status.

**Verification Result tab** — after pipeline completes, shows:
- Per-document field tables (one table per attachment): field name, extracted value, confidence badge, verdict, source snippet
- Cross-doc consistency strip: a row per shared field showing values from all docs with CONSISTENT/INCONSISTENT/MISSING badges
- Pipeline Audit Trail: timeline of all events from `audit_log` for this `trace_id`

**Discrepancy Detail tab** — visible when `status == draft_amendment`. Shows:
- Each discrepant field with found vs. expected values side by side
- Source snippet from each document that contributed a conflicting value
- Cross-doc diff showing which document has which version of the field

**Draft Reply tab** — shows the pre-filled amendment or approval email. CG can edit the text. Only the "Send (mock)" button dispatches the reply — it logs `reply_sent` to `audit_log` and moves the folder from `incoming/` (or `processing/`) to `processed/`.

**History tab** — queries `shipments` table; shows all processed shipments with action badges and links to open the result JSON.

**NL Query tab** — natural language query interface over the full 6-table SQLite schema.

### Analytics KPIs
At the top of the History tab: 4 KPI cards (Total Processed, Auto-Approved %, Amendments %, Flagged). Sidebar Quick Stats pull from `shipments` (counts) and `checkpoints` (total cost) separately — they live in different tables.

---

## 20. Part 2 — Mock SU Inbox

**File:** `nova/inbox/watcher.py`

### Folder-Based Inbox Phases

```
inbox/
├── incoming/        ← new SU emails land here
│   └── shipment_ACME_001/
│       ├── email.json
│       ├── bill_of_lading.pdf
│       ├── commercial_invoice.pdf
│       └── packing_list.pdf
├── processing/      ← folder moved here when pipeline starts (acts as a lock)
└── processed/       ← folder moved here after CG clicks Send
```

**`poll_once()`** — scans `incoming/` for folders with `email.json`. Returns their paths.

**`mark_processing(folder)`** — moves the folder from `incoming/` to `processing/`. Acts as a processing lock: if the app crashes mid-pipeline, the folder stays in `processing/` (no duplicate processing on restart).

**`mark_processed(folder, result_json)`** — moves from `processing/` to `processed/` and writes `_result.json`.

**`save_result(folder, state)`** — writes `_state.json` (full serialized `PipelineState`) to the folder. Enables the UI to reload pipeline results without a database round-trip on page reload.

### Why Folder-Based Instead of Real IMAP?
Folder-based mocking allows the demo to run offline without SMTP credentials. In production, `poll_once()` would be replaced with a Gmail API poller or Exchange listener — the interface is the same: return a list of email metadata + attachment paths.

---

## 21. Streamlit UIs

### app.py — Part 1 Single-Doc UI
Two tabs: Pipeline Runner (upload doc → run pipeline → view extraction/validation/decision) and NL Query. Includes crash recovery demo (resume by trace_id).

### app_cg.py — Part 2 CG Operations UI
Six tabs: Inbox, Verification Result, Discrepancy Detail, Draft Reply, History, NL Query. Structured around the 4-state CG operator flow.

### Background and Styling
Both apps use the same CSS approach:
- Background image loaded as base64 from `assets/bg_Img.jpg`, applied to `html::before` with `inset:-10%` to allow parallax travel
- JS `mousemove` handler sets `--nova-px`/`--nova-py` CSS variables on `document.documentElement`; `requestAnimationFrame` throttles redraws
- Streamlit's own containers (`stApp`, `stMain`, `stSidebar`, etc.) are set to `background:transparent` so the custom background shows through
- Streamlit's rainbow decoration bar (`stDecoration`) is hidden

---

## 22. Testing Strategy

### Layer 1: Unit Tests (no LLM, no cost, instant)

**`tests/unit/test_router_gate.py`** (13 tests) — trust gate logic, confidence cap, router function, reasoning text.

**`tests/unit/test_cross_doc.py`** (4 tests) — cross-doc gate: consistent case, inconsistent case, single-doc insufficient_data, partial missing field.

To run:
```bash
pytest tests/unit/ -v
```
All 17 tests are deterministic. No LLM calls. No OpenAI key required.

### Layer 2: Integration Tests (LLM calls, ~$0.05/run)
```bash
python -m nova.pipeline.pipeline samples/clean_bol.pdf     # expect: auto_approve
python -m nova.pipeline.pipeline samples/messy_invoice.jpg # expect: draft_amendment
```

### Layer 3: Crash Recovery Test
```bash
python -m nova.pipeline.pipeline samples/clean_bol.pdf --crash
```
Phase 1: runs through extractor, saves checkpoint, simulates crash. Phase 2: resumes from checkpoint, completes validation and routing without re-calling the vision model.

### Layer 4: End-to-End CG UI Test
Run `launch_cg.bat`, open http://localhost:8501:
1. Inbox tab → ACME_001 → Process Shipment → Verification shows all-green → Draft Reply tab → Send (mock) → folder moves to processed/
2. Inbox tab → ACME_002 → Process Shipment → Discrepancy Detail shows hs_code INCONSISTENT → Draft Reply tab → edit → Send (mock)

---

## 23. Evaluation Harness

**File:** `evals/run_eval.py` | **Data:** `evals/gold.csv`

### Purpose
The unit tests verify that the system's logic is correct. The eval harness verifies that the system's **accuracy** is correct — does it actually extract the right values from documents?

### Metrics Computed
- **Per-field accuracy** — for each of the 8 fields, what fraction of extractions exactly matched the gold value (after case normalization)?
- **Calibration** — are the model's confidence scores honest? Fields are bucketed into low [0.0–0.5), mid [0.5–0.85), and high [0.85–1.0] confidence. Within each bucket, actual accuracy is computed and compared to mean confidence.

### Honest Assessment of the Eval

The gold data in `evals/gold.csv` was generated by `scripts/generate_gold_samples.py`, which creates both the PDFs and the expected labels. This means **the eval measures extraction accuracy against synthetic documents we created**, not real-world trade documents.

Consequently:
- The calibration numbers will appear artificially good — the synthetic PDFs are clean and machine-generated, not scanned, handwritten, or stamped
- The `messy_invoice.jpg` (deliberately adversarial) is the closest to a real-world challenging document
- A production eval would require a dataset of actual historical trade documents with human-labelled ground truth

This is a POC-scope limitation and is stated as such. The eval harness and metrics methodology are production-ready; only the dataset scope is constrained.

---

## 24. End-to-End Data Flow

### Part 1 — Document Upload (messy_invoice.jpg → draft_amendment)

```
1. User uploads messy_invoice.jpg in the browser

2. app.py writes it to a tempfile, generates trace_id="abc-123"

3. nova.pipeline.run("abc-123", ["/tmp/messy_invoice.jpg"]) is called

4. node_scope → detects "invoice" in filename → INVOICE
   → audit_log: {event_type="scope", ...}
   → checkpoint: step="context"

5. node_context → loads config/rules.yaml
   → checkpoint: step="schema_route"

6. node_schema_route → confirms 8-field schema
   → checkpoint: step="extractor"

7. node_extractor → GPT-4o vision
   → hs_code: {value:"9999.99", confidence:0.90, source_snippet:"HS Code: 9999.99", page:1}
   → cost_usd += $0.015
   → checkpoint: step="validator"

8. node_validator → hs_code prefix check: "9999" not in [8471,8473,8542]
   → verdict: {field="hs_code", status="mismatch", found="9999.99", expected="8471/8473/8542"}
   → checkpoint: step="router"

9. node_router → has_mismatch=True → "draft_amendment"
   → GPT-4o-mini generates amendment email
   → cost_usd += $0.002
   → checkpoint: step="persist"

10. node_persist → writes shipments, fields, decisions, audit_log
    → checkpoint: step="done"

11. Streamlit renders: red DRAFT AMENDMENT banner + amendment email
```

### Part 2 — CG Flow (ACME_002 HS mismatch)

```
1. CG sees shipment_ACME_002 card in Inbox tab (email from exports@guangzhou-parts.com)

2. CG clicks "Process Shipment"
   → pipeline_cg.run() called
   → folder moved to inbox/processing/ (lock)

3. node_extract_all → ThreadPoolExecutor(3 workers)
   → BOL: hs_code="8471.30"
   → Invoice: hs_code="9999.99"  ← printed in red on the PDF
   → Packing: hs_code="8471.30"
   → cost_usd += $0.045 (3 vision calls)

4. node_cross_validate → deterministic
   → hs_code: values={"BOL[0]":"847130","Invoice[1]":"999999","Packing[2]":"847130"}
   → status="inconsistent"
   → all_consistent=False

5. node_route_shipment → cross-doc gate triggers
   → action="draft_amendment" (no further checks needed)
   → GPT-4o-mini drafts: "Subject: Amendment Required — hs_code mismatch..."

6. node_persist_shipment → writes all tables including cross_doc_checks

7. node_await_cg → status=pending_cg_review → pipeline stops

8. Verification tab: per-doc tables + hs_code row shows red INCONSISTENT badge
   Discrepancy tab: "BOL: 8471.30 | Invoice: 9999.99 | Packing: 8471.30"

9. CG edits draft reply, clicks "Send (mock)"
   → audit_log: {event_type="reply_sent", actor="cg_operator"}
   → folder moved to inbox/processed/
```

---

## 25. Design Decisions & Known Limitations

This section documents deliberate design choices that a reviewer might ask about, and honest scope limitations. The distinction matters: a design choice has a reasoned justification; a scope limitation is something we know we'd do differently in production.

### Cross-Validation: Only Three Shared Fields (Design Choice)
We check `consignee_name`, `hs_code`, and `invoice_number` across documents — and only these three. `port_of_loading`, `port_of_discharge`, `gross_weight`, and `incoterms` are deliberately excluded because they legitimately differ by doc type (BOL shows measured weight, packing list shows declared weight; BOL shows actual ports, invoice may show contracted ports). This is a documented choice, not an omission.

### Single-Doc Shipments and Cross-Validation (Design Choice)
A 1-attachment email yields `insufficient_data` on all cross-checks and `all_consistent=True`. The cross-doc safety net does nothing for a single document — it falls back entirely to the Part 1 trust gate. This is by design: cross-doc validation only makes semantic sense when there are multiple documents to compare. A single-doc shipment is validated through extraction confidence + rule matching, same as Part 1.

### gross_weight Rule Hardcoded to 1000 kg (POC Scope)
`config/rules.yaml` has `expected_kg: 1000.0` for all shipments. In production, the expected weight would come from the PO/contract system at runtime, not a static constant. The validation logic (numeric tolerance check with configurable %) is production-ready; only the data source is simplified.

### Crash-Safety at Node Granularity, Not LLM Call Granularity (Deliberate)
Checkpoints write after a node completes. A crash during a node (after the LLM call but before the checkpoint) will re-run and re-bill that node. This is exactly-once delivery at the node level. We do not claim zero-double-billing across all possible crash scenarios — and the README states this correctly in guarantee #4.

### Missing Required Field Detection (Now Implemented)
The `_REQUIRED_BY_DOC_TYPE` check in `cross_validator.py` catches cases where a mandatory field (e.g., `invoice_number` on a commercial invoice) is missing entirely. Such cases are surfaced as `status="inconsistent"` with `field="missing_required_field"`, forcing `draft_amendment`. A packing list is not required to carry `invoice_number` — this is per trade convention.

### Evaluation Dataset is Synthetic (POC Scope)
`evals/gold.csv` was generated by `generate_gold_samples.py`, which creates both the PDFs and the labels. Calibration numbers will appear artificially good against clean machine-generated PDFs. See §23 for full discussion.

### Single-User Streamlit (POC Scope)
Streamlit's session state model is per-browser-tab. Multiple simultaneous users would see each other's state. Production: React frontend + FastAPI backend with proper session management.

---

## 26. What Would Change in Production

| Concern | POC | Production |
|---------|-----|------------|
| **Database** | SQLite single file | PostgreSQL with connection pooling |
| **LLM provider abstraction** | Direct OpenAI SDK | LiteLLM for provider fallbacks + budget caps |
| **Multi-customer rules** | One rules.yaml | Rules stored in DB, loaded by customer_id |
| **UI** | Streamlit | React frontend with FastAPI backend |
| **Auth** | None | OAuth / SSO per operator |
| **Concurrency** | Single process | Celery workers or async task queue |
| **LLM observability** | LangSmith free tier | LangSmith Teams or Langfuse self-hosted |
| **Document storage** | Temp files / local folders | S3 or GCS with pre-signed URLs |
| **SU inbox** | Folder-based mock | Gmail API poller or Exchange listener |
| **Deployment** | `streamlit run` / `.bat` | Docker + Kubernetes |
| **CI/CD** | None | GitHub Actions with test + deploy pipeline |
| **Secrets** | `.env` file | AWS Secrets Manager / Vault |
| **gross_weight rule** | Hardcoded 1000 kg | Pulled from PO system at runtime |
| **Eval dataset** | Synthetic PDFs (self-labelled) | Historical trade docs with human-labelled ground truth |
| **Cross-doc fields** | 3 shared fields | Configurable per customer/trade lane |
| **Feedback loop** | CG edits logged, not fed back | Corrections retrain extraction rules |

The production notes are intentionally out of scope for this POC. The architecture was designed with production in mind — the infrastructure layer isolation and SOLID folder structure make the above swaps incremental rather than rewrites.
