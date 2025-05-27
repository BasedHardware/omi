import os
import uuid
import asyncio
import struct
from datetime import datetime, timezone, timedelta, time
from enum import Enum

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
from models.conversation import Conversation, TranscriptSegment, ConversationStatus, Structured, Geolocation
from models.message_event import ConversationEvent, MessageEvent, MessageServiceStatusEvent, LastConversationEvent, \
    TranslationEvent
from models.transcript_segment import Translation
from utils.apps import is_audio_bytes_app_enabled
from utils.conversations.location import get_google_maps_location
from utils.conversations.process_conversation import process_conversation, retrieve_in_progress_conversation
from utils.other.task import safe_create_task
from utils.app_integrations import trigger_external_integrations
from utils.stt.streaming import *
from utils.stt.streaming import get_stt_service_for_language, STTService
from utils.stt.streaming import process_audio_soniox, process_audio_dg, process_audio_speechmatics, \
    send_initial_file_path, process_audio_wyoming
from utils.webhooks import get_audio_bytes_webhook_seconds
from utils.pusher import connect_to_trigger_pusher
from utils.translation import translate_text, detect_language
from utils.translation_cache import TranscriptSegmentLanguageCache

from utils.other import endpoints as auth
from utils.other.storage import get_profile_audio_if_exists

router = APIRouter()


# Replace your _listen function with this fixed debug version:
async def _listen(
        websocket: WebSocket, uid: str, language: str = 'en', sample_rate: int = 8000, codec: str = 'pcm8',
        channels: int = 1, include_speech_profile: bool = True, stt_service: str = None,
        including_combined_segments: bool = False,
):
    print(f'🎤 _listen START: uid={uid}, language={language}, sample_rate={sample_rate}, codec={codec}')

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
    print(f'🔄 Language after conversion: {language}')

    # Determine the best STT service (ignore the requested stt_service for now)
    stt_service_enum, stt_language, stt_model = get_stt_service_for_language(language)
    print(f'🎯 STT Service Selection: service={stt_service_enum}, language={stt_language}, model={stt_model}')
    
    if not stt_service_enum or not stt_language:
        await websocket.close(code=1008, reason=f"The language is not supported, {language}")
        return

    try:
        print(f'🤝 Accepting WebSocket connection...')
        await websocket.accept()
        print(f'✅ WebSocket accepted successfully')
    except RuntimeError as e:
        print(e, uid)
        await websocket.close(code=1011, reason="Dirty state")
        return

    websocket_active = True

    # Import the proper message event classes
    from models.message_event import MessageServiceStatusEvent

    async def _asend_message_event(msg):
        print(f"📤 Sending message event: {msg}")
        if not websocket_active:
            return False
        try:
            # Use the proper message event format
            if hasattr(msg, 'to_json'):
                await websocket.send_json(msg.to_json())
            else:
                await websocket.send_json(msg)
            return True
        except Exception as e:
            print(f"Error sending message: {e}")
            return False

    def _send_message_event(msg):
        return asyncio.create_task(_asend_message_event(msg))

    # Send initial status using proper MessageServiceStatusEvent
    print(f'📡 Sending initial status...')
    _send_message_event(MessageServiceStatusEvent(
        event_type="service_status",
        status="initiating", 
        status_text="Service Starting"
    ))

    # Validate user (skip for now since auth is broken)
    print(f'👤 User validation skipped for testing')

    # STT Service handling
    if stt_service_enum == STTService.wyoming:
        print(f'🐍 Using Wyoming STT service')
        _send_message_event(MessageServiceStatusEvent(
            event_type="service_status",
            status="stt_connecting", 
            status_text="Connecting to Wyoming"
        ))
        
        try:
            print(f'🔗 Testing Wyoming connection...')
            # Simple Wyoming connection test
            from wyoming.client import AsyncTcpClient
            WYOMING_HOST = os.getenv('WYOMING_HOST', 'localhost')
            WYOMING_PORT = int(os.getenv('WYOMING_PORT', '10300'))
            
            client = AsyncTcpClient(WYOMING_HOST, WYOMING_PORT)
            await asyncio.wait_for(client.connect(), timeout=5.0)
            await client.disconnect()
            
            print(f'✅ Wyoming connection test successful!')
            _send_message_event(MessageServiceStatusEvent(
                event_type="service_status",
                status="ready", 
                status_text="Wyoming Ready"
            ))
            
        except Exception as e:
            print(f'❌ Wyoming connection failed: {e}')
            _send_message_event(MessageServiceStatusEvent(
                event_type="service_status",
                status="error", 
                status_text=f"Wyoming Error: {str(e)}"
            ))
    else:
        print(f'🔄 Using {stt_service_enum} STT service')
        _send_message_event(MessageServiceStatusEvent(
            event_type="service_status",
            status="ready", 
            status_text=f"{stt_service_enum} Ready"
        ))

    # Keep connection alive for testing
    print(f'⏰ Keeping connection alive for testing...')
    try:
        await asyncio.sleep(60)
    except Exception as e:
        print(f'Connection ended: {e}')
    finally:
        websocket_active = False
        print(f'🔚 _listen ended for {uid}')

# @deprecated
# TODO: should be removed after Sep 2025 due to backward compatibility
@router.websocket("/v3/listen")
async def listen_handler_v3(
        websocket: WebSocket, uid: str = Depends(auth.get_current_user_uid), language: str = 'en', sample_rate: int = 8000, codec: str = 'pcm8',
        channels: int = 1, include_speech_profile: bool = True, stt_service: STTService = None
):
    await _listen(websocket, uid, language, sample_rate, codec, channels, include_speech_profile, None)


# Replace your WebSocket handler with manual auth:
# Fix your WebSocket handler to accept all the parameters that Flutter sends:

# Replace your WebSocket handler with this final version:

@router.websocket("/v4/listen")
async def listen_handler(
        websocket: WebSocket, 
        language: str = 'en',
        sample_rate: int = 8000, 
        codec: str = 'pcm8',
        channels: int = 1, 
        include_speech_profile: bool = True, 
        stt_service: str = None
):
    print(f"🚨 WEBSOCKET ENDPOINT HIT!")
    print(f"📋 Query params: {websocket.query_params}")
    
    # Get UID manually from query params
    uid = websocket.query_params.get('uid')
    print(f"🔐 Manual UID extraction: {uid}")
    
    if not uid:
        print(f"❌ No UID provided in query params")
        await websocket.close(code=1008, reason="Missing uid parameter")
        return
    
    print(f"✅ UID found: {uid}")
    print(f"📋 Parameters: language={language}, sample_rate={sample_rate}, codec={codec}")
    print(f"📋 STT Service requested: {stt_service}")
    
    # Now call the fixed _listen function
    await _listen_fixed(websocket, uid, language, sample_rate, codec, channels, include_speech_profile, stt_service)

# Replace your _listen_fixed function with this full implementation:

async def _listen_fixed(
        websocket: WebSocket, uid: str, language: str = 'en', sample_rate: int = 8000, codec: str = 'pcm8',
        channels: int = 1, include_speech_profile: bool = True, stt_service: str = None,
):
    print(f'🎤 _listen_fixed START: uid={uid}, language={language}, sample_rate={sample_rate}, codec={codec}')

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
    print(f'🔄 Language after conversion: {language}')

    # Determine the best STT service 
    stt_service_enum, stt_language, stt_model = get_stt_service_for_language(language)
    print(f'🎯 STT Service Selection: service={stt_service_enum}, language={stt_language}, model={stt_model}')
    
    if not stt_service_enum or not stt_language:
        await websocket.close(code=1008, reason=f"The language is not supported, {language}")
        return

    try:
        print(f'🤝 Accepting WebSocket connection...')
        await websocket.accept()
        print(f'✅ WebSocket accepted successfully')
    except RuntimeError as e:
        print(f"❌ WebSocket accept error: {e}")
        await websocket.close(code=1011, reason="Dirty state")
        return

    websocket_active = True
    websocket_close_code = 1001

    # Import the proper message event classes
    from models.message_event import MessageServiceStatusEvent
    import opuslib

    async def _asend_message_event(msg):
        print(f"📤 Sending message event: {type(msg).__name__} - {msg}")
        if not websocket_active:
            return False
        try:
            message_json = msg.to_json()
            print(f"📤 JSON being sent: {message_json}")
            await websocket.send_json(message_json)
            return True
        except Exception as e:
            print(f"❌ Error sending message: {e}")
            return False

    def _send_message_event(msg):
        return asyncio.create_task(_asend_message_event(msg))

    # Send initial status
    print(f'📡 Sending initial status...')
    await _asend_message_event(MessageServiceStatusEvent(
        status="initiating", 
        status_text="Service Starting"
    ))

    # Validate user (skip for testing)
    print(f'👤 User validation skipped for testing')
    await asyncio.sleep(1)

    # Initialize Wyoming STT
    wyoming_send_audio = None
    wyoming_cleanup = None
    realtime_segment_buffers = []

    def stream_transcript(segments):
        """Handle transcription segments from Wyoming"""
        nonlocal realtime_segment_buffers
        print(f"📝 Received {len(segments)} transcript segments from Wyoming")
        for segment in segments:
            print(f"📝 Segment: {segment}")
        realtime_segment_buffers.extend(segments)

    if stt_service_enum == STTService.wyoming:
        print(f'🐍 Using Wyoming STT service')
        await _asend_message_event(MessageServiceStatusEvent(
            status="stt_connecting", 
            status_text="Connecting to Wyoming"
        ))
        
        try:
            print(f'🔗 Initializing Wyoming STT...')
            wyoming_send_audio, wyoming_cleanup = await process_audio_wyoming(
                stream_transcript, stt_language, sample_rate, channels, preseconds=0
            )
            
            print(f'✅ Wyoming STT initialized successfully!')
            await _asend_message_event(MessageServiceStatusEvent(
                status="ready", 
                status_text="Wyoming Ready"
            ))
            
        except Exception as e:
            print(f'❌ Wyoming initialization failed: {e}')
            await _asend_message_event(MessageServiceStatusEvent(
                status="error", 
                status_text=f"Wyoming Error: {str(e)}"
            ))
            websocket_active = False
            await websocket.close(code=1011, reason=f"STT initialization failed: {e}")
            return
    else:
        print(f'🔄 Using {stt_service_enum} STT service')
        await _asend_message_event(MessageServiceStatusEvent(
            status="ready", 
            status_text=f"{stt_service_enum} Ready"
        ))

    # Audio decoder for Opus
    decoder = None
    if codec == 'opus' and sample_rate == 16000:
        decoder = opuslib.Decoder(sample_rate, 1)
        print(f'🎵 Opus decoder initialized for {sample_rate}Hz')

    # Heart beat
    started_at = time.time()
    timeout_seconds = 420  # 7 minutes
    has_timeout = os.getenv('NO_SOCKET_TIMEOUT') is None
    inactivity_timeout_seconds = 30
    last_audio_received_time = None

    async def send_heartbeat():
        print("💓 send_heartbeat", uid)
        nonlocal websocket_active
        nonlocal websocket_close_code
        nonlocal started_at
        nonlocal last_audio_received_time

        try:
            while websocket_active:
                if websocket.client_state == WebSocketState.CONNECTED:
                    await websocket.send_text("ping")
                else:
                    break

                # Timeout checks
                if has_timeout and time.time() - started_at >= timeout_seconds:
                    print(f"Session timeout is hit by soft timeout {timeout_seconds}", uid)
                    websocket_close_code = 1001
                    websocket_active = False
                    break

                if last_audio_received_time and time.time() - last_audio_received_time > inactivity_timeout_seconds:
                    print(f"Session timeout due to inactivity ({inactivity_timeout_seconds}s)", uid)
                    websocket_close_code = 1001
                    websocket_active = False
                    break

                await asyncio.sleep(10)
        except Exception as e:
            print(f'💓 Heartbeat error: {e}', uid)
            websocket_close_code = 1011
        finally:
            websocket_active = False

    # Start heartbeat
    heartbeat_task = asyncio.create_task(send_heartbeat())

    # Process transcript segments and send to client
    async def stream_transcript_process():
        nonlocal websocket_active
        nonlocal realtime_segment_buffers
        
        while websocket_active:
            try:
                await asyncio.sleep(0.3)  # 300ms
                
                if not realtime_segment_buffers or len(realtime_segment_buffers) == 0:
                    continue
                
                segments = realtime_segment_buffers.copy()
                realtime_segment_buffers = []
                
                print(f"🔄 Processing {len(segments)} transcript segments")
                
                # Convert to the format expected by UI (TranscriptSegment format)
                formatted_segments = []
                for segment in segments:
                    formatted_segment = {
                        'id': str(uuid.uuid4()),  # Generate unique ID
                        'text': segment.get('text', ''),
                        'speaker': segment.get('speaker', 'SPEAKER_1'),
                        'start': segment.get('start', 0),
                        'end': segment.get('end', 0),
                        'is_user': segment.get('is_user', False),
                        'person_id': segment.get('person_id'),
                    }
                    formatted_segments.append(formatted_segment)
                
                # Send segments to UI
                if formatted_segments:
                    print(f"📤 Sending {len(formatted_segments)} segments to UI")
                    await websocket.send_json(formatted_segments)
                
            except Exception as e:
                print(f'❌ Could not process transcript: error {e}', uid)

    # Start transcript processor
    transcript_task = asyncio.create_task(stream_transcript_process())

    # Audio processing
    async def receive_audio():
        nonlocal websocket_active
        nonlocal websocket_close_code
        nonlocal last_audio_received_time
        
        print("🎧 Starting audio receiver...")
        
        try:
            while websocket_active:
                data = await websocket.receive_bytes()
                last_audio_received_time = time.time()
                
                # Decode Opus if needed
                if decoder and codec == 'opus' and sample_rate == 16000:
                    try:
                        data = decoder.decode(bytes(data), frame_size=frame_size)
                        # print(f"🎵 Decoded Opus: {len(data)} bytes")
                    except Exception as e:
                        print(f"❌ Opus decode error: {e}")
                        continue
                
                # Send to Wyoming STT
                if wyoming_send_audio and websocket_active:
                    try:
                        await wyoming_send_audio(data)
                        # print(f"🎤 Sent {len(data)} bytes to Wyoming")
                    except Exception as e:
                        print(f"❌ Error sending audio to Wyoming: {e}")
                        break
                        
        except WebSocketDisconnect:
            print("WebSocket disconnected", uid)
        except Exception as e:
            print(f'❌ Could not process audio: error {e}', uid)
            websocket_close_code = 1011
        finally:
            websocket_active = False

    # Start audio processing
    audio_task = asyncio.create_task(receive_audio())

    print(f'🎯 Wyoming STT ready - listening for audio...')

    try:
        # Wait for all tasks
        tasks = [audio_task, transcript_task, heartbeat_task]
        await asyncio.gather(*tasks)
    except Exception as e:
        print(f"❌ Error during WebSocket operation: {e}", uid)
    finally:
        websocket_active = False
        
        # Cleanup
        try:
            if wyoming_cleanup:
                await wyoming_cleanup()
                print("🧹 Wyoming cleanup completed")
        except Exception as e:
            print(f"❌ Error during Wyoming cleanup: {e}")
            
        # Close WebSocket
        if websocket.client_state == WebSocketState.CONNECTED:
            try:
                await websocket.close(code=websocket_close_code)
            except Exception as e:
                print(f"❌ Error closing WebSocket: {e}")
                
        print(f'🔚 _listen_fixed ended for {uid}')

# Make sure you have the process_audio_wyoming function from earlier artifacts too!
    print(f'🎤 _listen_fixed START: uid={uid}, language={language}, sample_rate={sample_rate}, codec={codec}')

    if not uid or len(uid) <= 0:
        await websocket.close(code=1008, reason="Bad uid")
        return

    # Convert 'auto' to 'multi' for consistency
    language = 'multi' if language == 'auto' else language
    print(f'🔄 Language after conversion: {language}')

    # Determine the best STT service 
    stt_service_enum, stt_language, stt_model = get_stt_service_for_language(language)
    print(f'🎯 STT Service Selection: service={stt_service_enum}, language={stt_language}, model={stt_model}')
    
    if not stt_service_enum or not stt_language:
        await websocket.close(code=1008, reason=f"The language is not supported, {language}")
        return

    try:
        print(f'🤝 Accepting WebSocket connection...')
        await websocket.accept()
        print(f'✅ WebSocket accepted successfully')
    except RuntimeError as e:
        print(f"❌ WebSocket accept error: {e}")
        await websocket.close(code=1011, reason="Dirty state")
        return

    websocket_active = True

    # Import the proper message event classes
    from models.message_event import MessageServiceStatusEvent

    async def _asend_message_event(msg):
        print(f"📤 Sending message event: {type(msg).__name__} - {msg}")
        if not websocket_active:
            return False
        try:
            # Always use the to_json() method for proper format
            message_json = msg.to_json()
            print(f"📤 JSON being sent: {message_json}")
            await websocket.send_json(message_json)
            return True
        except Exception as e:
            print(f"❌ Error sending message: {e}")
            return False

    def _send_message_event(msg):
        return asyncio.create_task(_asend_message_event(msg))

    # Send initial status
    print(f'📡 Sending initial status...')
    await _asend_message_event(MessageServiceStatusEvent(
        status="initiating", 
        status_text="Service Starting"
    ))

    # Validate user (skip for testing)
    print(f'👤 User validation skipped for testing')

    # Sleep to simulate initialization
    await asyncio.sleep(1)

    # STT Service handling
    if stt_service_enum == STTService.wyoming:
        print(f'🐍 Using Wyoming STT service')
        await _asend_message_event(MessageServiceStatusEvent(
            status="stt_connecting", 
            status_text="Connecting to Wyoming"
        ))
        
        try:
            print(f'🔗 Testing Wyoming connection...')
            from wyoming.client import AsyncTcpClient
            WYOMING_HOST = os.getenv('WYOMING_HOST', 'localhost')
            WYOMING_PORT = int(os.getenv('WYOMING_PORT', '10300'))
            
            client = AsyncTcpClient(WYOMING_HOST, WYOMING_PORT)
            await asyncio.wait_for(client.connect(), timeout=5.0)
            await client.disconnect()
            
            print(f'✅ Wyoming connection test successful!')
            await _asend_message_event(MessageServiceStatusEvent(
                status="ready", 
                status_text="Wyoming Ready"
            ))
            
        except Exception as e:
            print(f'❌ Wyoming connection failed: {e}')
            await _asend_message_event(MessageServiceStatusEvent(
                status="error", 
                status_text=f"Wyoming Error: {str(e)}"
            ))
    else:
        print(f'🔄 Using {stt_service_enum} STT service')
        await _asend_message_event(MessageServiceStatusEvent(
            status="ready", 
            status_text=f"{stt_service_enum} Ready"
        ))

    # Keep connection alive and send periodic status
    print(f'⏰ Keeping connection alive...')
    try:
        for i in range(60):  # 60 seconds
            await asyncio.sleep(1)
            
            # Send heartbeat every 10 seconds
            if i % 10 == 0 and websocket_active:
                await websocket.send_text("ping")
                print(f'💓 Heartbeat sent ({i}s)')
                
        print(f'⏰ Test period completed')
        
    except Exception as e:
        print(f'Connection ended: {e}')
    finally:
        websocket_active = False
        print(f'🔚 _listen_fixed ended for {uid}')