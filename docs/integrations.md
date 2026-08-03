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

## LLM Distillation

- OpenAI-compatible chat completion endpoint (Ollama default)
- Requests JSON object output for summary, key_topics, segments
- Handles long transcripts with map/reduce chunking
- Includes fallback behavior when reduce output is too thin
