"""Durable conversation ownership and lifecycle for a live listen session."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from models.conversation import Conversation
from models.conversation_enums import ConversationSource, ConversationStatus
from models.message_event import ConversationEvent, ConversationSessionEvent, LastConversationEvent
from models.structured import Structured  # type: ignore[reportAttributeAccessIssue]
from utils.byok import get_byok_keys
from utils.cloud_tasks import is_listen_finalization_dispatch_enabled
from utils.conversations import lifecycle as lifecycle_service
from utils.conversations.factory import deserialize_conversation
from utils.conversations.process_conversation import retrieve_in_progress_conversation
from utils.transcribe_decisions import (
    ConversationLifecycleAction,
    RecordingSessionReconnectAction,
    decide_existing_conversation_action,
    decide_lifecycle_action,
    decide_recording_session_reconnect_action,
    recording_session_id_for_lifecycle_event,
    select_recording_session_id,
)
from utils.transcribe_store import calendar_db, conversations_db, redis_db

logger = logging.getLogger(__name__)

# Orphan threshold for stale in_progress recovery (#9809). Any live session
# refreshes finished_at continuously and its lifecycle loop processes an idle
# conversation within the ~2-minute conversation timeout, so an hour of silence
# proves no session owns the row — including one on another device.
STALE_IN_PROGRESS_RECOVERY_AGE_SECONDS = 3600
# Per-session recovery bound: spreads a large backlog across sessions instead of
# fanning dozens of LLM finalizations out of one reconnect.
STALE_IN_PROGRESS_RECOVERY_BATCH = 10


class LiveConversationController:
    """Own the recording-session to conversation mapping for one WebSocket."""

    def __init__(self, host: Any):
        self.host = host

    async def _recording_session_event(self, recording_session_id: str, conversation_id: str, phase: str):
        try:
            return await self.host.persistence.call(
                lifecycle_service.record_recording_session_event,
                self.host.request.uid,
                recording_session_id,
                conversation_id,
                phase,
            )
        except Exception:
            logger.exception(
                'recording session event persistence failed session=%s conversation=%s uid=%s',
                recording_session_id,
                conversation_id,
                self.host.request.uid,
            )
            return None

    def send_conversation_session(
        self, binding: dict[str, Any], recording_session_id: str, *, status: str = 'in_progress'
    ):
        self.host.send_event(
            ConversationSessionEvent(
                conversation_id=binding['conversation_id'],
                status=status,
                recording_session_id=recording_session_id,
                lifecycle_version=binding['lifecycle_version'],
                lifecycle_phase=binding['lifecycle_phase'],
                lifecycle_sequence=binding['lifecycle_sequence'],
            )
        )

    async def emit_recording_lifecycle_event(self, conversation_id: str, phase: str) -> None:
        recording_session_id = recording_session_id_for_lifecycle_event(
            self.host.recording_session_ids_by_conversation, conversation_id
        )
        if not recording_session_id:
            logger.warning('Suppressing lifecycle event without durable binding conversation=%s', conversation_id)
            return
        data = await self.host.persistence.call(
            conversations_db.get_conversation, self.host.request.uid, conversation_id
        )
        if not data:
            return
        envelope = await self._recording_session_event(recording_session_id, conversation_id, phase)
        if envelope is None:
            return
        self.host.send_event(
            ConversationEvent(
                event_type='memory_created' if phase == 'completed' else 'memory_processing_started',
                memory=deserialize_conversation(data),
                messages=[] if phase == 'completed' else None,
                recording_session_id=envelope['recording_session_id'],
                conversation_id=envelope['conversation_id'],
                lifecycle_version=envelope['lifecycle_version'],
                lifecycle_phase=envelope['lifecycle_phase'],
                lifecycle_sequence=envelope['lifecycle_sequence'],
            )
        )

    def on_conversation_processed(self, conversation_id: str) -> None:
        self.host.spawn(
            self.emit_recording_lifecycle_event(conversation_id, 'completed'), name='recording_session_completed'
        )

    def on_conversation_processing_started(self, conversation_id: str) -> None:
        self.host.spawn(
            self.emit_recording_lifecycle_event(conversation_id, 'processing'), name='recording_session_processing'
        )

    async def schedule_finalization(self, conversation_id: str) -> bool:
        if not self.host.request_conversation_processing and not is_listen_finalization_dispatch_enabled():
            logger.warning('Pusher unavailable; finalization remains queued conversation=%s', conversation_id)
            return False
        finalization = await self.host.persistence.call(
            lifecycle_service.request_finalization,
            self.host.request.uid,
            conversation_id,
            has_byok_keys=bool(get_byok_keys()),
        )
        route = finalization['route']
        if route == 'pusher':
            if not self.host.request_conversation_processing:
                return False
            await self.host.request_conversation_processing(
                conversation_id, finalization['job_id'], finalization['dispatch_generation']
            )
            self.on_conversation_processing_started(conversation_id)
            return True
        if route in {'cloud_tasks', 'queued', 'blocked_byok'}:
            self.on_conversation_processing_started(conversation_id)
            return True
        return route == 'noop'

    async def process_conversation(self, conversation_id: str) -> bool:
        data = await self.host.persistence.call(
            conversations_db.get_conversation, self.host.request.uid, conversation_id
        )
        if not data:
            return False
        if data.get('transcript_segments') or data.get('photos'):
            return await self.schedule_finalization(conversation_id)
        recording_session_id = recording_session_id_for_lifecycle_event(
            self.host.recording_session_ids_by_conversation, conversation_id
        )
        deleted = await self.host.persistence.call(
            lifecycle_service.delete_empty_recording_conversation,
            self.host.request.uid,
            conversation_id,
            recording_session_id,
        )
        if deleted:
            return True
        latest = await self.host.persistence.call(
            conversations_db.get_conversation, self.host.request.uid, conversation_id
        )
        return bool(
            latest and (latest.get('transcript_segments') or latest.get('has_content') or latest.get('photos'))
        ) and await self.schedule_finalization(conversation_id)

    async def create_new_in_progress_conversation(self, *, rollover: bool = False) -> None:
        request = self.host.request
        self.host.recording_session_id = select_recording_session_id(
            client_conversation_id=self.host.client_conversation_id,
            current_recording_session_id=self.host.recording_session_id,
            rollover=rollover,
            generated_id=str(uuid.uuid4()),
        )
        try:
            source = ConversationSource(request.source) if request.source else ConversationSource.omi
        except ValueError:
            logger.error('Invalid conversation source %s; using omi', request.source)
            source = ConversationSource.omi
        proposed_id = (
            self.host.client_conversation_id if self.host.client_conversation_id and not rollover else str(uuid.uuid4())
        )
        binding = await self.host.persistence.call(
            lifecycle_service.open_live_recording_session,
            request.uid,
            self.host.recording_session_id,
            proposed_id,
        )
        if binding['requires_rollover']:
            await self.create_new_in_progress_conversation(rollover=True)
            return
        conversation_id = binding['conversation_id']
        self.host.recording_session_ids_by_conversation[conversation_id] = self.host.recording_session_id
        existing = await self.host.persistence.call(conversations_db.get_conversation, request.uid, conversation_id)
        if existing:
            action = decide_recording_session_reconnect_action(
                status=existing.get('status'),
                discarded=bool(existing.get('discarded')),
                in_progress_status=ConversationStatus.in_progress,
            )
            if action == RecordingSessionReconnectAction.resume_current:
                self.host.state.current_conversation_id = conversation_id
                await self.host.persistence.call(redis_db.set_in_progress_conversation_id, request.uid, conversation_id)
                self.send_conversation_session(binding, self.host.recording_session_id)
                return
            if action == RecordingSessionReconnectAction.suppress_discarded_and_rollover:
                await self.create_new_in_progress_conversation(rollover=True)
                return
            self.send_conversation_session(binding, self.host.recording_session_id, status=str(existing.get('status')))
            if existing.get('status') == ConversationStatus.completed.value:
                self.on_conversation_processed(conversation_id)
            await self.create_new_in_progress_conversation(rollover=True)
            return

        context = self.host.client_device_context
        conversation = Conversation(
            id=conversation_id,
            created_at=datetime.now(timezone.utc),
            started_at=datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc),
            structured=Structured(),
            language=self.host.language,
            transcript_segments=[],
            photos=[],
            status=ConversationStatus.in_progress,
            source=source,
            private_cloud_sync_enabled=self.host.private_cloud_sync_enabled,
            call_id=request.call_id if self.host.is_multi_channel else None,
            client_device_id=context.client_device_id,
            client_platform=context.platform,
        )
        await self.host.persistence.call(
            lifecycle_service.create_in_progress_conversation,
            request.uid,
            conversation.model_dump(),
            idempotent=bool(self.host.client_conversation_id and conversation_id == self.host.client_conversation_id),
        )
        await self.host.persistence.call(redis_db.set_in_progress_conversation_id, request.uid, conversation_id)
        if source == ConversationSource.desktop:
            now = datetime.now(timezone.utc)
            meetings = await self.host.persistence.call(
                calendar_db.get_meetings_in_time_range,
                request.uid,
                now - timedelta(minutes=2),
                now + timedelta(minutes=2),
            )
            if meetings:
                closest = min(meetings, key=lambda meeting: abs((meeting['start_time'] - now).total_seconds()))
                await self.host.persistence.call(redis_db.set_conversation_meeting_id, conversation_id, closest['id'])
        self.host.state.current_conversation_id = conversation_id
        self.send_conversation_session(binding, self.host.recording_session_id)

    async def prepare(self) -> Optional[str]:
        if self.host.is_multi_channel:
            await self.create_new_in_progress_conversation()
            return None
        if self.host.client_conversation_id:
            await self.create_new_in_progress_conversation()
            return None
        existing = await self.host.persistence.call(retrieve_in_progress_conversation, self.host.request.uid)
        if not existing:
            await self.create_new_in_progress_conversation()
            return None
        finished_at = datetime.fromisoformat(existing['finished_at'].isoformat())
        seconds = (datetime.now(timezone.utc) - finished_at).total_seconds()
        if (
            decide_existing_conversation_action(
                seconds_since_last_segment=seconds,
                conversation_creation_timeout=self.host.conversation_creation_timeout,
            )
            == ConversationLifecycleAction.process_and_create_new
        ):
            await self.create_new_in_progress_conversation()
            return existing['id']
        binding = await self.host.persistence.call(
            lifecycle_service.open_live_recording_session,
            self.host.request.uid,
            self.host.recording_session_id,
            existing['id'],
        )
        if binding['requires_rollover']:
            await self.create_new_in_progress_conversation(rollover=True)
            return None
        self.host.state.current_conversation_id = existing['id']
        self.host.recording_session_ids_by_conversation[existing['id']] = self.host.recording_session_id
        self.send_conversation_session(binding, self.host.recording_session_id)
        return None

    async def process_pending(self, timed_out_id: Optional[str]) -> None:
        # Interruptible delay, not a polling loop. An early wake means the session is shutting
        # down, which is precisely when the timed-out conversation and anything still stuck in
        # `processing` must be finalized, so the wake shortens the wait instead of skipping the
        # work. Returning here dropped both (pre-split this was an unconditional sleep).
        await self.host.wait(7)
        if timed_out_id:
            await self.process_conversation(timed_out_id)
        processing = await self.host.persistence.call(
            conversations_db.get_processing_conversations, self.host.request.uid
        )
        for conversation in processing or []:
            await self.schedule_finalization(conversation['id'])
        await self.recover_stale_in_progress()

    async def recover_stale_in_progress(self) -> None:
        """Route orphaned `in_progress` conversations through normal finalization (#9809).

        Conversations from sessions that died without processing sit invisible in
        `in_progress` forever; the manual /finalize workaround proves their content
        is intact. `process_conversation` already makes the right call per row —
        content goes through the durable finalization seam, empty rows are
        deleted — so recovery is exactly the path a live timeout takes. Bounded
        and oldest-first so one session never stampedes the pipeline.
        """
        stale = await self.host.persistence.call(
            conversations_db.get_stale_in_progress_conversations,
            self.host.request.uid,
            older_than_seconds=STALE_IN_PROGRESS_RECOVERY_AGE_SECONDS,
            limit=STALE_IN_PROGRESS_RECOVERY_BATCH,
        )
        for conversation in stale or []:
            if conversation['id'] == self.host.state.current_conversation_id:
                continue
            logger.info(
                'recovering stale in_progress conversation uid=%s conversation=%s finished_at=%s',
                self.host.request.uid,
                conversation['id'],
                conversation.get('finished_at'),
            )
            await self.process_conversation(conversation['id'])

    async def lifecycle_loop(self) -> None:
        while self.host.state.active:
            if await self.host.wait(5):
                break
            conversation_id = self.host.state.current_conversation_id
            if not conversation_id:
                continue
            conversation = await self.host.persistence.call(
                conversations_db.get_conversation, self.host.request.uid, conversation_id
            )
            if not conversation:
                await self.create_new_in_progress_conversation(rollover=True)
                continue
            finished_at = datetime.fromisoformat(conversation['finished_at'].isoformat())
            action = decide_lifecycle_action(
                conversation_exists=True,
                status=conversation.get('status'),
                in_progress_status=ConversationStatus.in_progress,
                seconds_since_last_update=(datetime.now(timezone.utc) - finished_at).total_seconds(),
                conversation_creation_timeout=self.host.conversation_creation_timeout,
            )
            if action == ConversationLifecycleAction.create_new:
                await self.create_new_in_progress_conversation(rollover=True)
            elif action == ConversationLifecycleAction.process_and_create_new:
                await self.host.transcripts.flush_speaker_assignments(conversation_id)
                await self.process_conversation(conversation_id)
                await self.create_new_in_progress_conversation(rollover=True)

    async def send_last_conversation(self) -> None:
        last = await self.host.persistence.call(conversations_db.get_last_completed_conversation, self.host.request.uid)
        if last:
            self.host.send_event(LastConversationEvent(memory_id=last['id']))
