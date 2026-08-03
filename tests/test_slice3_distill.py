from __future__ import annotations

from app.services.distiller import distill


class FakeLLM:
    def __init__(self, outputs):
        self.outputs = outputs
        self.calls = 0

    def complete_json(self, _system, _user):
        out = self.outputs[self.calls]
        self.calls += 1
        return out, {"total_tokens": 10, "completion_chars": 5}


class TestDistiller:
    def test_single_pass(self):
        llm = FakeLLM(
            [{"summary": "buy $AAPL and monitor Berkshire (BRK.B)", "key_topics": ["apple"], "segments": []}]
        )
        out, usage = distill(llm, "short transcript")
        assert out.summary == "buy $AAPL and monitor Berkshire (BRK.B)"
        assert llm.calls == 1
        assert usage["total_tokens"] == 10

    def test_map_reduce(self):
        llm = FakeLLM(
            [
                {"summary": "part1", "key_topics": [], "segments": []},
                {"summary": "part2", "key_topics": [], "segments": []},
                {"summary": "combined", "key_topics": ["x"], "segments": []},
            ]
        )
        out, usage = distill(llm, "x" * 25, max_chunk_chars=13)
        assert "Chunk 1" in out.summary
        assert "Chunk 2" in out.summary
        assert llm.calls == 3
        assert usage["total_tokens"] == 30
