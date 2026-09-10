"""Deterministic monthly retirement scenarios; no investment or purchase recommendations."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import Field
from sqlalchemy import insert, select, update

from .domain import Currency, StrictModel
from .household import HouseholdService
from .household_domain import Money, ShortText
from .models import retirement_plans, retirement_snapshots
from .service import ConflictError, NotFoundError, _hash_json, _new_id, _now

ALGORITHM = "retirement-monthly-gap-v1"


class RetirementIncome(StrictModel):
    label: ShortText
    monthly_amount: Money | None = None
    kind: Literal["GUARANTEED", "ESTIMATE", "NON_GUARANTEED"] = "ESTIMATE"
    source_note: str = Field(default="", max_length=1000)


class RetirementInput(StrictModel):
    name: ShortText
    person_id: str | None = None
    retirement_date: date | None = None
    currency: Currency = "CNY"
    monthly_expense: Money | None = None
    incomes: list[RetirementIncome] = Field(default_factory=list, max_length=30)
    income_inventory_complete: bool = False
    notes: str = Field(default="", max_length=2000)


class RetirementUpdate(RetirementInput):
    expected_revision: int = Field(ge=1)


class RetirementScenario(StrictModel):
    name: str
    monthly_income: str
    monthly_expense: str
    monthly_gap: str
    monthly_surplus: str


class RetirementResult(StrictModel):
    status: Literal["INCOMPLETE", "READY"]
    missing_inputs: list[str]
    algorithm_version: str = ALGORITHM
    input_hash: str
    currency: str
    valuation_date: date | None
    scenarios: list[RetirementScenario]
    assumptions: list[str]
    value_origin: Literal["DETERMINISTIC_CALCULATION"] = "DETERMINISTIC_CALCULATION"
    verification_status: Literal["UNVERIFIED"] = "UNVERIFIED"


class RetirementView(RetirementInput):
    id: str
    revision: int
    updated_at: str
    result: RetirementResult


class RetirementSnapshot(StrictModel):
    id: str
    plan_id: str
    created_at: str
    inputs: RetirementInput
    result: RetirementResult


def calculate_retirement(inputs: RetirementInput) -> RetirementResult:
    missing = []
    if not inputs.person_id:
        missing.append("规划对象")
    if not inputs.retirement_date:
        missing.append("退休收支参考日期")
    if inputs.monthly_expense is None:
        missing.append("退休时点月度支出预算")
    if not inputs.income_inventory_complete:
        missing.append("确认已登记目前已知收入（无收入也需明确确认）")
    if any(income.monthly_amount is None for income in inputs.incomes):
        missing.append("收入金额")
    scenarios = []
    if not missing:
        expense = Decimal(inputs.monthly_expense)
        for label, kinds in [
            ("仅用户标记的确定收入", {"GUARANTEED"}),
            ("加上用户估计收入", {"GUARANTEED", "ESTIMATE"}),
            ("再加入非保证演示收入", {"GUARANTEED", "ESTIMATE", "NON_GUARANTEED"}),
        ]:
            total = sum(
                (Decimal(i.monthly_amount) for i in inputs.incomes if i.kind in kinds), Decimal(0)
            )
            scenarios.append(
                RetirementScenario(
                    name=label,
                    monthly_income=f"{total:.2f}",
                    monthly_expense=f"{expense:.2f}",
                    monthly_gap=f"{max(Decimal(0), expense - total):.2f}",
                    monthly_surplus=f"{max(Decimal(0), total - expense):.2f}",
                )
            )
    return RetirementResult(
        status="INCOMPLETE" if missing else "READY",
        missing_inputs=missing,
        input_hash=_hash_json(inputs.model_dump(mode="json")),
        currency=inputs.currency,
        valuation_date=inputs.retirement_date,
        scenarios=scenarios,
        assumptions=[
            "所有金额均为所选参考时点、同一币种的月度净收支，由用户填写；不自动把今天购买力换算为未来金额。",
            "确定收入仅表示用户标记，合同保证属性尚需证据核验。估计和非保证收入不进入第一种情景。",
            "基础情景不计算通胀、税费、汇率、投资收益、寿命或退保价值；不将身故利益计为日常养老收入。",
            "月度缺口 = max(支出 − 当前情景收入, 0)；不代表推荐购买某种保险。",
        ],
    )


class RetirementService:
    def __init__(self, family: HouseholdService):
        self.family = family

    def get(self, identifier: str) -> RetirementView:
        with self.family.core.db.family.connect() as connection:
            row = connection.execute(
                select(retirement_plans).where(retirement_plans.c.id == identifier)
            ).first()
        if not row:
            raise NotFoundError("找不到这份养老目标")
        payload = self.family.unpack(row.payload_encrypted)
        return RetirementView(
            **payload["inputs"],
            id=row.id,
            revision=row.revision,
            updated_at=row.updated_at,
            result=payload["result"],
        )

    def list(self) -> list[RetirementView]:
        with self.family.core.db.family.connect() as connection:
            identifiers = (
                connection.execute(
                    select(retirement_plans.c.id).order_by(retirement_plans.c.updated_at.desc())
                )
                .scalars()
                .all()
            )
        return [self.get(identifier) for identifier in identifiers]

    def save(self, request: RetirementInput, identifier: str | None = None) -> RetirementView:
        if request.person_id:
            self.family.member(request.person_id)
        inputs = RetirementInput.model_validate(request.model_dump(exclude={"expected_revision"}))
        result = calculate_retirement(inputs)
        payload = {
            "inputs": inputs.model_dump(mode="json"),
            "result": result.model_dump(mode="json"),
        }
        previous = self.get(identifier) if identifier else None
        now = _now()
        with self.family.core.db.family.begin() as connection:
            values = {
                "person_id": inputs.person_id,
                "payload_encrypted": self.family.pack(payload),
                "updated_at": now,
            }
            if identifier:
                if not isinstance(request, RetirementUpdate):
                    raise ConflictError("更新养老目标需要版本号")
                saved = connection.execute(
                    update(retirement_plans)
                    .where(
                        retirement_plans.c.id == identifier,
                        retirement_plans.c.revision == request.expected_revision,
                    )
                    .values(**values, revision=request.expected_revision + 1)
                )
                if saved.rowcount != 1:
                    raise ConflictError("养老目标已被更新，请重新读取后再保存")
            else:
                identifier = _new_id("PLAN")
                connection.execute(
                    insert(retirement_plans).values(id=identifier, **values, created_at=now)
                )
            connection.execute(
                insert(retirement_snapshots).values(
                    id=_new_id("SNAP"),
                    plan_id=identifier,
                    payload_encrypted=self.family.pack(payload),
                    input_hash=result.input_hash,
                    created_at=now,
                )
            )
            self.family.audit(
                connection,
                "RETIREMENT",
                identifier,
                "UPDATED" if previous else "CREATED",
                previous.model_dump(mode="json") if previous else None,
                payload,
            )
        return self.get(identifier)

    def snapshots(self, identifier: str) -> list[RetirementSnapshot]:
        self.get(identifier)
        with self.family.core.db.family.connect() as connection:
            rows = connection.execute(
                select(retirement_snapshots)
                .where(retirement_snapshots.c.plan_id == identifier)
                .order_by(retirement_snapshots.c.created_at.desc())
            ).all()
        return [
            RetirementSnapshot(
                id=row.id,
                plan_id=row.plan_id,
                created_at=row.created_at,
                **self.family.unpack(row.payload_encrypted),
            )
            for row in rows
        ]

    def reproduce(self, identifier: str, snapshot_id: str) -> RetirementResult:
        snapshot = next(
            (item for item in self.snapshots(identifier) if item.id == snapshot_id), None
        )
        if not snapshot:
            raise NotFoundError("找不到这个计算版本")
        if snapshot.result.algorithm_version != ALGORITHM:
            raise ConflictError("当前计算器不支持此历史算法版本，请查看原始快照")
        reproduced = calculate_retirement(snapshot.inputs)
        if reproduced.model_dump(mode="json") != snapshot.result.model_dump(mode="json"):
            raise ConflictError("复算结果与历史快照不一致，已保留原始记录供核对")
        return reproduced
