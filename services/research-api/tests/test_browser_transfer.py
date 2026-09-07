from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from policylens_api.app import create_app
from policylens_api.crypto import AesTestProtector

PASSWORD = "SYNTHETIC-browser-backup-2026"


def test_browser_backup_download_and_uploaded_restore_never_accept_paths(tmp_path: Path) -> None:
    data_dir = tmp_path / "browser-transfer-data"
    app = create_app(
        data_dir,
        protector=AesTestProtector(b"W" * 32),
        testing=True,
        browser_mode=True,
        bound_port=8768,
    )
    origin = "http://127.0.0.1:8768"
    with TestClient(app, base_url=origin) as client:
        session = client.get("/api/v1/session").json()
        headers = {"Origin": origin, "X-PolicyLens-CSRF": session["csrf_token"]}
        downloaded = client.post(
            "/api/v1/backups/download",
            headers=headers,
            json={"password": PASSWORD},
        )
        assert downloaded.status_code == 200
        assert downloaded.headers["x-policylens-filename"].endswith(".plbackup")
        assert len(downloaded.headers["x-policylens-payload-sha256"]) == 64
        assert PASSWORD.encode() not in downloaded.content

        wrong = client.post(
            "/api/v1/restores/upload-preview",
            headers=headers,
            data={"password": "SYNTHETIC-wrong-password"},
            files={"file": ("portable.plbackup", downloaded.content, "application/octet-stream")},
        )
        assert wrong.status_code == 422

        preview = client.post(
            "/api/v1/restores/upload-preview",
            headers=headers,
            data={"password": PASSWORD},
            files={"file": ("portable.plbackup", downloaded.content, "application/octet-stream")},
        )
        assert preview.status_code == 200
        assert preview.json()["current_data_unchanged"] is True
        committed = client.post(
            "/api/v1/restores/commit",
            headers=headers,
            json={"restore_token": preview.json()["restore_token"]},
        )
        assert committed.status_code == 200
        assert committed.json()["dpapi_rewrapped"] is True

        assert client.post("/api/v1/backups", headers=headers, json={}).status_code == 404
        assert client.post("/api/v1/restores/preview", headers=headers, json={}).status_code == 404
        assert not any((data_dir / "temp" / "browser-uploads").glob("*.plbackup"))
