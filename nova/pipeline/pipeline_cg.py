"""
Part 2 CG pipeline: email folder → multi-doc extraction → cross-doc validation
→ route → persist → await CG review.

Node order:
  node_ingest_email
  node_extract_all
  node_validate_all_docs
  node_cross_validate_docs
  node_route_shipment_doc
  node_persist_shipment_doc
  node_await_cg_doc          ← pipeline stops here; CG must click Send

Checkpoint after every node so a crash resumes without re-billing GPT-4o.
The pipeline NEVER sends an email. That action belongs only to the CG operator
via the UI.
"""
import uuid
from pathlib import Path
from typing import Any

from langgraph.graph import END, StateGraph

from nova.infrastructure import database as db
from nova.agents.extractor import extract
from nova.agents.validator import validate
from nova.agents.cross_validator import cross_validate
from nova.agents.router import route_shipment
from nova.pipeline.multidoc import extract_all
from nova.domain.models import PipelineState
from nova.inbox import watcher


# ── Checkpoint helper (same pattern as Part 1) ─────────────────────────────────

def _checkpoint(ps: PipelineState) -> None:
    db.save_checkpoint(ps.trace_id, ps.step, ps.model_dump_json(), ps.cost_usd)


# ── Node implementations ────────────────────────────────────────────────────────

def node_ingest_email(state: dict) -> dict:
    ps = PipelineState(**state)
    folder = Path(ps.email_meta["folder"])

    email_data = watcher.read_email(folder)
    attachment_paths = watcher.attachments(folder)
    customer = email_data.get("customer", "Unknown")

    db.log_event(ps.trace_id, "email_received", {
        "message_id": email_data.get("message_id"),
        "from": email_data.get("from"),
        "customer": customer,
        "n_attachments": len(attachment_paths),
    })

    updated = ps.model_copy(update={
        "raw_doc_paths": attachment_paths,
        "customer": customer,
        "email_meta": {**ps.email_meta, "email_data": email_data},
        "step": "extract_all",
    })
    _checkpoint(updated)
    return updated.model_dump()


def node_extract_all(state: dict) -> dict:
    ps = PipelineState(**state)
    docs, total_cost = extract_all(ps.raw_doc_paths)

    db.log_event(ps.trace_id, "extracted_all", {
        "n_docs": len(docs),
        "doc_types": [d.doc_type for d in docs],
    })

    updated = ps.model_copy(update={
        "extracted_docs": docs,
        "step": "validate_all",
        "cost_usd": ps.cost_usd + total_cost,
    })
    _checkpoint(updated)
    return updated.model_dump()


def node_validate_all_docs(state: dict) -> dict:
    ps = PipelineState(**state)
    results = []
    total_cost = 0.0

    for doc in ps.extracted_docs:
        validation, cost = validate(doc)
        results.append(validation)
        total_cost += cost

    db.log_event(ps.trace_id, "validated_all", {
        "n_docs": len(results),
        "overall_confidences": [round(r.overall_confidence, 3) for r in results],
    })

    updated = ps.model_copy(update={
        "per_doc_validation": results,
        "step": "cross_validate",
        "cost_usd": ps.cost_usd + total_cost,
    })
    _checkpoint(updated)
    return updated.model_dump()


def node_cross_validate_docs(state: dict) -> dict:
    ps = PipelineState(**state)
    cross = cross_validate(ps.extracted_docs)

    db.log_event(ps.trace_id, "cross_validated", {
        "all_consistent": cross.all_consistent,
        "verdicts": [{"field": v.field, "status": v.status} for v in cross.verdicts],
    })

    updated = ps.model_copy(update={
        "cross_doc": cross,
        "step": "route_shipment",
    })
    _checkpoint(updated)
    return updated.model_dump()


def node_route_shipment_doc(state: dict) -> dict:
    ps = PipelineState(**state)
    decision, cost = route_shipment(ps.per_doc_validation, ps.cross_doc)

    db.log_event(ps.trace_id, "routed_shipment", {"action": decision.action})

    updated = ps.model_copy(update={
        "decision": decision,
        "step": "persist_shipment",
        "cost_usd": ps.cost_usd + cost,
    })
    _checkpoint(updated)
    return updated.model_dump()


def node_persist_shipment_doc(state: dict) -> dict:
    ps = PipelineState(**state)
    db.persist_cg_results(ps)
    db.log_event(ps.trace_id, "persisted_shipment", {"cost_usd": ps.cost_usd})

    updated = ps.model_copy(update={"step": "await_cg"})
    _checkpoint(updated)
    return updated.model_dump()


def node_await_cg_doc(state: dict) -> dict:
    """
    Pipeline terminates here. Status is 'pending_cg_review'.
    Only a human CG operator action (Send button in UI) dispatches the reply.
    """
    ps = PipelineState(**state)
    db.log_event(ps.trace_id, "pending_cg_review", {
        "action": ps.decision.action if ps.decision else None,
        "cost_usd_total": ps.cost_usd,
    })
    updated = ps.model_copy(update={"step": "done"})
    _checkpoint(updated)
    return updated.model_dump()


# ── Graph construction (mirrors Part 1 pattern) ────────────────────────────────

def _build_cg_graph() -> Any:
    g = StateGraph(dict)
    g.add_node("ingest_email",   node_ingest_email)
    g.add_node("extract_all",    node_extract_all)
    g.add_node("validate_all",   node_validate_all_docs)
    g.add_node("cross_validate", node_cross_validate_docs)
    g.add_node("route_shipment", node_route_shipment_doc)
    g.add_node("persist",        node_persist_shipment_doc)
    g.add_node("await_cg",       node_await_cg_doc)

    g.set_entry_point("ingest_email")
    g.add_edge("ingest_email",   "extract_all")
    g.add_edge("extract_all",    "validate_all")
    g.add_edge("validate_all",   "cross_validate")
    g.add_edge("cross_validate", "route_shipment")
    g.add_edge("route_shipment", "persist")
    g.add_edge("persist",        "await_cg")
    g.add_edge("await_cg",       END)
    return g.compile()


_CG_GRAPH = None


def _get_cg_graph() -> Any:
    global _CG_GRAPH
    if _CG_GRAPH is None:
        _CG_GRAPH = _build_cg_graph()
    return _CG_GRAPH


# ── Public API ─────────────────────────────────────────────────────────────────

def run_cg(folder_path: str) -> PipelineState:
    """
    Run the CG pipeline for a shipment folder.
    folder_path — absolute path to the shipment folder (inbox/processing/<name>).
    Returns PipelineState at step='done' (awaiting CG action).
    """
    db.init_db()
    trace_id = str(uuid.uuid4())
    initial = PipelineState(
        trace_id=trace_id,
        raw_doc_paths=[],
        email_meta={"folder": str(folder_path)},
        step="ingest_email",
    )
    result = _get_cg_graph().invoke(initial.model_dump())
    return PipelineState(**result)


if __name__ == "__main__":
    import sys
    folder = sys.argv[1] if len(sys.argv) > 1 else "inbox/incoming/shipment_ACME_001"
    print(f"[pipeline_cg] Running CG pipeline for: {folder}")
    result = run_cg(folder)
    print(f"\n=== CG Pipeline Complete ===")
    print(f"trace_id: {result.trace_id}")
    print(f"customer: {result.customer}")
    print(f"action:   {result.decision.action if result.decision else '—'}")
    print(f"cost:     ${result.cost_usd:.4f}")
    if result.cross_doc:
        print("\nCross-doc verdicts:")
        for v in result.cross_doc.verdicts:
            print(f"  {v.field}: {v.status}")
