from fastapi import APIRouter, Request, HTTPException, Header, Query, Response
from pydantic import BaseModel
from typing import Dict, Any, Optional, List, Union
import logging
import hmac
import hashlib
import os
import struct
import io
import re
from datetime import datetime

from ..integrations.omi import OmiWebhookHandler, OmiClient
from ..services.conversation_service import ConversationService
from ..services.memory_service import MemoryService
from ..core.config import get_settings
from ..core.tasks import process_conversation
from ..core.events import event_bus, Event, EventTypes

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/omi", tags=["omi"])
settings = get_settings()


def sanitize_uid(uid: str) -> str:
    """Sanitize user ID to prevent path traversal attacks."""
    sanitized = re.sub(r'[^a-zA-Z0-9_-]', '_', uid)
    sanitized = sanitized[:64]
    return sanitized or "unknown_user"


class OmiWebhookPayload(BaseModel):
    event: str
    data: Dict[str, Any]
    user_id: Optional[str] = None


def get_webhook_handler() -> OmiWebhookHandler:
    return OmiWebhookHandler(
        conversation_service=ConversationService()
    )


def get_memory_service() -> MemoryService:
    return MemoryService()


@router.post("/webhook")
async def handle_omi_webhook(
    payload: OmiWebhookPayload
):
    handler = get_webhook_handler()
    memory_service = get_memory_service()
    
    user_id = payload.user_id or "default_user"
    event_type = payload.event
    
    logger.info(f"Received Omi webhook: {event_type}")
    
    try:
        if event_type == "conversation.created":
            conversation = await handler.handle_conversation_created(
                user_id, 
                payload.data
            )
            
            if conversation.overview:
                process_conversation.delay(
                    conversation_id=conversation.id,
                    user_id=user_id
                )
                logger.info(f"Dispatched conversation processing task for {conversation.id}")
            
            return {
                "status": "queued",
                "conversation_id": conversation.id,
                "message": "Processing dispatched to background worker"
            }
        
        elif event_type == "conversation.updated":
            conversation = await handler.handle_conversation_updated(
                user_id,
                payload.data
            )
            return {
                "status": "updated",
                "conversation_id": conversation.id
            }
        
        elif event_type == "conversation.deleted":
            conversation_service = ConversationService()
            source_id = payload.data.get("id")
            
            if source_id:
                existing = await conversation_service.get_by_source_id(
                    user_id, "omi", str(source_id)
                )
                if existing:
                    await conversation_service.delete(existing.id)
            
            return {"status": "deleted"}
        
        else:
            logger.warning(f"Unknown webhook event type: {event_type}")
            return {"status": "ignored", "reason": "unknown event type"}
            
    except Exception as e:
        logger.error(f"Error processing Omi webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/conversations")
async def list_omi_conversations(
    limit: int = 20,
    days_back: int = 7
):
    from ..integrations.omi import OmiClient
    
    client = OmiClient()
    
    from datetime import datetime, timedelta
    start_date = datetime.utcnow() - timedelta(days=days_back)
    
    conversations = await client.get_conversations(
        user_id="default_user",
        limit=limit,
        start_date=start_date
    )
    
    return {"conversations": conversations}


@router.post("/sync")
async def trigger_omi_sync():
    from ..integrations.limitless_bridge import LimitlessBridge
    
    bridge = LimitlessBridge(
        conversation_service=ConversationService()
    )
    
    if not bridge.is_enabled:
        return {"status": "disabled", "message": "Limitless bridge is not enabled"}
    
    synced_ids = await bridge.sync_recent(
        user_id="default_user",
        hours=24
    )
    
    return {
        "status": "synced",
        "count": len(synced_ids),
        "conversation_ids": synced_ids
    }


@router.post("/process-existing")
async def process_existing_conversations(limit: int = 50):
    """Process existing Limitless conversations that haven't had memories extracted."""
    from ..integrations.limitless_bridge import LimitlessBridge
    
    bridge = LimitlessBridge(
        conversation_service=ConversationService()
    )
    
    memories_extracted = await bridge.process_unprocessed_conversations(
        user_id="default_user",
        limit=limit
    )
    
    return {
        "status": "processed",
        "memories_extracted": memories_extracted
    }


class OmiTranscriptSegment(BaseModel):
    text: str
    speaker: Optional[str] = None
    speaker_id: Optional[Union[int, str]] = None
    is_user: bool = False
    start: Optional[float] = None
    end: Optional[float] = None


class OmiStructured(BaseModel):
    title: Optional[str] = None
    overview: Optional[str] = None
    category: str = "other"
    action_items: Optional[List[Dict[str, Any]]] = None


class OmiGeolocation(BaseModel):
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class OmiConversationPayload(BaseModel):
    """Raw conversation format sent by Omi iOS app."""
    id: str
    created_at: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    structured: OmiStructured
    transcript_segments: Optional[List[OmiTranscriptSegment]] = None
    geolocation: Optional[OmiGeolocation] = None
    source: Optional[str] = None
    language: Optional[str] = None
    discarded: bool = False
    deleted: bool = False


@router.post("/conversation")
async def receive_omi_conversation(
    payload: OmiConversationPayload,
    uid: str = Query(default="default_user", description="User ID from Omi app")
):
    """
    Direct endpoint for Omi iOS app webhook.
    Accepts raw conversation JSON format from the app.
    Configure in Omi app Settings > Developer > Webhook on Conversation Created.
    """
    handler = get_webhook_handler()
    
    logger.info(f"Received Omi conversation from user {uid}: {payload.id}")
    
    try:
        omi_data = {
            "id": payload.id,
            "created_at": payload.created_at,
            "started_at": payload.started_at,
            "finished_at": payload.finished_at,
            "structured": {
                "title": payload.structured.title,
                "overview": payload.structured.overview,
                "category": payload.structured.category,
                "action_items": payload.structured.action_items or []
            },
            "transcript_segments": [
                {
                    "text": seg.text,
                    "speaker_name": seg.speaker,
                    "speaker_id": str(seg.speaker_id) if seg.speaker_id is not None else None,
                    "is_user": seg.is_user,
                    "start": seg.start,
                    "end": seg.end
                }
                for seg in (payload.transcript_segments or [])
            ],
            "geolocation": {
                "latitude": payload.geolocation.latitude,
                "longitude": payload.geolocation.longitude
            } if payload.geolocation else None
        }
        
        conversation = await handler.handle_conversation_created(uid, omi_data)
        
        if conversation.overview:
            await event_bus.publish_async(Event(
                type=EventTypes.CONVERSATION_CREATED,
                data={
                    "conversation_id": conversation.id,
                    "user_id": uid
                }
            ))
            logger.info(f"Published conversation.created event for {conversation.id}")
        
        return {
            "status": "success",
            "conversation_id": conversation.id,
            "message": "Conversation received and queued for processing"
        }
        
    except Exception as e:
        logger.error(f"Error processing Omi conversation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def omi_health_check():
    """Health check endpoint for Omi app connectivity testing."""
    return {
        "status": "healthy",
        "service": "zeke-core",
        "omi_integration": "active",
        "audio_streaming": settings.omi_audio_streaming_enabled
    }


def create_wav_header(sample_rate: int, num_samples: int, num_channels: int = 1, bits_per_sample: int = 16) -> bytes:
    """Create a WAV file header for raw PCM audio data."""
    byte_rate = sample_rate * num_channels * bits_per_sample // 8
    block_align = num_channels * bits_per_sample // 8
    data_size = num_samples * num_channels * bits_per_sample // 8
    
    header = struct.pack(
        '<4sI4s4sIHHIIHH4sI',
        b'RIFF',
        36 + data_size,
        b'WAVE',
        b'fmt ',
        16,
        1,
        num_channels,
        sample_rate,
        byte_rate,
        block_align,
        bits_per_sample,
        b'data',
        data_size
    )
    return header


@router.post("/audio")
async def receive_audio_stream(
    request: Request,
    sample_rate: int = Query(default=16000, description="Audio sample rate in Hz"),
    uid: str = Query(default="default_user", description="User ID from Omi app")
):
    """
    Receive real-time audio bytes from Omi device.
    Configure in Omi app Settings > Developer Mode > Realtime audio bytes.
    
    The audio is received as raw PCM bytes (octet-stream).
    - DevKit1 (v1.0.4+) and DevKit2: 16,000 Hz sample rate
    - DevKit1 (v1.0.2): 8,000 Hz sample rate
    """
    if not settings.omi_audio_streaming_enabled:
        return {"status": "disabled", "message": "Audio streaming is not enabled"}
    
    try:
        audio_bytes = await request.body()
        
        if not audio_bytes:
            return {"status": "error", "message": "No audio data received"}
        
        bytes_received = len(audio_bytes)
        num_samples = bytes_received // 2
        duration_seconds = num_samples / sample_rate
        
        safe_uid = sanitize_uid(uid)
        logger.info(f"Received {bytes_received} audio bytes from user {safe_uid} at {sample_rate}Hz ({duration_seconds:.2f}s)")
        
        storage_path = settings.omi_audio_storage_path
        os.makedirs(storage_path, exist_ok=True)
        
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
        filename = f"omi_audio_{safe_uid}_{timestamp}.wav"
        filepath = os.path.join(storage_path, filename)
        
        wav_header = create_wav_header(sample_rate, num_samples)
        
        with open(filepath, 'wb') as f:
            f.write(wav_header)
            f.write(audio_bytes)
        
        logger.info(f"Saved audio file: {filepath}")
        
        result = {
            "status": "success",
            "bytes_received": bytes_received,
            "duration_seconds": round(duration_seconds, 2),
            "sample_rate": sample_rate,
            "file_saved": filename
        }
        
        if settings.omi_audio_auto_transcribe:
            result["transcription_queued"] = True
        
        return result
        
    except Exception as e:
        logger.error(f"Error processing audio stream: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/audio/status")
async def audio_streaming_status():
    """Check audio streaming configuration and recent files."""
    storage_path = settings.omi_audio_storage_path
    
    files = []
    if os.path.exists(storage_path):
        all_files = sorted(os.listdir(storage_path), reverse=True)[:10]
        for f in all_files:
            filepath = os.path.join(storage_path, f)
            if os.path.isfile(filepath):
                files.append({
                    "filename": f,
                    "size_bytes": os.path.getsize(filepath),
                    "created": datetime.fromtimestamp(os.path.getctime(filepath)).isoformat()
                })
    
    return {
        "enabled": settings.omi_audio_streaming_enabled,
        "auto_transcribe": settings.omi_audio_auto_transcribe,
        "storage_path": storage_path,
        "recent_files": files
    }


@router.delete("/audio/files")
async def clear_audio_files():
    """Clear all stored audio files."""
    storage_path = settings.omi_audio_storage_path
    
    if not os.path.exists(storage_path):
        return {"status": "success", "files_deleted": 0}
    
    deleted = 0
    for f in os.listdir(storage_path):
        filepath = os.path.join(storage_path, f)
        if os.path.isfile(filepath) and f.endswith('.wav'):
            os.remove(filepath)
            deleted += 1
    
    return {"status": "success", "files_deleted": deleted}


@router.post("/audio/toggle")
async def toggle_audio_streaming(enabled: Optional[bool] = None):
    """Toggle audio streaming on or off.
    
    If enabled is not provided, it will toggle the current state.
    If enabled is provided, it will set to that value.
    """
    global settings
    
    if enabled is None:
        settings.omi_audio_streaming_enabled = not settings.omi_audio_streaming_enabled
    else:
        settings.omi_audio_streaming_enabled = enabled
    
    return {
        "status": "success",
        "audio_streaming_enabled": settings.omi_audio_streaming_enabled,
        "message": f"Audio streaming is now {'enabled' if settings.omi_audio_streaming_enabled else 'disabled'}"
    }
