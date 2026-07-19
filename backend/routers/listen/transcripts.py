"""Transcript, translation, and live-content persistence for listen sessions."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, cast

from models.conversation import Conversation
from models.conversation_enums import ConversationSource
from models.conversation_photo import ConversationPhoto
from models.message_event import (
    SegmentsDeletedEvent,
    SpeakerLabelSuggestionEvent,
    TranslationEvent,
)
from models.transcript_segment import TranscriptSegment, Translation
from utils.app_integrations import trigger_realtime_integrations
from utils.conversations.factory import deserialize_conversation
from utils.observability.fallback import record_fallback
from utils.speaker_assignment import process_speaker_assigned_segments, should_update_speaker_to_person_map
from utils.speaker_identification import detect_speaker_from_text
from utils.stt.streaming import sort_segments_by_start, sort_transcript_segments_in_place
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

    async def _load_conversation(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        return await self.host.persistence.call(
            conversations_db.get_conversation, self.host.request.uid, conversation_id
        )

    def enqueue(self, segments: List[Dict[str, Any]]) -> None:
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
                    await self.host.persistence.call(
                        conversations_db.update_conversation_segments,
                        self.host.request.uid,
                        conversation_id,
                        conversation['transcript_segments'],
                        data_protection_level=(
                            self.cache.protection_level
                            if conversation_id == self.host.state.current_conversation_id
                            else None
                        ),
                    )
                    if conversation_id == self.host.state.current_conversation_id:
                        self.cache.update_segments(conversation['transcript_segments'])
                        self.host.send_event(TranslationEvent(segments=[conversation['transcript_segments'][index]]))
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
    ) -> Optional[tuple[Conversation, List[TranscriptSegment], List[str]]]:
        updated: List[TranscriptSegment] = []
        removed: List[str] = []
        if segments:
            conversation.transcript_segments, updated, removed = TranscriptSegment.combine_segments(
                conversation.transcript_segments, segments
            )
            sort_transcript_segments_in_place(conversation.transcript_segments)
            speaker = self.host.speakers
            targets = conversation.transcript_segments if self.host.state.speaker_map_dirty else updated
            process_speaker_assigned_segments(targets, speaker.segment_assignments, speaker.speaker_to_person)
            self.host.state.speaker_map_dirty = False
            serialised = [segment.model_dump() for segment in conversation.transcript_segments]
            written = await self.host.persistence.call(
                conversations_db.update_conversation_segments,
                self.host.request.uid,
                conversation.id,
                serialised,
                started_at=started_at,
                data_protection_level=self.cache.protection_level,
            )
            if not written:
                return None
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
        if not conversation_id or not (speaker.speaker_to_person or speaker.segment_assignments):
            return
        data = await self.cache.get(conversation_id, force_refresh=True)
        if not data:
            return
        conversation = deserialize_conversation(data)
        process_speaker_assigned_segments(
            conversation.transcript_segments, speaker.segment_assignments, speaker.speaker_to_person
        )
        serialised = [segment.model_dump() for segment in conversation.transcript_segments]
        await self.host.persistence.call(
            conversations_db.update_conversation_segments,
            self.host.request.uid,
            conversation.id,
            serialised,
            data_protection_level=self.cache.protection_level,
        )
        self.cache.update_segments(serialised)
        self.host.state.speaker_map_dirty = False

    async def _translate(self, segments: List[TranscriptSegment], conversation_id: str, removed: List[str]) -> None:
        if self.translation_coordinator:
            await self.translation_coordinator.observe(segments, removed, conversation_id)

    async def process_loop(self) -> None:
        while self.host.state.active or self.segment_buffer or self.photo_buffer:
            if await self.host.wait(0.6) and not (self.segment_buffer or self.photo_buffer):
                break
            if not self.segment_buffer and not self.photo_buffer:
                continue
            raw_segments = sort_segments_by_start(list(self.segment_buffer))
            self.segment_buffer.clear()
            photos = list(self.photo_buffer)
            self.photo_buffer.clear()
            if not self.host.state.first_audio_byte_timestamp:
                continue
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
                conversation_started = data['started_at']
                if isinstance(conversation_started, str):
                    conversation_started = datetime.fromisoformat(conversation_started)
                offset = self.host.state.first_audio_byte_timestamp - conversation_started.timestamp()
                for raw in raw_segments:
                    raw['start'] += offset
                    raw['end'] += offset
                    segment = TranscriptSegment(**raw, speech_profile_processed=True)
                    if (
                        self.host.request.onboarding_mode
                        and raw.get('speaker_id') != self.host.onboarding_omi_speaker_id
                    ):
                        segment.is_user = True
                    new_segments.append(segment)
                    self.current_session_segments[cast(str, segment.id)] = segment.speech_profile_processed
                self.host.state.words_transcribed_since_last_record += len(
                    ' '.join(segment.text for segment in new_segments).split()
                )
            transcript_segments, _, _ = TranscriptSegment.combine_segments([], new_segments)
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
            await self.host.request.websocket.send_json([segment.model_dump() for segment in updated])
            if self.host.transcript_send is not None and self.host.user_has_credits:
                self.host.transcript_send([segment.model_dump() for segment in transcript_segments])
            elif not self.host.pusher_enabled and self.host.user_has_credits:
                try:
                    await trigger_realtime_integrations(
                        self.host.request.uid,
                        [segment.model_dump() for segment in transcript_segments],
                        self.host.state.current_conversation_id,
                        source=self.host.request.source,
                    )
                except Exception as error:
                    logger.error('Realtime integration trigger failed type=%s', type(error).__name__)
            if self.host.onboarding_handler and not self.host.onboarding_handler.completed:
                self.host.onboarding_handler.on_segments_received(
                    [segment.model_dump() for segment in transcript_segments]
                )
            await self._translate(updated, conversation.id, removed)
            await self._speaker_detection(updated, offset)
        try:
            await asyncio.wait_for(self.host.state.speaker_id_done.wait(), timeout=15.0)
        except asyncio.TimeoutError:
            logger.warning('Timed out waiting for listen speaker identification to finish')
        await self.host.speakers.drain(timeout=10, label='listen_speaker_final')
        await self.flush_speaker_assignments(self.host.state.current_conversation_id)

    async def _write_fresh(
        self,
        segments: List[TranscriptSegment],
        photos: List[ConversationPhoto],
        finished_at: datetime,
        started_at: Optional[datetime],
    ) -> Optional[tuple[Conversation, List[TranscriptSegment], List[str]]]:
        data = await self.cache.get(self.host.state.current_conversation_id, force_refresh=True)
        return (
            await self._update_live_conversation(
                deserialize_conversation(data), segments, photos, finished_at, started_at
            )
            if data
            else None
        )

    async def _speaker_detection(self, segments: List[TranscriptSegment], offset: float) -> None:
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
                else:
                    self.host.emit_speaker_suggestion(segment.speaker_id, person_id, person_name, segment_id)
                self.suggested_segments.add(segment_id)
                continue
            if should_queue_speaker_embedding(
                speaker_id=segment.speaker_id,
                person_id=segment.person_id,
                is_user=segment.is_user,
                speaker_id_enabled=self.host.state.speaker_id_enabled,
                has_person_embeddings=bool(speaker.person_embeddings),
                speaker_already_mapped=segment.speaker_id in speaker.speaker_to_person,
            ):
                try:
                    speaker.queue.put_nowait(
                        {
                            'id': segment.id,
                            'speaker_id': segment.speaker_id,
                            'abs_start': self.host.state.first_audio_byte_timestamp + segment.start - offset,
                            'abs_end': self.host.state.first_audio_byte_timestamp + segment.end - offset,
                            'duration': segment.end - segment.start,
                        }
                    )
                except asyncio.QueueFull:
                    pass
            name = detect_speaker_from_text(segment.text)
            if not name:
                continue
            person = await self.host.persistence.call(user_db.get_person_by_name, self.host.request.uid, name)
            person_id = person['id'] if person else (str(uuid.uuid4()) if self.host.request.create_speakers else None)
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
                self.suggested_segments.add(segment_id)

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
