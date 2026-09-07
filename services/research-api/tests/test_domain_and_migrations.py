from __future__ import annotations

import os
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from policylens_api.crypto import DpapiProtector
from policylens_api.domain import (
    PremiumRate,
    RateAdjustmentRule,
    RenewalTerms,
    SourceAuthority,
    ValueOrigin,
    VerificationStatus,
)
from policylens_api.migrations import run_migrations
from policylens_api.service import PolicyLensService


@pytest.mark.skipif(os.name != "nt", reason="Windows DPAPI acceptance only runs on Windows")
def test_real_windows_dpapi_roundtrip_uses_current_user_context() -> None:
    original = os.urandom(32)
    wrapped = DpapiProtector().protect(original)
    assert wrapped != original
    assert DpapiProtector().unprotect(wrapped) == original


def test_three_semantic_dimensions_are_independent() -> None:
    combinations = {
        (verification.value, origin.value, authority.value)
        for verification in VerificationStatus
        for origin in ValueOrigin
        for authority in SourceAuthority
    }
    assert len(combinations) == 5 * 6 * 6
    assert "ESTIMATED" not in {item.value for item in VerificationStatus}
    assert "AI" not in {item.value for item in SourceAuthority}


def test_renewal_and_price_contracts_do_not_imply_each_other() -> None:
    renewal = RenewalTerms(renewal_mode="GUARANTEED_RENEWAL", guarantee_period_years=6)
    rate = PremiumRate(
        version_label="Synthetic 2026",
        currency="CNY",
        frequency="ANNUAL",
        amount="1280.00",
    )
    adjustment = RateAdjustmentRule(scope="COHORT", frequency="ANNUAL_REVIEW")
    assert renewal.renewal_mode == "GUARANTEED_RENEWAL"
    assert not hasattr(renewal, "premium_fixed")
    assert rate.amount == "1280.00"
    assert adjustment.scope == "COHORT"


def test_alembic_migrates_separate_research_and_family_databases(
    service: PolicyLensService,
) -> None:
    expected = {
        "research.db": {
            "products",
            "product_versions",
            "facts",
            "source_documents",
            "research_runs",
            "discovery_leads",
            "source_revisions",
            "insurers",
        },
        "family.db": {"persons", "policies", "policy_premium_records", "ai_analysis_runs"},
    }
    expected_revision = {"research.db": "research_0002", "family.db": "family_0001"}
    for name, required in expected.items():
        path = service.data_dir / "databases" / name
        assert path.exists()
        with closing(sqlite3.connect(path)) as connection:
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            version = connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        assert required.issubset(tables)
        assert str(version) == expected_revision[name]
    assert (service.data_dir / "databases" / "research.db").resolve() != (
        service.data_dir / "databases" / "family.db"
    ).resolve()


def test_research_migration_recovers_an_orphaned_sqlite_batch_table(
    service: PolicyLensService,
) -> None:
    path = service.data_dir / "databases" / "research.db"
    with closing(sqlite3.connect(path)) as connection:
        connection.execute(
            "CREATE TABLE _alembic_tmp_candidate_fields (id VARCHAR(40) PRIMARY KEY)"
        )
        connection.execute(
            "UPDATE alembic_version SET version_num = 'research_0001'"
        )
        connection.commit()

    run_migrations(service.data_dir)

    with closing(sqlite3.connect(path)) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        version = connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
    assert "_alembic_tmp_candidate_fields" not in tables
    assert version == "research_0002"
    assert integrity == "ok"


def test_research_migration_upgrades_the_legacy_sqlite_schema(tmp_path: Path) -> None:
    data_dir = tmp_path / "legacy-data"
    databases = data_dir / "databases"
    databases.mkdir(parents=True)
    path = databases / "research.db"
    with closing(sqlite3.connect(path)) as connection:
        connection.executescript(
            """
            CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL);
            INSERT INTO alembic_version VALUES ('research_0001');
            CREATE TABLE source_documents (
                id VARCHAR(40) PRIMARY KEY, sha256 VARCHAR(64) NOT NULL,
                title_encrypted TEXT NOT NULL, document_type VARCHAR(40) NOT NULL,
                authority VARCHAR(50) NOT NULL, page_count INTEGER NOT NULL,
                extractor_version VARCHAR(40) NOT NULL, vault_id VARCHAR(80),
                status VARCHAR(40) NOT NULL, imported_at VARCHAR(40) NOT NULL
            );
            CREATE TABLE import_sessions (
                id VARCHAR(40) PRIMARY KEY, source_id VARCHAR(40) NOT NULL,
                status VARCHAR(40) NOT NULL, duplicate BOOLEAN NOT NULL,
                created_at VARCHAR(40) NOT NULL,
                FOREIGN KEY(source_id) REFERENCES source_documents(id)
            );
            CREATE TABLE candidate_fields (
                id VARCHAR(40) PRIMARY KEY, import_session_id VARCHAR(40) NOT NULL,
                field_path VARCHAR(120) NOT NULL, value_encrypted TEXT NOT NULL,
                raw_value_encrypted TEXT NOT NULL, unit VARCHAR(40),
                page_number INTEGER NOT NULL, excerpt_encrypted TEXT NOT NULL,
                excerpt_hash VARCHAR(64) NOT NULL, verification_status VARCHAR(30) NOT NULL,
                value_origin VARCHAR(40) NOT NULL, source_authority VARCHAR(50) NOT NULL,
                decision VARCHAR(30), extractor_version VARCHAR(40) NOT NULL,
                FOREIGN KEY(import_session_id) REFERENCES import_sessions(id)
            );
            CREATE TABLE products (
                id VARCHAR(40) PRIMARY KEY, display_name VARCHAR(160) NOT NULL,
                jurisdiction VARCHAR(30) NOT NULL, line_of_business VARCHAR(40) NOT NULL,
                currency VARCHAR(3) NOT NULL, created_at VARCHAR(40) NOT NULL
            );
            CREATE TABLE product_versions (
                id VARCHAR(40) PRIMARY KEY, product_id VARCHAR(40) NOT NULL,
                version_label VARCHAR(100) NOT NULL, effective_date VARCHAR(20),
                record_status VARCHAR(20) NOT NULL, source_id VARCHAR(40) NOT NULL,
                created_at VARCHAR(40) NOT NULL,
                FOREIGN KEY(product_id) REFERENCES products(id),
                FOREIGN KEY(source_id) REFERENCES source_documents(id)
            );
            CREATE TABLE evidence_anchors (
                id VARCHAR(40) PRIMARY KEY, source_id VARCHAR(40) NOT NULL,
                page_number INTEGER NOT NULL, excerpt_encrypted TEXT NOT NULL,
                excerpt_hash VARCHAR(64) NOT NULL, authority VARCHAR(50) NOT NULL,
                FOREIGN KEY(source_id) REFERENCES source_documents(id)
            );
            INSERT INTO source_documents VALUES (
                'SRC-LEGACY', 'synthetic-sha', 'ciphertext', 'TEXT_PDF',
                'INSURER_OFFICIAL_DISCLOSURE', 1, 'legacy', NULL,
                'WAITING_REVIEW', '2026-01-01T00:00:00Z'
            );
            INSERT INTO import_sessions VALUES (
                'IMP-LEGACY', 'SRC-LEGACY', 'WAITING_REVIEW', 0, '2026-01-01T00:00:00Z'
            );
            INSERT INTO candidate_fields VALUES (
                'CAN-LEGACY', 'IMP-LEGACY', 'product.display_name', 'ciphertext',
                'ciphertext', NULL, 1, 'ciphertext', 'synthetic-hash', 'UNVERIFIED',
                'RULE_EXTRACTION', 'INSURER_OFFICIAL_DISCLOSURE', NULL, 'legacy'
            );
            INSERT INTO products VALUES (
                'PROD-LEGACY', 'Synthetic Legacy', 'HK', 'LIFE_SAVINGS', 'HKD',
                '2026-01-01T00:00:00Z'
            );
            INSERT INTO product_versions VALUES (
                'VER-LEGACY', 'PROD-LEGACY', 'Legacy 2026', NULL, 'DRAFT',
                'SRC-LEGACY', '2026-01-01T00:00:00Z'
            );
            INSERT INTO evidence_anchors VALUES (
                'EVD-LEGACY', 'SRC-LEGACY', 1, 'ciphertext', 'synthetic-hash',
                'INSURER_OFFICIAL_DISCLOSURE'
            );
            """
        )
        connection.commit()

    run_migrations(data_dir)

    with closing(sqlite3.connect(path)) as connection:
        revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        candidate_columns = {
            row[1]: bool(row[3]) for row in connection.execute("PRAGMA table_info(candidate_fields)")
        }
        evidence_columns = {
            row[1]: bool(row[3]) for row in connection.execute("PRAGMA table_info(evidence_anchors)")
        }
        foreign_keys = {
            table: {(row[3], row[2]) for row in connection.execute(f"PRAGMA foreign_key_list({table})")}
            for table in ("import_sessions", "products", "evidence_anchors")
        }
        count_queries = {
            "source_documents": "SELECT COUNT(*) FROM source_documents",
            "import_sessions": "SELECT COUNT(*) FROM import_sessions",
            "candidate_fields": "SELECT COUNT(*) FROM candidate_fields",
            "products": "SELECT COUNT(*) FROM products",
            "product_versions": "SELECT COUNT(*) FROM product_versions",
            "evidence_anchors": "SELECT COUNT(*) FROM evidence_anchors",
        }
        counts = {
            table: connection.execute(query).fetchone()[0]
            for table, query in count_queries.items()
        }
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
    assert revision == "research_0002"
    assert candidate_columns["guarantee_type"]
    assert not candidate_columns["page_number"]
    assert not evidence_columns["page_number"]
    assert {"source_revision_id", "locator_json"}.issubset(evidence_columns)
    assert ("source_revision_id", "source_revisions") in foreign_keys["import_sessions"]
    assert ("insurer_id", "insurers") in foreign_keys["products"]
    assert ("source_revision_id", "source_revisions") in foreign_keys["evidence_anchors"]
    assert counts == {table: 1 for table in counts}
    assert integrity == "ok"
