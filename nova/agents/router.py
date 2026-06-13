"""
Router agent: ValidationResult → Decision.
Trust gate: auto_approve only when ALL fields pass (conf >= 0.85 AND match).
One uncertain → flag_for_review. Any mismatch → draft_amendment.
Never silently approves.
"""
from nova.infrastructure.llm import call_text
from nova.domain.models import Decision, FieldVerdict, ValidationResult

_CONFIDENCE_THRESHOLD = 0.85

_AMENDMENT_SYSTEM = (
    "You are a professional freight operations coordinator. "
    "Write concise, formal emails to suppliers requesting document amendments."
)


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
    """Apply trust gate and return (Decision, cost_usd)."""
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


if __name__ == "__main__":
    import sys
    from nova.models import ValidationResult

    if len(sys.argv) > 1:
        import json
        with open(sys.argv[1]) as f:
            vr = ValidationResult.model_validate_json(f.read())
        decision, cost = route(vr)
        print(decision.model_dump_json(indent=2))
        print(f"\nCost: ${cost:.6f}")
    else:
        print("Usage: python -m nova.agents.router <validation_result.json>")
