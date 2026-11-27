"""Wake a recent Finish again in seconds after a builder pass committed around it or raced.

A Finish's own write (its cut, or its fast transcript) can land while another pass holds the owner: that
pass commits around it (source_moved) or races, and its coalesced next-minute wake would hold the Finish
for up to a minute more. A recent Finish recording is woken again ``FINISH_REWAKE`` after that pass
released its lease instead. Each Finish recording gets at most ``FINISH_REWAKE_LIMIT`` re-wakes: they are
Cloud Tasks named by the recording and an ordinal, with no clock in the name, so a Finish whose passes keep
racing (a deterministic guard answers ``source_changed`` too) stops after the last ordinal without any
stored state. The minute wake the caller already scheduled stays the backstop, so every failure here is
logged and swallowed.
"""

import hashlib
import logging
import math
import os
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone

from config.conversations_v3 import finish_fast_rewake_enabled
from database import conversations_v3_finish_markers as markers
from utils.cloud_tasks import enqueue_named_task
from utils.conversations.v3 import metrics
from utils.conversations.v3.finish_stamp import FINISH_STAMP_FIELD
from utils.conversations.v3.triggers import task_base
from utils.executors import db_executor, run_blocking

logger = logging.getLogger(__name__)

FINISH_REWAKE = timedelta(seconds=3)
FINISH_REWAKE_LIMIT = 2
FINISH_REWAKE_WINDOW = timedelta(minutes=3)


def _aware(value):
    if not isinstance(value, datetime):
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def finish_time(row):
    """When the owner finished this recording: the Finish stamp when one is stored, else ``finished_at``.

    None for a row that is not a Finish (no cut and no stored request), or that is deleted or discarded.
    """
    if not row or row.get('deleted') or row.get('discarded'):
        return None
    if row.get('v3_manual_end') is not True and row.get('v3_manual_end_requested') is not True:
        return None
    stamp = row.get(FINISH_STAMP_FIELD)
    return (_aware(stamp.get('at')) if isinstance(stamp, Mapping) else None) or _aware(row.get('finished_at'))


def recent_finish(row, now):
    """A recording the owner finished within ``FINISH_REWAKE_WINDOW`` of now."""
    finished = finish_time(row)
    # Either side of now: a Finish written during the pass, or a device clock slightly ahead, is recent too.
    return finished is not None and abs(now - finished) <= FINISH_REWAKE_WINDOW


def _newest(rows, now):
    """The id of the most recently finished recent Finish among ``rows`` (id -> row), or None."""
    recent = [(finish_time(row), rid) for rid, row in rows.items() if recent_finish(row, now)]
    return max(recent)[1] if recent else None


def task_id(uid, rid, ordinal):
    """The re-wake's full Cloud Tasks name: owner, Finish recording and ordinal, no clock."""
    owner = hashlib.sha256(uid.encode()).hexdigest()[:32]
    recording = hashlib.sha256(rid.encode()).hexdigest()[:32]
    return f'conversations-v3-{owner}-finish-rewake-{recording}-{ordinal}'


def _schedule(uid, rid, at):
    """Blocking. Create the first free ordinal's task; its ordinal, or None when every name is taken.

    Cloud Tasks refuses a name it still holds (queued, or run within about an hour), well past the window.
    """
    # The queue and handler of triggers.enqueue, which names its tasks by minute.
    queue = os.getenv('CONVERSATIONS_V3_TASKS_QUEUE', 'conversations-v3')
    url = task_base() + '/v1/conversations-v3/reconcile'
    for ordinal in range(1, FINISH_REWAKE_LIMIT + 1):
        if enqueue_named_task(queue, url, task_id(uid, rid, ordinal), {'uid': uid}, schedule_at=at):
            return ordinal
    return None


async def wake_soon(uid, rid, reason, now):
    at = math.ceil((now + FINISH_REWAKE).timestamp())
    ordinal = await run_blocking(db_executor, _schedule, uid, rid, at)
    outcome = 'scheduled' if ordinal else 'capped'
    metrics.safe_metric(lambda: metrics.FINISH_REWAKES.labels(reason, outcome).inc())


def _failed(error):
    metrics.safe_metric(
        lambda: logger.warning('event=v3_finish_rewake outcome=error exception_type=%s', type(error).__name__)
    )


def _by_recency(recordings, ids):
    """``ids`` newest first by their loaded rows, so a bounded marker read keeps the likeliest Finishes."""
    epoch = datetime.min.replace(tzinfo=timezone.utc)

    def when(rid):
        row = recordings.get(rid) or {}
        return finish_time(row) or _aware(row.get('finished_at')) or _aware(row.get('started_at')) or epoch

    return sorted(ids, key=lambda rid: (when(rid), rid), reverse=True)


async def after_moved(uid, recordings, moved):
    """A committed pass left ``moved`` recordings owed; wake soon if one of them is a recent Finish.

    Called after the pass released its lease, so the follow-up finds the builder free.
    """
    try:
        if not finish_fast_rewake_enabled():
            return
        now = datetime.now(timezone.utc)
        # The loaded snapshot can predate the Finish write that moved the recording: judge the stored row.
        rid = _newest({rid: recordings.get(rid) for rid in moved}, now)
        if rid is None:
            current = await run_blocking(db_executor, markers.finish_markers, uid, _by_recency(recordings, moved))
            rid = _newest(current, now)
        if rid is not None:
            await wake_soon(uid, rid, 'source_moved', now)
    except Exception as error:
        _failed(error)


async def after_raced(uid, recordings):
    """Nothing committed; wake soon if the pass loaded a pending recent Finish. Called after the release."""
    try:
        if not finish_fast_rewake_enabled():
            return
        now = datetime.now(timezone.utc)
        rid = _newest({rid: row for rid, row in recordings.items() if row.get('v3_pending')}, now)
        if rid is not None:
            await wake_soon(uid, rid, 'raced', now)
    except Exception as error:
        _failed(error)
