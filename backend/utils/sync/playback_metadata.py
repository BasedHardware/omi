"""Bound metadata repair to one playback open; never build audio in the drain."""

from collections import OrderedDict, deque
from concurrent.futures import Future, TimeoutError
import threading
import time

from fastapi import HTTPException

from utils.executors import playback_metadata_executor, submit_with_context, ExecutorSaturatedError

OPEN_TIMEOUT_SECONDS = 8.0
MAX_ACTIVE = 2
MAX_USER_ACTIVE = 1
ATTEMPT_WINDOW_SECONDS = 60.0
MAX_USER_ATTEMPTS = 4
MAX_PROCESS_ATTEMPTS = 32
COOLDOWN_SECONDS = 30.0
MAX_HISTORY = 1024


class MetadataPending(TimeoutError):
    def __init__(self, reason: str):
        super().__init__('Playback metadata pending')
        self.reason = reason


class DemandCoordinator:
    """Bound single-flight, retries and negative history across request threads."""

    def __init__(self):
        self.lock = threading.RLock()
        self.active: dict[tuple[str, str], Future] = {}
        self.cooldown: OrderedDict[tuple[str, str], tuple[float, int | None]] = OrderedDict()
        self.attempts: deque[tuple[float, str]] = deque()

    def get(self, uid: str, cid: str) -> Future:
        key, now = (uid, cid), time.monotonic()
        with self.lock:
            while self.attempts and self.attempts[0][0] <= now - ATTEMPT_WINDOW_SECONDS:
                self.attempts.popleft()
            while self.cooldown and next(iter(self.cooldown.values()))[0] <= now:
                self.cooldown.popitem(last=False)
            if key in self.active:
                return self.active[key]
            if key in self.cooldown:
                _, status = self.cooldown[key]
                if status is not None:
                    raise HTTPException(status, 'Playback metadata access refused')
                raise MetadataPending('circuit_open')
            if (
                len(self.active) >= MAX_ACTIVE
                or sum(owner == uid for owner, _ in self.active) >= MAX_USER_ACTIVE
                or sum(owner == uid for _, owner in self.attempts) >= MAX_USER_ATTEMPTS
                or len(self.attempts) >= MAX_PROCESS_ATTEMPTS
                or len(self.cooldown) + len(self.active) >= MAX_HISTORY
            ):
                raise MetadataPending('capacity_full')
            self.attempts.append((now, uid))
            try:
                future = submit_with_context(playback_metadata_executor, _refresh_safely, uid, cid)
            except ExecutorSaturatedError:
                self.cooldown[key] = now + COOLDOWN_SECONDS, None
                raise MetadataPending('capacity_full') from None
            self.active[key] = future
            future.add_done_callback(lambda done: self.complete(key, done))
            return future

    def complete(self, key: tuple[str, str], future: Future) -> None:
        with self.lock:
            if self.active.get(key) is not future:
                return
            self.active.pop(key)
            try:
                row = future.result()
            except HTTPException as error:
                status = error.status_code if error.status_code in {402, 404} else None
            except Exception:
                status = None
            else:
                if row.get('audio_files'):
                    return
                status = None
            self.cooldown[key] = time.monotonic() + COOLDOWN_SECONDS, status


_coordinator = DemandCoordinator()


def _refresh(uid: str, cid: str):
    from database import conversations, record_projection_rebuild as debt
    from utils.batch_pipeline.record_projection_rebuild import rebuild

    version = debt.pending_version(uid, cid)
    # Reuse cold repair's strict discovery, deletion/privacy transaction and CAS.
    # This is metadata only. Existing /urls demand handling builds real artifacts.
    if version is not None and not debt.preflight_projection(uid, cid):
        raise HTTPException(404, 'Conversation not found')
    applied = rebuild(uid, cid) if version is not None else None
    if applied is False:
        raise HTTPException(404, 'Conversation not found')
    row = conversations.get_conversation_raw_snapshot(
        uid, cid, field_paths=['audio_files', 'deleted', 'is_locked'], timeout=1
    )
    if row is None or row.get('deleted'):
        raise HTTPException(404, 'Conversation not found')
    if row.get('is_locked'):
        raise HTTPException(402, 'A paid plan is required to access this conversation.')
    # A background refresh may publish and retire debt after the route's first
    # empty read. Always read back metadata, even if its marker is already gone.
    if not row.get('audio_files') and version is not None:
        raise MetadataPending('input_missing' if applied == 'no_objects' else 'unavailable')
    if applied is True:
        try:
            debt.retire_observed(uid, cid, observed_update_time=version)
        except Exception:
            from utils.observability.fallback import record_fallback

            record_fallback(
                component='audio_merge',
                from_mode='playback_metadata_debt',
                to_mode='durable_repair',
                reason='other',
                outcome='degraded',
            )
    # Incomplete or empty discovery retains debt. Newer marker versions always
    # survive the conditional delete; neither result has producer-token authority.
    return row


def _refresh_safely(uid: str, cid: str):
    try:
        return _refresh(uid, cid)
    except (HTTPException, MetadataPending):
        raise
    except Exception:
        # The Future's shared callback must not log private SDK payloads.
        raise HTTPException(503, 'Playback metadata repair is unavailable') from None


def refresh_on_open(uid: str, cid: str):
    """Request budget bounds the wait; two workers/zero queue bound late work."""
    future = _coordinator.get(uid, cid)
    try:
        return future.result(timeout=OPEN_TIMEOUT_SECONDS)
    except MetadataPending:
        raise
    except TimeoutError:
        # Cancellation can stop an unstarted task only. A running leaf retains
        # its single-flight/user/process slot until completion, never a queue.
        future.cancel()
        raise MetadataPending('timeout') from None
    except HTTPException as error:
        if error.status_code in {402, 404}:
            raise
        raise MetadataPending('unavailable') from None
    except Exception:
        raise MetadataPending('unavailable') from None
