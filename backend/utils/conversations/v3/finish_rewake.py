"""Wake a recent Finish again in seconds after a builder pass committed around it or raced.

A Finish's own write (its cut, or its fast transcript) can land while another pass holds the owner: that
pass commits around it (source_moved) or races, and its coalesced next-minute wake would hold the Finish
for up to a minute more. A recent Finish recording is woken again ``FINISH_REWAKE`` later instead: one
wake per owner per slot, only while the Finish is recent, so a chain stays short. The minute wake the
caller already scheduled stays the backstop, so every failure here is logged and swallowed.
"""

import logging
from datetime import datetime, timedelta, timezone

from config.conversations_v3 import finish_fast_rewake_enabled
from database import conversations_v3_finish_markers as markers
from utils.conversations.v3 import metrics
from utils.conversations.v3.triggers import enqueue
from utils.executors import db_executor, run_blocking

logger = logging.getLogger(__name__)

FINISH_REWAKE = timedelta(seconds=3)
FINISH_REWAKE_SLOT_SECONDS = 10
FINISH_REWAKE_WINDOW = timedelta(minutes=3)


def recent_finish(row, now):
    """A recording the owner finished (cut or requested) within ``FINISH_REWAKE_WINDOW`` of now."""
    if not row or row.get('deleted') or row.get('discarded'):
        return False
    if row.get('v3_manual_end') is not True and row.get('v3_manual_end_requested') is not True:
        return False
    finished = row.get('finished_at')
    # Either side of now: a Finish written during the pass, or a device clock slightly ahead, is recent too.
    return isinstance(finished, datetime) and abs(now - finished) <= FINISH_REWAKE_WINDOW


async def wake_soon(uid, reason, now):
    slot = int(now.timestamp()) // FINISH_REWAKE_SLOT_SECONDS
    await run_blocking(db_executor, enqueue, uid, at=now + FINISH_REWAKE, wake_key=f'finish-rewake-{slot}')
    metrics.safe_metric(lambda: metrics.FINISH_REWAKES.labels(reason).inc())


def _failed(error):
    metrics.safe_metric(
        lambda: logger.warning('event=v3_finish_rewake outcome=error exception_type=%s', type(error).__name__)
    )


async def after_moved(uid, recordings, moved):
    """A committed pass left ``moved`` recordings owed; wake soon if one of them is a recent Finish."""
    try:
        if not finish_fast_rewake_enabled():
            return
        now = datetime.now(timezone.utc)
        # The loaded snapshot can predate the Finish write that moved the recording: judge the stored row.
        if not any(recent_finish(recordings.get(rid), now) for rid in moved):
            current = await run_blocking(db_executor, markers.finish_markers, uid, moved)
            if not any(recent_finish(row, now) for row in current.values()):
                return
        await wake_soon(uid, 'source_moved', now)
    except Exception as error:
        _failed(error)


async def after_raced(uid, recordings):
    """Nothing committed; wake soon if the pass loaded a pending recent Finish."""
    try:
        if not finish_fast_rewake_enabled():
            return
        now = datetime.now(timezone.utc)
        if any(row.get('v3_pending') and recent_finish(row, now) for row in recordings.values()):
            await wake_soon(uid, 'raced', now)
    except Exception as error:
        _failed(error)
