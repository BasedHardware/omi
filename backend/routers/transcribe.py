import asyncio
import json
import os
import struct
import uuid
from datetime import datetime, time, timedelta, timezone
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple

import opuslib
import webrtcvad
from fastapi import APIRouter, Depends
from fastapi.websockets import WebSocket, WebSocketDisconnect
from pydub import AudioSegment
from starlette.websockets import WebSocketState

import database.conversations as conversations_db
import database.users as user_db
from database import redis_db
from database.redis_db import get_cached_user_geolocation
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
from utils.other.storage import get_profile_audio_if_exists
from utils.other.task import safe_create_task
from utils.pusher import connect_to_trigger_pusher
from utils.speaker_identification import detect_speaker_from_text
from utils.stt.streaming import *
from utils.stt.streaming import (
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


async def _listen(
    websocket: WebSocket,
    uid: str,
    language: str = 'en',
    sample_rate: int = 8000,
    codec: str = 'pcm8',
    channels: int = 1,
    include_speech_profile: bool = True,
    stt_service: STTService = None,
    including_combined_segments: bool = False,
    conversation_timeout: int = 120,
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
        including_combined_segments,
        conversation_timeout,
    )

    try:
        await websocket.accept()
    except RuntimeError as e:
        print(e, uid, session_id)
        return

    if not uid or len(uid) <= 0:
        await websocket.close(code=1008, reason="Bad uid")
        return

    if not has_transcription_credits(uid):
        # Send credit limit notification (with Redis caching to prevent spam)
        try:
            await send_credit_limit_notification(uid)
        except Exception as e:
            print(f"Error sending credit limit notification: {e}", uid, session_id)

    # Frame size, codec
    frame_size: int = 160
    if codec == "opus_fs320":
        codec = "opus"
        frame_size = 320

    # Convert 'auto' to 'multi' for consistency
    language = 'multi' if language == 'auto' else language

    # Determine the best STT service
    stt_service, stt_language, stt_model = get_stt_service_for_language(language)
    if not stt_service or not stt_language:
        await websocket.close(code=1008, reason=f"The language is not supported, {language}")
        return

    # Translation language
    translation_language = None
    if stt_language == 'multi':
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
    speech_profile_processed = False
    current_session_segments: Dict[str, TranscriptSegment] = {}
    suggested_segments: Set[str] = set()
    first_audio_byte_timestamp: Optional[float] = None
    last_usage_record_timestamp: Optional[float] = None
    words_transcribed_since_last_record: int = 0
    last_transcript_time: Optional[float] = None

    async def _record_usage_periodically():
        nonlocal websocket_active, last_usage_record_timestamp, words_transcribed_since_last_record
        nonlocal last_audio_received_time, last_transcript_time

        while websocket_active:
            await asyncio.sleep(60)
            if not websocket_active:
                break

            # Record usages
            if last_usage_record_timestamp:
                current_time = time.time()
                transcription_seconds = int(current_time - last_usage_record_timestamp)

                words_to_record = words_transcribed_since_last_record
                words_transcribed_since_last_record = 0  # reset

                if transcription_seconds > 0 or words_to_record > 0:
                    record_usage(uid, transcription_seconds=transcription_seconds, words_transcribed=words_to_record)
                last_usage_record_timestamp = current_time

            # Send credit limit notification
            if not has_transcription_credits(uid):
                try:
                    await send_credit_limit_notification(uid)
                except Exception as e:
                    print(f"Error sending credit limit notification: {e}", uid, session_id)

                # Lock the in-progress conversation if credit limit is reached
                conversation = retrieve_in_progress_conversation(uid)
                if conversation and conversation.get('id') and conversation['id'] not in locked_conversation_ids:
                    conversation_id = conversation['id']
                    print(f"Locking conversation {conversation_id} due to transcription limit.", uid, session_id)
                    conversations_db.update_conversation(uid, conversation_id, {'is_locked': True})
                    locked_conversation_ids.add(conversation_id)

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
        print(f"Message: type ${msg.event_type}", uid, session_id)
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
        return asyncio.create_task(_asend_message_event(msg))

    # Heart beat
    started_at = time.time()
    timeout_seconds = 420  # 7m # Soft timeout, should < MODAL_TIME_OUT - 3m
    has_timeout = os.getenv('NO_SOCKET_TIMEOUT') is None
    inactivity_timeout_seconds = 30
    last_audio_received_time = None

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

                # timeout
                if has_timeout and time.time() - started_at >= timeout_seconds:
                    print(f"Session timeout is hit by soft timeout {timeout_seconds}", uid, session_id)
                    websocket_close_code = 1001
                    websocket_active = False
                    break

                # Inactivity timeout
                if last_audio_received_time and time.time() - last_audio_received_time > inactivity_timeout_seconds:
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

    # Stream transcript
    async def _trigger_create_conversation_with_delay(delay_seconds: int, finished_at: datetime):
        try:
            await asyncio.sleep(delay_seconds)

            # recheck session
            conversation = retrieve_in_progress_conversation(uid)
            if not conversation or conversation['finished_at'] > finished_at:
                print("_trigger_create_conversation_with_delay not conversation or not last session", uid, session_id)
                return
            await _create_current_conversation()
        except asyncio.CancelledError:
            pass

    async def _create_conversation(conversation: dict):
        conversation = Conversation(**conversation)
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

    async def finalize_processing_conversations():
        # handle edge case of conversation was actually processing? maybe later, doesn't hurt really anyway.
        # also fix from getMemories endpoint?
        processing = conversations_db.get_processing_conversations(uid)
        print('finalize_processing_conversations len(processing):', len(processing), uid, session_id)
        if not processing or len(processing) == 0:
            return

        # sleep for 1 second to yeld the network for ws accepted.
        await asyncio.sleep(1)
        for conversation in processing:
            await _create_conversation(conversation)

    # Process processing conversations
    asyncio.create_task(finalize_processing_conversations())

    # Send last completed conversation to client
    async def send_last_conversation():
        last_conversation = conversations_db.get_last_completed_conversation(uid)
        if last_conversation:
            await _send_message_event(LastConversationEvent(memory_id=last_conversation['id']))

    asyncio.create_task(send_last_conversation())

    async def _create_current_conversation():
        print("_create_current_conversation", uid, session_id)

        # Reset state variables
        nonlocal seconds_to_trim
        nonlocal seconds_to_add
        seconds_to_trim = None
        seconds_to_add = None

        conversation = retrieve_in_progress_conversation(uid)
        if not conversation or (not conversation.get('transcript_segments') and not conversation.get('photos')):
            return
        await _create_conversation(conversation)

    conversation_creation_task_lock = asyncio.Lock()
    conversation_creation_task = None
    seconds_to_trim = None
    seconds_to_add = None

    conversation_creation_timeout = conversation_timeout
    if conversation_timeout < 120:
        conversation_creation_timeout = 120

    # Process existing conversations
    def _process_in_progess_memories():
        nonlocal conversation_creation_task
        nonlocal seconds_to_add
        nonlocal conversation_creation_timeout
        # Determine previous disconnected socket seconds to add + start processing timer if a conversation in progress
        if existing_conversation := retrieve_in_progress_conversation(uid):
            # segments seconds alignment
            started_at = datetime.fromisoformat(existing_conversation['started_at'].isoformat())
            seconds_to_add = (datetime.now(timezone.utc) - started_at).total_seconds()

            # processing if needed logic
            finished_at = datetime.fromisoformat(existing_conversation['finished_at'].isoformat())
            seconds_since_last_segment = (datetime.now(timezone.utc) - finished_at).total_seconds()
            if seconds_since_last_segment >= conversation_creation_timeout:
                print(
                    '_websocket_util processing existing_conversation',
                    existing_conversation['id'],
                    seconds_since_last_segment,
                    uid,
                    session_id,
                )
                asyncio.create_task(_create_current_conversation())
            else:
                print(
                    '_websocket_util will process',
                    existing_conversation['id'],
                    'in',
                    conversation_creation_timeout - seconds_since_last_segment,
                    'seconds',
                    uid,
                    session_id,
                )
                conversation_creation_task = asyncio.create_task(
                    _trigger_create_conversation_with_delay(
                        conversation_creation_timeout - seconds_since_last_segment, finished_at
                    )
                )

    _send_message_event(
        MessageServiceStatusEvent(status="in_progress_memories_processing", status_text="Processing Memories")
    )
    _process_in_progess_memories()

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

    def _upsert_in_progress_conversation(
        segments: List[TranscriptSegment], photos: List[ConversationPhoto], finished_at: datetime
    ):
        if existing := retrieve_in_progress_conversation(uid):
            conversation = Conversation(**existing)
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

            conversations_db.update_conversation_finished_at(uid, conversation.id, finished_at)
            redis_db.set_in_progress_conversation_id(uid, conversation.id)
            return conversation, (starts, ends)

        # new conversation
        if not segments and not photos:
            return None, (0, 0)

        if segments:
            started_at = datetime.now(timezone.utc) - timedelta(seconds=segments[0].end - segments[0].start)
        else:  # No segments, only photos
            started_at = finished_at

        conversation = Conversation(
            id=str(uuid.uuid4()),
            uid=uid,
            structured=Structured(),
            language=language,
            created_at=started_at,
            started_at=started_at,
            finished_at=finished_at,
            transcript_segments=segments,
            photos=photos,
            status=ConversationStatus.in_progress,
            source=ConversationSource.openglass if photos else ConversationSource.omi,
        )
        conversations_db.upsert_conversation(uid, conversation_data=conversation.dict())
        redis_db.set_in_progress_conversation_id(uid, conversation.id)
        return conversation, (0, len(segments))

    async def create_conversation_on_segment_received_task(finished_at: datetime):
        nonlocal conversation_creation_task
        async with conversation_creation_task_lock:
            if conversation_creation_task is not None:
                conversation_creation_task.cancel()
                try:
                    await conversation_creation_task
                except asyncio.CancelledError:
                    print("conversation_creation_task is cancelled now", uid, session_id)
            conversation_creation_task = asyncio.create_task(
                _trigger_create_conversation_with_delay(conversation_creation_timeout, finished_at)
            )

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
    soniox_socket2 = None
    speechmatics_socket = None
    deepgram_socket = None
    deepgram_socket2 = None
    speech_profile_duration = 0

    realtime_segment_buffers = []
    realtime_photo_buffers = []

    def stream_transcript(segments):
        nonlocal realtime_segment_buffers
        realtime_segment_buffers.extend(segments)

    async def _process_stt():
        nonlocal websocket_close_code
        nonlocal soniox_socket
        nonlocal soniox_socket2
        nonlocal speechmatics_socket
        nonlocal deepgram_socket
        nonlocal deepgram_socket2
        nonlocal speech_profile_duration
        nonlocal speech_profile_processed
        try:
            file_path, speech_profile_duration = None, 0
            # Thougts: how bee does for recognizing other languages speech profile?
            if (
                (language == 'en' or language == 'auto')
                and (codec == 'opus' or codec == 'pcm16')
                and include_speech_profile
            ):
                file_path = get_profile_audio_if_exists(uid)
                speech_profile_duration = AudioSegment.from_wav(file_path).duration_seconds + 5 if file_path else 0

            speech_profile_processed = not (speech_profile_duration > 0)

            # DEEPGRAM
            if stt_service == STTService.deepgram:
                deepgram_socket = await process_audio_dg(
                    stream_transcript,
                    stt_language,
                    sample_rate,
                    1,
                    preseconds=speech_profile_duration,
                    model=stt_model,
                )
                if speech_profile_duration:
                    deepgram_socket2 = await process_audio_dg(
                        stream_transcript, stt_language, sample_rate, 1, model=stt_model
                    )

                    async def deepgram_socket_send(data):
                        return deepgram_socket.send(data)

                    safe_create_task(send_initial_file_path(file_path, deepgram_socket_send))

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
                    preseconds=speech_profile_duration,
                    language_hints=hints,
                )

                # Create a second socket for initial speech profile if needed
                print("speech_profile_duration", speech_profile_duration)
                print("file_path", file_path)
                if speech_profile_duration and file_path:
                    soniox_socket2 = await process_audio_soniox(
                        stream_transcript,
                        sample_rate,
                        stt_language,
                        uid if include_speech_profile else None,
                        language_hints=hints,
                    )

                    safe_create_task(send_initial_file_path(file_path, soniox_socket.send))
                    print('speech_profile soniox duration', speech_profile_duration, uid, session_id)
            # SPEECHMATICS
            elif stt_service == STTService.speechmatics:
                speechmatics_socket = await process_audio_speechmatics(
                    stream_transcript, sample_rate, stt_language, preseconds=speech_profile_duration
                )
                if speech_profile_duration:
                    safe_create_task(send_initial_file_path(file_path, speechmatics_socket.send))
                    print('speech_profile speechmatics duration', speech_profile_duration, uid, session_id)

        except Exception as e:
            print(f"Initial processing error: {e}", uid, session_id)
            websocket_close_code = 1011
            await websocket.close(code=websocket_close_code)
            return

    # Pusher
    #
    def create_pusher_task_handler():
        nonlocal websocket_active

        pusher_ws = None
        pusher_connect_lock = asyncio.Lock()
        pusher_connected = False

        # Transcript
        segment_buffers = []
        in_progress_conversation_id = None

        def transcript_send(segments, conversation_id):
            nonlocal segment_buffers
            nonlocal in_progress_conversation_id
            in_progress_conversation_id = conversation_id
            segment_buffers.extend(segments)

        async def transcript_consume():
            nonlocal websocket_active
            nonlocal segment_buffers
            nonlocal in_progress_conversation_id
            nonlocal pusher_ws
            nonlocal pusher_connected
            while websocket_active or len(segment_buffers) > 0:
                await asyncio.sleep(1)
                if pusher_connected and pusher_ws and len(segment_buffers) > 0:
                    try:
                        # 102|data
                        data = bytearray()
                        data.extend(struct.pack("I", 102))
                        data.extend(
                            bytes(
                                json.dumps({"segments": segment_buffers, "memory_id": in_progress_conversation_id}),
                                "utf-8",
                            )
                        )
                        segment_buffers = []  # reset
                        await pusher_ws.send(data)
                    except websockets.exceptions.ConnectionClosed as e:
                        print(f"Pusher transcripts Connection closed: {e}", uid, session_id)
                        pusher_connected = False
                    except Exception as e:
                        print(f"Pusher transcripts failed: {e}", uid, session_id)
                if pusher_connected is False:
                    await connect()

        # Audio bytes
        audio_buffers = bytearray()
        audio_bytes_enabled = bool(get_audio_bytes_webhook_seconds(uid)) or is_audio_bytes_app_enabled(uid)

        def audio_bytes_send(audio_bytes):
            nonlocal audio_buffers
            audio_buffers.extend(audio_bytes)

        async def audio_bytes_consume():
            nonlocal websocket_active
            nonlocal audio_buffers
            nonlocal pusher_ws
            nonlocal pusher_connected
            while websocket_active or len(audio_buffers) > 0:
                await asyncio.sleep(1)
                if pusher_connected and pusher_ws and len(audio_buffers) > 0:
                    try:
                        # 101|data
                        data = bytearray()
                        data.extend(struct.pack("I", 101))
                        data.extend(audio_buffers.copy())
                        audio_buffers = bytearray()  # reset
                        await pusher_ws.send(data)
                    except websockets.exceptions.ConnectionClosed as e:
                        print(f"Pusher audio_bytes Connection closed: {e}", uid, session_id)
                        pusher_connected = False
                    except Exception as e:
                        print(f"Pusher audio_bytes failed: {e}", uid, session_id)
                if pusher_connected is False:
                    await connect()

        async def connect():
            nonlocal pusher_connected
            nonlocal pusher_connect_lock
            nonlocal pusher_ws
            nonlocal websocket_active
            async with pusher_connect_lock:
                if pusher_connected or not websocket_active:
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

            try:
                pusher_ws = await connect_to_trigger_pusher(uid, sample_rate)
                pusher_connected = True
            except Exception as e:
                print(f"Exception in connect: {e}")

        async def close(code: int = 1000):
            if pusher_ws:
                await pusher_ws.close(code)

        return (
            connect,
            close,
            transcript_send,
            transcript_consume,
            audio_bytes_send if audio_bytes_enabled else None,
            audio_bytes_consume if audio_bytes_enabled else None,
        )

    transcript_send = None
    transcript_consume = None
    audio_bytes_send = None
    audio_bytes_consume = None
    pusher_close = None
    pusher_connect = None

    # Transcripts
    #
    current_conversation_id = None
    translation_enabled = including_combined_segments and translation_language is not None
    language_cache = TranscriptSegmentLanguageCache()
    translation_service = TranslationService()

    async def translate(segments: List[TranscriptSegment], conversation_id: str):
        try:
            translated_segments = []
            for segment in segments:
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

    async def stream_transcript_process():
        nonlocal websocket_active, realtime_segment_buffers, realtime_photo_buffers, websocket, seconds_to_trim
        nonlocal current_conversation_id, including_combined_segments, translation_enabled, speech_profile_processed, speaker_to_person_map, suggested_segments, words_transcribed_since_last_record, last_transcript_time

        while websocket_active or len(realtime_segment_buffers) > 0 or len(realtime_photo_buffers) > 0:
            await asyncio.sleep(0.6)

            if not realtime_segment_buffers and not realtime_photo_buffers:
                continue

            segments_to_process = realtime_segment_buffers.copy()
            realtime_segment_buffers = []

            photos_to_process = realtime_photo_buffers.copy()
            realtime_photo_buffers = []

            finished_at = datetime.now(timezone.utc)
            await create_conversation_on_segment_received_task(finished_at)

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
                    TranscriptSegment(**s, speech_profile_processed=speech_profile_processed)
                    for s in segments_to_process
                ]
                words_transcribed = len(" ".join([seg.text for seg in newly_processed_segments]).split())
                if words_transcribed > 0:
                    words_transcribed_since_last_record += words_transcribed

                for seg in newly_processed_segments:
                    current_session_segments[seg.id] = seg
                transcript_segments, _ = TranscriptSegment.combine_segments([], newly_processed_segments)

            result = _upsert_in_progress_conversation(transcript_segments, photos_to_process, finished_at)
            if not result or not result[0]:
                continue
            conversation, (starts, ends) = result
            current_conversation_id = conversation.id

            if transcript_segments:
                if including_combined_segments:
                    updates_segments = [segment.dict() for segment in conversation.transcript_segments[starts:ends]]
                else:
                    updates_segments = [segment.dict() for segment in transcript_segments]
                await websocket.send_json(updates_segments)

                if transcript_send is not None:
                    transcript_send([segment.dict() for segment in transcript_segments], current_conversation_id)

                if translation_enabled:
                    await translate(conversation.transcript_segments[starts:ends], conversation.id)

                # Speaker detection
                for segment in conversation.transcript_segments[starts:ends]:
                    if segment.person_id or segment.is_user or segment.id in suggested_segments:
                        continue

                    if speech_profile_processed:
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

    image_chunks = {}  # A temporary in-memory cache for image chunks

    async def process_photo(uid: str, image_b64: str, temp_id: str, send_event_func, photo_buffer: list):
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
        uid: str, chunk_data: dict, image_chunks_cache: dict, send_event_func, photo_buffer: list
    ):
        temp_id = chunk_data.get('id')
        index = chunk_data.get('index')
        total = chunk_data.get('total')
        data = chunk_data.get('data')

        if not all([temp_id, isinstance(index, int), isinstance(total, int), data]):
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

    decoder = opuslib.Decoder(sample_rate, 1)

    async def receive_data(dg_socket1, dg_socket2, soniox_socket, soniox_socket2, speechmatics_socket1):
        nonlocal websocket_active, websocket_close_code, last_audio_received_time, current_conversation_id
        nonlocal realtime_photo_buffers, speech_profile_processed, speaker_to_person_map, first_audio_byte_timestamp, last_usage_record_timestamp

        timer_start = time.time()
        last_audio_received_time = timer_start
        try:
            while websocket_active:
                message = await websocket.receive()
                last_audio_received_time = time.time()

                if message.get("bytes") is not None:
                    if first_audio_byte_timestamp is None:
                        first_audio_byte_timestamp = last_audio_received_time
                        last_usage_record_timestamp = first_audio_byte_timestamp
                    data = message.get("bytes")
                    if codec == 'opus' and sample_rate == 16000:
                        data = decoder.decode(bytes(data), frame_size=frame_size)

                    if soniox_socket is not None:
                        elapsed_seconds = time.time() - timer_start
                        if elapsed_seconds > speech_profile_duration or not soniox_socket2:
                            await soniox_socket.send(data)
                            if soniox_socket2:
                                print('Killing soniox_socket2', uid, session_id)
                                await soniox_socket2.close()
                                soniox_socket2 = None
                                speech_profile_processed = True
                        else:
                            await soniox_socket2.send(data)

                    if speechmatics_socket1 is not None:
                        await speechmatics_socket1.send(data)

                    if dg_socket1 is not None:
                        elapsed_seconds = time.time() - timer_start
                        if elapsed_seconds > speech_profile_duration or not dg_socket2:
                            dg_socket1.send(data)
                            if dg_socket2:
                                print('Killing deepgram_socket2', uid, session_id)
                                dg_socket2.finish()
                                dg_socket2 = None
                                speech_profile_processed = True
                        else:
                            dg_socket2.send(data)

                    if audio_bytes_send is not None:
                        audio_bytes_send(data)

                elif message.get("text") is not None:
                    try:
                        json_data = json.loads(message.get("text"))
                        if json_data.get('type') == 'image_chunk':
                            await handle_image_chunk(
                                uid, json_data, image_chunks, _asend_message_event, realtime_photo_buffers
                            )
                        elif json_data.get('type') == 'speaker_assigned':
                            segment_ids = json_data.get('segment_ids', [])
                            can_assign = False
                            if segment_ids:
                                for sid in segment_ids:
                                    if (
                                        sid in current_session_segments
                                        and current_session_segments[sid].speech_profile_processed
                                    ):
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
            print("WebSocket disconnected", uid, session_id)
        except Exception as e:
            print(f'Could not process data: error {e}', uid, session_id)
            websocket_close_code = 1011
        finally:
            websocket_active = False

    # Start
    #
    try:
        # Init STT
        _send_message_event(MessageServiceStatusEvent(status="stt_initiating", status_text="STT Service Starting"))
        await _process_stt()

        # Init pusher
        pusher_connect, pusher_close, transcript_send, transcript_consume, audio_bytes_send, audio_bytes_consume = (
            create_pusher_task_handler()
        )

        # Tasks
        data_process_task = asyncio.create_task(
            receive_data(deepgram_socket, deepgram_socket2, soniox_socket, soniox_socket2, speechmatics_socket)
        )
        stream_transcript_task = asyncio.create_task(stream_transcript_process())
        record_usage_task = asyncio.create_task(_record_usage_periodically())

        # Pusher tasks
        pusher_tasks = [asyncio.create_task(pusher_connect())]
        if transcript_consume is not None:
            pusher_tasks.append(asyncio.create_task(transcript_consume()))
        if audio_bytes_consume is not None:
            pusher_tasks.append(asyncio.create_task(audio_bytes_consume()))

        _send_message_event(MessageServiceStatusEvent(status="ready"))

        tasks = [data_process_task, stream_transcript_task, heartbeat_task, record_usage_task] + pusher_tasks
        await asyncio.gather(*tasks)

    except Exception as e:
        print(f"Error during WebSocket operation: {e}", uid, session_id)
    finally:
        if last_usage_record_timestamp:
            transcription_seconds = int(time.time() - last_usage_record_timestamp)
            words_to_record = words_transcribed_since_last_record
            if transcription_seconds > 0 or words_to_record > 0:
                record_usage(uid, transcription_seconds=transcription_seconds, words_transcribed=words_to_record)
        websocket_active = False

        # STT sockets
        try:
            if deepgram_socket:
                deepgram_socket.finish()
            if deepgram_socket2:
                deepgram_socket2.finish()
            if soniox_socket:
                await soniox_socket.close()
            if soniox_socket2:
                await soniox_socket2.close()
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
    stt_service: STTService = None,
    conversation_timeout: int = 120,
):
    await _listen(
        websocket,
        uid,
        language,
        sample_rate,
        codec,
        channels,
        include_speech_profile,
        None,
        including_combined_segments=True,
        conversation_timeout=conversation_timeout,
    )
