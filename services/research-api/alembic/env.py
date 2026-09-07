from __future__ import annotations

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context
from policylens_api.models import family_metadata, research_metadata

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)

database_kind = context.get_x_argument(as_dictionary=True).get("db", "research")
target_metadata = research_metadata if database_kind == "research" else family_metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        rebuilds_legacy_tables = database_kind == "research"
        connection.exec_driver_sql(
            "PRAGMA foreign_keys=OFF" if rebuilds_legacy_tables else "PRAGMA foreign_keys=ON"
        )
        connection.commit()
        try:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                compare_type=True,
            )
            with context.begin_transaction():
                context.run_migrations()
            if rebuilds_legacy_tables:
                violations = connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
                if violations:
                    raise RuntimeError(
                        f"research migration produced {len(violations)} foreign-key violations"
                    )
        finally:
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
            connection.commit()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
