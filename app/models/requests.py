from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict


class ReprocessRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    from_date: date | None = None
    to_date: date | None = None
    only_stale: bool = False


class RetryFailedRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    from_date: date | None = None
    to_date: date | None = None
    max_attempts: int | None = None
    delete_after_attempts: int | None = None


class RunTriggerRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    run_date: date | None = None
