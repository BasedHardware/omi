"""Session-local drain state backed by persistent capture-level custody."""

import uuid
import os
import time
import logging
from functools import lru_cache
from pathlib import Path
from prometheus_client import Counter

from database import record_audio as record_audio_db
from utils.executors import record_barrier_executor, run_blocking
from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)
CLOSE_RETRY_BUDGET = 3

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


class PusherRecordBarrier:
    def __init__(self, uid: str):
        self.uid = uid
        self.record_upload_failed = False
        self.failed_recordings: set[str] = set()
        self.upload_sessions: dict[str, str] = {}
        self.checked_conversations: set[str] = set()
        self.pending_clears: set[tuple[str, str]] = set()
        self.close_failures: dict[str, int] = {}

    def _close_failed(self, conversation_id: str, stage: str) -> bool:
        _record_failure(stage)
        attempts = self.close_failures.get(conversation_id, 0) + 1
        if attempts >= CLOSE_RETRY_BUDGET or (
            conversation_id not in self.close_failures and len(self.close_failures) >= 128
        ):
            self.close_failures.pop(conversation_id, None)
            return True  # Stop this bounded drain; leave durable repair debt.
        self.close_failures[conversation_id] = attempts
        return False

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
        except record_audio_db.RecordUploadCapacityExceeded:
            _record_failure('capacity')
            await self.fail_recording(conversation_id)
        except Exception:
            # Metadata outages must not interrupt the audio custody lane.
            _record_failure('begin')
            await self.fail_recording(conversation_id)

    async def finish_recording(self, conversation_id: str) -> bool:
        """Return whether this close is settled or its retry budget exhausted."""
        token = self.upload_sessions.get(conversation_id)
        if token is not None:
            self.pending_clears.add((conversation_id, token))
        self.checked_conversations.discard(conversation_id)
        try:
            for cid, token in list(self.pending_clears):
                if cid != conversation_id:
                    continue
                await run_blocking(
                    record_barrier_executor,
                    record_audio_db.set_record_upload_pending,
                    self.uid,
                    conversation_id,
                    token,
                    False,
                )
                self.pending_clears.discard((conversation_id, token))
                if self.upload_sessions.get(conversation_id) == token:
                    self.upload_sessions.pop(conversation_id, None)
        except Exception:
            return self._close_failed(conversation_id, 'finish')
        try:
            refused = await run_blocking(
                record_barrier_executor, record_audio_db.seal_record_audio, self.uid, conversation_id
            )
            if refused is not None:
                _SEAL_REFUSAL_COUNTERS[refused].inc()
                logger.info('event=record_seal_refused reason=%s', refused)
        except Exception:
            return self._close_failed(conversation_id, 'seal')
        self.close_failures.pop(conversation_id, None)
        return True

    def hold_recording(self, conversation_id: str) -> None:
        """Keep this socket's token without asserting permanent custody loss."""
        if len(self.failed_recordings) < 128:
            self.failed_recordings.add(conversation_id)
        else:
            self.record_upload_failed = True  # bounded fail-closed overflow, never forget a failed source

    async def fail_recording(self, conversation_id: str) -> None:
        self.hold_recording(conversation_id)
        # Await the durable refusal when available, but never let its failure
        # terminate the audio uploader or discard its remaining ready lane.
        try:
            await run_blocking(
                record_barrier_executor, record_audio_db.mark_record_upload_failed, self.uid, conversation_id
            )
        except Exception:
            _record_failure('failure_marker')
