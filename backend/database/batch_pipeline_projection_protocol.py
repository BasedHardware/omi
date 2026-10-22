"""Result projection replay/binding protocol shared by store and session."""

from typing import Any

from utils.batch_pipeline.contracts import ProjectionBinding


class ProjectionBlocked(RuntimeError):
    """A predecessor, immutable binding, or ledger owner is not ready."""


class ProjectionPredecessorPending(ProjectionBlocked):
    """The owner chain must replay an earlier committed row before this one."""


class ProjectionReplay(Exception):
    def __init__(self, receipt: dict):
        self.receipt = receipt


def normalized_binding(raw: dict[str, Any]) -> ProjectionBinding:
    values: dict[str, Any] = {**raw, 'segment_ids': tuple(raw['segment_ids'])}
    return ProjectionBinding(**values)
