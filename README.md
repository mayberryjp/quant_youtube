# youtube

YouTube transcript ingestion worker for the shared `quant_distill` API.

## Status

- Vertical slices 0 through 9 implemented in-code
- End-to-end flow present: discover episodes, fetch transcript, distill, persist, retry/reprocess
- Operational API routes wired: health, ready, stats, episode reads, background jobs, run triggers
- Worker loop and background job registry implemented
- Test suite passing

## Quick Start

1. Install dependencies:

```powershell
py -m pip install -e ".[dev]"
```

2. Run tests:

```powershell
py -m pytest -q
```

3. Run the API locally:

```powershell
py -m app.main
```

4. Health check:

```powershell
curl http://localhost:8022/allin/health
```

## API

- GET /allin/health
- GET /allin/ready
- GET /allin/stats
- GET /allin/summary
- GET /episodes
- GET /episodes/{id}
- DELETE /episodes/{id}
- POST /episodes/{video_id}/reprocess
- POST /episodes/{video_id}/restart
- POST /episodes/{video_id}/requeue
- POST /reprocess
- POST /retry-failed
- POST /runs/trigger
- GET /jobs/{id}

## Workers

Three independent stages, each its own process:

```powershell
py -m app.workers.discover --once      # crawl channels -> insert episodes (logs an ingest_runs row)
py -m app.workers.transcript --once    # download transcripts for discovered episodes
py -m app.workers.distill --once       # send fetched transcripts to quant_distill
```

Retry failed transcript fetches:

```powershell
py -m app.workers.transcript --retry-failed --max-attempts 5
```

## YouTube API

Discovery and transcript fetching both run through [transcriptapi.com](https://transcriptapi.com).
Discovery uses the free `GET /youtube/channel/latest` (RSS) endpoint; transcripts use
`GET /youtube/transcript` (1 credit, charged only on success).

Required configuration:

- `TRANSCRIPTAPI_KEY` (get one at https://transcriptapi.com/dashboard/api-keys)
- `YOUTUBE_CHANNEL_HANDLE` (default `allin`) or `YOUTUBE_CHANNEL_ID`

Optional:

- `TRANSCRIPTAPI_BASE_URL` (default `https://transcriptapi.com/api/v2`)
- `TRANSCRIPT_LANGUAGES` priority list of transcriptapi codes (default `en,asr`; region is ignored, `asr` = auto-generated)

Optional multi-channel discovery:

- `YOUTUBE_CHANNELS` as a comma-separated list.
- Token formats:
	- `allin` or `@allin` (handle)
	- `id:UCxxxxxxxx` (explicit channel ID)
	- `slug=allin` (custom slug + handle)
	- `slug=id:UCxxxxxxxx` (custom slug + channel ID)


## Distillation API Integration

Each fetched transcript is submitted once to `POST {DISTILL_API_URL}/v1/process`, which returns
`202` + a `job_id`. The worker stores that id on the episode and polls `GET /v1/jobs/{job_id}` until
the job succeeds or fails; if polling runs out of time the episode stays retryable and the stored
job id is reused on the next pass rather than resubmitting. The shared service
owns distillation, sentiment, entity extraction, and downstream delivery. This worker does not call
those downstream APIs directly.

Configuration:

- `DISTILL_API_URL` (default `http://quant-distill:8021`)
- `DISTILL_SUBMIT_TIMEOUT` (default `30` seconds, for `POST /v1/process`)
- `DISTILL_POLL_INTERVAL` (default `20` seconds between `GET /v1/jobs/{id}` polls)
- `DISTILL_JOB_TIMEOUT` (default `3600` seconds before polling gives up for this pass)
- `DISTILL_MAX_ATTEMPTS` (default `10` failed distill attempts before the episode is left failed)
- `DISTILL_SOURCE` (default `youtube`)
- `DISTILL_MAX_CHUNK_CHARS` (default `12000`)

The source transcript remains in `allin.episodes.raw_text`. The complete process request and
authoritative response are stored in `allin.distillations.request_payload` and
`allin.distillations.response_payload`; normalized summary fields remain available for list APIs.
