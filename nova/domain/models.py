from pydantic import BaseModel, Field, model_validator
from typing import Literal, Optional
from datetime import datetime


class FieldValue(BaseModel):
    value: Optional[str] = None
    confidence: float = Field(ge=0.0, le=1.0)
    source_snippet: Optional[str] = None
    source_page: Optional[int] = None

    @model_validator(mode="after")
    def cap_confidence_without_snippet(self) -> "FieldValue":
        if self.source_snippet is None and self.confidence > 0.3:
            self.confidence = 0.3
        return self


class ExtractedDoc(BaseModel):
    doc_type: str
    consignee_name: FieldValue
    hs_code: FieldValue
    port_of_loading: FieldValue
    port_of_discharge: FieldValue
    incoterms: FieldValue
    description_of_goods: FieldValue
    gross_weight: FieldValue
    invoice_number: FieldValue

    def field_names(self) -> list[str]:
        return [
            "consignee_name", "hs_code", "port_of_loading", "port_of_discharge",
            "incoterms", "description_of_goods", "gross_weight", "invoice_number",
        ]

    def get_field(self, name: str) -> FieldValue:
        return getattr(self, name)


class FieldVerdict(BaseModel):
    field: str
    status: Literal["match", "mismatch", "uncertain"]
    found: Optional[str] = None
    expected: Optional[str] = None
    confidence: float
    reason: str


class ValidationResult(BaseModel):
    verdicts: list[FieldVerdict]
    overall_confidence: float


# ── Part 2: Cross-document consistency models ──────────────────────────────────

class CrossDocVerdict(BaseModel):
    field: str
    status: Literal["consistent", "inconsistent", "insufficient_data"]
    values_by_doc: dict[str, Optional[str]]  # {"BOL[0]": "ACME...", "INVOICE[1]": "ACME..."}
    reason: str


class CrossDocResult(BaseModel):
    verdicts: list[CrossDocVerdict]
    all_consistent: bool  # True only when no verdict is "inconsistent"


# ── Decision (extended with approval_email for Part 2) ─────────────────────────

class Decision(BaseModel):
    action: Literal["auto_approve", "flag_for_review", "draft_amendment"]
    reasoning: str
    amendment_email: Optional[str] = None
    approval_email: Optional[str] = None   # Part 2: pre-drafted approval for CG to send


# ── PipelineState (extended with Part 2 fields, all backward-compatible) ───────

class PipelineState(BaseModel):
    trace_id: str
    raw_doc_paths: list[str]
    extracted: Optional[ExtractedDoc] = None        # Part 1 single-doc extraction
    validation: Optional[ValidationResult] = None   # Part 1 single-doc validation
    decision: Optional[Decision] = None
    step: str = "scope"
    retries: int = 0
    cost_usd: float = 0.0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    rules_data: Optional[dict] = None
    # Part 2 extensions — optional, default-valued so Part 1 checkpoints still load
    extracted_docs: list[ExtractedDoc] = []
    per_doc_validation: list[ValidationResult] = []
    cross_doc: Optional[CrossDocResult] = None
    customer: Optional[str] = None
    email_meta: Optional[dict] = None
