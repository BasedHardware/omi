"""Closed, log-safe tokens naming why an owner-chain walk stopped (log only)."""

import re

from config.batch_pipeline import projection_drain_live_target_backoff_enabled
from utils.sync.assignment_errors import SyncAssignmentConflict, SyncAssignmentConflictReason

# `end` is the normal chain end; every other token is a stop with rows possibly
# still unprojected behind it.
WALK_STOPS = frozenset(
    {
        'end',
        'deadline',
        'limit',
        'claim_busy',
        'watermark_error',
        'read_error',
        'prefetch_wait',
        'step_deadline',
        'privacy_blocked',
        'head_error',
        'head_awaiting_live_target',
        'hold_not_landed',
        'not_advanced',
        'owe_error',
        # Drain-turn level (projection_drain.OwnerDrains.run).
        'turn_deadline',
        'error',
    }
)
_BLOCK_MESSAGE = re.compile(r'[a-z][a-z -]{0,63}')


def walk_head_stop(error: BaseException) -> str:
    """Name a bound head whose existing failure resolver left it waiting."""
    return (
        'head_awaiting_live_target'
        if isinstance(error, SyncAssignmentConflict)
        and error.subtype == SyncAssignmentConflictReason.LIVE_TARGET_NOT_PERSISTED
        and projection_drain_live_target_backoff_enabled()
        else 'head_error'
    )


def walk_block_stop(error: BaseException, reason: str) -> str:
    """``blocked_<token>``: the closed block reason, else a slug of a constant literal message."""
    if reason == 'other':
        message = str(error)
        if _BLOCK_MESSAGE.fullmatch(message):
            reason = re.sub(r'[ -]+', '_', message)
    return f'blocked_{reason}'
