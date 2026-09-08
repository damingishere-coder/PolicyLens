from __future__ import annotations

import hashlib
import json
import os
import secrets
import shutil
from collections import Counter
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy import and_, insert, select, update

from .crypto import VAULT_AAD
from .domain import (
    CandidateComparisonRequest,
    EvidenceComparisonRequest,
    ResearchDiscoveredProduct,
    ResearchDiscoveryOutput,
    ResearchRunStatus,
    ResearchStartRequest,
    SourceAuthority,
    ValueOrigin,
)
from .ingestion import Candidate
from .models import (
    discovery_leads,
    import_sessions,
    insurers,
    official_domains,
    product_versions,
    products,
    research_runs,
    source_documents,
    source_revisions,
)
from .service import ConflictError, NotFoundError, PolicyLensService
from .web_fetcher import FetchedSource, FetchError, OfficialSourceFetcher, evidence_matches

RESEARCH_SCOPE = {
    "jurisdiction": "HK",
    "categories": ["LIFE_SAVINGS", "ANNUITY"],
    "insurer_ids": ["aia-hk", "prudential-hk", "manulife-hk"],
    "max_products_per_insurer": 5,
    "official_evidence_only": True,
}

INSURER_SEEDS = (
    {
        "id": "aia-hk",
        "legal_name": "AIA International Limited",
        "brand_name": "友邦香港",
        "hosts": ("aia.com.hk", "www.aia.com.hk"),
    },
    {
        "id": "prudential-hk",
        "legal_name": "Prudential Hong Kong Limited",
        "brand_name": "保诚香港",
        "hosts": ("prudential.com.hk", "www.prudential.com.hk"),
    },
    {
        "id": "manulife-hk",
        "legal_name": "Manulife (International) Limited",
        "brand_name": "宏利香港",
        "hosts": ("manulife.com.hk", "www.manulife.com.hk"),
    },
)

REQUIRED_RESEARCH_FIELDS = {
    "product.display_name",
    "product.version_label",
    "product.jurisdiction",
    "product.line_of_business",
    "product.currency",
    "product.insurer_id",
    "product.sale_status",
}

OFFICIAL_CANDIDATE_AUTHORITIES = {
    SourceAuthority.INSURER_OFFICIAL_DISCLOSURE.value,
    SourceAuthority.INSURER_OFFICIAL_WEB.value,
}


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}-{secrets.token_hex(8).upper()}"


def _hash_json(value: object) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _public_lead_url(url: str) -> str | None:
    try:
        parsed = urlsplit(url.strip())
        port = parsed.port
    except ValueError:
        return None
    if (
        parsed.scheme.lower() != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        return None
    if port not in {None, 443}:
        return None
    return urlunsplit(
        ("https", parsed.hostname.lower().rstrip("."), parsed.path or "/", parsed.query, "")
    )


class PublicResearchService:
    def __init__(self, core: PolicyLensService) -> None:
        self.core = core
        self._ensure_catalog()
        self._mark_interrupted_runs()

    def _ensure_catalog(self) -> None:
        now = _now()
        with self.core.db.research.begin() as connection:
            for seed in INSURER_SEEDS:
                exists = connection.execute(
                    select(insurers.c.id).where(insurers.c.id == seed["id"])
                ).first()
                if not exists:
                    connection.execute(
                        insert(insurers).values(
                            id=seed["id"],
                            legal_name=seed["legal_name"],
                            brand_name=seed["brand_name"],
                            jurisdiction="HK",
                            regulator_registration=None,
                            status="ACTIVE",
                            created_at=now,
                            updated_at=now,
                        )
                    )
                for host in seed["hosts"]:
                    domain = connection.execute(
                        select(official_domains.c.id).where(
                            and_(
                                official_domains.c.host == host,
                                official_domains.c.path_prefix == "/",
                            )
                        )
                    ).first()
                    if not domain:
                        connection.execute(
                            insert(official_domains).values(
                                id=_new_id("DOM"),
                                insurer_id=seed["id"],
                                host=host,
                                path_prefix="/",
                                https_only=True,
                                status="VERIFIED",
                                verified_at=now,
                            )
                        )

    def _mark_interrupted_runs(self) -> None:
        active = {
            ResearchRunStatus.QUEUED.value,
            ResearchRunStatus.DISCOVERING.value,
            ResearchRunStatus.FETCHING.value,
        }
        with self.core.db.research.begin() as connection:
            connection.execute(
                update(research_runs)
                .where(research_runs.c.status.in_(active))
                .values(
                    status=ResearchRunStatus.INTERRUPTED.value,
                    error_code="PROCESS_INTERRUPTED",
                    finished_at=_now(),
                )
            )

    def preview(self) -> dict[str, Any]:
        scope = dict(RESEARCH_SCOPE)
        preview = {
            "scope": scope,
            "insurers": [
                {
                    "id": item["id"],
                    "brand_name": item["brand_name"],
                    "legal_name": item["legal_name"],
                    "official_hosts": list(item["hosts"]),
                }
                for item in INSURER_SEEDS
            ],
            "query_summary": "香港储蓄保险与年金产品；全网发现线索，官方来源逐条验证",
            "will_send": ["固定公开研究主题", "三家公司名称", "预置官方域名"],
            "will_not_send": ["家庭成员资料", "保单资料", "本地文件内容", "本地路径"],
            "usage_notice": "启动后会使用当前 Codex CLI 账号执行一次实时网页搜索，消耗相应使用额度。",
            "argument_profile": "LIVE_SEARCH_EPHEMERAL_JSON_READ_ONLY_SCHEMA_V1",
            "requires_confirmation": True,
        }
        preview["preview_hash"] = _hash_json(preview)
        return preview

    def create_run(self, request: ResearchStartRequest) -> str:
        preview = self.preview()
        if request.preview_hash != preview["preview_hash"]:
            raise ConflictError("研究预览已经变化，请重新查看后再确认。")
        active = {
            ResearchRunStatus.QUEUED.value,
            ResearchRunStatus.DISCOVERING.value,
            ResearchRunStatus.FETCHING.value,
        }
        with self.core.db.research.begin() as connection:
            if connection.execute(
                select(research_runs.c.id).where(research_runs.c.status.in_(active))
            ).first():
                raise ConflictError("已有公开资料研究正在运行。")
            run_id = _new_id("RUN")
            now = _now()
            connection.execute(
                insert(research_runs).values(
                    id=run_id,
                    scope_json=json.dumps(RESEARCH_SCOPE, separators=(",", ":")),
                    preview_hash=request.preview_hash,
                    status=ResearchRunStatus.DISCOVERING.value,
                    request_hash=_hash_json(
                        {"preview_hash": request.preview_hash, "confirmed": request.confirmed}
                    ),
                    cli_version=None,
                    argument_profile=None,
                    summary_json="{}",
                    error_code=None,
                    cancel_requested=False,
                    created_at=now,
                    started_at=now,
                    finished_at=None,
                )
            )
        return run_id

    def _lead_view(self, item) -> dict[str, Any]:
        return {
            "id": item.id,
            "insurer_id": item.insurer_id,
            "title": item.title,
            "url": item.canonical_url,
            "channel": item.discovery_channel,
            "authority": item.authority,
            "official_verification_url": item.official_verification_url,
            "status": item.status,
            "rejection_code": item.rejection_code,
            "import_id": item.import_id,
        }

    @staticmethod
    def _insurer_outcomes(
        leads, run_status: str, error_code: str | None = None
    ) -> list[dict[str, Any]]:
        outcomes = []
        unsuccessful = run_status in {"FAILED", "CANCELLED", "INTERRUPTED"} and (
            error_code != "NO_VERIFIED_OFFICIAL_SOURCE"
        )
        terminal = run_status not in {
            ResearchRunStatus.QUEUED.value,
            ResearchRunStatus.DISCOVERING.value,
            ResearchRunStatus.FETCHING.value,
        }
        for insurer in INSURER_SEEDS:
            matched = [item for item in leads if item.insurer_id == insurer["id"]]
            official = [item for item in matched if item.discovery_channel == "OFFICIAL_SEARCH"]
            third_party = [item for item in matched if item.discovery_channel == "THIRD_PARTY_LEAD"]
            waiting = sum(item.status == "WAITING_REVIEW" for item in official)
            published = sum(item.status.startswith("PUBLISHED_") for item in official)
            rejected = sum(bool(item.rejection_code) for item in official)
            errors = sorted({item.rejection_code for item in matched if item.rejection_code})
            if unsuccessful:
                errors = sorted({*errors, error_code or f"RESEARCH_{run_status}"})
            elif terminal and not official:
                errors = sorted(
                    set(
                        [*errors, "NO_OFFICIAL_CANDIDATE" if third_party else "NO_RESULT_RETURNED"]
                    )
                )
            if waiting:
                status = "WAITING_REVIEW"
            elif published:
                status = "PUBLISHED"
            elif rejected:
                status = "REJECTED"
            elif third_party:
                status = "LEAD_ONLY"
            elif unsuccessful:
                status = run_status
            elif terminal:
                status = "NO_RESULT"
            else:
                status = "SEARCHING"
            outcomes.append(
                {
                    "insurer_id": insurer["id"],
                    "brand_name": insurer["brand_name"],
                    "status": status,
                    "official_candidates": len(official),
                    "waiting_review": waiting,
                    "published": published,
                    "rejected": rejected,
                    "lead_only": len(third_party),
                    "error_codes": errors,
                }
            )
        return outcomes

    def get_run(self, run_id: str) -> dict[str, Any]:
        with self.core.db.research.connect() as connection:
            row = connection.execute(
                select(research_runs).where(research_runs.c.id == run_id)
            ).first()
            if not row:
                raise NotFoundError("research run not found")
            leads = connection.execute(
                select(discovery_leads)
                .where(discovery_leads.c.research_run_id == run_id)
                .order_by(discovery_leads.c.discovered_at)
            ).all()
        return {
            "id": row.id,
            "status": row.status,
            "scope": json.loads(row.scope_json),
            "preview_hash": row.preview_hash,
            "cli_version": row.cli_version,
            "argument_profile": row.argument_profile,
            "summary": json.loads(row.summary_json),
            "error_code": row.error_code,
            "cancel_requested": bool(row.cancel_requested),
            "created_at": row.created_at,
            "started_at": row.started_at,
            "finished_at": row.finished_at,
            "leads": [self._lead_view(item) for item in leads],
            "insurer_outcomes": self._insurer_outcomes(leads, row.status, row.error_code),
        }

    def list_runs(self, limit: int = 10) -> list[dict[str, Any]]:
        with self.core.db.research.connect() as connection:
            ids = connection.execute(
                select(research_runs.c.id)
                .order_by(research_runs.c.created_at.desc())
                .limit(min(max(limit, 1), 50))
            ).scalars()
            return [self.get_run(run_id) for run_id in ids]

    def cancel_active(self) -> str | None:
        active = {
            ResearchRunStatus.QUEUED.value,
            ResearchRunStatus.DISCOVERING.value,
            ResearchRunStatus.FETCHING.value,
        }
        with self.core.db.research.begin() as connection:
            row = connection.execute(
                select(research_runs.c.id)
                .where(research_runs.c.status.in_(active))
                .order_by(research_runs.c.created_at.desc())
            ).first()
            if not row:
                return None
            connection.execute(
                update(research_runs)
                .where(research_runs.c.id == row.id)
                .values(cancel_requested=True)
            )
            return str(row.id)

    def fail_run(self, run_id: str, error_code: str, *, cancelled: bool = False) -> None:
        with self.core.db.research.begin() as connection:
            connection.execute(
                update(research_runs)
                .where(research_runs.c.id == run_id)
                .values(
                    status=(
                        ResearchRunStatus.CANCELLED.value
                        if cancelled
                        else ResearchRunStatus.FAILED.value
                    ),
                    error_code=error_code,
                    finished_at=_now(),
                )
            )

    def _insert_lead(
        self,
        connection,
        *,
        run_id: str,
        insurer_id: str,
        title: str,
        url: str,
        channel: str,
        authority: str,
        official_verification_url: str | None = None,
        status: str,
        rejection_code: str | None = None,
        import_id: str | None = None,
    ) -> None:
        canonical = _public_lead_url(url) or url[:2000]
        connection.execute(
            insert(discovery_leads).values(
                id=_new_id("LEAD"),
                research_run_id=run_id,
                insurer_id=insurer_id,
                title=title,
                canonical_url=canonical,
                url_hash=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
                discovery_channel=channel,
                authority=authority,
                official_verification_url=official_verification_url,
                status=status,
                rejection_code=rejection_code,
                import_id=import_id,
                discovered_at=_now(),
                last_checked_at=_now() if channel == "OFFICIAL_SEARCH" else None,
            )
        )

    def _store_source(
        self,
        run_id: str,
        product: ResearchDiscoveredProduct,
        fetched: FetchedSource,
    ) -> tuple[str, str]:
        authority = (
            SourceAuthority.INSURER_OFFICIAL_DISCLOSURE.value
            if fetched.content.startswith(b"%PDF-")
            else SourceAuthority.INSURER_OFFICIAL_WEB.value
        )
        vault_id = "VAULT-" + fetched.sha256[:24].upper()
        destination = self.core.data_dir / "vault" / f"{fetched.sha256}.vault"
        if not destination.exists():
            temporary = destination.with_suffix(".tmp")
            temporary.write_bytes(self.core.cipher.encrypt_bytes(fetched.content, VAULT_AAD))
            os.replace(temporary, destination)
        with self.core.db.research.begin() as connection:
            source = connection.execute(
                select(source_documents.c.id).where(source_documents.c.sha256 == fetched.sha256)
            ).first()
            if source:
                source_id = str(source.id)
            else:
                source_id = _new_id("SRC")
                connection.execute(
                    insert(source_documents).values(
                        id=source_id,
                        sha256=fetched.sha256,
                        title_encrypted=self.core.cipher.encrypt_text(product.source_title),
                        document_type=(
                            "OFFICIAL_PDF" if fetched.content.startswith(b"%PDF-") else "WEB_HTML"
                        ),
                        authority=authority,
                        page_count=fetched.page_count or 0,
                        extractor_version="codex-search-evidence-v1",
                        vault_id=vault_id,
                        status="FETCHED",
                        imported_at=_now(),
                    )
                )
            existing_revision = connection.execute(
                select(source_revisions.c.id).where(
                    and_(
                        source_revisions.c.canonical_url == fetched.canonical_url,
                        source_revisions.c.sha256 == fetched.sha256,
                    )
                )
            ).first()
            if existing_revision:
                revision_id = str(existing_revision.id)
            else:
                previous = connection.execute(
                    select(source_revisions.c.id)
                    .where(source_revisions.c.canonical_url == fetched.canonical_url)
                    .order_by(source_revisions.c.fetched_at.desc())
                ).first()
                revision_id = _new_id("REV")
                connection.execute(
                    insert(source_revisions).values(
                        id=revision_id,
                        source_document_id=source_id,
                        research_run_id=run_id,
                        canonical_url=fetched.canonical_url,
                        url_hash=hashlib.sha256(fetched.canonical_url.encode("utf-8")).hexdigest(),
                        host=fetched.host,
                        fetched_at=_now(),
                        http_status=fetched.status_code,
                        content_type=fetched.content_type,
                        etag=fetched.etag,
                        last_modified=fetched.last_modified,
                        byte_count=len(fetched.content),
                        sha256=fetched.sha256,
                        vault_id=vault_id,
                        previous_revision_id=previous.id if previous else None,
                        processing_status="FETCHED",
                    )
                )
        return source_id, revision_id

    @staticmethod
    def _semantic_product_error(product: ResearchDiscoveredProduct) -> str | None:
        values = {item.field_path: item.value for item in product.facts}
        if values.get("product.display_name") != product.display_name:
            return "IDENTITY_MISMATCH"
        if values.get("product.version_label") != product.version_label:
            return "IDENTITY_MISMATCH"
        if values.get("product.insurer_id") != product.insurer_id:
            return "INSURER_MISMATCH"
        if values.get("product.jurisdiction") != "HK":
            return "JURISDICTION_REJECTED"
        if values.get("product.line_of_business") not in {"LIFE_SAVINGS", "ANNUITY"}:
            return "CATEGORY_REJECTED"
        currency = values.get("product.currency", "")
        if len(currency) != 3 or not currency.isalpha() or currency.upper() != currency:
            return "CURRENCY_REJECTED"
        return None

    def _create_import(
        self,
        source_id: str,
        revision_id: str,
        product: ResearchDiscoveredProduct,
        fetched: FetchedSource,
    ) -> str | None:
        matched = [
            item for item in product.facts if evidence_matches(fetched.text, item.evidence_excerpt)
        ]
        if not REQUIRED_RESEARCH_FIELDS.issubset({item.field_path for item in matched}):
            with self.core.db.research.begin() as connection:
                connection.execute(
                    update(source_revisions)
                    .where(source_revisions.c.id == revision_id)
                    .values(processing_status="EVIDENCE_MISMATCH")
                )
            return None
        authority = (
            SourceAuthority.INSURER_OFFICIAL_DISCLOSURE
            if fetched.content.startswith(b"%PDF-")
            else SourceAuthority.INSURER_OFFICIAL_WEB
        )
        candidates = [
            Candidate(
                field_path=item.field_path,
                value=item.value,
                raw_value=item.value,
                unit=item.unit,
                page_number=item.page_number,
                excerpt=item.evidence_excerpt,
                value_origin=ValueOrigin.AI_EXTRACTION,
                source_authority=authority,
                guarantee_type=item.guarantee_type,
            )
            for item in matched
        ]
        import_id = _new_id("IMP")
        with self.core.db.research.begin() as connection:
            connection.execute(
                insert(import_sessions).values(
                    id=import_id,
                    source_id=source_id,
                    source_revision_id=revision_id,
                    status="WAITING_REVIEW",
                    duplicate=False,
                    created_at=_now(),
                )
            )
            self.core._insert_candidates(connection, import_id, candidates)
            connection.execute(
                update(source_documents)
                .where(source_documents.c.id == source_id)
                .values(status="WAITING_REVIEW")
            )
            connection.execute(
                update(source_revisions)
                .where(source_revisions.c.id == revision_id)
                .values(processing_status="WAITING_REVIEW")
            )
        return import_id

    def apply_discovery(
        self,
        run_id: str,
        output: ResearchDiscoveryOutput,
        fetcher: OfficialSourceFetcher,
        *,
        cli_version: str,
        argument_profile: str,
    ) -> dict[str, Any]:
        with self.core.db.research.begin() as connection:
            row = connection.execute(
                select(research_runs).where(research_runs.c.id == run_id)
            ).first()
            if not row:
                raise NotFoundError("research run not found")
            already_cancelled = bool(row.cancel_requested)
            if already_cancelled:
                connection.execute(
                    update(research_runs)
                    .where(research_runs.c.id == run_id)
                    .values(
                        status=ResearchRunStatus.CANCELLED.value,
                        error_code="USER_CANCELLED",
                        finished_at=_now(),
                    )
                )
            else:
                connection.execute(
                    update(research_runs)
                    .where(research_runs.c.id == run_id)
                    .values(
                        status=ResearchRunStatus.FETCHING.value,
                        cli_version=cli_version,
                        argument_profile=argument_profile,
                    )
                )
            if already_cancelled:
                return self.get_run(run_id)
            for lead in output.leads:
                canonical = _public_lead_url(lead.url)
                status = "LEAD_ONLY" if canonical else "REJECTED"
                self._insert_lead(
                    connection,
                    run_id=run_id,
                    insurer_id=lead.insurer_id,
                    title=lead.title,
                    url=lead.url,
                    channel=lead.channel,
                    authority=(
                        SourceAuthority.THIRD_PARTY_REFERENCE.value
                        if lead.channel == "THIRD_PARTY_LEAD"
                        else SourceAuthority.INSURER_OFFICIAL_WEB.value
                    ),
                    official_verification_url=lead.official_verification_url,
                    status=status,
                    rejection_code=None if canonical else "INVALID_LEAD_URL",
                )

        successes = 0
        rejected = 0
        per_insurer: Counter[str] = Counter()
        for product in output.products:
            if self.get_run(run_id)["cancel_requested"]:
                self.fail_run(run_id, "USER_CANCELLED", cancelled=True)
                return self.get_run(run_id)
            if per_insurer[product.insurer_id] >= RESEARCH_SCOPE["max_products_per_insurer"]:
                rejected += 1
                continue
            per_insurer[product.insurer_id] += 1
            semantic_error = self._semantic_product_error(product)
            import_id: str | None = None
            rejection_code = semantic_error
            fetched: FetchedSource | None = None
            if rejection_code is None:
                try:
                    fetched = fetcher.fetch(product.source_url, product.insurer_id)
                    expected_pdf = product.document_type == "OFFICIAL_PDF"
                    if expected_pdf != fetched.content.startswith(b"%PDF-"):
                        rejection_code = "DOCUMENT_TYPE_MISMATCH"
                    else:
                        source_id, revision_id = self._store_source(run_id, product, fetched)
                        import_id = self._create_import(source_id, revision_id, product, fetched)
                        if import_id is None:
                            rejection_code = "EVIDENCE_MISMATCH"
                except FetchError as exc:
                    rejection_code = exc.code
            status = "WAITING_REVIEW" if import_id else "REJECTED"
            if import_id:
                successes += 1
            else:
                rejected += 1
            with self.core.db.research.begin() as connection:
                self._insert_lead(
                    connection,
                    run_id=run_id,
                    insurer_id=product.insurer_id,
                    title=product.display_name,
                    url=product.source_url,
                    channel="OFFICIAL_SEARCH",
                    authority=(
                        SourceAuthority.INSURER_OFFICIAL_DISCLOSURE.value
                        if product.document_type == "OFFICIAL_PDF"
                        else SourceAuthority.INSURER_OFFICIAL_WEB.value
                    ),
                    official_verification_url=product.source_url,
                    status=status,
                    rejection_code=rejection_code,
                    import_id=import_id,
                )

        if successes and rejected:
            status = ResearchRunStatus.PARTIAL.value
        elif successes:
            status = ResearchRunStatus.WAITING_REVIEW.value
        elif output.leads:
            status = ResearchRunStatus.PARTIAL.value
        else:
            status = ResearchRunStatus.FAILED.value
        summary = {
            "discovered_products": len(output.products),
            "waiting_review": successes,
            "rejected_products": rejected,
            "lead_only": len(output.leads),
        }
        with self.core.db.research.begin() as connection:
            connection.execute(
                update(research_runs)
                .where(research_runs.c.id == run_id)
                .values(
                    status=status,
                    summary_json=json.dumps(summary, separators=(",", ":")),
                    error_code="NO_VERIFIED_OFFICIAL_SOURCE" if status == "FAILED" else None,
                    finished_at=_now(),
                )
            )
        return self.get_run(run_id)

    def dashboard(self) -> dict[str, Any]:
        runs = self.list_runs(5)
        candidates = self.list_candidates(status="WAITING_REVIEW")
        products_view = [item for item in self.core.list_products() if item["jurisdiction"] == "HK"]
        return {
            "insurers": [
                {"id": item["id"], "brand_name": item["brand_name"]} for item in INSURER_SEEDS
            ],
            "research_runs": len(runs),
            "waiting_review": len(candidates),
            "candidate_products": len(self.list_candidates()),
            "hk_products": len(products_view),
            "active_hk_products": sum(item["record_status"] == "ACTIVE" for item in products_view),
            "recent_runs": runs,
        }

    def readiness(self) -> dict[str, Any]:
        checks: list[dict[str, Any]] = []
        database_ready = False
        try:
            with self.core.db.research.connect() as connection:
                integrity = connection.exec_driver_sql("PRAGMA integrity_check").scalar_one()
            database_ready = integrity == "ok"
            checks.append(
                {
                    "id": "research_database",
                    "ready": database_ready,
                    "message": "研究数据库完整且迁移已就绪" if database_ready else "研究数据库完整性检查失败",
                }
            )
        except Exception:
            checks.append(
                {"id": "research_database", "ready": False, "message": "无法读取研究数据库"}
            )

        vault = self.core.data_dir / "vault"
        vault_ready = vault.is_dir() and os.access(vault, os.W_OK)
        checks.append(
            {
                "id": "encrypted_vault",
                "ready": vault_ready,
                "message": "加密来源仓可写" if vault_ready else "加密来源仓不可写",
            }
        )

        codex_command = os.environ.get("POLICYLENS_FAKE_CODEX_COMMAND", "codex")
        cli_path = shutil.which(codex_command)
        cli_ready = bool(cli_path)
        checks.append(
            {
                "id": "codex_cli",
                "ready": cli_ready,
                "message": "Codex CLI 可用" if cli_ready else "未找到 Codex CLI，暂时不能启动联网研究",
            }
        )
        active = next(
            (
                item
                for item in self.list_runs(10)
                if item["status"]
                in {
                    ResearchRunStatus.QUEUED.value,
                    ResearchRunStatus.DISCOVERING.value,
                    ResearchRunStatus.FETCHING.value,
                }
            ),
            None,
        )
        checks.append(
            {
                "id": "research_slot",
                "ready": active is None,
                "message": "可以启动一次新研究" if active is None else f"研究 {active['id']} 正在运行",
            }
        )
        return {
            "ready": all(item["ready"] for item in checks),
            "manual_confirmation_required": True,
            "checks": checks,
            "active_run_id": active["id"] if active else None,
        }

    def candidate(self, import_id: str) -> dict[str, Any]:
        with self.core.db.research.connect() as connection:
            lead = connection.execute(
                select(discovery_leads).where(discovery_leads.c.import_id == import_id)
            ).first()
            if not lead:
                raise NotFoundError("research candidate not found")
            if (
                lead.discovery_channel != "OFFICIAL_SEARCH"
                or lead.authority not in OFFICIAL_CANDIDATE_AUTHORITIES
            ):
                raise ConflictError("only official research candidates can be viewed")
            session = connection.execute(
                select(import_sessions).where(import_sessions.c.id == import_id)
            ).first()
            if not session:
                raise NotFoundError("candidate import session not found")
        imported = self.core.get_import(import_id)
        values = {item["field_path"]: item["value"] for item in imported["candidates"]}
        published_version = None
        if imported["status"] == "COMPLETED":
            with self.core.db.research.connect() as connection:
                match = and_(
                    product_versions.c.source_id == session.source_id,
                    product_versions.c.version_label
                    == values.get("product.version_label", "未知版本"),
                    products.c.display_name == values.get("product.display_name", lead.title),
                )
                insurer_id = values.get("product.insurer_id", lead.insurer_id)
                if insurer_id:
                    match = and_(match, products.c.insurer_id == insurer_id)
                published_version = connection.execute(
                    select(product_versions.c.id)
                    .join(products, product_versions.c.product_id == products.c.id)
                    .where(match)
                    .order_by(product_versions.c.created_at.desc())
                    .limit(1)
                ).scalar_one_or_none()
        missing = sorted(REQUIRED_RESEARCH_FIELDS - set(values))
        return {
            "import_id": import_id,
            "run_id": lead.research_run_id,
            "lead_id": lead.id,
            "review_status": imported["status"],
            "verification_label": (
                "UNVERIFIED_CANDIDATE"
                if imported["status"] == "WAITING_REVIEW"
                else "REVIEW_COMPLETED"
            ),
            "display_name": values.get("product.display_name", lead.title),
            "version_label": values.get("product.version_label", "未知版本"),
            "insurer_id": values.get("product.insurer_id", lead.insurer_id),
            "jurisdiction": values.get("product.jurisdiction"),
            "line_of_business": values.get("product.line_of_business"),
            "currency": values.get("product.currency"),
            "sale_status": values.get("product.sale_status"),
            "missing_fields": missing,
            "field_count": len(imported["candidates"]),
            "published_product_version_id": published_version,
            "source": imported["source"],
            "fields": imported["candidates"],
        }

    def list_candidates(
        self, *, run_id: str | None = None, status: str | None = None
    ) -> list[dict[str, Any]]:
        if status not in {None, "WAITING_REVIEW", "COMPLETED"}:
            raise ConflictError("candidate status must be WAITING_REVIEW or COMPLETED")
        with self.core.db.research.connect() as connection:
            query = (
                select(discovery_leads.c.import_id)
                .join(import_sessions, discovery_leads.c.import_id == import_sessions.c.id)
                .where(
                    and_(
                        discovery_leads.c.discovery_channel == "OFFICIAL_SEARCH",
                        discovery_leads.c.authority.in_(OFFICIAL_CANDIDATE_AUTHORITIES),
                        discovery_leads.c.import_id.is_not(None),
                    )
                )
                .order_by(import_sessions.c.created_at.desc())
                .limit(100)
            )
            if run_id:
                query = query.where(discovery_leads.c.research_run_id == run_id)
            if status:
                query = query.where(import_sessions.c.status == status)
            ids = list(connection.execute(query).scalars())
        return [self.candidate(import_id) for import_id in ids]

    def candidate_comparison(self, request: CandidateComparisonRequest) -> dict[str, Any]:
        candidates = [self.candidate(import_id) for import_id in request.import_ids]
        fields = sorted(
            {
                item["field_path"]
                for candidate in candidates
                for item in candidate["fields"]
                if item["decision"] != "REJECT"
            }
        )
        rows = []
        for field in fields:
            cells = []
            for candidate in candidates:
                value = next(
                    (item for item in candidate["fields"] if item["field_path"] == field), None
                )
                cells.append(
                    {
                        "import_id": candidate["import_id"],
                        "candidate_id": value["id"] if value else None,
                        "value": value["value"] if value else None,
                        "unit": value["unit"] if value else None,
                        "verification_status": (
                            value["verification_status"] if value else "UNKNOWN"
                        ),
                        "guarantee_type": value["guarantee_type"] if value else "UNKNOWN",
                        "source_authority": value["source_authority"] if value else None,
                        "page_number": value["page_number"] if value else None,
                        "excerpt": value["excerpt"] if value else None,
                        "source_url": candidate["source"].get("canonical_url"),
                    }
                )
            rows.append({"field_path": field, "cells": cells})
        return {
            "candidates": [
                {
                    "import_id": item["import_id"],
                    "display_name": item["display_name"],
                    "version_label": item["version_label"],
                    "insurer_id": item["insurer_id"],
                    "review_status": item["review_status"],
                    "verification_label": item["verification_label"],
                }
                for item in candidates
            ],
            "rows": rows,
            "notice": "这是官方来源候选的待核验对比，不是正式产品结论；发布前必须逐项人工核验。",
        }

    def search(self, query: str) -> dict[str, Any]:
        needle = query.strip().casefold()
        if len(needle) < 2:
            raise ConflictError("搜索词至少需要 2 个字符。")
        product_results = [
            item
            for item in self.core.list_products()
            if needle in str(item["display_name"]).casefold()
            or needle in str(item["version_label"]).casefold()
        ][:20]
        source_results = [
            item for item in self.core.list_sources() if needle in str(item["title"]).casefold()
        ][:20]
        candidate_results = [
            item
            for item in self.list_candidates()
            if needle in str(item["display_name"]).casefold()
            or needle in str(item["version_label"]).casefold()
            or needle in str(item["insurer_id"]).casefold()
            or needle in str(item["source"]["title"]).casefold()
        ][:20]
        return {
            "query": query.strip(),
            "products": product_results,
            "candidates": candidate_results,
            "sources": source_results,
        }

    def evidence_comparison(self, request: EvidenceComparisonRequest) -> dict[str, Any]:
        product_views = [self.core.get_product(item) for item in request.product_version_ids]
        if any(item["record_status"] != "ACTIVE" for item in product_views):
            raise ConflictError("evidence comparison only accepts active verified products")
        fields = sorted(
            {
                fact["field_path"]
                for product in product_views
                for fact in product["facts"]
                if fact["verification_status"] != "REJECTED"
            }
        )
        rows = []
        for field in fields:
            cells = []
            for product in product_views:
                fact = next(
                    (item for item in reversed(product["facts"]) if item["field_path"] == field),
                    None,
                )
                cells.append(
                    {
                        "version_id": product["version_id"],
                        "value": fact["normalized_value"] if fact else None,
                        "unit": fact["unit"] if fact else None,
                        "verification_status": (fact["verification_status"] if fact else "UNKNOWN"),
                        "guarantee_type": fact["guarantee_type"] if fact else "UNKNOWN",
                        "evidence_count": len(fact["evidence"]) if fact else 0,
                        "evidence_ids": [item["id"] for item in fact["evidence"]] if fact else [],
                    }
                )
            rows.append({"field_path": field, "cells": cells})
        return {
            "products": [
                {
                    "version_id": item["version_id"],
                    "display_name": item["display_name"],
                    "version_label": item["version_label"],
                    "insurer_id": item["insurer_id"],
                }
                for item in product_views
            ],
            "rows": rows,
            "notice": "只展示已入库事实及其核验状态，不生成产品排名、推荐或综合分数。",
        }
