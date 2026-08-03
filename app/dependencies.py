from __future__ import annotations

from sqlalchemy.engine import Engine

from app.db import get_engine
from app.repository.distillations import DistillationRepository
from app.repository.entities import EntityRepository
from app.repository.episodes import EpisodeRepository
from app.repository.runs import RunRepository


def episode_repo(engine: Engine | None = None) -> EpisodeRepository:
    return EpisodeRepository(engine or get_engine())


def distillation_repo(engine: Engine | None = None) -> DistillationRepository:
    return DistillationRepository(engine or get_engine())


def entity_repo(engine: Engine | None = None) -> EntityRepository:
    return EntityRepository(engine or get_engine())


def run_repo(engine: Engine | None = None) -> RunRepository:
    return RunRepository(engine or get_engine())
