import asyncio
import io
import json
import os
import struct
import time
import uuid
import wave
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple, Callable

import av
import numpy as np
import opuslib  # type: ignore

import lc3  # lc3py

from fastapi import APIRouter, Depends
from fastapi.websockets import WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState
from websockets.exceptions import ConnectionClosed

import database.conversations as conversations_db
import database.calendar_meetings as calendar_db
import database.users as user_db
from database.users import get_user_transcription_preferences
from database import redis_db
from database.redis_db import (
    get_cached_user_geolocation,
    try_acquire_listen_lock,
)
from models.conversation import (
    Conversation,
    ConversationPhoto,
    ConversationSource,
    ConversationStatus,
    Geolocation,
    Structured,
    TranscriptSegment,
)
from models.message_event import (
    ConversationEvent,
    FREEMIUM_ACTION_SETUP_ON_DEVICE_STT,
    FreemiumThresholdReachedEvent,
    LastConversationEvent,
    MessageEvent,
    MessageServiceStatusEvent,
    PhotoDescribedEvent,
    PhotoProcessingEvent,
    SpeakerLabelSuggestionEvent,
    TranslationEvent,
)
from models.transcript_segment import Translation
from models.users import PlanType
from utils.analytics import record_usage
from utils.app_integrations import trigger_external_integrations
from utils.apps import is_audio_bytes_app_enabled
from utils.conversations.location import get_google_maps_location
from utils.conversations.process_conversation import process_conversation, retrieve_in_progress_conversation
from utils.notifications import send_credit_limit_notification, send_silent_user_notification
from utils.other import endpoints as auth
from utils.other.storage import get_profile_audio_if_exists, get_user_has_speech_profile
from utils.other.task import safe_create_task
from utils.pusher import connect_to_trigger_pusher
from utils.speaker_identification import detect_speaker_from_text
from utils.stt.streaming import (
    SPEECH_PROFILE_FIXED_DURATION,
    SPEECH_PROFILE_PADDING_DURATION,
    SPEECH_PROFILE_STABILIZE_DELAY,
    STTService,
    get_stt_service_for_language,
    process_audio_dg,
    process_audio_soniox,
    process_audio_speechmatics,
    send_initial_file_path,
)
from utils.subscription import has_transcription_credits, get_remaining_transcription_seconds
from utils.translation import TranslationService
from utils.translation_cache import TranscriptSegmentLanguageCache
from utils.webhooks import get_audio_bytes_webhook_seconds
from utils.onboarding import OnboardingHandler

from utils.aac import AACDecoder
from utils.audio import AudioRingBuffer
from utils.stt.speaker_embedding import (
    extract_embedding_from_bytes,
    compare_embeddings,
    SPEAKER_MATCH_THRESHOLD,
)


router = APIRouter()


PUSHER_ENABLED = bool(os.getenv('HOSTED_PUSHER_API_URL'))

# Freemium: Send notification when credits threshold is reached
FREEMIUM_THRESHOLD_SECONDS = 180  # 3 minutes remaining - notify user


class CustomSttMode(str, Enum):
    disabled = "disabled"
    enabled = "enabled"


async def _listen(
    websocket: WebSocket,
    uid: str,
    language: str = 'en',
    sample_rate: int = 8000,
    codec: str = 'pcm8',
    channels: int = 1,
    include_speech_profile: bool = True,
    stt_service: Optional[STTService] = None,
    conversation_timeout: int = 120,
    source: Optional[str] = None,
    custom_stt_mode: CustomSttMode = CustomSttMode.disabled,
    onboarding_mode: bool = False,
):
    session_id = str(uuid.uuid4())
    print(
        '_listen',
        uid,
        session_id,
        language,
        sample_rate,
        codec,
        include_speech_profile,
        stt_service,
        conversation_timeout,
        f'custom_stt={custom_stt_mode}',
        f'onboarding={onboarding_mode}',
    )

    use_custom_stt = custom_stt_mode == CustomSttMode.enabled

    # Onboarding mode overrides: no speech profile (creating new one), single language
    if onboarding_mode:
        include_speech_profile = False

    try:
        await websocket.accept()
    except RuntimeError as e:
        print(e, uid, session_id)
        return

    if not uid or len(uid) <= 0:
        await websocket.close(code=1008, reason="Bad uid")
        return

    user_has_credits = True if use_custom_stt else has_transcription_credits(uid)
    if not user_has_credits:
        try:
            await send_credit_limit_notification(uid)
        except Exception as e:
            print(f"Error sending credit limit notification: {e}", uid, session_id)

    # Frame size, codec
    frame_size: int = 160
    lc3_chunk_size: Optional[int] = None
    lc3_frame_duration_us: Optional[int] = None

    if codec == "opus_fs320":
        codec = "opus"
        frame_size = 320
    elif codec == "lc3_fs1030":
        codec = "lc3"
        lc3_chunk_size = 30  # 30 bytes per frame
        lc3_frame_duration_us = 10000  # 10ms = 10000 microseconds

    # Fetch user transcription preferences
    transcription_prefs = get_user_transcription_preferences(uid)
    single_language_mode = transcription_prefs.get('single_language_mode', False)
    vocabulary = transcription_prefs.get('vocabulary', [])

    # Onboarding mode: force single language for better accuracy
    if onboarding_mode:
        single_language_mode = True

    # Always include "Omi" as predefined vocabulary
    vocabulary = list({"Omi"} | set(vocabulary))

    # Convert 'auto' to 'multi' for consistency
    language = 'multi' if language == 'auto' else language

    # Determine the best STT service
    stt_service, stt_language, stt_model = get_stt_service_for_language(
        language, multi_lang_enabled=not single_language_mode
    )
    if not stt_service or not stt_language:
        await websocket.close(code=1008, reason=f"The language is not supported, {language}")
        return

    # Translation language (disabled in single language mode)
    translation_language = None
    if single_language_mode:
        translation_language = None
    elif stt_language == 'multi':
        if language == "multi":
            user_language_preference = user_db.get_user_language_preference(uid)
            if user_language_preference:
                translation_language = user_language_preference
        else:
            translation_language = language

    websocket_active = True
    websocket_close_code = 1001  # Going Away, don't close with good from backend

    # Initialize segment buffers early (before onboarding handler needs them)
    realtime_segment_buffers = []
    realtime_photo_buffers: list[ConversationPhoto] = []

    # === Speaker Identification State ===
    RING_BUFFER_DURATION = 60.0  # seconds
    SPEAKER_ID_MIN_AUDIO = 2.0
    SPEAKER_ID_TARGET_AUDIO = 4.0

    audio_ring_buffer: Optional[AudioRingBuffer] = None
    speaker_id_segment_queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=100)
    person_embeddings_cache: Dict[str, dict] = {}  # person_id -> {embedding, name}
    speaker_id_enabled = False  # Will be set after private_cloud_sync_enabled is known

    # Onboarding handler
    onboarding_handler: Optional[OnboardingHandler] = None
    if onboarding_mode:

        async def send_onboarding_event(event: dict):
            if websocket_active and websocket.client_state == WebSocketState.CONNECTED:
                try:
                    await websocket.send_json(event)
                except Exception as e:
                    print(f"Error sending onboarding event: {e}", uid, session_id)

        def onboarding_stream_transcript(segments: List[dict]):
            """Inject onboarding question segments into the transcript stream."""
            nonlocal realtime_segment_buffers
            realtime_segment_buffers.extend(segments)

        onboarding_handler = OnboardingHandler(uid, send_onboarding_event, onboarding_stream_transcript)
        asyncio.create_task(onboarding_handler.send_current_question())

    locked_conversation_ids: Set[str] = set()
    speaker_to_person_map: Dict[int, Tuple[str, str]] = {}
    segment_person_assignment_map: Dict[str, str] = {}
    current_session_segments: Dict[str, bool] = {}  # Store only speech_profile_processed status
    suggested_segments: Set[str] = set()
    first_audio_byte_timestamp: Optional[float] = None
    last_usage_record_timestamp: Optional[float] = None
    words_transcribed_since_last_record: int = 0
    last_transcript_time: Optional[float] = None
    current_conversation_id = None

    freemium_threshold_sent = False  # Track if we've sent the freemium threshold notification

    async def _record_usage_periodically():
        nonlocal websocket_active, last_usage_record_timestamp, words_transcribed_since_last_record
        nonlocal last_audio_received_time, last_transcript_time, user_has_credits
        nonlocal freemium_threshold_sent

        while websocket_active:
            await asyncio.sleep(60)
            if not websocket_active:
                break

            if use_custom_stt:
                continue

            if last_usage_record_timestamp:
                current_time = time.time()
                transcription_seconds = int(current_time - last_usage_record_timestamp)

                words_to_record = words_transcribed_since_last_record
                words_transcribed_since_last_record = 0  # reset

                if transcription_seconds > 0 or words_to_record > 0:
                    record_usage(uid, transcription_seconds=transcription_seconds, words_transcribed=words_to_record)
                last_usage_record_timestamp = current_time

            # Freemium: Check remaining credits and notify when threshold reached
            remaining_seconds = get_remaining_transcription_seconds(uid)

            # Notify user when approaching limit (3 minutes remaining)
            if (
                remaining_seconds is not None
                and remaining_seconds <= FREEMIUM_THRESHOLD_SECONDS
                and not freemium_threshold_sent
            ):
                # Determine required action
                # Currently: user must setup on-device STT
                # Future: backend may auto-fallback to lower-tier cloud STT (action = ACTION_NONE)
                await _asend_message_event(
                    FreemiumThresholdReachedEvent(
                        remaining_seconds=remaining_seconds,
                        action=FREEMIUM_ACTION_SETUP_ON_DEVICE_STT,
                    )
                )
                freemium_threshold_sent = True

                # Also send push notification
                try:
                    await send_credit_limit_notification(uid)
                except Exception as e:
                    print(f"Error sending credit limit notification: {e}", uid, session_id)

            # Update credits state
            if remaining_seconds is not None and remaining_seconds <= 0:
                user_has_credits = False
            elif remaining_seconds is None or remaining_seconds > 0:
                user_has_credits = True
                # Reset threshold flag if credits were restored (new month, upgrade, etc.)
                if remaining_seconds is None or remaining_seconds > FREEMIUM_THRESHOLD_SECONDS:
                    freemium_threshold_sent = False

            # Silence notification logic for basic plan users
            user_subscription = user_db.get_user_valid_subscription(uid)
            if not user_subscription or user_subscription.plan == PlanType.basic:
                time_of_last_words = last_transcript_time or first_audio_byte_timestamp
                if (
                    last_audio_received_time
                    and time_of_last_words
                    and (last_audio_received_time - time_of_last_words) > 15 * 60
                ):
                    print(f"User {uid} has been silent for over 15 minutes. Sending notification.", session_id)
                    try:
                        await send_silent_user_notification(uid)
                    except Exception as e:
                        print(f"Error sending silent user notification: {e}", uid, session_id)

    async def _asend_message_event(msg: MessageEvent):
        nonlocal websocket_active
        if not websocket_active:
            return False
        try:
            await websocket.send_json(msg.to_json())
            return True
        except WebSocketDisconnect:
            print("WebSocket disconnected", uid, session_id)
            websocket_active = False
        except Exception as e:
            print(f"Can not send message event, error: {e}", uid, session_id)

        return False

    def _send_message_event(msg: MessageEvent):
        nonlocal websocket_active
        if not websocket_active:
            return
        return asyncio.create_task(_asend_message_event(msg))

    # Heart beat
    started_at = time.time()
    inactivity_timeout_seconds = 90
    last_audio_received_time = None
    last_activity_time = None

    # Send pong every 10s then handle it in the app \
    # since Starlette is not support pong automatically
    async def send_heartbeat():
        print("send_heartbeat", uid, session_id)
        nonlocal websocket_active
        nonlocal websocket_close_code
        nonlocal started_at
        nonlocal last_audio_received_time

        try:
            while websocket_active:
                # ping fast
                if websocket.client_state == WebSocketState.CONNECTED:
                    await websocket.send_text("ping")
                else:
                    break

                # Inactivity timeout
                if last_activity_time and time.time() - last_activity_time > inactivity_timeout_seconds:
                    print(f"Session timeout due to inactivity ({inactivity_timeout_seconds}s)", uid, session_id)
                    websocket_close_code = 1001
                    websocket_active = False
                    break

                # next
                await asyncio.sleep(10)
        except WebSocketDisconnect:
            print("WebSocket disconnected", uid, session_id)
        except Exception as e:
            print(f'Heartbeat error: {e}', uid, session_id)
            websocket_close_code = 1011
        finally:
            websocket_active = False

    # Start heart beat
    heartbeat_task = asyncio.create_task(send_heartbeat())

    _send_message_event(
        MessageServiceStatusEvent(event_type="service_status", status="initiating", status_text="Service Starting")
    )

    # Validate user
    if not user_db.is_exists_user(uid):
        websocket_active = False
        await websocket.close(code=1008, reason="Bad user")
        return

    # Create or get conversation ID early for audio chunk storage
    private_cloud_sync_enabled = user_db.get_user_private_cloud_sync_enabled(uid)

    # Enable speaker identification if not custom STT and private cloud sync is enabled
    speaker_id_enabled = not use_custom_stt and private_cloud_sync_enabled
    if speaker_id_enabled:
        audio_ring_buffer = AudioRingBuffer(RING_BUFFER_DURATION, sample_rate)

    # Conversation timeout (to process the conversation after x seconds of silence)
    # Max: 4h, min 2m
    conversation_creation_timeout = conversation_timeout
    if conversation_creation_timeout == -1:
        conversation_creation_timeout = 4 * 60 * 60
    if conversation_creation_timeout < 120:
        conversation_creation_timeout = 120

    # Stream transcript
    # Callback for when pusher finishes processing a conversation
    def on_conversation_processed(conversation_id: str):
        conversation_data = conversations_db.get_conversation(uid, conversation_id)
        if conversation_data:
            conversation = Conversation(**conversation_data)
            _send_message_event(ConversationEvent(event_type="memory_created", memory=conversation, messages=[]))

    def on_conversation_processing_started(conversation_id: str):
        conversation_data = conversations_db.get_conversation(uid, conversation_id)
        if conversation_data:
            conversation = Conversation(**conversation_data)
            _send_message_event(ConversationEvent(event_type="memory_processing_started", memory=conversation))

    # Fallback for when pusher is not available
    async def _create_conversation_fallback(conversation_data: dict):
        conversation = Conversation(**conversation_data)
        if conversation.status != ConversationStatus.processing:
            _send_message_event(ConversationEvent(event_type="memory_processing_started", memory=conversation))
            conversations_db.update_conversation_status(uid, conversation.id, ConversationStatus.processing)
            conversation.status = ConversationStatus.processing

        try:
            # Geolocation
            geolocation = get_cached_user_geolocation(uid)
            if geolocation:
                geolocation = Geolocation(**geolocation)
                conversation.geolocation = get_google_maps_location(geolocation.latitude, geolocation.longitude)

            conversation = process_conversation(uid, language, conversation)
            messages = trigger_external_integrations(uid, conversation)
        except Exception as e:
            print(f"Error processing conversation: {e}", uid, session_id)
            conversations_db.set_conversation_as_discarded(uid, conversation.id)
            conversation.discarded = True
            messages = []

        _send_message_event(ConversationEvent(event_type="memory_created", memory=conversation, messages=messages))

    async def cleanup_processing_conversations():
        processing = conversations_db.get_processing_conversations(uid)
        print('finalize_processing_conversations len(processing):', len(processing), uid, session_id)
        if not processing or len(processing) == 0:
            return

        for conversation in processing:
            if PUSHER_ENABLED:
                await request_conversation_processing(conversation['id'])
            else:
                await _create_conversation_fallback(conversation)

    async def process_pending_conversations(timed_out_id: Optional[str]):
        await asyncio.sleep(7.0)
        if timed_out_id:
            await _process_conversation(timed_out_id)
        await cleanup_processing_conversations()

    # Send last completed conversation to client
    def send_last_conversation():
        last_conversation = conversations_db.get_last_completed_conversation(uid)
        if last_conversation:
            _send_message_event(LastConversationEvent(memory_id=last_conversation['id']))

    send_last_conversation()

    # Create new stub conversation for next batch
    async def _create_new_in_progress_conversation():
        nonlocal current_conversation_id

        conversation_source = ConversationSource.omi
        if source:
            try:
                conversation_source = ConversationSource(source)
            except ValueError:
                print(f"Invalid conversation source '{source}', defaulting to 'omi'", uid, session_id)
                conversation_source = ConversationSource.omi

        new_conversation_id = str(uuid.uuid4())
        stub_conversation = Conversation(
            id=new_conversation_id,
            created_at=datetime.now(timezone.utc),
            started_at=datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc),
            structured=Structured(),
            language=language,
            transcript_segments=[],
            photos=[],
            status=ConversationStatus.in_progress,
            source=conversation_source,
            private_cloud_sync_enabled=private_cloud_sync_enabled,
        )
        conversations_db.upsert_conversation(uid, conversation_data=stub_conversation.dict())
        redis_db.set_in_progress_conversation_id(uid, new_conversation_id)

        detected_meeting_id = None

        # Only check for meetings if source is desktop
        if conversation_source == ConversationSource.desktop:
            now = datetime.now(timezone.utc)
            # Check ±2 minute window
            time_window = timedelta(minutes=2)
            start_range = now - time_window
            end_range = now + time_window

            meetings = calendar_db.get_meetings_in_time_range(uid, start_range, end_range)

            if len(meetings) == 1:
                # Exactly one meeting found
                detected_meeting_id = meetings[0]['id']
            elif len(meetings) > 1:
                closest_meeting = None
                smallest_diff = None

                for meeting in meetings:
                    # Calculate absolute time difference between meeting start and now
                    time_diff = abs((meeting['start_time'] - now).total_seconds())

                    if smallest_diff is None or time_diff < smallest_diff:
                        smallest_diff = time_diff
                        closest_meeting = meeting

                if closest_meeting:
                    detected_meeting_id = closest_meeting['id']
                    print(
                        f"Selected closest meeting: {closest_meeting['title']} (diff: {smallest_diff}s)",
                        uid,
                        session_id,
                    )

        # Store meeting association if auto-detected
        if detected_meeting_id:
            redis_db.set_conversation_meeting_id(new_conversation_id, detected_meeting_id)

        current_conversation_id = new_conversation_id

        print(f"Created new stub conversation: {new_conversation_id}", uid, session_id)

    async def _process_conversation(conversation_id: str):
        print("_process_conversation", uid, session_id)
        conversation = conversations_db.get_conversation(uid, conversation_id)
        if conversation:
            has_content = conversation.get('transcript_segments') or conversation.get('photos')
            if has_content:
                if PUSHER_ENABLED:
                    on_conversation_processing_started(conversation_id)
                    await request_conversation_processing(conversation_id)
                else:
                    await _create_conversation_fallback(conversation)
            else:
                print(f'Clean up the conversation {conversation_id}, reason: no content', uid, session_id)
                conversations_db.delete_conversation(uid, conversation_id)

    # Process existing conversations
    async def _prepare_in_progess_conversations():
        nonlocal current_conversation_id

        if existing_conversation := retrieve_in_progress_conversation(uid):
            finished_at = datetime.fromisoformat(existing_conversation['finished_at'].isoformat())
            seconds_since_last_segment = (datetime.now(timezone.utc) - finished_at).total_seconds()
            if seconds_since_last_segment >= conversation_creation_timeout:
                print(
                    f'Processing existing conversation {existing_conversation["id"]} (timed out: {seconds_since_last_segment:.1f}s)',
                    uid,
                    session_id,
                )
                await _create_new_in_progress_conversation()
                return existing_conversation["id"]

            # Continue with the existing conversation
            current_conversation_id = existing_conversation['id']
            print(
                f"Resuming conversation {current_conversation_id}. Will timeout in {conversation_creation_timeout - seconds_since_last_segment:.1f}s",
                uid,
                session_id,
            )
            return None

        # else
        await _create_new_in_progress_conversation()
        return None

    _send_message_event(
        MessageServiceStatusEvent(status="in_progress_conversations_processing", status_text="Processing Conversations")
    )
    timed_out_conversation_id = await _prepare_in_progess_conversations()

    def _process_speaker_assigned_segments(transcript_segments: List[TranscriptSegment]):
        for segment in transcript_segments:
            if segment.id in segment_person_assignment_map and not segment.is_user and not segment.person_id:
                person_id = segment_person_assignment_map[segment.id]
                if person_id == 'user':
                    segment.is_user = True
                    segment.person_id = None
                else:
                    segment.is_user = False
                    segment.person_id = person_id

    def _update_in_progress_conversation(
        conversation: Conversation,
        segments: List[TranscriptSegment],
        photos: List[ConversationPhoto],
        finished_at: datetime,
    ):
        starts, ends = (0, 0)

        if segments:
            conversation.transcript_segments, (starts, ends) = TranscriptSegment.combine_segments(
                conversation.transcript_segments, segments
            )
            _process_speaker_assigned_segments(conversation.transcript_segments[starts:ends])
            conversations_db.update_conversation_segments(
                uid, conversation.id, [segment.dict() for segment in conversation.transcript_segments]
            )

        if photos:
            conversations_db.store_conversation_photos(uid, conversation.id, photos)
            # Update source if we now have photos
            if conversation.source != ConversationSource.openglass:
                conversations_db.update_conversation(uid, conversation.id, {'source': ConversationSource.openglass})
                conversation.source = ConversationSource.openglass

        conversations_db.update_conversation_finished_at(uid, conversation.id, finished_at)
        return conversation, (starts, ends)

    # STT
    # Validate websocket_active before initiating STT
    if not websocket_active or websocket.client_state != WebSocketState.CONNECTED:
        print("websocket was closed", uid, session_id)
        if websocket.client_state == WebSocketState.CONNECTED:
            try:
                await websocket.close(code=websocket_close_code)
            except Exception as e:
                print(f"Error closing WebSocket: {e}", uid, session_id)
        return

    # Process STT
    soniox_socket = None
    soniox_profile_socket = None  # Temporary socket for speech profile phase
    speechmatics_socket = None
    deepgram_socket = None
    deepgram_profile_socket = None  # Temporary socket for speech profile phase
    speech_profile_complete = asyncio.Event()  # Signals when speech profile send is done

    def stream_transcript(segments):
        nonlocal realtime_segment_buffers
        realtime_segment_buffers.extend(segments)

    async def _process_stt():
        nonlocal websocket_close_code
        nonlocal soniox_socket
        nonlocal soniox_profile_socket
        nonlocal speechmatics_socket
        nonlocal deepgram_socket
        nonlocal deepgram_profile_socket
        try:
            if use_custom_stt:
                speech_profile_complete.set()  # No speech profile needed
                print(f"Custom STT mode enabled - using suggested transcripts from app", uid, session_id)
                return None

            speech_profile_preseconds = 0
            has_speech_profile = False
            if (
                (language == 'en' or language == 'auto')
                and (codec == 'opus' or codec == 'pcm16')
                and include_speech_profile
            ):
                has_speech_profile = get_user_has_speech_profile(uid)
                if has_speech_profile:
                    speech_profile_preseconds = SPEECH_PROFILE_FIXED_DURATION + SPEECH_PROFILE_PADDING_DURATION

            # If no speech profile, mark as complete immediately
            if not has_speech_profile:
                speech_profile_complete.set()

            # DEEPGRAM
            if stt_service == STTService.deepgram:
                deepgram_socket = await process_audio_dg(
                    stream_transcript,
                    stt_language,
                    sample_rate,
                    1,
                    preseconds=speech_profile_preseconds,
                    model=stt_model,
                    keywords=vocabulary[:100] if vocabulary else None,
                )
                if has_speech_profile:
                    deepgram_profile_socket = await process_audio_dg(
                        stream_transcript,
                        stt_language,
                        sample_rate,
                        1,
                        model=stt_model,
                        keywords=vocabulary[:100] if vocabulary else None,
                    )

            # SONIOX
            elif stt_service == STTService.soniox:
                # For multi-language detection, provide language hints if available
                hints = None
                if stt_language == 'multi' and language != 'multi':
                    # Include the original language as a hint for multi-language detection
                    hints = [language]

                soniox_socket = await process_audio_soniox(
                    stream_transcript,
                    sample_rate,
                    stt_language,
                    uid if include_speech_profile else None,
                    preseconds=speech_profile_preseconds,
                    language_hints=hints,
                )

                # Create a second socket for initial speech profile if needed
                if has_speech_profile:
                    soniox_profile_socket = await process_audio_soniox(
                        stream_transcript,
                        sample_rate,
                        stt_language,
                        uid if include_speech_profile else None,
                        language_hints=hints,
                    )

            # SPEECHMATICS
            elif stt_service == STTService.speechmatics:
                speechmatics_socket = await process_audio_speechmatics(
                    stream_transcript, sample_rate, stt_language, preseconds=speech_profile_preseconds
                )

            # Return background task to load and send speech profile
            if has_speech_profile:
                return _create_speech_profile_loader_task(lambda: websocket_active, sample_rate)
            return None

        except Exception as e:
            print(f"Initial processing error: {e}", uid, session_id)
            websocket_close_code = 1011
            await websocket.close(code=websocket_close_code)
            return None

    def _create_speech_profile_loader_task(is_active: Callable, audio_sample_rate: int):
        """Create async task to load speech profile and send to STT in background."""

        async def _process_speech_profile():
            try:
                # Check if we should stop before doing any work
                if not is_active():
                    return

                # Download file in background thread (not blocking main flow)
                file_path = await asyncio.to_thread(get_profile_audio_if_exists, uid)

                if not file_path:
                    print(f"Speech profile file not found for {uid}", session_id)
                    return

                # Send to appropriate STT socket with fixed duration padding
                if stt_service == STTService.deepgram and deepgram_socket:

                    async def deepgram_socket_send(data):
                        return deepgram_socket.send(data)

                    await send_initial_file_path(
                        file_path,
                        deepgram_socket_send,
                        is_active,
                        sample_rate=audio_sample_rate,
                        target_duration=SPEECH_PROFILE_FIXED_DURATION,
                    )
                elif stt_service == STTService.soniox and soniox_socket:
                    await send_initial_file_path(
                        file_path,
                        soniox_socket.send,
                        is_active,
                        sample_rate=audio_sample_rate,
                        target_duration=SPEECH_PROFILE_FIXED_DURATION,
                    )
                elif stt_service == STTService.speechmatics and speechmatics_socket:
                    await send_initial_file_path(
                        file_path,
                        speechmatics_socket.send,
                        is_active,
                        sample_rate=audio_sample_rate,
                        target_duration=SPEECH_PROFILE_FIXED_DURATION,
                    )

                # Stabilization delay before switching to main socket
                if is_active():
                    print(
                        f"Speech profile sent, waiting {SPEECH_PROFILE_STABILIZE_DELAY}s for stabilization",
                        uid,
                        session_id,
                    )
                    await asyncio.sleep(SPEECH_PROFILE_STABILIZE_DELAY)

            except Exception as e:
                print(f"Error loading speech profile in background: {e}", uid, session_id)
            finally:
                # Always signal completion so main socket routing can proceed
                speech_profile_complete.set()
                print(f"Speech profile complete flag set", uid, session_id)

        return asyncio.create_task(_process_speech_profile())

    # Pusher
    #
    def create_pusher_task_handler():
        nonlocal websocket_active
        nonlocal current_conversation_id

        pusher_ws = None
        pusher_connect_lock = asyncio.Lock()
        pusher_connected = False

        # Transcript
        segment_buffers = []

        last_synced_conversation_id = None

        # Conversation processing
        pending_conversation_requests = set()
        pending_request_event = asyncio.Event()

        def transcript_send(segments):
            nonlocal segment_buffers
            segment_buffers.extend(segments)

        async def request_conversation_processing(conversation_id: str):
            """Request pusher to process a conversation."""
            nonlocal pusher_ws, pusher_connected, pending_conversation_requests, pending_request_event
            if not pusher_connected or not pusher_ws:
                print(f"Pusher not connected, falling back to local processing for {conversation_id}", uid, session_id)
                return False
            try:
                pending_conversation_requests.add(conversation_id)
                pending_request_event.set()  # Signal the receiver
                data = bytearray()
                data.extend(struct.pack("I", 104))
                data.extend(bytes(json.dumps({"conversation_id": conversation_id, "language": language}), "utf-8"))
                await pusher_ws.send(data)
                print(f"Sent process_conversation request to pusher: {conversation_id}", uid, session_id)
                return True
            except Exception as e:
                print(f"Failed to send process_conversation request: {e}", uid, session_id)
                pending_conversation_requests.discard(conversation_id)
                return False

        async def _transcript_flush(auto_reconnect: bool = True):
            nonlocal segment_buffers
            nonlocal pusher_ws
            nonlocal pusher_connected
            if pusher_connected and pusher_ws and len(segment_buffers) > 0:
                try:
                    # 102|data
                    data = bytearray()
                    data.extend(struct.pack("I", 102))
                    data.extend(
                        bytes(
                            json.dumps({"segments": segment_buffers, "memory_id": current_conversation_id}),
                            "utf-8",
                        )
                    )
                    segment_buffers = []  # reset
                    await pusher_ws.send(data)
                except ConnectionClosed as e:
                    print(f"Pusher transcripts Connection closed: {e}", uid, session_id)
                    pusher_connected = False
                except Exception as e:
                    print(f"Pusher transcripts failed: {e}", uid, session_id)
            if auto_reconnect and pusher_connected is False and websocket_active:
                await connect()

        async def transcript_consume():
            nonlocal websocket_active
            nonlocal segment_buffers
            while websocket_active:
                await asyncio.sleep(1)
                if len(segment_buffers) > 0:
                    await _transcript_flush(auto_reconnect=True)

        # Audio bytes
        audio_buffers = bytearray()
        audio_buffer_last_received: float = None  # Track when last audio was received
        audio_bytes_enabled = (
            bool(get_audio_bytes_webhook_seconds(uid)) or is_audio_bytes_app_enabled(uid) or private_cloud_sync_enabled
        )

        def audio_bytes_send(audio_bytes: bytes, received_at: float):
            nonlocal audio_buffers, audio_buffer_last_received
            audio_buffers.extend(audio_bytes)
            audio_buffer_last_received = received_at

        async def _audio_bytes_flush(auto_reconnect: bool = True):
            nonlocal audio_buffers
            nonlocal audio_buffer_last_received
            nonlocal pusher_ws
            nonlocal pusher_connected
            nonlocal last_synced_conversation_id

            # Send conversation ID
            if (
                pusher_ws
                and current_conversation_id
                and (last_synced_conversation_id is None or current_conversation_id != last_synced_conversation_id)
            ):
                try:
                    # 103|conversation_id
                    data = bytearray()
                    data.extend(struct.pack("I", 103))
                    data.extend(bytes(current_conversation_id, "utf-8"))
                    await pusher_ws.send(data)
                    last_synced_conversation_id = current_conversation_id
                except ConnectionClosed as e:
                    print(f"Pusher audio_bytes Connection closed: {e}", uid, session_id)
                    pusher_connected = False
                except Exception as e:
                    print(f"Failed to send conversation_id to pusher: {e}", uid, session_id)

            # Send audio bytes
            if pusher_connected and pusher_ws and len(audio_buffers) > 0:
                try:
                    # Calculate buffer start time:
                    # buffer_start = last_received_time - buffer_duration
                    # buffer_duration = buffer_length_bytes / (sample_rate * 2 bytes per sample)
                    buffer_duration_seconds = len(audio_buffers) / (sample_rate * 2)
                    buffer_start_time = (audio_buffer_last_received or time.time()) - buffer_duration_seconds

                    # 101|timestamp(8 bytes double)|audio_data
                    data = bytearray()
                    data.extend(struct.pack("I", 101))
                    data.extend(struct.pack("d", buffer_start_time))
                    data.extend(audio_buffers.copy())
                    audio_buffers = bytearray()  # reset
                    await pusher_ws.send(data)
                except ConnectionClosed as e:
                    print(f"Pusher audio_bytes Connection closed: {e}", uid, session_id)
                    pusher_connected = False
                except Exception as e:
                    print(f"Pusher audio_bytes failed: {e}", uid, session_id)
            if auto_reconnect and pusher_connected is False and websocket_active:
                await connect()

        async def audio_bytes_consume():
            nonlocal websocket_active
            nonlocal audio_buffers
            nonlocal pusher_ws
            nonlocal pusher_connected
            while websocket_active:
                await asyncio.sleep(1)
                if len(audio_buffers) > 0:
                    await _audio_bytes_flush(auto_reconnect=True)

        async def pusher_receive():
            """Receive and handle messages from pusher."""
            nonlocal websocket_active, pusher_ws, pusher_connected, pending_conversation_requests, pending_request_event
            while websocket_active:
                # Wait efficiently until there's work to do
                if not pending_conversation_requests:
                    pending_request_event.clear()
                    try:
                        await asyncio.wait_for(pending_request_event.wait(), timeout=5.0)
                    except asyncio.TimeoutError:
                        continue  # Check websocket_active

                if not pusher_connected or not pusher_ws:
                    await asyncio.sleep(0.5)
                    continue

                try:
                    msg = await asyncio.wait_for(pusher_ws.recv(), timeout=5.0)
                    if not msg or len(msg) < 4:
                        continue
                    header_type = struct.unpack('<I', msg[:4])[0]

                    # Conversation processed response
                    if header_type == 201:
                        result = json.loads(msg[4:].decode("utf-8"))
                        conversation_id = result.get("conversation_id")
                        pending_conversation_requests.discard(conversation_id)

                        if "error" in result:
                            print(f"Conversation processing failed: {result['error']}", uid, session_id)
                            continue

                        if result.get("success"):
                            print(f"Conversation processed by pusher: {conversation_id}", uid, session_id)
                            on_conversation_processed(conversation_id)

                except asyncio.TimeoutError:
                    continue  # Check loop conditions again
                except asyncio.CancelledError:
                    break
                except ConnectionClosed as e:
                    print(f"Pusher receive connection closed: {e}", uid, session_id)
                    pusher_connected = False
                except Exception as e:
                    print(f"Pusher receive error: {e}", uid, session_id)
                    await asyncio.sleep(0.5)

                # Reconnect outside try/except (same pattern as flush functions)
                if pusher_connected is False and websocket_active:
                    await connect()

        async def _flush():
            await _audio_bytes_flush(auto_reconnect=False)
            await _transcript_flush(auto_reconnect=False)

        async def connect():
            nonlocal pusher_connected
            nonlocal pusher_connect_lock
            nonlocal pusher_ws
            async with pusher_connect_lock:
                if pusher_connected:
                    return
                # drain
                if pusher_ws:
                    try:
                        await pusher_ws.close()
                        pusher_ws = None
                    except Exception as e:
                        print(f"Pusher draining failed: {e}", uid, session_id)
                # connect
                await _connect()

        async def _connect():
            nonlocal pusher_ws
            nonlocal pusher_connected
            nonlocal current_conversation_id

            try:
                pusher_ws = await connect_to_trigger_pusher(
                    uid, sample_rate, retries=5, is_active=lambda: websocket_active
                )
                if pusher_ws is None:
                    # Session ended during connection attempt
                    return
                pusher_connected = True
            except Exception as e:
                print(f"Exception in connect: {e}")

        async def close(code: int = 1000):
            await _flush()
            if pusher_ws:
                await pusher_ws.close(code)

        async def send_speaker_sample_request(
            person_id: str,
            conv_id: str,
            segment_ids: List[str],
        ):
            """Send speaker sample extraction request to pusher with segment IDs."""
            nonlocal pusher_ws, pusher_connected
            if not pusher_connected or not pusher_ws:
                return
            try:
                data = bytearray()
                data.extend(struct.pack("I", 105))
                data.extend(
                    bytes(
                        json.dumps(
                            {
                                "person_id": person_id,
                                "conversation_id": conv_id,
                                "segment_ids": segment_ids,
                            }
                        ),
                        "utf-8",
                    )
                )
                await pusher_ws.send(data)
                print(
                    f"Sent speaker sample request to pusher: person={person_id}, {len(segment_ids)} segments",
                    uid,
                    session_id,
                )
            except Exception as e:
                print(f"Failed to send speaker sample request: {e}", uid, session_id)

        def is_connected():
            return pusher_connected

        return (
            connect,
            close,
            transcript_send,
            transcript_consume,
            audio_bytes_send if audio_bytes_enabled else None,
            audio_bytes_consume if audio_bytes_enabled else None,
            request_conversation_processing,
            pusher_receive,
            is_connected,
            send_speaker_sample_request,
        )

    transcript_send = None
    transcript_consume = None
    audio_bytes_send = None
    audio_bytes_consume = None
    pusher_close = None
    pusher_connect = None
    request_conversation_processing = None
    pusher_receive = None
    pusher_is_connected = None
    send_speaker_sample_request = None

    # Transcripts
    #
    translation_enabled = translation_language is not None
    language_cache = TranscriptSegmentLanguageCache()
    translation_service = TranslationService()

    async def translate(segments: List[TranscriptSegment], conversation_id: str):
        if not translation_language:
            return

        try:
            translated_segments = []
            for segment in segments:
                if not segment or not segment.id:
                    continue

                segment_text = segment.text.strip()
                if not segment_text:
                    continue

                # Language Detection
                if language_cache.is_in_target_language(segment.id, segment_text, translation_language):
                    continue

                # Translation
                translated_text = translation_service.translate_text_by_sentence(translation_language, segment_text)

                if translated_text == segment_text:
                    # If translation is same as original, it's likely in the target language.
                    # Delete from cache to allow re-evaluation if more text is added.
                    language_cache.delete_cache(segment.id)
                    continue

                # Create/Update Translation object
                translation = Translation(lang=translation_language, text=translated_text)
                if segment.translations is not None:
                    existing_translation_index = next(
                        (i for i, t in enumerate(segment.translations) if t.lang == language), None
                    )
                    if existing_translation_index is not None:
                        segment.translations[existing_translation_index] = translation
                    else:
                        segment.translations.append(translation)

                translated_segments.append(segment)

            if not translated_segments:
                return

            # Persist and notify
            conversation = conversations_db.get_conversation(uid, conversation_id)
            if conversation:
                should_update = False
                for segment in translated_segments:
                    for i, existing_segment in enumerate(conversation['transcript_segments']):
                        if existing_segment['id'] == segment.id:
                            conversation['transcript_segments'][i]['translations'] = segment.dict()['translations']
                            should_update = True
                            break
                if should_update:
                    conversations_db.update_conversation_segments(
                        uid, conversation_id, conversation['transcript_segments']
                    )

            if websocket_active:
                _send_message_event(TranslationEvent(segments=[s.dict() for s in translated_segments]))

        except Exception as e:
            print(f"Translation error: {e}", uid, session_id)

    async def conversation_lifecycle_manager():
        """Background task that checks conversation timeout and triggers processing every 5 seconds."""
        nonlocal websocket_active, current_conversation_id, conversation_creation_timeout

        print(f"Starting conversation lifecycle manager (timeout: {conversation_creation_timeout}s)", uid, session_id)

        while websocket_active:
            await asyncio.sleep(5)

            if not current_conversation_id:
                print(f"WARN: the current conversation is not valid", uid, session_id)
                continue

            conversation = conversations_db.get_conversation(uid, current_conversation_id)
            if not conversation:
                print(f"WARN: the current conversation is not found (id: {current_conversation_id})", uid, session_id)
                await _create_new_in_progress_conversation()
                continue

            # Check if conversation status is not in_progress
            if conversation.get('status') != ConversationStatus.in_progress:
                print(
                    f"WARN: conversation {current_conversation_id} status is {conversation.get('status')}, not in_progress. Creating new conversation.",
                    uid,
                    session_id,
                )
                await _create_new_in_progress_conversation()
                continue

            # Check if conversation should be processed
            finished_at = datetime.fromisoformat(conversation['finished_at'].isoformat())
            seconds_since_last_update = (datetime.now(timezone.utc) - finished_at).total_seconds()
            if seconds_since_last_update >= conversation_creation_timeout:
                print(
                    f"Conversation {current_conversation_id} timeout reached ({seconds_since_last_update:.1f}s). Processing...",
                    uid,
                    session_id,
                )
                await _process_conversation(current_conversation_id)
                await _create_new_in_progress_conversation()

    async def speaker_identification_task():
        """Consume segment queue, accumulate per speaker, trigger match when ready."""
        nonlocal websocket_active, speaker_to_person_map
        nonlocal person_embeddings_cache, audio_ring_buffer

        if not speaker_id_enabled:
            return

        # Load person embeddings
        try:
            people = user_db.get_people(uid)
            for person in people:
                emb = person.get('speaker_embedding')
                if emb:
                    person_embeddings_cache[person['id']] = {
                        'embedding': np.array(emb, dtype=np.float32).reshape(1, -1),
                        'name': person['name'],
                    }
            print(f"Speaker ID: loaded {len(person_embeddings_cache)} person embeddings", uid, session_id)
        except Exception as e:
            print(f"Speaker ID: failed to load embeddings: {e}", uid, session_id)
            return

        if not person_embeddings_cache:
            print("Speaker ID: no stored embeddings, task disabled", uid, session_id)
            return

        # Consume loop
        while websocket_active:
            try:
                seg = await asyncio.wait_for(speaker_id_segment_queue.get(), timeout=2.0)
            except asyncio.TimeoutError:
                continue

            speaker_id = seg['speaker_id']

            # Skip if already resolved
            if speaker_id in speaker_to_person_map:
                continue

            duration = seg['duration']
            if duration >= SPEAKER_ID_MIN_AUDIO:
                asyncio.create_task(_match_speaker_embedding(speaker_id, seg))

        print("Speaker ID task ended", uid, session_id)

    async def _match_speaker_embedding(speaker_id: int, segment: dict):
        """Extract audio from ring buffer and match against stored embeddings."""
        nonlocal speaker_to_person_map, segment_person_assignment_map, audio_ring_buffer

        try:
            seg_start = segment['abs_start']
            seg_end = segment['abs_end']
            duration = segment['duration']

            if duration < SPEAKER_ID_MIN_AUDIO:
                print(f"Speaker ID: segment too short ({duration:.1f}s)", uid, session_id)
                return

            # Get buffer time range
            time_range = audio_ring_buffer.get_time_range()
            if time_range is None:
                print(f"Speaker ID: buffer empty", uid, session_id)
                return

            buffer_start_ts, buffer_end_ts = time_range

            # Calculate extraction range - stay within segment bounds, max 10 seconds from center
            MAX_EXTRACT_DURATION = 10.0

            if duration <= MAX_EXTRACT_DURATION:
                # Segment fits within max duration, use full segment
                extract_start = seg_start
                extract_end = seg_end
            else:
                # Segment is longer than max, extract 10s from center
                center = (seg_start + seg_end) / 2
                half_duration = MAX_EXTRACT_DURATION / 2
                extract_start = center - half_duration
                extract_end = center + half_duration

            # Clamp to buffer availability
            extract_start = max(buffer_start_ts, extract_start)
            extract_end = min(buffer_end_ts, extract_end)

            if extract_end <= extract_start:
                print(f"Speaker ID: no audio to extract", uid, session_id)
                return

            # Extract only the needed bytes directly from ring buffer
            pcm_data = audio_ring_buffer.extract(extract_start, extract_end)
            if not pcm_data:
                print(f"Speaker ID: failed to extract audio", uid, session_id)
                return

            # Convert PCM to numpy for WAV encoding
            samples = np.frombuffer(pcm_data, dtype=np.int16)

            # Convert PCM to WAV using av
            output_buffer = io.BytesIO()
            output_container = av.open(output_buffer, mode='w', format='wav')
            output_stream = output_container.add_stream('pcm_s16le', rate=sample_rate)
            output_stream.layout = 'mono'

            frame = av.AudioFrame.from_ndarray(samples.reshape(1, -1), format='s16', layout='mono')
            frame.rate = sample_rate

            for packet in output_stream.encode(frame):
                output_container.mux(packet)
            for packet in output_stream.encode():
                output_container.mux(packet)

            output_container.close()
            wav_bytes = output_buffer.getvalue()

            # Extract embedding (API call)
            query_embedding = await asyncio.to_thread(extract_embedding_from_bytes, wav_bytes, "query.wav")

            # Find best match
            best_match = None
            best_distance = float('inf')

            # Print all candidates with scores for tuning
            print(
                f"Speaker ID: comparing speaker {speaker_id} against {len(person_embeddings_cache)} people:",
                uid,
                session_id,
            )
            for person_id, data in person_embeddings_cache.items():
                distance = compare_embeddings(query_embedding, data['embedding'])
                print(f"  - {data['name']}: {distance:.4f}", uid, session_id)
                if distance < best_distance:
                    best_distance = distance
                    best_match = (person_id, data['name'])

            if best_match and best_distance < SPEAKER_MATCH_THRESHOLD:
                person_id, person_name = best_match
                print(
                    f"Speaker ID: speaker {speaker_id} -> {person_name} (distance={best_distance:.3f})", uid, session_id
                )

                # Store for session consistency
                speaker_to_person_map[speaker_id] = (person_id, person_name)

                # Auto-assign processed segment
                segment_person_assignment_map[segment['id']] = person_id

                # Notify client
                _send_message_event(
                    SpeakerLabelSuggestionEvent(
                        speaker_id=speaker_id,
                        person_id=person_id,
                        person_name=person_name,
                        segment_id=segment['id'],
                    )
                )
            else:
                print(f"Speaker ID: speaker {speaker_id} no match (best={best_distance:.3f})", uid, session_id)

        except Exception as e:
            print(f"Speaker ID: match error for speaker {speaker_id}: {e}", uid, session_id)

    async def stream_transcript_process():
        nonlocal websocket_active, realtime_segment_buffers, realtime_photo_buffers, websocket
        nonlocal current_conversation_id, translation_enabled, speaker_to_person_map, suggested_segments, words_transcribed_since_last_record, last_transcript_time

        while websocket_active or len(realtime_segment_buffers) > 0 or len(realtime_photo_buffers) > 0:
            await asyncio.sleep(0.6)

            if not realtime_segment_buffers and not realtime_photo_buffers:
                continue

            segments_to_process = realtime_segment_buffers.copy()
            realtime_segment_buffers = []

            photos_to_process = realtime_photo_buffers.copy()
            realtime_photo_buffers = []

            finished_at = datetime.now(timezone.utc)

            # Get conversation
            conversation_data = conversations_db.get_conversation(uid, current_conversation_id)
            if not conversation_data:
                print(
                    f"Warning: conversation {current_conversation_id} not found during segment processing",
                    uid,
                    session_id,
                )
                continue

            # Guard first_audio_byte_timestamp must be set
            if not first_audio_byte_timestamp:
                print(f"Warning: first_audio_byte_timestamp not set, skipping segment processing", uid, session_id)
                continue

            transcript_segments = []
            if segments_to_process:
                last_transcript_time = time.time()

                # If conversation has no segments yet, set started_at based on when first speech occurred
                if not conversation_data.get('transcript_segments'):
                    first_speech_timestamp = first_audio_byte_timestamp + segments_to_process[0]["start"]
                    new_started_at = datetime.fromtimestamp(first_speech_timestamp, tz=timezone.utc)
                    conversations_db.update_conversation(uid, current_conversation_id, {'started_at': new_started_at})
                    conversation_data['started_at'] = new_started_at

                # Calculate unified time offset: audio stream start relative to conversation start
                conversation_started_at = conversation_data['started_at']
                if isinstance(conversation_started_at, str):
                    conversation_started_at = datetime.fromisoformat(conversation_started_at)
                time_offset = first_audio_byte_timestamp - conversation_started_at.timestamp()

                # Apply offset to all segments
                for i, segment in enumerate(segments_to_process):
                    segment["start"] += time_offset
                    segment["end"] += time_offset
                    segments_to_process[i] = segment

                newly_processed_segments = []
                for s in segments_to_process:
                    segment = TranscriptSegment(**s, speech_profile_processed=speech_profile_complete.is_set())
                    # In onboarding mode, force is_user=True for non-Omi segments (user's answers)
                    if onboarding_mode and s.get('speaker_id') != OnboardingHandler.OMI_SPEAKER_ID:
                        segment.is_user = True
                    newly_processed_segments.append(segment)
                words_transcribed = len(" ".join([seg.text for seg in newly_processed_segments]).split())
                if words_transcribed > 0:
                    words_transcribed_since_last_record += words_transcribed

                for seg in newly_processed_segments:
                    current_session_segments[seg.id] = seg.speech_profile_processed
                transcript_segments, _ = TranscriptSegment.combine_segments([], newly_processed_segments)

            # Update transcript segments
            conversation = Conversation(**conversation_data)
            result = _update_in_progress_conversation(conversation, transcript_segments, photos_to_process, finished_at)
            if not result or not result[0]:
                continue
            conversation, (starts, ends) = result

            if transcript_segments:
                updates_segments = [segment.dict() for segment in conversation.transcript_segments[starts:ends]]
                await websocket.send_json(updates_segments)

                if transcript_send is not None and user_has_credits:
                    transcript_send([segment.dict() for segment in transcript_segments])

                # Onboarding: pass segments to handler for answer detection
                if onboarding_handler and not onboarding_handler.completed:
                    onboarding_handler.on_segments_received([s.dict() for s in transcript_segments])

                if translation_enabled:
                    await translate(conversation.transcript_segments[starts:ends], conversation.id)

                # Speaker detection
                for segment in conversation.transcript_segments[starts:ends]:
                    if segment.person_id or segment.is_user or segment.id in suggested_segments:
                        continue

                    # Session consistency speaker identification
                    if speech_profile_complete.is_set():
                        if segment.speaker_id in speaker_to_person_map:
                            person_id, person_name = speaker_to_person_map[segment.speaker_id]
                            _send_message_event(
                                SpeakerLabelSuggestionEvent(
                                    speaker_id=segment.speaker_id,
                                    person_id=person_id,
                                    person_name=person_name,
                                    segment_id=segment.id,
                                )
                            )
                            suggested_segments.add(segment.id)
                            continue

                    # Embeding id speaker indentification
                    if speaker_id_enabled and person_embeddings_cache:
                        started_at_ts = conversation.started_at.timestamp()
                        if (
                            segment.speaker_id is not None
                            and not segment.person_id
                            and not segment.is_user
                            and segment.speaker_id not in speaker_to_person_map
                        ):
                            try:
                                speaker_id_segment_queue.put_nowait(
                                    {
                                        'id': segment.id,
                                        'speaker_id': segment.speaker_id,
                                        'abs_start': first_audio_byte_timestamp
                                        + segment.start
                                        - time_offset,  # raw start/end
                                        'abs_end': first_audio_byte_timestamp + segment.end - time_offset,
                                        'duration': segment.end - segment.start,
                                        'text': segment.text,  # TODO: remove
                                    }
                                )
                            except asyncio.QueueFull:
                                pass  # Drop if queue is full

                    # Text-based detection
                    detected_name = detect_speaker_from_text(segment.text)
                    if detected_name:
                        person = user_db.get_person_by_name(uid, detected_name)
                        person_id = person['id'] if person else ''
                        _send_message_event(
                            SpeakerLabelSuggestionEvent(
                                speaker_id=segment.speaker_id,
                                person_id=person_id,
                                person_name=detected_name,
                                segment_id=segment.id,
                            )
                        )
                        suggested_segments.add(segment.id)

    image_chunks = {str: any}  # A temporary in-memory cache for image chunks

    async def process_photo(
        uid: str, image_b64: str, temp_id: str, send_event_func, photo_buffer: list[ConversationPhoto]
    ):
        from utils.llm.openglass import describe_image

        photo_id = str(uuid.uuid4())
        await send_event_func(PhotoProcessingEvent(temp_id=temp_id, photo_id=photo_id))

        try:
            description = await describe_image(image_b64)
            discarded = not description or not description.strip()
        except Exception as e:
            print(f"Error describing image: {e}", uid, session_id)
            description = "Could not generate description."
            discarded = True

        final_photo = ConversationPhoto(id=photo_id, base64=image_b64, description=description, discarded=discarded)
        photo_buffer.append(final_photo)
        await send_event_func(PhotoDescribedEvent(photo_id=photo_id, description=description, discarded=discarded))

    async def handle_image_chunk(
        uid: str, chunk_data: dict, image_chunks_cache: dict, send_event_func, photo_buffer: list[ConversationPhoto]
    ):
        temp_id = chunk_data.get('id')
        index = chunk_data.get('index')
        total = chunk_data.get('total')
        data = chunk_data.get('data')

        if not temp_id or not isinstance(index, int) or not isinstance(total, int) or not data:
            print(f"Invalid image chunk received: {chunk_data}", uid, session_id)
            return

        if temp_id not in image_chunks_cache:
            if total <= 0:
                return
            image_chunks_cache[temp_id] = [None] * total

        if index < total and image_chunks_cache[temp_id][index] is None:
            image_chunks_cache[temp_id][index] = data

        if all(chunk is not None for chunk in image_chunks_cache[temp_id]):
            b64_image_data = "".join(image_chunks_cache[temp_id])
            del image_chunks_cache[temp_id]
            safe_create_task(process_photo(uid, b64_image_data, temp_id, send_event_func, photo_buffer))

    # Initialize decoders based on codec
    opus_decoder = None
    aac_decoder = None
    lc3_decoder = None

    if codec == 'opus':
        opus_decoder = opuslib.Decoder(sample_rate, 1)
    elif codec == 'aac':
        aac_decoder = AACDecoder(uid=uid, session_id=session_id, sample_rate=sample_rate, channels=channels)
    elif codec == 'lc3':
        lc3_decoder = lc3.Decoder(lc3_frame_duration_us, sample_rate)

    async def receive_data(dg_socket, dg_profile_socket, soniox_sock, soniox_profile_sock, speechmatics_sock):
        nonlocal websocket_active, websocket_close_code, last_audio_received_time, last_activity_time, current_conversation_id
        nonlocal realtime_photo_buffers, speaker_to_person_map, first_audio_byte_timestamp, last_usage_record_timestamp
        nonlocal soniox_profile_socket, deepgram_profile_socket, audio_ring_buffer

        timer_start = time.time()
        last_audio_received_time = timer_start
        last_activity_time = timer_start

        # STT audio buffer - accumulate 30ms before sending for better transcription quality
        stt_audio_buffer = bytearray()
        stt_buffer_flush_size = int(sample_rate * 2 * 0.03)  # 30ms at 16-bit mono (e.g., 6400 bytes at 16kHz)

        async def flush_stt_buffer(force: bool = False):
            nonlocal stt_audio_buffer, soniox_profile_socket, deepgram_profile_socket

            if not stt_audio_buffer:
                return
            if not force and len(stt_audio_buffer) < stt_buffer_flush_size:
                return

            chunk = bytes(stt_audio_buffer)
            stt_audio_buffer.clear()

            # Use event-based routing instead of time-based
            profile_complete = speech_profile_complete.is_set()

            if dg_socket is not None:
                if profile_complete or not deepgram_profile_socket:
                    dg_socket.send(chunk)
                    if deepgram_profile_socket:
                        print('Scheduling delayed close of deepgram_profile_socket', uid, session_id)
                        socket_to_close = deepgram_profile_socket
                        deepgram_profile_socket = None  # Stop sending immediately

                        async def close_dg_profile():
                            await asyncio.sleep(5)
                            socket_to_close.finish()
                            print('Closed deepgram_profile_socket after 5s delay', uid, session_id)

                        asyncio.create_task(close_dg_profile())
                else:
                    deepgram_profile_socket.send(chunk)

            if soniox_sock is not None:
                if profile_complete or not soniox_profile_socket:
                    await soniox_sock.send(chunk)
                    if soniox_profile_socket:
                        print('Scheduling delayed close of soniox_profile_socket', uid, session_id)
                        socket_to_close = soniox_profile_socket
                        soniox_profile_socket = None  # Stop sending immediately

                        async def close_soniox_profile():
                            await asyncio.sleep(5)
                            await socket_to_close.close()
                            print('Closed soniox_profile_socket after 5s delay', uid, session_id)

                        asyncio.create_task(close_soniox_profile())
                else:
                    await soniox_profile_socket.send(chunk)

            if speechmatics_sock is not None:
                await speechmatics_sock.send(chunk)

        try:
            while websocket_active:
                message = await websocket.receive()
                last_activity_time = time.time()

                # Handle client disconnect
                if message.get("type") == "websocket.disconnect":
                    close_code = message.get("code", 1000)
                    close_reason = {
                        1000: "normal_closure",
                        1001: "going_away_os_or_background",
                        1006: "abnormal_closure",
                        1011: "server_error",
                    }.get(close_code, "unknown")
                    print(f"Client disconnected: code={close_code} reason={close_reason}", uid, session_id)
                    break

                if message.get("bytes") is not None:

                    data = message.get("bytes")
                    if len(data) <= 2:  # Ping/keepalive, 0x8a 0x00
                        continue

                    last_audio_received_time = time.time()

                    if first_audio_byte_timestamp is None:
                        first_audio_byte_timestamp = last_audio_received_time
                        last_usage_record_timestamp = first_audio_byte_timestamp

                    # Decode based on codec
                    if codec == 'opus' and sample_rate == 16000:
                        try:
                            data = opus_decoder.decode(bytes(data), frame_size=frame_size)
                            if not data:
                                continue
                        except Exception as e:
                            print(f"[OPUS] Decoding error: {e}", uid, session_id)
                            continue
                    elif codec == 'aac':
                        try:
                            data = aac_decoder.decode(bytes(data))
                            if not data:
                                continue
                        except Exception as e:
                            print(f"[AAC] Decoding error: {e}", uid, session_id)
                            continue
                    elif codec == 'lc3':
                        try:
                            # Decode LC3 frame to PCM
                            # lc3.decode returns PCM bytes directly with bit_depth=16
                            pcm_bytes = lc3_decoder.decode(bytes(data), bit_depth=16)
                            if not pcm_bytes:
                                continue
                            data = pcm_bytes
                        except Exception as e:
                            print(
                                f"[LC3] Decoding error: {e} | "
                                f"Data size: {len(data)} bytes (expected: {lc3_chunk_size}) | "
                                f"Frame duration: {lc3_frame_duration_us}μs | "
                                f"Sample rate: {sample_rate}Hz",
                                uid,
                                session_id,
                            )
                            continue

                    # Feed ring buffer for speaker identification
                    if audio_ring_buffer is not None:
                        audio_ring_buffer.write(data, last_audio_received_time)

                    if not use_custom_stt:
                        stt_audio_buffer.extend(data)
                        await flush_stt_buffer()

                    if audio_bytes_send is not None:
                        audio_bytes_send(data, last_audio_received_time)

                elif message.get("text") is not None:
                    try:
                        json_data = json.loads(message.get("text"))
                        if json_data.get('type') == 'image_chunk':
                            await handle_image_chunk(
                                uid, json_data, image_chunks, _asend_message_event, realtime_photo_buffers
                            )
                        elif json_data.get('type') == 'skip_question':
                            if onboarding_handler and not onboarding_handler.completed:
                                await onboarding_handler.skip_current_question()
                        elif json_data.get('type') == 'suggested_transcript':
                            if use_custom_stt:
                                suggested_segments = json_data.get('segments', [])
                                stt_provider = json_data.get('stt_provider')
                                if suggested_segments:
                                    # Attach stt_provider to each segment
                                    if stt_provider:
                                        for seg in suggested_segments:
                                            seg['stt_provider'] = stt_provider
                                    stream_transcript(suggested_segments)
                        elif json_data.get('type') == 'speaker_assigned':
                            segment_ids = json_data.get('segment_ids', [])
                            can_assign = False
                            if segment_ids:
                                for sid in segment_ids:
                                    if sid in current_session_segments and current_session_segments[sid]:
                                        can_assign = True
                                        break

                            if can_assign:
                                speaker_id = json_data.get('speaker_id')
                                person_id = json_data.get('person_id')
                                person_name = json_data.get('person_name')
                                if speaker_id is not None and person_id is not None and person_name is not None:
                                    speaker_to_person_map[speaker_id] = (person_id, person_name)
                                    for sid in segment_ids:
                                        segment_person_assignment_map[sid] = person_id
                                    print(
                                        f"Speaker {speaker_id} assigned to {person_name} ({person_id})", uid, session_id
                                    )

                                    # Forward to pusher for speech sample extraction (non-blocking)
                                    # Only for real people (not 'user') and when private cloud sync is enabled
                                    if (
                                        person_id
                                        and person_id != 'user'
                                        and private_cloud_sync_enabled
                                        and send_speaker_sample_request is not None
                                        and current_conversation_id
                                    ):
                                        asyncio.create_task(
                                            send_speaker_sample_request(
                                                person_id=person_id,
                                                conv_id=current_conversation_id,
                                                segment_ids=segment_ids,
                                            )
                                        )
                            else:
                                print(
                                    "Speaker assignment ignored: no segment_ids or no speech-profile-processed segments.",
                                    uid,
                                    session_id,
                                )
                    except json.JSONDecodeError:
                        print(f"Received non-json text message: {message.get('text')}", uid, session_id)

        except WebSocketDisconnect:
            print("WebSocket disconnected (exception)", uid, session_id)
        except Exception as e:
            print(f'Could not process data: error {e}', uid, session_id)
            websocket_close_code = 1011
        finally:
            # Flush any remaining audio in buffer to STT
            if not use_custom_stt:
                await flush_stt_buffer(force=True)
            websocket_active = False

    # Start
    #
    try:
        # Init STT (fast - profile file loads and sends in background)
        _send_message_event(MessageServiceStatusEvent(status="stt_initiating", status_text="STT Service Starting"))
        speech_profile_task = await _process_stt()

        # Init pusher
        pusher_tasks = []
        if PUSHER_ENABLED:
            (
                pusher_connect,
                pusher_close,
                transcript_send,
                transcript_consume,
                audio_bytes_send,
                audio_bytes_consume,
                request_conversation_processing,
                pusher_receive,
                pusher_is_connected,
                send_speaker_sample_request,
            ) = create_pusher_task_handler()

            # Pusher connection
            await pusher_connect()
            if not pusher_is_connected():
                print("Pusher connection failed after retries", uid, session_id)
                await websocket.close(code=1011, reason="Pusher connection failed")
                return

            # Pusher tasks
            if transcript_consume is not None:
                pusher_tasks.append(asyncio.create_task(transcript_consume()))
            if audio_bytes_consume is not None:
                pusher_tasks.append(asyncio.create_task(audio_bytes_consume()))
            if pusher_receive is not None:
                pusher_tasks.append(asyncio.create_task(pusher_receive()))

        # Tasks
        data_process_task = asyncio.create_task(
            receive_data(
                deepgram_socket, deepgram_profile_socket, soniox_socket, soniox_profile_socket, speechmatics_socket
            )
        )
        stream_transcript_task = asyncio.create_task(stream_transcript_process())
        record_usage_task = asyncio.create_task(_record_usage_periodically())
        lifecycle_manager_task = asyncio.create_task(conversation_lifecycle_manager())
        pending_conversations_task = asyncio.create_task(process_pending_conversations(timed_out_conversation_id))
        speaker_id_task = asyncio.create_task(speaker_identification_task())

        _send_message_event(MessageServiceStatusEvent(status="ready"))

        tasks = [
            data_process_task,
            stream_transcript_task,
            heartbeat_task,
            record_usage_task,
            lifecycle_manager_task,
            pending_conversations_task,
            speaker_id_task,
        ] + pusher_tasks

        # Add speech profile task to run concurrently (sends profile audio in background)
        if speech_profile_task:
            tasks.append(speech_profile_task)

        await asyncio.gather(*tasks)

    except Exception as e:
        print(f"Error during WebSocket operation: {e}", uid, session_id)
    finally:
        if not use_custom_stt and last_usage_record_timestamp:
            transcription_seconds = int(time.time() - last_usage_record_timestamp)
            words_to_record = words_transcribed_since_last_record
            if transcription_seconds > 0 or words_to_record > 0:
                record_usage(uid, transcription_seconds=transcription_seconds, words_transcribed=words_to_record)
        websocket_active = False

        # STT sockets
        try:
            if deepgram_socket:
                deepgram_socket.finish()
            if deepgram_profile_socket:
                deepgram_profile_socket.finish()
            if soniox_socket:
                await soniox_socket.close()
            if soniox_profile_socket:
                await soniox_profile_socket.close()
            if speechmatics_socket:
                await speechmatics_socket.close()
        except Exception as e:
            print(f"Error closing STT sockets: {e}", uid, session_id)

        # Client sockets
        if websocket.client_state == WebSocketState.CONNECTED:
            try:
                await websocket.close(code=websocket_close_code)
            except Exception as e:
                print(f"Error closing Client WebSocket: {e}", uid, session_id)

        # Pusher sockets
        if pusher_close is not None:
            try:
                await pusher_close()
            except Exception as e:
                print(f"Error closing Pusher: {e}", uid, session_id)

        # Clean up onboarding handler
        if onboarding_handler:
            onboarding_handler.cleanup()

        # Clean up collections to aid garbage collection
        try:
            locked_conversation_ids.clear()
            speaker_to_person_map.clear()
            segment_person_assignment_map.clear()
            current_session_segments.clear()
            suggested_segments.clear()
            realtime_segment_buffers.clear()
            realtime_photo_buffers.clear()
            image_chunks.clear()
            person_embeddings_cache.clear()
        except NameError as e:
            # Variables might not be defined if an error occurred early
            print(f"Cleanup error (safe to ignore): {e}", uid, session_id)

    print("_listen ended", uid, session_id)


@router.websocket("/v4/listen")
async def listen_handler(
    websocket: WebSocket,
    uid: str = Depends(auth.get_current_user_uid),
    language: str = 'en',
    sample_rate: int = 8000,
    codec: str = 'pcm8',
    channels: int = 1,
    include_speech_profile: bool = True,
    stt_service: Optional[STTService] = None,
    conversation_timeout: int = 120,
    source: Optional[str] = None,
    custom_stt: str = 'disabled',
    onboarding: str = 'disabled',
):
    custom_stt_mode = CustomSttMode.enabled if custom_stt == 'enabled' else CustomSttMode.disabled
    onboarding_mode = onboarding == 'enabled'
    await _listen(
        websocket,
        uid,
        language,
        sample_rate,
        codec,
        channels,
        include_speech_profile,
        None,
        conversation_timeout=conversation_timeout,
        source=source,
        custom_stt_mode=custom_stt_mode,
        onboarding_mode=onboarding_mode,
    )
