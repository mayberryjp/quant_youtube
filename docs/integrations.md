# Integrations

## YouTube Discovery

- Source: https://www.youtube.com/@allin
- Provider: transcriptapi.com `GET /youtube/channel/latest` (free RSS feed)
- Returns the latest uploads with exact publish timestamps; filtered by lookback window
- Canonical identity: video_id

## Transcript Retrieval

- Provider: transcriptapi.com `GET /youtube/transcript` (1 credit, charged only on HTTP 200)
- Language priority list of transcriptapi codes (`en,asr`); region is ignored, `asr` = auto-generated
- 429 / 402 / 5xx are treated as transient (episode stays retryable); 404 means unavailable
- Normalizes transcript text for deterministic hashing
- Saves transcript language and source type (`transcriptapi`) with each episode

## Shared Distillation

- Provider: `quant_distill` `POST /v1/process`
- Sends the complete transcript with stable YouTube identity and source metadata
- Requests distillation, sentiment, entity extraction, and optional downstream delivery in one call
- Retries transport errors and `5xx` responses with bounded exponential backoff
- Persists the exact request and authoritative response locally
