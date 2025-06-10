import os
import uuid
import asyncio
import struct
import time
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import List

import opuslib
import webrtcvad
from fastapi import APIRouter, Depends
from fastapi.websockets import WebSocketDisconnect, WebSocket
from pydub import AudioSegment
from starlette.websockets import WebSocketState

import database.conversations as conversations_db
import database.users as user_db
from database import redis_db
from database.redis_db import get_cached_user_geolocation
from models.conversation import Conversation, TranscriptSegment, ConversationStatus, Structured, Geolocation, ConversationPhoto
from models.message_event import ConversationEvent, MessageEvent, MessageServiceStatusEvent, LastConversationEvent, \
    TranslationEvent
from models.transcript_segment import Translation
from utils.apps import is_audio_bytes_app_enabled
from utils.conversations.location import get_google_maps_location
from utils.conversations.process_conversation import process_conversation, retrieve_in_progress_conversation
from utils.other.task import safe_create_task
from utils.app_integrations import trigger_external_integrations
from utils.webhooks import get_audio_bytes_webhook_seconds
from utils.pusher import connect_to_trigger_pusher
from utils.translation import translate_text, detect_language
from utils.translation_cache import TranscriptSegmentLanguageCache

from utils.other import endpoints as auth
from utils.other.storage import get_profile_audio_if_exists
from utils.stt.streaming import process_audio_dg, process_audio_soniox, process_audio_speechmatics, send_initial_file_path, get_stt_service_for_language as get_stt_service_from_streaming, STTService

router = APIRouter()

async def _listen(
        websocket: WebSocket, uid: str, language: str = 'en', sample_rate: int = 8000, codec: str = 'pcm8',
        channels: int = 1, include_speech_profile: bool = True, stt_service: STTService = None,
        including_combined_segments: bool = False,
):
    if not uid or len(uid) <= 0:
        await websocket.close(code=1008, reason="Bad uid")
        return

    # Frame size, codec
    frame_size: int = 160
    if codec == "opus_fs320":
        codec = "opus"
        frame_size = 320

    # Convert 'auto' to 'multi' for consistency
    language = 'multi' if language == 'auto' else language

    # Determine the best STT service
    stt_service, stt_language, stt_model = get_stt_service_from_streaming(language)
    if not stt_service or not stt_language:
        await websocket.close(code=1008, reason=f"The language is not supported, {language}")
        return

    try:
        await websocket.accept()
    except RuntimeError as e:
        print(e, uid)
        await websocket.close(code=1011, reason="Dirty state")
        return

    websocket_active = True
    websocket_close_code = 1001  # Going Away, don't close with good from backend

    async def _asend_message_event(msg: MessageEvent):
        nonlocal websocket_active
        if not websocket_active:
            return False
        try:
            await websocket.send_json(msg.to_json())
            return True
        except WebSocketDisconnect:
            print("WebSocket disconnected", uid)
            websocket_active = False
        except RuntimeError as e:
            print(f"Can not send message event, error: {e}", uid)

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

                # Check for clear_live_images messages from Redis
                try:
                    import json
                    from database.redis_db import r
                    
                    clear_images_key = f"clear_live_images:{uid}"
                    clear_message_data = r.get(clear_images_key)
                    
                    if clear_message_data:
                        # Send clear_live_images message to client
                        clear_message = json.loads(clear_message_data)
                        await websocket.send_json(clear_message)
                        
                        # Delete the message from Redis after sending
                        r.delete(clear_images_key)
                        
                except Exception as e:
                    print(f"Error handling clear_live_images message: {e}")

                # timeout
                if has_timeout and time.time() - started_at >= timeout_seconds:
                    print(f"Session timeout is hit by soft timeout {timeout_seconds}", uid)
                    websocket_close_code = 1001
                    websocket_active = False
                    break

                # Inactivity timeout
                if last_audio_received_time and time.time() - last_audio_received_time > inactivity_timeout_seconds:
                    print(f"Session timeout due to inactivity ({inactivity_timeout_seconds}s)", uid)
                    websocket_close_code = 1001
                    websocket_active = False
                    break

                # next
                await asyncio.sleep(10)
        except WebSocketDisconnect:
            print("WebSocket disconnected", uid)
        except Exception as e:
            print(f'Heartbeat error: {e}', uid)
            websocket_close_code = 1011
        finally:
            websocket_active = False

    # Start heart beat
    heartbeat_task = asyncio.create_task(send_heartbeat())

    _send_message_event(
        MessageServiceStatusEvent(event_type="service_status", status="initiating", status_text="Service Starting"))

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
            if not conversation:
                return
            
            # Safely access finished_at field
            conversation_finished_at = conversation.get('finished_at')
            if conversation_finished_at:
                # Handle both string and datetime objects
                if isinstance(conversation_finished_at, str):
                    finished_at_parsed = datetime.fromisoformat(conversation_finished_at)
                else:
                    # Already a datetime object
                    finished_at_parsed = conversation_finished_at
                
                if finished_at_parsed > finished_at:
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
            print(f"Error processing conversation: {e}", uid)
            conversations_db.set_conversation_as_discarded(uid, conversation.id)
            conversation.discarded = True
            messages = []

        _send_message_event(ConversationEvent(event_type="memory_created", memory=conversation, messages=messages))

    async def finalize_processing_conversations():
        # handle edge case of conversation was actually processing? maybe later, doesn't hurt really anyway.
        # also fix from getMemories endpoint?
        processing = conversations_db.get_processing_conversations(uid)
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
        # Reset state variables
        nonlocal seconds_to_trim
        nonlocal seconds_to_add
        seconds_to_trim = None
        seconds_to_add = None

        conversation = retrieve_in_progress_conversation(uid)
        if not conversation:
            return
        
        # CRITICAL: Process conversations with EITHER transcript segments OR photos
        # This ensures photo-only conversations get processed into summaries
        has_transcript_segments = conversation.get('transcript_segments') and len(conversation['transcript_segments']) > 0
        
        # Check if conversation has photos (they're stored separately, so we need to fetch them)
        has_photos = False
        if conversation.get('id'):
            try:
                from database import conversations as conversations_db
                photos = conversations_db.get_conversation_photos(uid, conversation['id'])
                has_photos = photos and len(photos) > 0
            except Exception as e:
                print(f"Error checking photos for conversation {conversation['id']}: {e}")
        
        if not has_transcript_segments and not has_photos:
            return
            
        await _create_conversation(conversation)

    conversation_creation_task_lock = asyncio.Lock()
    conversation_creation_task = None
    seconds_to_trim = None
    seconds_to_add = None

    conversation_creation_timeout = 120

    # Process existing conversations
    def _process_in_progess_memories():
        nonlocal conversation_creation_task
        nonlocal seconds_to_add
        nonlocal conversation_creation_timeout
        # Determine previous disconnected socket seconds to add + start processing timer if a conversation in progress
        if existing_conversation := retrieve_in_progress_conversation(uid):
            # segments seconds alignment - handle both string and datetime objects
            started_at_value = existing_conversation['started_at']
            if isinstance(started_at_value, str):
                started_at = datetime.fromisoformat(started_at_value)
            else:
                # Already a datetime object
                started_at = started_at_value
            
            seconds_to_add = (datetime.now(timezone.utc) - started_at).total_seconds()

            # processing if needed logic - handle missing finished_at field
            finished_at_value = existing_conversation.get('finished_at')
            if finished_at_value:
                if isinstance(finished_at_value, str):
                    finished_at = datetime.fromisoformat(finished_at_value)
                else:
                    # Already a datetime object
                    finished_at = finished_at_value
            else:
                # Fallback to current time if finished_at is missing
                finished_at = datetime.now(timezone.utc)
                print('Warning: missing finished_at field, using current time as fallback', uid)
            
            seconds_since_last_segment = (datetime.now(timezone.utc) - finished_at).total_seconds()
            if seconds_since_last_segment >= conversation_creation_timeout:
                asyncio.create_task(_create_current_conversation())
            else:
                conversation_creation_task = asyncio.create_task(
                    _trigger_create_conversation_with_delay(conversation_creation_timeout - seconds_since_last_segment,
                                                            finished_at)
                )

    _send_message_event(
        MessageServiceStatusEvent(status="in_progress_memories_processing", status_text="Processing Memories"))
    _process_in_progess_memories()

    def _upsert_in_progress_conversation(segments: List[TranscriptSegment], finished_at: datetime):
        if existing := retrieve_in_progress_conversation(uid):
            # Check if this is an active session (fake conversation ID)
            if existing.get('id', '').startswith('active_session_'):
                # Create a new real conversation instead of trying to update the fake one
                started_at = datetime.now(timezone.utc) - timedelta(seconds=segments[0].end - segments[0].start)
                conversation = Conversation(
                    id=str(uuid.uuid4()),
                    uid=uid,
                    structured=Structured(),
                    language=language,
                    created_at=started_at,
                    started_at=started_at,
                    finished_at=finished_at,
                    transcript_segments=segments,
                    status=ConversationStatus.in_progress,
                )
                conversations_db.upsert_conversation(uid, conversation_data=conversation.dict())
                redis_db.set_in_progress_conversation_id(uid, conversation.id)
                return conversation, (0, len(segments))
            else:
                # Normal existing conversation - update it
                # Ensure all required fields are present before creating Conversation object
                if 'finished_at' not in existing or existing['finished_at'] is None:
                    existing['finished_at'] = finished_at
                
                if 'created_at' not in existing or existing['created_at'] is None:
                    existing['created_at'] = datetime.now(timezone.utc)
                
                if 'started_at' not in existing or existing['started_at'] is None:
                    existing['started_at'] = datetime.now(timezone.utc)
                
                # Ensure status is set
                if 'status' not in existing:
                    existing['status'] = ConversationStatus.in_progress
                
                conversation = Conversation(**existing)
                conversation.transcript_segments, (starts, ends) = TranscriptSegment.combine_segments(
                    conversation.transcript_segments, segments)
                conversations_db.update_conversation_segments(uid, conversation.id,
                                                              [segment.dict() for segment in
                                                               conversation.transcript_segments])
                conversations_db.update_conversation_finished_at(uid, conversation.id, finished_at)
                redis_db.set_in_progress_conversation_id(uid, conversation.id)
                return conversation, (starts, ends)

        # new conversation
        started_at = datetime.now(timezone.utc) - timedelta(seconds=segments[0].end - segments[0].start)
        conversation = Conversation(
            id=str(uuid.uuid4()),
            uid=uid,
            structured=Structured(),
            language=language,
            created_at=started_at,
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
            transcript_segments=segments,
            status=ConversationStatus.in_progress,
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
                    print("conversation_creation_task is cancelled now", uid)
            conversation_creation_task = asyncio.create_task(
                _trigger_create_conversation_with_delay(conversation_creation_timeout, finished_at))

    # STT
    # Validate websocket_active before initiating STT
    if not websocket_active or websocket.client_state != WebSocketState.CONNECTED:
        print("websocket was closed", uid)
        if websocket.client_state == WebSocketState.CONNECTED:
            try:
                await websocket.close(code=websocket_close_code)
            except Exception as e:
                print(f"Error closing WebSocket: {e}", uid)
        return

    # Process STT
    soniox_socket = None
    soniox_socket2 = None
    speechmatics_socket = None
    deepgram_socket = None
    deepgram_socket2 = None
    speech_profile_duration = 0

    realtime_segment_buffers = []

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
        try:
            file_path, speech_profile_duration = None, 0
            # Thougts: how bee does for recognizing other languages speech profile?
            if (language == 'en' or language == 'auto') and (
                    codec == 'opus' or codec == 'pcm16') and include_speech_profile:
                file_path = get_profile_audio_if_exists(uid)
                speech_profile_duration = AudioSegment.from_wav(file_path).duration_seconds + 5 if file_path else 0

            # DEEPGRAM
            if stt_service == STTService.deepgram:
                deepgram_socket = await process_audio_dg(
                    stream_transcript, stt_language, sample_rate, 1, preseconds=speech_profile_duration,
                    model=stt_model, )
                if speech_profile_duration:
                    deepgram_socket2 = await process_audio_dg(stream_transcript, stt_language, sample_rate, 1,
                                                              model=stt_model)

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
                    stream_transcript, sample_rate, stt_language,
                    uid if include_speech_profile else None,
                    preseconds=speech_profile_duration,
                    language_hints=hints
                )

                # Create a second socket for initial speech profile if needed
                if speech_profile_duration and file_path:
                    soniox_socket2 = await process_audio_soniox(
                        stream_transcript, sample_rate, stt_language,
                        uid if include_speech_profile else None,
                        language_hints=hints
                    )

                    safe_create_task(send_initial_file_path(file_path, soniox_socket.send))
                    print('speech_profile soniox duration', speech_profile_duration, uid)
            # SPEECHMATICS
            elif stt_service == STTService.speechmatics:
                speechmatics_socket = await process_audio_speechmatics(
                    stream_transcript, sample_rate, stt_language, preseconds=speech_profile_duration
                )
                if speech_profile_duration:
                    safe_create_task(send_initial_file_path(file_path, speechmatics_socket.send))
                    print('speech_profile speechmatics duration', speech_profile_duration, uid)

        except Exception as e:
            print(f"Initial processing error: {e}", uid)
            websocket_close_code = 1011
            await websocket.close(code=websocket_close_code)
            return

    # Pusher
    #
    def create_pusher_task_handler():
        nonlocal websocket_active
        
        # Import json here to ensure it's in scope
        import json

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
                            bytes(json.dumps({"segments": segment_buffers, "memory_id": in_progress_conversation_id}),
                                  "utf-8"))
                        segment_buffers = []  # reset
                        await pusher_ws.send(data)
                    except websockets.exceptions.ConnectionClosed as e:
                        print(f"Pusher transcripts Connection closed: {e}", uid)
                        pusher_connected = False
                    except Exception as e:
                        print(f"Pusher transcripts failed: {e}", uid)
                # Only retry connection if Pusher is configured (not None)
                if pusher_connected is False and pusher_ws is not None:
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
                        print(f"Pusher audio_bytes Connection closed: {e}", uid)
                        pusher_connected = False
                    except Exception as e:
                        print(f"Pusher audio_bytes failed: {e}", uid)
                # Only retry connection if Pusher is configured (not None)
                if pusher_connected is False and pusher_ws is not None:
                    await connect()

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
                        print(f"Pusher draining failed: {e}", uid)
                # connect
                await _connect()

        async def _connect():
            nonlocal pusher_ws
            nonlocal pusher_connected

            try:
                pusher_ws = await connect_to_trigger_pusher(uid, sample_rate)
                if pusher_ws is None:
                    pusher_connected = False  # Keep it false so we don't try to send data
                    print(f"Pusher not configured, skipping webhook integration for {uid}")
                else:
                    pusher_connected = True
            except Exception as e:
                print(f"Exception in connect: {e}")
                pusher_connected = False

        async def close(code: int = 1000):
            if pusher_ws:
                await pusher_ws.close(code)

        return (connect, close,
                transcript_send, transcript_consume,
                audio_bytes_send if audio_bytes_enabled else None,
                audio_bytes_consume if audio_bytes_enabled else None)

    transcript_send = None
    transcript_consume = None
    audio_bytes_send = None
    audio_bytes_consume = None
    pusher_close = None
    pusher_connect = None

    # Transcripts
    #
    current_conversation_id = None
    translation_enabled = including_combined_segments and stt_language == 'multi'
    language_cache = TranscriptSegmentLanguageCache()

    async def translate(segments: List[TranscriptSegment], conversation_id: str):
        try:
            translated_segments = []
            for segment in segments:
                segment_text = segment.text.strip()
                if not segment_text or len(segment_text) <= 0:
                    continue
                # Check cache for language detection result
                is_previously_target_language, diff_text = language_cache.get_language_result(segment.id, segment_text,
                                                                                              language)
                if (is_previously_target_language is None or is_previously_target_language is True) \
                        and diff_text:
                    try:
                        detected_lang = detect_language(diff_text)
                        is_target_language = detected_lang is not None and detected_lang == language

                        # Update cache with the detection result
                        language_cache.update_cache(segment.id, segment_text, is_target_language)

                        # Skip translation if it's the target language
                        if is_target_language:
                            continue
                    except Exception as e:
                        print(f"Language detection error: {e}")
                        # Skip translation if couldn't detect the language
                        continue

                # Translate the text to the target language
                translated_text = translate_text(language, segment.text)

                # Skip, del cache to detect language again
                if translated_text == segment.text:
                    language_cache.delete_cache(segment.id)
                    continue

                # Create a Translation object
                translation = Translation(
                    lang=language,
                    text=translated_text,
                )

                # Check if a translation for this language already exists
                existing_translation_index = None
                for i, trans in enumerate(segment.translations):
                    if trans.lang == language:
                        existing_translation_index = i
                        break

                # Replace existing translation or add a new one
                if existing_translation_index is not None:
                    segment.translations[existing_translation_index] = translation
                else:
                    segment.translations.append(translation)

                translated_segments.append(segment)

            # Update the conversation in the database to persist translations
            if len(translated_segments) > 0:
                conversation = conversations_db.get_conversation(uid, conversation_id)
                if conversation:
                    should_updates = False
                    for segment in translated_segments:
                        for i, existing_segment in enumerate(conversation['transcript_segments']):
                            if existing_segment['id'] == segment.id:
                                conversation['transcript_segments'][i]['translations'] = segment.dict()['translations']
                                should_updates = True
                                break

                    # Update the database
                    if should_updates:
                        conversations_db.update_conversation_segments(
                            uid,
                            conversation_id,
                            conversation['transcript_segments']
                        )

            # Send a translation event to the client with the translated segments
            if websocket_active and len(translated_segments) > 0:
                translation_event = TranslationEvent(
                    segments=[segment.dict() for segment in translated_segments]
                )
                _send_message_event(translation_event)

        except Exception as e:
            print(f"Translation error: {e}", uid)

    async def stream_transcript_process():
        nonlocal websocket_active
        nonlocal realtime_segment_buffers
        nonlocal websocket
        nonlocal seconds_to_trim
        nonlocal current_conversation_id
        nonlocal including_combined_segments
        nonlocal translation_enabled

        while websocket_active or len(realtime_segment_buffers) > 0:
            try:
                await asyncio.sleep(0.3)  # 300ms

                if not realtime_segment_buffers or len(realtime_segment_buffers) == 0:
                    continue

                segments = realtime_segment_buffers.copy()
                realtime_segment_buffers = []
                segments.sort(key=lambda x: x["start"])

                # Align the start, end segment
                if seconds_to_trim is None:
                    seconds_to_trim = segments[0]["start"]

                finished_at = datetime.now(timezone.utc)
                await create_conversation_on_segment_received_task(finished_at)

                # Segments aligning duration seconds.
                if seconds_to_add:
                    for i, segment in enumerate(segments):
                        segment["start"] += seconds_to_add
                        segment["end"] += seconds_to_add
                        segments[i] = segment
                elif seconds_to_trim:
                    for i, segment in enumerate(segments):
                        segment["start"] -= seconds_to_trim
                        segment["end"] -= seconds_to_trim
                        segments[i] = segment

                transcript_segments, _ = TranscriptSegment.combine_segments([],
                                                                            [TranscriptSegment(**segment) for segment in
                                                                             segments])

                # can trigger race condition? increase soniox utterance?
                try:
                    conversation, (starts, ends) = _upsert_in_progress_conversation(transcript_segments, finished_at)
                    current_conversation_id = conversation.id

                    # Send to client
                    if including_combined_segments:
                        updates_segments = [segment.dict() for segment in conversation.transcript_segments[starts:ends]]
                    else:
                        updates_segments = [segment.dict() for segment in transcript_segments]

                    await websocket.send_json(updates_segments)

                    # Send to external trigger
                    if transcript_send is not None:
                        transcript_send([segment.dict() for segment in transcript_segments], current_conversation_id)

                    # Translate
                    if translation_enabled:
                        await translate(conversation.transcript_segments[starts:ends], conversation.id)
                        
                except Exception as conv_error:
                    print(f'Error in conversation processing: {conv_error}', uid)
                    # Continue processing even if conversation update fails
                    continue

            except Exception as e:
                print(f'Could not process transcript: error {e}', uid)

    # Audio bytes
    #
    # # Initiate a separate vad for each websocket
    # w_vad = webrtcvad.Vad()
    # w_vad.set_mode(1)

    decoder = opuslib.Decoder(sample_rate, 1)

    # # A  frame must be either 10, 20, or 30 ms in duration
    # def _has_speech(data, sample_rate):
    #     sample_size = 320 if sample_rate == 16000 else 160
    #     offset = 0
    #     while offset < len(data):
    #         sample = data[offset:offset + sample_size]
    #         if len(sample) < sample_size:
    #             sample = sample + bytes([0x00] * (sample_size - len(sample) % sample_size))
    #         has_speech = w_vad.is_speech(sample, sample_rate)
    #         if has_speech:
    #             return True
    #         offset += sample_size
    #     return False

    async def receive_audio(dg_socket1, dg_socket2, soniox_socket, soniox_socket2, speechmatics_socket1):
        nonlocal websocket_active
        nonlocal websocket_close_code
        nonlocal last_audio_received_time

        timer_start = time.time()
        last_audio_received_time = timer_start
        try:
            while websocket_active:
                data = await websocket.receive_bytes()
                last_audio_received_time = time.time()
                if codec == 'opus' and sample_rate == 16000:
                    data = decoder.decode(bytes(data), frame_size=frame_size)

                # STT
                has_speech = True
                # thinh's comment: disabled cause bad performance
                # if include_speech_profile and codec != 'opus':  # don't do for opus 1.0.4 for now
                #     has_speech = _has_speech(data, sample_rate)

                if has_speech:
                    # Handle Soniox sockets
                    if soniox_socket is not None:
                        elapsed_seconds = time.time() - timer_start
                        if elapsed_seconds > speech_profile_duration or not soniox_socket2:
                            await soniox_socket.send(data)
                            if soniox_socket2:
                                print('Killing soniox_socket2', uid)
                                await soniox_socket2.close()
                                soniox_socket2 = None
                        else:
                            await soniox_socket2.send(data)

                    # Handle Speechmatics socket
                    if speechmatics_socket1 is not None:
                        await speechmatics_socket1.send(data)

                    # Handle Deepgram sockets
                    if dg_socket1 is not None:
                        elapsed_seconds = time.time() - timer_start
                        if elapsed_seconds > speech_profile_duration or not dg_socket2:
                            dg_socket1.send(data)
                            if dg_socket2:
                                print('Killing deepgram_socket2', uid)
                                dg_socket2.finish()
                                dg_socket2 = None
                        else:
                            dg_socket2.send(data)

                    # Send to external trigger
                    if audio_bytes_send is not None:
                        audio_bytes_send(data)

        except WebSocketDisconnect:
            print("WebSocket disconnected", uid)
        except Exception as e:
            print(f'Could not process audio: error {e}', uid)
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
        pusher_connect, pusher_close, \
            transcript_send, transcript_consume, \
            audio_bytes_send, audio_bytes_consume = create_pusher_task_handler()

        # Tasks
        audio_process_task = asyncio.create_task(
            receive_audio(deepgram_socket, deepgram_socket2, soniox_socket, soniox_socket2, speechmatics_socket)
        )
        stream_transcript_task = asyncio.create_task(stream_transcript_process())

        # Pusher tasks
        pusher_tasks = [asyncio.create_task(pusher_connect())]
        if transcript_consume is not None:
            pusher_tasks.append(asyncio.create_task(transcript_consume()))
        if audio_bytes_consume is not None:
            pusher_tasks.append(asyncio.create_task(audio_bytes_consume()))

        _send_message_event(MessageServiceStatusEvent(status="ready"))

        tasks = [audio_process_task, stream_transcript_task, heartbeat_task] + pusher_tasks
        await asyncio.gather(*tasks)

    except Exception as e:
        print(f"Error during WebSocket operation: {e}", uid)
    finally:
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
            print(f"Error closing STT sockets: {e}", uid)

        # Client sockets
        if websocket.client_state == WebSocketState.CONNECTED:
            try:
                await websocket.close(code=websocket_close_code)
            except Exception as e:
                print(f"Error closing Client WebSocket: {e}", uid)

        # Pusher sockets
        if pusher_close is not None:
            try:
                await pusher_close()
            except Exception as e:
                print(f"Error closing Pusher: {e}", uid)
    print("_listen ended", uid)


# @deprecated
# TODO: should be removed after Sep 2025 due to backward compatibility
@router.websocket("/v3/listen")
async def listen_handler_v3(
        websocket: WebSocket, uid: str = Depends(auth.get_current_user_uid), language: str = 'en', sample_rate: int = 8000, codec: str = 'pcm8',
        channels: int = 1, include_speech_profile: bool = True, stt_service: STTService = None
):
    await _listen(websocket, uid, language, sample_rate, codec, channels, include_speech_profile, None)


@router.websocket("/v4/listen")
async def listen_handler(
        websocket: WebSocket, uid: str = Depends(auth.get_current_user_uid), language: str = 'en',
        sample_rate: int = 8000, codec: str = 'pcm8',
        channels: int = 1, include_speech_profile: bool = True, stt_service: STTService = None
):
    await _listen(websocket, uid, language, sample_rate, codec, channels, include_speech_profile, None,
                  including_combined_segments=True)
