# Data Model

Schema: allin

## Tables

1. allin.episodes
- One row per YouTube video discovered for the All-In channel
- Tracks pipeline status transitions: discovered, fetched, distilled, done, failed
- Stores raw transcript text and transcript metadata
- `distill_job_id` holds the in-flight `quant_distill` job while it is queued/running, so polling
  can resume after a restart; cleared once the job reaches a terminal state

2. allin.distillations
- Versioned distillation outputs by episode_id + model + prompt_version
- Maintains a current version marker via is_current
- Stores normalized summary fields plus token usage
- Stores the complete `quant_distill` request and response JSON and upstream request ID

3. allin.ingest_runs
- One row per run_date for worker execution tracking
- Records counters and run outcome status
- Carries heartbeat timestamp for readiness checks

## Key Constraints

- episodes.video_id unique
- distillations unique on (episode_id, model, prompt_version)
- distillations.episode_id foreign key to episodes.id

## Indexes

- episodes status + published_at
- episodes published_at
- optional non-unique content_hash index where present
