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
