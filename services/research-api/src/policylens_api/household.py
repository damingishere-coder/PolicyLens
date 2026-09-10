"""Family workflow; private records stay in the encrypted family database."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import insert, select, update

from .household_domain import (
    HouseholdSummary,
    MemberInput,
    MemberUpdate,
    MemberView,
    PaymentInput,
    PaymentUpdate,
    PaymentView,
    PolicyInput,
    PolicyUpdate,
    PolicyView,
)
from .models import family_audit_events, persons, policies, policy_premium_records
from .service import ConflictError, NotFoundError, _hash_json, _new_id, _now, _row

if TYPE_CHECKING:
    from .service import PolicyLensService


class HouseholdService:
    def __init__(self, core: PolicyLensService) -> None:
        self.core = core

    def pack(self, payload: dict[str, Any]) -> str:
        return self.core.cipher.encrypt_text(json.dumps(payload, ensure_ascii=False))

    def unpack(self, payload: str | None) -> dict[str, Any]:
        return json.loads(self.core.cipher.decrypt_text(payload)) if payload else {}

    def audit(self, connection, entity: str, identifier: str, action: str, before, after) -> None:
        connection.execute(
            insert(family_audit_events).values(
                id=_new_id("AUD"),
                entity_type=entity,
                entity_id=identifier,
                action=action,
                before_hash=_hash_json(before) if before is not None else None,
                after_hash=_hash_json(after),
                created_at=_now(),
            )
        )

    def members(self) -> list[MemberView]:
        with self.core.db.family.connect() as connection:
            rows = connection.execute(select(persons).order_by(persons.c.created_at)).all()
            links = connection.execute(select(policies.c.person_id, policies.c.status)).all()
        values = []
        for row in rows:
            item = _row(row)
            values.append(
                MemberView(
                    **self.unpack(item["profile_encrypted"]),
                    id=item["id"],
                    nickname=self.core.cipher.decrypt_text(item["nickname_encrypted"]),
                    revision=item["revision"],
                    policy_count=sum(
                        p.person_id == item["id"] and p.status != "ARCHIVED" for p in links
                    ),
                    possible_duplicate_ids=[],
                )
            )
        for member in values:
            member.possible_duplicate_ids = [
                other.id
                for other in values
                if other.id != member.id and other.nickname == member.nickname
            ]
        return values

    def member(self, identifier: str) -> MemberView:
        for member in self.members():
            if member.id == identifier:
                return member
        raise NotFoundError("找不到这位家庭成员")

    def save_member(self, request: MemberInput, identifier: str | None = None) -> MemberView:
        previous = self.member(identifier).model_dump(mode="json") if identifier else None
        payload = request.model_dump(mode="json", exclude={"expected_revision"})
        nickname = payload.pop("nickname")
        values = {
            "nickname_encrypted": self.core.cipher.encrypt_text(nickname),
            "profile_encrypted": self.pack(payload),
        }
        with self.core.db.family.begin() as connection:
            if identifier:
                if not isinstance(request, MemberUpdate):
                    raise ConflictError("更新成员需要当前版本号")
                result = connection.execute(
                    update(persons)
                    .where(
                        persons.c.id == identifier,
                        persons.c.revision == request.expected_revision,
                    )
                    .values(**values, revision=request.expected_revision + 1)
                )
                if result.rowcount != 1:
                    raise ConflictError("成员资料已在其他页面更新，请重新读取后再保存")
            else:
                identifier = _new_id("PERSON")
                connection.execute(
                    insert(persons).values(id=identifier, **values, created_at=_now())
                )
            self.audit(
                connection,
                "PERSON",
                identifier,
                "UPDATED" if previous else "CREATED",
                previous,
                payload | {"nickname": nickname},
            )
        return self.member(identifier)

    def policy(self, identifier: str, today: date | None = None) -> PolicyView:
        today = today or date.today()
        with self.core.db.family.connect() as connection:
            row = connection.execute(select(policies).where(policies.c.id == identifier)).first()
            if row is None:
                raise NotFoundError("找不到这份保单")
            payments = connection.execute(
                select(policy_premium_records)
                .where(
                    policy_premium_records.c.policy_id == identifier,
                )
                .order_by(policy_premium_records.c.due_date, policy_premium_records.c.id)
            ).all()
        item = _row(row)
        details = self.unpack(item["details_encrypted"])
        if not details:
            product = (
                self.core.get_product(item["product_version_id"])
                if item["product_version_id"]
                else None
            )
            details = {
                "name": product["display_name"] if product else "待完善保单",
                "line": product["line_of_business"] if product else "UNKNOWN",
            }
        missing = []
        if not item["person_id"]:
            missing.append("所属成员")
        if not details.get("start_date") or not (
            details.get("end_date") or details.get("lifetime")
        ):
            missing.append("保障期间")
        if not details.get("coverage_summary"):
            missing.append("保障责任")
        if not item["product_version_id"]:
            missing.append("条款与证据关联")
        state = "UNKNOWN"
        if item["status"] == "ARCHIVED":
            state = "ARCHIVED"
        elif item["status"] == "EXPIRED":
            state = "ENDED"
        elif item["status"] == "ACTIVE" and "保障期间" not in missing:
            start = date.fromisoformat(details["start_date"])
            end = date.fromisoformat(details["end_date"]) if details.get("end_date") else None
            state = (
                "SCHEDULED" if start > today else "ENDED" if end and end < today else "IN_PERIOD"
            )
        member = self.member(item["person_id"]) if item["person_id"] else None
        return PolicyView(
            **details,
            id=item["id"],
            revision=item["revision"],
            person_id=item["person_id"],
            product_version_id=item["product_version_id"],
            category=item["category"],
            status=item["status"],
            member_nickname=member.nickname if member else None,
            coverage_state=state,
            missing_fields=missing,
            premium_records=[self.payment_view(_row(p)) for p in payments],
        )

    def list_policies(self, today: date | None = None) -> list[PolicyView]:
        with self.core.db.family.connect() as connection:
            identifiers = (
                connection.execute(select(policies.c.id).order_by(policies.c.created_at.desc()))
                .scalars()
                .all()
            )
        return [self.policy(identifier, today) for identifier in identifiers]

    def save_policy(self, request: PolicyInput, identifier: str | None = None) -> PolicyView:
        for person_id in (request.person_id, request.owner_id, request.payer_id):
            if person_id:
                self.member(person_id)
        if request.product_version_id:
            product = self.core.get_product(request.product_version_id)
            if product["record_status"] != "ACTIVE":
                raise ConflictError("只可关联已核验产品；也可以先保存不关联产品的待完善保单")
        previous = self.policy(identifier).model_dump(mode="json") if identifier else None
        payload = request.model_dump(mode="json", exclude={"expected_revision"})
        values = {
            key: payload.pop(key)
            for key in ("person_id", "product_version_id", "category", "status")
        }
        values["details_encrypted"] = self.pack(payload)
        with self.core.db.family.begin() as connection:
            if identifier:
                if not isinstance(request, PolicyUpdate):
                    raise ConflictError("更新保单需要当前版本号")
                result = connection.execute(
                    update(policies)
                    .where(
                        policies.c.id == identifier,
                        policies.c.revision == request.expected_revision,
                    )
                    .values(**values, revision=request.expected_revision + 1)
                )
                if result.rowcount != 1:
                    raise ConflictError("保单已在其他页面更新，请重新读取后再保存")
            else:
                identifier = _new_id("POL")
                connection.execute(
                    insert(policies).values(id=identifier, **values, created_at=_now())
                )
            self.audit(
                connection,
                "POLICY",
                identifier,
                "UPDATED" if previous else "CREATED",
                previous,
                request.model_dump(mode="json"),
            )
        return self.policy(identifier)

    def payment_view(self, item: dict[str, Any]) -> PaymentView:
        return PaymentView(
            **{
                key: value
                for key, value in self.core._premium_record_view(item).items()
                if key != "premium_rate_id"
            },
            revision=item["revision"],
        )

    def save_payment(
        self, policy_id: str, request: PaymentInput, identifier: str | None = None
    ) -> PaymentView:
        self.policy(policy_id)
        values = {
            "due_amount_encrypted": self.core.cipher.encrypt_text(request.due_amount),
            "paid_amount_encrypted": self.core.cipher.encrypt_text(request.paid_amount)
            if request.paid_amount is not None
            else None,
            "currency": request.currency,
            "frequency": request.frequency,
            "due_date": request.due_date.isoformat(),
            "paid_date": request.paid_date.isoformat() if request.paid_date else None,
        }
        previous = None
        with self.core.db.family.begin() as connection:
            if identifier:
                row = connection.execute(
                    select(policy_premium_records).where(
                        policy_premium_records.c.id == identifier,
                        policy_premium_records.c.policy_id == policy_id,
                    )
                ).first()
                if row is None:
                    raise NotFoundError("找不到这笔缴费记录")
                previous = self.payment_view(_row(row)).model_dump(mode="json")
                if not isinstance(request, PaymentUpdate):
                    raise ConflictError("更新缴费需要当前版本号")
                result = connection.execute(
                    update(policy_premium_records)
                    .where(
                        policy_premium_records.c.id == identifier,
                        policy_premium_records.c.revision == request.expected_revision,
                    )
                    .values(**values, revision=request.expected_revision + 1)
                )
                if result.rowcount != 1:
                    raise ConflictError("缴费记录已更新，请重新读取后再保存")
            else:
                identifier = _new_id("PAY")
                connection.execute(
                    insert(policy_premium_records).values(
                        id=identifier, policy_id=policy_id, **values
                    )
                )
            self.audit(
                connection,
                "POLICY",
                policy_id,
                "PAYMENT_UPDATED" if previous else "PAYMENT_CREATED",
                previous,
                request.model_dump(mode="json"),
            )
            row = connection.execute(
                select(policy_premium_records).where(policy_premium_records.c.id == identifier)
            ).one()
            return self.payment_view(_row(row))

    def policy_history(self, identifier: str) -> list[dict[str, str]]:
        self.policy(identifier)
        with self.core.db.family.connect() as connection:
            rows = connection.execute(
                select(
                    family_audit_events.c.id,
                    family_audit_events.c.action,
                    family_audit_events.c.created_at,
                )
                .where(
                    family_audit_events.c.entity_type == "POLICY",
                    family_audit_events.c.entity_id == identifier,
                )
                .order_by(family_audit_events.c.created_at.desc())
            ).all()
        return [_row(row) for row in rows]

    def summary(self, year: int | None = None, today: date | None = None) -> HouseholdSummary:
        from .household_tasks import HouseholdTasks

        today = today or date.today()
        year = year or today.year
        items = self.list_policies(today)
        totals: dict[str, dict[str, Decimal]] = {}
        for policy in items:
            for payment in policy.premium_records:
                total = totals.setdefault(
                    payment.currency,
                    {"paid_this_year": Decimal(0), "outstanding_registered": Decimal(0)},
                )
                if (
                    payment.paid_date
                    and payment.paid_date.year == year
                    and payment.paid_amount is not None
                ):
                    total["paid_this_year"] += Decimal(payment.paid_amount)
                if payment.due_date.year == year and policy.status != "ARCHIVED":
                    total["outstanding_registered"] += max(
                        Decimal(0),
                        Decimal(payment.due_amount) - Decimal(payment.paid_amount or "0"),
                    )
        return HouseholdSummary(
            as_of=today,
            year=year,
            members=self.members(),
            policies=items,
            tasks=HouseholdTasks(self).list(today),
            totals=[
                {"currency": currency, **{k: f"{v:.2f}" for k, v in total.items()}}
                for currency, total in sorted(totals.items())
            ],
            policies_without_payments=sum(
                not p.premium_records for p in items if p.status != "ARCHIVED"
            ),
            disclaimer="仅汇总已登记资料；本年已缴按实缴日期、待缴按应缴日期归年，按原币分别统计。资料未录入不代表没有保障，期间内不代表一定获赔。",
        )
