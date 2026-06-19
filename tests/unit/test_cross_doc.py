"""
Deterministic tests for Part 2 cross-doc logic.
cross_validate() is pure. route_shipment()'s LLM email calls are monkeypatched
so no LLM is hit — we only assert the gate decision.
"""
import pytest

import nova.agents.router as router
from nova.agents.cross_validator import cross_validate
from nova.agents.router import route_shipment
from nova.domain.models import (
    ExtractedDoc, FieldValue, FieldVerdict, ValidationResult,
)


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def _fv(v: str) -> FieldValue:
    return FieldValue(value=v, confidence=0.95, source_snippet=v)


def _doc(doc_type: str, hs: str) -> ExtractedDoc:
    return ExtractedDoc(
        doc_type=doc_type,
        consignee_name=_fv("ACME LOGISTICS PTE LTD"),
        hs_code=_fv(hs),
        port_of_loading=_fv("Shanghai"),
        port_of_discharge=_fv("Singapore"),
        incoterms=_fv("FOB"),
        description_of_goods=_fv("electronics"),
        gross_weight=_fv("1000 kg"),
        invoice_number=_fv("INV-0001"),
    )


def _pass_validation() -> ValidationResult:
    v = FieldVerdict(
        field="hs_code", status="match", found="8471.30",
        expected="8471", confidence=0.95, reason="ok",
    )
    return ValidationResult(verdicts=[v], overall_confidence=0.95)


# ──────────────────────────────────────────────
# cross_validate() — pure, no monkeypatching needed
# ──────────────────────────────────────────────

def test_cross_validate_detects_hs_mismatch():
    res = cross_validate([_doc("BOL", "8471.30"), _doc("INVOICE", "9999.99")])
    assert res.all_consistent is False
    hs = next(v for v in res.verdicts if v.field == "hs_code")
    assert hs.status == "inconsistent"


def test_cross_validate_passes_when_all_agree():
    res = cross_validate([_doc("BOL", "8471.30"), _doc("INVOICE", "8471.30")])
    assert res.all_consistent is True


# ──────────────────────────────────────────────
# route_shipment() — cross-doc gate assertions
# ──────────────────────────────────────────────

def test_inconsistent_cannot_be_auto_approved(monkeypatch):
    """Cross-doc inconsistency must force draft_amendment even when per-doc verdicts all pass."""
    monkeypatch.setattr(
        router, "_draft_cross_doc_amendment",
        lambda bad: ("Subject: Fix\n\nbody", 0.0),
    )
    cross = cross_validate([_doc("BOL", "8471.30"), _doc("INVOICE", "9999.99")])
    decision, _ = route_shipment([_pass_validation(), _pass_validation()], cross)
    assert decision.action == "draft_amendment"


def test_consistent_and_passing_auto_approves(monkeypatch):
    """All docs consistent + all per-doc verdicts pass → auto_approve."""
    monkeypatch.setattr(
        router, "_draft_approval_email",
        lambda: ("Subject: Approved\n\nbody", 0.0),
    )
    cross = cross_validate([_doc("BOL", "8471.30"), _doc("INVOICE", "8471.30")])
    decision, _ = route_shipment([_pass_validation(), _pass_validation()], cross)
    assert decision.action == "auto_approve"
