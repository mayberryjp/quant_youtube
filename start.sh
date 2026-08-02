#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY'
from app.config import settings
from sqlalchemy.engine import make_url

if not settings.database_url:
  raise SystemExit("DATABASE_URL is not configured")

url = make_url(settings.database_url)
target = f"{url.host or 'localhost'}:{url.port or 5432}/{url.database or ''}"
print(f"Running migrations against {target}")
PY

python3 - <<'PY'
from sqlalchemy import create_engine, text
from app.config import settings

LEGACY_TO_CURRENT = {
  # Legacy revision from earlier branch history that no longer exists in this repo.
  "0002_vendor_run_symbol_counts": "0001_allin_schema",
}

engine = create_engine(settings.database_url, future=True, pool_pre_ping=True)
with engine.begin() as conn:
  has_version_table = conn.execute(
    text("SELECT to_regclass('public.alembic_version')")
  ).scalar_one()

  if not has_version_table:
    print("No alembic_version table found yet; skipping legacy revision remap")
  else:
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
PY

until alembic upgrade head; do
  echo "alembic retry in 2s"
  sleep 2
done

alembic current

python3 - <<'PY'
from sqlalchemy import create_engine, text
from app.config import settings

engine = create_engine(settings.database_url, future=True, pool_pre_ping=True)
with engine.connect() as conn:
  exists = conn.execute(text("SELECT to_regclass('allin.ingest_runs')")).scalar_one()

if not exists:
  raise SystemExit("Migration verification failed: allin.ingest_runs not found in target database")

print("Migration verification succeeded: allin.ingest_runs exists")
PY

exec supervisord -c /app/supervisord.conf
