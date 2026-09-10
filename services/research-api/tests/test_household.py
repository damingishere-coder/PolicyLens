from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select

from policylens_api.app import create_app
from policylens_api.household import HouseholdService
from policylens_api.household_domain import (
    MemberInput,
    MemberUpdate,
    PaymentInput,
    PaymentUpdate,
    PolicyInput,
    PolicyUpdate,
)
from policylens_api.models import persons, policies
from policylens_api.service import ConflictError


def test_empty_product_library_does_not_block_family_records(service):
    family = HouseholdService(service)
    member = family.save_member(
        MemberInput(nickname="SYNTHETIC member", age=28, age_as_of=date.today())
    )
    first = family.save_policy(
        PolicyInput(name="SYNTHETIC medical", person_id=member.id, line="MEDICAL")
    )
    second = family.save_policy(
        PolicyInput(name="SYNTHETIC accident", person_id=member.id, line="ACCIDENT")
    )
    unassigned = family.save_policy(PolicyInput(name="SYNTHETIC pending"))
    assert len(family.members()) == 1
    assert family.member(member.id).policy_count == 2
    assert first.person_id == second.person_id
    assert first.product_version_id is None
    assert first.status == "DRAFT" and first.coverage_state == "UNKNOWN"
    assert first.verification_status == "UNVERIFIED"
    assert "所属成员" in unassigned.missing_fields
    # Legacy list and dashboard readers remain usable with V2 drafts.
    assert len(service.list_policies()) == 3
    service.dashboard()


def test_duplicate_names_are_not_merged_and_policy_can_be_reassigned(service):
    family = HouseholdService(service)
    a = family.save_member(MemberInput(nickname="SYNTHETIC same"))
    b = family.save_member(MemberInput(nickname="SYNTHETIC same"))
    assert a.id != b.id
    assert family.member(a.id).possible_duplicate_ids == [b.id]
    policy = family.save_policy(PolicyInput(name="SYNTHETIC policy", person_id=a.id))
    moved = family.save_policy(
        PolicyUpdate(name=policy.name, person_id=b.id, expected_revision=policy.revision), policy.id
    )
    assert moved.person_id == b.id
    assert family.member(a.id).policy_count == 0
    assert len(family.members()) == 2


def test_stale_edits_fail_without_overwriting_changes(service):
    family = HouseholdService(service)
    member = family.save_member(MemberInput(nickname="SYNTHETIC original"))
    family.save_member(MemberUpdate(nickname="SYNTHETIC updated", expected_revision=1), member.id)
    with pytest.raises(ConflictError):
        family.save_member(MemberUpdate(nickname="SYNTHETIC stale", expected_revision=1), member.id)
    assert family.member(member.id).nickname == "SYNTHETIC updated"
    p = family.save_policy(PolicyInput(name="SYNTHETIC original"))
    family.save_policy(PolicyUpdate(name="SYNTHETIC revised", expected_revision=1), p.id)
    with pytest.raises(ConflictError):
        family.save_policy(PolicyUpdate(name="SYNTHETIC stale", expected_revision=1), p.id)
    assert family.policy(p.id).name == "SYNTHETIC revised"


def test_coverage_state_uses_dates_without_promising_claims(service):
    family = HouseholdService(service)
    today = date.today()
    p = family.save_policy(
        PolicyInput(
            name="SYNTHETIC contract",
            status="ACTIVE",
            start_date=today,
            end_date=today + timedelta(days=365),
        )
    )
    assert family.policy(p.id, today - timedelta(days=1)).coverage_state == "SCHEDULED"
    assert family.policy(p.id, today).coverage_state == "IN_PERIOD"
    assert family.policy(p.id, today + timedelta(days=366)).coverage_state == "ENDED"
    assert p.verification_status == "UNVERIFIED"
    with pytest.raises(ValidationError):
        PolicyInput(name="SYNTHETIC incomplete", status="ACTIVE")


def test_totals_use_paid_date_year_original_currency_and_decimal(service):
    family = HouseholdService(service)
    p = family.save_policy(PolicyInput(name="SYNTHETIC payments"))
    family.save_payment(
        p.id,
        PaymentInput(
            due_amount="100.10",
            due_date=date(2025, 12, 31),
            paid_amount="40.10",
            paid_date=date(2026, 1, 1),
        ),
    )
    family.save_payment(
        p.id,
        PaymentInput(
            due_amount="200.20",
            due_date=date(2026, 6, 1),
            paid_amount="100.20",
            paid_date=date(2026, 6, 1),
        ),
    )
    family.save_payment(
        p.id,
        PaymentInput(
            due_amount="300", due_date=date(2026, 7, 1), currency="HKD", frequency="MONTHLY"
        ),
    )
    totals = {row.currency: row for row in family.summary(2026).totals}
    assert totals["CNY"].paid_this_year == "140.30"
    assert totals["CNY"].outstanding_registered == "100.00"
    assert totals["HKD"].paid_this_year == "0.00"
    assert totals["HKD"].outstanding_registered == "300.00"
    assert family.summary(2025).totals[0].paid_this_year == "0.00"
    assert len(family.policy(p.id).premium_records) == 3


def test_payment_can_be_completed_and_edited_with_revision(service):
    family = HouseholdService(service)
    policy = family.save_policy(PolicyInput(name="SYNTHETIC policy"))
    payment = family.save_payment(
        policy.id, PaymentInput(due_amount="10.01", due_date=date.today())
    )
    assert payment.paid_date is None and payment.paid_amount is None
    updated = family.save_payment(
        policy.id,
        PaymentUpdate(
            due_amount="10.01",
            due_date=date.today(),
            paid_amount="10.01",
            paid_date=date.today(),
            expected_revision=1,
        ),
        payment.id,
    )
    assert Decimal(updated.paid_amount) == Decimal("10.01")
    with pytest.raises(ConflictError):
        family.save_payment(
            policy.id,
            PaymentUpdate(due_amount="10.01", due_date=date.today(), expected_revision=1),
            payment.id,
        )
    assert len(family.policy_history(policy.id)) == 3


@pytest.mark.parametrize(
    "extra",
    [
        {"paid_amount": "10"},
        {"paid_date": date(2026, 1, 1)},
        {"paid_amount": "10", "paid_date": date.today() + timedelta(days=1)},
        {"due_amount": "-1"},
        {"due_amount": "NaN"},
    ],
)
def test_invalid_payments_are_not_saved(extra):
    with pytest.raises(ValidationError):
        PaymentInput(**({"due_amount": "10", "due_date": date.today()} | extra))


def test_private_profile_and_notes_are_encrypted(service):
    family = HouseholdService(service)
    family.save_member(MemberInput(nickname="SYNTHETIC encrypted", age=58, age_as_of=date.today()))
    family.save_policy(
        PolicyInput(name="SYNTHETIC encrypted title", notes="SYNTHETIC private note")
    )
    with service.db.family.connect() as connection:
        member = connection.execute(select(persons)).one()
        policy = connection.execute(select(policies)).one()
    assert "SYNTHETIC" not in member.nickname_encrypted
    assert "SYNTHETIC" not in policy.details_encrypted
    assert member.profile_encrypted.startswith("enc:v1:")


def test_household_routes_require_session_csrf_and_typed_input(tmp_path, protector):
    app = create_app(tmp_path / "api", browser_mode=True, testing=True, protector=protector)
    with TestClient(app) as client:
        assert client.get("/api/v1/household/members").status_code == 401
        token = client.get("/api/v1/session").json()["csrf_token"]
        route = "/api/v1/household/policies"
        assert client.post(route, json={"name": "SYNTHETIC record"}).status_code == 403
        headers = {"origin": "http://testserver", "x-policylens-csrf": token}
        created = client.post(route, json={"name": "SYNTHETIC record"}, headers=headers)
        assert created.status_code == 200
        assert created.json()["coverage_state"] == "UNKNOWN"
        assert (
            client.post(
                route, json={"name": "SYNTHETIC", "confirmed_by_ai": True}, headers=headers
            ).status_code
            == 422
        )
        assert client.get("/api/v1/household/summary").status_code == 200
