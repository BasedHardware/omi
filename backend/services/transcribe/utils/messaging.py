"""WebSocket message handling utilities."""
from fastapi.websockets import WebSocket
from models.message_event import MessageServiceStatusEvent


class MessageSender:
    """Handles sending messages to WebSocket clients."""
    
    def __init__(self, websocket: WebSocket):
        self.websocket = websocket
        
    async def send_status(self, status: str, message: str):
        """Send a status message to the client."""
        try:
            event = MessageServiceStatusEvent(
                status=status,
                message=message
            )
            await self.websocket.send_json(event.dict())
        except Exception as e:
            print(f"❌ Failed to send status message: {e}")
            
    async def send_error(self, message: str):
        """Send an error message to the client."""
        await self.send_status("error", message)
        
    async def send_ready(self):
        """Send ready status to the client."""
        await self.send_status("ready", "Ready for Audio") 