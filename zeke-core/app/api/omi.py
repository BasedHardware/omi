from fastapi import APIRouter, Request, HTTPException, Header
from pydantic import BaseModel
from typing import Dict, Any, Optional
import logging
import hmac
import hashlib

from ..integrations.omi import OmiWebhookHandler
from ..services.conversation_service import ConversationService
from ..services.memory_service import MemoryService
from ..core.config import get_settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/omi", tags=["omi"])
settings = get_settings()


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
                conversation_service = ConversationService()
                transcript = conversation_service.get_transcript_text(conversation)
                await memory_service.extract_from_conversation(
                    user_id=user_id,
                    conversation_id=conversation.id,
                    transcript=transcript,
                    overview=conversation.overview
                )
            
            return {
                "status": "processed",
                "conversation_id": conversation.id
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
