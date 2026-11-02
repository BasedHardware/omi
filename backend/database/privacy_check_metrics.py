"""Privacy decisions and session census with closed, identifier-free labels."""

import asyncio
from collections import Counter as Counts
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
import logging
import threading
import time

from prometheus_client import Counter, Histogram
from database.batch_privacy_attempt import PrivacyAttempt

logger = logging.getLogger(__name__)
FAMILIES = frozenset({'batch', 'external', 'tombstone', 'deletion_marker'})
REASONS = frozenset(
    {
        'allow',
        'account_deleted',
        'account_missing',
        'data_protection_changed',
        'privacy_generation_changed',
        'conversation_redirect_cycle',
        'conversation_fence_budget',
        'conversation_deleted',
        'recording_privacy_changed',
        'conversation_redirect_missing',
        'result_lease_lost',
        'destructive_operation',
        'authority_unavailable',
        'unknown',
    }
)
CHECKS = Counter('privacy_checks_total', 'Privacy check decisions', ['family', 'mode', 'reason'])
CALLS = Counter('privacy_check_calls_total', 'Privacy check calls including invalid inputs', ['family', 'mode'])
READS = Counter('privacy_check_reads_total', 'Privacy document reads issued', ['family', 'mode', 'result'])
WALKS = Counter('privacy_conversations_walked_total', 'Distinct conversation documents walked per check', ['mode'])
DECISION_MISMATCH = Counter(
    'privacy_decision_mismatch_total', 'Live and candidate privacy decisions disagree', ['family', 'reason']
)
SHADOW_CHECKS = Counter('privacy_shadow_checks_total', 'Privacy shadow comparisons', ['family', 'result'])
MEMO_REQUESTS = Counter('privacy_memo_requests_total', 'Candidate decision reuse', ['family', 'result'])
CENSUS = Histogram(
    'privacy_session_cycle_operations',
    'Operations in each completed 60 second session interval',
    ['plane', 'family', 'mode', 'kind'],
    buckets=(0, 1, 2, 3, 4, 8, 16, 32, 64, 128, 256),
)

_MODE: ContextVar[str] = ContextVar('privacy_metrics_mode', default='live')
_READ_CALLER: ContextVar[str | None] = ContextVar('privacy_read_caller', default=None)
_READ_CALLERS = {
    'batch': 'database.batch_pipeline_privacy:read',
    'external': 'database.legal_holds:external_write_fence',
    'tombstone': 'database.conversation_tombstones:is_deleted',
    'deletion_marker': 'database.account_deletion_marker:_s4_read_deletion_status',
}
_SESSION: ContextVar['SessionCensus | None'] = ContextVar('privacy_metrics_session', default=None)
_LOG_LOCK = threading.Lock()
_LOG_AT = {}


def _family(value):
    return value if value in FAMILIES else 'batch'


def _reason(value):
    return value if value in REASONS else 'unknown'


def _count(family, kind):
    session = _SESSION.get()
    if session is not None:
        with session.lock:
            if not session.closed:
                session.counts[(_family(family), _MODE.get(), kind)] += 1


def decision(family, reason='allow'):
    try:
        CHECKS.labels(_family(family), _MODE.get(), _reason(reason)).inc()
    except Exception:
        pass  # Metrics must never alter authority decisions.


def called(family):
    try:
        CALLS.labels(_family(family), _MODE.get()).inc()
        _count(family, 'checks')
    except Exception:
        pass


def memo_result(family, result):
    try:
        result = result if result in {'hit', 'miss', 'ineligible'} else 'ineligible'
        MEMO_REQUESTS.labels(_family(family), result).inc()
    except Exception:
        pass


def read_snapshot(family, reference, *, memo_read=False, **kwargs):
    """Count issued reads, including failures, without inspecting paths or payloads."""
    _count(family, 'reads')
    caller = (
        'database.batch_pipeline_privacy:get' if family == 'batch' and memo_read else _READ_CALLERS[_family(family)]
    )
    caller_token = _READ_CALLER.set(caller)
    try:
        snapshot = reference.get(**kwargs)
    except BaseException:
        _read_result(family, 'error')
        raise
    finally:
        _READ_CALLER.reset(caller_token)
    _read_result(family, 'hit' if snapshot.exists else 'miss')
    return snapshot


def current_read_caller():
    """Only the closed names above may override SDK attribution."""
    return _READ_CALLER.get()


def _read_result(family, result):
    try:
        READS.labels(_family(family), _MODE.get(), result).inc()
    except Exception:
        pass


def walked():
    try:
        WALKS.labels(_MODE.get()).inc()
        _count('batch', 'conversations')
    except Exception:
        pass


@contextmanager
def mode_scope(mode):
    token = _MODE.set('shadow' if mode == 'shadow' else 'live')
    try:
        yield
    finally:
        _MODE.reset(token)


def compare(family, live, candidate):
    """Only bounded decision names leave this module; never exception text."""
    family, live, candidate = _family(family), _reason(live), _reason(candidate)
    mismatch = live != candidate
    try:
        SHADOW_CHECKS.labels(family, 'mismatch' if mismatch else 'match').inc()
        if mismatch:
            reason = 'stale_allow' if candidate == 'allow' else 'stale_block' if live == 'allow' else 'block_reason'
            DECISION_MISMATCH.labels(family, reason).inc()
            # At most one fixed-size line per family per minute, across threads.
            with _LOG_LOCK:
                now = time.monotonic()
                if now - _LOG_AT.get(family, -60.0) >= 60:
                    _LOG_AT[family] = now
                    logger.warning(
                        'privacy shadow decision_mismatch family=%s reason=%s live=%s candidate=%s',
                        family,
                        reason,
                        live,
                        candidate,
                    )
    except Exception:
        pass


def shadow_error(family):
    try:
        SHADOW_CHECKS.labels(_family(family), 'error').inc()
    except Exception:
        pass


class SessionCensus:
    def __init__(self, plane):
        self.plane = 'pusher' if plane == 'pusher' else 'listen'
        self.counts = Counts()
        self.lock = threading.RLock()
        self.closed = False
        self.memo = PrivacyAttempt()

    def flush(self):
        with self.lock:
            if self.closed:
                return
            counts, self.counts = self.counts, Counts()
        for family in FAMILIES:
            for mode in ('live', 'shadow'):
                for kind in ('checks', 'reads', 'conversations'):
                    try:
                        CENSUS.labels(self.plane, family, mode, kind).observe(counts[(family, mode, kind)])
                    except Exception:
                        pass


def flush_session_census():
    session = _SESSION.get()
    if session is not None:
        session.flush()


def reset_session_census():
    """Start the first full interval after session bootstrap has completed."""
    session = _SESSION.get()
    if session is not None:
        with session.lock:
            session.counts.clear()


def session_memo():
    session = _SESSION.get()
    return session.memo if session is not None and not session.closed else None


async def _pusher_census_ticks(holder):
    from utils.executors import db_executor, run_blocking

    while True:
        await asyncio.sleep(60)
        try:
            await run_blocking(db_executor, holder.flush)
        except Exception:
            pass  # Telemetry must not end an otherwise healthy socket.


def with_session_census(plane):
    def decorate(function):
        @wraps(function)
        async def wrapped(*args, **kwargs):
            holder = SessionCensus(plane)
            token = _SESSION.set(holder)
            ticker = (
                asyncio.create_task(_pusher_census_ticks(holder), name='privacy:pusher:census')
                if holder.plane == 'pusher'
                else None
            )
            try:
                return await function(*args, **kwargs)
            finally:
                try:
                    if ticker is not None:
                        ticker.cancel()
                        await asyncio.gather(ticker, return_exceptions=True)
                finally:
                    with holder.lock:
                        holder.closed = True
                        holder.counts.clear()
                        holder.memo.close()
                    _SESSION.reset(token)

        return wrapped

    return decorate
