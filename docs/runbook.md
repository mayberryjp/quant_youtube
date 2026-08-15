# Runbook

## Local Setup

1. Set required environment variables such as `TRANSCRIPTAPI_KEY`, or provide them in `.env`.
2. Install dependencies:
   - py -m pip install -e ".[dev]"
3. Run tests:
   - py -m pytest -q

## Start API

- py -m app.main

## Start Workers Once

- py -m app.workers.discover --once
- py -m app.workers.transcript --once
- py -m app.workers.distill --once

## Retry Failed Episodes

- py -m app.workers.transcript --retry-failed --max-attempts 5

## Trigger Operational Jobs via API

- POST /runs/trigger
- POST /reprocess
- POST /retry-failed

## Container Mode

- docker compose up --build

Docker image defaults are declared in `Dockerfile`. Use shell variables or an optional `.env` file
to override them at runtime, especially for credentials.

Supervisord starts:
- alembic migration
- API process
- worker process
