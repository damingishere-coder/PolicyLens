from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import secrets
import shutil
import sqlite3
import tempfile
import zipfile
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from argon2.low_level import Type, hash_secret_raw
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .crypto import VAULT_AAD, KeyManager
from .migrations import SCHEMA_VERSION, run_migrations

FORMAT_VERSION = 1
KDF_MEMORY_KIB = 65_536
KDF_TIME_COST = 3
KDF_PARALLELISM = 1
DEK_AAD = b"PolicyLens-portable-DEK-v1"
PAYLOAD_AAD = b"PolicyLens-portable-payload-v1"


class BackupError(RuntimeError):
    code = "BACKUP_FAILED"


class RestoreValidationError(BackupError):
    code = "RESTORE_VALIDATION_FAILED"


@dataclass
class RestorePlan:
    token: str
    staging_dir: Path
    dek: bytes
    source_count: int
    product_count: int
    policy_count: int
    created_at: str


def _derive_kek(password: str, salt: bytes) -> bytes:
    return hash_secret_raw(
        password.encode("utf-8"),
        salt,
        time_cost=KDF_TIME_COST,
        memory_cost=KDF_MEMORY_KIB,
        parallelism=KDF_PARALLELISM,
        hash_len=32,
        type=Type.ID,
    )


def _b64(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def _unb64(value: str) -> bytes:
    return base64.b64decode(value, validate=True)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _database_bytes(path: Path) -> bytes:
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("PRAGMA wal_checkpoint(FULL)")
        return connection.serialize()


def _safe_archive_name(name: str) -> bool:
    pure = PurePosixPath(name)
    return not pure.is_absolute() and ".." not in pure.parts and "\\" not in name


class BackupManager:
    def __init__(self, data_dir: Path, key_manager: KeyManager, dek: bytes) -> None:
        self.data_dir = data_dir
        self.key_manager = key_manager
        self.dek = dek
        self._plans: dict[str, RestorePlan] = {}

    def _build_payload(self) -> bytes:
        entries: dict[str, bytes] = {
            "databases/research.db": _database_bytes(self.data_dir / "databases" / "research.db"),
            "databases/family.db": _database_bytes(self.data_dir / "databases" / "family.db"),
        }
        vault = self.data_dir / "vault"
        if vault.exists():
            for path in sorted(vault.glob("*.vault")):
                entries[f"vault/{path.name}"] = path.read_bytes()

        payload_manifest = {
            "schema_version": SCHEMA_VERSION,
            "entries": {name: hashlib.sha256(value).hexdigest() for name, value in entries.items()},
        }
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(
                "payload_manifest.json",
                json.dumps(payload_manifest, sort_keys=True, separators=(",", ":")),
            )
            for name, value in entries.items():
                archive.writestr(name, value)
        return output.getvalue()

    def create_portable(self, password: str, destination: Path) -> dict[str, object]:
        if len(password) < 12:
            raise BackupError("recovery password must contain at least 12 characters")
        destination = destination.resolve()
        if destination.suffix.lower() != ".plbackup":
            raise BackupError("backup file must use the .plbackup extension")
        destination.parent.mkdir(parents=True, exist_ok=True)

        salt = os.urandom(16)
        wrap_nonce = os.urandom(12)
        payload_nonce = os.urandom(12)
        kek = _derive_kek(password, salt)
        wrapped_dek = AESGCM(kek).encrypt(wrap_nonce, self.dek, DEK_AAD)
        payload_ciphertext = AESGCM(self.dek).encrypt(
            payload_nonce, self._build_payload(), PAYLOAD_AAD
        )
        created_at = _utc_now()
        manifest = {
            "format": "PolicyLens Portable Backup",
            "format_version": FORMAT_VERSION,
            "schema_version": SCHEMA_VERSION,
            "created_at": created_at,
            "kdf": {
                "name": "Argon2id",
                "memory_kib": KDF_MEMORY_KIB,
                "time_cost": KDF_TIME_COST,
                "parallelism": KDF_PARALLELISM,
                "salt": _b64(salt),
            },
            "dek_wrap": {
                "cipher": "AES-256-GCM",
                "nonce": _b64(wrap_nonce),
                "ciphertext": _b64(wrapped_dek),
            },
            "payload": {
                "cipher": "AES-256-GCM",
                "nonce": _b64(payload_nonce),
                "sha256": hashlib.sha256(payload_ciphertext).hexdigest(),
                "bytes": len(payload_ciphertext),
            },
        }
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        try:
            with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_STORED) as archive:
                archive.writestr(
                    "manifest.json", json.dumps(manifest, sort_keys=True, separators=(",", ":"))
                )
                archive.writestr("payload.enc", payload_ciphertext)
            self._validate_outer(temporary)
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
        return {
            "file_name": destination.name,
            "created_at": created_at,
            "format_version": FORMAT_VERSION,
            "argon2id": f"m={KDF_MEMORY_KIB} KiB, t={KDF_TIME_COST}, p={KDF_PARALLELISM}",
            "payload_sha256": manifest["payload"]["sha256"],
        }

    @staticmethod
    def _validate_outer(source: Path) -> tuple[dict[str, object], bytes]:
        try:
            with zipfile.ZipFile(source, "r") as archive:
                if set(archive.namelist()) != {"manifest.json", "payload.enc"}:
                    raise RestoreValidationError("backup contains unexpected entries")
                manifest = json.loads(archive.read("manifest.json"))
                payload = archive.read("payload.enc")
        except (OSError, zipfile.BadZipFile, KeyError, json.JSONDecodeError) as exc:
            raise RestoreValidationError("backup container is invalid") from exc
        if manifest.get("format_version") != FORMAT_VERSION:
            raise RestoreValidationError("backup format version is not supported")
        if manifest.get("schema_version") not in {1, SCHEMA_VERSION}:
            raise RestoreValidationError("backup schema version is not supported")
        kdf = manifest.get("kdf", {})
        if kdf != {
            "name": "Argon2id",
            "memory_kib": KDF_MEMORY_KIB,
            "time_cost": KDF_TIME_COST,
            "parallelism": KDF_PARALLELISM,
            "salt": kdf.get("salt"),
        }:
            raise RestoreValidationError("backup KDF parameters are not supported")
        if hashlib.sha256(payload).hexdigest() != manifest.get("payload", {}).get("sha256"):
            raise RestoreValidationError("backup payload integrity check failed")
        return manifest, payload

    def preview_restore(self, password: str, source: Path) -> dict[str, object]:
        manifest, payload = self._validate_outer(source.resolve())
        try:
            salt = _unb64(manifest["kdf"]["salt"])
            wrap_nonce = _unb64(manifest["dek_wrap"]["nonce"])
            wrapped_dek = _unb64(manifest["dek_wrap"]["ciphertext"])
            payload_nonce = _unb64(manifest["payload"]["nonce"])
            if len(salt) != 16 or len(wrap_nonce) != 12 or len(payload_nonce) != 12:
                raise RestoreValidationError("backup cryptographic parameters are invalid")
            kek = _derive_kek(password, salt)
            restored_dek = AESGCM(kek).decrypt(wrap_nonce, wrapped_dek, DEK_AAD)
            payload_plaintext = AESGCM(restored_dek).decrypt(payload_nonce, payload, PAYLOAD_AAD)
        except (InvalidTag, ValueError, KeyError, TypeError) as exc:
            raise RestoreValidationError(
                "recovery password or backup integrity is invalid"
            ) from exc

        token = secrets.token_urlsafe(32)
        staging_dir = Path(tempfile.mkdtemp(prefix="restore-", dir=self.data_dir / "temp"))
        try:
            self._extract_and_validate(payload_plaintext, restored_dek, staging_dir)
            run_migrations(staging_dir)
            self._validate_current_revisions(staging_dir)
            source_count = self._count(
                staging_dir / "databases" / "research.db", "source_documents"
            )
            product_count = self._count(staging_dir / "databases" / "research.db", "products")
            policy_count = self._count(staging_dir / "databases" / "family.db", "policies")
            plan = RestorePlan(
                token=token,
                staging_dir=staging_dir,
                dek=restored_dek,
                source_count=source_count,
                product_count=product_count,
                policy_count=policy_count,
                created_at=str(manifest["created_at"]),
            )
            self._plans[token] = plan
            return {
                "restore_token": token,
                "source_count": source_count,
                "product_count": product_count,
                "policy_count": policy_count,
                "backup_created_at": plan.created_at,
                "current_data_unchanged": True,
            }
        except Exception:
            shutil.rmtree(staging_dir, ignore_errors=True)
            raise
        finally:
            payload_plaintext = b""

    @staticmethod
    def _extract_and_validate(payload: bytes, dek: bytes, destination: Path) -> None:
        try:
            with zipfile.ZipFile(io.BytesIO(payload), "r") as archive:
                names = archive.namelist()
                if any(not _safe_archive_name(name) for name in names):
                    raise RestoreValidationError("backup payload contains an unsafe path")
                payload_manifest = json.loads(archive.read("payload_manifest.json"))
                expected = payload_manifest.get("entries", {})
                if set(expected) != set(names) - {"payload_manifest.json"}:
                    raise RestoreValidationError("backup payload manifest does not match entries")
                for name, expected_hash in expected.items():
                    content = archive.read(name)
                    if hashlib.sha256(content).hexdigest() != expected_hash:
                        raise RestoreValidationError("backup payload entry integrity failed")
                    output = destination / PurePosixPath(name)
                    output.parent.mkdir(parents=True, exist_ok=True)
                    output.write_bytes(content)
        except (zipfile.BadZipFile, KeyError, json.JSONDecodeError) as exc:
            raise RestoreValidationError("decrypted backup payload is invalid") from exc

        supported_revisions = {
            "research.db": {"research_0001", "research_0002"},
            "family.db": {"family_0001"},
        }
        for name in ("research.db", "family.db"):
            db_path = destination / "databases" / name
            if not db_path.exists():
                raise RestoreValidationError("backup is missing a required database")
            with closing(sqlite3.connect(db_path)) as connection:
                integrity = connection.execute("PRAGMA integrity_check").fetchone()
                if not integrity or integrity[0] != "ok":
                    raise RestoreValidationError("restored database integrity check failed")
                version = connection.execute("SELECT version_num FROM alembic_version").fetchone()
                if not version or str(version[0]) not in supported_revisions[name]:
                    raise RestoreValidationError("restored database schema is incompatible")

        for vault_path in (destination / "vault").glob("*.vault"):
            value = vault_path.read_bytes()
            try:
                AESGCM(dek).decrypt(value[:12], value[12:], VAULT_AAD)
            except (InvalidTag, ValueError) as exc:
                raise RestoreValidationError(
                    "restored vault object integrity check failed"
                ) from exc

    @staticmethod
    def _count(database: Path, table: str) -> int:
        queries = {
            "source_documents": "SELECT COUNT(*) FROM source_documents",
            "products": "SELECT COUNT(*) FROM products",
            "policies": "SELECT COUNT(*) FROM policies",
        }
        if table not in queries:
            raise RestoreValidationError("unsupported restore summary table")
        with closing(sqlite3.connect(database)) as connection:
            return int(connection.execute(queries[table]).fetchone()[0])

    @staticmethod
    def _validate_current_revisions(data_dir: Path) -> None:
        expected = {"research.db": "research_0002", "family.db": "family_0001"}
        for name, revision in expected.items():
            database = data_dir / "databases" / name
            with closing(sqlite3.connect(database)) as connection:
                current = connection.execute("SELECT version_num FROM alembic_version").fetchone()
                integrity = connection.execute("PRAGMA integrity_check").fetchone()
            if not current or str(current[0]) != revision:
                raise RestoreValidationError(
                    "restored database migration did not reach current schema"
                )
            if not integrity or integrity[0] != "ok":
                raise RestoreValidationError(
                    "restored database integrity check failed after migration"
                )

    def _create_local_snapshot(self) -> Path:
        payload_nonce = os.urandom(12)
        encrypted = AESGCM(self.dek).encrypt(payload_nonce, self._build_payload(), PAYLOAD_AAD)
        created = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        destination = self.data_dir / "backups" / f"pre-restore-{created}.pllocal"
        key_wrapper = json.loads(self.key_manager.key_path.read_text(encoding="utf-8"))
        with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_STORED) as archive:
            archive.writestr(
                "manifest.json",
                json.dumps(
                    {
                        "format": "PolicyLens Local Pre-Restore Snapshot",
                        "version": 1,
                        "payload_nonce": _b64(payload_nonce),
                        "payload_sha256": hashlib.sha256(encrypted).hexdigest(),
                        "local_key_wrapper": key_wrapper,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            )
            archive.writestr("payload.enc", encrypted)
        return destination

    def commit_restore(self, token: str) -> dict[str, object]:
        plan = self._plans.pop(token, None)
        if plan is None:
            raise RestoreValidationError("restore preview token is missing or expired")
        snapshot = self._create_local_snapshot()
        rollback = self.data_dir / "temp" / f"rollback-{secrets.token_hex(8)}"
        rollback.mkdir(parents=True)
        current_names = ("databases", "vault", "keys")
        try:
            staged_keys = plan.staging_dir / "keys"
            staged_keys.mkdir(parents=True, exist_ok=True)
            wrapped = self.key_manager.protector.protect(plan.dek)
            (staged_keys / "dek.dpapi.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "protector": self.key_manager.protector.name,
                        "wrapped_dek": _b64(wrapped),
                    },
                    separators=(",", ":"),
                ),
                encoding="utf-8",
            )
            for name in current_names:
                current = self.data_dir / name
                if current.exists():
                    os.replace(current, rollback / name)
            for name in current_names:
                staged = plan.staging_dir / name
                if not staged.exists():
                    staged.mkdir(parents=True)
                os.replace(staged, self.data_dir / name)
        except Exception as exc:
            for name in current_names:
                failed = self.data_dir / name
                if failed.exists():
                    shutil.rmtree(failed) if failed.is_dir() else failed.unlink()
                previous = rollback / name
                if previous.exists():
                    os.replace(previous, failed)
            raise BackupError("restore switch failed and previous data was restored") from exc
        finally:
            shutil.rmtree(plan.staging_dir, ignore_errors=True)
        shutil.rmtree(rollback, ignore_errors=True)
        self.dek = plan.dek
        return {
            "restored": True,
            "source_count": plan.source_count,
            "product_count": plan.product_count,
            "policy_count": plan.policy_count,
            "dpapi_rewrapped": True,
            "safety_snapshot": snapshot.name,
        }

    def clear_plans(self) -> None:
        for plan in self._plans.values():
            shutil.rmtree(plan.staging_dir, ignore_errors=True)
        self._plans.clear()
