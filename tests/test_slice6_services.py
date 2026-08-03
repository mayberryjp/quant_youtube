from __future__ import annotations

from collections import Counter

from app.models.domain import Episode, EpisodeStatus, WatchlistStatus
from app.services.discovery import DiscoveryService
from app.services.distillation import DistillService
from app.services.transcripts import TranscriptService
from app.services.youtube_client import TranscriptRateLimited


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

    def list_needing_distill(self, *, limit=200, max_attempts=5):
        return [
            e for e in self._by_id.values()
            if e.status == EpisodeStatus.fetched
            or (e.status == EpisodeStatus.failed and e.raw_text is not None and e.attempts < max_attempts)
        ]

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

    def touch_stage(self, _eid, _stage):
        pass

    def reset_for_reprocess(self, eid):
        self._by_id[eid].status = EpisodeStatus.fetched
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
    def __init__(self, *, items=None, transcript=("hello transcript", "en", "test"), rate_limited=False, length_seconds=None):
        self._items = items or []
        self._transcript = transcript
        self._rate_limited = rate_limited
        self._length_seconds = length_seconds

    def discover_recent_videos(self, **_kwargs):
        return self._items

    def fetch_transcript(self, _video_id, **_kwargs):
        if self._rate_limited:
            raise TranscriptRateLimited("429")
        return self._transcript

    def fetch_transcript_detail(self, _video_id, **_kwargs):
        if self._rate_limited:
            raise TranscriptRateLimited("429")
        text, language, source = self._transcript
        return {
            "text": text,
            "language": language,
            "source": source,
            "length_seconds": self._length_seconds,
        }


class FakeLLM:
    def complete_json(self, system, _user):
        s = system or ""
        if "market-sentiment classifier" in s:
            return {
                "observations": [
                    {
                        "subject_type": "ticker",
                        "subject": "MSFT",
                        "sentiment_label": "bullish",
                        "sentiment_score": 0.6,
                        "confidence": 0.7,
                    }
                ]
            }, {"total_tokens": 8}
        if "extract every company or ticker" in s:
            return {
                "entities": [
                    {
                        "raw_mention": "Microsoft",
                        "entity_type": "company",
                        "company_name": "Microsoft",
                        "ticker": "MSFT",
                        "direction": "long",
                        "confidence": 0.8,
                        "context": "cloud growth",
                    }
                ]
            }, {"total_tokens": 9}
        return {"summary": "sum mentions $MSFT", "key_topics": ["ai"], "segments": []}, {"total_tokens": 10}


class FakeEntityRepo:
    def __init__(self):
        self.rows = []
        self.watchlist = []
        self._seq = 0

    def insert(self, e):
        self._seq += 1
        self.rows.append(e)
        return self._seq

    def set_watchlist(self, row_id, status, *, submitted_at=None):
        self.watchlist.append((row_id, status, submitted_at))


class FakeWatchlistApi:
    def __init__(self, status=WatchlistStatus.submitted):
        self.calls = []
        self._status = status

    def submit(self, e, episode):
        self.calls.append((e, episode))
        return self._status


class FakeSentimentApi:
    def __init__(self):
        self.calls = []

    def deliver(self, obs, episode, *, model, prompt_version):
        self.calls.append((obs, episode, model, prompt_version))
        return True, "sentiment:1"


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
        return episodes, DistillService(
            episode_repo=episodes,
            distillation_repo=FakeDistRepo(),
            llm_client=FakeLLM(),
            model="m1",
            distill_prompt_version="v1",
            **kwargs,
        )

    def test_fetched_to_done(self):
        episodes, svc = self._svc()
        e = episodes.add("abcdefghijk", status=EpisodeStatus.fetched, raw_text="raw")
        totals = svc.run()
        assert totals["distilled"] == 1
        assert episodes.get_by_id(e.id).status == EpisodeStatus.done

    def test_reprocess(self):
        episodes, svc = self._svc()
        e = episodes.add("abcdefghijk", status=EpisodeStatus.done, raw_text="raw")
        totals = svc.reprocess(e)
        assert totals["reprocessed"] == 1
        assert totals["distilled"] == 1

    def test_entities_submitted(self):
        entity_repo = FakeEntityRepo()
        watchlist = FakeWatchlistApi()
        episodes, svc = self._svc(
            entity_repo=entity_repo,
            watchlist_api=watchlist,
        )
        e = episodes.add("abcdefghijk", status=EpisodeStatus.fetched, raw_text="talking about $MSFT")
        totals = svc.distill_one(e)
        assert totals["entities_submitted"] == 1
        assert len(watchlist.calls) == 1
        assert watchlist.calls[0][0].ticker == "MSFT"
        assert entity_repo.watchlist[0][1] == WatchlistStatus.submitted

    def test_entities_persist_without_watchlist(self):
        entity_repo = FakeEntityRepo()
        episodes, svc = self._svc(entity_repo=entity_repo)
        e = episodes.add("abcdefghijk", status=EpisodeStatus.fetched, raw_text="talking about $MSFT")
        totals = svc.distill_one(e)
        assert totals["distilled"] == 1
        assert totals.get("entities_submitted", 0) == 0
        assert len(entity_repo.rows) == 1
        assert entity_repo.rows[0].ticker == "MSFT"
        assert entity_repo.rows[0].watchlist_status == WatchlistStatus.pending

    def test_sentiment_publish(self):
        sentiment = FakeSentimentApi()
        episodes, svc = self._svc(
            sentiment_client=sentiment,
            sentiment_enabled=True,
            sentiment_prompt_version="v1",
        )
        e = episodes.add("abcdefghijk", status=EpisodeStatus.fetched, raw_text="talking about $MSFT")
        totals = svc.distill_one(e)
        assert totals["sentiments_sent"] == 1
        assert len(sentiment.calls) == 1
