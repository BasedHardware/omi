"""Transcript, translation, and live-content persistence for listen sessions."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple, cast

from fastapi.websockets import WebSocketDisconnect

from database.firestore_read_metrics import FirestoreReadSite
from models.conversation import Conversation
from models.conversation_enums import ConversationSource
from models.conversation_photo import ConversationPhoto
from models.message_event import (
    SegmentsDeletedEvent,
    SpeakerLabelSuggestionEvent,
    TranslationEvent,
)
from models.transcript_segment import SpeakerIdentityStatus, TranscriptSegment, Translation
from routers.listen.contracts import persisted_started_seconds
from utils.app_integrations import trigger_realtime_integrations
from utils.audio_timeline import UNPLACED_SEGMENT_OFFSET
from utils.conversations.factory import deserialize_conversation
from utils.metrics import OMI_AUDIO_TIMELINE_SEGMENTS_TOTAL
from utils.observability.fallback import record_fallback
from utils.manual_speaker_assignments import LiveTranscriptMerge
from utils.speaker_assignment import process_speaker_assigned_segments, should_update_speaker_to_person_map
from utils.speaker_identification import detect_speaker_introduction
from utils.stt.streaming import sort_segments_by_start
from utils.stt.speaker_identity import ConversationSpeakerIdAllocator
from utils.transcribe_decisions import (
    is_user_self_match,
    person_id_for_client,
    resolve_photo_conversation_source,
    should_queue_speaker_embedding,
    should_skip_speaker_detection,
)
from utils.transcribe_store import conversations_db, user_db
from utils.translation import TranslationService
from utils.translation_cache import ConversationLanguageState, TranscriptSegmentLanguageCache
from utils.translation_coordinator import TranslationCoordinator
from utils.product_telemetry import emit_product_event

logger = logging.getLogger(__name__)


class ConversationCache:
    """Cache one live conversation without hiding its freshness contract."""

    def __init__(self, loader: Any, monotonic: Any = time.monotonic, refresh_seconds: float = 30.0):
        self.loader = loader
        self.monotonic = monotonic
        self.refresh_seconds = refresh_seconds
        self.data: Optional[Dict[str, Any]] = None
        self.conversation_id: Optional[str] = None
        self.loaded_at = 0.0
        self.protection_level = 'standard'

    async def get(self, conversation_id: Optional[str], *, force_refresh: bool = False) -> Optional[Dict[str, Any]]:
        if not conversation_id:
            return None
        now = self.monotonic()
        stale = now - self.loaded_at >= self.refresh_seconds
        if self.data is None or self.conversation_id != conversation_id or stale or force_refresh:
            data = await self.loader(conversation_id)
            if data:
                self.data = data
                self.conversation_id = conversation_id
                self.loaded_at = now
                self.protection_level = data.get('data_protection_level', 'standard')
            return data
        return self.data

    def update_segments(self, segments: List[Dict[str, Any]]) -> None:
        if self.data is not None:
            self.data['transcript_segments'] = segments

    def clear(self) -> None:
        self.data = None


class TranscriptProcessor:
    def __init__(self, host: Any):
        self.host = host
        self.segment_buffer: deque[Dict[str, Any]] = deque(maxlen=host.limits.max_segment_buffer_size)
        self.photo_buffer: deque[ConversationPhoto] = deque(maxlen=host.limits.max_photo_buffer_size)
        self.cache = ConversationCache(self._load_conversation)
        self.current_session_segments: Dict[str, bool] = {}
        self.suggested_segments: set[str] = set()
        self.speaker_id_allocator = ConversationSpeakerIdAllocator()
        self.language_cache = TranscriptSegmentLanguageCache()
        self.translation_service = TranslationService()
        self.translation_lock = asyncio.Lock()
        self.translation_enabled = host.translation_language is not None
        self.translation_coordinator: Optional[TranslationCoordinator] = None
        if self.translation_enabled:
            self.translation_coordinator = TranslationCoordinator(
                target_language=host.translation_language or 'en',
                translation_service=self.translation_service,
                on_translation_ready=self._on_translation_ready,
                language_state=ConversationLanguageState(host.translation_language or 'en'),
            )
        self._flush_failures = 0
        self._flush_backoff_until = 0.0

    async def _load_conversation(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        return await self.host.persistence.call(
            conversations_db.get_conversation,
            self.host.request.uid,
            conversation_id,
            read_site=FirestoreReadSite.LISTEN_TRANSCRIPT_CACHE_LOAD,
        )

    def enqueue(self, segments: List[Dict[str, Any]]) -> None:
        if getattr(self.host.state, 'capture_timeline_v2', False) and self.segment_buffer.maxlen is not None:
            # deque(maxlen=...) silently discards old provider text on
            # overflow. V2 retains it and lets the persistence loop drain.
            self.segment_buffer = deque(self.segment_buffer)
        self.segment_buffer.extend(segments)

    async def _on_translation_ready(
        self, segment_id: str, translated_text: str, _detected_language: str, conversation_id: str
    ) -> None:
        if not self.host.translation_language:
            return
        if not self.host.state.active and not (
            self.translation_coordinator and self.translation_coordinator._flushing  # type: ignore[reportPrivateUsage]
        ):
            return
        # TranslationCoordinator invokes this callback from a bare task and only catches
        # (RuntimeError, ValueError), so a persist failure escaping here aborts the batch loop and
        # silently drops the translations for every remaining segment. Keep the failure contained.
        try:
            async with self.translation_lock:
                conversation = (
                    await self.cache.get(conversation_id)
                    if conversation_id == self.host.state.current_conversation_id
                    else await self._load_conversation(conversation_id)
                )
                if not conversation:
                    return
                for index, segment in enumerate(conversation.get('transcript_segments', [])):
                    if segment['id'] != segment_id:
                        continue
                    translations = segment.get('translations', [])
                    translation = Translation(lang=self.host.translation_language, text=translated_text).model_dump()
                    replacement = next(
                        (
                            i
                            for i, value in enumerate(translations)
                            if value.get('lang') == self.host.translation_language
                        ),
                        None,
                    )
                    if replacement is None:
                        translations.append(translation)
                    else:
                        translations[replacement] = translation
                    conversation['transcript_segments'][index]['translations'] = translations
                    written = await self.host.persistence.call(
                        conversations_db.update_conversation_segments,
                        self.host.request.uid,
                        conversation_id,
                        conversation['transcript_segments'],
                        data_protection_level=(
                            self.cache.protection_level
                            if conversation_id == self.host.state.current_conversation_id
                            else None
                        ),
                        # Opt out of the unconditional DELETE_FIELD sentinel so this ~0.6s
                        # write loop stays cheap when no projection is present. The segment
                        # transaction still clears a projection that is actually on the
                        # document (a finalize overlapping capture).
                        invalidate_client_processing=False,
                        segment_update_fields=('translations',),
                        return_segments=True,
                    )
                    if isinstance(written, list) and conversation_id == self.host.state.current_conversation_id:
                        self.cache.update_segments(written)
                        accepted = next((s for s in written if s['id'] == segment_id), None)
                        if accepted is not None:
                            self.host.send_event(TranslationEvent(segments=[accepted]))
                    return
        except Exception as error:
            logger.error(
                'Translation persist failed segment=%s uid=%s type=%s',
                segment_id,
                self.host.request.uid,
                type(error).__name__,
            )

    async def _update_live_conversation(
        self,
        conversation: Conversation,
        segments: List[TranscriptSegment],
        photos: List[ConversationPhoto],
        finished_at: datetime,
        started_at: Optional[datetime],
        audio_timeline: Optional[Dict[str, Any]] = None,
    ) -> Optional[tuple[Conversation, List[TranscriptSegment], List[str]]]:
        updated: List[TranscriptSegment] = []
        removed: List[str] = []
        if segments:
            # Preserve unmerged speech until the transaction reads the current receipt.
            fresh = [segment.model_dump() for segment in segments]
            speaker = self.host.speakers
            targets = (
                [*conversation.transcript_segments, *segments]
                if self.host.state.speaker_map_dirty
                else [*conversation.transcript_segments[-1:], *segments]
            )
            process_speaker_assigned_segments(targets, speaker.segment_assignments, speaker.speaker_to_person)
            self._apply_speaker_identity_statuses(targets)
            written = await self.host.persistence.call(
                conversations_db.update_conversation_segments,
                self.host.request.uid,
                conversation.id,
                [segment.model_dump() for segment in targets],
                live_segments=fresh,
                started_at=started_at,
                audio_timeline=audio_timeline,
                data_protection_level=self.cache.protection_level,
                invalidate_client_processing=False,
            )
            if not isinstance(written, LiveTranscriptMerge):
                return None
            serialised = written.segments
            by_id = {s['id']: TranscriptSegment(**s) for s in serialised}
            conversation.transcript_segments = list(by_id.values())
            updated = [s for sid, s in by_id.items() if sid in written.updated_ids or self.host.state.speaker_map_dirty]
            removed = written.removed_ids
            self.host.state.speaker_map_dirty = False
            self.cache.update_segments(serialised)
        if photos:
            stored = await self.host.persistence.call(
                conversations_db.store_conversation_photos, self.host.request.uid, conversation.id, photos
            )
            if not stored:
                return None
            source = resolve_photo_conversation_source(conversation.source.value if conversation.source else None)
            if source is not None and conversation.source != ConversationSource(source):
                conversation.source = ConversationSource(source)
                await self.host.persistence.call(
                    conversations_db.update_conversation,
                    self.host.request.uid,
                    conversation.id,
                    {'source': conversation.source},
                )
        await self.host.persistence.call(
            conversations_db.update_conversation_finished_at, self.host.request.uid, conversation.id, finished_at
        )
        return conversation, updated, removed

    async def flush_speaker_assignments(self, conversation_id: Optional[str]) -> None:
        speaker = self.host.speakers
        if not conversation_id or not (
            speaker.speaker_to_person or speaker.segment_assignments or speaker.segment_identity_status
        ):
            return
        data = await self.cache.get(conversation_id, force_refresh=True)
        if not data:
            return
        conversation = deserialize_conversation(data)
        before = {
            cast(str, segment.id): (segment.person_id, segment.is_user, str(segment.speaker_identity_status))
            for segment in conversation.transcript_segments
        }
        process_speaker_assigned_segments(
            conversation.transcript_segments, speaker.segment_assignments, speaker.speaker_to_person
        )
        self._apply_speaker_identity_statuses(conversation.transcript_segments)
        serialised = [segment.model_dump() for segment in conversation.transcript_segments]
        written = await self.host.persistence.call(
            conversations_db.update_conversation_segments,
            self.host.request.uid,
            conversation.id,
            serialised,
            data_protection_level=self.cache.protection_level,
            # Opt out of the unconditional DELETE_FIELD sentinel so this ~0.6s
            # write loop stays cheap when no projection is present. The segment
            # transaction still clears a projection that is actually on the
            # document (a finalize overlapping capture).
            invalidate_client_processing=False,
            segment_update_fields=('person_id', 'is_user', 'speaker_identity_status'),
            return_segments=True,
        )
        if not written:
            failures = self._flush_failures + 1
            self._flush_failures = min(failures, 4)
            self._flush_backoff_until = time.monotonic() + min(5.0, 0.6 * (2 ** (self._flush_failures - 1)))
            return
        if isinstance(written, list):
            serialised = written
        self.cache.update_segments(serialised)
        self.host.state.speaker_map_dirty = False
        self._flush_failures = 0
        self._flush_backoff_until = 0.0
        changed = [
            item
            for item in serialised
            if before.get(str(item.get('id') or ''))
            != (item.get('person_id'), item.get('is_user'), str(item.get('speaker_identity_status') or ''))
        ]
        if self.host.state.active and changed:
            await self._deliver_segments(changed)

    def _apply_speaker_identity_statuses(self, segments: List[TranscriptSegment]) -> None:
        speaker = self.host.speakers
        for segment in segments:
            person_id = speaker.segment_assignments.get(cast(str, segment.id))
            if person_id is None and segment.speaker_id in speaker.speaker_to_person:
                person_id = speaker.speaker_to_person[cast(int, segment.speaker_id)][0]
            if person_id is not None:
                segment.speaker_identity_status = (
                    SpeakerIdentityStatus.user if is_user_self_match(person_id) else SpeakerIdentityStatus.not_user
                )
                continue
            status = speaker.segment_identity_status.get(cast(str, segment.id))
            if status is not None:
                segment.speaker_identity_status = status

    async def _translate(self, segments: List[TranscriptSegment], conversation_id: str, removed: List[str]) -> None:
        if self.translation_coordinator:
            await self.translation_coordinator.observe(segments, removed, conversation_id)

    async def _deliver_segments(self, client_segments: List[Dict[str, Any]]) -> bool:
        """Push live segments to the client without letting a gone client kill the loop.

        A disconnect is normal, and the ASGI server answers a send after close with a
        RuntimeError. Either way the socket is finished, not this loop: `process_loop`
        still owes the session its final speaker-assignment flush.
        """
        try:
            await self.host.request.websocket.send_json(client_segments)
            return True
        except WebSocketDisconnect:
            self.host.state.active = False
        except RuntimeError as error:
            self.host.state.active = False
            logger.warning('Listen segment delivery after close type=%s', type(error).__name__)
        return False

    async def _deliver_live_updates(
        self,
        conversation: Conversation,
        updated: List[TranscriptSegment],
        removed: List[str],
        new_segments: List[TranscriptSegment],
        conversation_id: str,
    ) -> None:
        """Deliver one batch's live updates: client WS, pusher/realtime, onboarding, translation.

        Shared by the legacy loop and the v2 batch path so the two persistence
        modes never drift in what a delivered segment triggers downstream.
        """
        client_segments = [segment.model_dump() for segment in updated]
        delivered = await self._deliver_segments(client_segments)
        if delivered and client_segments:
            self.host.complete_live_transcription()
        if self.host.transcript_send is not None and self.host.user_has_credits:
            self.host.transcript_send([segment.model_dump() for segment in new_segments])
        elif not self.host.pusher_enabled and self.host.user_has_credits:
            try:
                await trigger_realtime_integrations(
                    self.host.request.uid,
                    [segment.model_dump() for segment in new_segments],
                    conversation_id,
                    source=self.host.request.source,
                    client_kind=self.host.client_kind,
                )
            except Exception as error:
                logger.error('Realtime integration trigger failed type=%s', type(error).__name__)
        if self.host.onboarding_handler and not self.host.onboarding_handler.completed:
            self.host.onboarding_handler.on_segments_received([segment.model_dump() for segment in new_segments])
        await self._translate(updated, conversation.id, removed)

    async def process_loop(self) -> None:
        diarized_speaker_ids_by_conversation: Dict[str, set[int]] = {}
        while self.host.state.active or self.segment_buffer or self.photo_buffer:
            if await self.host.wait(0.6) and not (self.segment_buffer or self.photo_buffer):
                break
            if not self.segment_buffer and not self.photo_buffer:
                if self.host.state.speaker_map_dirty and time.monotonic() >= self._flush_backoff_until:
                    await self.flush_speaker_assignments(self.host.state.current_conversation_id)
                continue
            raw_segments = sort_segments_by_start(list(self.segment_buffer))
            conversation_id = self.host.state.current_conversation_id
            self.segment_buffer.clear()
            photos = list(self.photo_buffer)
            self.photo_buffer.clear()
            if not self.host.state.first_audio_byte_timestamp:
                # The first accepted frame may lag a provider callback. Keep
                # text until the capture origin exists rather than clearing it.
                if getattr(self.host.state, 'capture_timeline_v2', False):
                    for segment in reversed(raw_segments):
                        self.segment_buffer.appendleft(segment)
                continue
            if getattr(self.host.state, 'capture_timeline_v2', False):
                # Audio-timeline v2 persistence: segments already carry
                # absolute projected wall times and their owning conversation
                # from the capture span; offsets are computed against the
                # pinned origin below.
                await self._process_v2_batches(raw_segments, photos, diarized_speaker_ids_by_conversation)
                continue
            # Legacy persistence (flag off, resumed rows, custom/multi channel).
            # Segments may still carry a capture-clock window attached by the
            # receiver: the transcript math below is byte-identical to the
            # flag-off baseline, and the window only relocates speaker-ID
            # clips so they survive provider failovers that restart provider
            # time at zero.
            capture_windows: Dict[str, Tuple[float, float]] = {}
            for raw in raw_segments:
                abs_start = raw.pop('_capture_abs_start', None)
                abs_end = raw.pop('_capture_abs_end', None)
                if abs_start is not None and abs_end is not None:
                    capture_windows[cast(str, raw.get('id'))] = (float(abs_start), float(abs_end))
            missing_capture_windows = any(raw.get('_capture_window_unavailable') for raw in raw_segments)
            data = await self.cache.get(self.host.state.current_conversation_id)
            if not data:
                continue
            finished_at = datetime.now(timezone.utc)
            started_at: Optional[datetime] = None
            offset = 0.0
            new_segments: List[TranscriptSegment] = []
            if raw_segments:
                self.host.state.last_transcript_time = time.time()
                if not data.get('transcript_segments'):
                    started_at = datetime.fromtimestamp(
                        self.host.state.first_audio_byte_timestamp + raw_segments[0]['start'], tz=timezone.utc
                    )
                    data['started_at'] = started_at
                started_ts = (
                    persisted_started_seconds(data.get('started_at')) or self.host.state.first_audio_byte_timestamp
                )
                offset = self.host.state.first_audio_byte_timestamp - started_ts
                self.speaker_id_allocator.hydrate(data.get('transcript_segments', []))
                for raw in raw_segments:
                    self.speaker_id_allocator.assign(raw)
                    raw['start'] += offset
                    raw['end'] += offset
                    segment = TranscriptSegment(**raw, speech_profile_processed=True)
                    if (
                        self.host.onboarding_handler is not None
                        and raw.get('speaker_id') != self.host.onboarding_omi_speaker_id
                    ):
                        segment.is_user = True
                        segment.speaker_identity_status = SpeakerIdentityStatus.user
                    new_segments.append(segment)
                    self.current_session_segments[cast(str, segment.id)] = segment.speech_profile_processed
                if conversation_id:
                    diarized_speaker_ids_by_conversation.setdefault(conversation_id, set()).update(
                        segment.speaker_id for segment in new_segments if isinstance(segment.speaker_id, int)
                    )
                self.host.state.words_transcribed_since_last_record += len(
                    ' '.join(segment.text for segment in new_segments).split()
                )
            transcript_segments = new_segments
            current = deserialize_conversation(data)
            result = await self._update_live_conversation(current, transcript_segments, photos, finished_at, started_at)
            rolled_over = False
            if result is None:
                await self.host.conversations.create_new_in_progress_conversation(rollover=True)
                result = await self._write_fresh(transcript_segments, photos, finished_at, started_at)
                rolled_over = True
            if rolled_over:
                record_fallback(
                    component='other',
                    from_mode='fenced_generation',
                    to_mode='fresh_generation',
                    reason='local_heal',
                    outcome='recovered' if result else 'exhausted',
                    log=logger,
                )
            if not result or not result[0]:
                continue
            conversation, updated, removed = result
            if removed:
                self.host.send_event(SegmentsDeletedEvent(segment_ids=removed))
            if not transcript_segments:
                continue
            await self._deliver_live_updates(conversation, updated, removed, transcript_segments, conversation.id)
            await self._speaker_detection(
                updated,
                self.host.state.first_audio_byte_timestamp - offset,
                capture_windows=capture_windows,
                queue_from_raw=raw_segments if capture_windows or missing_capture_windows else None,
            )
        if self.host.speakers.tasks:
            try:
                await asyncio.wait_for(self.host.state.speaker_id_done.wait(), timeout=15.0)
            except asyncio.TimeoutError:
                logger.warning('Timed out waiting for listen speaker identification to finish')
        await self.host.speakers.drain(timeout=10, label='listen_speaker_final')
        await self.flush_speaker_assignments(self.host.state.current_conversation_id)
        for conversation_id, diarized_speaker_ids in diarized_speaker_ids_by_conversation.items():
            if not diarized_speaker_ids:
                continue
            emit_product_event(
                uid=self.host.request.uid,
                event='Diarization Completed',
                properties={
                    'recording_id': getattr(self.host, 'recording_session_id', None),
                    'conversation_id': conversation_id,
                    'speaker_count': len(diarized_speaker_ids),
                    'source': 'stt_provider',
                },
            )

    def _reroute_unplaced(self, segments: List[Dict[str, Any]], *, base: float = 0.0) -> None:
        """Retain late text on the current generation without claiming audio."""
        for raw in segments:
            raw['start'] = float(raw['start']) + base
            raw['end'] = raw['start']
            raw['audio_alignment'] = 'unplaced'
            raw.pop('audio_capture_run', None)
            raw['_conversation_id'] = self.host.state.current_conversation_id
            self.segment_buffer.append(raw)
            OMI_AUDIO_TIMELINE_SEGMENTS_TOTAL.labels(mode='v2', outcome='unplaced').inc()

    async def _process_v2_batches(
        self,
        raw_segments: List[Dict[str, Any]],
        photos: List[ConversationPhoto],
        diarized_by_conversation: Dict[str, set[int]],
    ) -> None:
        """Audio-timeline v2 persistence for one drain of the segment buffer.

        Epoch-translated segments carry absolute projected wall start/end plus
        the owning conversation resolved from their capture span. The current
        generation gets the full live path (persist, deliver, translate,
        speaker detection) with offsets projected against the conversation's
        pinned first-audio origin; a late batch whose owner is still open is
        written to that owner, while a terminal owner is fenced out and its
        text is explicitly unplaced on the active conversation.

        Late-but-open owners are **persist-only**: their segments are written
        and speaker-detected on the row that owns them, but WebSocket
        delivery, realtime integrations, onboarding and translation run for
        the session's current conversation only — a client watching this
        socket is watching the current conversation, and the late row's own
        finalization owns its post-processing.

        Only a conversation admitted as v2 from its first audio (a pinnable
        origin, or an already-pinned marker) may carry the v2 marker. A
        resumed row adopts its persisted ``started_at`` as the projection
        base and stays legacy for its lifetime — no marker, no origin move.
        """
        state = self.host.state
        groups: Dict[str, List[Dict[str, Any]]] = {}
        order: List[str] = []
        for raw in raw_segments:
            owner = raw.pop('_conversation_id', None) or state.current_conversation_id
            if not owner:
                self.segment_buffer.append(raw)
                continue
            if owner not in groups:
                groups[owner] = []
                order.append(owner)
            groups[owner].append(raw)
        if photos and state.current_conversation_id and state.current_conversation_id not in groups:
            # Photo-only drain, or a batch of late segments for a previous
            # owner: the current conversation's photos must still be written,
            # so run its write with an empty segment list.
            groups[state.current_conversation_id] = []
            order.append(state.current_conversation_id)

        for owner in order:
            segments = groups[owner]
            is_current = owner == state.current_conversation_id
            data = await self.cache.get(owner) if is_current else await self._load_conversation(owner)
            if not data:
                if is_current and segments:
                    # The conversation row may be a beat behind its binding;
                    # re-queue rather than drop live speech.
                    for segment in reversed(segments):
                        self.segment_buffer.appendleft(segment)
                else:
                    self._reroute_unplaced(segments)
                continue
            marker = data.get('audio_timeline')
            pinned = isinstance(marker, dict) and marker.get('version') == 2
            origin = state.conversation_capture_origins.get(owner)
            origin_wall = origin.wall if origin is not None else None
            if pinned:
                started_ts = persisted_started_seconds(data.get('started_at'))
                if started_ts is None:
                    self._reroute_unplaced(segments)
                    continue
                pin_started_at: Optional[datetime] = None
                pin_marker: Optional[Dict[str, Any]] = None
            elif origin_wall is not None:
                started_ts = origin_wall
                if origin.pinnable:
                    # Fresh v2 generation: pin the marker and the first-audio
                    # origin atomically with this batch's write.
                    pin_started_at = datetime.fromtimestamp(origin_wall, tz=timezone.utc)
                    pin_marker = {'version': 2}
                else:
                    # Adopted (resumed) row: project against its own persisted
                    # started_at; never pin the marker or move the origin.
                    pin_started_at = None
                    pin_marker = None
            elif not segments:
                # Photo-only drain before any audio: photos keep ordinary wall
                # lifecycle times and pin nothing.
                started_ts = persisted_started_seconds(data.get('started_at'))
                if started_ts is None:
                    continue
                pin_started_at = None
                pin_marker = None
            elif owner in state.conversations_legacy_locked:
                # Resumed with an unparseable started_at: keep the transcript
                # on the legacy projection base; never pin v2. The row's own
                # started_at stays as-is — the shadow datetime below only
                # makes the in-memory row model parseable, and no write in
                # this path touches started_at.
                started_ts = float(state.first_audio_byte_timestamp or 0.0)
                data['started_at'] = datetime.fromtimestamp(started_ts, tz=timezone.utc)
                pin_started_at = None
                pin_marker = None
            else:
                if is_current and segments:
                    # First audio not observed yet; the origin is pinned by the
                    # receiver at the next accepted frame.
                    for segment in reversed(segments):
                        self.segment_buffer.appendleft(segment)
                    continue
                self._reroute_unplaced(segments)
                continue
            if not is_current and data.get('status') != 'in_progress':
                # Terminal or processing generation: a late old-provider
                # callback must not reopen it.
                self._reroute_unplaced(segments)
                continue

            finished_at = datetime.now(timezone.utc)
            new_segments: List[TranscriptSegment] = []
            if segments:
                state.last_transcript_time = time.time()
                self.speaker_id_allocator.hydrate(data.get('transcript_segments', []))
                for raw in segments:
                    self.speaker_id_allocator.assign(raw)
                    raw['start'] = float(raw['start']) - started_ts
                    raw['end'] = float(raw['end']) - started_ts
                    if raw.get('audio_alignment') == 'unplaced':
                        # Released Flutter/macOS clients seek by start alone.
                        # V2 capture spans begin at >=0, so this offset cannot
                        # resolve to audio even when the marker is invisible.
                        raw['start'] = raw['end'] = UNPLACED_SEGMENT_OFFSET
                    segment = TranscriptSegment(**raw, speech_profile_processed=True)
                    if (
                        self.host.onboarding_handler is not None
                        and raw.get('speaker_id') != self.host.onboarding_omi_speaker_id
                    ):
                        segment.is_user = True
                        segment.speaker_identity_status = SpeakerIdentityStatus.user
                    new_segments.append(segment)
                    self.current_session_segments[cast(str, segment.id)] = segment.speech_profile_processed
                state.words_transcribed_since_last_record += len(
                    ' '.join(segment.text for segment in new_segments).split()
                )
                diarized_by_conversation.setdefault(owner, set()).update(
                    segment.speaker_id for segment in new_segments if isinstance(segment.speaker_id, int)
                )
            current = deserialize_conversation(data)
            result = await self._update_live_conversation(
                current,
                new_segments,
                photos if is_current else [],
                finished_at,
                pin_started_at,
                audio_timeline=pin_marker,
            )
            if result is None:
                if not is_current:
                    self._reroute_unplaced(segments, base=started_ts)
                    continue
                await self.host.conversations.create_new_in_progress_conversation(rollover=True)
                result = await self._write_fresh(
                    new_segments, [], finished_at, pin_started_at, audio_timeline=pin_marker
                )
                record_fallback(
                    component='other',
                    from_mode='fenced_generation',
                    to_mode='fresh_generation',
                    reason='local_heal',
                    outcome='recovered' if result else 'exhausted',
                    log=logger,
                )
            if not result or not result[0]:
                self._reroute_unplaced(segments, base=started_ts)
                continue
            conversation, updated, removed = result
            if removed:
                self.host.send_event(SegmentsDeletedEvent(segment_ids=removed))
            if not new_segments:
                continue
            if is_current:
                await self._deliver_live_updates(conversation, updated, removed, new_segments, owner)
            await self._speaker_detection(
                updated,
                started_ts,
                queue_from_raw=segments,
            )

    async def _write_fresh(
        self,
        segments: List[TranscriptSegment],
        photos: List[ConversationPhoto],
        finished_at: datetime,
        started_at: Optional[datetime],
        audio_timeline: Optional[Dict[str, Any]] = None,
    ) -> Optional[tuple[Conversation, List[TranscriptSegment], List[str]]]:
        data = await self.cache.get(self.host.state.current_conversation_id, force_refresh=True)
        return (
            await self._update_live_conversation(
                deserialize_conversation(data), segments, photos, finished_at, started_at, audio_timeline=audio_timeline
            )
            if data
            else None
        )

    async def _speaker_detection(
        self,
        segments: List[TranscriptSegment],
        abs_base: float,
        capture_windows: Optional[Dict[str, Tuple[float, float]]] = None,
        queue_from_raw: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """Queue speaker embedding work at absolute wall seconds.

        abs_base is the wall second of offset 0 for these segments: for v1 it
        is first_audio_byte_timestamp - offset (== started_at), for v2 the
        pinned conversation origin. Speaker clips cut from the ring buffer use
        the same projection as the stored offsets.

        capture_windows override that projection per segment id: when the
        receiver located the segment's audio on the capture clock (every
        server-STT session, flag or not), the clip window is that position,
        which stays correct across provider failovers whose timestamps restart
        at zero — the legacy first-audio + provider-time formula does not.

        queue_from_raw queues embedding work from the provider's raw segments
        instead of the post-merge ``segments``: the live merge re-labels a
        merged turn with the absorbing id, whose window is not in this batch's
        id-keyed map, while each raw segment keeps its own capture window (the
        matcher's covered-audio subtraction dedupes overlapping re-sends).
        """
        speaker = self.host.speakers
        for segment in segments:
            segment_id = cast(str, segment.id)
            if should_skip_speaker_detection(
                person_id=segment.person_id,
                is_user=segment.is_user,
                segment_id=segment_id,
                suggested_segments=cast(Sequence[str], self.suggested_segments),
            ):
                continue
            if segment.speaker_id in speaker.speaker_to_person:
                person_id, person_name = speaker.speaker_to_person[segment.speaker_id]
                if is_user_self_match(person_id):
                    segment.is_user = True
                    segment.speaker_identity_status = SpeakerIdentityStatus.user
                else:
                    segment.speaker_identity_status = SpeakerIdentityStatus.not_user
                    self.host.emit_speaker_suggestion(segment.speaker_id, person_id, person_name, segment_id)
                self.suggested_segments.add(segment_id)
                continue
            # queue_from_raw only re-homes the *embedding* work (the raw
            # segments keep their own capture windows through the live merge);
            # introduction detection must run on these merged segments exactly
            # as it does without capture windows.
            if queue_from_raw is None and should_queue_speaker_embedding(
                speaker_id=segment.speaker_id,
                person_id=segment.person_id,
                is_user=segment.is_user,
                speaker_id_enabled=self.host.state.speaker_id_enabled,
                has_person_embeddings=bool(speaker.person_embeddings),
                speaker_already_mapped=segment.speaker_id in speaker.speaker_to_person,
            ):
                if segment.audio_alignment == 'unplaced':
                    continue
                window = (capture_windows or {}).get(segment_id)
                if window is not None:
                    abs_start, abs_end = window
                else:
                    abs_start = abs_base + segment.start
                    abs_end = abs_base + segment.end
                try:
                    speaker.queue.put_nowait(
                        {
                            'id': segment.id,
                            'conversation_id': self.host.state.current_conversation_id,
                            'speaker_id': segment.speaker_id,
                            'abs_start': abs_start,
                            'abs_end': abs_end,
                            'duration': segment.end - segment.start,
                        }
                    )
                except asyncio.QueueFull:
                    pass
            detection = detect_speaker_introduction(segment.text, language=self.host.language)
            if not detection:
                continue
            name = detection.name
            # The owner is identified by voice, never by hearing their own name: minting
            # a person for it produced a second "David" alongside "David (You)".
            owner_name = await speaker.resolve_owner_name()
            if owner_name and name.casefold() == owner_name.casefold():
                continue
            person = await self.host.persistence.call(user_db.get_person_by_name, self.host.request.uid, name)
            # Only an explicit self-introduction may create a person. A bare copula
            # ("I'm Chinese") still resolves one the user already has, so a real name
            # keeps working, but it can no longer fill the picker with regex guesses.
            may_create = self.host.request.create_speakers and detection.explicit
            person_id = person['id'] if person else (str(uuid.uuid4()) if may_create else None)
            if person_id and not person:
                await self.host.persistence.call(
                    user_db.create_person,
                    self.host.request.uid,
                    {
                        'id': person_id,
                        'name': name,
                        'created_at': datetime.now(timezone.utc),
                        'updated_at': datetime.now(timezone.utc),
                    },
                )
            self.host.send_event(
                SpeakerLabelSuggestionEvent(
                    speaker_id=cast(int, segment.speaker_id),
                    person_id=person_id_for_client(person_id, self.host.request.speaker_auto_assign_enabled),
                    person_name=name,
                    segment_id=segment_id,
                )
            )
            if person_id:
                if should_update_speaker_to_person_map(segment.speaker_id):
                    speaker.speaker_to_person[cast(int, segment.speaker_id)] = (person_id, name)
                speaker.segment_assignments[segment_id] = person_id
                self.host.state.speaker_map_dirty = True
                self.suggested_segments.add(segment_id)
        if queue_from_raw is not None:
            self._queue_raw_detections(queue_from_raw, capture_windows, abs_base)

    def _queue_raw_detections(
        self,
        raw_segments: List[Dict[str, Any]],
        capture_windows: Optional[Dict[str, Tuple[float, float]]],
        abs_base: float,
    ) -> None:
        speaker = self.host.speakers
        for raw in raw_segments:
            if raw.get('audio_alignment') == 'unplaced' or raw.get('_capture_window_unavailable'):
                continue
            if should_skip_speaker_detection(
                person_id=raw.get('person_id'),
                is_user=raw.get('is_user', False),
                segment_id=cast(str, raw.get('id')),
                suggested_segments=cast(Sequence[str], self.suggested_segments),
            ):
                continue
            speaker_id = raw.get('speaker_id')
            if should_queue_speaker_embedding(
                speaker_id=speaker_id,
                person_id=raw.get('person_id'),
                is_user=raw.get('is_user', False),
                speaker_id_enabled=self.host.state.speaker_id_enabled,
                has_person_embeddings=bool(speaker.person_embeddings),
                speaker_already_mapped=speaker_id in speaker.speaker_to_person,
            ):
                window = (capture_windows or {}).get(cast(str, raw.get('id')))
                if window is not None:
                    abs_start, abs_end = window
                else:
                    abs_start = abs_base + float(raw['start'])
                    abs_end = abs_base + float(raw['end'])
                try:
                    speaker.queue.put_nowait(
                        {
                            'id': raw.get('id'),
                            'conversation_id': self.host.state.current_conversation_id,
                            'speaker_id': speaker_id,
                            'abs_start': abs_start,
                            'abs_end': abs_end,
                            'duration': float(raw['end']) - float(raw['start']),
                        }
                    )
                except asyncio.QueueFull:
                    pass

    async def flush_translations(self) -> None:
        if self.translation_coordinator:
            await self.translation_coordinator.flush()

    def clear(self) -> None:
        self.segment_buffer.clear()
        self.photo_buffer.clear()
        self.current_session_segments.clear()
        self.suggested_segments.clear()
        self.cache.clear()
        self.language_cache.cache.clear()
        self.translation_service.clear_session_cache()
