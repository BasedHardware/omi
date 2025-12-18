import asyncio
import io
import json
import os
import struct
import time
import uuid
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple, Callable

import av
import opuslib  # type: ignore
import webrtcvad  # type: ignore

import lc3  # lc3py

from fastapi import APIRouter, Depends
from fastapi.websockets import WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState
from websockets.exceptions import ConnectionClosed

# Suppress FFmpeg duration estimation warnings
av.logging.set_level(av.logging.ERROR)

import database.conversations as conversations_db
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
from utils.subscription import has_transcription_credits
from utils.translation import TranslationService
from utils.translation_cache import TranscriptSegmentLanguageCache
from utils.webhooks import get_audio_bytes_webhook_seconds

router = APIRouter()


PUSHER_ENABLED = bool(os.getenv('HOSTED_PUSHER_API_URL'))


class CustomSttMode(str, Enum):
    disabled = "disabled"
    enabled = "enabled"


class AACDecoder:

    def __init__(self, uid: str = '', session_id: str = '', sample_rate: int = 16000, channels: int = 1):
        self.uid = uid
        self.session_id = session_id

        # Initialize codec context immediately
        self.codec_context = av.CodecContext.create('aac', 'r')

        # Initialize resampler immediately
        from av.audio.resampler import AudioResampler

        target_layout = 'mono' if channels == 1 else 'stereo'
        self.resampler = AudioResampler(format='s16', layout=target_layout, rate=sample_rate)

    def decode(self, aac_data: bytes) -> bytes:
        """Decode AAC frame using persistent codec context.

        Args:
            aac_data: Complete AAC frame with ADTS header

        Returns:
            PCM data as bytes
        """
        if not aac_data:
            return b''

        try:
            # Create packet and decode
            packet = av.Packet(aac_data)
            frames = self.codec_context.decode(packet)

            if not frames:
                return b''

            # Resample and collect PCM data
            pcm_chunks = []
            for frame in frames:
                resampled_frames = self.resampler.resample(frame)
                for resampled_frame in resampled_frames:
                    frame_array = resampled_frame.to_ndarray()
                    if frame_array.ndim > 1:
                        frame_array = frame_array.T.flatten()
                    pcm_chunks.append(frame_array.tobytes())

            return b''.join(pcm_chunks)

        except (EOFError, av.AVError):
            # Expected for incomplete frames, return empty
            return b''
        except Exception as e:
            print(f"[AAC] Decode error: {e}", self.uid, self.session_id)
            return b''


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
    )

    use_custom_stt = custom_stt_mode == CustomSttMode.enabled

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
    locked_conversation_ids: Set[str] = set()
    speaker_to_person_map: Dict[int, Tuple[str, str]] = {}
    segment_person_assignment_map: Dict[str, str] = {}
    current_session_segments: Dict[str, bool] = {}  # Store only speech_profile_processed status
    suggested_segments: Set[str] = set()
    first_audio_byte_timestamp: Optional[float] = None
    last_usage_record_timestamp: Optional[float] = None
    words_transcribed_since_last_record: int = 0
    last_transcript_time: Optional[float] = None
    seconds_to_trim = None
    seconds_to_add = None
    current_conversation_id = None

    async def _record_usage_periodically():
        nonlocal websocket_active, last_usage_record_timestamp, words_transcribed_since_last_record
        nonlocal last_audio_received_time, last_transcript_time, user_has_credits

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

            if not use_custom_stt and not has_transcription_credits(uid):
                user_has_credits = False
                try:
                    await send_credit_limit_notification(uid)
                except Exception as e:
                    print(f"Error sending credit limit notification: {e}", uid, session_id)

                if current_conversation_id and current_conversation_id not in locked_conversation_ids:
                    conversation = conversations_db.get_conversation(uid, current_conversation_id)
                    if conversation and conversation['status'] == ConversationStatus.in_progress:
                        conversation_id = conversation['id']
                        print(f"Locking conversation {conversation_id} due to transcription limit.", uid, session_id)
                        conversations_db.update_conversation(uid, conversation_id, {'is_locked': True})
                        locked_conversation_ids.add(conversation_id)
            elif not use_custom_stt:
                user_has_credits = True

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
        nonlocal seconds_to_trim
        nonlocal seconds_to_add
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
        current_conversation_id = new_conversation_id
        seconds_to_trim = None
        seconds_to_add = None

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
        nonlocal seconds_to_add
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
            started_at = datetime.fromisoformat(existing_conversation['started_at'].isoformat())
            seconds_to_add = (
                (datetime.now(timezone.utc) - started_at).total_seconds()
                if existing_conversation['transcript_segments']
                else None
            )
            print(
                f"Resuming conversation {current_conversation_id} with {(seconds_to_add if seconds_to_add else 0):.1f}s offset. Will timeout in {conversation_creation_timeout - seconds_since_last_segment:.1f}s",
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
        conversation_id: str, segments: List[TranscriptSegment], photos: List[ConversationPhoto], finished_at: datetime
    ):
        """Update the current in-progress conversation with new segments/photos."""
        conversation_data = conversations_db.get_conversation(uid, conversation_id)
        if not conversation_data:
            print(f"Warning: conversation {conversation_id} not found", uid, session_id)
            return None, (0, 0)

        conversation = Conversation(**conversation_data)
        starts, ends = (0, 0)

        if segments:
            # If conversation has no segments yet but we're adding some, update started_at
            if not conversation.transcript_segments:
                started_at = finished_at - timedelta(seconds=max(0, segments[-1].end))
                conversations_db.update_conversation(uid, conversation.id, {'started_at': started_at})
                conversation.started_at = started_at

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

    realtime_segment_buffers = []
    realtime_photo_buffers: list[ConversationPhoto] = []

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
        audio_bytes_enabled = (
            bool(get_audio_bytes_webhook_seconds(uid)) or is_audio_bytes_app_enabled(uid) or private_cloud_sync_enabled
        )

        def audio_bytes_send(audio_bytes):
            nonlocal audio_buffers
            audio_buffers.extend(audio_bytes)

        async def _audio_bytes_flush(auto_reconnect: bool = True):
            nonlocal audio_buffers
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
                    # 101|data
                    data = bytearray()
                    data.extend(struct.pack("I", 101))
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

    async def stream_transcript_process():
        nonlocal websocket_active, realtime_segment_buffers, realtime_photo_buffers, websocket, seconds_to_trim
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

            transcript_segments = []
            if segments_to_process:
                last_transcript_time = time.time()
                if seconds_to_trim is None:
                    seconds_to_trim = segments_to_process[0]["start"]

                if seconds_to_add:
                    for i, segment in enumerate(segments_to_process):
                        segment["start"] += seconds_to_add
                        segment["end"] += seconds_to_add
                        segments_to_process[i] = segment
                elif seconds_to_trim:
                    for i, segment in enumerate(segments_to_process):
                        segment["start"] -= seconds_to_trim
                        segment["end"] -= seconds_to_trim
                        segments_to_process[i] = segment

                newly_processed_segments = [
                    TranscriptSegment(**s, speech_profile_processed=speech_profile_complete.is_set())
                    for s in segments_to_process
                ]
                words_transcribed = len(" ".join([seg.text for seg in newly_processed_segments]).split())
                if words_transcribed > 0:
                    words_transcribed_since_last_record += words_transcribed

                for seg in newly_processed_segments:
                    current_session_segments[seg.id] = seg.speech_profile_processed
                transcript_segments, _ = TranscriptSegment.combine_segments([], newly_processed_segments)

            if not current_conversation_id:
                print("Warning: No current conversation ID", uid, session_id)
                continue

            result = _update_in_progress_conversation(
                current_conversation_id, transcript_segments, photos_to_process, finished_at
            )
            if not result or not result[0]:
                continue
            conversation, (starts, ends) = result

            if transcript_segments:
                updates_segments = [segment.dict() for segment in conversation.transcript_segments[starts:ends]]
                await websocket.send_json(updates_segments)

                if transcript_send is not None and user_has_credits:
                    transcript_send([segment.dict() for segment in transcript_segments])

                if translation_enabled:
                    await translate(conversation.transcript_segments[starts:ends], conversation.id)

                # Speaker detection
                for segment in conversation.transcript_segments[starts:ends]:
                    if segment.person_id or segment.is_user or segment.id in suggested_segments:
                        continue

                    if speech_profile_complete.is_set():
                        # Session consistency
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
        nonlocal soniox_profile_socket, deepgram_profile_socket

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

                    if not use_custom_stt:
                        stt_audio_buffer.extend(data)
                        await flush_stt_buffer()

                    if audio_bytes_send is not None:
                        audio_bytes_send(data)

                elif message.get("text") is not None:
                    try:
                        json_data = json.loads(message.get("text"))
                        if json_data.get('type') == 'image_chunk':
                            await handle_image_chunk(
                                uid, json_data, image_chunks, _asend_message_event, realtime_photo_buffers
                            )
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

        _send_message_event(MessageServiceStatusEvent(status="ready"))

        tasks = [
            data_process_task,
            stream_transcript_task,
            heartbeat_task,
            record_usage_task,
            lifecycle_manager_task,
            pending_conversations_task,
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
):
    custom_stt_mode = CustomSttMode.enabled if custom_stt == 'enabled' else CustomSttMode.disabled
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
    )
