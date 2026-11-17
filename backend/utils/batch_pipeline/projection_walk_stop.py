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
# Closed metric classes for a stop token. ``blocked_<token>`` is an open family
# (a slug of a constant message), so a metric folds it to ``blocked_privacy`` or
# ``blocked`` and the log line keeps the full token.
STOP_CLASSES = tuple(sorted(WALK_STOPS | {'yield', 'blocked', 'blocked_privacy', 'other'}))


def walk_stop_class(stop: str | None) -> str:
    """The closed metric class of a walk/turn stop token."""
    if stop in WALK_STOPS or stop == 'yield':
        return stop
    if isinstance(stop, str) and stop.startswith('blocked_privacy_'):
        return 'blocked_privacy'
    if isinstance(stop, str) and stop.startswith('blocked_'):
        return 'blocked'
    return 'other'


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
