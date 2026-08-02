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
