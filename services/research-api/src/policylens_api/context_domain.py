"""Explicit external allowlist for single-product and retirement explanations."""

from typing import Literal, Self

from pydantic import Field, model_validator

from .domain import (
    CodexAnalysisResult,
    CodexExternalEvidence,
    CodexExternalProduct,
    Currency,
    StrictModel,
)


class ExternalScenario(StrictModel):
    name: str = Field(max_length=80)
    monthly_income: str = Field(pattern=r"^\d{1,16}\.\d{2}$")
    monthly_expense: str = Field(pattern=r"^\d{1,16}\.\d{2}$")
    monthly_gap: str = Field(pattern=r"^\d{1,16}\.\d{2}$")
    monthly_surplus: str = Field(pattern=r"^\d{1,16}\.\d{2}$")


class ExternalCalculation(StrictModel):
    reference: str = Field(pattern=r"^CALC-[A-F0-9]{16}$")
    algorithm: Literal["retirement-monthly-gap-v1"]
    currency: Currency
    scenarios: list[ExternalScenario] = Field(min_length=3, max_length=3)
    assumptions: list[str] = Field(max_length=8)


class ExplanationPayload(StrictModel):
    schema_version: Literal["context-v1"] = "context-v1"
    task: Literal["EXPLAIN_POLICY", "EXPLAIN_RETIREMENT"]
    product: CodexExternalProduct | None = None
    evidence_excerpts: list[CodexExternalEvidence] = Field(default_factory=list, max_length=12)
    calculation: ExternalCalculation | None = None

    @model_validator(mode="after")
    def scope(self) -> Self:
        if self.task == "EXPLAIN_POLICY" and (not self.product or self.calculation):
            raise ValueError("单保单解读只允许已选的产品资料")
        if self.task == "EXPLAIN_RETIREMENT" and (
            not self.calculation or self.product or self.evidence_excerpts
        ):
            raise ValueError("养老解释只允许确定性计算摘要")
        ids = {item.evidenceId for item in self.evidence_excerpts}
        if (
            len(ids) != len(self.evidence_excerpts)
            or sum(len(e.text) for e in self.evidence_excerpts) > 7200
        ):
            raise ValueError("证据数量、去重或长度不符合外发限制")
        if self.product and any(not set(f.evidenceIds).issubset(ids) for f in self.product.facts):
            raise ValueError("字段引用了预览之外的证据")
        return self


class ExplanationPreviewRequest(StrictModel):
    scope: Literal["POLICY", "RETIREMENT"]
    target_id: str = Field(max_length=40)
    snapshot_id: str | None = Field(default=None, max_length=40)
    evidence_ids: list[str] | None = Field(default=None, max_length=12)


class ExplanationRunRequest(StrictModel):
    confirmed: Literal[True]
    preview_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class ExplanationView(StrictModel):
    id: str
    scope: Literal["POLICY", "RETIREMENT"]
    target_id: str
    snapshot_id: str | None
    status: Literal[
        "PREVIEW", "RUNNING", "DRAFT", "ACCEPTED_AS_NOTE", "REJECTED", "FAILED", "CANCELLED"
    ]
    created_at: str
    preview_hash: str
    payload: ExplanationPayload
    result: CodexAnalysisResult | None = None
    error: str | None = None
    stale: bool
    will_send: list[str]
    will_not_send: list[str]
