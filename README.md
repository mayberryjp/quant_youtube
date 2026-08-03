# quant_allinpodcast

All-In Podcast transcript ingestion and Ollama distillation service.

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
- GET /episodes
- GET /episodes/{id}
- DELETE /episodes/{id}
- POST /episodes/{video_id}/reprocess
- POST /episodes/{video_id}/restart
- POST /episodes/{video_id}/requeue
- POST /reprocess
- POST /retry-failed
- POST /runs/trigger
- GET /entities
- GET /jobs/{id}

## Workers

Three independent stages, each its own process:

```powershell
py -m app.workers.discover --once      # crawl channels -> insert episodes (logs an ingest_runs row)
py -m app.workers.transcript --once    # download transcripts for discovered episodes
py -m app.workers.distill --once       # distill fetched transcripts
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


## Watchlist API Integration

A dedicated entity pass runs after distillation: the LLM extracts every referenced company/ticker
from the distilled summary, resolves company names to tickers, and each mention is persisted to
`allin.referenced_entities` (queryable via `GET /entities`). Resolved tickers are submitted per
entity to a quant_signals-style watchlist API.

Entity extraction and persistence always run. Submission happens whenever a watchlist URL is
configured (mentions stay `pending` locally otherwise):

- `WATCHLIST_API_URL=https://<host>/signals`
- `WATCHLIST_API_KEY=<optional bearer token>`
- `WATCHLIST_SOURCE=quant_allinpodcast` (optional source label)
- `WATCHLIST_SIGNAL_TYPE=allin_mention` (optional signal type label)
- `ENTITY_PROMPT_VERSION=v1`


## Sentiment API Integration

To run a separate sentiment pass and deliver quant_sentiment-compatible payloads, configure:

- `SENTIMENT_ENABLED=true`
- `SENTIMENT_API_URL=https://<host>/sentiment`
- `SENTIMENT_API_KEY=<optional bearer token>`
- `SENTIMENT_SOURCE=quant_allinpodcast`
- `SENTIMENT_PROMPT_VERSION=v1`
- `SENTIMENT_FAIL_ON_ERROR=false` (set `true` to fail ingest when delivery fails)


When enabled, each successfully distilled episode runs a separate structured sentiment pass and sends one `POST /sentiment` per extracted observation.
