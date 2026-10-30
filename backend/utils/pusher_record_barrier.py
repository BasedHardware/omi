"""Session-local drain state backed by persistent capture-level custody."""

import uuid
import os
import time
from functools import lru_cache
from pathlib import Path
from prometheus_client import Counter

from database import record_audio as record_audio_db
from utils.executors import db_executor, run_blocking

RECORD_BARRIER_FAILURES = Counter(
    'omi_pusher_record_barrier_failures_total', 'Record barrier metadata failures; audio upload continues', ['stage']
)
for _stage in ('begin', 'finish', 'seal', 'failure_marker', 'capacity'):
    RECORD_BARRIER_FAILURES.labels(stage=_stage).inc(0)


def _record_failure(stage):
    RECORD_BARRIER_FAILURES.labels(stage=stage).inc()


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
                db_executor,
                record_audio_db.set_record_upload_pending,
                self.uid,
                conversation_id,
                token,
                True,
                producer=producer_identity(),
            ):
                self.upload_sessions[conversation_id] = token
        except Exception:
            # Metadata outages must not interrupt the audio custody lane.
            _record_failure('begin')
            await self.fail_recording(conversation_id)

    async def finish_recording(self, conversation_id: str) -> None:
        token = self.upload_sessions.get(conversation_id)
        if token is not None:
            self.pending_clears.add((conversation_id, token))
        self.checked_conversations.discard(conversation_id)
        try:
            for cid, token in list(self.pending_clears):
                if cid != conversation_id:
                    continue
                await run_blocking(
                    db_executor, record_audio_db.set_record_upload_pending, self.uid, conversation_id, token, False
                )
                self.pending_clears.discard((conversation_id, token))
                if self.upload_sessions.get(conversation_id) == token:
                    self.upload_sessions.pop(conversation_id, None)
        except Exception:
            _record_failure('finish')
            return
        try:
            await run_blocking(db_executor, record_audio_db.seal_record_audio, self.uid, conversation_id)
        except Exception:
            _record_failure('seal')

    async def fail_recording(self, conversation_id: str) -> None:
        if len(self.failed_recordings) < 128:
            self.failed_recordings.add(conversation_id)
        else:
            self.record_upload_failed = True  # bounded fail-closed overflow, never forget a failed source
        # Await the durable refusal when available, but never let its failure
        # terminate the audio uploader or discard its remaining ready lane.
        try:
            await run_blocking(db_executor, record_audio_db.mark_record_upload_failed, self.uid, conversation_id)
        except Exception:
            _record_failure('failure_marker')
