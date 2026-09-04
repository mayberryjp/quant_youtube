from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool, text

from app.config import settings

# Every table owned by this project (including Alembic's bookkeeping) lives in this schema.
VERSION_TABLE_SCHEMA = "youtube"

# Schema this project previously used; migration 0008 relocates its tables into VERSION_TABLE_SCHEMA.
LEGACY_SCHEMA = "allin"

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", settings.database_url or "postgresql+psycopg://")

target_metadata = None


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        version_table_schema=VERSION_TABLE_SCHEMA,
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
        connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{VERSION_TABLE_SCHEMA}"'))
        # Relocate legacy migration bookkeeping before Alembic reads it, so an existing
        # deployment keeps its revision history when the schema is renamed (see migration 0008).
        connection.execute(
            text(
                f"""
                DO $$
                BEGIN
                    IF to_regclass('{LEGACY_SCHEMA}.alembic_version') IS NOT NULL
                       AND to_regclass('{VERSION_TABLE_SCHEMA}.alembic_version') IS NULL THEN
                        ALTER TABLE {LEGACY_SCHEMA}.alembic_version SET SCHEMA {VERSION_TABLE_SCHEMA};
                    END IF;
                END $$;
                """
            )
        )
        connection.commit()
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            version_table_schema=VERSION_TABLE_SCHEMA,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
