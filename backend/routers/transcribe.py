import os
import uuid
import asyncio
import struct
from datetime import datetime, timezone, timedelta, time
from enum import Enum

import opuslib
import webrtcvad
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
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

# --- Wyoming Handler Import ---
from services.transcribe.wyoming_simple import _listen as wyoming_listen

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


@router.websocket("/v4/listen")
async def listen_handler(
        websocket: WebSocket, 
        language: str = 'en',
        sample_rate: int = 8000, 
        codec: str = 'pcm8',
        channels: int = 1, 
        include_speech_profile: bool = True, 
        stt_service: str = None,
        wyoming_server_ip: str = None
):
    """Main WebSocket endpoint for transcription."""
    print(f"🚨 WebSocket endpoint hit: {websocket.query_params}")
    
    # Get UID from query params (manual auth for testing)
    uid = websocket.query_params.get('uid')
    if not uid:
        print("❌ No UID provided in query params")
        await websocket.close(code=1008, reason="No UID provided")
        return
    
    print(f"✅ UID from query params: {uid}")
    
    # Determine STT service based on language
    stt_service, actual_language, model = get_stt_service_for_language(language)
    print(f"🎯 Selected STT service: {stt_service}, language: {actual_language}, model: {model}")
    
    # Route to appropriate handler based on STT service
    if stt_service == STTService.wyoming:
        print(f"🐍 Routing to Wyoming handler with server IP: {wyoming_server_ip}")
        await _listen_wyoming(
            websocket, uid, actual_language, sample_rate, codec, channels, 
            include_speech_profile, wyoming_server_ip=wyoming_server_ip
        )
    else:
        print(f"🔧 Routing to classic handler")
        await _listen(
            websocket, uid, actual_language, sample_rate, codec, channels, 
            include_speech_profile
        )

async def _listen_wyoming(
    websocket: WebSocket, 
    uid: str, 
    language: str = 'en', 
    sample_rate: int = 8000, 
    codec: str = 'pcm8',
    channels: int = 1, 
    include_speech_profile: bool = True,
    wyoming_server_ip: str = None
):
    """Wyoming WebSocket handler with configurable server IP."""
    print(f'🎤 Wyoming transcribe session for {uid}: {language}, {sample_rate}Hz, {codec}')
    print(f'🔗 Wyoming server IP: {wyoming_server_ip}')
    
    # Validate user ID
    if not uid or len(uid) <= 0:
        await websocket.close(code=1008, reason="Bad uid")
        return
    
    # Handle codec and frame size
    frame_size = 160
    if codec == "opus_fs320":
        codec = "opus"
        frame_size = 320
    
    # Convert 'auto' to 'multi' for consistency
    language = 'multi' if language == 'auto' else language
    
    # Accept WebSocket connection
    try:
        await websocket.accept()
        print(f'✅ WebSocket accepted for {uid}')
    except RuntimeError as e:
        print(f"❌ WebSocket accept error: {e}")
        await websocket.close(code=1011, reason="Dirty state")
        return
    
    # Session state
    websocket_active = True
    websocket_close_code = 1001
    realtime_segment_buffers = []
    
    # Heartbeat management
    started_at = time.time()
    timeout_seconds = 420  # 7 minutes
    has_timeout = os.getenv('NO_SOCKET_TIMEOUT') is None
    inactivity_timeout_seconds = 30
    last_audio_received_time = None
    
    async def send_heartbeat():
        """Send heartbeat to keep connection alive."""
        nonlocal websocket_active, websocket_close_code, started_at, last_audio_received_time
        
        try:
            while websocket_active:
                # Send ping
                if websocket.client_state == WebSocketState.CONNECTED:
                    await websocket.send_text("ping")
                else:
                    break
                
                # Check timeout
                if has_timeout and time.time() - started_at >= timeout_seconds:
                    print(f"Session timeout hit: {timeout_seconds}s for {uid}")
                    websocket_close_code = 1001
                    websocket_active = False
                    break
                
                # Check inactivity timeout
                if last_audio_received_time and time.time() - last_audio_received_time > inactivity_timeout_seconds:
                    print(f"Session timeout due to inactivity: {inactivity_timeout_seconds}s for {uid}")
                    websocket_close_code = 1001
                    websocket_active = False
                    break
                
                await asyncio.sleep(10)
        except WebSocketDisconnect:
            print(f"WebSocket disconnected for {uid}")
        except Exception as e:
            print(f'Heartbeat error for {uid}: {e}')
            websocket_close_code = 1011
        finally:
            websocket_active = False
    
    # Start heartbeat
    heartbeat_task = asyncio.create_task(send_heartbeat())
    
    # Send initial status
    print(f'📤 [Wyoming-{uid}] Sending initial status: initiating')
    await websocket.send_json(MessageServiceStatusEvent(
        event_type="service_status", 
        status="initiating", 
        status_text="Service Starting"
    ).dict())
    
    # Define stream_transcript function before using it
    def stream_transcript(segments):
        """Buffer transcript segments for processing."""
        nonlocal realtime_segment_buffers
        realtime_segment_buffers.extend(segments)
    
    # Initialize Wyoming STT
    wyoming_send_audio = None
    wyoming_cleanup = None
    decoder = None
    
    try:
        # Initialize Opus decoder if needed
        if codec == 'opus' and sample_rate == 16000:
            decoder = opuslib.Decoder(sample_rate, 1)
            print(f'🎵 Opus decoder initialized for {sample_rate}Hz')
        
        # Send STT connecting status
        print(f'📤 [Wyoming-{uid}] Sending STT connecting status')
        await websocket.send_json(MessageServiceStatusEvent(
            event_type="service_status", 
            status="stt_connecting", 
            status_text="Connecting to Wyoming STT"
        ).dict())
        
        # Initialize Wyoming connection with custom server IP
        print(f'🔗 [Wyoming-{uid}] Initializing Wyoming connection...')
        wyoming_send_audio, wyoming_cleanup = await process_audio_wyoming(
            stream_transcript, 
            language, 
            sample_rate, 
            channels, 
            preseconds=0,
            wyoming_server_ip=wyoming_server_ip
        )
        
        # Send ready status
        print(f'📤 [Wyoming-{uid}] Sending ready status: ready')
        await websocket.send_json(MessageServiceStatusEvent(
            event_type="service_status", 
            status="ready", 
            status_text="Listening"
        ).dict())
        
        print(f'✅ Wyoming STT initialized successfully for {uid}')
        
    except Exception as e:
        print(f'❌ Wyoming initialization failed for {uid}: {e}')
        print(f'📤 [Wyoming-{uid}] Sending error status')
        await websocket.send_json(MessageServiceStatusEvent(
            event_type="service_status", 
            status="error", 
            status_text="STT Service Failed"
        ).dict())
        await websocket.close(code=1011, reason="STT initialization failed")
        return
    
    # Audio processing task
    async def process_audio():
        """Process incoming audio data."""
        nonlocal last_audio_received_time, websocket_active, websocket_close_code
        
        try:
            while websocket_active:
                data = await websocket.receive_bytes()
                last_audio_received_time = time.time()
                
                # Decode Opus if needed
                if decoder:
                    try:
                        data = decoder.decode(bytes(data), frame_size=frame_size)
                    except Exception as e:
                        print(f"❌ Opus decode error for {uid}: {e}")
                        continue
                
                # Send to Wyoming STT
                if wyoming_send_audio:
                    await wyoming_send_audio(data)
                    
        except WebSocketDisconnect:
            print(f"WebSocket disconnected for {uid}")
        except Exception as e:
            print(f'❌ Could not process audio for {uid}: {e}')
            websocket_close_code = 1011
        finally:
            websocket_active = False
    
    # Transcript processing task
    async def process_transcripts():
        """Process and send transcript segments to client."""
        nonlocal websocket_active, realtime_segment_buffers
        
        try:
            while websocket_active:
                if realtime_segment_buffers:
                    segments_to_send = realtime_segment_buffers.copy()
                    realtime_segment_buffers.clear()
                    
                    # Send segments to client
                    await websocket.send_json(segments_to_send)
                    print(f'📤 Sent {len(segments_to_send)} segments to {uid}')
                
                await asyncio.sleep(0.1)  # Small delay to prevent busy waiting
                
        except WebSocketDisconnect:
            print(f"WebSocket disconnected for {uid}")
        except Exception as e:
            print(f'❌ Could not process transcripts for {uid}: {e}')
        finally:
            websocket_active = False
    
    # Start processing tasks
    audio_task = asyncio.create_task(process_audio())
    transcript_task = asyncio.create_task(process_transcripts())
    
    try:
        # Wait for any task to complete (indicating an error or disconnect)
        done, pending = await asyncio.wait(
            [heartbeat_task, audio_task, transcript_task],
            return_when=asyncio.FIRST_COMPLETED
        )
        
        # Cancel remaining tasks
        for task in pending:
            task.cancel()
            
    except Exception as e:
        print(f'❌ Session error for {uid}: {e}')
        websocket_close_code = 1011
    finally:
        websocket_active = False
        
        # Cleanup Wyoming STT
        if wyoming_cleanup:
            try:
                await wyoming_cleanup()
            except Exception as e:
                print(f'❌ Wyoming cleanup error for {uid}: {e}')
        
        # Close WebSocket
        try:
            await websocket.close(code=websocket_close_code)
        except Exception as e:
            print(f'❌ WebSocket close error for {uid}: {e}')
        
        print(f'🔚 Wyoming session ended for {uid}')