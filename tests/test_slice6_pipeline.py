from __future__ import annotations

from collections import Counter
from datetime import date

from app.models.domain import Episode, EpisodeStatus
from app.services.pipeline import Pipeline


class FakeEpisodeRepo:
    def __init__(self):
        self._seq = 0
        self._by_id = {}

    def add(self, video_id: str, status=EpisodeStatus.fetched, raw_text="text"):
        self._seq += 1
        e = Episode(
            id=self._seq,
            video_id=video_id,
            source_url=f"https://youtube.com/watch?v={video_id}",
            status=status,
            raw_text=raw_text,
        )
        self._by_id[e.id] = e
        return e

    def upsert_discovered(self, _items):
        return 0

    def list_actionable(self, **_kwargs):
        return list(self._by_id.values())

    def get_by_id(self, eid):
        return self._by_id.get(eid)

    def get_by_identifier(self, video_id):
        for e in self._by_id.values():
            if e.video_id == video_id:
                return e
        return None

    def mark_fetched(self, eid, **kwargs):
        e = self._by_id[eid]
        e.raw_text = kwargs.get("raw_text")
        e.status = EpisodeStatus.fetched

    def set_status(self, eid, status, last_error=None, bump_attempts=False):
        e = self._by_id[eid]
        e.status = EpisodeStatus(status) if isinstance(status, str) else status
        e.last_error = last_error
        if bump_attempts:
            e.attempts += 1

    def touch_stage(self, _eid, _stage):
        pass

    def reset_for_reprocess(self, eid):
        self._by_id[eid].status = EpisodeStatus.fetched
        return True

    def reset_full(self, eid):
        self._by_id[eid].status = EpisodeStatus.discovered
        self._by_id[eid].raw_text = None
        return True

    def failed_candidates(self, **_kwargs):
        return [e for e in self._by_id.values() if e.status == EpisodeStatus.failed]

    def delete(self, eid):
        return self._by_id.pop(eid, None) is not None

    def reprocess_candidates(self, **_kwargs):
        return [e for e in self._by_id.values() if e.raw_text]


class FakeDistRepo:
    def __init__(self):
        self.rows = {}

    def upsert(self, d):
        self.rows[d.episode_id] = d
        return d


class FakeRunRepo:
    def __init__(self):
        self.counters = Counter()

    def start_run(self, _run_date):
        pass

    def add_counters(self, _run_date, **kwargs):
        self.counters.update(kwargs)

    def finish_run(self, _run_date, _status, notes=None):
        self.notes = notes


class FakeYouTube:
    def discover_recent_videos(self, **_kwargs):
        return []

    def fetch_transcript(self, _video_id, **_kwargs):
        return "hello transcript", "en", "test"


class FakeLLM:
    def complete_json(self, _system, _user):
        return {"summary": "sum", "key_topics": ["ai"], "segments": []}, {"total_tokens": 10}


def _pipeline():
    return Pipeline(
        episode_repo=FakeEpisodeRepo(),
        distillation_repo=FakeDistRepo(),
        run_repo=FakeRunRepo(),
        youtube_client=FakeYouTube(),
        llm_client=FakeLLM(),
        model="m1",
        distill_prompt_version="v1",
    )


class TestPipeline:
    def test_fetched_to_done(self):
        p = _pipeline()
        e = p.episodes.add("abcdefghijk", status=EpisodeStatus.fetched, raw_text="raw")
        c = p.process_one(e)
        assert c["distilled"] == 1
        assert p.episodes.get_by_id(e.id).status == EpisodeStatus.done

    def test_reprocess(self):
        p = _pipeline()
        e = p.episodes.add("abcdefghijk", status=EpisodeStatus.done, raw_text="raw")
        c = p.reprocess(e, run_date=date(2026, 8, 2))
        assert c["reprocessed"] == 1
