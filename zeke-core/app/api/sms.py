from fastapi import APIRouter, Request, Form, Response
from typing import Optional
import logging

from ..integrations.twilio import TwilioClient, SMSHandler
from ..core.orchestrator import SkillOrchestrator
from ..integrations.openai import OpenAIClient
from ..services.memory_service import MemoryService
from ..services.conversation_service import ConversationService
from ..services.task_service import TaskService
from ..core.config import get_settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/sms", tags=["sms"])
settings = get_settings()


def get_orchestrator() -> SkillOrchestrator:
    return SkillOrchestrator(
        openai_client=OpenAIClient(),
        memory_service=MemoryService(),
        conversation_service=ConversationService(),
        task_service=TaskService()
    )


def get_sms_handler() -> SMSHandler:
    return SMSHandler(
        twilio_client=TwilioClient(),
        orchestrator=get_orchestrator()
    )


@router.post("/webhook")
async def handle_sms_webhook(
    request: Request,
    Body: str = Form(...),
    From: str = Form(...),
    To: Optional[str] = Form(None),
    MessageSid: Optional[str] = Form(None)
):
    logger.info(f"Received SMS from {From}: {Body[:50]}...")
    
    if From != settings.user_phone_number:
        logger.warning(f"Ignoring SMS from unknown number: {From}")
        return Response(
            content=TwilioClient.create_response("Sorry, I don't recognize your number."),
            media_type="application/xml"
        )
    
    handler = get_sms_handler()
    
    try:
        response_message = await handler.handle_incoming(
            from_number=From,
            body=Body,
            user_id="default_user"
        )
        
        return Response(
            content=TwilioClient.create_response(response_message),
            media_type="application/xml"
        )
        
    except Exception as e:
        logger.error(f"Error handling SMS: {e}")
        return Response(
            content=TwilioClient.create_response(
                "Sorry, I encountered an error processing your message. Please try again."
            ),
            media_type="application/xml"
        )


@router.post("/send")
async def send_sms(
    message: str,
    to: Optional[str] = None
):
    client = TwilioClient()
    
    if to:
        message_sid = await client.send_sms(to, message)
    else:
        message_sid = await client.send_to_user(message)
    
    if message_sid:
        return {"status": "sent", "message_sid": message_sid}
    else:
        return {"status": "failed", "error": "Could not send message"}
