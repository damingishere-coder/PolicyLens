"""Add public web research runs, official sources, and product metadata.

Revision ID: research_0002
Revises: research_0001
"""

import sqlalchemy as sa

from alembic import op

revision = "research_0002"
down_revision = "research_0001"
branch_labels = None
depends_on = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _columns(table: str) -> set[str]:
    return {item["name"] for item in sa.inspect(op.get_bind()).get_columns(table)}


def _drop_orphan_batch_table(source_table: str) -> None:
    """Remove only Alembic's leftover table from an interrupted SQLite batch rebuild."""
    temporary_table = f"_alembic_tmp_{source_table}"
    tables = _tables()
    if source_table in tables and temporary_table in tables:
        op.drop_table(temporary_table)


def upgrade() -> None:
    tables = _tables()
    if "insurers" not in tables:
        op.create_table(
            "insurers",
            sa.Column("id", sa.String(40), primary_key=True),
            sa.Column("legal_name", sa.String(200), nullable=False),
            sa.Column("brand_name", sa.String(120), nullable=False),
            sa.Column("jurisdiction", sa.String(30), nullable=False),
            sa.Column("regulator_registration", sa.String(120)),
            sa.Column("status", sa.String(30), nullable=False),
            sa.Column("created_at", sa.String(40), nullable=False),
            sa.Column("updated_at", sa.String(40), nullable=False),
        )
    if "official_domains" not in tables:
        op.create_table(
            "official_domains",
            sa.Column("id", sa.String(40), primary_key=True),
            sa.Column("insurer_id", sa.String(40), sa.ForeignKey("insurers.id"), nullable=False),
            sa.Column("host", sa.String(253), nullable=False),
            sa.Column("path_prefix", sa.String(500), nullable=False),
            sa.Column("https_only", sa.Boolean(), nullable=False),
            sa.Column("status", sa.String(30), nullable=False),
            sa.Column("verified_at", sa.String(40), nullable=False),
            sa.UniqueConstraint("host", "path_prefix", name="uq_official_domain_path"),
        )
    if "research_runs" not in tables:
        op.create_table(
            "research_runs",
            sa.Column("id", sa.String(40), primary_key=True),
            sa.Column("scope_json", sa.Text(), nullable=False),
            sa.Column("preview_hash", sa.String(64), nullable=False),
            sa.Column("status", sa.String(40), nullable=False),
            sa.Column("request_hash", sa.String(64), nullable=False),
            sa.Column("cli_version", sa.String(120)),
            sa.Column("argument_profile", sa.String(100)),
            sa.Column("summary_json", sa.Text(), nullable=False),
            sa.Column("error_code", sa.String(80)),
            sa.Column("cancel_requested", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.String(40), nullable=False),
            sa.Column("started_at", sa.String(40)),
            sa.Column("finished_at", sa.String(40)),
        )
    if "source_revisions" not in tables:
        op.create_table(
            "source_revisions",
            sa.Column("id", sa.String(40), primary_key=True),
            sa.Column(
                "source_document_id",
                sa.String(40),
                sa.ForeignKey("source_documents.id"),
                nullable=False,
            ),
            sa.Column("research_run_id", sa.String(40), sa.ForeignKey("research_runs.id")),
            sa.Column("canonical_url", sa.String(2000), nullable=False),
            sa.Column("url_hash", sa.String(64), nullable=False),
            sa.Column("host", sa.String(253), nullable=False),
            sa.Column("fetched_at", sa.String(40), nullable=False),
            sa.Column("http_status", sa.Integer(), nullable=False),
            sa.Column("content_type", sa.String(120), nullable=False),
            sa.Column("etag", sa.String(500)),
            sa.Column("last_modified", sa.String(200)),
            sa.Column("byte_count", sa.Integer(), nullable=False),
            sa.Column("sha256", sa.String(64), nullable=False),
            sa.Column("vault_id", sa.String(80), nullable=False),
            sa.Column("previous_revision_id", sa.String(40), sa.ForeignKey("source_revisions.id")),
            sa.Column("processing_status", sa.String(40), nullable=False),
            sa.UniqueConstraint("canonical_url", "sha256", name="uq_source_revision_url_content"),
        )

    import_columns = _columns("import_sessions")
    if "source_revision_id" not in import_columns:
        _drop_orphan_batch_table("import_sessions")
        with op.batch_alter_table("import_sessions", recreate="always") as batch:
            batch.add_column(
                sa.Column(
                    "source_revision_id",
                    sa.String(40),
                    sa.ForeignKey(
                        "source_revisions.id",
                        name="fk_import_sessions_source_revision_id",
                    ),
                )
            )

    product_columns = _columns("products")
    product_additions = (
        sa.Column(
            "insurer_id",
            sa.String(40),
            sa.ForeignKey("insurers.id", name="fk_products_insurer_id"),
        ),
        sa.Column("product_category", sa.String(60)),
        sa.Column("sale_status", sa.String(40)),
        sa.Column("first_seen_at", sa.String(40)),
        sa.Column("last_seen_at", sa.String(40)),
    )
    if any(column.name not in product_columns for column in product_additions):
        _drop_orphan_batch_table("products")
        with op.batch_alter_table("products", recreate="always") as batch:
            for column in product_additions:
                if column.name not in product_columns:
                    batch.add_column(column)

    _drop_orphan_batch_table("candidate_fields")
    candidate_columns = _columns("candidate_fields")
    candidate_page = next(
        item
        for item in sa.inspect(op.get_bind()).get_columns("candidate_fields")
        if item["name"] == "page_number"
    )
    if "guarantee_type" not in candidate_columns or not candidate_page["nullable"]:
        with op.batch_alter_table("candidate_fields", recreate="always") as batch:
            if "guarantee_type" not in candidate_columns:
                batch.add_column(
                    sa.Column(
                        "guarantee_type",
                        sa.String(40),
                        nullable=False,
                        server_default="UNKNOWN",
                    )
                )
            if not candidate_page["nullable"]:
                batch.alter_column("page_number", existing_type=sa.Integer(), nullable=True)

    _drop_orphan_batch_table("evidence_anchors")
    evidence_columns = _columns("evidence_anchors")
    evidence_page = next(
        item
        for item in sa.inspect(op.get_bind()).get_columns("evidence_anchors")
        if item["name"] == "page_number"
    )
    if (
        "source_revision_id" not in evidence_columns
        or "locator_json" not in evidence_columns
        or not evidence_page["nullable"]
    ):
        with op.batch_alter_table("evidence_anchors", recreate="always") as batch:
            if "source_revision_id" not in evidence_columns:
                batch.add_column(
                    sa.Column(
                        "source_revision_id",
                        sa.String(40),
                        sa.ForeignKey(
                            "source_revisions.id",
                            name="fk_evidence_anchors_source_revision_id",
                        ),
                    )
                )
            if "locator_json" not in evidence_columns:
                batch.add_column(sa.Column("locator_json", sa.Text()))
            if not evidence_page["nullable"]:
                batch.alter_column("page_number", existing_type=sa.Integer(), nullable=True)

    tables = _tables()
    if "product_version_sources" not in tables:
        op.create_table(
            "product_version_sources",
            sa.Column(
                "product_version_id",
                sa.String(40),
                sa.ForeignKey("product_versions.id"),
                primary_key=True,
            ),
            sa.Column(
                "source_revision_id",
                sa.String(40),
                sa.ForeignKey("source_revisions.id"),
                primary_key=True,
            ),
            sa.Column("role", sa.String(40), nullable=False),
        )
    if "discovery_leads" not in tables:
        op.create_table(
            "discovery_leads",
            sa.Column("id", sa.String(40), primary_key=True),
            sa.Column(
                "research_run_id", sa.String(40), sa.ForeignKey("research_runs.id"), nullable=False
            ),
            sa.Column("insurer_id", sa.String(40), sa.ForeignKey("insurers.id"), nullable=False),
            sa.Column("title", sa.String(300), nullable=False),
            sa.Column("canonical_url", sa.String(2000), nullable=False),
            sa.Column("url_hash", sa.String(64), nullable=False),
            sa.Column("discovery_channel", sa.String(40), nullable=False),
            sa.Column("authority", sa.String(50), nullable=False),
            sa.Column("official_verification_url", sa.String(2000)),
            sa.Column("status", sa.String(40), nullable=False),
            sa.Column("rejection_code", sa.String(80)),
            sa.Column("import_id", sa.String(40), sa.ForeignKey("import_sessions.id")),
            sa.Column("discovered_at", sa.String(40), nullable=False),
            sa.Column("last_checked_at", sa.String(40)),
        )


def downgrade() -> None:
    tables = _tables()
    for table in (
        "discovery_leads",
        "product_version_sources",
        "source_revisions",
        "official_domains",
        "research_runs",
        "insurers",
    ):
        if table in tables:
            op.drop_table(table)
    product_columns = _columns("products")
    for name in ("last_seen_at", "first_seen_at", "sale_status", "product_category", "insurer_id"):
        if name in product_columns:
            op.drop_column("products", name)
    if "guarantee_type" in _columns("candidate_fields"):
        op.drop_column("candidate_fields", "guarantee_type")
    if "source_revision_id" in _columns("import_sessions"):
        op.drop_column("import_sessions", "source_revision_id")
    evidence_columns = _columns("evidence_anchors")
    for name in ("locator_json", "source_revision_id"):
        if name in evidence_columns:
            op.drop_column("evidence_anchors", name)
