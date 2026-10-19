"""Result projection replay/binding protocol shared by store and session."""

from typing import Any

from config.policy import BatchUnitPolicy
from utils.batch_pipeline.contracts import ProjectionBinding


class ProjectionBlocked(RuntimeError):
    """A predecessor, immutable binding, or ledger owner is not ready."""


class ProjectionReplay(Exception):
    def __init__(self, receipt: dict):
        self.receipt = receipt


def normalized_binding(raw: dict[str, Any], *, policy: BatchUnitPolicy | None = None) -> ProjectionBinding:
    values: dict[str, Any] = {**raw, 'segment_ids': tuple(raw['segment_ids'])}
    if values.get('policy') is None and policy is not None:
        values['policy'] = policy
    return ProjectionBinding(**values)
