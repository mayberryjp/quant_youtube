from __future__ import annotations

from collections import Counter

from app.models.domain import Distillation, Episode


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


class FakePipeline:
    def __init__(self):
        self.episodes = self

    def get_by_identifier(self, _video_id):
        return _episode(1)

    def reprocess(self, _e):
        return Counter({"reprocessed": 1})

    def restart(self, _e):
        return Counter({"reprocessed": 1})

    def run(self, run_date=None):
        return Counter({"distilled": 1})

    def retry_failed(self, **_kwargs):
        return Counter({"retried": 1})

    def reprocess_candidates(self, **_kwargs):
        return [_episode(1)]


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
        monkeypatch.setattr("app.routes.episodes.build_pipeline", lambda *a, **k: FakePipeline())
        resp = app_client.post_json("/episodes/abcdefghijk/reprocess", {})
        assert resp.status_int == 202
        assert resp.json["status"] == "accepted"
