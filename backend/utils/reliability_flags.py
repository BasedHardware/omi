"""The flag store read behind ``config.reliability_experiments``.

``admits(key, uid)`` answers whether the Omi flag store rule ``key`` admits the account. A thread
reads the store directly (an in-memory evaluation; the store refreshes its snapshot at most every
15 s). An event loop never does: a snapshot refresh is a Redis read and sometimes a Firestore read,
so on a loop the answer is what was last learned for that account and key, and a worker thread
learns it again when that is older than ``REFRESH_SECONDS``. An account never seen by this process
reads as not admitted until that first read lands; ``warm(uid)`` awaits it.

Bound by ``utils.rollout_cohorts.configure_rollout_runtime``, which every serving process and
worker already calls at start.
"""

from __future__ import annotations

import asyncio
import contextvars
import logging
import time
from collections import OrderedDict
from threading import Lock

from config import reliability_experiments
from utils import executors, omi_flags

logger = logging.getLogger(__name__)

REFRESH_SECONDS = 15.0
MAX_ANSWERS = 8192

_lock = Lock()
# (key, uid) -> (admitted, monotonic time learned). Oldest answers leave first.
_answers: OrderedDict[tuple[str, str], tuple[bool, float]] = OrderedDict()
# Accounts whose rules a worker thread is learning now: one task per account, whatever the key asked for.
_refreshing: set[str] = set()


def _now() -> float:
    return time.monotonic()


def _learn(key: str, uid: str) -> bool:
    try:
        resolved = omi_flags.resolve(key, uid)
        admitted = resolved is not None and resolved.enabled
    except Exception as error:
        logger.warning('event=reliability_flag outcome=read_failed exception_type=%s', type(error).__name__)
        admitted = False
    with _lock:
        _answers[(key, uid)] = (admitted, _now())
        _answers.move_to_end((key, uid))
        while len(_answers) > MAX_ANSWERS:
            _answers.popitem(last=False)
    return admitted


def _on_event_loop() -> bool:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return False
    return True


def _learn_all(uid: str) -> None:
    try:
        for key in reliability_experiments.EXPERIMENTS:
            _learn(key, uid)
    finally:
        with _lock:
            _refreshing.discard(uid)


def _submit(uid: str) -> None:
    executors.get_rollout_executor().submit(contextvars.copy_context().run, _learn_all, uid)


def admits(key: str, uid: str) -> bool:
    if not _on_event_loop():
        return _learn(key, uid)
    with _lock:
        known = _answers.get((key, uid))
        stale = known is None or _now() - known[1] >= REFRESH_SECONDS
        refresh = stale and uid not in _refreshing
        if refresh:
            _refreshing.add(uid)
    if refresh:
        try:
            _submit(uid)
        except Exception:
            # A full queue or a closing pool: keep the answer held and try again on a later check.
            with _lock:
                _refreshing.discard(uid)
    return known is not None and known[0]


async def warm(uid: str) -> None:
    """Learn every rule for the account on a worker thread, unless all of them were learned recently."""
    now = _now()
    with _lock:
        fresh = all(
            (known := _answers.get((key, uid))) is not None and now - known[1] < REFRESH_SECONDS
            for key in reliability_experiments.EXPERIMENTS
        )
    if not fresh:
        await executors.run_blocking(executors.get_rollout_executor(), _learn_all, uid)


def reset() -> None:
    """Forget every answer (tests)."""
    with _lock:
        _answers.clear()
        _refreshing.clear()


def configure() -> None:
    reliability_experiments.configure_resolver(admits, warm)
