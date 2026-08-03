"""Slice 5 tests: entity pass (company->ticker) + watchlist submission."""

from __future__ import annotations

import httpx

from app.models.domain import Episode, EntityType, WatchlistStatus
from app.models.llm_schemas import EntityMention, EntityOutput
from app.services.entity_pass import WatchlistApiClient, build_rows, extract_entities

VID = "abcdefghijk"


def _episode():
    return Episode(
        id=1,
        video_id=VID,
        channel_slug="allin",
        title="All-In E200",
        source_url=f"https://youtube.com/watch?v={VID}",
    )


class FakeLLM:
    def __init__(self, response):
        self.response = response

    def complete_json(self, _system, _user):
        return self.response, {"total_tokens": 5}


class FakeHttpClient:
    def __init__(self, status: int):
        self.status = status
        self.posts: list[tuple] = []

    def post(self, url, json=None):
        self.posts.append((url, json))
        return httpx.Response(self.status)


class TestEntityPass:
    def test_build_rows_resolved_and_unresolved(self):
        llm = FakeLLM({"entities": [
            {"raw_mention": "Apple", "entity_type": "company", "company_name": "Apple Inc.", "ticker": "aapl"},
            {"raw_mention": "some private startup", "entity_type": "company", "ticker": None},
        ]})
        out, _ = extract_entities(llm, "summary")
        rows = build_rows(_episode(), out, model="m1", prompt_version="v1")
        assert rows[0].ticker == "AAPL"
        assert rows[0].watchlist_status == WatchlistStatus.pending
        assert rows[1].watchlist_status == WatchlistStatus.unresolved
        assert rows[0].idempotency_key == f"allin:{VID}:AAPL:m1:v1"

    def test_build_rows_dedup(self):
        llm = FakeLLM({"entities": [
            {"raw_mention": "Apple", "ticker": "AAPL"},
            {"raw_mention": "AAPL", "ticker": "AAPL"},
        ]})
        out, _ = extract_entities(llm, "summary")
        rows = build_rows(_episode(), out, model="m1", prompt_version="v1")
        assert len(rows) == 1

    def test_unknown_entity_type_and_direction_coerced(self):
        # Small models sometimes emit types/directions outside the enum; these
        # must not fail validation for the whole batch.
        llm = FakeLLM({"entities": [
            {"raw_mention": "S&P 500", "entity_type": "index", "direction": "up"},
        ]})
        out, _ = extract_entities(llm, "summary")
        assert out.entities[0].entity_type == EntityType.company
        assert out.entities[0].direction is None

    def test_submit_resolved_ticker(self):
        client = WatchlistApiClient(
            url="http://signals.local/signals", retries=0, client=FakeHttpClient(201)
        )
        out = EntityOutput(entities=[EntityMention(raw_mention="Apple", ticker="AAPL")])
        rows = build_rows(_episode(), out, model="m1", prompt_version="v1")
        assert client.submit(rows[0], _episode()) == WatchlistStatus.submitted

    def test_submit_duplicate(self):
        client = WatchlistApiClient(
            url="http://signals.local/signals", retries=0, client=FakeHttpClient(200)
        )
        out = EntityOutput(entities=[EntityMention(raw_mention="Apple", ticker="AAPL")])
        rows = build_rows(_episode(), out, model="m1", prompt_version="v1")
        assert client.submit(rows[0], _episode()) == WatchlistStatus.duplicate

    def test_submit_unresolved_skips_http(self):
        fake = FakeHttpClient(500)
        client = WatchlistApiClient(url="http://signals.local/signals", retries=0, client=fake)
        out = EntityOutput(entities=[EntityMention(raw_mention="startup", ticker=None)])
        rows = build_rows(_episode(), out, model="m1", prompt_version="v1")
        assert client.submit(rows[0], _episode()) == WatchlistStatus.unresolved
        assert fake.posts == []
