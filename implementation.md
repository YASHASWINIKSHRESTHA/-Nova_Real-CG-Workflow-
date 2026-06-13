# Nova POC — Complete Implementation Document

## Table of Contents

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
15. [Streamlit UI](#15-streamlit-ui)
16. [Observability — LangSmith](#16-observability--langsmith)
17. [Testing Strategy](#17-testing-strategy)
18. [Evaluation Harness](#18-evaluation-harness)
19. [End-to-End Data Flow](#19-end-to-end-data-flow)
20. [What Would Change in Production](#20-what-would-change-in-production)

---

## 1. Project Purpose & Problem Statement

### What GoComet Nova Does

GoComet is a freight intelligence platform. One of its core real-world workflows is **trade document validation** — when a shipment is created, suppliers submit documents like Bills of Lading (BOL), Commercial Invoices, and Packing Lists. These documents must be validated against the customer's contracted rules before the shipment can proceed.

This is currently a manual, slow, error-prone process. A human reviewer opens each document, checks each field (consignee name, HS code, port of loading, incoterms, etc.) against what the customer's contract says it should be, flags mismatches, and either approves or sends an amendment request back to the supplier.

### What This POC Demonstrates

This project is a **proof-of-concept miniature of Nova**, GoComet's real platform. It automates that entire review loop:

1. **Extract** — use a vision LLM to read the document (PDF or image) and extract the 8 key trade fields, with a confidence score and verbatim source snippet for every field
2. **Validate** — check each extracted field against the customer's rules (which live in a YAML config, not in prompts)
3. **Route** — apply a deterministic trust gate to decide: auto-approve, flag for human review, or draft an amendment email automatically
4. **Persist** — record everything to SQLite with a full audit trail

The core thesis that must never be violated:
- Every field carries `value + confidence + source_snippet + source_page` — no hallucination without evidence
- If there is no source snippet, confidence is capped at 0.3 — the LLM cannot claim certainty about something it cannot point to
- The router never silently approves — it always explains why
- Rules live in `config/rules.yaml`, never embedded in prompts — this makes the system auditable and customer-configurable
- The pipeline is checkpointed after every node — it can recover from crashes

---

## 2. High-Level Architecture

```
User (browser)
     │
     ▼
app.py  ─── Streamlit UI (two tabs: Pipeline Runner, NL Query)
     │
     ├──► nova/pipeline/pipeline.py  ─── LangGraph 7-node DAG
     │         │
     │         ├── node_scope        ─── detect doc type from filename
     │         ├── node_context      ─── load rules.yaml for this customer
     │         ├── node_schema_route ─── confirm 8-field schema
     │         ├── node_extractor    ─── nova/agents/extractor.py → GPT-4o vision
     │         ├── node_validator    ─── nova/agents/validator.py → deterministic + GPT-4o-mini
     │         ├── node_router       ─── nova/agents/router.py → trust gate + amendment email
     │         └── node_persist      ─── nova/infrastructure/database.py → SQLite
     │
     └──► nova/query/query.py  ─── NL → GPT-4o-mini function-calling → SQLite SELECT → NL answer
```

Every node reads from and writes to a **typed `PipelineState`** Pydantic object. Every node also saves its state to SQLite immediately after completing, so a crash at any point leaves a recoverable checkpoint.

---

## 3. Technology Stack Choices & Rationale

### Python 3.11
The minimum version that ships `tomllib` in stdlib, has full `match/case` support, and significantly improved `asyncio`. More importantly: all the libraries in this stack (LangGraph, Pydantic v2, PyMuPDF) have first-class 3.11 support with no known issues.

### LangGraph (not plain LangChain)
LangGraph is a graph-based orchestration framework from the LangChain team specifically designed for **stateful, multi-agent workflows**. Key reasons it was chosen over alternatives:

- **State machine semantics** — a `StateGraph` with named nodes and edges is the right mental model for a pipeline with distinct stages (scope → context → extract → validate → route → persist). Plain function calls don't enforce stage ordering or make the DAG visible.
- **Type-safe state passing** — each node receives the full pipeline state as a dict, processes it, and returns the updated dict. The state is always `PipelineState` (a Pydantic model), so there are no silent field drops between stages.
- **Built-in interrupt/resume** — LangGraph is designed for exactly the checkpoint-and-resume pattern this pipeline uses. The `StateGraph.compile()` result is a runnable that operates on dicts, making serialization trivial.
- **LangSmith auto-instrumentation** — because LangGraph is part of the LangChain ecosystem, every node and LLM call is automatically traced to LangSmith when the env vars are set. No manual spans, no wrappers.

Why not Prefect, Airflow, or Celery? Those are workflow orchestrators designed for data pipelines with retries, scheduling, and distributed workers. Overkill for a single-request, synchronous, per-document pipeline on a laptop.

### OpenAI API (direct, not via LangChain)
All LLM calls go through `nova/infrastructure/llm.py`, which talks directly to the OpenAI API via the `openai` Python SDK. This was a deliberate choice:

- **No abstraction layer over the LLM** — LangChain's `ChatOpenAI` wrapper is useful in production for swapping providers, but for a POC it adds indirection. Direct API calls mean you see exactly what's being sent and received.
- **Cost tracking** — the direct API response includes `usage.prompt_tokens` and `usage.completion_tokens`. The wrapper computes cost from those and logs it per call. This is how we know the total cost per pipeline run.
- **Two models for two purposes** — `gpt-4o` (vision) for extraction because it can read images/PDFs with high accuracy. `gpt-4o-mini` (text) for the validator's semantic check and the router's amendment email, because these are text-only tasks where the cheaper model is more than sufficient.

### Pydantic v2
Used for all data models. Three reasons:

- **Type enforcement at the boundary** — when the LLM returns JSON, it goes straight into `ExtractedDoc(**data)`. If any field is the wrong type or missing, Pydantic raises immediately. This is "fail loud" — a bad extraction crashes early rather than propagating garbage silently.
- **Model validators** — the `cap_confidence_without_snippet` validator on `FieldValue` enforces the core thesis at the data model level: if `source_snippet is None` and `confidence > 0.3`, confidence is forcibly lowered to 0.3. No code elsewhere needs to check this rule — it's enforced by the type system.
- **JSON serialization** — `model_dump_json()` and `model_dump()` make checkpoint serialization trivial.

### SQLite (via stdlib `sqlite3`)
See the dedicated section (§7). Short answer: zero infrastructure, ACID guarantees, and sufficient for a single-user POC.

### Streamlit
Chosen for the UI because it is the fastest path from Python logic to a running web interface. No HTML, no JavaScript, no REST API, no frontend build step. For a POC demo, this is the right trade-off. The app is not designed for concurrent users — Streamlit's session state model is per-browser-tab, which is fine for a demo.

### PyMuPDF (`fitz`)
Used to render PDF pages to PNG images in memory before sending them to the vision model. PDFs cannot be sent directly to GPT-4o — they must first be rasterized. PyMuPDF is the fastest pure-Python PDF renderer and does this in a few lines with no temp files.

### PyYAML
Rules are stored in `config/rules.yaml` and loaded fresh at the `context` node of every pipeline run. YAML was chosen over JSON for readability (comments, no quoting for strings) and over a database table for simplicity (rules are per-customer config, not runtime data).

---

## 4. Production Folder Structure & SOLID Principles

### Why Restructure at All?

The original flat structure (`nova/models.py`, `nova/db.py`, `nova/llm.py`, `nova/pipeline.py`, `nova/query.py`) works for a quick script but has problems at scale:

- `db.py` mixed DDL (schema creation), checkpoint logic, and result persistence — three responsibilities in one file
- `llm.py` and `models.py` lived at the same level as the orchestration layer, making it unclear which depends on which
- `rules.yaml` was inside the source package — config should never live inside Python packages
- `generate_samples.py` was a utility script at the root, mixed with the entry point
- No clear separation between domain (what the business cares about), infrastructure (how we talk to external systems), and application logic (how we orchestrate)

### The Final Structure

```
nova-poc/
├── app.py                          # Streamlit entry point
├── nova/
│   ├── domain/
│   │   └── models.py               # Pure Pydantic models — no external deps
│   ├── agents/
│   │   ├── extractor.py            # Vision extraction agent
│   │   ├── validator.py            # Validation agent
│   │   └── router.py               # Trust gate agent
│   ├── infrastructure/
│   │   ├── database.py             # SQLite operations
│   │   └── llm.py                  # OpenAI API client
│   ├── pipeline/
│   │   ├── __init__.py             # Re-exports run, resume, run_partial
│   │   └── pipeline.py             # LangGraph DAG
│   └── query/
│       ├── __init__.py             # Re-exports ask
│       └── query.py                # NL → SQL → NL
├── config/
│   └── rules.yaml                  # Customer validation rules
├── scripts/
│   └── generate_samples.py         # One-off utility
├── tests/
│   └── unit/
│       └── test_router_gate.py
├── evals/
│   ├── gold.csv
│   └── run_eval.py
└── samples/ assets/                # Sample docs and static assets
```

### SOLID Applied to Folder Structure

**Single Responsibility Principle (S)**

Every sub-package has exactly one reason to change:

- `nova/domain/` changes only when the business data model changes (new field types, new statuses)
- `nova/agents/` changes only when the AI logic for extraction, validation, or routing changes
- `nova/infrastructure/` changes only when the external systems change (swap SQLite for Postgres, swap OpenAI for Anthropic)
- `nova/pipeline/` changes only when the orchestration DAG changes (add/remove stages)
- `nova/query/` changes only when the NL querying capability changes
- `config/` changes only when customer rules change

**Open/Closed Principle (O)**

Adding a new agent (say, a `classifier.py` that determines document language) means adding one file to `nova/agents/` and one node to `nova/pipeline/pipeline.py`. Nothing else changes. Adding a new infrastructure adapter (say, PostgreSQL) means adding `nova/infrastructure/postgres.py` without touching any agent or pipeline code.

**Liskov Substitution Principle (L)**

`nova/domain/models.py` has zero imports from `nova/infrastructure/`. This means you can completely swap out the database or LLM provider and the domain models remain valid. The pipeline and agents depend on the domain types, not on infrastructure — so swapping infrastructure does not break domain logic.

**Interface Segregation Principle (I)**

`database.py` and `llm.py` are separate modules. An agent that only calls the LLM imports from `nova.infrastructure.llm` — it does not get pulled into the database interface. A module that only reads from the database does not need to import the LLM client. Fine-grained imports mean fine-grained dependencies.

**Dependency Inversion Principle (D)**

High-level modules (`pipeline`, `agents`) depend on abstractions (`domain.models`) not on concrete infrastructure. The `database.py` is only directly imported by `pipeline.py` and `query.py` — the actual orchestration boundary. Agents have no knowledge of how data is persisted; they only receive and return typed domain objects.

---

## 5. Domain Layer — Models

**File:** `nova/domain/models.py`

This file defines all typed data contracts for the system. It has no imports from any other Nova module — it is the only layer that can be imported by everyone without creating circular dependencies.

### FieldValue

```python
class FieldValue(BaseModel):
    value: Optional[str]
    confidence: float  # 0.0–1.0
    source_snippet: Optional[str]
    source_page: Optional[int]
```

This is the atomic unit of extracted information. Every extracted field carries not just its value but the **evidence** that supports it. `source_snippet` is the verbatim text from the document that the LLM used to determine the value. `source_page` is the page number.

The critical validator:
```python
@model_validator(mode="after")
def cap_confidence_without_snippet(self):
    if self.source_snippet is None and self.confidence > 0.3:
        self.confidence = 0.3
```

This enforces the core architectural thesis at the type level: an LLM cannot assign itself a confidence above 30% on a field it cannot point to in the document. This prevents a class of hallucinations where the model makes up a value but claims high certainty. The cap of 0.3 means the router will always see it as "uncertain" (the threshold for auto-approve is 0.85), preventing silent hallucination approvals.

### ExtractedDoc

Contains eight `FieldValue` fields representing the standard trade document fields. The `field_names()` and `get_field(name)` methods allow the validator to iterate over fields without a giant if/else chain.

### ValidationResult

A list of `FieldVerdict` objects (one per field) plus an overall confidence score. Each verdict carries the field name, status (`match/mismatch/uncertain`), what was found, what was expected, the confidence, and a human-readable reason string.

### Decision

The final output of the router:
- `action`: one of `auto_approve`, `flag_for_review`, `draft_amendment`
- `reasoning`: always populated — the router never makes a silent decision
- `amendment_email`: only populated when action is `draft_amendment`

### PipelineState

The single state object that flows through every LangGraph node. It accumulates data as the pipeline progresses: `raw_doc_paths` → `extracted` (after extractor) → `validation` (after validator) → `decision` (after router). Also tracks `step` (current stage), `cost_usd` (running total), and `rules_data` (loaded from YAML at the context node).

---

## 6. Infrastructure Layer — LLM Client

**File:** `nova/infrastructure/llm.py`

All OpenAI API calls go through exactly two public functions: `call_vision` and `call_text`. A third utility `parse_json_response` handles stripping markdown fences from LLM outputs.

### Why Centralize LLM Calls?

By routing all LLM calls through one module:
- Cost tracking is consistent — every call uses the same `_calc_cost` function
- Logging is consistent — every call prints `[llm] model=... in=... out=... cost=...`
- Model selection is explicit — `gpt-4o` for vision tasks, `gpt-4o-mini` for text tasks
- Swapping providers means changing one file

### call_vision

Takes a list of images (either file paths or raw PNG bytes already in memory from the PDF renderer) and a prompt. Encodes each image as base64 data URI and sends them all in a single `user` message. Returns `(raw_text, cost_usd)`.

Why base64 and not URLs? Because the documents are local files uploaded by the user — they have no public URL. The OpenAI vision API accepts base64 data URIs for local files.

Why `detail: "high"`? The default `auto` mode may downsample the image. Trade documents have small text (HS codes, invoice numbers) that requires high resolution to read accurately.

### call_text

Takes a prompt, optional system message, optional tool definitions, and optional tool_choice. Used by the validator (semantic field check) and the router (amendment email). Returns `(raw_text_or_json, cost_usd)`.

The function-calling path: if `tools` are provided and the model responds with a tool call, the function returns the tool call arguments as a JSON string rather than the message content. This is how the NL query module gets structured SQL back from the model.

### Cost Tracking

```python
_COST = {
    "gpt-4o":      {"input": 5.00,  "output": 15.00},
    "gpt-4o-mini": {"input": 0.15,  "output": 0.60},
}
```

Prices are per 1M tokens. The formula:
```python
cost = (tokens_in * rate_in + tokens_out * rate_out) / 1_000_000
```

This cost is returned from every LLM call and accumulated into `PipelineState.cost_usd`. After a full pipeline run, the UI shows the exact dollar cost of processing that document.

---

## 7. Infrastructure Layer — Database

**File:** `nova/infrastructure/database.py`

Uses Python's built-in `sqlite3` module. The database file is `nova.db` at the project root.

### Why SQLite?

1. **Zero infrastructure** — no server process, no Docker, no connection string with credentials. The database is a single file. For a POC that "runs on a laptop", this is the only correct choice.
2. **ACID guarantees** — SQLite's write-ahead logging ensures that checkpoint saves are atomic. If the process crashes mid-write, the database is not corrupted. This is essential for the crash-recovery feature.
3. **Single-writer model is fine** — Streamlit is single-user, single-process. SQLite's limitation (only one writer at a time) is irrelevant here.
4. **Production note** — in production, this module would be replaced with a PostgreSQL-backed repository. Because `database.py` is isolated in the infrastructure layer, all agents and the pipeline would be unaffected by that swap.

### Schema — Five Tables

**shipments** — one row per pipeline run. Tracks `trace_id`, the document paths, and the final status (the router's decision action).

**fields** — one row per extracted field per run. Stores the extracted value, confidence, source snippet, and source page. This is the detailed evidence record — every field decision is auditable.

**decisions** — one row per run. Stores the action, the full reasoning text, and the amendment email if one was drafted.

**audit_log** — append-only event log. Every pipeline node writes a row when it completes, with a JSON payload describing what happened. This is the full operation trail — if something goes wrong, you can reconstruct exactly what each stage saw and did.

**checkpoints** — one row per trace_id (upserted). Stores the full serialized `PipelineState` as JSON after each node. This enables crash recovery: if the process dies after the extractor node, the next `resume(trace_id)` call will reload the state from this table and continue from the validator node.

### DB_PATH Calculation

```python
DB_PATH = Path(__file__).parent.parent.parent / "nova.db"
```

From `nova/infrastructure/database.py`:
- `.parent` → `nova/infrastructure/`
- `.parent.parent` → `nova/`
- `.parent.parent.parent` → project root (`nova-poc/`)

So `nova.db` lives at the project root, not inside the Python package. Runtime data files should never be inside source packages.

---

## 8. Agent Layer — Extractor

**File:** `nova/agents/extractor.py`

The extractor is responsible for one thing: given a list of document file paths (PDF or image), return an `ExtractedDoc` with all 8 trade fields populated, each with value, confidence, source snippet, and page number.

### PDF Rendering

PDFs cannot be sent directly to GPT-4o. They must be rendered to images first:

```python
def _render_pdf_pages(pdf_path: str, dpi: int = 150) -> list[bytes]:
    doc = fitz.open(pdf_path)
    for page in doc:
        pix = page.get_pixmap(matrix=fitz.Matrix(dpi/72, dpi/72))
        yield pix.tobytes("png")
```

PyMuPDF renders each page to a PNG pixmap entirely in memory (no temp files written to disk). The DPI controls resolution: 150 DPI is the default (good quality, manageable size), 300 DPI is used for the retry path if the first pass has too many missing snippets.

### The Extraction Prompt

The prompt is a carefully structured instruction that:
1. Lists all 8 fields with their exact names and descriptions
2. Specifies the exact JSON schema the response must follow, including the nested `{value, confidence, source_snippet, source_page}` structure for every field
3. Explicitly says "RULES: source_snippet MUST be verbatim text found in the document"
4. Says "If you cannot find a field, set value=null, confidence=0.1, source_snippet=null"
5. Says "Never fabricate values"

The explicit schema in the prompt is essential. Without it, the model would return free-form text that requires complex parsing. With it, the response is almost always valid JSON that parses directly into `ExtractedDoc`.

### Retry Logic

After the first extraction attempt, the code counts how many fields have `source_snippet=None`. If more than 4 out of 8 fields lack snippets, it means the document was probably too low-resolution to read accurately. In that case:

```python
if missing > total_fields / 2 and retries < 1:
    image_paths_hd = _load_images(doc_paths, dpi=300)
    raw2, cost2 = call_vision(image_paths_hd, _EXTRACTION_PROMPT)
```

The document is re-rendered at 300 DPI (2x the original) and re-sent to the model. The retry is limited to once (`retries < 1`) to prevent infinite loops. The additional cost is accumulated.

### Why GPT-4o for Extraction?

GPT-4o has the best vision accuracy of the available models. Trade documents often have:
- Small fonts
- Tables with misaligned columns
- Stamps overlapping text
- Multiple languages in one document
- Handwritten corrections

GPT-4o-mini has significantly worse OCR accuracy on dense, messy documents. For the extraction step, accuracy matters more than cost — a missed or wrong HS code has real business consequences.

---

## 9. Agent Layer — Validator

**File:** `nova/agents/validator.py`

The validator takes an `ExtractedDoc` and a rules file and produces a `ValidationResult` containing one `FieldVerdict` per field.

### Rules are NOT in Prompts

This is architecturally critical. The validation rules for each customer (expected consignee name, allowed HS code prefixes, allowed ports, etc.) live in `config/rules.yaml`. They are loaded fresh every pipeline run. They are NOT embedded in the LLM prompt.

Why? Because:
1. **Auditability** — a human can read `rules.yaml` and understand exactly what the system checks. If the rules are in a prompt, they are opaque.
2. **Customer configurability** — each customer has different rules. Changing rules means editing a YAML file, not modifying Python code or prompt strings.
3. **Determinism** — most checks (exact match, prefix, enum, numeric tolerance, regex) are done with pure Python, not by the LLM. The LLM is only called for the semantic `description_of_goods` check, where the question "does this description match the expected goods type?" genuinely requires language understanding.

### Five Match Types

**exact_ci** — case-insensitive exact string match. Used for `consignee_name`. If the document says "Acme Logistics Pte Ltd" and the rule says "ACME LOGISTICS PTE LTD", it's a match.

**prefix** — the field value must start with one of the allowed prefixes after removing spaces and dots. Used for `hs_code` — the rule defines allowed chapter prefixes (e.g. `8471`, `8473`), and the extracted value `8471.30` is a match because it starts with `8471`.

**enum** — the value must be in a set of allowed values. Used for `port_of_loading`, `port_of_discharge`, and `incoterms`.

**numeric_tolerance** — parse a numeric value from the field (stripping units), compare it to an expected value within a percentage tolerance. Used for `gross_weight` — the rule says 1000 kg ±5%, so an extracted value of 980 kg is a match but 1200 kg is a mismatch.

**regex** — the field must match a regular expression. Used for `invoice_number` — the pattern `INV-\d{4,}` means the invoice number must start with "INV-" followed by at least 4 digits.

**semantic** — the only match type that calls the LLM. Used for `description_of_goods`. The rule defines expected keywords (`electronics`, `semiconductor`, `PCB`). The validator asks GPT-4o-mini: "Does this description relate to these concepts?" and gets back `{match: bool, confidence: float, reason: str}`.

### Confidence Enforcement

After determining a raw status (`match`, `mismatch`, or `uncertain`), the validator applies a final check:

```python
def _enforce_confidence(status: str, confidence: float) -> str:
    if confidence < _CONFIDENCE_THRESHOLD:  # 0.85
        return "uncertain"
    return status
```

Even if the extraction says "match" (e.g., consignee name matches), if the extractor only had 0.60 confidence, the verdict becomes `uncertain`. A low-confidence match is not actionable — it needs human review.

---

## 10. Agent Layer — Router

**File:** `nova/agents/router.py`

The router is the trust gate. It takes a `ValidationResult` and makes the final decision.

### Gate Logic

```python
def _classify(verdicts: list[FieldVerdict]) -> str:
    has_mismatch = any(v.status == "mismatch" for v in verdicts)
    has_uncertain = any(v.status == "uncertain" for v in verdicts)

    if has_mismatch:
        return "draft_amendment"
    if has_uncertain:
        return "flag_for_review"
    return "auto_approve"
```

The logic is deliberately simple and deterministic:
- **Any mismatch → draft_amendment** (mismatch beats uncertain — if something is provably wrong, it needs correction, not just review)
- **Any uncertain → flag_for_review** (uncertain means a human should look)
- **All match → auto_approve** (only when every single field is confirmed correct with confidence ≥ 0.85)

This means the only path to `auto_approve` is all 8 fields being `match` with confidence ≥ 0.85. One field with 0.84 confidence forces a flag. This is intentional conservatism — false positives (wrong auto-approvals) have real business consequences in trade.

### Amendment Email Generation

Only when the action is `draft_amendment` does the router make an LLM call. It builds a prompt listing all mismatched fields (what was found vs. what was expected) and asks GPT-4o-mini to draft a professional email to the supplier requesting corrections within 24 hours.

This is the only router LLM call — `auto_approve` and `flag_for_review` generate their reasoning text deterministically, without any LLM.

### Reasoning Always Populated

The `reasoning` field of the `Decision` is always a human-readable explanation:
- For `auto_approve`: "All fields passed validation with confidence ≥ 0.85. Shipment auto-approved."
- For `flag_for_review`: lists each uncertain field with its confidence and why it's uncertain
- For `draft_amendment`: lists each mismatching field with what was found vs. expected

---

## 11. Pipeline Layer — LangGraph Orchestration

**File:** `nova/pipeline/pipeline.py`

### The Seven Nodes

The pipeline follows a 5-stage structure inspired by GoComet's real Nova platform, expanded to 7 nodes for implementation reasons:

```
scope → context → schema_route → extractor → validator → router → persist
```

**node_scope** — detects the document type by inspecting the filename. "invoice" in the name → INVOICE, "packing" → PACKING_LIST, default → BOL. Logs the guess. This is deliberately simple — a production version would use the extractor's output doc_type field.

**node_context** — loads `config/rules.yaml` and stores it in `PipelineState.rules_data`. This is the "load customer rules" step. Logging the customer name from the YAML creates an audit trail showing which rule set was applied.

**node_schema_route** — in a production multi-customer system, this node would select the appropriate extraction schema based on doc type and customer. In this POC it's a pass-through that logs "8 standard trade fields". It exists because the real Nova has this step and it's architecturally correct to keep it — adding customer-specific schemas later doesn't require restructuring the pipeline.

**node_extractor** — calls `extract()` from the extractor agent. Receives `raw_doc_paths` from state, returns populated `extracted` field and accumulated cost.

**node_validator** — calls `validate()` from the validator agent. Receives `extracted` from state, returns populated `validation` field.

**node_router** — calls `route()` from the router agent. Receives `validation` from state, returns populated `decision` field.

**node_persist** — calls `persist_results()` and `log_event()` from the database module. Writes the complete run results (shipment record, all field values, decision, audit event) to SQLite.

### Why LangGraph Instead of a For Loop?

A naive implementation could just be:
```python
extracted = extract(doc_paths)
validation = validate(extracted)
decision = route(validation)
persist(extracted, validation, decision)
```

LangGraph adds:
1. **Named node execution** — each node is a named callable. The graph can be inspected, visualized, and traced.
2. **State typed handoffs** — each node receives the full state dict and returns an updated state dict. The state accumulates all data across stages, which is essential for the persist node to have access to all earlier results.
3. **LangSmith auto-tracing** — every node invocation appears as a separate span in LangSmith with its inputs and outputs.
4. **Partial graph execution** — the `resume()` function rebuilds a subgraph starting from the last checkpointed node. This is possible because the graph structure is explicit.

### Public API

`run(trace_id, doc_paths)` — runs the full 7-node graph from scratch.

`resume(trace_id)` — loads the last checkpoint, determines which node to start from, rebuilds a subgraph of only the remaining nodes, and runs it. This is the crash recovery path.

`run_partial(trace_id, doc_paths)` — runs only the first 4 nodes (through the extractor), then stops. Used to demonstrate crash recovery.

### __init__.py Re-exports

```python
# nova/pipeline/__init__.py
from nova.pipeline.pipeline import run, resume, run_partial
```

This means `app.py` can do `from nova.pipeline import run, resume` — the import path is stable even if the internal module is refactored.

---

## 12. Query Layer — Natural Language to SQL

**File:** `nova/query/query.py`

This module implements a three-step process to answer natural language questions about shipment data:

### Step 1: Generate SQL via Function Calling

The question is sent to GPT-4o-mini along with the full database schema description and a tool definition for `run_query(sql, explanation)`. The model is forced to call this tool (`tool_choice: force`). The response is the structured SQL query.

Why function calling instead of just asking for SQL in a prompt? Function calling guarantees a structured JSON response. Asking "write SQL for this question" in a regular prompt produces markdown-wrapped SQL that requires regex parsing. Function calling produces `{"sql": "SELECT ...", "explanation": "..."}` reliably.

### Step 2: Safety Check

```python
def _is_safe_select(sql: str) -> bool:
    stripped = sql.strip().upper()
    if not stripped.startswith("SELECT"):
        return False
    for kw in ["INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER", "ATTACH", "PRAGMA"]:
        if re.search(r"\b" + kw + r"\b", stripped):
            return False
    return True
```

The NL query interface is **read-only**. No user question, no matter how cleverly phrased, can result in a write to the database. The safety check rejects anything that is not a pure SELECT and blocks any destructive keywords even inside subqueries or CTEs.

### Step 3: Execute and Explain

The SQL is executed against `nova.db`. The raw rows (up to 20) are sent back to GPT-4o-mini with the original question, and the model writes a natural language answer that cites the actual values from the results.

---

## 13. Configuration — rules.yaml

**File:** `config/rules.yaml`

This file defines the validation rules for the current customer (Acme Logistics). It is loaded at the `context` node of every pipeline run — not at startup, not hardcoded in any Python file.

### Why YAML and Not a Database Table?

Rules are customer configuration, not runtime data. They change rarely (when a contract is renegotiated, not when a shipment is processed). YAML is human-readable, diffable in version control, and straightforward to edit without a database client. In production, rules would likely be stored in a database with a UI for customer operations teams to edit — but the loading mechanism in `node_context` is already designed for that: it calls `yaml.safe_load(f)` which could be trivially replaced with a database query.

### Why NOT in Prompts?

If rules were in the prompt ("validate that the consignee name is ACME LOGISTICS PTE LTD"), they would be:
- Hard to audit — what exact rules did this run use?
- Hard to change without redeployment
- Consuming tokens on every run
- Mixed with instructions, making prompt engineering harder

With YAML, the rules are data. The code that interprets them is logic. They are separated, as they should be.

---

## 14. Crash Recovery & Checkpointing

### The Problem

LLM calls are slow and cost money. A pipeline run that processes a multi-page PDF through GPT-4o vision takes 10–30 seconds and costs $0.03–$0.10. If the process crashes after extraction but before validation, losing that work and the cost associated with it is unacceptable.

### The Solution

After every node completes, the full `PipelineState` is serialized to JSON and upserted into the `checkpoints` table:

```python
def _checkpoint(ps: PipelineState) -> None:
    db.save_checkpoint(ps.trace_id, ps.step, ps.model_dump_json(), ps.cost_usd)
```

The `ON CONFLICT(trace_id) DO UPDATE` pattern means each `trace_id` has exactly one checkpoint row, always containing the state at the last completed node.

### Resuming

```python
checkpoint = db.load_checkpoint(trace_id)
state_data = json.loads(checkpoint["state_json"])
current_step = checkpoint["step"]
```

The resume function reads the checkpoint, identifies which step completed last, and builds a partial graph containing only the remaining nodes. If the crash happened after the extractor (step=`validator`), the resume graph starts at `validator` and runs `validator → router → persist`.

The extracted data is already in the state JSON — it does not need to be re-extracted. The expensive GPT-4o vision call is not repeated.

---

## 15. Streamlit UI

**File:** `app.py`

### Tab 1: Pipeline Runner

The upload widget accepts PDF, JPG, JPEG, and PNG files. When "Run Pipeline" is clicked:
1. The file is written to a temp file (via `tempfile.NamedTemporaryFile`)
2. A new `trace_id` is generated (`uuid4`)
3. `run(trace_id, [tmp_path])` is called inside a `st.spinner`
4. The result is stored in `st.session_state["pipeline_result"]`

The results section displays three expandable areas:
- **Extraction Results** — one expander per field, showing the value, confidence bar (green/yellow/red), page number, and source snippet in a code block
- **Validation Verdicts** — a table row per field with color-coded status badges
- **Router Decision** — a large colored banner (green for auto-approve, yellow for flag, red for amendment) plus the full reasoning text and the amendment email if one was generated

The Resume section accepts a `trace_id` and calls `resume(trace_id)` — this is the crash recovery demo path.

### Tab 2: NL Query

Pre-populated example questions help users explore without knowing the schema. The question is sent to `ask()` which returns the SQL, explanation, raw rows, and natural language answer. The last 5 queries are shown as expandable cards in the session.

### Background Image

The background is loaded from `assets/bg_Img.jpg` and injected as a base64 data URI in a CSS `::before` pseudo-element on `body`. An animated CSS keyframe (`nova-bg-drift`) creates a slow parallax drift effect. A dark overlay (`body::after`) keeps text readable over the image.

If the image file is missing, the app falls back gracefully to a dark gradient — the UI never breaks.

---

## 16. Observability — LangSmith

### What It Is

LangSmith is the observability platform from the LangChain team. For this project, it provides:
- A trace for every pipeline run, showing all 7 nodes as spans
- Within each node, every LLM call as a child span
- The full prompt and response for each LLM call
- Latency per call and per node
- Token counts and cost per call
- Side-by-side comparison of runs

### Why It Is Free for This Project

LangSmith's Developer tier is free: 5,000 traces/month, 14-day data retention, 1 user. A POC running a few dozen test documents per day will never exceed this limit.

### Why No Code Changes Were Needed

Because the project already uses LangGraph, and LangGraph is part of the LangChain ecosystem. When the following environment variables are set, LangGraph automatically instruments itself:

```
LANGCHAIN_TRACING_V2=true
LANGCHAIN_PROJECT=nova-poc
LANGCHAIN_API_KEY=lsv2_...
```

`python-dotenv` loads these from `.env` at startup (via `load_dotenv()` in `nova/infrastructure/llm.py`). From that point, every `StateGraph.invoke()` call and every OpenAI API call made through LangChain-compatible wrappers is automatically traced.

### What to Look For

In the LangSmith UI (`smith.langchain.com` → your `nova-poc` project):
- Each pipeline run appears as one top-level trace
- Expand it to see the 7 nodes as sequential spans
- Click the `extractor` span to see the GPT-4o vision call — the full base64 image, the extraction prompt, and the raw JSON response
- Click the `router` span to see the amendment email generation (if applicable)
- The metadata sidebar shows total tokens, total cost, and total latency

---

## 17. Testing Strategy

### Layer 1: Unit Tests (no LLM, no cost, instant)

**File:** `tests/unit/test_router_gate.py`

These tests verify the deterministic logic of the system without making any LLM calls:

- **Trust gate logic** (`_classify`) — tests all four states: all-match → auto_approve, any-uncertain → flag_for_review, any-mismatch → draft_amendment, mismatch beats uncertain
- **Confidence cap** (`FieldValue` model validator) — tests that missing snippet forces confidence ≤ 0.3, that present snippet leaves confidence unchanged, and that already-low confidence is not altered
- **Router function** (`route`) — uses `monkeypatch` to mock `call_text`, verifying that auto_approve never calls the LLM, draft_amendment calls it exactly once for the email, and flag_for_review never produces an email
- **Reasoning text** (`_build_reasoning`) — verifies that the reasoning string mentions the specific failing fields

To run:
```bash
pytest tests/unit/test_router_gate.py -v
```

### Layer 2: Agent Integration Tests (LLM calls, real cost)

Run each agent as a script against the sample documents:

```bash
# Extractor: should extract 8 fields from the clean BOL with high confidence
python -m nova.agents.extractor samples/clean_bol.pdf

# Extractor: should extract HS code 9999.99 from the messy invoice
python -m nova.agents.extractor samples/messy_invoice.jpg

# Full pipeline on each sample
python -m nova.pipeline.pipeline samples/clean_bol.pdf
python -m nova.pipeline.pipeline samples/messy_invoice.jpg
```

Expected results:
- `clean_bol.pdf` → `auto_approve` (all fields match, all confidence ≥ 0.85)
- `messy_invoice.jpg` → `draft_amendment` (HS code 9999.99 is not in the allowed prefixes 8471/8473/8542, which is a deliberate mismatch)

### Layer 3: Crash Recovery Test

```bash
python -m nova.pipeline.pipeline samples/clean_bol.pdf --crash
```

Phase 1: runs through extractor, prints "checkpoint saved", simulates crash.
Phase 2: resumes from the checkpoint, completes validation and routing without re-calling the vision model.

The SQLite `checkpoints` table should show the state after extraction if inspected mid-run.

### Layer 4: End-to-End UI Test

```bash
streamlit run app.py --server.headless true
```

Upload each sample document in Tab 1, verify the displayed extraction results match expected values, verify the decision banner matches expected action, check the NL Query tab with several questions.

---

## 18. Evaluation Harness

**File:** `evals/run_eval.py`
**Data:** `evals/gold.csv`

### Purpose

The unit tests verify that the system's logic is correct. The eval harness verifies that the system's **accuracy** is correct — does it actually extract the right values from real documents?

### Gold CSV Format

```
doc_id,doc_path,field_name,true_value
clean_bol_001,samples/clean_bol.pdf,consignee_name,ACME LOGISTICS PTE LTD
clean_bol_001,samples/clean_bol.pdf,hs_code,8471.30
...
```

Each row is one (document, field, expected value) triple. The eval runs extraction on each document once and compares all field extractions against the gold values.

### Metrics Computed

**Per-field accuracy** — for each of the 8 fields, what fraction of extractions exactly matched the gold value (after case normalization)? This reveals which fields the extractor struggles with.

**Calibration** — does the model's confidence actually predict accuracy? Fields are bucketed into low [0.0–0.5), mid [0.5–0.85), and high [0.85–1.0] confidence. Within each bucket, the actual accuracy is computed and compared to the mean confidence. Calibration error = |actual_accuracy - mean_confidence|. A well-calibrated model should have high actual accuracy in the high-confidence bucket. If the model claims 0.9 confidence but only achieves 0.5 accuracy, it is overconfident and the confidence cap threshold might need adjusting.

---

## 19. End-to-End Data Flow

Here is the complete journey of a document upload through the system:

```
1. User uploads messy_invoice.jpg in the browser

2. app.py writes it to a tempfile, generates trace_id="abc-123"

3. nova.pipeline.run("abc-123", ["/tmp/messy_invoice.jpg"]) is called

4. node_scope:
   - Detects "invoice" in filename → doc_type_guess = "INVOICE"
   - Logs to audit_log: {event="scope", doc_type_guess="INVOICE"}
   - Saves checkpoint: step="context"

5. node_context:
   - Loads config/rules.yaml
   - Logs customer="Acme Logistics"
   - Saves checkpoint: step="schema_route", rules_data={...}

6. node_schema_route:
   - Logs "8 standard trade fields"
   - Saves checkpoint: step="extractor"

7. node_extractor:
   - _load_images: no PDF, passes image path directly
   - call_vision(["/tmp/messy_invoice.jpg"], _EXTRACTION_PROMPT)
     → GPT-4o reads image, returns JSON with 8 fields
     → hs_code: {value: "9999.99", confidence: 0.90, source_snippet: "HS Code: 9999.99", source_page: 1}
   - ExtractedDoc(**data) validates the JSON
   - cost_usd += $0.015
   - Saves checkpoint: step="validator"

8. node_validator:
   - For hs_code: match_type="prefix", allowed_prefixes=["8471","8473","8542"]
     - "9999" does not start with any allowed prefix → raw_status="mismatch"
     - confidence=0.90 ≥ 0.85 → final_status="mismatch"
     - verdict: {field="hs_code", status="mismatch", found="9999.99", expected="one of ['8471','8473','8542']"}
   - For description_of_goods: match_type="semantic"
     - call_text("Does 'Electronic Parts and Semiconductor Devices' relate to ['electronics','semiconductor','PCB']?")
     - response: {match: true, confidence: 0.88, reason: "contains semiconductor"}
     - verdict: {field="description_of_goods", status="match", confidence=0.88}
   - All other fields: match
   - overall_confidence = mean of all field confidences ≈ 0.87
   - Saves checkpoint: step="router"

9. node_router:
   - _classify: has_mismatch=True (hs_code) → action="draft_amendment"
   - _draft_amendment_email: call_text with mismatch details
     → GPT-4o-mini writes: "Subject: Amendment Required...\n\nDear Supplier..."
   - cost_usd += $0.002
   - Decision: {action="draft_amendment", reasoning="Amendment required due to field mismatches:\n  • hs_code: found '9999.99', expected one of ['8471','8473','8542']", amendment_email="Subject: ..."}
   - Saves checkpoint: step="persist"

10. node_persist:
    - INSERT INTO shipments: (trace_id="abc-123", status="draft_amendment")
    - INSERT INTO fields: 8 rows with all extracted values
    - INSERT INTO decisions: action, reasoning, email
    - INSERT INTO audit_log: pipeline_complete event
    - Saves checkpoint: step="done"

11. PipelineState returned to app.py

12. Streamlit renders:
    - Extraction table: hs_code row shows confidence bar in red, source snippet "HS Code: 9999.99"
    - Validation verdicts: hs_code row shows red MISMATCH badge, reason text
    - Decision banner: large red "DRAFT AMENDMENT" block
    - Amendment email in a code block, ready to copy

13. LangSmith records:
    - 1 top-level trace "nova-poc" run
    - 7 node spans
    - 2 LLM call spans (extractor GPT-4o, router GPT-4o-mini)
    - Total latency, token counts, cost
```

---

## 20. What Would Change in Production

This POC deliberately keeps things simple. Here is what a production version of this system would change:

| Concern | POC | Production |
|---------|-----|------------|
| **Database** | SQLite single file | PostgreSQL with connection pooling |
| **LLM provider abstraction** | Direct OpenAI SDK | LiteLLM or LangChain's model abstraction for provider fallbacks |
| **Multi-customer rules** | One rules.yaml | Rules stored in DB, loaded by customer_id |
| **UI** | Streamlit | React frontend with a FastAPI backend |
| **Auth** | None | OAuth / SSO |
| **Concurrency** | Single process | Celery workers or async task queue |
| **LLM observability** | LangSmith free tier | LangSmith Teams or Langfuse self-hosted |
| **Cost controls** | Logged, not enforced | Per-customer rate limits and budget caps |
| **Document storage** | Temp files | S3 or GCS with pre-signed URLs |
| **Deployment** | `streamlit run app.py` | Docker + Kubernetes |
| **CI/CD** | None | GitHub Actions with test + deploy pipeline |
| **Secrets** | `.env` file | AWS Secrets Manager / Vault |
| **PDF rendering** | In-process (PyMuPDF) | Separate rendering microservice |
| **Retry logic** | DPI upscale once | Exponential backoff + fallback model |

The production notes are intentionally out of scope for this POC. The architecture, however, was designed with production in mind — particularly the infrastructure layer isolation and the SOLID folder structure, which make the above swaps incremental rather than rewrites.
