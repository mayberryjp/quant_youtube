from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Segment(BaseModel):
    model_config = ConfigDict(extra="ignore")
    speaker: str | None = None
    role: str | None = None
    summary: str = ""


class DistillOutput(BaseModel):
    model_config = ConfigDict(extra="ignore")
    summary: str
    key_topics: list[str] = Field(default_factory=list)
    symbols: list[str] = Field(default_factory=list)
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
