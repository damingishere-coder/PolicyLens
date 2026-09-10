from __future__ import annotations

import sqlite3
import sys
from argparse import Namespace
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from alembic.config import Config

from alembic import command

SCHEMA_VERSION = 3
EXPECTED_REVISIONS = {"research": "research_0002", "family": "family_0002"}


def _current_revision(path: Path) -> str | None:
    if not path.exists() or path.stat().st_size == 0:
        return None
    try:
        with closing(sqlite3.connect(path)) as connection:
            row = connection.execute("SELECT version_num FROM alembic_version").fetchone()
    except sqlite3.Error:
        return None
    return str(row[0]) if row else None


def _snapshot_before_upgrade(data_dir: Path, kind: str, path: Path) -> Path | None:
    current = _current_revision(path)
    if current is None or current == EXPECTED_REVISIONS[kind]:
        return None
    backups = data_dir / "backups"
    backups.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    destination = backups / f"pre-migration-{kind}-{current}-{timestamp}.db"
    with (
        closing(sqlite3.connect(path)) as source,
        closing(sqlite3.connect(destination)) as snapshot,
    ):
        source.backup(snapshot)
        integrity = snapshot.execute("PRAGMA integrity_check").fetchone()
    if not integrity or integrity[0] != "ok":
        destination.unlink(missing_ok=True)
        raise RuntimeError(f"{kind} database pre-migration snapshot failed integrity check")
    return destination


def run_migrations(data_dir: Path) -> None:
    if getattr(sys, "frozen", False):
        service_root = Path(sys._MEIPASS) / "service_resources"
    else:
        service_root = Path(__file__).resolve().parents[2]
    ini_path = service_root / "alembic.ini"
    script_location = service_root / "alembic"
    databases = data_dir / "databases"
    databases.mkdir(parents=True, exist_ok=True)

    for kind in ("research", "family"):
        config = Config(str(ini_path))
        config.set_main_option("script_location", str(script_location))
        config.set_main_option("version_locations", str(script_location / "versions" / kind))
        db_path = (databases / f"{kind}.db").resolve()
        _snapshot_before_upgrade(data_dir, kind, db_path)
        config.set_main_option("sqlalchemy.url", f"sqlite:///{db_path.as_posix()}")
        config.cmd_opts = Namespace(x=[f"db={kind}"])
        command.upgrade(config, "head")
