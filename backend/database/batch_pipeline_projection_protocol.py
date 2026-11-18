"""Result projection replay/binding protocol shared by store and session."""

from typing import Any

from utils.batch_pipeline.contracts import ProjectionBinding
from utils.batch_pipeline.result_protocol import SOURCE_MARKERS, REQUIRED, supported, requirements
from utils.observability.fallback import record_fallback


class ProjectionBlocked(RuntimeError):
    """A predecessor, immutable binding, or ledger owner is not ready."""


class ProjectionPredecessorPending(ProjectionBlocked):
    """The owner chain must replay an earlier committed row before this one."""


class ProjectionGenerationAmbiguous(ProjectionBlocked):
    """Validated intake reached the unresolved generation fence; never assign text."""


class ProjectionReplay(Exception):
    def __init__(self, receipt: dict):
        self.receipt = receipt


def normalized_binding(raw: dict[str, Any]) -> ProjectionBinding:
    values: dict[str, Any] = {**raw, 'segment_ids': tuple(raw['segment_ids'])}
    return ProjectionBinding(**values)


_SOURCE_MARKERS = SOURCE_MARKERS

# Result-row fields stamping a bounded-retry head's first failure. Written
# once per failure episode; the release reset and source-fallback redrive
# clear them. A privacy replay continues the same head-wait episode.
PROJECTION_HEAD_BLOCKED_SINCE = 'projection_blocked_since'
PROJECTION_HEAD_BLOCK_TYPE = 'projection_block_type'


def source_reader_marked(entry: dict[str, Any], job: dict[str, Any]) -> bool:
    """Whether a protocol-2 result row is a source-reuse row this reader may project.

    The ordered merger copies the job's ``source_reuse_version`` /
    ``source_alias_version`` onto the result row. A merger built before source
    reuse (a GPU pump image older than the intake that stamped the job) copies
    only ``protocol_version``: the row is then protocol 2 with no marker, and
    refusing it stops the owner's whole projection chain behind it
    (2026-11-16 incident). Explicit job requirements are checked against the
    registry; every non-null copy must match that job. Missing/null copies are
    recovered and counted once. Older jobs without the map retain these rules:

    - no ``source_reuse_key`` on the job: never a source row;
    - any marker field present on the row: at least one non-null marker, and
      every non-null marker must be 1 (a present-but-wrong marker is refused,
      never inherited from the job);
    - no marker field on the row: inherit the immutable job's marker, and
      count it. This is the permanent compatibility path for independently
      deployed metadata copiers, not a temporary rollout allowance.
    """
    if REQUIRED in job:
        if not supported(job):
            return False
        required = requirements(job)
        # Explicit disagreements are corruption, never a compatibility miss.
        if any(
            entry.get(field) is not None and (type(entry[field]) is not int or entry[field] != required.get(field))
            for field in SOURCE_MARKERS
        ):
            return False
        if any(entry.get(field) is None for field in required):
            _observe_inheritance()
        return bool(required)
    if not job.get('source_reuse_key'):
        return False
    if any(field in entry for field in _SOURCE_MARKERS):
        values = [entry.get(field) for field in _SOURCE_MARKERS if entry.get(field) is not None]
        return bool(values) and all(type(value) is int and value == 1 for value in values)
    inherited = any(type(job.get(field)) is int and job[field] == version for field, version in _SOURCE_MARKERS.items())
    if any(field in job and job[field] != version for field, version in _SOURCE_MARKERS.items()):
        return False
    if inherited:
        _observe_inheritance()
    return inherited


def _observe_inheritance():
    record_fallback(
        component='sync_dispatch',
        from_mode='row_source_marker',
        to_mode='job_source_marker',
        reason='capability_mismatch',
        outcome='recovered',
    )
