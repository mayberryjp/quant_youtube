#!/usr/bin/env bash
set -euo pipefail

until alembic upgrade head; do
  echo "alembic retry in 2s"
  sleep 2
done

exec supervisord -c /app/supervisord.conf
