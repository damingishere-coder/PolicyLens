from __future__ import annotations

from typing import Literal, Self

from pydantic import Field, model_validator
from sqlalchemy import insert, select

from .domain import Currency, StrictModel
from .household import HouseholdService
from .household_domain import Money, ShortText
from .models import comparison_records
from .service import ConflictError, NotFoundError, _hash_json, _new_id, _now


class FamilyComparisonInput(StrictModel):
    purpose: ShortText
    person_id: str | None = None
    age: int | None = Field(default=None, ge=0, le=130)
    jurisdiction: Literal["CN_MAINLAND", "HK"] | None = None
    currency: Currency | None = None
    annual_budget: Money | None = None
    payment_term: str = Field(default="", max_length=100)
    benefit_term: str = Field(default="", max_length=100)
    product_version_ids: list[str] = Field(min_length=2, max_length=4)

    @model_validator(mode="after")
    def distinct(self) -> Self:
        if len(set(self.product_version_ids)) != len(self.product_version_ids):
            raise ValueError("请选择不同的产品版本")
        return self


class ComparisonCell(StrictModel):
    product_version_id: str
    value: str | None
    verification_status: str
    guarantee_type: str
    evidence_ids: list[str]


class ComparisonDifference(StrictModel):
    field: str
    label: str
    cells: list[ComparisonCell]


class FamilyComparisonView(StrictModel):
    id: str
    created_at: str
    inputs: FamilyComparisonInput
    input_hash: str
    product_names: list[str]
    blockers: list[str]
    questions: list[str]
    differences: list[ComparisonDifference]
    evidence_complete: bool
    stale: bool
    algorithm_version: Literal["family-comparison-v1"] = "family-comparison-v1"


FIELD_LABELS = {
    "benefit.limit": "责任限额",
    "premium_rate.amount": "标准费率参考",
    "renewal_terms.renewal_mode": "续保条件",
    "renewal_terms.guarantee_period_years": "保证续保期间",
    "renewal_terms.maximum_renewal_age": "最高续保年龄",
    "rate_adjustment_rule.scope": "调费范围",
    "product.payment_term": "缴费期间",
    "product.issue_age": "投保年龄范围",
    "product.benefit_term": "保障或领取期间",
    "product.guarantee_summary": "保证利益",
    "product.non_guaranteed_summary": "非保证利益",
    "risk.surrender": "退保限制与风险",
    "risk.exchange_rate": "汇率风险",
    "risk.non_guaranteed": "非保证风险",
}


class FamilyComparisons:
    def __init__(self, family: HouseholdService):
        self.family = family

    def _products(self, ids: list[str]):
        products = [self.family.core.get_product(identifier) for identifier in ids]
        if any(product["record_status"] != "ACTIVE" for product in products):
            raise ConflictError("正式比较只接受已核验产品；未核验候选仍可在研究工作台查看")
        return products

    def save(self, request: FamilyComparisonInput) -> FamilyComparisonView:
        if request.person_id:
            self.family.member(request.person_id)
        products = self._products(request.product_version_ids)
        blockers, questions = [], []
        for key, label in [
            ("jurisdiction", "适用地区"),
            ("currency", "币种"),
            ("line_of_business", "险种"),
        ]:
            if len({product[key] for product in products}) > 1:
                blockers.append(f"产品{label}不同，不可直接按金额或收益排序")
        if request.currency and any(p["currency"] != request.currency for p in products):
            blockers.append("产品币种与比较目标不一致，不自动进行汇率换算")
        if request.jurisdiction and any(
            p["jurisdiction"] != request.jurisdiction for p in products
        ):
            blockers.append("产品司法辖区与目标地区不一致")
        for key, label in [
            ("person_id", "规划对象"),
            ("age", "比较年龄"),
            ("jurisdiction", "适用地区"),
            ("currency", "目标币种"),
            ("annual_budget", "年度预算"),
            ("payment_term", "目标缴费期"),
            ("benefit_term", "目标保障或领取期"),
        ]:
            if getattr(request, key) is None or getattr(request, key) == "":
                questions.append(f"{label}尚未明确")
        questions.append(
            "年龄、健康、职业、预算和期间能否适用仍需逐项核对原始条款；字段并排展示不等于已通过投保或同口径校验。"
        )
        maps = [{fact["field_path"]: fact for fact in p["facts"]} for p in products]
        differences = []
        complete = True
        for field, label in FIELD_LABELS.items():
            if not any(field in facts for facts in maps):
                continue
            cells = []
            for product, facts in zip(products, maps, strict=True):
                fact = facts.get(field)
                if not fact or fact["verification_status"] != "VERIFIED":
                    complete = False
                cells.append(
                    ComparisonCell(
                        product_version_id=product["version_id"],
                        value=(
                            f"{fact['normalized_value']} {fact['unit'] or ''}".strip()
                            if fact
                            else None
                        ),
                        verification_status=fact["verification_status"] if fact else "UNVERIFIED",
                        guarantee_type=fact["guarantee_type"] if fact else "UNKNOWN",
                        evidence_ids=[item["id"] for item in fact["evidence"]] if fact else [],
                    )
                )
            differences.append(ComparisonDifference(field=field, label=label, cells=cells))
        if not differences:
            complete = False
            questions.append("缺少可用于需求比较的责任、费用与限制字段")
        if not complete:
            questions.append("部分字段缺失或未核验，不能据此推断哪款更适合")
        identifier = _new_id("CASE")
        view = FamilyComparisonView(
            id=identifier,
            created_at=_now(),
            inputs=request,
            input_hash=_hash_json(request.model_dump(mode="json")),
            product_names=[p["display_name"] for p in products],
            blockers=blockers,
            questions=questions,
            differences=differences,
            evidence_complete=complete,
            stale=False,
        )
        payload = {"view": view.model_dump(mode="json"), "product_hash": _hash_json(products)}
        with self.family.core.db.family.begin() as connection:
            connection.execute(
                insert(comparison_records).values(
                    id=identifier,
                    payload_encrypted=self.family.pack(payload),
                    created_at=view.created_at,
                )
            )
        return view

    def get(self, identifier: str) -> FamilyComparisonView:
        with self.family.core.db.family.connect() as connection:
            row = connection.execute(
                select(comparison_records).where(comparison_records.c.id == identifier)
            ).first()
        if not row:
            raise NotFoundError("找不到这份比较记录")
        payload = self.family.unpack(row.payload_encrypted)
        view = FamilyComparisonView.model_validate(payload["view"])
        try:
            view.stale = (
                _hash_json(self._products(view.inputs.product_version_ids))
                != payload["product_hash"]
            )
        except (NotFoundError, ConflictError):
            view.stale = True
        return view

    def list(self) -> list[FamilyComparisonView]:
        with self.family.core.db.family.connect() as connection:
            ids = (
                connection.execute(
                    select(comparison_records.c.id).order_by(comparison_records.c.created_at.desc())
                )
                .scalars()
                .all()
            )
        return [self.get(identifier) for identifier in ids]
