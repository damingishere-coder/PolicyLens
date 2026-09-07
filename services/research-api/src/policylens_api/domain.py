from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class VerificationStatus(StrEnum):
    UNVERIFIED = "UNVERIFIED"
    VERIFIED = "VERIFIED"
    CONFLICTING = "CONFLICTING"
    STALE = "STALE"
    REJECTED = "REJECTED"


class ValueOrigin(StrEnum):
    MANUAL_ENTRY = "MANUAL_ENTRY"
    STRUCTURED_IMPORT = "STRUCTURED_IMPORT"
    RULE_EXTRACTION = "RULE_EXTRACTION"
    AI_EXTRACTION = "AI_EXTRACTION"
    DETERMINISTIC_CALCULATION = "DETERMINISTIC_CALCULATION"
    USER_ASSUMPTION = "USER_ASSUMPTION"


class SourceAuthority(StrEnum):
    CONTRACT_DOCUMENT = "CONTRACT_DOCUMENT"
    REGULATOR_PUBLICATION = "REGULATOR_PUBLICATION"
    INSURER_OFFICIAL_DISCLOSURE = "INSURER_OFFICIAL_DISCLOSURE"
    INSURER_OFFICIAL_WEB = "INSURER_OFFICIAL_WEB"
    THIRD_PARTY_REFERENCE = "THIRD_PARTY_REFERENCE"
    UNATTRIBUTED = "UNATTRIBUTED"


class GuaranteeType(StrEnum):
    CONTRACT_GUARANTEED = "CONTRACT_GUARANTEED"
    NON_GUARANTEED = "NON_GUARANTEED"
    UNKNOWN = "UNKNOWN"


class AnalysisStatus(StrEnum):
    DRAFT = "DRAFT"
    ACCEPTED_AS_NOTE = "ACCEPTED_AS_NOTE"
    REJECTED = "REJECTED"


class RenewalMode(StrEnum):
    GUARANTEED_RENEWAL = "GUARANTEED_RENEWAL"
    CONDITIONAL_RENEWAL = "CONDITIONAL_RENEWAL"
    NON_GUARANTEED_RENEWAL = "NON_GUARANTEED_RENEWAL"
    NON_RENEWABLE = "NON_RENEWABLE"
    UNKNOWN = "UNKNOWN"


class RateAdjustmentScope(StrEnum):
    INDIVIDUAL = "INDIVIDUAL"
    COHORT = "COHORT"
    PORTFOLIO = "PORTFOLIO"
    REGULATORY = "REGULATORY"
    UNKNOWN = "UNKNOWN"


class ImportStatus(StrEnum):
    WAITING_REVIEW = "WAITING_REVIEW"
    COMPLETED = "COMPLETED"
    REJECTED = "REJECTED"


Currency = Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")]
DecimalString = Annotated[str, StringConstraints(pattern=r"^-?\d+(?:\.\d{1,4})?$")]


class RenewalTerms(StrictModel):
    renewal_mode: RenewalMode = RenewalMode.UNKNOWN
    guarantee_period_years: int | None = Field(default=None, ge=0, le=100)
    maximum_renewal_age: int | None = Field(default=None, ge=0, le=130)
    requires_reunderwriting: bool | None = None
    reassesses_health: bool | None = None
    waiting_period_days: int | None = Field(default=None, ge=0, le=3650)
    continuity_conditions: str | None = Field(default=None, max_length=1000)
    discontinuation_treatment: str | None = Field(default=None, max_length=1000)
    termination_conditions: str | None = Field(default=None, max_length=1000)


class PremiumRate(StrictModel):
    version_label: str = Field(min_length=1, max_length=100)
    valid_from: date | None = None
    valid_to: date | None = None
    currency: Currency
    frequency: Literal["MONTHLY", "QUARTERLY", "SEMI_ANNUAL", "ANNUAL", "SINGLE"]
    amount: DecimalString
    pricing_dimensions: dict[str, str] = Field(default_factory=dict)

    @field_validator("amount")
    @classmethod
    def amount_non_negative(cls, value: str) -> str:
        if Decimal(value) < 0:
            raise ValueError("standard premium cannot be negative")
        return value


class RateAdjustmentRule(StrictModel):
    scope: RateAdjustmentScope = RateAdjustmentScope.UNKNOWN
    trigger_conditions: str | None = Field(default=None, max_length=1000)
    frequency: str | None = Field(default=None, max_length=100)
    notice_days: int | None = Field(default=None, ge=0, le=3650)
    cap: DecimalString | None = None
    floor: DecimalString | None = None
    effective_from: date | None = None


class PolicyPremiumRecord(StrictModel):
    id: str
    due_amount: DecimalString
    paid_amount: DecimalString | None = None
    currency: Currency
    frequency: Literal["MONTHLY", "QUARTERLY", "SEMI_ANNUAL", "ANNUAL", "SINGLE"]
    due_date: date
    paid_date: date | None = None
    premium_rate_id: str | None = None


class ManualMaterialRequest(StrictModel):
    display_name: str = Field(min_length=1, max_length=120)
    version_label: str = Field(default="手工版本 1", min_length=1, max_length=100)
    jurisdiction: Literal["CN_MAINLAND", "HK"]
    line_of_business: Literal[
        "MEDICAL", "ACCIDENT", "CRITICAL_ILLNESS", "ANNUITY", "LIFE_SAVINGS", "OTHER"
    ]
    currency: Currency
    annual_premium: DecimalString
    renewal_mode: RenewalMode
    guarantee_period_years: int | None = Field(default=None, ge=0, le=100)
    maximum_renewal_age: int | None = Field(default=None, ge=0, le=130)
    rate_adjustment_scope: RateAdjustmentScope
    benefit_limit: DecimalString | None = None
    source_authority: SourceAuthority = SourceAuthority.UNATTRIBUTED
    evidence_note: str = Field(min_length=1, max_length=600)


class CandidateDecision(StrictModel):
    candidate_id: str
    decision: Literal["ACCEPT", "EDIT", "REJECT", "KEEP_UNVERIFIED"]
    edited_value: str | None = Field(default=None, max_length=1000)

    @field_validator("edited_value")
    @classmethod
    def edited_value_required(cls, value: str | None, info):
        if info.data.get("decision") == "EDIT" and not value:
            raise ValueError("EDIT requires edited_value")
        return value


class ImportReviewRequest(StrictModel):
    decisions: list[CandidateDecision] = Field(min_length=1, max_length=50)


class PolicyCreateRequest(StrictModel):
    member_nickname: str = Field(min_length=1, max_length=40)
    product_version_id: str
    category: Literal["CORE", "GROUP", "GIFT", "UNCONFIRMED"]
    status: Literal["DRAFT", "ACTIVE", "EXPIRED", "ARCHIVED"] = "ACTIVE"
    due_amount: DecimalString
    paid_amount: DecimalString | None = None
    currency: Currency
    frequency: Literal["MONTHLY", "QUARTERLY", "SEMI_ANNUAL", "ANNUAL", "SINGLE"]
    due_date: date
    paid_date: date | None = None


class CodexPreviewRequest(StrictModel):
    product_version_ids: list[str] = Field(min_length=2, max_length=2)
    evidence_ids: list[str] | None = Field(default=None, max_length=12)

    @field_validator("product_version_ids")
    @classmethod
    def unique_products(cls, value: list[str]) -> list[str]:
        if len(set(value)) != 2:
            raise ValueError("two distinct product versions are required")
        return value

    @field_validator("evidence_ids")
    @classmethod
    def unique_evidence(cls, value: list[str] | None) -> list[str] | None:
        if value is not None and len(value) != len(set(value)):
            raise ValueError("evidence ids must be unique")
        return value


class CodexExternalEvidence(StrictModel):
    evidenceId: str = Field(pattern=r"^EV-[A-Z0-9-]+$")
    text: str = Field(max_length=600)
    authority: SourceAuthority


class CodexExternalFact(StrictModel):
    field: str = Field(max_length=120)
    value: str = Field(max_length=1200)
    unit: str | None = Field(default=None, max_length=40)
    guaranteeType: GuaranteeType
    verificationStatus: VerificationStatus
    valueOrigin: ValueOrigin
    evidenceIds: list[str] = Field(max_length=12)


class CodexExternalProduct(StrictModel):
    publicId: str = Field(pattern=r"^PUB-[A-F0-9]+$")
    displayName: str = Field(max_length=160)
    versionLabel: str = Field(max_length=100)
    jurisdiction: str = Field(max_length=30)
    currency: Currency
    facts: list[CodexExternalFact] = Field(max_length=50)


class CodexExternalComparison(StrictModel):
    products: list[CodexExternalProduct] = Field(min_length=2, max_length=2)
    evidenceExcerpts: list[CodexExternalEvidence] = Field(max_length=12)

    @model_validator(mode="after")
    def validate_evidence_boundary(self):
        if len({item.publicId for item in self.products}) != 2:
            raise ValueError("two distinct public product ids are required")
        evidence_ids = {item.evidenceId for item in self.evidenceExcerpts}
        if len(evidence_ids) != len(self.evidenceExcerpts):
            raise ValueError("evidence ids must be unique")
        if sum(len(item.text) for item in self.evidenceExcerpts) > 7200:
            raise ValueError("evidence excerpts exceed the 7200-character limit")
        fact_evidence = {
            evidence_id
            for product in self.products
            for fact in product.facts
            for evidence_id in fact.evidenceIds
        }
        if not fact_evidence.issubset(evidence_ids):
            raise ValueError("facts reference evidence outside the approved preview")
        return self


class CodexExternalPayload(StrictModel):
    schemaVersion: Literal["1.0"]
    comparison: CodexExternalComparison


class CodexRunRequest(StrictModel):
    confirmed: Literal[True]
    payload: CodexExternalPayload


class CodexDifference(StrictModel):
    title: str = Field(max_length=200)
    explanation: str = Field(max_length=2000)
    evidence_ids: list[str] = Field(max_length=12)


class CodexAnalysisResult(StrictModel):
    summary: str = Field(max_length=4000)
    differences: list[CodexDifference] = Field(max_length=20)
    unknowns: list[str] = Field(max_length=30)
    risks: list[str] = Field(max_length=30)
    questions_for_human_review: list[str] = Field(max_length=30)
    calculation_refs: list[str] = Field(max_length=30)


class SaveAnalysisRequest(StrictModel):
    preview_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    evidence_ids: list[str] = Field(max_length=12)
    result: CodexAnalysisResult
    cli_version: str = Field(max_length=120)
    argument_profile: Literal["EPHEMERAL_JSON_READ_ONLY_SCHEMA_V1"]
    prompt_template_version: Literal["policylens-analysis-v1"]
    exit_status: int = 0
    schema_valid: Literal[True]


class AnalysisStatusRequest(StrictModel):
    status: Literal["ACCEPTED_AS_NOTE", "REJECTED"]


class BackupPasswordRequest(StrictModel):
    password: str = Field(min_length=12, max_length=256)


class BackupCreateRequest(BackupPasswordRequest):
    destination: str = Field(min_length=1, max_length=1000)


class RestorePreviewRequest(BackupPasswordRequest):
    source: str = Field(min_length=1, max_length=1000)


class RestoreCommitRequest(StrictModel):
    restore_token: str = Field(min_length=20, max_length=200)


class SemanticEnumsResponse(StrictModel):
    verification_statuses: list[VerificationStatus]
    value_origins: list[ValueOrigin]
    source_authorities: list[SourceAuthority]


class ResearchRunStatus(StrEnum):
    QUEUED = "QUEUED"
    DISCOVERING = "DISCOVERING"
    FETCHING = "FETCHING"
    WAITING_REVIEW = "WAITING_REVIEW"
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    INTERRUPTED = "INTERRUPTED"


InsurerId = Literal["aia-hk", "prudential-hk", "manulife-hk"]


class ResearchStartRequest(StrictModel):
    confirmed: Literal[True]
    preview_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class ResearchDiscoveryFact(StrictModel):
    field_path: str = Field(min_length=1, max_length=120, pattern=r"^[a-z][a-z0-9_.-]+$")
    value: str = Field(min_length=1, max_length=1200)
    unit: str | None = Field(default=None, max_length=40)
    guarantee_type: GuaranteeType = GuaranteeType.UNKNOWN
    evidence_excerpt: str = Field(min_length=12, max_length=600)
    page_number: int | None = Field(default=None, ge=1, le=5000)
    locator: str | None = Field(default=None, max_length=300)


class ResearchDiscoveredProduct(StrictModel):
    insurer_id: InsurerId
    display_name: str = Field(min_length=2, max_length=160)
    version_label: str = Field(min_length=1, max_length=100)
    source_title: str = Field(min_length=2, max_length=300)
    source_url: str = Field(min_length=10, max_length=2000)
    document_type: Literal["OFFICIAL_WEB", "OFFICIAL_PDF"]
    facts: list[ResearchDiscoveryFact] = Field(min_length=7, max_length=30)

    @model_validator(mode="after")
    def validate_identity_facts(self):
        fields = {item.field_path for item in self.facts}
        required = {
            "product.display_name",
            "product.version_label",
            "product.jurisdiction",
            "product.line_of_business",
            "product.currency",
            "product.insurer_id",
            "product.sale_status",
        }
        if not required.issubset(fields):
            raise ValueError("discovered product is missing required identity facts")
        if len(fields) != len(self.facts):
            raise ValueError("discovered product contains duplicate fact fields")
        return self


class ResearchDiscoveryLead(StrictModel):
    insurer_id: InsurerId
    title: str = Field(min_length=2, max_length=300)
    url: str = Field(min_length=10, max_length=2000)
    channel: Literal["OFFICIAL_SEARCH", "THIRD_PARTY_LEAD"]
    official_verification_url: str | None = Field(default=None, max_length=2000)


class ResearchDiscoveryOutput(StrictModel):
    schema_version: Literal["1.0"]
    products: list[ResearchDiscoveredProduct] = Field(max_length=15)
    leads: list[ResearchDiscoveryLead] = Field(max_length=30)


class EvidenceComparisonRequest(StrictModel):
    product_version_ids: list[str] = Field(min_length=2, max_length=4)

    @field_validator("product_version_ids")
    @classmethod
    def unique_versions(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("product versions must be unique")
        return value
