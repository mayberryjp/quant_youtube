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
- POST /episodes/{video_id}/reprocess
- POST /episodes/{video_id}/restart
- POST /reprocess
- POST /retry-failed
- POST /runs/trigger
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

Discovery uses the official YouTube Data API v3.

Required configuration:

- `YOUTUBE_API_KEY`
- `YOUTUBE_CHANNEL_HANDLE` (default `allin`) or `YOUTUBE_CHANNEL_ID`

Optional multi-channel discovery:

- `YOUTUBE_CHANNELS` as a comma-separated list.
- Token formats:
	- `allin` or `@allin` (handle)
	- `id:UCxxxxxxxx` (explicit channel ID)
	- `slug=allin` (custom slug + handle)
	- `slug=id:UCxxxxxxxx` (custom slug + channel ID)


## Watchlist API Integration

Ticker extraction now runs as part of distillation and stores symbols with each current distillation row.

To publish extracted symbols to a watchlist API endpoint (quant_cnbc-style), configure:

- `WATCHLIST_ENABLED=true`
- `WATCHLIST_API_URL=https://<host>/...`
- `WATCHLIST_API_KEY=<optional bearer token>`
- `WATCHLIST_SOURCE=quant_allinpodcast` (optional source label)
- `WATCHLIST_FAIL_ON_ERROR=false` (set `true` to fail ingest when publish fails)


## Sentiment API Integration

To run a separate sentiment pass and deliver quant_sentiment-compatible payloads, configure:

- `SENTIMENT_ENABLED=true`
- `SENTIMENT_API_URL=https://<host>/sentiment`
- `SENTIMENT_API_KEY=<optional bearer token>`
- `SENTIMENT_SOURCE=quant_allinpodcast`
- `SENTIMENT_PROMPT_VERSION=v1`
- `SENTIMENT_FAIL_ON_ERROR=false` (set `true` to fail ingest when delivery fails)


When enabled, each successfully distilled episode runs a separate structured sentiment pass and sends one `POST /sentiment` per extracted observation.

When enabled, each successfully distilled episode sends one payload containing episode metadata,
symbols, summary, key topics, model, and prompt version.
