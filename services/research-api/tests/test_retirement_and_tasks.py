from datetime import date, timedelta
from decimal import Decimal

import pytest

from policylens_api.household import HouseholdService
from policylens_api.household_domain import (
    MemberInput,
    PaymentInput,
    PaymentUpdate,
    PolicyInput,
    TaskAction,
    TaskInput,
)
from policylens_api.household_tasks import HouseholdTasks
from policylens_api.retirement import (
    RetirementIncome,
    RetirementInput,
    RetirementService,
    RetirementUpdate,
    calculate_retirement,
)
from policylens_api.service import ConflictError


def test_retirement_missing_is_unknown_not_zero():
    result = calculate_retirement(RetirementInput(name="SYNTHETIC partial"))
    assert result.status == "INCOMPLETE" and result.scenarios == []
    assert "退休时点月度支出预算" in result.missing_inputs
    result = calculate_retirement(
        RetirementInput(
            name="SYNTHETIC",
            person_id="synthetic",
            retirement_date=date(2050, 1, 1),
            monthly_expense="100",
        )
    )
    assert result.status == "INCOMPLETE"


def test_retirement_separates_non_guaranteed_and_estimated_income():
    result = calculate_retirement(
        RetirementInput(
            name="SYNTHETIC",
            person_id="synthetic",
            retirement_date=date(2050, 1, 1),
            monthly_expense="8000.10",
            income_inventory_complete=True,
            incomes=[
                RetirementIncome(
                    label="SYNTHETIC guaranteed", monthly_amount="3000.01", kind="GUARANTEED"
                ),
                RetirementIncome(
                    label="SYNTHETIC assumed", monthly_amount="1000.02", kind="ESTIMATE"
                ),
                RetirementIncome(
                    label="SYNTHETIC non-guaranteed",
                    monthly_amount="5000.03",
                    kind="NON_GUARANTEED",
                ),
            ],
        )
    )
    assert result.status == "READY"
    assert [s.monthly_gap for s in result.scenarios] == ["5000.09", "4000.07", "0.00"]
    assert result.scenarios[2].monthly_surplus == "999.96"
    assert result.verification_status == "UNVERIFIED"
    # Independent decimal identity, not the implementation's max expression.
    for scenario in result.scenarios:
        assert Decimal(scenario.monthly_income) + Decimal(scenario.monthly_gap) == Decimal(
            scenario.monthly_expense
        ) + Decimal(scenario.monthly_surplus)


def test_explicit_zero_income_is_supported():
    result = calculate_retirement(
        RetirementInput(
            name="SYNTHETIC zero",
            person_id="synthetic",
            retirement_date=date(2050, 1, 1),
            monthly_expense="100",
            income_inventory_complete=True,
        )
    )
    assert result.status == "READY" and result.scenarios[0].monthly_gap == "100.00"


def test_retirement_keeps_immutable_snapshots_and_independent_members(service):
    family = HouseholdService(service)
    a = family.save_member(MemberInput(nickname="SYNTHETIC self"))
    b = family.save_member(MemberInput(nickname="SYNTHETIC parent"))
    plans = RetirementService(family)
    first = plans.save(RetirementInput(name="SYNTHETIC long term", person_id=a.id))
    plans.save(RetirementInput(name="SYNTHETIC parent", person_id=b.id))
    before = plans.snapshots(first.id)[0]
    updated = plans.save(
        RetirementUpdate(
            name=first.name,
            person_id=a.id,
            monthly_expense="100",
            retirement_date=date(2050, 1, 1),
            income_inventory_complete=True,
            expected_revision=1,
        ),
        first.id,
    )
    assert updated.result.status == "READY"
    assert len(plans.list()) == 2 and len(plans.snapshots(first.id)) == 2
    assert plans.reproduce(first.id, before.id).status == "INCOMPLETE"
    assert plans.snapshots(first.id)[-1] == before
    with pytest.raises(ConflictError):
        plans.save(RetirementUpdate(name="SYNTHETIC stale", expected_revision=1), first.id)


def test_generated_tasks_are_pure_reads_and_payment_resolution_is_financial(service):
    family = HouseholdService(service)
    tasks = HouseholdTasks(family)
    p = family.save_policy(PolicyInput(name="SYNTHETIC policy"))
    payment = family.save_payment(p.id, PaymentInput(due_amount="10", due_date=date.today()))
    task = next(t for t in tasks.list() if t.kind == "PAYMENT")
    assert task.revision == 0
    assert [t.id for t in tasks.list()] == [t.id for t in tasks.list()]
    with pytest.raises(ConflictError):
        tasks.act(task.id, TaskAction(status="DONE", expected_revision=0))
    family.save_payment(
        p.id,
        PaymentUpdate(
            due_amount="10",
            due_date=date.today(),
            paid_amount="10",
            paid_date=date.today(),
            expected_revision=1,
        ),
        payment.id,
    )
    assert not any(t.kind == "PAYMENT" for t in tasks.list())


def test_task_snooze_reopens_on_date_and_stale_update_fails(service):
    family = HouseholdService(service)
    tasks = HouseholdTasks(family)
    custom = tasks.create(TaskInput(title="SYNTHETIC review"))
    tomorrow = date.today() + timedelta(days=1)
    updated = tasks.act(
        custom.id, TaskAction(status="SNOOZED", snoozed_until=tomorrow, expected_revision=1)
    )
    assert updated.status == "SNOOZED"
    assert tasks.list(tomorrow)[0].status == "OPEN"
    with pytest.raises(ConflictError):
        tasks.act(custom.id, TaskAction(status="DONE", expected_revision=1))
    done = tasks.act(custom.id, TaskAction(status="DONE", expected_revision=updated.revision))
    assert done.status == "DONE"


def test_generated_information_task_state_survives_restart(service):
    family = HouseholdService(service)
    tasks = HouseholdTasks(family)
    family.save_policy(PolicyInput(name="SYNTHETIC policy"))
    task = tasks.list()[0]
    done = tasks.act(task.id, TaskAction(status="DONE", expected_revision=0))
    assert done.revision == 1 and done.status == "DONE"
    assert (
        next(t for t in HouseholdTasks(HouseholdService(service)).list() if t.id == task.id).status
        == "DONE"
    )
