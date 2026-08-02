from __future__ import annotations

import logging
import re
from typing import Any

from app.models.llm_schemas import DistillOutput

log = logging.getLogger("quant_allinpodcast.distiller")

DISTILL_SYSTEM = (
    "Summarize this podcast transcript into a detailed markdown summary and return JSON "
    "with keys summary, key_topics, symbols, and segments only. "
    "symbols must be an array of normalized stock tickers like AAPL or BRK.B."
)

REDUCE_SYSTEM = (
    "Merge the chunk summaries into one detailed summary and return JSON with "
    "summary, key_topics, symbols, and segments only. "
    "symbols must be an array of normalized stock tickers like AAPL or BRK.B."
)

_HEADING = re.compile(r"^\s*(?:\d+\.\s+)?\*\*(.+?)\*\*\s*:?\s*$", re.MULTILINE)
_DOLLAR_TICKER = re.compile(r"\$([A-Z]{1,6}(?:\.[A-Z])?)\b")
_PAREN_TICKER = re.compile(r"\(([A-Z]{1,6}(?:\.[A-Z])?)\)")
_STOP_TICKERS = {
    "A",
    "AN",
    "AND",
    "AS",
    "AT",
    "BY",
    "FOR",
    "FROM",
    "IN",
    "IS",
    "IT",
    "OF",
    "ON",
    "OR",
    "THE",
    "TO",
    "US",
    "USA",
    "WE",
    "YOU",
}


def _user_prompt(text: str) -> str:
    return f'Transcript:\n"""\n{text}\n"""\n\nReturn the JSON object.'


def _chunks(text: str, size: int) -> list[str]:
    return [text[i : i + size] for i in range(0, len(text), size)]


def _iter_strings(value: Any):
    if isinstance(value, str):
        if value.strip():
            yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _iter_strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from _iter_strings(v)


def _dedupe_preserve(items: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        key = item.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item.strip())
    return out


def _topics_from_summary(summary: str) -> list[str]:
    return _dedupe_preserve([m.group(1).strip() for m in _HEADING.finditer(summary or "")])


def _normalize_symbol(raw: str) -> str | None:
    token = (raw or "").strip().upper()
    if not token:
        return None
    if token in _STOP_TICKERS:
        return None
    if not re.fullmatch(r"[A-Z]{1,6}(?:\.[A-Z])?", token):
        return None
    return token


def _symbols_from_text(text: str) -> list[str]:
    if not text:
        return []
    found: list[str] = []
    for match in _DOLLAR_TICKER.finditer(text):
        sym = _normalize_symbol(match.group(1))
        if sym:
            found.append(sym)
    for match in _PAREN_TICKER.finditer(text):
        sym = _normalize_symbol(match.group(1))
        if sym:
            found.append(sym)
    return _dedupe_preserve(found)


def _normalize_symbols(items: list[str] | None) -> list[str]:
    out: list[str] = []
    for item in items or []:
        sym = _normalize_symbol(item)
        if sym:
            out.append(sym)
    return _dedupe_preserve(out)


def _extract_symbols(raw: Any) -> list[str]:
    if isinstance(raw, str):
        return _normalize_symbols([raw])
    if isinstance(raw, list):
        return _normalize_symbols([str(x) for x in raw if x is not None])
    if isinstance(raw, dict):
        symbols = raw.get("symbols")
        if symbols is not None:
            return _extract_symbols(symbols)
        tickers = raw.get("tickers")
        if tickers is not None:
            return _extract_symbols(tickers)
    return []


def _enrich_symbols(output: DistillOutput, text: str) -> DistillOutput:
    merged = _dedupe_preserve(output.symbols + _symbols_from_text(output.summary or "") + _symbols_from_text(text))
    return output.model_copy(update={"symbols": merged})


def _fallback_from_partials(partials: list[DistillOutput]) -> DistillOutput:
    merged_summary = "\n\n".join(
        f"### Chunk {idx}\n{(p.summary or '').strip()}" for idx, p in enumerate(partials, 1)
    ).strip()
    topics = _dedupe_preserve([t for p in partials for t in (p.key_topics or [])])
    if not topics:
        topics = _topics_from_summary(merged_summary)
    symbols = _dedupe_preserve([s for p in partials for s in (p.symbols or [])])
    segments = [s.model_dump() for p in partials for s in (p.segments or [])][:200]
    return DistillOutput(summary=merged_summary, key_topics=topics, symbols=symbols, segments=segments)


def _is_thin_reduce_output(*, reduced: DistillOutput, partials: list[DistillOutput], total_partial_chars: int) -> bool:
    partial_topic_count = sum(1 for p in partials if p.key_topics)
    partial_segment_count = sum(1 for p in partials if p.segments)
    reduced_chars = len((reduced.summary or "").strip())
    if reduced_chars < max(300, int(total_partial_chars * 0.15)):
        return True
    if (not reduced.key_topics and partial_topic_count > 0) or (
        not reduced.segments and partial_segment_count > 0
    ):
        return True
    return False


def _coerce_distill(data: Any) -> dict[str, Any]:
    if isinstance(data, dict) and isinstance(data.get("summary"), str) and data["summary"].strip():
        return {**data, "symbols": _extract_symbols(data)}
    if isinstance(data, str):
        return {"summary": data, "symbols": _symbols_from_text(data)}
    if not isinstance(data, dict):
        text = str(data)
        return {"summary": text, "symbols": _symbols_from_text(text)}

    if len(data) == 1:
        inner = next(iter(data.values()))
        if isinstance(inner, dict):
            coerced = _coerce_distill(inner)
            if coerced.get("summary"):
                return {**coerced, "symbols": _extract_symbols(data) or coerced.get("symbols", [])}
        if isinstance(inner, str) and inner.strip():
            return {"summary": inner, "symbols": _symbols_from_text(inner)}

    for alt in ("markdown", "document", "content", "text", "body", "summary_markdown"):
        if isinstance(data.get(alt), str) and data[alt].strip():
            return {**data, "summary": data[alt], "symbols": _extract_symbols(data) or _symbols_from_text(data[alt])}

    if data.get("summary") is not None:
        joined = "\n\n".join(_iter_strings(data["summary"]))
        if joined.strip():
            return {**data, "summary": joined, "symbols": _extract_symbols(data) or _symbols_from_text(joined)}

    candidates = list(_iter_strings(data))
    if candidates:
        summary = max(candidates, key=len)
        return {**data, "summary": summary, "symbols": _extract_symbols(data) or _symbols_from_text(summary)}
    return data


def _merge_usage(acc: dict[str, Any], usage: dict[str, Any]) -> None:
    for k, v in (usage or {}).items():
        if isinstance(v, (int, float)):
            acc[k] = acc.get(k, 0) + v


def distill(llm_client, text: str, *, max_chunk_chars: int = 6000) -> tuple[DistillOutput, dict[str, Any]]:
    if len(text) <= max_chunk_chars:
        data, usage = llm_client.complete_json(DISTILL_SYSTEM, _user_prompt(text))
        out = DistillOutput.model_validate(_coerce_distill(data))
        return _enrich_symbols(out, text), usage

    chunks = _chunks(text, max_chunk_chars)
    partials: list[DistillOutput] = []
    total_usage: dict[str, Any] = {}
    for chunk in chunks:
        data, usage = llm_client.complete_json(DISTILL_SYSTEM, _user_prompt(chunk))
        partials.append(_enrich_symbols(DistillOutput.model_validate(_coerce_distill(data)), chunk))
        _merge_usage(total_usage, usage)

    combined = "\n\n".join(f"### Chunk {idx}\n{(p.summary or '').strip()}" for idx, p in enumerate(partials, 1))
    data, usage = llm_client.complete_json(REDUCE_SYSTEM, _user_prompt(combined))
    _merge_usage(total_usage, usage)
    reduced = DistillOutput.model_validate(_coerce_distill(data))
    total_partial_chars = sum(len((p.summary or "").strip()) for p in partials)
    if _is_thin_reduce_output(reduced=reduced, partials=partials, total_partial_chars=total_partial_chars):
        log.warning("reduce output looked too thin; using fallback")
        reduced = _fallback_from_partials(partials)
    return _enrich_symbols(reduced, text), total_usage
