from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import threading
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, ClassVar
from urllib.parse import urlsplit

from fastapi import FastAPI, File, Form, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .backup import BackupError
from .codex_runner import CodexRunner, CodexRunnerError
from .crypto import KeyProtector
from .domain import (
    AnalysisStatusRequest,
    BackupPasswordRequest,
    CandidateComparisonRequest,
    CodexPreviewRequest,
    CodexRunRequest,
    EvidenceComparisonRequest,
    ImportReviewRequest,
    ManualMaterialRequest,
    PolicyCreateRequest,
    ResearchStartRequest,
    RestoreCommitRequest,
    SaveAnalysisRequest,
    SemanticEnumsResponse,
    SourceAuthority,
    ValueOrigin,
    VerificationStatus,
)
from .ingestion import MAX_PDF_BYTES, ImportValidationError
from .migrations import SCHEMA_VERSION
from .public_research import PublicResearchService
from .research_codex_runner import ResearchCodexError, ResearchCodexRunner
from .service import PolicyLensService, ServiceError
from .web_fetcher import FetchedSource, OfficialSourceFetcher

MAX_REQUEST_BYTES = 128 * 1024 * 1024
MAX_BACKUP_BYTES = 120 * 1024 * 1024
LOOPBACK_HOST = re.compile(r"^(127\.0\.0\.1|localhost)(:\d+)?$", re.I)
SESSION_COOKIE = "policylens_session"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


class SafeEventLog:
    def __init__(self, data_dir: Path) -> None:
        self.path = data_dir / "logs" / "events.jsonl"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, event: str, code: str, request_id: str) -> None:
        record = {
            "timestamp": datetime.now(UTC).isoformat(),
            "event": event,
            "code": code,
            "request_id": request_id,
        }
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, separators=(",", ":")) + "\n")


class _SyntheticResearchSourceFetcher:
    """Deterministic official-source fixture, enabled only by explicit test mode."""

    NAMES: ClassVar[dict[str, str]] = {
        "aia-hk": "SYNTHETIC Future Savings Plan",
        "prudential-hk": "SYNTHETIC Retirement Plan",
    }

    def fetch(self, url: str, insurer_id: str) -> FetchedSource:
        name = self.NAMES[insurer_id]
        text = " ".join(
            [
                f"Official product name is {name}",
                "September 2026 official edition",
                "This product is issued in HK",
                "Product category is LIFE_SAVINGS",
                "The primary illustration currency is HKD",
                f"Official insurer identity is {insurer_id}",
                "Sale status is ACTIVE",
                "Premium payment terms include 5 years",
            ]
        )
        content = f"<html><body>{text}</body></html>".encode()
        return FetchedSource(
            canonical_url=url,
            host=urlsplit(url).hostname or "",
            status_code=200,
            content_type="text/html",
            content=content,
            text=text,
            sha256=hashlib.sha256(content).hexdigest(),
            page_count=None,
            etag='"synthetic-browser-v1"',
            last_modified=None,
        )

    def close(self) -> None:
        return None


def create_app(
    data_dir: Path,
    token: str | None = None,
    *,
    protector: KeyProtector | None = None,
    testing: bool = False,
    bound_port: int | None = None,
    browser_mode: bool = False,
    static_dir: Path | None = None,
    manager: str = "manual",
    codex_runner: CodexRunner | None = None,
    research_runner: ResearchCodexRunner | None = None,
    source_fetcher: OfficialSourceFetcher | None = None,
) -> FastAPI:
    service = PolicyLensService(data_dir, protector)
    public_research = PublicResearchService(service)
    event_log = SafeEventLog(data_dir)
    session_secret = secrets.token_bytes(32)
    schema_source = (
        Path(__file__).resolve().parents[4]
        / "packages"
        / "contracts"
        / "schemas"
        / "codex-analysis.schema.json"
    )
    if codex_runner is None:
        command = "codex"
        prefix_args: list[str] = []
        timeout_seconds = 120.0
        if os.environ.get("POLICYLENS_TEST_MODE") == "1":
            command = os.environ.get("POLICYLENS_FAKE_CODEX_COMMAND", command)
            fake_script = os.environ.get("POLICYLENS_FAKE_CODEX_SCRIPT")
            if fake_script:
                prefix_args = [fake_script]
            timeout_seconds = 15.0
        codex_runner = CodexRunner(
            data_dir,
            schema_source,
            command=command,
            prefix_args=prefix_args,
            timeout_seconds=timeout_seconds,
        )
    if research_runner is None:
        research_command = "codex"
        research_prefix_args: list[str] = []
        research_timeout = 240.0
        if os.environ.get("POLICYLENS_TEST_MODE") == "1":
            research_command = os.environ.get(
                "POLICYLENS_FAKE_RESEARCH_CODEX_COMMAND", research_command
            )
            fake_research_script = os.environ.get("POLICYLENS_FAKE_RESEARCH_CODEX_SCRIPT")
            if fake_research_script:
                research_prefix_args = [fake_research_script]
            research_timeout = 15.0
        research_runner = ResearchCodexRunner(
            data_dir,
            command=research_command,
            prefix_args=research_prefix_args,
            timeout_seconds=research_timeout,
        )
    if source_fetcher is None:
        source_fetcher = (
            _SyntheticResearchSourceFetcher()
            if os.environ.get("POLICYLENS_TEST_MODE") == "1"
            and os.environ.get("POLICYLENS_FAKE_RESEARCH_SOURCE") == "1"
            else OfficialSourceFetcher()
        )
    research_threads: set[threading.Thread] = set()
    research_threads_lock = threading.Lock()

    def execute_public_research(run_id: str) -> None:
        try:
            if public_research.get_run(run_id)["cancel_requested"]:
                public_research.fail_run(run_id, "USER_CANCELLED", cancelled=True)
                return
            executed = research_runner.run()
            public_research.apply_discovery(
                run_id,
                executed["result"],
                source_fetcher,
                cli_version=str(executed["cli_version"]),
                argument_profile=str(executed["argument_profile"]),
            )
        except ResearchCodexError as exc:
            cancelled = public_research.get_run(run_id)["cancel_requested"]
            public_research.fail_run(
                run_id,
                "USER_CANCELLED" if cancelled else exc.code,
                cancelled=bool(cancelled),
            )
        except Exception:
            public_research.fail_run(run_id, "RESEARCH_PIPELINE_FAILED")
        finally:
            current = threading.current_thread()
            with research_threads_lock:
                research_threads.discard(current)

    def signed_value(label: str, value: str) -> str:
        return hmac.new(
            session_secret,
            f"{label}:{value}".encode(),
            hashlib.sha256,
        ).hexdigest()

    def valid_session(cookie: str | None) -> str | None:
        if not cookie or "." not in cookie:
            return None
        session_id, supplied = cookie.rsplit(".", 1)
        if len(session_id) < 32 or not hmac.compare_digest(
            supplied, signed_value("session", session_id)
        ):
            return None
        return session_id

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        codex_runner.cancel()
        research_runner.cancel()
        with research_threads_lock:
            active_threads = list(research_threads)
        for thread in active_threads:
            thread.join(timeout=5)
        source_fetcher.close()
        service.shutdown()

    app = FastAPI(
        title="PolicyLens Local Research API",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.service = service
    app.state.token = token
    app.state.testing = testing
    app.state.browser_mode = browser_mode
    app.state.codex_runner = codex_runner
    app.state.public_research = public_research
    app.state.research_runner = research_runner

    @app.middleware("http")
    async def local_security(request: Request, call_next):
        request_id = secrets.token_hex(8)
        host = request.headers.get("host", "")
        if not LOOPBACK_HOST.fullmatch(host) and not (testing and host == "testserver"):
            event_log.write("request_rejected", "NON_LOOPBACK_HOST", request_id)
            return JSONResponse(status_code=403, content={"code": "NON_LOOPBACK_HOST"})
        origin = request.headers.get("origin")
        expected_origin = f"http://{host}"
        origin_allowed = (
            origin == expected_origin
            if browser_mode
            else bool(
                origin is None
                or origin.startswith("http://127.0.0.1:")
                or origin.startswith("http://localhost:")
            )
        )
        if origin and not origin_allowed:
            event_log.write("request_rejected", "NON_LOOPBACK_ORIGIN", request_id)
            return JSONResponse(status_code=403, content={"code": "NON_LOOPBACK_ORIGIN"})
        length = request.headers.get("content-length")
        if length:
            try:
                too_large = int(length) > MAX_REQUEST_BYTES
            except ValueError:
                too_large = True
            if too_large:
                event_log.write("request_rejected", "REQUEST_TOO_LARGE", request_id)
                return JSONResponse(status_code=413, content={"code": "REQUEST_TOO_LARGE"})
        if browser_mode:
            is_api = request.url.path.startswith("/api/")
            session_public = request.url.path == "/api/v1/session"
            if is_api and not session_public:
                session_id = valid_session(request.cookies.get(SESSION_COOKIE))
                if session_id is None:
                    event_log.write("request_rejected", "INVALID_BROWSER_SESSION", request_id)
                    return JSONResponse(
                        status_code=401, content={"code": "INVALID_BROWSER_SESSION"}
                    )
                if request.method not in SAFE_METHODS:
                    supplied_csrf = request.headers.get("x-policylens-csrf", "")
                    expected_csrf = signed_value("csrf", session_id)
                    if origin != expected_origin or not hmac.compare_digest(
                        supplied_csrf, expected_csrf
                    ):
                        event_log.write("request_rejected", "INVALID_CSRF", request_id)
                        return JSONResponse(status_code=403, content={"code": "INVALID_CSRF"})
        else:
            supplied = request.headers.get("x-policylens-token", "")
            if token is None or not secrets.compare_digest(supplied, token):
                event_log.write("request_rejected", "INVALID_LOCAL_TOKEN", request_id)
                return JSONResponse(status_code=401, content={"code": "INVALID_LOCAL_TOKEN"})
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data: blob:; font-src 'self'; connect-src 'self'; "
            "object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        )
        return response

    @app.exception_handler(ServiceError)
    async def service_error(_request: Request, exc: ServiceError):
        event_log.write("service_error", exc.code, secrets.token_hex(8))
        status = 404 if exc.code == "NOT_FOUND" else 409
        return JSONResponse(status_code=status, content={"code": exc.code, "message": str(exc)})

    @app.exception_handler(ImportValidationError)
    async def import_error(_request: Request, exc: ImportValidationError):
        event_log.write("import_rejected", exc.code, secrets.token_hex(8))
        return JSONResponse(status_code=422, content={"code": exc.code, "message": str(exc)})

    @app.exception_handler(BackupError)
    async def backup_error(_request: Request, exc: BackupError):
        event_log.write("backup_error", exc.code, secrets.token_hex(8))
        return JSONResponse(status_code=422, content={"code": exc.code, "message": str(exc)})

    @app.exception_handler(CodexRunnerError)
    async def codex_error(_request: Request, exc: CodexRunnerError):
        event_log.write("codex_error", exc.code, secrets.token_hex(8))
        return JSONResponse(status_code=422, content={"code": exc.code, "message": str(exc)})

    @app.exception_handler(ResearchCodexError)
    async def research_codex_error(_request: Request, exc: ResearchCodexError):
        event_log.write("research_codex_error", exc.code, secrets.token_hex(8))
        return JSONResponse(status_code=422, content={"code": exc.code, "message": str(exc)})

    @app.get("/api/v1/session", tags=["system"])
    def create_browser_session(response: Response) -> dict[str, str]:
        if not browser_mode:
            return {"mode": "header-token", "csrf_token": "not-applicable"}
        session_id = secrets.token_urlsafe(32)
        cookie = f"{session_id}.{signed_value('session', session_id)}"
        response.set_cookie(
            SESSION_COOKIE,
            cookie,
            httponly=True,
            secure=False,
            samesite="strict",
            path="/",
        )
        return {
            "mode": "localhost-browser",
            "csrf_token": signed_value("csrf", session_id),
        }

    @app.get("/health", tags=["system"])
    def health() -> dict[str, object]:
        return {
            "status": "ok",
            "service": "policylens",
            "mode": "localhost-browser" if browser_mode else "header-token-test",
            "pid": os.getpid(),
            "host": "127.0.0.1",
            "port": bound_port,
            "schema_version": SCHEMA_VERSION,
        }

    @app.get("/api/v1/runtime", tags=["system"])
    def runtime() -> dict[str, object]:
        return {
            "servicePid": os.getpid(),
            "serviceHost": "127.0.0.1",
            "servicePort": bound_port,
            "manager": manager,
            "browserMode": browser_mode,
            "sessionProtection": "HttpOnly SameSite=Strict + CSRF",
        }

    @app.get("/api/v1/dashboard", tags=["workspace"])
    def dashboard() -> dict[str, object]:
        return service.dashboard()

    @app.get("/api/v1/research/dashboard", tags=["research"])
    def research_dashboard() -> dict[str, object]:
        return public_research.dashboard()

    @app.get("/api/v1/research/readiness", tags=["research"])
    def research_readiness() -> dict[str, object]:
        return public_research.readiness()

    @app.get("/api/v1/research/candidates", tags=["research"])
    def list_research_candidates(
        run_id: str | None = Query(default=None, max_length=40),
        status: str | None = Query(default=None, max_length=40),
    ) -> list[dict[str, object]]:
        return public_research.list_candidates(run_id=run_id, status=status)

    @app.get("/api/v1/research/candidates/{import_id}", tags=["research"])
    def get_research_candidate(import_id: str) -> dict[str, object]:
        return public_research.candidate(import_id)

    @app.post("/api/v1/research/candidate-comparisons", tags=["research"])
    def compare_research_candidates(request: CandidateComparisonRequest) -> dict[str, object]:
        return public_research.candidate_comparison(request)

    @app.post("/api/v1/research/preview", tags=["research"])
    def research_preview() -> dict[str, object]:
        return public_research.preview()

    @app.get("/api/v1/research/runs", tags=["research"])
    def list_research_runs(limit: int = Query(default=10, ge=1, le=50)) -> list[dict[str, object]]:
        return public_research.list_runs(limit)

    @app.get("/api/v1/research/runs/{run_id}", tags=["research"])
    def get_research_run(run_id: str) -> dict[str, object]:
        return public_research.get_run(run_id)

    @app.post("/api/v1/research/runs", tags=["research"])
    def run_public_research(request: ResearchStartRequest) -> dict[str, object]:
        run_id = public_research.create_run(request)
        thread = threading.Thread(
            target=execute_public_research,
            args=(run_id,),
            name=f"PolicyLensResearch-{run_id[-8:]}",
            daemon=True,
        )
        with research_threads_lock:
            research_threads.add(thread)
        thread.start()
        return public_research.get_run(run_id)

    @app.post("/api/v1/research/runs/{run_id}/cancel", tags=["research"])
    def cancel_public_research(run_id: str) -> dict[str, object]:
        current = public_research.get_run(run_id)
        if current["status"] not in {"QUEUED", "DISCOVERING", "FETCHING"}:
            return {"cancelled": False, "run": current}
        active_id = public_research.cancel_active()
        process_terminated = research_runner.cancel() if active_id == run_id else False
        return {
            "cancelled": active_id == run_id,
            "process_terminated": process_terminated,
            "run_id": run_id,
        }

    @app.get("/api/v1/research/products", tags=["research"])
    def list_research_products(include_drafts: bool = True) -> list[dict[str, object]]:
        return [
            item
            for item in service.list_products(include_drafts)
            if item["jurisdiction"] == "HK"
            and item["line_of_business"] in {"LIFE_SAVINGS", "ANNUITY"}
        ]

    @app.get("/api/v1/search", tags=["workspace"])
    def local_search(q: str = Query(min_length=2, max_length=120)) -> dict[str, object]:
        return public_research.search(q)

    @app.get("/api/v1/imports", tags=["imports"])
    def list_imports() -> list[dict[str, object]]:
        return service.list_imports()

    @app.get("/api/v1/imports/{import_id}", tags=["imports"])
    def get_import(import_id: str) -> dict[str, object]:
        return service.get_import(import_id)

    @app.post("/api/v1/imports/manual", tags=["imports"])
    def import_manual(request: ManualMaterialRequest) -> dict[str, object]:
        return service.import_manual(request)

    @app.post("/api/v1/imports/pdf", tags=["imports"])
    async def import_pdf(
        file: Annotated[UploadFile, File()],
        authority: Annotated[SourceAuthority, Form()],
    ) -> dict[str, object]:
        content = await file.read(MAX_PDF_BYTES + 1)
        return service.import_pdf(content, file.filename or "document.pdf", authority)

    @app.post("/api/v1/imports/{import_id}/review", tags=["imports"])
    def review_import(import_id: str, request: ImportReviewRequest) -> dict[str, object]:
        return service.review_import(import_id, request)

    @app.get("/api/v1/products", tags=["products"])
    def list_products(include_drafts: bool = True) -> list[dict[str, object]]:
        return service.list_products(include_drafts)

    @app.get("/api/v1/products/{version_id}", tags=["products"])
    def get_product(version_id: str) -> dict[str, object]:
        return service.get_product(version_id)

    @app.get("/api/v1/policies", tags=["policies"])
    def list_policies() -> list[dict[str, object]]:
        return service.list_policies()

    @app.post("/api/v1/policies", tags=["policies"])
    def create_policy(request: PolicyCreateRequest) -> dict[str, object]:
        return service.create_policy(request)

    @app.get("/api/v1/policies/{policy_id}", tags=["policies"])
    def get_policy(policy_id: str) -> dict[str, object]:
        return service.get_policy(policy_id)

    @app.get("/api/v1/sources", tags=["evidence"])
    def list_sources() -> list[dict[str, object]]:
        return service.list_sources()

    @app.post("/api/v1/comparisons/basic", tags=["comparison"])
    def compare(request: CodexPreviewRequest) -> dict[str, object]:
        return service.compare(request.product_version_ids)

    @app.post("/api/v1/comparisons/evidence", tags=["comparison"])
    def evidence_compare(request: EvidenceComparisonRequest) -> dict[str, object]:
        return public_research.evidence_comparison(request)

    @app.post("/api/v1/codex/preview", tags=["codex"])
    def codex_preview(request: CodexPreviewRequest) -> dict[str, object]:
        return service.codex_preview(request)

    @app.post("/api/v1/codex/run", tags=["codex"])
    def run_codex(request: CodexRunRequest) -> dict[str, object]:
        return codex_runner.run(request.payload)

    @app.post("/api/v1/codex/cancel", tags=["codex"])
    def cancel_codex() -> dict[str, bool]:
        return {"cancelled": codex_runner.cancel()}

    @app.post("/api/v1/analyses", tags=["codex"])
    def save_analysis(request: SaveAnalysisRequest) -> dict[str, object]:
        return service.save_analysis(request)

    @app.get("/api/v1/analyses/{analysis_id}", tags=["codex"])
    def get_analysis(analysis_id: str) -> dict[str, object]:
        return service.get_analysis(analysis_id)

    @app.patch("/api/v1/analyses/{analysis_id}/status", tags=["codex"])
    def update_analysis_status(
        analysis_id: str, request: AnalysisStatusRequest
    ) -> dict[str, object]:
        return service.update_analysis_status(analysis_id, request.status)

    @app.post("/api/v1/backups/download", tags=["backup"])
    def download_backup(request: BackupPasswordRequest) -> FileResponse:
        file_name = f"PolicyLens-backup-{datetime.now(UTC).date()}-{secrets.token_hex(4)}.plbackup"
        destination = service.data_dir / "backups" / file_name
        result = service.create_backup(request.password, destination)
        return FileResponse(
            destination,
            media_type="application/octet-stream",
            filename=file_name,
            headers={
                "X-PolicyLens-Filename": file_name,
                "X-PolicyLens-Payload-SHA256": str(result["payload_sha256"]),
            },
        )

    @app.post("/api/v1/restores/upload-preview", tags=["backup"])
    async def upload_restore_preview(
        file: Annotated[UploadFile, File()],
        password: Annotated[str, Form(min_length=12, max_length=256)],
    ) -> dict[str, object]:
        if not (file.filename or "").lower().endswith(".plbackup"):
            raise BackupError("restore file must use the .plbackup extension")
        upload_dir = service.data_dir / "temp" / "browser-uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        source = upload_dir / f"restore-{secrets.token_hex(16)}.plbackup"
        total = 0
        try:
            with source.open("wb") as stream:
                while chunk := await file.read(1024 * 1024):
                    total += len(chunk)
                    if total > MAX_BACKUP_BYTES:
                        raise BackupError("backup exceeds the 120 MiB browser upload limit")
                    stream.write(chunk)
            return service.preview_restore(password, source)
        finally:
            source.unlink(missing_ok=True)

    @app.post("/api/v1/restores/commit", tags=["backup"])
    def commit_restore(request: RestoreCommitRequest) -> dict[str, object]:
        return service.commit_restore(request.restore_token)

    @app.get("/api/v1/settings", tags=["system"])
    def settings() -> dict[str, object]:
        return service.settings()

    @app.get("/api/v1/contracts/enums", tags=["system"], response_model=SemanticEnumsResponse)
    def semantic_enums() -> SemanticEnumsResponse:
        return SemanticEnumsResponse(
            verification_statuses=list(VerificationStatus),
            value_origins=list(ValueOrigin),
            source_authorities=list(SourceAuthority),
        )

    if static_dir is not None:
        resolved_static = static_dir.resolve()
        assets = resolved_static / "assets"
        if assets.exists():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        def spa(full_path: str):
            if full_path.startswith("api/"):
                return JSONResponse(status_code=404, content={"code": "NOT_FOUND"})
            index = resolved_static / "index.html"
            if not index.exists():
                return JSONResponse(
                    status_code=503,
                    content={"code": "WEB_BUILD_MISSING", "message": "本地网页尚未构建。"},
                )
            return FileResponse(index)

    return app
