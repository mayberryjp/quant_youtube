"""Slice 0 tests: scaffolding, config, health endpoint."""

from __future__ import annotations


class TestScaffold:
    def test_health_ok(self, app_client):
        resp = app_client.get("/allin/health")
        assert resp.status_int == 200
        assert resp.json == {"status": "ok"}

    def test_config_loads_defaults(self):
        from app.config import settings

        assert settings.api_port == 8020
        assert settings.channel_url == "https://www.youtube.com/@allin"
        assert settings.llm_model == "llama3.1:8b"

    def test_transcript_language_parsing(self):
        from app.config import Settings

        cfg = Settings(transcript_languages="en, en-US ,")
        assert cfg.transcript_language_preference == ["en", "en-US"]
