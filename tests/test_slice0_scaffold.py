"""Slice 0 tests: scaffolding, config, health endpoint."""

from __future__ import annotations


class TestScaffold:
    def test_health_ok(self, app_client):
        resp = app_client.get("/allin/health")
        assert resp.status_int == 200
        assert resp.json == {"status": "ok"}

    def test_config_loads_defaults(self):
        from app.config import settings

        assert settings.api_port == 8022
        assert settings.transcriptapi_base_url == "https://transcriptapi.com/api/v2"
        assert settings.youtube_channel_handle == "allin"
        assert settings.distill_api_url == "http://quant-distill:8021"

    def test_transcript_language_parsing(self):
        from app.config import Settings

        cfg = Settings(transcript_languages="en, en-US ,")
        assert cfg.transcript_language_preference == ["en", "en-US"]

    def test_multi_channel_parsing(self):
        from app.config import Settings

        cfg = Settings(youtube_channels="allin, bnn=id:UC1234567890")
        assert cfg.youtube_channel_targets == [
            {"channel_id": "", "channel_handle": "allin", "channel_slug": "allin"},
            {"channel_id": "UC1234567890", "channel_handle": "", "channel_slug": "bnn"},
        ]
