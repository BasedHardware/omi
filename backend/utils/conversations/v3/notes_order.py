"""The order the v3 notes drain settles an owner's pending rows in: manual Finishes first.

The drain runs one row at a time, and its scan is in document-id order, so a Finish the owner is waiting
on could sit behind unrelated rows (a backlog, or the other windows of the same pass).
"""

from datetime import datetime, timezone

from config.conversations_v3 import notes_finish_first_enabled
from utils.conversations.v3 import metrics, policy

_OLDEST = datetime.min.replace(tzinfo=timezone.utc)


def _finished(row):
    finished = row.get('finished_at')
    return finished if isinstance(finished, datetime) else _OLDEST


def finish_first(rows):
    """The owner's manual Finishes first, newest first; every other row keeps the scan's order."""
    finishes = [row for row in rows if row is not None and policy.manual_intent(row)]
    if not finishes or not notes_finish_first_enabled():
        return rows
    finishes.sort(key=_finished, reverse=True)
    ordered = finishes + [row for row in rows if row is None or not policy.manual_intent(row)]
    if any(moved is not kept for moved, kept in zip(ordered, rows)):
        metrics.safe_metric(lambda: metrics.NOTES_FINISH_FIRST.inc())
    return ordered
