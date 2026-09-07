from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Column,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
)

research_metadata = MetaData()
family_metadata = MetaData()

insurers = Table(
    "insurers",
    research_metadata,
    Column("id", String(40), primary_key=True),
    Column("legal_name", String(200), nullable=False),
    Column("brand_name", String(120), nullable=False),
    Column("jurisdiction", String(30), nullable=False),
    Column("regulator_registration", String(120)),
    Column("status", String(30), nullable=False),
    Column("created_at", String(40), nullable=False),
    Column("updated_at", String(40), nullable=False),
)

official_domains = Table(
    "official_domains",
    research_metadata,
    Column("id", String(40), primary_key=True),
    Column("insurer_id", ForeignKey("insurers.id"), nullable=False),
    Column("host", String(253), nullable=False),
    Column("path_prefix", String(500), nullable=False, default="/"),
    Column("https_only", Boolean, nullable=False, default=True),
    Column("status", String(30), nullable=False),
    Column("verified_at", String(40), nullable=False),
    UniqueConstraint("host", "path_prefix", name="uq_official_domain_path"),
)

research_runs = Table(
    "research_runs",
    research_metadata,
    Column("id", String(40), primary_key=True),
    Column("scope_json", Text, nullable=False),
    Column("preview_hash", String(64), nullable=False),
    Column("status", String(40), nullable=False),
    Column("request_hash", String(64), nullable=False),
    Column("cli_version", String(120)),
    Column("argument_profile", String(100)),
    Column("summary_json", Text, nullable=False, default="{}"),
    Column("error_code", String(80)),
    Column("cancel_requested", Boolean, nullable=False, default=False),
    Column("created_at", String(40), nullable=False),
    Column("started_at", String(40)),
    Column("finished_at", String(40)),
)

source_documents = Table(
    "source_documents",
    research_metadata,
    Column("id", String(40), primary_key=True),
    Column("sha256", String(64), nullable=False, unique=True),
    Column("title_encrypted", Text, nullable=False),
    Column("document_type", String(40), nullable=False),
    Column("authority", String(50), nullable=False),
    Column("page_count", Integer, nullable=False),
    Column("extractor_version", String(40), nullable=False),
    Column("vault_id", String(80)),
    Column("status", String(40), nullable=False),
    Column("imported_at", String(40), nullable=False),
)

source_revisions = Table(
    "source_revisions",
    research_metadata,
    Column("id", String(40), primary_key=True),
    Column("source_document_id", ForeignKey("source_documents.id"), nullable=False),
    Column("research_run_id", ForeignKey("research_runs.id")),
    Column("canonical_url", String(2000), nullable=False),
    Column("url_hash", String(64), nullable=False),
    Column("host", String(253), nullable=False),
    Column("fetched_at", String(40), nullable=False),
    Column("http_status", Integer, nullable=False),
    Column("content_type", String(120), nullable=False),
    Column("etag", String(500)),
    Column("last_modified", String(200)),
    Column("byte_count", Integer, nullable=False),
    Column("sha256", String(64), nullable=False),
    Column("vault_id", String(80), nullable=False),
    Column("previous_revision_id", ForeignKey("source_revisions.id")),
    Column("processing_status", String(40), nullable=False),
    UniqueConstraint("canonical_url", "sha256", name="uq_source_revision_url_content"),
)

import_sessions = Table(
    "import_sessions",
    research_metadata,
    Column("id", String(40), primary_key=True),
    Column("source_id", ForeignKey("source_documents.id"), nullable=False),
    Column("source_revision_id", ForeignKey("source_revisions.id")),
    Column("status", String(40), nullable=False),
    Column("duplicate", Boolean, nullable=False, default=False),
    Column("created_at", String(40), nullable=False),
)

candidate_fields = Table(
    "candidate_fields",
    research_metadata,
    Column("id", String(40), primary_key=True),
    Column("import_session_id", ForeignKey("import_sessions.id"), nullable=False),
    Column("field_path", String(120), nullable=False),
    Column("value_encrypted", Text, nullable=False),
    Column("raw_value_encrypted", Text, nullable=False),
    Column("unit", String(40)),
    Column("page_number", Integer),
    Column("excerpt_encrypted", Text, nullable=False),
    Column("excerpt_hash", String(64), nullable=False),
    Column("verification_status", String(30), nullable=False),
    Column("value_origin", String(40), nullable=False),
    Column("source_authority", String(50), nullable=False),
    Column("guarantee_type", String(40), nullable=False, default="UNKNOWN"),
    Column("decision", String(30)),
    Column("extractor_version", String(40), nullable=False),
)

products = Table(
    "products",
    research_metadata,
    Column("id", String(40), primary_key=True),
    Column("display_name", String(160), nullable=False),
    Column("jurisdiction", String(30), nullable=False),
    Column("line_of_business", String(40), nullable=False),
    Column("currency", String(3), nullable=False),
    Column("insurer_id", ForeignKey("insurers.id")),
    Column("product_category", String(60)),
    Column("sale_status", String(40)),
    Column("first_seen_at", String(40)),
    Column("last_seen_at", String(40)),
    Column("created_at", String(40), nullable=False),
)

product_versions = Table(
    "product_versions",
    research_metadata,
    Column("id", String(40), primary_key=True),
    Column("product_id", ForeignKey("products.id"), nullable=False),
    Column("version_label", String(100), nullable=False),
    Column("effective_date", String(20)),
    Column("record_status", String(20), nullable=False),
    Column("source_id", ForeignKey("source_documents.id"), nullable=False),
    Column("created_at", String(40), nullable=False),
)

evidence_anchors = Table(
    "evidence_anchors",
    research_metadata,
    Column("id", String(40), primary_key=True),
    Column("source_id", ForeignKey("source_documents.id"), nullable=False),
    Column("source_revision_id", ForeignKey("source_revisions.id")),
    Column("page_number", Integer),
    Column("locator_json", Text),
    Column("excerpt_encrypted", Text, nullable=False),
    Column("excerpt_hash", String(64), nullable=False),
    Column("authority", String(50), nullable=False),
)

product_version_sources = Table(
    "product_version_sources",
    research_metadata,
    Column("product_version_id", ForeignKey("product_versions.id"), primary_key=True),
    Column("source_revision_id", ForeignKey("source_revisions.id"), primary_key=True),
    Column("role", String(40), nullable=False),
)

discovery_leads = Table(
    "discovery_leads",
    research_metadata,
    Column("id", String(40), primary_key=True),
    Column("research_run_id", ForeignKey("research_runs.id"), nullable=False),
    Column("insurer_id", ForeignKey("insurers.id"), nullable=False),
    Column("title", String(300), nullable=False),
    Column("canonical_url", String(2000), nullable=False),
    Column("url_hash", String(64), nullable=False),
    Column("discovery_channel", String(40), nullable=False),
    Column("authority", String(50), nullable=False),
    Column("official_verification_url", String(2000)),
    Column("status", String(40), nullable=False),
    Column("rejection_code", String(80)),
    Column("import_id", ForeignKey("import_sessions.id")),
    Column("discovered_at", String(40), nullable=False),
    Column("last_checked_at", String(40)),
)

facts = Table(
    "facts",
    research_metadata,
    Column("id", String(40), primary_key=True),
    Column("product_version_id", ForeignKey("product_versions.id"), nullable=False),
    Column("field_path", String(120), nullable=False),
    Column("normalized_value", String(1200), nullable=False),
    Column("raw_value_encrypted", Text, nullable=False),
    Column("unit", String(40)),
    Column("guarantee_type", String(40), nullable=False),
    Column("verification_status", String(30), nullable=False),
    Column("value_origin", String(40), nullable=False),
    Column("verified_at", String(40)),
    Column("supersedes_fact_id", String(40)),
    Column("created_at", String(40), nullable=False),
)

fact_evidence = Table(
    "fact_evidence",
    research_metadata,
    Column("fact_id", ForeignKey("facts.id"), primary_key=True),
    Column("evidence_id", ForeignKey("evidence_anchors.id"), primary_key=True),
)

renewal_terms = Table(
    "renewal_terms",
    research_metadata,
    Column("id", String(40), primary_key=True),
    Column("product_version_id", ForeignKey("product_versions.id"), nullable=False, unique=True),
    Column("renewal_mode", String(40), nullable=False),
    Column("guarantee_period_years", Integer),
    Column("maximum_renewal_age", Integer),
    Column("requires_reunderwriting", Boolean),
    Column("reassesses_health", Boolean),
    Column("waiting_period_days", Integer),
    Column("continuity_conditions", Text),
    Column("discontinuation_treatment", Text),
    Column("termination_conditions", Text),
)

premium_rates = Table(
    "premium_rates",
    research_metadata,
    Column("id", String(40), primary_key=True),
    Column("product_version_id", ForeignKey("product_versions.id"), nullable=False),
    Column("version_label", String(100), nullable=False),
    Column("valid_from", String(20)),
    Column("valid_to", String(20)),
    Column("currency", String(3), nullable=False),
    Column("frequency", String(30), nullable=False),
    Column("amount", String(40), nullable=False),
    Column("pricing_dimensions_json", Text, nullable=False),
)

rate_adjustment_rules = Table(
    "rate_adjustment_rules",
    research_metadata,
    Column("id", String(40), primary_key=True),
    Column("product_version_id", ForeignKey("product_versions.id"), nullable=False),
    Column("scope", String(30), nullable=False),
    Column("trigger_conditions", Text),
    Column("frequency", String(100)),
    Column("notice_days", Integer),
    Column("cap", String(40)),
    Column("floor", String(40)),
    Column("effective_from", String(20)),
)

research_audit_events = Table(
    "audit_events",
    research_metadata,
    Column("id", String(40), primary_key=True),
    Column("entity_type", String(40), nullable=False),
    Column("entity_id", String(40), nullable=False),
    Column("action", String(60), nullable=False),
    Column("before_hash", String(64)),
    Column("after_hash", String(64)),
    Column("created_at", String(40), nullable=False),
)

workspaces = Table(
    "workspaces",
    family_metadata,
    Column("id", String(40), primary_key=True),
    Column("default_region", String(30), nullable=False),
    Column("display_currency", String(3), nullable=False),
    Column("codex_enabled", Boolean, nullable=False, default=False),
    Column("created_at", String(40), nullable=False),
)

persons = Table(
    "persons",
    family_metadata,
    Column("id", String(40), primary_key=True),
    Column("nickname_encrypted", Text, nullable=False),
    Column("created_at", String(40), nullable=False),
)

policies = Table(
    "policies",
    family_metadata,
    Column("id", String(40), primary_key=True),
    Column("person_id", ForeignKey("persons.id"), nullable=False),
    Column("product_version_id", String(40), nullable=False),
    Column("category", String(30), nullable=False),
    Column("status", String(30), nullable=False),
    Column("created_at", String(40), nullable=False),
)

policy_premium_records = Table(
    "policy_premium_records",
    family_metadata,
    Column("id", String(40), primary_key=True),
    Column("policy_id", ForeignKey("policies.id"), nullable=False),
    Column("due_amount_encrypted", Text, nullable=False),
    Column("paid_amount_encrypted", Text),
    Column("currency", String(3), nullable=False),
    Column("frequency", String(30), nullable=False),
    Column("due_date", String(20), nullable=False),
    Column("paid_date", String(20)),
    Column("premium_rate_id", String(40)),
)

comparison_cases = Table(
    "comparison_cases",
    family_metadata,
    Column("id", String(40), primary_key=True),
    Column("product_version_ids_json", Text, nullable=False),
    Column("input_snapshot_hash", String(64), nullable=False),
    Column("algorithm_version", String(40), nullable=False),
    Column("created_at", String(40), nullable=False),
)

ai_analysis_runs = Table(
    "ai_analysis_runs",
    family_metadata,
    Column("id", String(40), primary_key=True),
    Column("preview_hash", String(64), nullable=False),
    Column("evidence_ids_json", Text, nullable=False),
    Column("status", String(30), nullable=False),
    Column("result_json", Text, nullable=False),
    Column("schema_version", String(20), nullable=False),
    Column("cli_version", String(120), nullable=False),
    Column("argument_profile", String(80), nullable=False),
    Column("prompt_template_version", String(80), nullable=False),
    Column("exit_status", Integer, nullable=False),
    Column("schema_valid", Boolean, nullable=False),
    Column("created_at", String(40), nullable=False),
)

family_audit_events = Table(
    "audit_events",
    family_metadata,
    Column("id", String(40), primary_key=True),
    Column("entity_type", String(40), nullable=False),
    Column("entity_id", String(40), nullable=False),
    Column("action", String(60), nullable=False),
    Column("before_hash", String(64)),
    Column("after_hash", String(64)),
    Column("created_at", String(40), nullable=False),
)

UniqueConstraint(
    policies.c.person_id, policies.c.product_version_id, name="uq_person_product_version"
)
