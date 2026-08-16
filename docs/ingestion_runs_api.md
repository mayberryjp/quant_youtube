# Ingestion Runs API Spec

## Purpose

This spec defines how a front-end should read ingestion run history from the ingestion API for `youtube`.

The front end should use this data to display:

- the latest ingestion status
- historical run rows
- counts for episodes discovered, transcripts fetched, distilled, reprocessed, and failures
- the last heartbeat / freshness of the worker
- job state for a manually triggered run

## Current API Surface

The API already exposes:

- `GET /allin/stats` for the latest summary counters
- `POST /runs/trigger` to queue a new ingestion run
- `GET /jobs/{id}` to poll the background job started by `POST /runs/trigger`

## Required API Contract for Run History

The front end needs a run-history endpoint backed by `allin.ingest_runs`.
If it does not already exist, the backend should add it.

### 1. List ingestion runs

`GET /allin/runs`

Query parameters:

- `page` optional, default `1`
- `page_size` optional, default `25`
- `status` optional, filter by `running`, `success`, `partial`, or `failed`
- `from_date` optional, ISO date `YYYY-MM-DD`
- `to_date` optional, ISO date `YYYY-MM-DD`

Response:

```json
{
  "items": [
    {
      "run_date": "2026-08-02",
      "status": "success",
      "episodes_discovered": 3,
      "transcripts_fetched": 3,
      "distilled": 3,
      "reprocessed": 0,
      "failures": 0,
      "last_heartbeat": "2026-08-02T17:22:14.123456+00:00",
      "notes": {"totals": {"distilled": 3}},
      "created_at": "2026-08-02T17:00:00+00:00",
      "updated_at": "2026-08-02T17:22:14.123456+00:00"
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 25
}
```

Sorting:

- newest first by `run_date`

### 2. Read a single ingestion run

`GET /allin/runs/{run_date}`

Path params:

- `run_date` required, ISO date `YYYY-MM-DD`

Response:

```json
{
  "run_date": "2026-08-02",
  "status": "success",
  "episodes_discovered": 3,
  "transcripts_fetched": 3,
  "distilled": 3,
  "reprocessed": 0,
  "failures": 0,
  "last_heartbeat": "2026-08-02T17:22:14.123456+00:00",
  "notes": {"totals": {"distilled": 3}},
  "created_at": "2026-08-02T17:00:00+00:00",
  "updated_at": "2026-08-02T17:22:14.123456+00:00"
}
```

## Existing Summary Endpoint

`GET /allin/stats` is the lightweight summary endpoint for the dashboard header.
Use it for current totals and last run status when the UI does not need the full history table.

Response shape:

```json
{
  "episodes_discovered": 3,
  "transcripts_fetched": 3,
  "distilled": 3,
  "reprocessed": 0,
  "failures": 0,
  "episodes_total": 120,
  "last_run_date": "2026-08-02",
  "last_run_status": "success",
  "last_heartbeat": "2026-08-02T17:22:14.123456+00:00"
}
```

## Manual Trigger Flow

The front end should not create runs directly.
Instead:

1. POST ` /runs/trigger`
2. Read the returned `job_id`
3. Poll `GET /jobs/{job_id}` until `status` becomes `done` or `failed`
4. Refresh `GET /allin/stats` and `GET /allin/runs` after completion

Example trigger response:

```json
{
  "status": "accepted",
  "job_id": "...",
  "job_status": "queued"
}
```

Example job response:

```json
{
  "id": "...",
  "kind": "run-trigger",
  "status": "done",
  "result": {"distilled": 3},
  "error": null
}
```

## Front-End Usage Notes

- Show `last_run_status` and `last_heartbeat` in the top-level dashboard.
- Show the run history table sorted by `run_date` descending.
- Use badges for `success`, `partial`, `failed`, and `running`.
- Surface `failures` prominently.
- Display `notes` only if present.
- Treat `last_heartbeat` as the freshness indicator for the worker.

## Pagination Rules

- Default to `page=1` and `page_size=25`.
- Cap `page_size` on the backend.
- Fetch the next page only when the user requests more history.

## Error Handling

- `404` for an unknown `run_date`
- `422` for invalid query or path parameters
- `503` from readiness endpoints if the database is not reachable

## Open Backend Work

If the run-history endpoints do not exist yet, they should be added to the API before the front end depends on them.
The data already exists in `allin.ingest_runs` and `RunRepository`, so this is a read API addition rather than a schema change.
