"""Result projection replay/binding protocol shared by store and session."""

from typing import Any

from utils.batch_pipeline.contracts import ProjectionBinding


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


_SOURCE_MARKERS = ('source_reuse_version', 'source_alias_version')


def source_reader_marked(entry: dict[str, Any], job: dict[str, Any]) -> bool:
    """Whether a protocol-2 result row is a source-reuse row this reader may project.

    The ordered merger copies the job's ``source_reuse_version`` /
    ``source_alias_version`` onto the result row. A merger built before source
    reuse (a GPU pump image older than the intake that stamped the job) copies
    only ``protocol_version``: the row is then protocol 2 with no marker, and
    refusing it stops the owner's whole projection chain behind it
    (2026-11-16 incident). Rules:

    - no ``source_reuse_key`` on the job: never a source row;
    - any marker field present on the row: at least one non-null marker, and
      every non-null marker must be 1 (a present-but-wrong marker is refused,
      never inherited from the job);
    - no marker field on the row: inherit the immutable job's marker, and
      count it, so the residual pre-reuse merger output is observable.
    """
    if not job.get('source_reuse_key'):
        return False
    if any(field in entry for field in _SOURCE_MARKERS):
        values = [entry.get(field) for field in _SOURCE_MARKERS if entry.get(field) is not None]
        return bool(values) and all(value == 1 for value in values)
    inherited = any(job.get(field) == 1 for field in _SOURCE_MARKERS)
    if inherited:
        from utils.observability.fallback import record_fallback

        record_fallback(
            component='sync_dispatch',
            from_mode='row_source_marker',
            to_mode='job_source_marker',
            reason='capability_mismatch',
            outcome='recovered',
        )
    return inherited
