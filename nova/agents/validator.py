"""
Validator agent: ExtractedDoc + rules.yaml → ValidationResult.
Deterministic for exact/prefix/enum/regex/numeric fields.
GPT-4o-mini only for semantic goods-description check.
Confidence < 0.85 always forces status = 'uncertain'.
"""
import re
import sys
from pathlib import Path
from statistics import mean
from typing import Optional

import yaml

from nova.infrastructure.llm import call_text
from nova.domain.models import ExtractedDoc, FieldValue, FieldVerdict, ValidationResult

_RULES_PATH = Path(__file__).parent.parent.parent / "config" / "rules.yaml"

_CONFIDENCE_THRESHOLD = 0.85


def _load_rules(path: Optional[Path] = None) -> dict:
    p = path or _RULES_PATH
    with open(p) as f:
        return yaml.safe_load(f)


def _enforce_confidence(status: str, confidence: float) -> str:
    if confidence < _CONFIDENCE_THRESHOLD:
        return "uncertain"
    return status


def _check_exact_ci(found: str, rule: dict) -> tuple[str, str]:
    expected = rule["expected"]
    ok = found.strip().lower() == expected.strip().lower()
    return ("match" if ok else "mismatch"), expected


def _check_prefix(found: str, rule: dict) -> tuple[str, str]:
    prefixes = rule["allowed_prefixes"]
    clean = found.strip().replace(" ", "").replace(".", "")
    ok = any(clean.startswith(p) for p in prefixes)
    return ("match" if ok else "mismatch"), f"one of {prefixes}"


def _check_enum(found: str, rule: dict) -> tuple[str, str]:
    allowed = [a.upper() for a in rule["allowed"]]
    ok = found.strip().upper() in allowed
    return ("match" if ok else "mismatch"), f"one of {rule['allowed']}"


def _check_numeric_tolerance(found: str, rule: dict) -> tuple[str, str]:
    tol = rule["tolerance_pct"] / 100.0
    expected_kg = float(rule["expected_kg"])
    numeric = re.sub(r"[^\d.]", "", found.split()[0] if found else "")
    if not numeric:
        return "uncertain", f"{expected_kg} kg ±{rule['tolerance_pct']}%"
    try:
        found_val = float(numeric)
        ok = abs(found_val - expected_kg) / expected_kg <= tol
        return ("match" if ok else "mismatch"), f"{expected_kg} kg ±{rule['tolerance_pct']}%"
    except ValueError:
        return "uncertain", f"{expected_kg} kg ±{rule['tolerance_pct']}%"


def _check_regex(found: str, rule: dict) -> tuple[str, str]:
    pattern = rule["pattern"]
    ok = bool(re.search(pattern, found.strip()))
    return ("match" if ok else "mismatch"), f"matches {pattern}"


def _check_semantic(found: str, rule: dict) -> tuple[str, str, float, float]:
    """Use GPT-4o-mini to check if description contains expected concepts."""
    keywords = rule["expected_keywords"]
    prompt = (
        f"Does the following goods description relate to these concepts: {keywords}?\n\n"
        f"Description: {found}\n\n"
        "Reply with exactly one JSON object: "
        '{"match": true/false, "confidence": 0.0-1.0, "reason": "one sentence"}'
    )
    raw, cost = call_text(prompt)
    try:
        import json
        from nova.infrastructure.llm import parse_json_response
        data = parse_json_response(raw)
        status = "match" if data.get("match") else "mismatch"
        confidence = float(data.get("confidence", 0.5))
        return status, f"expected concepts: {keywords}", confidence, cost
    except Exception:
        return "uncertain", f"expected concepts: {keywords}", 0.5, cost


def validate(extracted: ExtractedDoc, rules_path: Optional[Path] = None) -> tuple[ValidationResult, float]:
    """Validate ExtractedDoc against rules. Returns (ValidationResult, cost_usd)."""
    rules_data = _load_rules(rules_path)
    rules = rules_data.get("rules", {})
    verdicts: list[FieldVerdict] = []
    total_cost = 0.0

    for fname in extracted.field_names():
        fv: FieldValue = extracted.get_field(fname)
        rule = rules.get(fname)

        if fv.value is None or fv.value.strip() == "":
            verdicts.append(FieldVerdict(
                field=fname,
                status="uncertain",
                found=None,
                expected=rule.get("expected") if rule else None,
                confidence=fv.confidence,
                reason="Field not found in document",
            ))
            continue

        if rule is None:
            verdicts.append(FieldVerdict(
                field=fname,
                status="match",
                found=fv.value,
                expected=None,
                confidence=fv.confidence,
                reason="No rule defined — accepted as-is",
            ))
            continue

        match_type = rule.get("match_type", "exact_ci")
        semantic_confidence: Optional[float] = None

        if match_type == "exact_ci":
            raw_status, expected_str = _check_exact_ci(fv.value, rule)
        elif match_type == "prefix":
            raw_status, expected_str = _check_prefix(fv.value, rule)
        elif match_type == "enum":
            raw_status, expected_str = _check_enum(fv.value, rule)
        elif match_type == "numeric_tolerance":
            raw_status, expected_str = _check_numeric_tolerance(fv.value, rule)
        elif match_type == "regex":
            raw_status, expected_str = _check_regex(fv.value, rule)
        elif match_type == "semantic":
            raw_status, expected_str, semantic_confidence, sem_cost = _check_semantic(fv.value, rule)
            total_cost += sem_cost
        else:
            raw_status, expected_str = "uncertain", "unknown rule type"

        effective_conf = semantic_confidence if semantic_confidence is not None else fv.confidence
        final_status = _enforce_confidence(raw_status, effective_conf)

        reason = _build_reason(fname, fv.value, raw_status, expected_str, effective_conf)

        verdicts.append(FieldVerdict(
            field=fname,
            status=final_status,
            found=fv.value,
            expected=expected_str,
            confidence=effective_conf,
            reason=reason,
        ))

    overall = mean(v.confidence for v in verdicts) if verdicts else 0.0
    return ValidationResult(verdicts=verdicts, overall_confidence=overall), total_cost


def _build_reason(field: str, found: str, status: str, expected: str, confidence: float) -> str:
    if status == "match":
        return f"'{found}' satisfies rule ({expected})"
    elif status == "mismatch":
        return f"'{found}' does not satisfy rule: expected {expected}"
    else:
        return f"Confidence {confidence:.2f} below threshold or field ambiguous (expected {expected})"


if __name__ == "__main__":
    import json
    sample_json = sys.argv[1] if len(sys.argv) > 1 else None
    if sample_json:
        from nova.models import ExtractedDoc
        with open(sample_json) as f:
            doc = ExtractedDoc.model_validate_json(f.read())
        result, cost = validate(doc)
        print(result.model_dump_json(indent=2))
        print(f"\nCost: ${cost:.6f}")
    else:
        print("Usage: python -m nova.agents.validator <extracted_doc.json>")
