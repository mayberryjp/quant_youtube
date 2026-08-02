from __future__ import annotations

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
    segments: list[Segment] = Field(default_factory=list)
