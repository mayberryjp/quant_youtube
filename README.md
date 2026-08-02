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
curl http://localhost:8020/allin/health
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

## Worker

Run once:

```powershell
py -m app.services.ingest_worker --once
```

Retry failed episodes:

```powershell
py -m app.services.ingest_worker --retry-failed --max-attempts 5
```

## YouTube API

Discovery uses the official YouTube Data API v3.

Required configuration:

- `ALLIN_YOUTUBE_API_KEY`
- `ALLIN_YOUTUBE_CHANNEL_HANDLE` (default `allin`) or `ALLIN_YOUTUBE_CHANNEL_ID`

Optional multi-channel discovery:

- `ALLIN_YOUTUBE_CHANNELS` as a comma-separated list.
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

Backward-compatible aliases are also accepted: `ALLIN_WATCHLIST_*`.

When enabled, each successfully distilled episode sends one payload containing episode metadata,
symbols, summary, key topics, model, and prompt version.
