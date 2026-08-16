FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DATABASE_URL=postgresql+psycopg://quant:quant_dev_password@db:5432/quant \
    API_LISTEN_ADDRESS=0.0.0.0 \
    API_PORT=8022 \
    INGEST_WAKE_TIME=06:00 \
    INGEST_INTERVAL=86400 \
    INGEST_INTERVAL_HOURS=4 \
    LOOKBACK_DAYS=14 \
    MAX_ATTEMPTS=5 \
    FAILED_RETRY_INTERVAL_HOURS=6 \
    FAILED_RETRY_DELETE_ATTEMPTS=10 \
    CHANNEL_URL=https://www.youtube.com/@allin \
    CHANNEL_SLUG=allin \
    YOUTUBE_CHANNEL_ID="" \
    YOUTUBE_CHANNEL_HANDLE=allin \
    YOUTUBE_CHANNELS=allin \
    TRANSCRIPT_LANGUAGES=en,asr \
    MIN_VIDEO_DURATION_SECONDS=600 \
    TRANSCRIPTAPI_KEY="" \
    TRANSCRIPTAPI_BASE_URL=https://transcriptapi.com/api/v2 \
    TRANSCRIPTAPI_TIMEOUT=120 \
    LIVE_TRANSCRIPT_VIDEO_ID=sBI3_gPf13s \
    DISTILL_API_URL=http://quant-distill:8021 \
    DISTILL_API_TIMEOUT=3600 \
    DISTILL_SOURCE=youtube \
    DISTILL_MAX_CHUNK_CHARS=12000 \
    HTTP_RETRIES=3 \
    RETRY_BACKOFF=1.0

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends bash ca-certificates git vim procps \
    && rm -rf /var/lib/apt/lists/*

COPY . /app

RUN python3 -m pip install --upgrade pip \
    && python3 -m pip install -e ".[dev]" \
    && python3 -m pip install supervisor

CMD ["supervisord", "-c", "/app/supervisord.conf"]
