"""
Cross-document consistency: shared fields must agree across all attachments
in one shipment. Deterministic — no LLM in the decision path.
"""
from nova.domain.models import CrossDocResult, CrossDocVerdict, ExtractedDoc

# Fields that must agree across all documents in a single shipment
_SHARED_FIELDS = ["consignee_name", "hs_code", "invoice_number"]

# Extractor returns uppercase short-form doc_type ("BOL", "INVOICE", "PACKING_LIST").
# Required-field keys use snake_case for readability. Normalise before lookup.
_DOC_TYPE_NORM: dict[str, str] = {
    "BOL":          "bill_of_lading",
    "INVOICE":      "commercial_invoice",
    "PACKING_LIST": "packing_list",
}

# Fields that MUST be present (non-None) on a given doc type.
# Packing lists don't carry invoice_number by trade convention.
_REQUIRED_BY_DOC_TYPE: dict[str, list[str]] = {
    "commercial_invoice": ["invoice_number", "hs_code", "consignee_name"],
    "bill_of_lading":    ["hs_code", "consignee_name"],
    "packing_list":      ["consignee_name"],
}


def _norm(v: str | None) -> str | None:
    """Normalise for comparison: strip, uppercase, collapse spaces."""
    if v is None:
        return None
    cleaned = v.strip().upper().replace(" ", "").replace(".", "").replace("-", "")
    return cleaned if cleaned else None


def cross_validate(docs: list[ExtractedDoc]) -> CrossDocResult:
    """
    Check that every shared field has the same value across all documents
    AND that required fields are present on their expected doc types.
    Returns CrossDocResult with one CrossDocVerdict per shared field.
    """
    verdicts: list[CrossDocVerdict] = []

    # Per-doc-type required-field check: catch missing mandatory fields early.
    missing_errors: list[str] = []
    for doc in docs:
        normalised_type = _DOC_TYPE_NORM.get(doc.doc_type, doc.doc_type)
        required = _REQUIRED_BY_DOC_TYPE.get(normalised_type, [])
        for field in required:
            fv = doc.get_field(field)
            if fv is None or fv.value is None:
                missing_errors.append(
                    f"{field} is required on {doc.doc_type} but was not extracted"
                )

    for field in _SHARED_FIELDS:
        values_by_doc: dict[str, str | None] = {}
        for i, doc in enumerate(docs):
            fv = doc.get_field(field)
            values_by_doc[f"{doc.doc_type}[{i}]"] = fv.value

        present_normalised = [_norm(v) for v in values_by_doc.values() if _norm(v)]

        if len(present_normalised) < 2:
            status = "insufficient_data"
            reason = f"{field} present in fewer than 2 documents; cannot cross-check"
        elif len(set(present_normalised)) == 1:
            status = "consistent"
            reason = f"{field} agrees across {len(present_normalised)} document(s)"
        else:
            status = "inconsistent"
            pairs = ", ".join(
                f"{doc}: '{val}'" for doc, val in values_by_doc.items() if val
            )
            reason = f"{field} differs across documents: {pairs}"

        verdicts.append(CrossDocVerdict(
            field=field,
            status=status,
            values_by_doc=values_by_doc,
            reason=reason,
        ))

    # A missing required field is treated as an inconsistency — it forces
    # draft_amendment so the operator is not silently approving an incomplete doc.
    if missing_errors:
        for err in missing_errors:
            verdicts.append(CrossDocVerdict(
                field="missing_required_field",
                status="inconsistent",
                values_by_doc={"error": err},
                reason=err,
            ))

    all_consistent = all(
        v.status != "inconsistent" for v in verdicts
    )
    return CrossDocResult(verdicts=verdicts, all_consistent=all_consistent)
