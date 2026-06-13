# Nova POC — Multi-Agent Trade Doc Pipeline (GoComet DAW Part 1)

## What this is
A POC-scale miniature of GoComet's real Nova platform: governed agentic doc validation.
Light nod to Nova's 5 stages: scope -> context -> schema route -> plan+execute -> evidence.

## Core thesis (NEVER violate)
- Every field carries value + confidence + source evidence (snippet + page).
- No source_snippet -> confidence capped <= 0.3.
- Router NEVER silently approves. auto_approve needs ALL fields >= 0.85 AND match.
  One uncertain -> flag_for_review. Any mismatch -> draft_amendment. Always explain WHY.
- Typed Pydantic handoffs on a LangGraph state. Checkpoint per node; resume(trace_id).
- Rules live in config/rules.yaml, NOT in prompts. retries <= 2, log per-doc cost.

## Stack (POC scope — keep it simple)
Python 3.11, LangGraph, OpenAI API direct (gpt-4o vision for extraction,
gpt-4o-mini for text), Pydantic v2, SQLite, Streamlit, PyMuPDF.
NO LiteLLM/Langfuse/multi-tenant in the POC — those are prod notes in the write-up only.

## Conventions
- All LLM calls go through nova/infrastructure/llm.py. Validate outputs via Pydantic, fail loud.
- trace_id per run; JSON-log each stage. NL query is read-only SELECT only.
- Runs on a laptop: single SQLite file, `streamlit run app.py`.
