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


def passive_finish(row):
    """A media or background window the owner finished that shows on Home.

    ``policy.manual_intent`` leaves these out (they get no full notes), but the owner is waiting on the
    card. The stored ``home_hidden`` is the planner's projection of ``CONVERSATIONS_V3_MANUAL_END_HOME_VISIBLE``
    for the row, so a passive Finish that Home hides stays in the scan's order.
    """
    return bool(
        policy.flag(row, 'v3_derived')
        and policy.flag(row, 'manual_end')
        and policy.field(row, 'kind') in {'media', 'background'}
        and row.get('home_hidden') is False
    )


def _finish(row):
    return row is not None and (policy.manual_intent(row) or passive_finish(row))


def finish_first(rows):
    """The owner's Finishes first, every other row after them in the scan's order.

    Visible passive Finishes lead: they settle without a model call, so they cost a manual Finish behind them
    almost nothing, while one behind a 20 to 40 s summary would wait that long. Each group is newest first.
    """
    finishes = [row for row in rows if _finish(row)]
    if not finishes or not notes_finish_first_enabled():
        return rows
    finishes.sort(key=lambda row: (passive_finish(row), _finished(row)), reverse=True)
    ordered = finishes + [row for row in rows if not _finish(row)]
    # Count each Finish that moved ahead of at least one other pending row, not reorders among Finishes.
    ahead, seen_other = 0, False
    for row in rows:
        if not _finish(row):
            seen_other = True
        elif seen_other:
            ahead += 1
    if ahead:
        metrics.safe_metric(lambda: metrics.NOTES_FINISH_FIRST.inc(ahead))
    return ordered
