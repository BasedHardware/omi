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

from services.transcribe.session import WebSocketTranscribeSession

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
        stt_service: str = None
):
    """Main WebSocket endpoint for transcription."""
    print(f"🚨 WebSocket endpoint hit: {websocket.query_params}")
    
    # Get UID from query params (manual auth for testing)
    uid = websocket.query_params.get('uid')
    if not uid:
        print("❌ No UID provided in query params")
        await websocket.close(code=1008, reason="Missing uid parameter")
        return
    
    print(f"✅ Starting session for UID: {uid}")
    
    # Create and run session
    session = WebSocketTranscribeSession(
        websocket=websocket,
        uid=uid,
        language=language,
        sample_rate=sample_rate,
        codec=codec,
        channels=channels,
        include_speech_profile=include_speech_profile,
        stt_service=stt_service,
        including_combined_segments=True
    )
    
    await session.run()