"""Local family contracts. None of these objects is a Codex external DTO."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal, Self

from pydantic import Field, StringConstraints, model_validator

from .domain import Currency, StrictModel

ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
Money = Annotated[str, StringConstraints(pattern=r"^\d{1,12}(?:\.\d{1,2})?$")]
Frequency = Literal["MONTHLY", "QUARTERLY", "SEMI_ANNUAL", "ANNUAL", "SINGLE"]
PolicyLine = Literal[
    "MEDICAL",
    "ACCIDENT",
    "HUIMIN",
    "CRITICAL_ILLNESS",
    "ANNUITY",
    "LIFE_SAVINGS",
    "LIFE",
    "PET",
    "OTHER",
    "UNKNOWN",
]


class MemberInput(StrictModel):
    nickname: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]
    relationship: Literal["SELF", "PARENT", "PARTNER", "CHILD", "OTHER"] = "OTHER"
    age: int | None = Field(default=None, ge=0, le=130)
    age_as_of: date | None = None
    archived: bool = False

    @model_validator(mode="after")
    def age_reference(self) -> Self:
        if (self.age is None) != (self.age_as_of is None):
            raise ValueError("年龄与参考日期需要同时填写或同时留空")
        return self


class MemberUpdate(MemberInput):
    expected_revision: int = Field(ge=1)


class MemberView(MemberInput):
    id: str
    revision: int
    policy_count: int
    possible_duplicate_ids: list[str]


class PolicyInput(StrictModel):
    name: ShortText
    person_id: str | None = None
    product_version_id: str | None = None
    owner_id: str | None = None
    payer_id: str | None = None
    insurer: str = Field(default="", max_length=160)
    line: PolicyLine = "UNKNOWN"
    category: Literal["CORE", "GROUP", "GIFT", "UNCONFIRMED"] = "UNCONFIRMED"
    status: Literal["DRAFT", "ACTIVE", "EXPIRED", "ARCHIVED"] = "DRAFT"
    start_date: date | None = None
    end_date: date | None = None
    lifetime: bool = False
    coverage_summary: str = Field(default="", max_length=2000)
    exclusions: str = Field(default="", max_length=2000)
    personal_terms: str = Field(default="", max_length=2000)
    notes: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def dates(self) -> Self:
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("终止日期不能早于生效日期")
        if self.lifetime and self.end_date:
            raise ValueError("终身保障不能同时填写终止日期")
        if self.status == "ACTIVE" and (
            not self.start_date or not (self.end_date or self.lifetime)
        ):
            raise ValueError("确认保障状态前请填写生效日及终止日，或明确终身保障")
        return self


class PolicyUpdate(PolicyInput):
    expected_revision: int = Field(ge=1)


class PaymentInput(StrictModel):
    due_amount: Money
    due_date: date
    currency: Currency = "CNY"
    frequency: Frequency = "ANNUAL"
    paid_amount: Money | None = None
    paid_date: date | None = None

    @model_validator(mode="after")
    def payment_pair(self) -> Self:
        if (self.paid_amount is None) != (self.paid_date is None):
            raise ValueError("实缴金额和实缴日期需要同时填写，尚未缴费请都留空")
        if self.paid_date and self.paid_date > date.today():
            raise ValueError("未来日期不能登记为已经缴费")
        return self


class PaymentUpdate(PaymentInput):
    expected_revision: int = Field(ge=1)


class PaymentView(PaymentInput):
    id: str
    revision: int


class PolicyView(PolicyInput):
    id: str
    revision: int
    member_nickname: str | None
    coverage_state: Literal["UNKNOWN", "SCHEDULED", "IN_PERIOD", "ENDED", "ARCHIVED"]
    missing_fields: list[str]
    premium_records: list[PaymentView]
    value_origin: Literal["MANUAL_ENTRY"] = "MANUAL_ENTRY"
    verification_status: Literal["UNVERIFIED"] = "UNVERIFIED"

    @model_validator(mode="after")
    def dates(self) -> Self:
        # Legacy ACTIVE records lack dates; expose UNKNOWN coverage without rewriting them.
        return self


class PolicyHistoryView(StrictModel):
    id: str
    action: str
    created_at: str


class TaskInput(StrictModel):
    title: ShortText
    policy_id: str | None = None
    due_date: date | None = None


class TaskAction(StrictModel):
    status: Literal["OPEN", "DONE", "SNOOZED"]
    snoozed_until: date | None = None
    expected_revision: int = Field(ge=0)

    @model_validator(mode="after")
    def snooze(self) -> Self:
        if self.status == "SNOOZED" and (
            not self.snoozed_until or self.snoozed_until <= date.today()
        ):
            raise ValueError("延期日期必须晚于今天")
        if self.status != "SNOOZED" and self.snoozed_until:
            raise ValueError("只有延期事项可以设置延期日期")
        return self


class TaskView(TaskInput):
    id: str
    kind: Literal["PAYMENT", "EXPIRY", "INFORMATION", "CUSTOM"]
    status: Literal["OPEN", "DONE", "SNOOZED"]
    snoozed_until: date | None = None
    revision: int
    reason: str
    href: str


class CurrencyTotal(StrictModel):
    currency: str
    paid_this_year: str
    outstanding_registered: str


class HouseholdSummary(StrictModel):
    as_of: date
    year: int
    members: list[MemberView]
    policies: list[PolicyView]
    tasks: list[TaskView]
    totals: list[CurrencyTotal]
    policies_without_payments: int
    disclaimer: str
