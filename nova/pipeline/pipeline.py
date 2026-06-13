"""
LangGraph pipeline: scope → context → schema_route → extractor → validator → router → persist.
PipelineState is checkpointed to SQLite after every node.
resume(trace_id) reloads the last checkpoint and continues.
"""
import json
import uuid
from pathlib import Path
from typing import Any

from langgraph.graph import END, StateGraph

from nova.infrastructure import database as db
from nova.agents.extractor import extract
from nova.agents.router import route
from nova.agents.validator import validate
from nova.domain.models import Decision, PipelineState

_RULES_PATH = Path(__file__).parent.parent.parent / "config" / "rules.yaml"


# ──────────────────────────────────────────────
# Node implementations
# ──────────────────────────────────────────────

def node_scope(state: dict) -> dict:
    ps = PipelineState(**state)
    paths = ps.raw_doc_paths
    guessed_type = "BOL"
    for p in paths:
        lower = Path(p).name.lower()
        if "invoice" in lower:
            guessed_type = "INVOICE"
        elif "packing" in lower:
            guessed_type = "PACKING_LIST"
    db.log_event(ps.trace_id, "scope", {"doc_type_guess": guessed_type, "paths": paths})
    updated = ps.model_copy(update={"step": "context"})
    _checkpoint(updated)
    return updated.model_dump()


def node_context(state: dict) -> dict:
    ps = PipelineState(**state)
    import yaml
    with open(_RULES_PATH) as f:
        rules_data = yaml.safe_load(f)
    db.log_event(ps.trace_id, "context", {"customer": rules_data.get("customer")})
    updated = ps.model_copy(update={"step": "schema_route", "rules_data": rules_data})
    _checkpoint(updated)
    return updated.model_dump()


def node_schema_route(state: dict) -> dict:
    ps = PipelineState(**state)
    db.log_event(ps.trace_id, "schema_route", {"fields": "8 standard trade fields"})
    updated = ps.model_copy(update={"step": "extractor"})
    _checkpoint(updated)
    return updated.model_dump()


def node_extractor(state: dict) -> dict:
    ps = PipelineState(**state)
    extracted, cost = extract(ps.raw_doc_paths, retries=ps.retries)
    db.log_event(ps.trace_id, "extracted", {"fields_extracted": len(extracted.field_names())})
    updated = ps.model_copy(update={
        "extracted": extracted,
        "step": "validator",
        "cost_usd": ps.cost_usd + cost,
    })
    _checkpoint(updated)
    return updated.model_dump()


def node_validator(state: dict) -> dict:
    ps = PipelineState(**state)
    validation, cost = validate(ps.extracted)
    db.log_event(ps.trace_id, "validated", {
        "overall_confidence": validation.overall_confidence,
        "verdicts": [v.status for v in validation.verdicts],
    })
    updated = ps.model_copy(update={
        "validation": validation,
        "step": "router",
        "cost_usd": ps.cost_usd + cost,
    })
    _checkpoint(updated)
    return updated.model_dump()


def node_router(state: dict) -> dict:
    ps = PipelineState(**state)
    decision, cost = route(ps.validation)
    db.log_event(ps.trace_id, "routed", {"action": decision.action})
    updated = ps.model_copy(update={
        "decision": decision,
        "step": "persist",
        "cost_usd": ps.cost_usd + cost,
    })
    _checkpoint(updated)
    return updated.model_dump()


def node_persist(state: dict) -> dict:
    ps = PipelineState(**state)
    db.persist_results(
        ps.trace_id,
        ps.raw_doc_paths,
        ps.extracted,
        ps.validation,
        ps.decision,
    )
    db.log_event(ps.trace_id, "persisted", {"cost_usd": ps.cost_usd})
    updated = ps.model_copy(update={"step": "done"})
    _checkpoint(updated)
    return updated.model_dump()


# ──────────────────────────────────────────────
# Checkpoint helper
# ──────────────────────────────────────────────

def _checkpoint(ps: PipelineState) -> None:
    db.save_checkpoint(ps.trace_id, ps.step, ps.model_dump_json(), ps.cost_usd)


# ──────────────────────────────────────────────
# Graph construction
# ──────────────────────────────────────────────

def _build_graph() -> Any:
    g = StateGraph(dict)
    g.add_node("scope", node_scope)
    g.add_node("context", node_context)
    g.add_node("schema_route", node_schema_route)
    g.add_node("extractor", node_extractor)
    g.add_node("validator", node_validator)
    g.add_node("router", node_router)
    g.add_node("persist", node_persist)

    g.set_entry_point("scope")
    g.add_edge("scope", "context")
    g.add_edge("context", "schema_route")
    g.add_edge("schema_route", "extractor")
    g.add_edge("extractor", "validator")
    g.add_edge("validator", "router")
    g.add_edge("router", "persist")
    g.add_edge("persist", END)
    return g.compile()


_GRAPH = None


def _get_graph():
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = _build_graph()
    return _GRAPH


# ──────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────

_STEP_TO_NODE = {
    "scope": "scope",
    "context": "context",
    "schema_route": "schema_route",
    "extractor": "extractor",
    "validator": "validator",
    "router": "router",
    "persist": "persist",
}


def run(trace_id: str, doc_paths: list[str]) -> PipelineState:
    """Run the full pipeline from scratch."""
    db.init_db()
    initial = PipelineState(trace_id=trace_id, raw_doc_paths=doc_paths)
    result = _get_graph().invoke(initial.model_dump())
    return PipelineState(**result)


def resume(trace_id: str) -> PipelineState:
    """Resume a pipeline from the last saved checkpoint."""
    db.init_db()
    checkpoint = db.load_checkpoint(trace_id)
    if checkpoint is None:
        raise ValueError(f"No checkpoint found for trace_id={trace_id}")

    state_data = json.loads(checkpoint["state_json"])
    current_step = checkpoint["step"]
    print(f"[pipeline] Resuming trace_id={trace_id} from step={current_step}")

    # Rebuild graph starting from the current step node
    g = StateGraph(dict)
    nodes = {
        "scope": node_scope, "context": node_context, "schema_route": node_schema_route,
        "extractor": node_extractor, "validator": node_validator,
        "router": node_router, "persist": node_persist,
    }
    order = ["scope", "context", "schema_route", "extractor", "validator", "router", "persist"]

    # Find where to resume
    if current_step in order:
        start_idx = order.index(current_step)
    else:
        start_idx = 0

    remaining = order[start_idx:]

    for name in remaining:
        g.add_node(name, nodes[name])

    g.set_entry_point(remaining[0])
    for i in range(len(remaining) - 1):
        g.add_edge(remaining[i], remaining[i + 1])
    g.add_edge(remaining[-1], END)

    partial_graph = g.compile()
    result = partial_graph.invoke(state_data)
    return PipelineState(**result)


# ──────────────────────────────────────────────
# Helpers for crash-recovery demo
# ──────────────────────────────────────────────

def run_partial(trace_id: str, doc_paths: list[str]) -> PipelineState:
    """Run pipeline through extractor only (simulates a crash before validator)."""
    db.init_db()
    state = PipelineState(trace_id=trace_id, raw_doc_paths=doc_paths).model_dump()
    for node_fn in [node_scope, node_context, node_schema_route, node_extractor]:
        state = node_fn(state)
    ps = PipelineState(**state)
    print(f"[pipeline] Partial run complete at step={ps.step}, cost=${ps.cost_usd:.6f}")
    return ps


# ──────────────────────────────────────────────
# Crash-recovery demo
# ──────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    db.init_db()

    doc_path = sys.argv[1] if len(sys.argv) > 1 else "samples/clean_bol.pdf"
    trace_id = str(uuid.uuid4())
    print(f"\n=== Nova Pipeline Demo ===")
    print(f"trace_id: {trace_id}")
    print(f"doc: {doc_path}\n")

    _crash_demo = "--crash" in sys.argv

    if _crash_demo:
        print("--- Phase 1: Running pipeline through extraction, then simulating crash ---")
        partial = run_partial(trace_id, [doc_path])
        print(f"\n[CRASH] Pipeline crashed after extraction. Checkpoint saved at step={partial.step}")
        print(f"[pipeline] trace_id={trace_id} is checkpointed and recoverable.\n")

        print("--- Phase 2: Resuming from checkpoint ---")
        final = resume(trace_id)
        print(f"\n=== Resumed Pipeline Complete ===")
        print(f"Action: {final.decision.action}")
        print(f"Reasoning:\n{final.decision.reasoning}")
        print(f"Total cost: ${final.cost_usd:.6f}")
    else:
        final = run(trace_id, [doc_path])
        print(f"\n=== Pipeline Complete ===")
        print(f"Action: {final.decision.action}")
        print(f"Reasoning:\n{final.decision.reasoning}")
        if final.decision.amendment_email:
            print(f"\nAmendment Email:\n{final.decision.amendment_email}")
        print(f"Total cost: ${final.cost_usd:.6f}")
