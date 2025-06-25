"""Simplified Wyoming-based transcription service - single file approach like main branch."""
import os
import uuid
import asyncio
import time
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any

import opuslib
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from models.message_event import MessageServiceStatusEvent
from utils.other.storage import get_profile_audio_if_exists
from utils.stt.streaming import process_audio_wyoming


router = APIRouter()


async def _listen(
    websocket: WebSocket, 
    uid: str, 
    language: str = 'en', 
    sample_rate: int = 8000, 
    codec: str = 'pcm8',
    channels: int = 1, 
    include_speech_profile: bool = True,
    including_combined_segments: bool = False,
):
    """Main WebSocket handler for Wyoming-based transcription."""
    print(f'🎤 Wyoming transcribe session for {uid}: {language}, {sample_rate}Hz, {codec}')
    
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
        await websocket.send_json(MessageServiceStatusEvent(
            event_type="service_status", 
            status="stt_connecting", 
            status_text="Connecting to Wyoming STT"
        ).dict())
        
        # Initialize Wyoming connection
        wyoming_send_audio, wyoming_cleanup = await process_audio_wyoming(
            stream_transcript, 
            language, 
            sample_rate, 
            channels, 
            preseconds=0
        )
        
        # Send ready status
        await websocket.send_json(MessageServiceStatusEvent(
            event_type="service_status", 
            status="ready", 
            status_text="Ready for Audio"
        ).dict())
        
        print(f'✅ Wyoming STT initialized successfully for {uid}')
        
    except Exception as e:
        print(f'❌ Wyoming initialization failed for {uid}: {e}')
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
        
        while websocket_active or len(realtime_segment_buffers) > 0:
            try:
                await asyncio.sleep(0.3)  # 300ms
                
                if not realtime_segment_buffers:
                    continue
                
                segments = realtime_segment_buffers.copy()
                realtime_segment_buffers.clear()
                
                print(f"🔄 Processing {len(segments)} transcript segments for {uid}")
                
                # Format segments for UI
                formatted_segments = []
                for segment in segments:
                    formatted_segment = {
                        'id': str(uuid.uuid4()),
                        'text': segment.get('text', ''),
                        'speaker': segment.get('speaker', 'SPEAKER_1'),
                        'start': segment.get('start', 0),
                        'end': segment.get('end', 0),
                        'is_user': segment.get('is_user', False),
                        'person_id': segment.get('person_id'),
                    }
                    formatted_segments.append(formatted_segment)
                
                # Send to client
                if formatted_segments:
                    await websocket.send_json(formatted_segments)
                    
            except Exception as e:
                print(f'❌ Could not process transcript for {uid}: {e}')
    
    # Run main tasks
    try:
        await asyncio.gather(
            process_audio(),
            process_transcripts(),
            return_exceptions=True
        )
    finally:
        # Cleanup
        websocket_active = False
        
        # Cancel heartbeat
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass
        
        # Cleanup Wyoming
        if wyoming_cleanup:
            try:
                await wyoming_cleanup()
                print(f"🧹 Wyoming cleanup completed for {uid}")
            except Exception as e:
                print(f"❌ Error during Wyoming cleanup for {uid}: {e}")
        
        # Close WebSocket
        if websocket.client_state == WebSocketState.CONNECTED:
            try:
                await websocket.close(code=websocket_close_code)
            except Exception:
                pass
        
        print(f'🔚 Wyoming transcribe session ended for {uid}')


@router.websocket("/ws/transcribe/{uid}")
async def websocket_endpoint(
    websocket: WebSocket,
    uid: str,
    language: str = 'en',
    sample_rate: int = 8000,
    codec: str = 'pcm8',
    channels: int = 1,
    include_speech_profile: bool = True,
    including_combined_segments: bool = False,
):
    """WebSocket endpoint for Wyoming-based transcription."""
    await _listen(
        websocket=websocket,
        uid=uid,
        language=language,
        sample_rate=sample_rate,
        codec=codec,
        channels=channels,
        include_speech_profile=include_speech_profile,
        including_combined_segments=including_combined_segments,
    ) 