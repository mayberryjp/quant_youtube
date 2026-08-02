# Integrations

## YouTube Discovery

- Source: https://www.youtube.com/@allin
- Discovery client extracts recent video IDs from channel videos page
- Canonical identity: video_id

## Transcript Retrieval

- Uses YouTube timedtext endpoint by language preference
- Normalizes transcript text for deterministic hashing
- Saves transcript language and source type with each episode

## LLM Distillation

- OpenAI-compatible chat completion endpoint (Ollama default)
- Requests JSON object output for summary, key_topics, segments
- Handles long transcripts with map/reduce chunking
- Includes fallback behavior when reduce output is too thin
