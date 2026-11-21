"""Recording-derived conversations; independent of the episode engine."""

from datetime import datetime


class Conflict(RuntimeError):
    """Retryable v3 ownership and source-revision conflicts."""


def preview_wakes(rows, recordings) -> dict[str, datetime]:
    """Keep one recording pending per preview so the existing sweep can recover its deadline."""
    wakes: dict[str, datetime] = {}
    for row in rows:
        due = row.get('_v3_preview_due_at')
        if not isinstance(due, datetime):
            continue
        rid = next(
            (
                rid
                for rid in row.get('v3_recording_ids', ())
                if rid in recordings and not recordings[rid].get('deleted')
            ),
            None,
        )
        if rid is not None:
            wakes[rid] = min(due, wakes.get(rid, due))
    return wakes
