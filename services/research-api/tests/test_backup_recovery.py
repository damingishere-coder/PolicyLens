from __future__ import annotations

import base64
import hashlib
import json
import os
import zipfile
from pathlib import Path

import pytest
from conftest import accept_all
from cryptography.exceptions import InvalidTag

from policylens_api.backup import RestoreValidationError
from policylens_api.crypto import AesTestProtector, DpapiProtector, KeyManager
from policylens_api.domain import PolicyCreateRequest
from policylens_api.service import PolicyLensService

PASSWORD = "SYNTHETIC-passphrase-2026"


def seed_service(service: PolicyLensService, alpha_manual, beta_manual) -> tuple[str, str]:
    alpha = accept_all(service, service.import_manual(alpha_manual))["product_version_id"]
    beta = accept_all(service, service.import_manual(beta_manual))["product_version_id"]
    service.create_policy(
        PolicyCreateRequest(
            member_nickname="SYNTHETIC Member A",
            product_version_id=alpha,
            category="CORE",
            due_amount="1280.00",
            paid_amount="1280.00",
            currency="CNY",
            frequency="ANNUAL",
            due_date="2026-09-03",
            paid_date="2026-09-03",
        )
    )
    return alpha, beta


def rewrite_manifest(source: Path, destination: Path, mutate) -> None:
    with zipfile.ZipFile(source, "r") as archive:
        manifest = json.loads(archive.read("manifest.json"))
        payload = archive.read("payload.enc")
    mutate(manifest, payload)
    with zipfile.ZipFile(destination, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("payload.enc", payload)


def test_portable_backup_uses_required_kdf_and_fresh_nonces(
    service: PolicyLensService, tmp_path: Path, alpha_manual, beta_manual
) -> None:
    seed_service(service, alpha_manual, beta_manual)
    first = tmp_path / "first.plbackup"
    second = tmp_path / "second.plbackup"
    service.create_backup(PASSWORD, first)
    service.create_backup(PASSWORD, second)
    manifests = []
    for backup in (first, second):
        with zipfile.ZipFile(backup, "r") as archive:
            manifest = json.loads(archive.read("manifest.json"))
            payload = archive.read("payload.enc")
        assert manifest["kdf"]["name"] == "Argon2id"
        assert manifest["kdf"]["memory_kib"] == 65536
        assert manifest["kdf"]["time_cost"] == 3
        assert manifest["kdf"]["parallelism"] == 1
        assert len(base64.b64decode(manifest["kdf"]["salt"])) == 16
        assert len(base64.b64decode(manifest["dek_wrap"]["nonce"])) == 12
        assert len(base64.b64decode(manifest["payload"]["nonce"])) == 12
        assert manifest["payload"]["sha256"] == hashlib.sha256(payload).hexdigest()
        assert PASSWORD.encode() not in backup.read_bytes()
        manifests.append(manifest)
    assert manifests[0]["kdf"]["salt"] != manifests[1]["kdf"]["salt"]
    assert manifests[0]["dek_wrap"]["nonce"] != manifests[1]["dek_wrap"]["nonce"]


def test_wrong_password_tamper_and_version_fail_before_switch(
    service: PolicyLensService, tmp_path: Path, alpha_manual, beta_manual
) -> None:
    seed_service(service, alpha_manual, beta_manual)
    backup = tmp_path / "source.plbackup"
    service.create_backup(PASSWORD, backup)
    destination = PolicyLensService(tmp_path / "destination", AesTestProtector(b"B" * 32))
    try:
        before = destination.dashboard()
        with pytest.raises(RestoreValidationError):
            destination.preview_restore("wrong-password-value", backup)
        assert destination.dashboard() == before

        tampered = tmp_path / "tampered.plbackup"
        rewrite_manifest(
            backup,
            tampered,
            lambda manifest, payload: manifest["payload"].update({"sha256": "0" * 64}),
        )
        with pytest.raises(RestoreValidationError, match="integrity"):
            destination.preview_restore(PASSWORD, tampered)
        assert destination.dashboard() == before

        incompatible = tmp_path / "incompatible.plbackup"
        rewrite_manifest(
            backup,
            incompatible,
            lambda manifest, payload: manifest.update({"format_version": 999}),
        )
        with pytest.raises(RestoreValidationError, match="version"):
            destination.preview_restore(PASSWORD, incompatible)
        assert destination.dashboard() == before
    finally:
        destination.shutdown()


def test_correct_password_restores_into_different_machine_wrapper(
    service: PolicyLensService, tmp_path: Path, alpha_manual, beta_manual
) -> None:
    seed_service(service, alpha_manual, beta_manual)
    source_dashboard = service.dashboard()
    backup = tmp_path / "portable.plbackup"
    service.create_backup(PASSWORD, backup)

    machine_b = AesTestProtector(b"B" * 32)
    destination = PolicyLensService(tmp_path / "machine-b", machine_b)
    try:
        preview = destination.preview_restore(PASSWORD, backup)
        assert preview["current_data_unchanged"] is True
        assert destination.dashboard()["local_products"] == 0
        restored = destination.commit_restore(preview["restore_token"])
        assert restored["restored"] is True
        assert restored["dpapi_rewrapped"] is True
        assert restored["policy_count"] == 1
        assert destination.dashboard() == source_dashboard
        assert KeyManager(destination.data_dir, machine_b).load_or_create() == destination.dek
        with pytest.raises(InvalidTag):
            KeyManager(destination.data_dir, AesTestProtector(b"A" * 32)).load_or_create()
        assert (destination.data_dir / "backups" / restored["safety_snapshot"]).exists()
    finally:
        destination.shutdown()


@pytest.mark.skipif(os.name != "nt", reason="Windows DPAPI acceptance only runs on Windows")
def test_real_dpapi_rewraps_after_verified_restore_in_isolated_config_directories(
    tmp_path: Path, alpha_manual, beta_manual
) -> None:
    source = PolicyLensService(tmp_path / "windows-source", DpapiProtector())
    destination = PolicyLensService(tmp_path / "windows-restored", DpapiProtector())
    backup = tmp_path / "windows-portable.plbackup"
    try:
        seed_service(source, alpha_manual, beta_manual)
        expected = source.dashboard()
        source.create_backup(PASSWORD, backup)
        source_wrapper = (source.data_dir / "keys" / "dek.dpapi.json").read_bytes()

        before = destination.dashboard()
        with pytest.raises(RestoreValidationError):
            destination.preview_restore("wrong-password-value", backup)
        assert destination.dashboard() == before

        preview = destination.preview_restore(PASSWORD, backup)
        assert preview["current_data_unchanged"] is True
        restored = destination.commit_restore(preview["restore_token"])
        destination_wrapper = (destination.data_dir / "keys" / "dek.dpapi.json").read_bytes()

        assert restored["dpapi_rewrapped"] is True
        assert destination.dashboard() == expected
        assert destination_wrapper != source_wrapper
        assert (
            KeyManager(destination.data_dir, DpapiProtector()).load_or_create() == destination.dek
        )
    finally:
        source.shutdown()
        destination.shutdown()
