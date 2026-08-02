from __future__ import annotations

import subprocess
import time

from sqlalchemy import create_engine, text

from app.config import settings


LEGACY_TO_CURRENT = {
    "0002_vendor_run_symbol_counts": "0001_allin_schema",
}
MIGRATION_MARKER = "/tmp/allin-migrations.done"


def _repair_legacy_revision() -> None:
    engine = create_engine(settings.database_url, future=True, pool_pre_ping=True)
    with engine.begin() as conn:
        has_version_table = conn.execute(
            text("SELECT to_regclass('public.alembic_version')")
        ).scalar_one()
        if not has_version_table:
            print("No alembic_version table found yet; skipping legacy revision remap")
            return

        current = conn.execute(text("SELECT version_num FROM public.alembic_version")).scalar_one_or_none()
        if current in LEGACY_TO_CURRENT:
            mapped = LEGACY_TO_CURRENT[current]
            conn.execute(
                text("UPDATE public.alembic_version SET version_num = :mapped"),
                {"mapped": mapped},
            )
            print(f"Remapped legacy alembic revision {current} -> {mapped}")
        else:
            print(f"Alembic revision before upgrade: {current}")


def _run_upgrade() -> None:
    attempt = 0
    while True:
        attempt += 1
        try:
            _repair_legacy_revision()
            subprocess.run(["alembic", "upgrade", "head"], check=True)
            subprocess.run(["alembic", "current"], check=True)
            return
        except Exception as exc:  # pragma: no cover - container startup path
            print(f"alembic attempt {attempt} failed: {exc}")
            print("alembic retry in 2s")
            time.sleep(2)


def main() -> None:
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is not configured")
    _run_upgrade()
    with open(MIGRATION_MARKER, "w", encoding="utf-8") as f:
        f.write("ok\n")
    print(f"Migration marker created at {MIGRATION_MARKER}")


if __name__ == "__main__":
    main()
