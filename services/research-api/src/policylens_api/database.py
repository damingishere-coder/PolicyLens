from __future__ import annotations

from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.pool import NullPool

from .migrations import run_migrations


def _engine(path: Path) -> Engine:
    engine = create_engine(f"sqlite:///{path.as_posix()}", poolclass=NullPool)

    @event.listens_for(engine, "connect")
    def configure_sqlite(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=FULL")
        cursor.close()

    return engine


class DatabaseManager:
    def __init__(self, data_dir: Path) -> None:
        run_migrations(data_dir)
        databases = data_dir / "databases"
        self.research = _engine(databases / "research.db")
        self.family = _engine(databases / "family.db")

    def dispose(self) -> None:
        self.research.dispose()
        self.family.dispose()
