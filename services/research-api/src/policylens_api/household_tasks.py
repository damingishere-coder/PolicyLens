from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import insert, select, update

from .household_domain import TaskAction, TaskInput, TaskView
from .models import household_tasks
from .service import ConflictError, NotFoundError, _hash_json, _new_id, _now

if TYPE_CHECKING:
    from .household import HouseholdService


class HouseholdTasks:
    def __init__(self, family: HouseholdService):
        self.family = family

    def list(self, today: date | None = None) -> list[TaskView]:
        today = today or date.today()
        tasks: dict[str, TaskView] = {}
        for policy in self.family.list_policies(today):
            if policy.status == "ARCHIVED":
                continue
            href = f"/policies/{policy.id}"
            for field in policy.missing_fields:
                identifier = f"INFO:{policy.id}:{_hash_json(field)[:12]}"
                tasks[identifier] = TaskView(
                    id=identifier,
                    title=f"{policy.name}：补充{field}",
                    policy_id=policy.id,
                    kind="INFORMATION",
                    status="OPEN",
                    revision=0,
                    reason="尚未登记足够信息，不能判断保障是否满足需要。",
                    href=href,
                )
            if policy.end_date and policy.end_date <= today + timedelta(days=30):
                identifier = f"EXPIRY:{policy.id}:{policy.end_date}"
                tasks[identifier] = TaskView(
                    id=identifier,
                    title=f"{policy.name}：复查保障期间",
                    policy_id=policy.id,
                    due_date=policy.end_date,
                    kind="EXPIRY",
                    status="OPEN",
                    revision=0,
                    reason="按你登记的终止日期生成；请核对是否需要续保，不会自动修改保单。",
                    href=href,
                )
            for payment in policy.premium_records:
                balance = Decimal(payment.due_amount) - Decimal(payment.paid_amount or "0")
                if balance <= 0:
                    continue
                fingerprint = _hash_json(payment.model_dump(mode="json", exclude={"revision"}))[:16]
                identifier = f"PAYMENT:{payment.id}:{fingerprint}"
                tasks[identifier] = TaskView(
                    id=identifier,
                    title=f"{policy.name}：待登记缴费",
                    policy_id=policy.id,
                    due_date=payment.due_date,
                    kind="PAYMENT",
                    status="OPEN",
                    revision=0,
                    reason=f"已登记应缴与实缴相差 {payment.currency} {balance:.2f}；这不等同于保险公司确认欠费。",
                    href=href,
                )
        with self.family.core.db.family.connect() as connection:
            rows = connection.execute(select(household_tasks)).all()
        for row in rows:
            payload = self.family.unpack(row.payload_encrypted)
            if row.id.startswith("CUSTOM:"):
                tasks[row.id] = TaskView(**payload, id=row.id, revision=row.revision)
            elif row.id in tasks:
                tasks[row.id] = tasks[row.id].model_copy(
                    update=payload | {"revision": row.revision}
                )
        for task in tasks.values():
            if (
                task.status == "SNOOZED"
                and task.snoozed_until
                and date.fromisoformat(str(task.snoozed_until)) <= today
            ):
                task.status = "OPEN"
                task.snoozed_until = None
        return sorted(
            tasks.values(),
            key=lambda item: (item.status != "OPEN", str(item.due_date or "9999-12-31"), item.id),
        )

    def create(self, request: TaskInput) -> TaskView:
        if request.policy_id:
            self.family.policy(request.policy_id)
        identifier = "CUSTOM:" + _new_id("TASK")
        task = TaskView(
            **request.model_dump(),
            id=identifier,
            kind="CUSTOM",
            status="OPEN",
            revision=1,
            reason="你创建的本地待办。",
            href=f"/policies/{request.policy_id}" if request.policy_id else "/tasks",
        )
        with self.family.core.db.family.begin() as connection:
            connection.execute(
                insert(household_tasks).values(
                    id=identifier,
                    payload_encrypted=self.family.pack(
                        task.model_dump(mode="json", exclude={"id", "revision"})
                    ),
                    updated_at=_now(),
                )
            )
        return task

    def act(self, identifier: str, request: TaskAction) -> TaskView:
        current = next((task for task in self.list() if task.id == identifier), None)
        if not current:
            raise NotFoundError("事项已解决或不存在，请刷新列表")
        if current.kind == "PAYMENT" and request.status == "DONE":
            raise ConflictError("请在保单中登记实缴情况，缴费事项会按记录自动更新")
        if current.revision != request.expected_revision:
            raise ConflictError("事项已更新，请刷新后再处理")
        payload = (
            current.model_dump(mode="json", exclude={"id", "revision"})
            if current.kind == "CUSTOM"
            else {}
        )
        payload.update(request.model_dump(mode="json", exclude={"expected_revision"}))
        with self.family.core.db.family.begin() as connection:
            if current.revision == 0:
                # SQLite serializes this transaction; a concurrent insert is a conflict.
                from sqlalchemy.exc import IntegrityError

                try:
                    connection.execute(
                        insert(household_tasks).values(
                            id=identifier,
                            payload_encrypted=self.family.pack(payload),
                            updated_at=_now(),
                        )
                    )
                except IntegrityError as exc:
                    raise ConflictError("事项已更新，请刷新后再处理") from exc
            else:
                result = connection.execute(
                    update(household_tasks)
                    .where(
                        household_tasks.c.id == identifier,
                        household_tasks.c.revision == request.expected_revision,
                    )
                    .values(
                        payload_encrypted=self.family.pack(payload),
                        revision=current.revision + 1,
                        updated_at=_now(),
                    )
                )
                if result.rowcount != 1:
                    raise ConflictError("事项已更新，请刷新后再处理")
        return next(task for task in self.list() if task.id == identifier)
