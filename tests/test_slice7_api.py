from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timezone

from app.models.domain import Distillation, Episode, IngestRun


def _episode(eid=1):
    return Episode(
        id=eid,
        video_id="abcdefghijk",
        title="All-In Episode",
        source_url="https://youtube.com/watch?v=abcdefghijk",
        status="done",
    )


class FakeEpisodeRepo:
    def list(self, **_kwargs):
        return ([_episode(1)], 1)

    def get_by_id(self, eid):
        return _episode(eid)


class FakeService:
    def __init__(self):
        self.episodes = self

    def get_by_identifier(self, _video_id):
        return _episode(1)

    def reprocess(self, _e):
        return Counter({"reprocessed": 1})

    def restart(self, _e):
        return Counter({"reprocessed": 1})

    def retry_failed(self, **_kwargs):
        return Counter({"retried": 1})

    def reprocess_candidates(self, **_kwargs):
        return [_episode(1)]


class RunRepo:
    def list(self, **_kwargs):
        return [self._run()], 1

    def get_by_run_date(self, run_date):
        if str(run_date) != "2026-08-02":
            return None
        return self._run()

    def _run(self):
        return IngestRun(
            run_date=date(2026, 8, 2),
            status="success",
            episodes_discovered=3,
            transcripts_fetched=3,
            distilled=3,
            reprocessed=0,
            failures=0,
            last_heartbeat=datetime(2026, 8, 2, 17, 0, tzinfo=timezone.utc),
            notes={"totals": {"distilled": 3}},
            created_at=datetime(2026, 8, 2, 17, 0, tzinfo=timezone.utc),
            updated_at=datetime(2026, 8, 2, 17, 5, tzinfo=timezone.utc),
        )


class DRepo:
    def get_current_map(self, ids):
        return {
            i: Distillation(
                id=1,
                episode_id=i,
                model="m1",
                prompt_version="v1",
                summary="Short summary",
                key_topics=[],
                segments=[],
            )
            for i in ids
        }

    def get_current(self, eid):
        return Distillation(
            id=1,
            episode_id=eid,
            model="m1",
            prompt_version="v1",
            summary="Short summary",
            key_topics=[],
            segments=[],
        )


class TestReadApi:
    def test_list_episodes(self, app_client, monkeypatch):
        monkeypatch.setattr("app.dependencies.episode_repo", lambda *a, **k: FakeEpisodeRepo())
        monkeypatch.setattr("app.dependencies.distillation_repo", lambda *a, **k: DRepo())
        resp = app_client.get("/episodes")
        assert resp.status_int == 200
        assert resp.json["total"] == 1
        assert resp.json["items"][0]["video_id"] == "abcdefghijk"

    def test_reprocess_endpoint(self, app_client, monkeypatch):
        monkeypatch.setattr("app.routes.episodes.build_distill_service", lambda *a, **k: FakeService())
        resp = app_client.post_json("/episodes/abcdefghijk/reprocess", {})
        assert resp.status_int == 202
        assert resp.json["status"] == "accepted"

    def test_list_runs(self, app_client, monkeypatch):
        monkeypatch.setattr("app.dependencies.run_repo", lambda *a, **k: RunRepo())
        resp = app_client.get("/allin/runs")
        assert resp.status_int == 200
        assert resp.json["total"] == 1
        assert resp.json["items"][0]["run_date"] == "2026-08-02"

    def test_get_run(self, app_client, monkeypatch):
        monkeypatch.setattr("app.dependencies.run_repo", lambda *a, **k: RunRepo())
        resp = app_client.get("/allin/runs/2026-08-02")
        assert resp.status_int == 200
        assert resp.json["status"] == "success"
