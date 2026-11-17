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


def source_reader_marked(entry: dict[str, Any], job: dict[str, Any]) -> bool:
    """Whether a protocol-2 result row is a source-reuse row this reader may project.

    The ordered merger copies the job's ``source_reuse_version`` /
    ``source_alias_version`` onto the result row. A merger built before source
    reuse (a GPU pump image older than the intake that stamped the job) copies
    only ``protocol_version``: the row is then protocol 2 with no marker, and
    refusing it stops the owner's whole projection chain behind it. The
    immutable job carries the same marker, so a row with neither marker field
    is admitted on the job's. A row whose marker is present but wrong is
    still refused.
    """
    if not job.get('source_reuse_key'):
        return False
    if entry.get('source_reuse_version') == 1 or entry.get('source_alias_version') == 1:
        return True
    return (
        'source_reuse_version' not in entry
        and 'source_alias_version' not in entry
        and (job.get('source_reuse_version') == 1 or job.get('source_alias_version') == 1)
    )
