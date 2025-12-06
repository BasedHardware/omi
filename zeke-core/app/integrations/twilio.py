from typing import Optional
from twilio.rest import Client
from twilio.twiml.messaging_response import MessagingResponse
import logging

from ..core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class TwilioClient:
    def __init__(
        self,
        account_sid: Optional[str] = None,
        auth_token: Optional[str] = None,
        from_number: Optional[str] = None
    ):
        self.account_sid = account_sid or settings.twilio_account_sid
        self.auth_token = auth_token or settings.twilio_auth_token
        self.from_number = from_number or settings.twilio_phone_number
        self.user_number = settings.user_phone_number
        
        if self.account_sid and self.auth_token:
            self.client = Client(self.account_sid, self.auth_token)
        else:
            self.client = None
            logger.warning("Twilio credentials not configured")
    
    async def send_sms(self, to: str, body: str) -> Optional[str]:
        if not self.client:
            logger.error("Twilio client not initialized")
            return None
        
        try:
            message = self.client.messages.create(
                body=body,
                from_=self.from_number,
                to=to
            )
            logger.info(f"Sent SMS to {to}: {message.sid}")
            return message.sid
        except Exception as e:
            logger.error(f"Failed to send SMS: {e}")
            return None
    
    async def send_to_user(self, body: str) -> Optional[str]:
        if not self.user_number:
            logger.error("User phone number not configured")
            return None
        return await self.send_sms(self.user_number, body)
    
    @staticmethod
    def create_response(message: str) -> str:
        response = MessagingResponse()
        response.message(message)
        return str(response)


class SMSHandler:
    def __init__(self, twilio_client: TwilioClient, orchestrator):
        self.twilio = twilio_client
        self.orchestrator = orchestrator
    
    async def handle_incoming(
        self, 
        from_number: str, 
        body: str,
        user_id: str
    ) -> str:
        from ..core.orchestrator import OrchestratorContext
        
        context = OrchestratorContext(
            user_message=body,
            user_id=user_id,
            channel="sms"
        )
        
        response = await self.orchestrator.process(context)
        
        return response.message
