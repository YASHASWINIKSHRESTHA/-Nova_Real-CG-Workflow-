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


class Decision(BaseModel):
    action: Literal["auto_approve", "flag_for_review", "draft_amendment"]
    reasoning: str
    amendment_email: Optional[str] = None


class PipelineState(BaseModel):
    trace_id: str
    raw_doc_paths: list[str]
    extracted: Optional[ExtractedDoc] = None
    validation: Optional[ValidationResult] = None
    decision: Optional[Decision] = None
    step: str = "scope"
    retries: int = 0
    cost_usd: float = 0.0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    rules_data: Optional[dict] = None
