from __future__ import annotations

from collections import Counter
from datetime import date

from app.models.domain import Episode, EpisodeStatus
from app.services.discovery import DiscoveryService
from app.services.distillation import DistillService
from app.services import factory
from app.services.transcripts import TranscriptService
from app.services.youtube_client import TranscriptRateLimited, TranscriptUnavailable


class FakeEpisodeRepo:
    def __init__(self):
        self._seq = 0
        self._by_id: dict[int, Episode] = {}

    def add(self, video_id: str, status=EpisodeStatus.discovered, raw_text=None):
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

    def upsert_discovered(self, items):
        inserted = 0
        for it in items:
            if not any(e.video_id == it["video_id"] for e in self._by_id.values()):
                self.add(it["video_id"])
                inserted += 1
        return inserted

    def list_needing_transcript(self, *, limit=200, max_attempts=5):
        return [
            e for e in self._by_id.values()
            if e.status == EpisodeStatus.discovered
            or (e.status == EpisodeStatus.failed and e.raw_text is None and e.attempts < max_attempts)
        ]

    def list_needing_distill(self, *, limit=200, max_attempts=10):
        return [
            e for e in self._by_id.values()
            if (e.status == EpisodeStatus.fetched and e.distill_job_id is None)
            or (e.status == EpisodeStatus.failed and e.raw_text is not None and e.distill_attempts < max_attempts)
        ]

    def list_pending_distill(self, *, limit=200):
        return [
            e for e in self._by_id.values()
            if e.status == EpisodeStatus.fetched and e.distill_job_id is not None
        ][:limit]

    def get_by_id(self, eid):
        return self._by_id.get(eid)

    def get_by_identifier(self, video_id):
        return next((e for e in self._by_id.values() if e.video_id == video_id), None)

    def mark_fetched(self, eid, **kwargs):
        e = self._by_id[eid]
        e.raw_text = kwargs.get("raw_text")
        e.duration_seconds = kwargs.get("duration_seconds")
        e.status = EpisodeStatus.fetched

    def mark_skipped(self, eid, **kwargs):
        e = self._by_id[eid]
        e.duration_seconds = kwargs.get("duration_seconds")
        e.last_error = kwargs.get("reason")
        e.status = EpisodeStatus.skipped

    def set_status(self, eid, status, last_error=None, bump_attempts=False):
        e = self._by_id[eid]
        e.status = EpisodeStatus(status) if isinstance(status, str) else status
        e.last_error = last_error
        if bump_attempts:
            e.attempts += 1

    def set_distill_job(self, eid, job_id):
        self._by_id[eid].distill_job_id = job_id

    def bump_distill_attempts(self, eid):
        self._by_id[eid].distill_attempts += 1

    def touch_stage(self, _eid, _stage):
        pass

    def reset_for_reprocess(self, eid):
        e = self._by_id[eid]
        e.status = EpisodeStatus.fetched
        e.distill_attempts = 0
        e.distill_job_id = None
        return True

    def reset_full(self, eid):
        e = self._by_id[eid]
        e.status = EpisodeStatus.discovered
        e.raw_text = None
        return True

    def failed_candidates(self, **_kwargs):
        return [e for e in self._by_id.values() if e.status == EpisodeStatus.failed]

    def delete(self, eid):
        return self._by_id.pop(eid, None) is not None

    def reprocess_candidates(self, **_kwargs):
        return [e for e in self._by_id.values() if e.raw_text]


class FakeRunRepo:
    def __init__(self):
        self.counters = Counter()
        self.finished = None

    def start_run(self, _run_date):
        pass

    def add_counters(self, _run_date, **kwargs):
        self.counters.update(kwargs)

    def finish_run(self, _run_date, status, notes=None):
        self.finished = (status, notes)


class FakeDistRepo:
    def __init__(self):
        self.rows = {}

    def upsert(self, d):
        self.rows[d.episode_id] = d
        return d


class FakeYouTube:
    def __init__(self, *, items=None, transcript=("hello transcript", "en", "test"), rate_limited=False, length_seconds=None, unavailable=False):
        self._items = items or []
        self._transcript = transcript
        self._rate_limited = rate_limited
        self._length_seconds = length_seconds
        self._unavailable = unavailable

    def discover_recent_videos(self, **_kwargs):
        return self._items

    def fetch_transcript(self, _video_id, **_kwargs):
        if self._rate_limited:
            raise TranscriptRateLimited("429")
        return self._transcript

    def fetch_transcript_detail(self, _video_id, **_kwargs):
        if self._rate_limited:
            raise TranscriptRateLimited("429")
        if self._unavailable:
            raise TranscriptUnavailable("transcript unavailable")
        text, language, source = self._transcript
        return {
            "text": text,
            "language": language,
            "source": source,
            "length_seconds": self._length_seconds,
        }


class FakeDistillApi:
    def __init__(self, error=None):
        self.calls = []
        self.jobs = []
        self.error = error

    def submit(self, payload):
        self.calls.append(payload)
        job_id = f"job-{len(self.calls)}"
        self.jobs.append(job_id)
        return job_id

    def wait_for_result(self, _job_id):
        if self.error:
            raise self.error
        return {
            "status": "ok",
            "request_id": "request-1",
            "processing": {
                "model": "m1",
                "distill_prompt_version": "v1",
                "token_usage": {"total_tokens": 10},
                "warnings": [],
            },
            "distillation": {
                "summary": "sum mentions $MSFT",
                "key_topics": ["ai"],
                "segments": [],
            },
            "sentiment": {"observations": []},
            "entities": {"items": []},
        }


class TestDiscovery:
    def test_inserts_new_episodes_and_records_run(self):
        episodes = FakeEpisodeRepo()
        runs = FakeRunRepo()
        yt = FakeYouTube(items=[{"video_id": "aaaaaaaaaaa"}, {"video_id": "bbbbbbbbbbb"}])
        svc = DiscoveryService(episode_repo=episodes, run_repo=runs, youtube_client=yt)

        new_count = svc.run()

        assert new_count == 2
        assert runs.counters["episodes_discovered"] == 2
        assert runs.finished[0] == "success"

    def test_records_failure(self):
        class BoomYouTube(FakeYouTube):
            def discover_recent_videos(self, **_kwargs):
                raise RuntimeError("api down")

        runs = FakeRunRepo()
        svc = DiscoveryService(episode_repo=FakeEpisodeRepo(), run_repo=runs, youtube_client=BoomYouTube())
        try:
            svc.run()
        except RuntimeError:
            pass
        assert runs.finished[0] == "failed"
        assert runs.counters["failures"] == 1


class TestTranscripts:
    def _svc(self, **yt_kwargs):
        episodes = FakeEpisodeRepo()
        return episodes, TranscriptService(episode_repo=episodes, youtube_client=FakeYouTube(**yt_kwargs))

    def test_skips_episode_above_maximum_duration(self):
        episodes = FakeEpisodeRepo()
        svc = TranscriptService(
            episode_repo=episodes,
            youtube_client=FakeYouTube(length_seconds=601),
            max_duration_seconds=600,
        )
        episode = episodes.add("abcdefghijk", status=EpisodeStatus.discovered)

        assert svc.run()["skipped"] == 1
        assert episodes.get_by_id(episode.id).status == EpisodeStatus.skipped
        assert "maximum" in episodes.get_by_id(episode.id).last_error

    def test_fetches_discovered_episode(self):
        episodes, svc = self._svc()
        e = episodes.add("abcdefghijk", status=EpisodeStatus.discovered)
        totals = svc.run()
        assert totals["transcripts_fetched"] == 1
        assert episodes.get_by_id(e.id).status == EpisodeStatus.fetched
        assert episodes.get_by_id(e.id).raw_text == "hello transcript"

    def test_rate_limited_stays_discovered(self):
        episodes, svc = self._svc(rate_limited=True)
        e = episodes.add("abcdefghijk", status=EpisodeStatus.discovered)
        totals = svc.run()
        assert totals["failures"] == 1
        assert episodes.get_by_id(e.id).status == EpisodeStatus.discovered
        assert episodes.get_by_id(e.id).attempts == 0

    def test_missing_transcript_stays_retryable_then_skips(self):
        episodes, svc = self._svc(unavailable=True)
        e = episodes.add("abcdefghijk", status=EpisodeStatus.discovered)

        totals = svc.run()
        assert totals["unavailable"] == 1
        assert episodes.get_by_id(e.id).status == EpisodeStatus.failed
        assert episodes.get_by_id(e.id).attempts == 1

        for _ in range(10):
            svc.run()
        assert episodes.get_by_id(e.id).status == EpisodeStatus.skipped
        assert episodes.get_by_id(e.id).attempts == 4

    def test_skips_short_video(self):
        episodes = FakeEpisodeRepo()
        svc = TranscriptService(
            episode_repo=episodes,
            youtube_client=FakeYouTube(length_seconds=120),
            min_duration_seconds=600,
        )
        e = episodes.add("abcdefghijk", status=EpisodeStatus.discovered)
        totals = svc.run()
        assert totals["skipped"] == 1
        assert totals["transcripts_fetched"] == 0
        assert episodes.get_by_id(e.id).status == EpisodeStatus.skipped
        assert episodes.get_by_id(e.id).raw_text is None

    def test_keeps_long_video(self):
        episodes = FakeEpisodeRepo()
        svc = TranscriptService(
            episode_repo=episodes,
            youtube_client=FakeYouTube(length_seconds=1200),
            min_duration_seconds=600,
        )
        e = episodes.add("abcdefghijk", status=EpisodeStatus.discovered)
        totals = svc.run()
        assert totals["transcripts_fetched"] == 1
        assert episodes.get_by_id(e.id).status == EpisodeStatus.fetched

    def test_restart_refetches(self):
        episodes, svc = self._svc()
        e = episodes.add("abcdefghijk", status=EpisodeStatus.done, raw_text="old")
        totals = svc.restart(e)
        assert totals["reprocessed"] == 1
        assert episodes.get_by_id(e.id).status == EpisodeStatus.fetched


class TestDistill:
    def _svc(self, episodes=None, **kwargs):
        episodes = episodes or FakeEpisodeRepo()
        api = kwargs.pop("distill_api", FakeDistillApi())
        repo = FakeDistRepo()
        return episodes, DistillService(
            episode_repo=episodes,
            distillation_repo=repo,
            distill_api=api,
            **kwargs,
        ), api, repo

    def test_submits_fetched_episode_without_waiting(self):
        episodes, svc, api, repo = self._svc()
        e = episodes.add("abcdefghijk", status=EpisodeStatus.fetched, raw_text="raw")
        totals = svc.run()
        assert totals["submitted"] == 1
        assert episodes.get_by_id(e.id).status == EpisodeStatus.fetched
        assert episodes.get_by_id(e.id).distill_job_id == "job-1"
        assert api.calls[0]["source_item_id"] == "abcdefghijk"
        assert api.calls[0]["text"] == "raw"
        assert repo.rows == {}

    def test_submits_the_full_batch_before_waiting_for_results(self):
        class OrderedApi(FakeDistillApi):
            def __init__(self):
                super().__init__()
                self.events = []

            def submit(self, payload):
                self.events.append(("submit", payload["source_item_id"]))
                return super().submit(payload)

            def wait_for_result(self, job_id):
                self.events.append(("wait", job_id))
                return super().wait_for_result(job_id)

        episodes = FakeEpisodeRepo()
        api = OrderedApi()
        _, svc, _, _ = self._svc(episodes=episodes, distill_api=api)
        episodes.add("abcdefghijk", status=EpisodeStatus.fetched, raw_text="first")
        episodes.add("lmnopqrstuv", status=EpisodeStatus.fetched, raw_text="second")

        totals = svc.run()

        assert totals["submitted"] == 2
        assert [event[0] for event in api.events] == ["submit", "submit"]

    def test_status_pass_collects_previously_submitted_job(self):
        episodes, svc, api, repo = self._svc()
        e = episodes.add("abcdefghijk", status=EpisodeStatus.fetched, raw_text="raw")

        svc.run()
        totals = svc.collect()

        assert totals["distilled"] == 1
        assert episodes.get_by_id(e.id).status == EpisodeStatus.done
        assert episodes.get_by_id(e.id).distill_job_id is None
        assert repo.rows[e.id].request_payload == api.calls[0]
        assert repo.rows[e.id].response_payload["request_id"] == "request-1"

    def test_reprocess(self):
        episodes, svc, _, _ = self._svc()
        e = episodes.add("abcdefghijk", status=EpisodeStatus.done, raw_text="raw")
        totals = svc.reprocess(e)
        assert totals["reprocessed"] == 1
        assert totals["submitted"] == 1
        assert svc.collect()["distilled"] == 1

    def test_api_failure_marks_episode_failed(self):
        api = FakeDistillApi(error=RuntimeError("distill unavailable"))
        episodes, svc, _, _ = self._svc(distill_api=api)
        e = episodes.add("abcdefghijk", status=EpisodeStatus.fetched, raw_text="raw")
        svc.distill_one(e)
        totals = svc.collect()
        assert totals["failures"] == 1
        assert episodes.get_by_id(e.id).status == EpisodeStatus.failed
        assert episodes.get_by_id(e.id).distill_attempts == 1
        assert episodes.get_by_id(e.id).distill_job_id is None

    def test_retries_until_max_distill_attempts(self):
        api = FakeDistillApi(error=RuntimeError("distill unavailable"))
        episodes, svc, _, _ = self._svc(distill_api=api, max_attempts=10)
        episodes.add("abcdefghijk", status=EpisodeStatus.fetched, raw_text="raw")

        for _ in range(12):
            svc.run()
            svc.collect()

        # 10 submissions, then the episode drops out of the retry query.
        assert len(api.calls) == 10
        assert episodes.get_by_id(1).distill_attempts == 10


def test_run_all_once_records_complete_ingestion(monkeypatch):
    runs = FakeRunRepo()

    class Service:
        def __init__(self, result):
            self.result = result

        def run(self, **_kwargs):
            return self.result

    monkeypatch.setattr(factory.db, "get_engine", lambda: object())
    monkeypatch.setattr(factory, "build_discovery_service", lambda _engine: Service(2))
    monkeypatch.setattr(
        factory, "build_transcript_service", lambda _engine: Service(Counter(transcripts_fetched=2))
    )
    monkeypatch.setattr(
        factory, "build_distill_service", lambda _engine: Service(Counter(distilled=1, failures=1))
    )
    monkeypatch.setattr(factory.deps, "run_repo", lambda _engine: runs)

    result = factory.run_all_once(date(2026, 8, 14))

    assert result == {"episodes_discovered": 2, "transcripts_fetched": 2, "distilled": 1, "failures": 1}
    assert runs.counters == Counter(transcripts_fetched=2, distilled=1, failures=1)
    assert runs.finished == ("partial", result)


def test_independent_distill_pass_records_run_counter(monkeypatch):
    runs = FakeRunRepo()

    class Service:
        def run(self, **_kwargs):
            return Counter(distilled=3)

    monkeypatch.setattr(factory, "build_distill_service", lambda: Service())
    monkeypatch.setattr(factory.deps, "run_repo", lambda: runs)

    result = factory.run_distill_once(limit=10, run_date=date(2026, 8, 16))

    assert result == Counter(distilled=3)
    assert runs.counters == Counter(distilled=3, failures=0)
