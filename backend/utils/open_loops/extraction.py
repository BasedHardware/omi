"""Bridge from a parsed notes output to the persisted open-loop payload."""

from __future__ import annotations

from typing import Any, Optional

OPEN_LOOP_EXTRACTIONS_FIELD = 'open_loop_extractions'
OPEN_LOOP_EXTRACTIONS_COMPRESSED_FIELD = 'open_loop_extractions_compressed'
OPEN_LOOP_EXTRACTIONS_VERSION = 1

OPEN_LOOP_LIST_FIELDS = ('delegated_by_user', 'commitments_by_others', 'observed_issue_or_blocker')


def _carries_open_loop_fields(output: Any) -> bool:
    return all(hasattr(output, field) for field in OPEN_LOOP_LIST_FIELDS)


def extraction_payload(output: Any) -> Optional[dict[str, Any]]:
    """The persistable open-loop payload from one parsed notes output.

    Returns None when nothing was extracted; the caller writes an explicit
    null in that case so a reprocess clears stale extractions.
    """
    issue = getattr(output, 'observed_issue_or_blocker', None)
    delegated = [entry.model_dump() for entry in (getattr(output, 'delegated_by_user', None) or [])]
    committed = [entry.model_dump() for entry in (getattr(output, 'commitments_by_others', None) or [])]
    if not delegated and not committed and issue is None:
        return None
    return {
        'version': OPEN_LOOP_EXTRACTIONS_VERSION,
        'delegated_by_user': delegated,
        'commitments_by_others': committed,
        'observed_issue_or_blocker': issue.model_dump() if issue is not None else None,
    }


def capture_into_sink(output: Any, sink: Optional[dict[str, Any]]) -> None:
    """Record one fresh notes parse on the mutable sink the pipeline owns.

    No-op when the sink is None or the parsed schema carries no open-loop
    fields (switch off), so dedupe reuse, quiet-minimum and flag-off paths
    leave the stored field untouched instead of wiping it. A fresh parse that
    found nothing records None, which the pipeline persists as an explicit
    clearing null.
    """
    if sink is None or not _carries_open_loop_fields(output):
        return
    sink['extractions'] = extraction_payload(output)
