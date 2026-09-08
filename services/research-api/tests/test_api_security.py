from __future__ import annotations

import time
from pathlib import Path

from fastapi.testclient import TestClient
from test_public_research import SyntheticFetcher, create_run, discovery_output

from policylens_api.app import create_app
from policylens_api.crypto import AesTestProtector
from policylens_api.domain import ResearchDiscoveryOutput
from policylens_api.research_codex_runner import ResearchCodexError


class EmptyResearchRunner:
    def run(self) -> dict[str, object]:
        return {
            "result": ResearchDiscoveryOutput(schema_version="1.0", products=[], leads=[]),
            "cli_version": "codex-cli synthetic",
            "argument_profile": "LIVE_SEARCH_EPHEMERAL_JSON_READ_ONLY_SCHEMA_V1",
        }

    def cancel(self) -> bool:
        return False


class NoopSourceFetcher:
    def close(self) -> None:
        return None


def test_research_api_preserves_safe_cli_failure_code(tmp_path: Path) -> None:
    class FailingRunner(EmptyResearchRunner):
        def run(self):
            raise ResearchCodexError("synthetic-private-diagnostic", code="CODEX_TIMEOUT")

    token = "synthetic-failure-token"
    app = create_app(
        tmp_path / "failure-data",
        token,
        protector=AesTestProtector(b"F" * 32),
        testing=True,
        research_runner=FailingRunner(),
        source_fetcher=NoopSourceFetcher(),
    )
    headers = {"X-PolicyLens-Token": token}
    with TestClient(app) as client:
        preview = client.post("/api/v1/research/preview", headers=headers).json()
        response = client.post(
            "/api/v1/research/runs",
            headers=headers,
            json={"confirmed": True, "preview_hash": preview["preview_hash"]},
        )
        assert response.status_code == 200
        run_id = response.json()["id"]
        for _ in range(100):
            response = client.get(f"/api/v1/research/runs/{run_id}", headers=headers)
            if response.json()["status"] == "FAILED":
                break
            time.sleep(0.01)
        run = response.json()
        assert run["status"] == "FAILED"
        assert run["error_code"] == "CODEX_TIMEOUT"
        assert all(item["error_codes"] == ["CODEX_TIMEOUT"] for item in run["insurer_outcomes"])
        assert "synthetic-private-diagnostic" not in response.text


def test_loopback_token_origin_and_extra_fields_are_rejected(tmp_path: Path) -> None:
    token = "synthetic-local-token-for-test-only"
    app = create_app(
        tmp_path / "api-data",
        token,
        protector=AesTestProtector(b"T" * 32),
        testing=True,
    )
    with TestClient(app) as client:
        missing = client.get("/health")
        assert missing.status_code == 401
        headers = {"X-PolicyLens-Token": token}
        assert client.get("/health", headers=headers).status_code == 200
        bad_origin = client.get(
            "/health", headers={**headers, "Origin": "https://untrusted.invalid"}
        )
        assert bad_origin.status_code == 403
        invalid = client.post(
            "/api/v1/imports/manual",
            headers=headers,
            json={
                "display_name": "SYNTHETIC",
                "version_label": "v1",
                "jurisdiction": "CN_MAINLAND",
                "line_of_business": "MEDICAL",
                "currency": "CNY",
                "annual_premium": "1.00",
                "renewal_mode": "UNKNOWN",
                "rate_adjustment_scope": "UNKNOWN",
                "source_authority": "UNATTRIBUTED",
                "evidence_note": "SYNTHETIC TEST",
                "unexpected_private_path": "not allowed",
            },
        )
        assert invalid.status_code == 422
        preview = client.post("/api/v1/research/preview", headers=headers)
        assert preview.status_code == 200
        assert preview.json()["requires_confirmation"] is True
        assert preview.json()["scope"]["insurer_ids"] == [
            "aia-hk",
            "prudential-hk",
            "manulife-hk",
        ]
        stale = client.post(
            "/api/v1/research/runs",
            headers=headers,
            json={"confirmed": True, "preview_hash": "0" * 64},
        )
        assert stale.status_code == 409
    log = (tmp_path / "api-data" / "logs" / "events.jsonl").read_text(encoding="utf-8")
    assert "synthetic-local-token" not in log
    assert "unexpected_private_path" not in log


def test_browser_mode_requires_signed_session_same_origin_and_csrf(tmp_path: Path) -> None:
    app = create_app(
        tmp_path / "browser-data",
        protector=AesTestProtector(b"B" * 32),
        testing=True,
        browser_mode=True,
        bound_port=8768,
        manager="RunDock",
    )
    origin = "http://127.0.0.1:8768"
    with TestClient(app, base_url=origin) as client:
        assert client.get("/api/v1/dashboard").status_code == 401
        session = client.get("/api/v1/session")
        assert session.status_code == 200
        assert session.json()["mode"] == "localhost-browser"
        assert "HttpOnly" in session.headers["set-cookie"]
        assert "SameSite=strict" in session.headers["set-cookie"]
        csrf = session.json()["csrf_token"]
        assert client.get("/api/v1/dashboard").status_code == 200

        body = {
            "display_name": "SYNTHETIC Browser Product",
            "version_label": "Synthetic Browser 2026",
            "jurisdiction": "CN_MAINLAND",
            "line_of_business": "MEDICAL",
            "currency": "CNY",
            "annual_premium": "1.00",
            "renewal_mode": "UNKNOWN",
            "rate_adjustment_scope": "UNKNOWN",
            "source_authority": "UNATTRIBUTED",
            "evidence_note": "SYNTHETIC TEST ONLY",
        }
        assert client.post("/api/v1/imports/manual", json=body).status_code == 403
        bad_origin = client.post(
            "/api/v1/imports/manual",
            json=body,
            headers={"Origin": "http://127.0.0.1:9999", "X-PolicyLens-CSRF": csrf},
        )
        assert bad_origin.status_code == 403
        accepted = client.post(
            "/api/v1/imports/manual",
            json=body,
            headers={"Origin": origin, "X-PolicyLens-CSRF": csrf},
        )
        assert accepted.status_code == 200
        response = client.get("/api/v1/runtime")
        assert response.json()["manager"] == "RunDock"
        assert "access-control-allow-origin" not in response.headers

    log = (tmp_path / "browser-data" / "logs" / "events.jsonl").read_text(encoding="utf-8")
    assert csrf not in log
    assert "SYNTHETIC Browser Product" not in log


def test_confirmed_research_run_is_persisted_and_executes_off_request_thread(
    tmp_path: Path,
) -> None:
    token = "synthetic-research-token"
    app = create_app(
        tmp_path / "research-api-data",
        token,
        protector=AesTestProtector(b"R" * 32),
        testing=True,
        research_runner=EmptyResearchRunner(),
        source_fetcher=NoopSourceFetcher(),
    )
    headers = {"X-PolicyLens-Token": token}
    with TestClient(app) as client:
        preview = client.post("/api/v1/research/preview", headers=headers).json()
        started = client.post(
            "/api/v1/research/runs",
            headers=headers,
            json={"confirmed": True, "preview_hash": preview["preview_hash"]},
        )
        assert started.status_code == 200
        run_id = started.json()["id"]
        current = started.json()
        for _ in range(100):
            current = client.get(f"/api/v1/research/runs/{run_id}", headers=headers).json()
            if current["status"] not in {"QUEUED", "DISCOVERING", "FETCHING"}:
                break
            time.sleep(0.01)
        assert current["status"] == "FAILED"
        assert current["error_code"] == "NO_VERIFIED_OFFICIAL_SOURCE"


def test_candidate_workbench_routes_are_authenticated_strict_and_official_only(
    tmp_path: Path,
) -> None:
    token = "synthetic-candidate-token"
    app = create_app(
        tmp_path / "candidate-api-data",
        token,
        protector=AesTestProtector(b"W" * 32),
        testing=True,
    )
    research = app.state.public_research
    first = discovery_output()
    second = discovery_output(
        insurer_id="prudential-hk",
        display_name="Official Synthetic Retirement Plan",
        source_url="https://www.prudential.com.hk/synthetic/retirement-plan",
    )
    output = ResearchDiscoveryOutput(
        schema_version="1.0",
        products=[*first.products, *second.products],
        leads=first.leads,
    )
    run_id = create_run(research)
    research.apply_discovery(
        run_id,
        output,
        SyntheticFetcher(first, second),
        cli_version="codex-cli synthetic",
        argument_profile="LIVE_SEARCH_EPHEMERAL_JSON_READ_ONLY_SCHEMA_V1",
    )
    headers = {"X-PolicyLens-Token": token}

    with TestClient(app) as client:
        assert client.get("/api/v1/research/readiness").status_code == 401
        readiness = client.get("/api/v1/research/readiness", headers=headers)
        assert readiness.status_code == 200
        assert readiness.json()["manual_confirmation_required"] is True
        assert {item["id"] for item in readiness.json()["checks"]} == {
            "research_database",
            "encrypted_vault",
            "codex_cli",
            "research_slot",
        }

        response = client.get(
            f"/api/v1/research/candidates?run_id={run_id}&status=WAITING_REVIEW",
            headers=headers,
        )
        assert response.status_code == 200
        candidates = response.json()
        assert len(candidates) == 2
        assert all(
            item["source"]["authority"].startswith("INSURER_OFFICIAL") for item in candidates
        )
        detail = client.get(
            f"/api/v1/research/candidates/{candidates[0]['import_id']}", headers=headers
        )
        assert detail.status_code == 200
        assert detail.json()["verification_label"] == "UNVERIFIED_CANDIDATE"

        compared = client.post(
            "/api/v1/research/candidate-comparisons",
            headers=headers,
            json={"import_ids": [item["import_id"] for item in candidates]},
        )
        assert compared.status_code == 200
        assert len(compared.json()["candidates"]) == 2
        duplicate = client.post(
            "/api/v1/research/candidate-comparisons",
            headers=headers,
            json={"import_ids": [candidates[0]["import_id"], candidates[0]["import_id"]]},
        )
        assert duplicate.status_code == 422
        extra = client.post(
            "/api/v1/research/candidate-comparisons",
            headers=headers,
            json={
                "import_ids": [item["import_id"] for item in candidates],
                "include_third_party": True,
            },
        )
        assert extra.status_code == 422
