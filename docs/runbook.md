# Runbook

## Local Setup

1. Copy .env.example to .env and adjust values.
2. Install dependencies:
   - py -m pip install -e ".[dev]"
3. Run tests:
   - py -m pytest -q

## Start API

- py -m app.main

## Start Worker Once

- py -m app.services.ingest_worker --once

## Retry Failed Episodes

- py -m app.services.ingest_worker --retry-failed --max-attempts 5

## Trigger Operational Jobs via API

- POST /runs/trigger
- POST /reprocess
- POST /retry-failed

## Container Mode

- docker compose up --build

Supervisord starts:
- alembic migration
- API process
- worker process
