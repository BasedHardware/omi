"""Durable conversation ownership and lifecycle for a live listen session."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Optional

from config.sync_lineage import sync_lineage_resolve_enabled
from database.firestore_read_metrics import FirestoreReadSite
from models.conversation import Conversation
from models.conversation_enums import ConversationSource, ConversationStatus
from models.message_event import ConversationEvent, ConversationSessionEvent, LastConversationEvent
from models.structured import Structured  # type: ignore[reportAttributeAccessIssue]
from routers.listen.contracts import ConversationCaptureOrigin, persisted_started_seconds
from utils.byok import get_byok_keys
from utils.cloud_tasks import is_listen_finalization_dispatch_enabled
from utils.live_speaker_carry import carried_receipt
from utils.observability.fallback import record_fallback
from utils.observability.transcription import record_listen_audio_outcome
from utils.conversations import lifecycle as lifecycle_service
from utils.conversations.live_continuation import resolve_live_continuation
from database.listen_continuations import calendar_continuity_row
from utils.conversation_continuity import calendar_continuity_identity, continuation_timeout, resumable_continuation
from utils.conversations.factory import deserialize_conversation
from utils.conversations.finalization_failure import classify_finalization_failure
from utils.conversations.projection_payload import omit_null_processing_state
from utils.conversations.process_conversation import retrieve_in_progress_conversation
from utils.transcribe_decisions import (
    ConversationLifecycleAction,
    RecordingSessionReconnectAction,
    decide_existing_conversation_action,
    decide_lifecycle_action,
    normalize_listen_source,
    decide_recording_session_reconnect_action,
    recording_session_id_for_lifecycle_event,
    select_recording_session_id,
    should_attach_to_existing_in_progress,
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
RECORDING_SESSION_LEASE_RENEW_INTERVAL = timedelta(minutes=1)


def resolve_onboarding_provenance_marker(host: Any) -> Optional[str]:
    """The onboarding-provenance marker consumed by the daily memory sweep
    (utils/memory/daily_memory_sweep.py) must reflect the runtime's own
    onboarding-admission decision (``host.onboarding_session_id``), not
    ``OnboardingHandler.session_id``: the handler mints its own fallback id
    whenever none is supplied (utils/onboarding.py), so a Settings speech-
    profile redo — which runs the same question handler but intentionally
    clears the runtime's admission id — must not be re-tagged as onboarding
    provenance just because the handler picked an id for itself.
    """
    session_id = getattr(host, 'onboarding_session_id', None)
    return session_id if isinstance(session_id, str) and len(session_id) >= 16 else None


class LiveConversationController:
    """Own the recording-session to conversation mapping for one WebSocket."""

    def __init__(self, host: Any, *, clock: Callable[[], datetime] | None = None) -> None:
        self.host = host
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self._last_recording_session_lease_renewal: datetime | None = None

    def note_audio_activity(self) -> None:
        """Renew the active recording fence at most once per minute."""
        conversation_id = self.host.state.current_conversation_id
        recording_session_id = self.host.recording_session_id
        if not conversation_id or not recording_session_id:
            return
        now = self.clock()
        last = self._last_recording_session_lease_renewal
        if last is not None and now - last < RECORDING_SESSION_LEASE_RENEW_INTERVAL:
            return
        self._last_recording_session_lease_renewal = now
        self.host.spawn(
            self.host.persistence.call(
                lifecycle_service.renew_live_recording_session_lease,
                self.host.request.uid,
                recording_session_id,
                conversation_id,
            ),
            name='recording_session_lease_renewal',
        )

    async def _continuity_row(self, row: dict[str, Any]) -> dict[str, Any]:
        if calendar_continuity_identity(row) is None:
            return row
        return dict(await self.host.persistence.call(calendar_continuity_row, self.host.request.uid, row))

    async def _continuation(self, proposed: dict[str, str] | None = None) -> dict[str, str] | None:
        if not self.host.client_conversation_id or self.host.is_multi_channel:
            return None
        return await self.host.persistence.call(
            resolve_live_continuation,
            self.host.request.uid,
            self.host.client_conversation_id,
            source=normalize_listen_source(self.host.request.source),
            device_id=self.host.client_device_context.client_device_id,
            now=self.clock(),
            timeout=self.host.conversation_creation_timeout,
            proposed=proposed,
        )

    async def _resume_continuation(self, pointer: dict[str, str]) -> bool:
        binding = await self.host.persistence.call(
            lifecycle_service.open_live_recording_session,
            self.host.request.uid,
            pointer['recording_session_id'],
            pointer['conversation_id'],
        )
        if binding['requires_rollover']:
            return False
        existing = binding.get('conversation_snapshot')
        if existing is None:
            existing = await self.host.persistence.call(
                conversations_db.get_conversation,
                self.host.request.uid,
                binding['conversation_id'],
                read_site=FirestoreReadSite.LISTEN_CLIENT_ID_PROBE,
            )
        if existing:
            existing = await self._continuity_row(existing)
        if not existing or not resumable_continuation(
            existing,
            source=normalize_listen_source(self.host.request.source),
            device_id=self.host.client_device_context.client_device_id,
            now=self.clock(),
            timeout=self.host.conversation_creation_timeout,
        ):
            return False
        self.host.recording_session_id = pointer['recording_session_id']
        self.host.state.current_conversation_id = binding['conversation_id']
        self.host.recording_session_ids_by_conversation[binding['conversation_id']] = self.host.recording_session_id
        self._adopt_capture_timeline(binding['conversation_id'], (existing or {}).get('started_at'))
        if self.host.use_custom_stt and not existing.get('uses_custom_stt', False):
            await self.host.persistence.call(
                conversations_db.update_conversation,
                self.host.request.uid,
                binding['conversation_id'],
                {'uses_custom_stt': True},
            )
        await self.host.persistence.call(
            redis_db.set_in_progress_conversation_id, self.host.request.uid, binding['conversation_id']
        )
        await self.host.speakers.refresh_for_conversation(binding['conversation_id'])
        self.send_conversation_session(binding, self.host.recording_session_id)
        return True

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
            conversations_db.get_conversation,
            self.host.request.uid,
            conversation_id,
            read_site=FirestoreReadSite.LISTEN_RECORDING_LIFECYCLE_EVENT,
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

    def _adopt_capture_timeline(self, conversation_id: str, started_at: Any) -> None:
        """Track the audio-timeline v2 origin for a conversation this session owns.

        A resumed conversation reuses its persisted ``started_at`` as the
        projection origin; that row is never admitted as v2 — the adopted
        origin carries ``pinnable=False`` so no later batch pins the v2 marker
        or rewrites ``started_at`` on it. A conversation created fresh by this
        session waits for its first accepted audio frame, which the receiver
        pins as the (pinnable) origin. A ``started_at`` that cannot be parsed
        (datetime, number, or ISO string) locks the row to legacy projection:
        it never falls through to a fresh pin.
        """
        state = getattr(self.host, 'state', None)
        if state is None or getattr(state, 'capture_timeline', None) is None:
            return
        if started_at is None:
            state.conversations_awaiting_capture_origin.add(conversation_id)
            return
        timestamp = persisted_started_seconds(started_at)
        if timestamp is None:
            state.conversations_legacy_locked.add(conversation_id)
            return
        state.conversation_capture_origins[conversation_id] = ConversationCaptureOrigin(timestamp, pinnable=False)

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
            client_kind=self.host.client_kind,
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

    def _should_report_no_audio_teardown(self) -> bool:
        """Multi-channel session (phone calls today) that never sent a first audio byte."""

        return bool(
            getattr(self.host, 'is_multi_channel', False)
            and getattr(self.host.state, 'first_audio_byte_timestamp', None) is None
        )

    async def process_conversation(self, conversation_id: str) -> bool:
        data = await self.host.persistence.call(
            conversations_db.get_conversation,
            self.host.request.uid,
            conversation_id,
            read_site=FirestoreReadSite.LISTEN_PROCESS_CONVERSATION,
        )
        if not data:
            return False
        if data.get('transcript_segments') or data.get('photos'):
            return await self.schedule_finalization(conversation_id)
        recording_session_id = recording_session_id_for_lifecycle_event(
            self.host.recording_session_ids_by_conversation, conversation_id
        )
        # Snapshot before the fenced delete: the outcome is only truthful if the
        # delete actually wins the race to content, so emit after `deleted`.
        was_no_audio_session = self._should_report_no_audio_teardown()
        deleted = await self.host.persistence.call(
            lifecycle_service.delete_empty_recording_conversation,
            self.host.request.uid,
            conversation_id,
            recording_session_id,
        )
        if deleted:
            if was_no_audio_session:
                # A phone_call that stayed silent for its whole duration must be
                # distinguishable from a call that was never transcribed at all;
                # the empty-conversation deletion itself is unchanged.
                logger.warning(
                    'Listen session tore down with no audio received source=%s platform=%s',
                    self.host.request.source,
                    self.host.client_device_context.platform,
                )
                record_listen_audio_outcome(
                    source=self.host.request.source,
                    outcome='no_audio_teardown',
                    platform=self.host.client_device_context.platform,
                )
            return True
        latest = await self.host.persistence.call(
            conversations_db.get_conversation,
            self.host.request.uid,
            conversation_id,
            read_site=FirestoreReadSite.LISTEN_POST_DELETE_REREAD,
        )
        return bool(
            latest and (latest.get('transcript_segments') or latest.get('has_content') or latest.get('photos'))
        ) and await self.schedule_finalization(conversation_id)

    def _active_speaker_scope(self) -> Optional[str]:
        epoch = getattr(getattr(self.host, 'receiver', None), 'speaker_provider_epoch', None)
        return getattr(epoch, 'current_scope', None)

    async def _active_calendar_meeting(self) -> dict[str, Any] | None:
        now = self.clock()
        try:
            meetings = await self.host.persistence.call(
                calendar_db.get_meetings_in_time_range,
                self.host.request.uid,
                now - timedelta(minutes=2),
                now + timedelta(minutes=2),
            )
            candidates = []
            for meeting in meetings or []:
                if meeting.get('calendar_source') == 'screen_activity':
                    continue
                start = persisted_started_seconds(meeting.get('start_time'))
                end = persisted_started_seconds(meeting.get('end_time'))
                duration = meeting.get('duration_minutes')
                if (
                    end is None
                    and start is not None
                    and isinstance(duration, (int, float))
                    and not isinstance(duration, bool)
                ):
                    end = start + duration * 60
                if meeting.get('id') and start is not None and end is not None and start <= now.timestamp() < end:
                    candidates.append((start, meeting))
            return max(candidates, key=lambda item: item[0])[1] if candidates else None
        except Exception as error:
            logger.warning('Live calendar lookup unavailable exception_type=%s', type(error).__name__)
            record_fallback(
                component='other',
                from_mode='calendar_continuity',
                to_mode='silence_boundary',
                reason='other',
                outcome='degraded',
                log=logger,
            )
            return None

    async def create_new_in_progress_conversation(self, *, rollover: bool = False) -> None:
        request = self.host.request
        carry_from: Optional[tuple[str, str]] = None
        if rollover:
            previous_id = self.host.state.current_conversation_id
            active_scope = self._active_speaker_scope()
            if previous_id and active_scope:
                carry_from = (previous_id, active_scope)
            continuation = await self._continuation()
            if continuation and await self._resume_continuation(continuation):
                return
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
        use_client_conversation_id = bool(self.host.client_conversation_id) and not rollover
        proposed_id = self.host.client_conversation_id if use_client_conversation_id else str(uuid.uuid4())
        proposed_id_is_server_generated = not use_client_conversation_id
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
        if proposed_id_is_server_generated and conversation_id == proposed_id:
            # proposed_id was invented for this call and the binding adopted it
            # verbatim, so no conversation document can exist under it yet: a
            # lookup here is a guaranteed NOT_FOUND read. Client-supplied ids
            # always still get looked up below, since they can legitimately
            # name an existing conversation (resume/idempotency).
            existing = None
        elif binding.get('conversation_snapshot_known'):
            # open_live_recording_session already read this exact document while
            # resolving the binding; reuse it instead of reading it again.
            existing = binding['conversation_snapshot']
        else:
            existing = await self.host.persistence.call(
                conversations_db.get_conversation,
                request.uid,
                conversation_id,
                read_site=FirestoreReadSite.LISTEN_CLIENT_ID_PROBE,
            )
        if existing:
            existing = await self._continuity_row(existing)
            action = decide_recording_session_reconnect_action(
                status=existing.get('status'),
                discarded=bool(existing.get('discarded')),
                in_progress_status=ConversationStatus.in_progress,
            )
            if action == RecordingSessionReconnectAction.resume_current and not existing.get('deleted'):
                if not self.host.is_multi_channel and not resumable_continuation(
                    existing,
                    source=normalize_listen_source(request.source),
                    device_id=self.host.client_device_context.client_device_id,
                    now=self.clock(),
                    timeout=self.host.conversation_creation_timeout,
                ):
                    if (
                        existing.get('source') == normalize_listen_source(request.source)
                        and existing.get('client_device_id') == self.host.client_device_context.client_device_id
                        and not any(
                            existing.get(key) for key in ('transcript_segments', 'photos', 'has_content', 'is_locked')
                        )
                    ):
                        await self.process_conversation(conversation_id)
                    await self.create_new_in_progress_conversation(rollover=True)
                    return
                self.host.state.current_conversation_id = conversation_id
                self._adopt_capture_timeline(conversation_id, existing.get('started_at'))
                # Persist the custom-STT marker on resume so a conversation that
                # started under normal STT but continues under custom STT keeps
                # accurate provenance: once any session was custom-STT, the
                # conversation is marked as such.
                if self.host.use_custom_stt and not existing.get('uses_custom_stt', False):
                    await self.host.persistence.call(
                        conversations_db.update_conversation,
                        request.uid,
                        conversation_id,
                        {'uses_custom_stt': True},
                    )
                await self.host.persistence.call(redis_db.set_in_progress_conversation_id, request.uid, conversation_id)
                await self.host.speakers.refresh_for_conversation(conversation_id)
                self.send_conversation_session(binding, self.host.recording_session_id)
                return
            if existing.get('deleted') or action == RecordingSessionReconnectAction.suppress_discarded_and_rollover:
                await self.create_new_in_progress_conversation(rollover=True)
                return
            self.send_conversation_session(binding, self.host.recording_session_id, status=str(existing.get('status')))
            if existing.get('status') == ConversationStatus.completed.value:
                self.on_conversation_processed(conversation_id)
            await self.create_new_in_progress_conversation(rollover=True)
            return

        context = self.host.client_device_context
        external_data: dict[str, Any] = {
            'conversation_role': request.conversation_role,
            'recording_session_id': self.host.recording_session_id,
        }
        if self.host.client_conversation_id and sync_lineage_resolve_enabled():
            # Every rollover generation names the client's recording, which the
            # phone also stamps on its WALs, so sync can find them all.
            external_data['recording_origin_id'] = self.host.client_conversation_id
        if getattr(request, 'screen_evidence_pass', False):
            external_data['screen_evidence_pass'] = True
        onboarding_session_id = resolve_onboarding_provenance_marker(self.host)
        if onboarding_session_id:
            # This marker reflects the backend's own onboarding-admission
            # decision; request.source and request.onboarding_mode are client
            # input and are intentionally not used as provenance.
            external_data['onboarding_session_id'] = onboarding_session_id
        meeting = await self._active_calendar_meeting()
        if meeting and meeting.get('calendar_event_id') and meeting['calendar_event_id'] != 'screen-activity':
            external_data['calendar_meeting_context'] = {
                key: meeting[key]
                for key in ('calendar_event_id', 'calendar_source', 'start_time', 'end_time', 'duration_minutes')
                if key in meeting
            }
            # Finalization parses the stamp as CalendarMeetingContext even when
            # its window means continuity hydration has nothing left to fetch.
            external_data['calendar_meeting_context']['title'] = meeting.get('title') or ''
        conversation = Conversation(
            id=conversation_id,
            created_at=self.clock(),
            started_at=self.clock(),
            finished_at=self.clock(),
            structured=Structured(),
            language=self.host.language,
            transcript_segments=[],
            photos=[],
            status=ConversationStatus.in_progress,
            source=source,
            private_cloud_sync_enabled=self.host.private_cloud_sync_enabled,
            uses_custom_stt=self.host.use_custom_stt,
            call_id=request.call_id if self.host.is_multi_channel else None,
            client_device_id=context.client_device_id,
            client_platform=context.platform,
            external_data=external_data,
            geolocation=request.geolocation,
        )
        carry = {}
        if carry_from:
            try:
                previous = await self.host.persistence.call(
                    conversations_db.get_conversation,
                    request.uid,
                    carry_from[0],
                    read_site=FirestoreReadSite.LISTEN_CLIENT_ID_PROBE,
                )
            except Exception as error:
                logger.warning('Speaker carry lookup failed type=%s', type(error).__name__)
                previous = None
            if (
                previous
                and not previous.get('deleted')
                and not previous.get('discarded')
                and not previous.get('is_locked')
                and self._active_speaker_scope() == carry_from[1]
            ):
                carry = carried_receipt(previous, carry_from[1])
        # The modeled field's None default is omitted, never stamped:
        # persist is merge=True, so a dumped None would become an
        # explicit Firestore key on every fresh recording.
        payload = omit_null_processing_state(conversation.model_dump())
        if carry:
            payload['manual_speaker_assignments'] = carry
        await self.host.persistence.call(
            lifecycle_service.create_in_progress_conversation,
            request.uid,
            payload,
            idempotent=bool(self.host.client_conversation_id and conversation_id == self.host.client_conversation_id),
        )
        if rollover:
            proposed = {'conversation_id': conversation_id, 'recording_session_id': self.host.recording_session_id}
            adopted = await self._continuation(proposed)
            if adopted and adopted != proposed and await self._resume_continuation(adopted):
                # The winner is revalidated before deleting our unexposed loser.
                # A racing content write or lock still defeats deletion.
                await self.host.persistence.call(
                    lifecycle_service.delete_empty_recording_conversation,
                    request.uid,
                    proposed['conversation_id'],
                    proposed['recording_session_id'],
                )
                return
        await self.host.persistence.call(redis_db.set_in_progress_conversation_id, request.uid, conversation_id)
        if source == ConversationSource.desktop and meeting:
            await self.host.persistence.call(redis_db.set_conversation_meeting_id, conversation_id, meeting['id'])
        self.host.state.current_conversation_id = conversation_id
        # Fresh v2 generation: the origin is pinned by the receiver at the
        # first accepted audio frame associated with this conversation.
        self._adopt_capture_timeline(conversation_id, None)
        if rollover:
            carried_ids: set[int] = set()
            for key in carry.get('speakers') or {}:
                try:
                    carried_ids.add(int(key))
                except (TypeError, ValueError):
                    continue
            note_carry = getattr(self.host.speakers, 'note_rollover_carry', None)
            if note_carry is not None:
                note_carry(carried_ids)
        await self.host.speakers.refresh_for_conversation(conversation_id)
        self.send_conversation_session(binding, self.host.recording_session_id)

    async def prepare(self) -> Optional[str]:
        if self.host.is_multi_channel:
            await self.create_new_in_progress_conversation()
            return None
        if self.host.client_conversation_id:
            await self.create_new_in_progress_conversation()
            return None
        if self.host.request.onboarding_mode and self.host.onboarding_admitted:
            # A speech-profile recording (onboarding step or Settings redo) is its
            # own conversation. Attaching to a still-open one from a previous
            # attempt makes combine_segments() merge the new speech into that
            # conversation's last segment, and the client then shows the words
            # from last time as soon as the user starts talking again.
            # Admission, not the raw request flag, owns this decision: the
            # runtime refuses onboarding provenance for completed accounts, and
            # an unadmitted onboarding claim must keep the ordinary session's
            # existing-conversation behavior instead of dodging it.
            await self.create_new_in_progress_conversation()
            return None
        existing = await self.host.persistence.call(retrieve_in_progress_conversation, self.host.request.uid)
        if not existing:
            await self.create_new_in_progress_conversation()
            return None
        existing_source = existing.get('source')
        if hasattr(existing_source, 'value'):
            existing_source = existing_source.value
        # Cross-source sockets (pendant + web meeting) must not share one conversation (#5388).
        if not should_attach_to_existing_in_progress(
            existing_source=existing_source if isinstance(existing_source, str) else None,
            request_source=self.host.request.source,
        ):
            await self.create_new_in_progress_conversation()
            return None
        if (
            any(existing.get(key) for key in ('deleted', 'discarded', 'is_locked'))
            or existing.get('client_device_id') != self.host.client_device_context.client_device_id
        ):
            await self.create_new_in_progress_conversation()
            return None
        existing = await self._continuity_row(existing)
        finished_at = datetime.fromisoformat(existing['finished_at'].isoformat())
        seconds = (self.clock() - finished_at).total_seconds()
        if (
            decide_existing_conversation_action(
                seconds_since_last_segment=seconds,
                conversation_creation_timeout=continuation_timeout(existing, self.host.conversation_creation_timeout),
            )
            == ConversationLifecycleAction.process_and_create_new
        ):
            # This runs before STT initialization: an outage cannot indefinitely
            # defer empty-generation cleanup. The transaction still lets content win.
            if not (existing.get('transcript_segments') or existing.get('photos') or existing.get('has_content')):
                await self.process_conversation(existing['id'])
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
        if binding.get('conversation_snapshot_known'):
            current = binding.get('conversation_snapshot')
            if (
                not current
                or current.get('status') != ConversationStatus.in_progress.value
                or any(current.get(key) for key in ('deleted', 'discarded', 'is_locked'))
            ):
                await self.create_new_in_progress_conversation(rollover=True)
                return None
            existing = current
        self.host.state.current_conversation_id = existing['id']
        self.host.recording_session_ids_by_conversation[existing['id']] = self.host.recording_session_id
        self._adopt_capture_timeline(existing['id'], existing.get('started_at'))
        self.send_conversation_session(binding, self.host.recording_session_id)
        return None

    async def process_pending(self, timed_out_id: Optional[str]) -> None:
        # Interruptible delay, not a polling loop. An early wake means the session is shutting
        # down, which is precisely when the timed-out conversation and anything still stuck in
        # `processing` must be finalized, so the wake shortens the wait instead of skipping the
        # work. Returning here dropped both (pre-split this was an unconditional sleep).
        await self.host.wait(7)
        if timed_out_id:
            await self._finalize_isolated(self.process_conversation, timed_out_id, stage='timed_out')
        processing = await self.host.persistence.call(
            conversations_db.get_processing_conversations, self.host.request.uid
        )
        for conversation in processing or []:
            await self._finalize_isolated(self.schedule_finalization, conversation['id'], stage='processing')
        await self.recover_stale_in_progress()

    async def _finalize_isolated(
        self, finalize: Callable[[str], Awaitable[bool]], conversation_id: str, *, stage: str
    ) -> None:
        """Finalize one earlier conversation without letting its failure end the live session.

        process_pending runs as a supervised finite task, so an exception escaping it is a
        supervisor crash that tears down the socket. A conversation whose finalization write
        fails every time (a document already at Firestore's 1 MiB limit) was retried by each
        reconnect and ended each session seconds after it started, so the client reconnected
        in a loop and its live transcription never ran. A transient failure (contention, an
        expired transaction) keeps the row's status for the next session's sweep; unrelated rows
        in the same sweep still run. A rejection at the 1 MiB ceiling is permanent, so that row
        goes to ``_close_oversized`` instead of being retried by every reconnect.
        """
        try:
            await finalize(conversation_id)
        except Exception as error:
            failure = classify_finalization_failure(error, conversation_id)
            if failure.conversation_at_size_limit:
                await self._close_oversized(conversation_id, stage=stage)
                return
            # Bounded tokens, never the message: Firestore names the rejected
            # document by its path, which carries the uid.
            logger.error(
                'Listen pending finalization failed stage=%s conversation=%s type=%s reason=%s document=%s',
                stage,
                conversation_id,
                type(error).__name__,
                failure.reason,
                failure.document,
            )

    async def _close_oversized(self, conversation_id: str, *, stage: str) -> None:
        """Terminalize a row whose finalization can never commit because it is at the 1 MiB ceiling.

        Retrying is pointless (the binding write grows the document) and the row
        would stay ``in_progress``, invisible to the user, while every reconnect
        retried it. The lifecycle owner closes it as a kept, completed
        conversation with its transcript intact; its own fences decide, and any
        refusal leaves the row exactly as it was.
        """
        try:
            outcome = await self.host.persistence.call(
                lifecycle_service.close_oversized_in_progress_conversation,
                self.host.request.uid,
                conversation_id,
                quiet_for=timedelta(seconds=STALE_IN_PROGRESS_RECOVERY_AGE_SECONDS),
            )
        except Exception as error:
            logger.error(
                'Listen oversized conversation close failed stage=%s conversation=%s type=%s reason=%s',
                stage,
                conversation_id,
                type(error).__name__,
                classify_finalization_failure(error, conversation_id).reason,
            )
            return
        logger.warning(
            'Listen pending finalization hit the document size limit stage=%s conversation=%s close=%s',
            stage,
            conversation_id,
            outcome,
        )
        if outcome != 'closed':
            return
        record_fallback(
            component='conversation_finalization',
            from_mode='listen_finalization',
            to_mode='oversized_terminal',
            reason='other',
            outcome='degraded',
            log=logger,
        )
        self.on_conversation_processed(conversation_id)

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
            await self._finalize_isolated(self.process_conversation, conversation['id'], stage='stale_in_progress')

    async def lifecycle_loop(self) -> None:
        while self.host.state.active:
            if await self.host.wait(5):
                break
            conversation_id = self.host.state.current_conversation_id
            if not conversation_id:
                continue
            conversation = await self.host.persistence.call(
                conversations_db.get_conversation,
                self.host.request.uid,
                conversation_id,
                read_site=FirestoreReadSite.LISTEN_LIFECYCLE_POLL,
            )
            if not conversation:
                await self.create_new_in_progress_conversation(rollover=True)
                continue
            conversation = await self._continuity_row(conversation)
            finished_at = datetime.fromisoformat(conversation['finished_at'].isoformat())
            action = decide_lifecycle_action(
                conversation_exists=True,
                status=conversation.get('status'),
                in_progress_status=ConversationStatus.in_progress,
                seconds_since_last_update=(self.clock() - finished_at).total_seconds(),
                conversation_creation_timeout=continuation_timeout(
                    conversation, self.host.conversation_creation_timeout
                ),
            )
            if action == ConversationLifecycleAction.create_new:
                await self.create_new_in_progress_conversation(rollover=True)
            elif action == ConversationLifecycleAction.process_and_create_new:
                await self.host.transcripts.flush_speaker_assignments(conversation_id)
                await self._finalize_isolated(self.process_conversation, conversation_id, stage='lifecycle_rollover')
                await self.create_new_in_progress_conversation(rollover=True)

    async def send_last_conversation(self) -> None:
        last = await self.host.persistence.call(conversations_db.get_last_completed_conversation, self.host.request.uid)
        if last:
            self.host.send_event(LastConversationEvent(memory_id=last['id']))
