"""
Deterministic trust-gate tests for nova/agents/router.py.
No LLM calls — all inputs are hand-crafted ValidationResult objects.
"""
import pytest

from nova.domain.models import Decision, FieldValue, FieldVerdict, ValidationResult
from nova.agents.router import route, _classify


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def _make_verdict(field: str, status: str, confidence: float) -> FieldVerdict:
    return FieldVerdict(
        field=field,
        status=status,
        found="found_value",
        expected="expected_value",
        confidence=confidence,
        reason="test",
    )


def _make_validation(verdicts: list[FieldVerdict]) -> ValidationResult:
    overall = sum(v.confidence for v in verdicts) / len(verdicts)
    return ValidationResult(verdicts=verdicts, overall_confidence=overall)


# ──────────────────────────────────────────────
# Gate logic tests (no LLM — test _classify directly)
# ──────────────────────────────────────────────

def test_all_pass_auto_approve():
    verdicts = [
        _make_verdict("consignee_name", "match", 0.95),
        _make_verdict("hs_code", "match", 0.90),
        _make_verdict("port_of_loading", "match", 0.88),
    ]
    assert _classify(verdicts) == "auto_approve"


def test_one_uncertain_flags_for_review():
    verdicts = [
        _make_verdict("consignee_name", "match", 0.95),
        _make_verdict("hs_code", "uncertain", 0.60),
        _make_verdict("port_of_loading", "match", 0.90),
    ]
    assert _classify(verdicts) == "flag_for_review"


def test_one_mismatch_drafts_amendment():
    verdicts = [
        _make_verdict("consignee_name", "match", 0.95),
        _make_verdict("hs_code", "mismatch", 0.90),
        _make_verdict("port_of_loading", "match", 0.88),
    ]
    assert _classify(verdicts) == "draft_amendment"


def test_mismatch_beats_uncertain():
    """draft_amendment must win over flag_for_review when both present."""
    verdicts = [
        _make_verdict("consignee_name", "mismatch", 0.90),
        _make_verdict("hs_code", "uncertain", 0.60),
        _make_verdict("port_of_loading", "match", 0.88),
    ]
    assert _classify(verdicts) == "draft_amendment"


def test_all_fields_uncertain_flag_for_review():
    verdicts = [
        _make_verdict("consignee_name", "uncertain", 0.50),
        _make_verdict("hs_code", "uncertain", 0.40),
    ]
    assert _classify(verdicts) == "flag_for_review"


def test_single_mismatch_in_many_matches():
    verdicts = [
        _make_verdict(f"field_{i}", "match", 0.90) for i in range(7)
    ]
    verdicts.append(_make_verdict("hs_code", "mismatch", 0.91))
    assert _classify(verdicts) == "draft_amendment"


# ──────────────────────────────────────────────
# Evidence cap: FieldValue model validator
# ──────────────────────────────────────────────

def test_no_snippet_caps_confidence():
    fv = FieldValue(value="SOME VALUE", confidence=0.95, source_snippet=None, source_page=None)
    assert fv.confidence <= 0.3, f"Expected confidence <= 0.3, got {fv.confidence}"


def test_snippet_present_confidence_unchanged():
    fv = FieldValue(value="SOME VALUE", confidence=0.92, source_snippet="SOME VALUE", source_page=1)
    assert fv.confidence == 0.92


def test_no_snippet_already_low_confidence_unchanged():
    fv = FieldValue(value="SOME VALUE", confidence=0.20, source_snippet=None, source_page=None)
    assert fv.confidence == 0.20


# ──────────────────────────────────────────────
# Route function (mocks LLM for amendment email)
# ──────────────────────────────────────────────

def test_route_auto_approve_no_llm_call(monkeypatch):
    """auto_approve should not call any LLM."""
    calls = []

    def mock_call_text(*args, **kwargs):
        calls.append(args)
        return "MOCK EMAIL", 0.0

    monkeypatch.setattr("nova.agents.router.call_text", mock_call_text)

    verdicts = [_make_verdict("hs_code", "match", 0.92)]
    vr = _make_validation(verdicts)
    decision, cost = route(vr)

    assert decision.action == "auto_approve"
    assert decision.amendment_email is None
    assert len(calls) == 0, "auto_approve should not call LLM"


def test_route_draft_amendment_calls_llm(monkeypatch):
    """draft_amendment must call LLM once for the email."""
    calls = []

    def mock_call_text(*args, **kwargs):
        calls.append(args)
        return "Subject: Amendment\n\nPlease correct field X.", 0.001

    monkeypatch.setattr("nova.agents.router.call_text", mock_call_text)

    verdicts = [_make_verdict("hs_code", "mismatch", 0.92)]
    vr = _make_validation(verdicts)
    decision, cost = route(vr)

    assert decision.action == "draft_amendment"
    assert decision.amendment_email is not None
    assert len(calls) == 1, "draft_amendment must call LLM exactly once"


def test_route_flag_for_review_no_email(monkeypatch):
    """flag_for_review should not produce an amendment email."""
    monkeypatch.setattr("nova.agents.router.call_text", lambda *a, **k: ("", 0.0))

    verdicts = [_make_verdict("hs_code", "uncertain", 0.60)]
    vr = _make_validation(verdicts)
    decision, cost = route(vr)

    assert decision.action == "flag_for_review"
    assert decision.amendment_email is None


def test_reasoning_cites_failing_fields():
    verdicts = [
        _make_verdict("hs_code", "mismatch", 0.92),
        _make_verdict("consignee_name", "match", 0.95),
    ]
    vr = _make_validation(verdicts)

    # Don't actually call LLM — just test _build_reasoning logic
    from nova.agents.router import _build_reasoning
    reasoning = _build_reasoning("draft_amendment", verdicts)
    assert "hs_code" in reasoning
