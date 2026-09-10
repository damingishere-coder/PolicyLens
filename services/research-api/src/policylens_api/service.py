from __future__ import annotations

import hashlib
import json
import os
import secrets
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import and_, func, insert, select, update

from .backup import BackupManager
from .crypto import VAULT_AAD, EnvelopeCipher, KeyManager, KeyProtector
from .database import DatabaseManager
from .domain import (
    AnalysisStatus,
    CandidateDecision,
    CodexPreviewRequest,
    ImportReviewRequest,
    ManualMaterialRequest,
    PolicyCreateRequest,
    SaveAnalysisRequest,
    SourceAuthority,
    ValueOrigin,
    VerificationStatus,
)
from .ingestion import EXTRACTOR_VERSION, Candidate, ParsedPdf, parse_text_pdf
from .models import (
    ai_analysis_runs,
    candidate_fields,
    comparison_cases,
    discovery_leads,
    evidence_anchors,
    fact_evidence,
    facts,
    family_audit_events,
    import_sessions,
    persons,
    policies,
    policy_premium_records,
    premium_rates,
    product_version_sources,
    product_versions,
    products,
    rate_adjustment_rules,
    renewal_terms,
    research_audit_events,
    research_runs,
    source_documents,
    source_revisions,
    workspaces,
)

TRUSTED_AUTHORITIES = {
    SourceAuthority.CONTRACT_DOCUMENT.value,
    SourceAuthority.REGULATOR_PUBLICATION.value,
    SourceAuthority.INSURER_OFFICIAL_DISCLOSURE.value,
    SourceAuthority.INSURER_OFFICIAL_WEB.value,
}


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}-{secrets.token_hex(8).upper()}"


def _row(row) -> dict[str, Any]:
    return dict(row._mapping)


def _hash_json(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class ServiceError(RuntimeError):
    code = "SERVICE_ERROR"


class NotFoundError(ServiceError):
    code = "NOT_FOUND"


class ConflictError(ServiceError):
    code = "CONFLICT"


class PolicyLensService:
    def __init__(self, data_dir: Path, protector: KeyProtector | None = None) -> None:
        self.data_dir = data_dir.resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        for directory in ("databases", "vault", "backups", "exports", "logs", "temp", "keys"):
            (self.data_dir / directory).mkdir(parents=True, exist_ok=True)
        self.key_manager = KeyManager(self.data_dir, protector)
        self.dek = self.key_manager.load_or_create()
        self.cipher = EnvelopeCipher(self.dek)
        self.db = DatabaseManager(self.data_dir)
        self.backups = BackupManager(self.data_dir, self.key_manager, self.dek)
        self._ensure_workspace()

    def _ensure_workspace(self) -> None:
        with self.db.family.begin() as connection:
            if connection.execute(select(func.count()).select_from(workspaces)).scalar_one() == 0:
                connection.execute(
                    insert(workspaces).values(
                        id="WORKSPACE-LOCAL",
                        default_region="CN_MAINLAND",
                        display_currency="CNY",
                        codex_enabled=False,
                        created_at=_now(),
                    )
                )

    def _store_parsed_pdf(self, parsed: ParsedPdf, content: bytes) -> dict[str, Any]:
        with self.db.research.begin() as connection:
            existing = connection.execute(
                select(source_documents.c.id).where(source_documents.c.sha256 == parsed.sha256)
            ).first()
            if existing:
                session = connection.execute(
                    select(import_sessions.c.id)
                    .where(import_sessions.c.source_id == existing.id)
                    .order_by(import_sessions.c.created_at.desc())
                ).first()
                if session:
                    result = self.get_import(session.id)
                    result["duplicate"] = True
                    return result

            source_id = _new_id("SRC")
            import_id = _new_id("IMP")
            vault_id = "VAULT-" + parsed.sha256[:24].upper()
            encrypted = self.cipher.encrypt_bytes(content, VAULT_AAD)
            vault_destination = self.data_dir / "vault" / f"{parsed.sha256}.vault"
            temporary = vault_destination.with_suffix(".tmp")
            temporary.write_bytes(encrypted)
            os.replace(temporary, vault_destination)
            authority = (
                parsed.candidates[0].source_authority.value
                if parsed.candidates
                else SourceAuthority.UNATTRIBUTED.value
            )
            connection.execute(
                insert(source_documents).values(
                    id=source_id,
                    sha256=parsed.sha256,
                    title_encrypted=self.cipher.encrypt_text(parsed.title),
                    document_type="TEXT_PDF",
                    authority=authority,
                    page_count=parsed.page_count,
                    extractor_version=EXTRACTOR_VERSION,
                    vault_id=vault_id,
                    status="WAITING_REVIEW",
                    imported_at=_now(),
                )
            )
            connection.execute(
                insert(import_sessions).values(
                    id=import_id,
                    source_id=source_id,
                    status="WAITING_REVIEW",
                    duplicate=False,
                    created_at=_now(),
                )
            )
            self._insert_candidates(connection, import_id, parsed.candidates)
        return self.get_import(import_id)

    def import_pdf(
        self, content: bytes, file_name: str, authority: SourceAuthority
    ) -> dict[str, Any]:
        parsed = parse_text_pdf(content, file_name, authority)
        return self._store_parsed_pdf(parsed, content)

    def import_manual(self, request: ManualMaterialRequest) -> dict[str, Any]:
        material = request.model_dump(mode="json")
        digest = _hash_json(material)
        fields: list[tuple[str, str, str | None]] = [
            ("product.display_name", request.display_name, None),
            ("product.version_label", request.version_label, None),
            ("product.jurisdiction", request.jurisdiction, None),
            ("product.line_of_business", request.line_of_business, None),
            ("product.currency", request.currency, None),
            ("premium_rate.amount", request.annual_premium, "currency/year"),
            ("renewal_terms.renewal_mode", request.renewal_mode.value, None),
            (
                "rate_adjustment_rule.scope",
                request.rate_adjustment_scope.value,
                None,
            ),
        ]
        if request.guarantee_period_years is not None:
            fields.append(
                (
                    "renewal_terms.guarantee_period_years",
                    str(request.guarantee_period_years),
                    "years",
                )
            )
        if request.maximum_renewal_age is not None:
            fields.append(
                (
                    "renewal_terms.maximum_renewal_age",
                    str(request.maximum_renewal_age),
                    "years",
                )
            )
        if request.benefit_limit is not None:
            fields.append(("benefit.limit", request.benefit_limit, "currency"))
        candidates = [
            Candidate(
                field_path=field,
                value=value,
                raw_value=value,
                unit=unit,
                page_number=1,
                excerpt=request.evidence_note,
                value_origin=ValueOrigin.MANUAL_ENTRY,
                source_authority=request.source_authority,
            )
            for field, value, unit in fields
        ]
        parsed = ParsedPdf(
            sha256=digest,
            title=f"手工资料：{request.display_name}",
            page_count=1,
            candidates=candidates,
        )
        with self.db.research.begin() as connection:
            existing = connection.execute(
                select(source_documents.c.id).where(source_documents.c.sha256 == digest)
            ).first()
            if existing:
                session = connection.execute(
                    select(import_sessions.c.id)
                    .where(import_sessions.c.source_id == existing.id)
                    .order_by(import_sessions.c.created_at.desc())
                ).first()
                if session:
                    result = self.get_import(session.id)
                    result["duplicate"] = True
                    return result
            source_id = _new_id("SRC")
            import_id = _new_id("IMP")
            connection.execute(
                insert(source_documents).values(
                    id=source_id,
                    sha256=digest,
                    title_encrypted=self.cipher.encrypt_text(parsed.title),
                    document_type="MANUAL_MATERIAL",
                    authority=request.source_authority.value,
                    page_count=1,
                    extractor_version="manual-v1",
                    vault_id=None,
                    status="WAITING_REVIEW",
                    imported_at=_now(),
                )
            )
            connection.execute(
                insert(import_sessions).values(
                    id=import_id,
                    source_id=source_id,
                    status="WAITING_REVIEW",
                    duplicate=False,
                    created_at=_now(),
                )
            )
            self._insert_candidates(connection, import_id, candidates)
        return self.get_import(import_id)

    def _insert_candidates(self, connection, import_id: str, values: list[Candidate]) -> None:
        for candidate in values:
            excerpt = candidate.excerpt[:600]
            connection.execute(
                insert(candidate_fields).values(
                    id=_new_id("CAN"),
                    import_session_id=import_id,
                    field_path=candidate.field_path,
                    value_encrypted=self.cipher.encrypt_text(candidate.value),
                    raw_value_encrypted=self.cipher.encrypt_text(candidate.raw_value),
                    unit=candidate.unit,
                    page_number=candidate.page_number,
                    excerpt_encrypted=self.cipher.encrypt_text(excerpt),
                    excerpt_hash=hashlib.sha256(excerpt.encode("utf-8")).hexdigest(),
                    verification_status=VerificationStatus.UNVERIFIED.value,
                    value_origin=candidate.value_origin.value,
                    source_authority=candidate.source_authority.value,
                    guarantee_type=candidate.guarantee_type.value,
                    decision=None,
                    extractor_version=(
                        "codex-search-evidence-v1"
                        if candidate.value_origin == ValueOrigin.AI_EXTRACTION
                        else EXTRACTOR_VERSION
                    ),
                )
            )

    def get_import(self, import_id: str) -> dict[str, Any]:
        with self.db.research.connect() as connection:
            session = connection.execute(
                select(import_sessions, source_documents)
                .join(source_documents, import_sessions.c.source_id == source_documents.c.id)
                .where(import_sessions.c.id == import_id)
            ).first()
            if not session:
                raise NotFoundError("import session not found")
            data = _row(session)
            candidates = connection.execute(
                select(candidate_fields)
                .where(candidate_fields.c.import_session_id == import_id)
                .order_by(candidate_fields.c.field_path)
            ).all()
            revision = (
                connection.execute(
                    select(source_revisions).where(
                        source_revisions.c.id == data["source_revision_id"]
                    )
                ).first()
                if data.get("source_revision_id")
                else None
            )
        return {
            "id": data["id"],
            "status": data["status"],
            "duplicate": bool(data["duplicate"]),
            "source": {
                "id": data["source_id"],
                "title": self.cipher.decrypt_text(data["title_encrypted"]),
                "document_type": data["document_type"],
                "authority": data["authority"],
                "page_count": data["page_count"],
                "sha256": data["sha256"],
                "canonical_url": revision.canonical_url if revision else None,
                "fetched_at": revision.fetched_at if revision else None,
            },
            "candidates": [self._candidate_view(_row(item)) for item in candidates],
        }

    def _candidate_view(self, value: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": value["id"],
            "field_path": value["field_path"],
            "value": self.cipher.decrypt_text(value["value_encrypted"]),
            "raw_value": self.cipher.decrypt_text(value["raw_value_encrypted"]),
            "unit": value["unit"],
            "page_number": value["page_number"],
            "excerpt": self.cipher.decrypt_text(value["excerpt_encrypted"]),
            "excerpt_hash": value["excerpt_hash"],
            "verification_status": value["verification_status"],
            "value_origin": value["value_origin"],
            "source_authority": value["source_authority"],
            "guarantee_type": value["guarantee_type"],
            "decision": value["decision"],
        }

    def list_imports(self) -> list[dict[str, Any]]:
        with self.db.research.connect() as connection:
            ids = connection.execute(
                select(import_sessions.c.id).order_by(import_sessions.c.created_at.desc()).limit(20)
            ).scalars()
            return [self.get_import(import_id) for import_id in ids]

    def review_import(self, import_id: str, request: ImportReviewRequest) -> dict[str, Any]:
        decisions = {item.candidate_id: item for item in request.decisions}
        if len(decisions) != len(request.decisions):
            raise ConflictError("candidate decisions contain duplicate ids")
        with self.db.research.begin() as connection:
            session = connection.execute(
                select(import_sessions).where(import_sessions.c.id == import_id)
            ).first()
            if not session:
                raise NotFoundError("import session not found")
            if session.status != "WAITING_REVIEW":
                raise ConflictError("import session is no longer waiting for review")
            rows = connection.execute(
                select(candidate_fields).where(candidate_fields.c.import_session_id == import_id)
            ).all()
            if {row.id for row in rows} != set(decisions):
                raise ConflictError("every candidate must receive exactly one review decision")

            accepted: dict[str, tuple[dict[str, Any], str, str]] = {}
            for row_value in rows:
                item = _row(row_value)
                decision: CandidateDecision = decisions[item["id"]]
                current_value = self.cipher.decrypt_text(item["value_encrypted"])
                chosen_value = (
                    decision.edited_value if decision.decision == "EDIT" else current_value
                )
                if decision.decision in {"ACCEPT", "EDIT"}:
                    verification = (
                        VerificationStatus.VERIFIED.value
                        if item["source_authority"] in TRUSTED_AUTHORITIES
                        else VerificationStatus.UNVERIFIED.value
                    )
                    accepted[item["field_path"]] = (item, chosen_value or "", verification)
                elif decision.decision == "REJECT":
                    verification = VerificationStatus.REJECTED.value
                else:
                    verification = VerificationStatus.UNVERIFIED.value
                values: dict[str, Any] = {
                    "decision": decision.decision,
                    "verification_status": verification,
                }
                if decision.decision == "EDIT":
                    values["value_encrypted"] = self.cipher.encrypt_text(chosen_value or "")
                connection.execute(
                    update(candidate_fields)
                    .where(candidate_fields.c.id == item["id"])
                    .values(**values)
                )

            display = accepted.get("product.display_name")
            if not display:
                raise ConflictError("product name must be accepted before publishing")
            source_id = session.source_id
            product_id, product_version_id, record_status = self._publish_product(
                connection, source_id, accepted, session.source_revision_id
            )
            connection.execute(
                update(import_sessions)
                .where(import_sessions.c.id == import_id)
                .values(status="COMPLETED")
            )
            connection.execute(
                update(source_documents)
                .where(source_documents.c.id == source_id)
                .values(status="VERIFIED" if record_status == "ACTIVE" else "REVIEWED")
            )
            lead = connection.execute(
                select(discovery_leads).where(discovery_leads.c.import_id == import_id)
            ).first()
            if lead:
                connection.execute(
                    update(discovery_leads)
                    .where(discovery_leads.c.id == lead.id)
                    .values(
                        status=(
                            "PUBLISHED_ACTIVE" if record_status == "ACTIVE" else "PUBLISHED_DRAFT"
                        ),
                        last_checked_at=_now(),
                    )
                )
                pending = connection.execute(
                    select(func.count())
                    .select_from(discovery_leads)
                    .where(
                        and_(
                            discovery_leads.c.research_run_id == lead.research_run_id,
                            discovery_leads.c.status == "WAITING_REVIEW",
                        )
                    )
                ).scalar_one()
                published_active = connection.execute(
                    select(func.count())
                    .select_from(discovery_leads)
                    .where(
                        and_(
                            discovery_leads.c.research_run_id == lead.research_run_id,
                            discovery_leads.c.status == "PUBLISHED_ACTIVE",
                        )
                    )
                ).scalar_one()
                published_draft = connection.execute(
                    select(func.count())
                    .select_from(discovery_leads)
                    .where(
                        and_(
                            discovery_leads.c.research_run_id == lead.research_run_id,
                            discovery_leads.c.status == "PUBLISHED_DRAFT",
                        )
                    )
                ).scalar_one()
                run = connection.execute(
                    select(research_runs).where(research_runs.c.id == lead.research_run_id)
                ).first()
                if run:
                    summary = json.loads(run.summary_json)
                    summary.update(
                        {
                            "waiting_review": pending,
                            "published_active": published_active,
                            "published_draft": published_draft,
                        }
                    )
                    terminal_status = run.status
                    if pending == 0:
                        terminal_status = (
                            "PARTIAL"
                            if published_draft or int(summary.get("rejected_products", 0))
                            else "COMPLETED"
                        )
                    connection.execute(
                        update(research_runs)
                        .where(research_runs.c.id == lead.research_run_id)
                        .values(
                            status=terminal_status,
                            summary_json=json.dumps(summary, separators=(",", ":")),
                            finished_at=_now() if pending == 0 else run.finished_at,
                        )
                    )
            connection.execute(
                insert(research_audit_events).values(
                    id=_new_id("AUD"),
                    entity_type="IMPORT_SESSION",
                    entity_id=import_id,
                    action="HUMAN_REVIEW_COMPLETED",
                    before_hash=None,
                    after_hash=_hash_json({"decisions": sorted(decisions)}),
                    created_at=_now(),
                )
            )
        return {
            "import": self.get_import(import_id),
            "product_id": product_id,
            "product_version_id": product_version_id,
        }

    def _publish_product(
        self,
        connection,
        source_id: str,
        accepted: dict[str, tuple[dict[str, Any], str, str]],
        source_revision_id: str | None = None,
    ) -> tuple[str, str, str]:
        def value(path: str, default: str) -> str:
            item = accepted.get(path)
            return item[1] if item else default

        product_id = _new_id("PRD")
        version_id = _new_id("PV")
        revision = (
            connection.execute(
                select(source_revisions).where(source_revisions.c.id == source_revision_id)
            ).first()
            if source_revision_id
            else None
        )
        required_fields = {
            "product.display_name",
            "product.version_label",
            "product.jurisdiction",
            "product.line_of_business",
            "product.currency",
        }
        if revision:
            required_fields.update({"product.insurer_id", "product.sale_status"})
        verified = required_fields.issubset(accepted) and all(
            accepted[field][2] == VerificationStatus.VERIFIED.value for field in required_fields
        )
        record_status = "ACTIVE" if verified else "DRAFT"
        now = _now()
        connection.execute(
            insert(products).values(
                id=product_id,
                display_name=value("product.display_name", "未命名产品"),
                jurisdiction=value("product.jurisdiction", "CN_MAINLAND"),
                line_of_business=value("product.line_of_business", "OTHER"),
                currency=value("product.currency", "CNY"),
                insurer_id=value("product.insurer_id", "") or None,
                product_category=value(
                    "product.product_category", value("product.line_of_business", "OTHER")
                ),
                sale_status=value("product.sale_status", "UNKNOWN"),
                first_seen_at=now if revision else None,
                last_seen_at=now if revision else None,
                created_at=now,
            )
        )
        connection.execute(
            insert(product_versions).values(
                id=version_id,
                product_id=product_id,
                version_label=value("product.version_label", "导入版本 1"),
                effective_date=None,
                record_status=record_status,
                source_id=source_id,
                created_at=_now(),
            )
        )
        if revision:
            connection.execute(
                insert(product_version_sources).values(
                    product_version_id=version_id,
                    source_revision_id=revision.id,
                    role="PRIMARY_PRODUCT_SOURCE",
                )
            )
        connection.execute(
            insert(renewal_terms).values(
                id=_new_id("REN"),
                product_version_id=version_id,
                renewal_mode=value("renewal_terms.renewal_mode", "UNKNOWN"),
                guarantee_period_years=self._optional_int(
                    value("renewal_terms.guarantee_period_years", "")
                ),
                maximum_renewal_age=self._optional_int(
                    value("renewal_terms.maximum_renewal_age", "")
                ),
                requires_reunderwriting=None,
                reassesses_health=None,
                waiting_period_days=None,
                continuity_conditions=None,
                discontinuation_treatment=None,
                termination_conditions=None,
            )
        )
        premium_id: str | None = None
        premium = accepted.get("premium_rate.amount")
        if premium:
            premium_id = _new_id("RATE")
            connection.execute(
                insert(premium_rates).values(
                    id=premium_id,
                    product_version_id=version_id,
                    version_label=value("product.version_label", "导入费率 1"),
                    valid_from=None,
                    valid_to=None,
                    currency=value("product.currency", "CNY"),
                    frequency="ANNUAL",
                    amount=premium[1],
                    pricing_dimensions_json="{}",
                )
            )
        connection.execute(
            insert(rate_adjustment_rules).values(
                id=_new_id("ADJ"),
                product_version_id=version_id,
                scope=value("rate_adjustment_rule.scope", "UNKNOWN"),
                trigger_conditions=None,
                frequency=None,
                notice_days=None,
                cap=None,
                floor=None,
                effective_from=None,
            )
        )

        evidence_cache: dict[tuple[int | None, str, str], str] = {}
        for field_path, (candidate, chosen_value, verification) in accepted.items():
            evidence_key = (
                candidate["page_number"],
                candidate["excerpt_hash"],
                candidate["source_authority"],
            )
            evidence_id = evidence_cache.get(evidence_key)
            if evidence_id is None:
                evidence_id = _new_id("EV")
                evidence_cache[evidence_key] = evidence_id
                connection.execute(
                    insert(evidence_anchors).values(
                        id=evidence_id,
                        source_id=source_id,
                        source_revision_id=revision.id if revision else None,
                        page_number=candidate["page_number"],
                        locator_json=(
                            json.dumps({"type": "WEB_TEXT"}, separators=(",", ":"))
                            if revision and candidate["page_number"] is None
                            else None
                        ),
                        excerpt_encrypted=candidate["excerpt_encrypted"],
                        excerpt_hash=candidate["excerpt_hash"],
                        authority=candidate["source_authority"],
                    )
                )
            fact_id = _new_id("FACT")
            guarantee_type = candidate.get("guarantee_type") or "UNKNOWN"
            if (
                field_path == "renewal_terms.renewal_mode"
                and chosen_value == "GUARANTEED_RENEWAL"
                and candidate["source_authority"] == SourceAuthority.CONTRACT_DOCUMENT.value
            ):
                guarantee_type = "CONTRACT_GUARANTEED"
            connection.execute(
                insert(facts).values(
                    id=fact_id,
                    product_version_id=version_id,
                    field_path=field_path,
                    normalized_value=chosen_value,
                    raw_value_encrypted=candidate["raw_value_encrypted"],
                    unit=candidate["unit"],
                    guarantee_type=guarantee_type,
                    verification_status=verification,
                    value_origin=candidate["value_origin"],
                    verified_at=_now() if verification == "VERIFIED" else None,
                    supersedes_fact_id=None,
                    created_at=_now(),
                )
            )
            connection.execute(
                insert(fact_evidence).values(fact_id=fact_id, evidence_id=evidence_id)
            )
        return product_id, version_id, record_status

    @staticmethod
    def _optional_int(value: str) -> int | None:
        return int(value) if value.isdigit() else None

    def list_products(self, include_drafts: bool = True) -> list[dict[str, Any]]:
        query = (
            select(
                products.c.id,
                products.c.display_name,
                products.c.jurisdiction,
                products.c.line_of_business,
                products.c.currency,
                products.c.insurer_id,
                products.c.product_category,
                products.c.sale_status,
                products.c.first_seen_at,
                products.c.last_seen_at,
                product_versions.c.id.label("version_id"),
                product_versions.c.version_label,
                product_versions.c.record_status,
            )
            .join(product_versions, products.c.id == product_versions.c.product_id)
            .order_by(products.c.created_at.desc())
        )
        if not include_drafts:
            query = query.where(product_versions.c.record_status == "ACTIVE")
        with self.db.research.connect() as connection:
            rows = connection.execute(query).all()
            output = []
            for row_value in rows:
                item = _row(row_value)
                item["verified_facts"] = connection.execute(
                    select(func.count())
                    .select_from(facts)
                    .where(
                        and_(
                            facts.c.product_version_id == item["version_id"],
                            facts.c.verification_status == VerificationStatus.VERIFIED.value,
                        )
                    )
                ).scalar_one()
                output.append(item)
            return output

    def get_product(self, version_id: str) -> dict[str, Any]:
        with self.db.research.connect() as connection:
            base = connection.execute(
                select(
                    products,
                    product_versions.c.id.label("version_id"),
                    product_versions.c.version_label,
                    product_versions.c.record_status,
                    product_versions.c.source_id,
                    product_versions.c.created_at.label("version_created_at"),
                )
                .join(product_versions, products.c.id == product_versions.c.product_id)
                .where(product_versions.c.id == version_id)
            ).first()
            if not base:
                raise NotFoundError("product version not found")
            renewal = connection.execute(
                select(renewal_terms).where(renewal_terms.c.product_version_id == version_id)
            ).first()
            rate = connection.execute(
                select(premium_rates).where(premium_rates.c.product_version_id == version_id)
            ).first()
            adjustment = connection.execute(
                select(rate_adjustment_rules).where(
                    rate_adjustment_rules.c.product_version_id == version_id
                )
            ).first()
            fact_rows = connection.execute(
                select(facts)
                .where(facts.c.product_version_id == version_id)
                .order_by(facts.c.field_path)
            ).all()
            fact_views: list[dict[str, Any]] = []
            for fact_row in fact_rows:
                item = _row(fact_row)
                evidence_rows = connection.execute(
                    select(evidence_anchors)
                    .join(fact_evidence, evidence_anchors.c.id == fact_evidence.c.evidence_id)
                    .where(fact_evidence.c.fact_id == item["id"])
                ).all()
                item["evidence"] = [self._evidence_view(_row(entry)) for entry in evidence_rows]
                item.pop("raw_value_encrypted", None)
                fact_views.append(item)
        base_view = _row(base)
        return {
            "id": base_view["id"],
            "display_name": base_view["display_name"],
            "jurisdiction": base_view["jurisdiction"],
            "line_of_business": base_view["line_of_business"],
            "currency": base_view["currency"],
            "insurer_id": base_view["insurer_id"],
            "product_category": base_view["product_category"],
            "sale_status": base_view["sale_status"],
            "first_seen_at": base_view["first_seen_at"],
            "last_seen_at": base_view["last_seen_at"],
            "version_id": base_view["version_id"],
            "version_label": base_view["version_label"],
            "record_status": base_view["record_status"],
            "renewal_terms": _row(renewal) if renewal else None,
            "premium_rate": _row(rate) if rate else None,
            "rate_adjustment_rule": _row(adjustment) if adjustment else None,
            "facts": fact_views,
        }

    def _evidence_view(self, item: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": item["id"],
            "source_id": item["source_id"],
            "page_number": item["page_number"],
            "excerpt": self.cipher.decrypt_text(item["excerpt_encrypted"]),
            "excerpt_hash": item["excerpt_hash"],
            "authority": item["authority"],
            "source_revision_id": item.get("source_revision_id"),
            "locator": json.loads(item["locator_json"]) if item.get("locator_json") else None,
        }

    def create_policy(self, request: PolicyCreateRequest) -> dict[str, Any]:
        product = self.get_product(request.product_version_id)
        if product["record_status"] != "ACTIVE":
            raise ConflictError("only a verified active product version can be linked to a policy")
        person_id = _new_id("PERSON")
        policy_id = _new_id("POL")
        premium_id = _new_id("PAY")
        with self.db.family.begin() as connection:
            connection.execute(
                insert(persons).values(
                    id=person_id,
                    nickname_encrypted=self.cipher.encrypt_text(request.member_nickname),
                    created_at=_now(),
                )
            )
            connection.execute(
                insert(policies).values(
                    id=policy_id,
                    person_id=person_id,
                    product_version_id=request.product_version_id,
                    category=request.category,
                    status=request.status,
                    created_at=_now(),
                )
            )
            connection.execute(
                insert(policy_premium_records).values(
                    id=premium_id,
                    policy_id=policy_id,
                    due_amount_encrypted=self.cipher.encrypt_text(request.due_amount),
                    paid_amount_encrypted=(
                        self.cipher.encrypt_text(request.paid_amount)
                        if request.paid_amount is not None
                        else None
                    ),
                    currency=request.currency,
                    frequency=request.frequency,
                    due_date=request.due_date.isoformat(),
                    paid_date=request.paid_date.isoformat() if request.paid_date else None,
                    premium_rate_id=None,
                )
            )
            connection.execute(
                insert(family_audit_events).values(
                    id=_new_id("AUD"),
                    entity_type="POLICY",
                    entity_id=policy_id,
                    action="CREATED",
                    before_hash=None,
                    after_hash=_hash_json(
                        {
                            "product_version_id": request.product_version_id,
                            "category": request.category,
                        }
                    ),
                    created_at=_now(),
                )
            )
        return self.get_policy(policy_id)

    def list_policies(self) -> list[dict[str, Any]]:
        with self.db.family.connect() as connection:
            ids = connection.execute(
                select(policies.c.id).order_by(policies.c.created_at.desc())
            ).scalars()
            return [self.get_policy(policy_id) for policy_id in ids]

    def get_policy(self, policy_id: str) -> dict[str, Any]:
        with self.db.family.connect() as connection:
            base = connection.execute(
                select(policies, persons.c.nickname_encrypted)
                .outerjoin(persons, policies.c.person_id == persons.c.id)
                .where(policies.c.id == policy_id)
            ).first()
            if not base:
                raise NotFoundError("policy not found")
            payments = connection.execute(
                select(policy_premium_records).where(
                    policy_premium_records.c.policy_id == policy_id
                )
            ).all()
        data = _row(base)
        product = self.get_product(data["product_version_id"]) if data["product_version_id"] else None
        return {
            "id": data["id"],
            "member_nickname": self.cipher.decrypt_text(data["nickname_encrypted"]) if data["nickname_encrypted"] else None,
            "category": data["category"],
            "status": data["status"],
            "product": product,
            "premium_records": [self._premium_record_view(_row(item)) for item in payments],
        }

    def _premium_record_view(self, item: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": item["id"],
            "due_amount": self.cipher.decrypt_text(item["due_amount_encrypted"]),
            "paid_amount": (
                self.cipher.decrypt_text(item["paid_amount_encrypted"])
                if item["paid_amount_encrypted"]
                else None
            ),
            "currency": item["currency"],
            "frequency": item["frequency"],
            "due_date": item["due_date"],
            "paid_date": item["paid_date"],
            "premium_rate_id": item["premium_rate_id"],
        }

    def dashboard(self) -> dict[str, Any]:
        policies_view = self.list_policies()
        products_view = self.list_products()
        imports_view = self.list_imports()
        annual_total = sum((
            Decimal(record["paid_amount"])
            for policy in policies_view
            for record in policy["premium_records"]
            if record["currency"] == "CNY" and record["paid_amount"] is not None
            and record["paid_date"] and record["paid_date"].startswith(f"{date.today().year}-")
        ), Decimal(0))
        with self.db.family.connect() as connection:
            member_count = connection.execute(select(func.count()).select_from(persons)).scalar_one()
        pending = sum(
            1
            for item in imports_view
            for candidate in item["candidates"]
            if candidate["verification_status"] in {"UNVERIFIED", "CONFLICTING", "STALE"}
        )
        return {
            "members": member_count,
            "active_policies": sum(item["status"] == "ACTIVE" for item in policies_view),
            "annual_premium_cny": f"{annual_total:.2f}",
            "pending_verification": pending,
            "local_products": len(products_view),
            "recent_imports": [
                {
                    "id": item["id"],
                    "title": item["source"]["title"],
                    "status": item["status"],
                }
                for item in imports_view[:4]
            ],
        }

    def list_sources(self) -> list[dict[str, Any]]:
        with self.db.research.connect() as connection:
            rows = connection.execute(
                select(source_documents).order_by(source_documents.c.imported_at.desc())
            ).all()
            output = []
            for row_value in rows:
                item = _row(row_value)
                revision = connection.execute(
                    select(source_revisions)
                    .where(source_revisions.c.source_document_id == item["id"])
                    .order_by(source_revisions.c.fetched_at.desc())
                ).first()
                evidence_count = connection.execute(
                    select(func.count())
                    .select_from(evidence_anchors)
                    .where(evidence_anchors.c.source_id == item["id"])
                ).scalar_one()
                output.append(
                    {
                        "id": item["id"],
                        "title": self.cipher.decrypt_text(item["title_encrypted"]),
                        "document_type": item["document_type"],
                        "authority": item["authority"],
                        "page_count": item["page_count"],
                        "sha256": item["sha256"],
                        "status": item["status"],
                        "evidence_count": evidence_count,
                        "imported_at": item["imported_at"],
                        "canonical_url": revision.canonical_url if revision else None,
                        "fetched_at": revision.fetched_at if revision else None,
                        "content_type": revision.content_type if revision else None,
                    }
                )
            return output

    def compare(self, version_ids: list[str]) -> dict[str, Any]:
        if len(version_ids) != 2 or len(set(version_ids)) != 2:
            raise ConflictError("comparison requires exactly two distinct product versions")
        product_views = [self.get_product(item) for item in version_ids]
        if any(item["record_status"] != "ACTIVE" for item in product_views):
            raise ConflictError("comparison only accepts active, verified product versions")
        snapshot = {
            "version_ids": version_ids,
            "algorithm_version": "basic-comparison-v1",
            "products": [
                {"version_id": item["version_id"], "facts": item["facts"]} for item in product_views
            ],
        }
        case_id = _new_id("CMP")
        with self.db.family.begin() as connection:
            connection.execute(
                insert(comparison_cases).values(
                    id=case_id,
                    product_version_ids_json=json.dumps(version_ids),
                    input_snapshot_hash=_hash_json(snapshot),
                    algorithm_version="basic-comparison-v1",
                    created_at=_now(),
                )
            )
        return {
            "case_id": case_id,
            "algorithm_version": "basic-comparison-v1",
            "products": product_views,
            "notice": "续保权利、标准费率、调费规则与实际缴费彼此独立；保证续保不表示保费固定。",
        }

    def codex_preview(self, request: CodexPreviewRequest) -> dict[str, Any]:
        compared = self.compare(request.product_version_ids)
        products_payload: list[dict[str, Any]] = []
        all_evidence: dict[str, dict[str, str]] = {}
        seen_evidence: set[str] = set()
        for product in compared["products"]:
            product_facts = []
            for fact in product["facts"]:
                evidence_ids = [
                    item["id"]
                    for item in fact["evidence"]
                    if request.evidence_ids is None or item["id"] in request.evidence_ids
                ]
                product_facts.append(
                    {
                        "field": fact["field_path"],
                        "value": fact["normalized_value"],
                        "unit": fact["unit"],
                        "guaranteeType": fact["guarantee_type"],
                        "verificationStatus": fact["verification_status"],
                        "valueOrigin": fact["value_origin"],
                        "evidenceIds": evidence_ids,
                    }
                )
                for evidence in fact["evidence"]:
                    if evidence["id"] in seen_evidence:
                        continue
                    excerpt = evidence["excerpt"]
                    if len(excerpt) > 600:
                        raise ConflictError("evidence excerpt exceeds the 600-character limit")
                    all_evidence[evidence["id"]] = {
                        "evidenceId": evidence["id"],
                        "text": excerpt,
                        "authority": evidence["authority"],
                        "field": fact["field_path"],
                        "product": product["display_name"],
                    }
                    seen_evidence.add(evidence["id"])
            public_id = (
                "PUB-" + hashlib.sha256(product["version_id"].encode()).hexdigest()[:12].upper()
            )
            products_payload.append(
                {
                    "publicId": public_id,
                    "displayName": product["display_name"],
                    "versionLabel": product["version_label"],
                    "jurisdiction": product["jurisdiction"],
                    "currency": product["currency"],
                    "facts": product_facts,
                }
            )
        if request.evidence_ids is None and len(all_evidence) > 12:
            return {
                "requires_selection": True,
                "evidence_options": list(all_evidence.values()),
                "limits": {"max_excerpts": 12, "max_each_characters": 600, "max_total": 7200},
                "message": "证据超过 12 段，请主动选择本次要发送的摘录。",
            }
        selected_ids = request.evidence_ids or list(all_evidence)
        if any(item not in all_evidence for item in selected_ids):
            raise ConflictError("selected evidence is outside the comparison")
        evidence_payload = [
            {key: all_evidence[item][key] for key in ("evidenceId", "text", "authority")}
            for item in selected_ids
        ]
        total_excerpt_length = sum(len(item["text"]) for item in evidence_payload)
        if len(evidence_payload) > 12 or total_excerpt_length > 7200:
            raise ConflictError("selected evidence exceeds the external data limits")
        payload = {
            "schemaVersion": "1.0",
            "comparison": {
                "products": products_payload,
                "evidenceExcerpts": evidence_payload,
            },
        }
        return {
            "payload": payload,
            "preview_hash": _hash_json(payload),
            "excerpt_count": len(evidence_payload),
            "excerpt_characters": total_excerpt_length,
            "warnings": [
                "Codex 进程拥有当前 Windows 用户权限；临时目录与只读 sandbox 只是纵深防御。",
                "本预览由白名单字段直接构造，不包含原始文件、私人路径、vault ID 或身份字段。",
            ],
        }

    def save_analysis(self, request: SaveAnalysisRequest) -> dict[str, Any]:
        result_evidence = {
            evidence_id
            for difference in request.result.differences
            for evidence_id in difference.evidence_ids
        }
        allowed = set(request.evidence_ids)
        if not result_evidence.issubset(allowed):
            raise ConflictError("Codex result references evidence outside the approved preview")
        if allowed:
            with self.db.research.connect() as connection:
                found = set(
                    connection.execute(
                        select(evidence_anchors.c.id).where(evidence_anchors.c.id.in_(allowed))
                    ).scalars()
                )
            if found != allowed:
                raise ConflictError("Codex result references unknown evidence")
        analysis_id = _new_id("AI")
        with self.db.family.begin() as connection:
            connection.execute(
                insert(ai_analysis_runs).values(
                    id=analysis_id,
                    preview_hash=request.preview_hash,
                    evidence_ids_json=json.dumps(request.evidence_ids),
                    status=AnalysisStatus.DRAFT.value,
                    result_json=request.result.model_dump_json(),
                    schema_version="1.0",
                    cli_version=request.cli_version,
                    argument_profile=request.argument_profile,
                    prompt_template_version=request.prompt_template_version,
                    exit_status=request.exit_status,
                    schema_valid=request.schema_valid,
                    created_at=_now(),
                )
            )
        return self.get_analysis(analysis_id)

    def list_analyses(self) -> list[dict[str, Any]]:
        with self.db.family.connect() as connection:
            identifiers = connection.execute(select(ai_analysis_runs.c.id).order_by(ai_analysis_runs.c.created_at.desc())).scalars().all()
        return [self.get_analysis(identifier) for identifier in identifiers]

    def get_analysis(self, analysis_id: str) -> dict[str, Any]:
        with self.db.family.connect() as connection:
            row_value = connection.execute(
                select(ai_analysis_runs).where(ai_analysis_runs.c.id == analysis_id)
            ).first()
        if not row_value:
            raise NotFoundError("analysis draft not found")
        item = _row(row_value)
        return {
            "id": item["id"],
            "preview_hash": item["preview_hash"],
            "evidence_ids": json.loads(item["evidence_ids_json"]),
            "status": item["status"],
            "result": json.loads(item["result_json"]),
            "schema_version": item["schema_version"],
            "cli_version": item["cli_version"],
            "argument_profile": item["argument_profile"],
            "prompt_template_version": item["prompt_template_version"],
            "exit_status": item["exit_status"],
            "schema_valid": item["schema_valid"],
            "created_at": item["created_at"],
            "fact_verification_changed": False,
        }

    def update_analysis_status(self, analysis_id: str, status: str) -> dict[str, Any]:
        with self.db.family.begin() as connection:
            if not connection.execute(
                select(ai_analysis_runs.c.id).where(ai_analysis_runs.c.id == analysis_id)
            ).first():
                raise NotFoundError("analysis draft not found")
            connection.execute(
                update(ai_analysis_runs)
                .where(ai_analysis_runs.c.id == analysis_id)
                .values(status=status)
            )
        return self.get_analysis(analysis_id)

    def create_backup(self, password: str, destination: Path) -> dict[str, object]:
        return self.backups.create_portable(password, destination)

    def preview_restore(self, password: str, source: Path) -> dict[str, object]:
        return self.backups.preview_restore(password, source)

    def commit_restore(self, token: str) -> dict[str, object]:
        self.db.dispose()
        candidate_db = None
        candidate_cipher = None
        candidate_dek = None

        def validate_switch(expected_dek: bytes):
            nonlocal candidate_db, candidate_cipher, candidate_dek
            try:
                candidate_dek = self.key_manager.load_or_create()
                if candidate_dek != expected_dek:
                    raise ServiceError("恢复密钥与已验证备份不一致")
                candidate_cipher = EnvelopeCipher(candidate_dek)
                candidate_db = DatabaseManager(self.data_dir)
                # Verify actual key/data compatibility before dropping rollback directories.
                for engine, metadata in [(candidate_db.family, persons.metadata), (candidate_db.research, products.metadata)]:
                    with engine.connect() as connection:
                        for table in metadata.sorted_tables:
                            encrypted = [column for column in table.columns if column.name.endswith("_encrypted")]
                            if not encrypted:
                                continue
                            for row in connection.execute(select(*encrypted)):
                                for value in row:
                                    if value is not None:
                                        candidate_cipher.decrypt_text(value)
            except Exception:
                if candidate_db:
                    candidate_db.dispose()
                if candidate_cipher:
                    candidate_cipher.clear()
                raise
        try:
            result = self.backups.commit_restore(token, validate_switch)
            self.cipher.clear()
            self.dek = candidate_dek
            self.cipher = candidate_cipher
            self.db = candidate_db
            self.backups = BackupManager(self.data_dir, self.key_manager, self.dek)
            return result
        except Exception:
            # Existing engines use NullPool and still point at the restored original paths.
            # Keep the original, uncleared key and cipher when post-switch validation fails.
            raise

    def settings(self) -> dict[str, Any]:
        return {
            "data_directory": str(self.data_dir),
            "database_directory": str(self.data_dir / "databases"),
            "vault_directory": str(self.data_dir / "vault"),
            "backup_directory": str(self.data_dir / "backups"),
            "encryption": "AES-256-GCM",
            "local_key_wrapper": self.key_manager.protector.name,
            "portable_backup_kdf": "Argon2id m=65536 KiB, t=3, p=1",
            "telemetry": False,
            "codex_default_enabled": False,
        }

    def shutdown(self) -> None:
        self.backups.clear_plans()
        self.db.dispose()
        self.cipher.clear()
