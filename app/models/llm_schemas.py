from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.domain import Direction, EntityType


def _clamp(value: float | None, lo: float, hi: float) -> float | None:
    if value is None:
        return None
    return max(lo, min(hi, value))


class Segment(BaseModel):
    model_config = ConfigDict(extra="ignore")
    speaker: str | None = None
    role: str | None = None
    summary: str = ""


class DistillOutput(BaseModel):
    model_config = ConfigDict(extra="ignore")
    summary: str
    key_topics: list[str] = Field(default_factory=list)
    segments: list[Segment] = Field(default_factory=list)


class SentimentObservation(BaseModel):
    model_config = ConfigDict(extra="ignore")
    subject_type: Literal["ticker", "sector", "theme", "market"] = "market"
    subject: str = "ALL"
    sentiment_label: Literal["bullish", "bearish", "neutral"] = "neutral"
    sentiment_score: float | None = Field(default=None, ge=-1.0, le=1.0)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    horizon: str | None = None
    reason: str | None = None


class SentimentOutput(BaseModel):
    model_config = ConfigDict(extra="ignore")
    observations: list[SentimentObservation] = Field(default_factory=list)


class EntityMention(BaseModel):
    model_config = ConfigDict(extra="ignore")
    raw_mention: str
    entity_type: EntityType = EntityType.company
    company_name: str | None = None
    ticker: str | None = None
    speaker: str | None = None
    direction: Direction | None = None
    confidence: float | None = None
    context: str | None = None

    @field_validator("entity_type", mode="before")
    @classmethod
    def _coerce_entity_type(cls, v: object) -> object:
        # Fall back to company for LLM-invented types (e.g. 'index', 'etf').
        if v is None or v == "":
            return EntityType.company
        try:
            return EntityType(v)
        except (ValueError, TypeError):
            return EntityType.company

    @field_validator("direction", mode="before")
    @classmethod
    def _coerce_direction(cls, v: object) -> object:
        # Drop LLM-invented directions rather than fail validation.
        if v is None or v == "":
            return None
        try:
            return Direction(v)
        except (ValueError, TypeError):
            return None

    @field_validator("ticker")
    @classmethod
    def _upper_ticker(cls, v: str | None) -> str | None:
        v = (v or "").strip().upper()
        return v or None

    @field_validator("confidence")
    @classmethod
    def _clamp_conf(cls, v: float | None) -> float | None:
        return _clamp(v, 0.0, 1.0)


class EntityOutput(BaseModel):
    model_config = ConfigDict(extra="ignore")
    entities: list[EntityMention] = Field(default_factory=list)
