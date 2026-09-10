"""Exercise a populated family_0001 shape, including its original uniqueness constraint."""

import sqlite3
from contextlib import closing

from conftest import accept_all

from policylens_api.domain import PolicyCreateRequest
from policylens_api.household import HouseholdService
from policylens_api.household_domain import PolicyInput
from policylens_api.migrations import run_migrations


def test_populated_legacy_family_preserves_ids_encryption_payments_and_backup(
    service, alpha_manual, tmp_path
):
    product = accept_all(service, service.import_manual(alpha_manual))["product_version_id"]
    policy = service.create_policy(
        PolicyCreateRequest(
            member_nickname="SYNTHETIC legacy member",
            product_version_id=product,
            category="CORE",
            due_amount="1280.00",
            paid_amount="1200.00",
            currency="CNY",
            frequency="ANNUAL",
            due_date="2026-09-03",
            paid_date="2026-09-03",
        )
    )
    service.db.family.dispose()
    database = service.data_dir / "databases/family.db"
    with closing(sqlite3.connect(database)) as connection:
        connection.execute("PRAGMA foreign_keys=OFF")
        # Only test data is reshaped into the exact legacy columns; production never downgrades.
        connection.executescript("""
            CREATE TABLE legacy_persons (id VARCHAR(40) PRIMARY KEY, nickname_encrypted TEXT NOT NULL, created_at VARCHAR(40) NOT NULL);
            INSERT INTO legacy_persons SELECT id,nickname_encrypted,created_at FROM persons;
            CREATE TABLE legacy_policies (id VARCHAR(40) PRIMARY KEY, person_id VARCHAR(40) NOT NULL REFERENCES persons(id),product_version_id VARCHAR(40) NOT NULL,category VARCHAR(30) NOT NULL,status VARCHAR(30) NOT NULL,created_at VARCHAR(40) NOT NULL,CONSTRAINT uq_person_product_version UNIQUE(person_id,product_version_id));
            INSERT INTO legacy_policies SELECT id,person_id,product_version_id,category,status,created_at FROM policies;
            CREATE TABLE legacy_payments (id VARCHAR(40) PRIMARY KEY,policy_id VARCHAR(40) NOT NULL REFERENCES policies(id),due_amount_encrypted TEXT NOT NULL,paid_amount_encrypted TEXT,currency VARCHAR(3) NOT NULL,frequency VARCHAR(30) NOT NULL,due_date VARCHAR(20) NOT NULL,paid_date VARCHAR(20),premium_rate_id VARCHAR(40));
            INSERT INTO legacy_payments SELECT id,policy_id,due_amount_encrypted,paid_amount_encrypted,currency,frequency,due_date,paid_date,premium_rate_id FROM policy_premium_records;
            DROP TABLE policy_premium_records; DROP TABLE policies; DROP TABLE persons;
            ALTER TABLE legacy_persons RENAME TO persons;
            ALTER TABLE legacy_policies RENAME TO policies;
            ALTER TABLE legacy_payments RENAME TO policy_premium_records;
            UPDATE alembic_version SET version_num='family_0001';
        """)
        for name in [
            "family_documents",
            "household_tasks",
            "retirement_snapshots",
            "retirement_plans",
            "comparison_records",
            "context_analysis_runs",
        ]:
            connection.execute(f'DROP TABLE "{name}"')
        before = connection.execute(
            "SELECT id,person_id,product_version_id FROM policies"
        ).fetchall()
        ciphertext = connection.execute("SELECT nickname_encrypted FROM persons").fetchone()[0]
        payment_before = connection.execute("SELECT * FROM policy_premium_records").fetchall()
        connection.commit()
    backup = tmp_path / "legacy-family.plbackup"
    service.create_backup("SYNTHETIC-legacy-password", backup)
    run_migrations(service.data_dir)
    with closing(sqlite3.connect(database)) as connection:
        assert (
            connection.execute("SELECT id,person_id,product_version_id FROM policies").fetchall()
            == before
        )
        assert (
            connection.execute("SELECT nickname_encrypted FROM persons").fetchone()[0] == ciphertext
        )
        assert [
            row[:-1]
            for row in connection.execute("SELECT * FROM policy_premium_records").fetchall()
        ] == payment_before
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    family = HouseholdService(service)
    old = family.policy(policy["id"])
    assert old.coverage_state == "UNKNOWN" and old.premium_records[0].paid_amount == "1200.00"
    family.save_policy(
        PolicyInput(
            name="SYNTHETIC second policy", person_id=old.person_id, product_version_id=product
        )
    )
    family.save_policy(PolicyInput(name="SYNTHETIC unlinked"))
    preview = service.preview_restore("SYNTHETIC-legacy-password", backup)
    assert preview["policy_count"] == 1
    service.commit_restore(preview["restore_token"])
    assert family.policy(old.id).person_id == old.person_id
    assert family.member(old.person_id).nickname == "SYNTHETIC legacy member"
