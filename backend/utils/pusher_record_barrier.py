"""Session-local drain state backed by persistent capture-level custody."""

import uuid
import os
import time
import logging
import asyncio
import contextvars
import random
import threading
from collections import OrderedDict
from functools import lru_cache
from pathlib import Path
from typing import Callable, ParamSpec, TypeVar
from prometheus_client import Counter, Gauge

from database import record_audio as record_audio_db
from utils.executors import ExecutorSaturatedError, record_barrier_executor, run_blocking
from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)
CLOSE_RETRY_BUDGET = 3
CLOSE_RETRY_MAX_SECONDS = 60.0
CLOSE_RETRY_MAX_IN_FLIGHT = 4
CLOSE_METADATA_DEADLINE_SECONDS = 30.0
# Bound all outstanding writes, including abandoned ones, below pool capacity.
# Leave one quarter of workers (four by default) for begin/failure markers.
CLOSE_METADATA_MAX_OUTSTANDING = min(
    12, max(1, record_barrier_executor._max_workers - max(1, record_barrier_executor._max_workers // 4))
)
_close_retry_slots = threading.BoundedSemaphore(CLOSE_RETRY_MAX_IN_FLIGHT)
_close_outstanding_slots = threading.BoundedSemaphore(CLOSE_METADATA_MAX_OUTSTANDING)
P = ParamSpec('P')
T = TypeVar('T')

RECORD_CLOSE_ABANDONED = Counter(
    'omi_pusher_record_close_abandoned_total',
    'Record close calls with unknown write outcome after their admission deadline',
    ['reason'],
)
_CLOSE_DEADLINE_COUNTER = RECORD_CLOSE_ABANDONED.labels(reason='deadline')
RECORD_CLOSE_ABANDONED_OUTSTANDING = Gauge(
    'omi_pusher_record_close_abandoned_outstanding',
    'Outstanding close metadata calls abandoned at their admission deadline; process-local, no identifiers',
)
RECORD_CLOSE_OUTSTANDING_REFUSALS = Counter(
    'omi_pusher_record_close_outstanding_refusals_total',
    'Close metadata admissions refused because the outstanding-call cap is full',
)


class _CloseAdmission:
    """Recycle admission at a deadline while bounding still-running writes."""

    def __init__(self):
        self.slots = _close_retry_slots
        self.outstanding_slots = _close_outstanding_slots
        self.lock = threading.Lock()
        self.state = 'active'

    def abandon(self):
        with self.lock:
            if self.state == 'active':
                self.state = 'abandoned'
                self.slots.release()
                _CLOSE_DEADLINE_COUNTER.inc()
                RECORD_CLOSE_ABANDONED_OUTSTANDING.inc()

    def completed(self, _future):
        with self.lock:
            if self.state == 'active':
                self.slots.release()
            elif self.state == 'abandoned':
                RECORD_CLOSE_ABANDONED_OUTSTANDING.dec()
            self.outstanding_slots.release()
            self.state = 'completed'


RECORD_BARRIER_FAILURES = Counter(
    'omi_pusher_record_barrier_failures_total', 'Record barrier metadata failures; audio upload continues', ['stage']
)
for _stage in ('begin', 'finish', 'seal', 'failure_marker', 'capacity'):
    RECORD_BARRIER_FAILURES.labels(stage=_stage).inc(0)

RECORD_SEAL_REFUSED = Counter(
    'omi_pusher_record_seal_refused_total', 'Record audio seals refused by persisted custody state', ['reason']
)
_SEAL_REFUSAL_COUNTERS = {
    'producer_pending': RECORD_SEAL_REFUSED.labels(reason='producer_pending'),
    'upload_failed': RECORD_SEAL_REFUSED.labels(reason='upload_failed'),
    'not_batch_owner': RECORD_SEAL_REFUSED.labels(reason='not_batch_owner'),
    'deleted': RECORD_SEAL_REFUSED.labels(reason='deleted'),
}


def _record_failure(stage):
    RECORD_BARRIER_FAILURES.labels(stage=stage).inc()
    record_fallback(
        component='pusher',
        from_mode='record_barrier',
        to_mode='raw_audio',
        reason='other',
        outcome='degraded',
        log=logger,
    )


@lru_cache(maxsize=1)
def producer_identity():
    # Linux process start, stable across websocket sessions. Local development
    # uses a conservative first-use epoch when /proc is unavailable.
    try:
        boot = next(
            float(line.split()[1]) for line in Path('/proc/stat').read_text().splitlines() if line.startswith('btime ')
        )
        fields = Path('/proc/self/stat').read_text().rsplit(')', 1)[1].split()
        started = boot + int(fields[19]) / os.sysconf('SC_CLK_TCK')
    except (OSError, ValueError, StopIteration, IndexError):
        started = time.time()
    return {'pod': os.getenv('HOSTNAME', ''), 'process_started_at': started}


class _ProcessRecordTokens:
    """Bounded recovery hints, never an authority to expire durable producers.

    Only held or successfully drained tokens can be recovered by a later
    producer. Active sockets retain their fence. No socket is retained here;
    eviction forgets a hint without clearing anything in Firestore.
    All access is synchronous on the pusher event loop.
    """

    def __init__(self, *, max_tokens=4096, ttl_seconds=3600):
        self.max_tokens = max_tokens
        self.ttl_seconds = ttl_seconds
        self.pid = os.getpid()
        self.tokens: OrderedDict[tuple[str, str], tuple[float, dict[str, tuple[int, bool]]]] = OrderedDict()
        self.size = 0
        self.order = 0

    def _prune(self):
        if self.pid != os.getpid():
            # Forked children must never recover their parent's tokens.
            self.tokens.clear()
            self.size = 0
            self.pid = os.getpid()
        cutoff = time.monotonic() - self.ttl_seconds
        while self.tokens and next(iter(self.tokens.values()))[0] <= cutoff:
            _, (_, tokens) = self.tokens.popitem(last=False)
            self.size -= len(tokens)

    def mint_order(self):
        self._prune()
        self.order += 1
        return self.order

    def remember(self, uid, cid, token, *, mint_order=None):
        self._prune()
        key = (uid, cid)
        _, tokens = self.tokens.pop(key, (0, {}))
        if token not in tokens:
            tokens[token] = (self.mint_order() if mint_order is None else mint_order, False)
            self.size += 1
        self.tokens[key] = (time.monotonic(), tokens)
        while self.size > self.max_tokens:
            _, (_, evicted) = self.tokens.popitem(last=False)
            self.size -= len(evicted)

    def ready(self, uid, cid, token, *, committed=True):
        self._prune()
        entry = self.tokens.get((uid, cid))
        if entry is not None and token in entry[1]:
            entry[1][token] = (entry[1][token][0], committed)

    def recoverable_before(self, uid, cid, successful_token):
        self._prune()
        entry = self.tokens.get((uid, cid))
        if entry is None or successful_token not in entry[1]:
            return []
        successful_order = entry[1][successful_token][0]
        return [token for token, (order, ready) in entry[1].items() if ready and order < successful_order]

    def forget(self, uid, cid, token):
        self._prune()
        key = (uid, cid)
        entry = self.tokens.get(key)
        if entry is not None and token in entry[1]:
            del entry[1][token]
            self.size -= 1
            if not entry[1]:
                del self.tokens[key]


@lru_cache(maxsize=1)
def _process_record_tokens():
    return _ProcessRecordTokens()


class PusherRecordBarrier:
    def __init__(self, uid: str):
        self.uid = uid
        self.record_upload_failed = False
        self.failed_recordings: set[str] = set()
        self.upload_sessions: dict[str, str] = {}
        self.checked_conversations: set[str] = set()
        self.pending_clears: set[tuple[str, str]] = set()
        self.close_failures: dict[str, int] = {}
        self.close_retry_at: dict[str, float] = {}
        self.keep_close_pending = False

    def _close_failed(self, conversation_id: str, stage: str) -> bool:
        _record_failure(stage)
        attempts = min(self.close_failures.get(conversation_id, 0) + 1, 6)
        if not self.keep_close_pending and (
            attempts >= CLOSE_RETRY_BUDGET
            or (conversation_id not in self.close_failures and len(self.close_failures) >= 128)
        ):
            self.retire_close(conversation_id)
            return True  # Stop this bounded drain; leave durable repair debt.
        self.close_failures[conversation_id] = attempts
        if self.keep_close_pending:
            ceiling = min(2.0**attempts, CLOSE_RETRY_MAX_SECONDS)
            self.close_retry_at[conversation_id] = time.monotonic() + random.uniform(ceiling / 2, ceiling)
        return False

    async def _close_metadata(self, conversation_id: str, fn: Callable[P, T], *args: P.args, **kwargs: P.kwargs) -> T:
        if not self.keep_close_pending:
            return await run_blocking(record_barrier_executor, fn, *args, **kwargs)
        slots = _close_retry_slots
        if not slots.acquire(blocking=False):
            raise ExecutorSaturatedError('record close retry capacity')
        if not _close_outstanding_slots.acquire(blocking=False):
            slots.release()
            RECORD_CLOSE_OUTSTANDING_REFUSALS.inc()
            raise ExecutorSaturatedError('record close outstanding capacity')
        admission = _CloseAdmission()
        context = contextvars.copy_context()

        def call() -> T:
            return context.run(fn, *args, **kwargs)

        try:
            future = record_barrier_executor.submit(call)
        except BaseException:
            slots.release()
            admission.outstanding_slots.release()
            raise
        future.add_done_callback(admission.completed)
        wrapped = asyncio.wrap_future(future)
        deadline = asyncio.get_running_loop().call_later(CLOSE_METADATA_DEADLINE_SECONDS, admission.abandon)

        def settled(done):
            deadline.cancel()
            if not done.cancelled():
                done.exception()  # Observe late errors even after caller cancellation/timeout.

        wrapped.add_done_callback(settled)
        # Unknown is neither failure proof nor success proof. Keep the token's
        # pending clear; its exact-token removal and transactional seal are
        # idempotent even if the original write succeeds after a retry.
        return await asyncio.wait_for(asyncio.shield(wrapped), timeout=CLOSE_METADATA_DEADLINE_SECONDS)

    def retire_close(self, conversation_id: str) -> None:
        """Forget scheduling state only; never change durable custody proof."""
        self.close_failures.pop(conversation_id, None)
        self.close_retry_at.pop(conversation_id, None)
        # Failed recordings remain fenced by failed_recordings/global failure;
        # they no longer need a second entry in begin's checked-set budget.
        self.checked_conversations.discard(conversation_id)

    async def begin_recording(self, conversation_id: str) -> None:
        if conversation_id in self.checked_conversations or conversation_id in self.failed_recordings:
            return
        if self.record_upload_failed or len(self.checked_conversations) + len(self.pending_clears) >= 128:
            _record_failure('capacity')
            await self.fail_recording(conversation_id)
            return
        self.checked_conversations.add(conversation_id)
        # Persist before accepting audio into a buffer: a concurrent empty
        # reconnect may not certify this session's uncommitted tail.
        try:
            token = uuid.uuid4().hex
            registry = _process_record_tokens()
            # Allocate before dispatch: registration responses can return in
            # the reverse order of producer minting.
            mint_order = registry.mint_order()
            if await run_blocking(
                record_barrier_executor,
                record_audio_db.set_record_upload_pending,
                self.uid,
                conversation_id,
                token,
                True,
                producer=producer_identity(),
            ):
                self.upload_sessions[conversation_id] = token
                registry.remember(self.uid, conversation_id, token, mint_order=mint_order)
        except record_audio_db.RecordUploadCapacityExceeded:
            _record_failure('capacity')
            await self.fail_recording(conversation_id)
        except Exception:
            # Metadata outages must not interrupt the audio custody lane.
            _record_failure('begin')
            await self.fail_recording(conversation_id)

    async def finish_recording(self, conversation_id: str) -> bool:
        """Return whether settled (or the legacy bounded retry budget exhausted).

        Durable drain owners set keep_close_pending so transient metadata
        failure never retires their only retry while this process is alive.
        """
        if self.record_upload_failed or conversation_id in self.failed_recordings:
            self.retire_close(conversation_id)
            return True  # A held tail is not a successful drain.
        if self.keep_close_pending and time.monotonic() < self.close_retry_at.get(conversation_id, 0):
            return False
        token = self.upload_sessions.get(conversation_id)
        registry = _process_record_tokens()
        if token is not None:
            # Only a later producer's successful drain certifies held tokens.
            # Empty reconnects and still-active overlapping sockets cannot.
            for earlier in registry.recoverable_before(self.uid, conversation_id, token):
                self.pending_clears.add((conversation_id, earlier))
            registry.ready(self.uid, conversation_id, token)
            self.pending_clears.add((conversation_id, token))
        self.checked_conversations.discard(conversation_id)
        try:
            for cid, token in list(self.pending_clears):
                if cid != conversation_id:
                    continue
                await self._close_metadata(
                    conversation_id,
                    record_audio_db.set_record_upload_pending,
                    self.uid,
                    conversation_id,
                    token,
                    False,
                )
                self.pending_clears.discard((conversation_id, token))
                registry.forget(self.uid, conversation_id, token)
                if self.upload_sessions.get(conversation_id) == token:
                    self.upload_sessions.pop(conversation_id, None)
                else:
                    logger.info('event=record_tokens_recleared count=1')
        except Exception:
            return self._close_failed(conversation_id, 'finish')
        try:
            refused = await self._close_metadata(
                conversation_id, record_audio_db.seal_record_audio, self.uid, conversation_id
            )
            if refused is not None:
                _SEAL_REFUSAL_COUNTERS[refused].inc()
                logger.info('event=record_seal_refused reason=%s', refused)
        except Exception:
            return self._close_failed(conversation_id, 'seal')
        self.retire_close(conversation_id)
        return True

    def hold_recording(self, conversation_id: str, *, tail_committed: bool = False) -> None:
        """Keep the token; only a proven durable tail may later be re-cleared."""
        token = self.upload_sessions.get(conversation_id)
        if token is not None:
            _process_record_tokens().ready(self.uid, conversation_id, token, committed=tail_committed)
        if len(self.failed_recordings) < 128:
            self.failed_recordings.add(conversation_id)
        else:
            self.record_upload_failed = True  # bounded fail-closed overflow, never forget a failed source

    async def fail_recording(self, conversation_id: str) -> None:
        self.hold_recording(conversation_id)
        # Terminal loss must not become recoverable if its durable failure
        # marker is unavailable. The persisted producer remains the fence.
        token = self.upload_sessions.get(conversation_id)
        if token is not None:
            _process_record_tokens().forget(self.uid, conversation_id, token)
        # Await the durable refusal when available, but never let its failure
        # terminate the audio uploader or discard its remaining ready lane.
        try:
            await run_blocking(
                record_barrier_executor, record_audio_db.mark_record_upload_failed, self.uid, conversation_id
            )
        except Exception:
            _record_failure('failure_marker')
