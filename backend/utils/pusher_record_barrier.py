"""Session-local drain state backed by persistent capture-level custody."""

import uuid

from database import record_audio as record_audio_db
from utils.executors import db_executor, run_blocking


class PusherRecordBarrier:
    def __init__(self, uid: str):
        self.uid = uid
        self.record_upload_failed = False
        self.failed_recordings: set[str] = set()
        self.upload_sessions: dict[str, str] = {}

    async def begin_recording(self, conversation_id: str) -> None:
        if conversation_id in self.upload_sessions:
            return
        if len(self.upload_sessions) >= 128:
            raise ValueError('record upload session budget exceeded')
        token = uuid.uuid4().hex
        # Persist before accepting audio into a buffer: a concurrent empty
        # reconnect may not certify this session's uncommitted tail.
        if await run_blocking(
            db_executor, record_audio_db.set_record_upload_pending, self.uid, conversation_id, token, True
        ):
            self.upload_sessions[conversation_id] = token

    async def finish_recording(self, conversation_id: str) -> None:
        token = self.upload_sessions.pop(conversation_id, None)
        if token is not None:
            await run_blocking(
                db_executor, record_audio_db.set_record_upload_pending, self.uid, conversation_id, token, False
            )
        await run_blocking(db_executor, record_audio_db.seal_record_audio, self.uid, conversation_id)

    async def fail_recording(self, conversation_id: str) -> None:
        if len(self.failed_recordings) < 128:
            self.failed_recordings.add(conversation_id)
        else:
            self.record_upload_failed = True  # bounded fail-closed overflow, never forget a failed source
        # No fire-and-forget write: reconnects must observe this refusal.
        await run_blocking(db_executor, record_audio_db.mark_record_upload_failed, self.uid, conversation_id)
