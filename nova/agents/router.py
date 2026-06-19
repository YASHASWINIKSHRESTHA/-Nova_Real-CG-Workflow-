"""
Router agent: ValidationResult → Decision.
Trust gate: auto_approve only when ALL fields pass (conf >= 0.85 AND match).
One uncertain → flag_for_review. Any mismatch → draft_amendment.
Never silently approves.

Part 2 additions:
  route_shipment()  — wraps route() with cross-doc consistency gate
  _merge_per_doc()  — takes the strictest verdict across N docs
"""
from statistics import mean

from nova.infrastructure.llm import call_text
from nova.domain.models import (
    CrossDocResult, CrossDocVerdict,
    Decision, FieldVerdict, ValidationResult,
)

_CONFIDENCE_THRESHOLD = 0.85

_AMENDMENT_SYSTEM = (
    "You are a professional freight operations coordinator. "
    "Write concise, formal emails to suppliers requesting document amendments."
)


# ── Part 1 core ───────────────────────────────────────────────────────────────

def _classify(verdicts: list[FieldVerdict]) -> str:
    has_mismatch = any(v.status == "mismatch" for v in verdicts)
    has_uncertain = any(v.status == "uncertain" for v in verdicts)

    if has_mismatch:
        return "draft_amendment"
    if has_uncertain:
        return "flag_for_review"
    return "auto_approve"


def _build_reasoning(action: str, verdicts: list[FieldVerdict]) -> str:
    if action == "auto_approve":
        return (
            "All fields passed validation with confidence >= 0.85. "
            "Shipment auto-approved."
        )

    failing = [v for v in verdicts if v.status in ("mismatch", "uncertain")]
    parts = []
    for v in failing:
        if v.status == "mismatch":
            parts.append(f"  • {v.field}: found '{v.found}', expected {v.expected}")
        else:
            parts.append(f"  • {v.field}: uncertain (confidence {v.confidence:.2f}) — {v.reason}")

    if action == "flag_for_review":
        return "Flagged for human review due to uncertain fields:\n" + "\n".join(parts)
    return "Amendment required due to field mismatches:\n" + "\n".join(parts)


def _draft_amendment_email(verdicts: list[FieldVerdict]) -> tuple[str, float]:
    mismatches = [v for v in verdicts if v.status == "mismatch"]
    discrepancies = "\n".join(
        f"- {v.field}: found '{v.found}', expected '{v.expected}'"
        for v in mismatches
    )
    prompt = (
        "Draft a professional amendment request email to the supplier. "
        "Subject line on first line, then blank line, then body.\n\n"
        f"The following discrepancies were found:\n{discrepancies}\n\n"
        "Be specific about each discrepancy. Ask them to resubmit corrected documents within 24 hours."
    )
    email_text, cost = call_text(prompt, system=_AMENDMENT_SYSTEM)
    return email_text.strip(), cost


def route(validation: ValidationResult) -> tuple[Decision, float]:
    """Apply trust gate and return (Decision, cost_usd). Part 1 interface — unchanged."""
    action = _classify(validation.verdicts)
    reasoning = _build_reasoning(action, validation.verdicts)
    amendment_email = None
    cost = 0.0

    if action == "draft_amendment":
        amendment_email, cost = _draft_amendment_email(validation.verdicts)

    return Decision(
        action=action,
        reasoning=reasoning,
        amendment_email=amendment_email,
    ), cost


# ── Part 2 additions ──────────────────────────────────────────────────────────

def _draft_cross_doc_amendment(
    inconsistent: list[CrossDocVerdict],
) -> tuple[str, float]:
    """Draft an amendment email that lists cross-document field inconsistencies."""
    discrepancies = "\n".join(
        f"- {v.field}: "
        + " | ".join(
            f"{doc}: '{val}'" for doc, val in v.values_by_doc.items() if val
        )
        for v in inconsistent
    )
    prompt = (
        "Draft a professional amendment request email to the supplier. "
        "Subject line on first line, then blank line, then body.\n\n"
        "The following CROSS-DOCUMENT INCONSISTENCIES were found — "
        "the same field has different values in different documents:\n"
        f"{discrepancies}\n\n"
        "List each discrepancy clearly (field · value in Document A · value in Document B). "
        "Request resubmission of corrected, consistent documents within 24 hours."
    )
    email_text, cost = call_text(prompt, system=_AMENDMENT_SYSTEM)
    return email_text.strip(), cost


def _draft_approval_email() -> tuple[str, float]:
    """Draft a brief approval notification for the CG to send to the supplier."""
    prompt = (
        "Draft a brief, professional approval confirmation email to the supplier. "
        "Their shipment documents have been verified: all fields passed validation "
        "and all documents are internally consistent. "
        "Inform them the shipment is cleared for processing. "
        "Subject line on first line, then blank line, then body. Keep it under 8 lines."
    )
    email_text, cost = call_text(prompt, system=_AMENDMENT_SYSTEM)
    return email_text.strip(), cost


def _merge_per_doc(results: list[ValidationResult]) -> ValidationResult:
    """
    Merge N per-doc ValidationResults into one by taking the strictest verdict
    per field across all docs (mismatch > uncertain > match).
    """
    if not results:
        return ValidationResult(verdicts=[], overall_confidence=0.0)
    if len(results) == 1:
        return results[0]

    field_names = [v.field for v in results[0].verdicts]
    merged: list[FieldVerdict] = []

    for fname in field_names:
        candidates: list[FieldVerdict] = []
        for result in results:
            for v in result.verdicts:
                if v.field == fname:
                    candidates.append(v)
                    break

        if not candidates:
            continue

        severity = {"mismatch": 2, "uncertain": 1, "match": 0}
        worst = max(candidates, key=lambda v: severity.get(v.status, 0))
        merged.append(worst)

    overall = mean(v.confidence for v in merged) if merged else 0.0
    return ValidationResult(verdicts=merged, overall_confidence=overall)


def route_shipment(
    per_doc: list[ValidationResult],
    cross: CrossDocResult,
) -> tuple[Decision, float]:
    """
    Part 2 routing gate.
    Cross-doc inconsistency → draft_amendment (overrides all per-doc results).
    Otherwise, fall back to Part 1 route() on the strictest per-doc result.
    """
    cost = 0.0

    # Cross-doc gate: inconsistency cannot be approved
    if not cross.all_consistent:
        bad = [v for v in cross.verdicts if v.status == "inconsistent"]
        reasoning_lines = [
            "Cross-document inconsistency detected — amendment required:",
        ]
        for v in bad:
            pairs = " | ".join(
                f"{doc}: '{val}'" for doc, val in v.values_by_doc.items() if val
            )
            reasoning_lines.append(f"  • {v.field}: {pairs}")
        reasoning = "\n".join(reasoning_lines)

        amendment_email, email_cost = _draft_cross_doc_amendment(bad)
        cost += email_cost

        return Decision(
            action="draft_amendment",
            reasoning=reasoning,
            amendment_email=amendment_email,
        ), cost

    # All cross-doc consistent → merge per-doc and apply Part 1 trust gate
    merged = _merge_per_doc(per_doc)
    decision, route_cost = route(merged)
    cost += route_cost

    # If auto-approved, generate a pre-drafted approval email for CG to send
    if decision.action == "auto_approve":
        approval_email, approval_cost = _draft_approval_email()
        cost += approval_cost
        decision = decision.model_copy(update={"approval_email": approval_email})

    return decision, cost


if __name__ == "__main__":
    import sys
    from nova.domain.models import ValidationResult

    if len(sys.argv) > 1:
        import json
        with open(sys.argv[1]) as f:
            vr = ValidationResult.model_validate_json(f.read())
        decision, cost = route(vr)
        print(decision.model_dump_json(indent=2))
        print(f"\nCost: ${cost:.6f}")
    else:
        print("Usage: python -m nova.agents.router <validation_result.json>")
