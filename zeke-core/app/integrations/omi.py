from typing import Optional, List, Dict, Any
from datetime import datetime
import httpx
import logging

from ..core.config import get_settings
from ..models.conversation import ConversationCreate, TranscriptSegment, ActionItem

logger = logging.getLogger(__name__)
settings = get_settings()


class OmiClient:
    def __init__(self, api_url: Optional[str] = None, api_key: Optional[str] = None):
        self.api_url = api_url or settings.omi_api_url
        self.api_key = api_key or settings.omi_api_key
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
    
    async def get_conversations(
        self,
        user_id: str,
        limit: int = 50,
        offset: int = 0,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        async with httpx.AsyncClient() as client:
            params = {"limit": limit, "offset": offset}
            if start_date:
                params["start_date"] = start_date.isoformat()
            if end_date:
                params["end_date"] = end_date.isoformat()
            
            response = await client.get(
                f"{self.api_url}/v1/conversations",
                headers=self.headers,
                params=params
            )
            response.raise_for_status()
            return response.json().get("data", {}).get("conversations", [])
    
    async def get_conversation(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.api_url}/v1/conversations/{conversation_id}",
                headers=self.headers
            )
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return response.json().get("data", {}).get("conversation")
    
    async def search_conversations(
        self,
        user_id: str,
        query: str,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.api_url}/v1/conversations",
                headers=self.headers,
                params={"search": query, "limit": limit}
            )
            response.raise_for_status()
            return response.json().get("data", {}).get("conversations", [])
    
    @staticmethod
    def parse_omi_conversation(omi_data: Dict[str, Any]) -> ConversationCreate:
        segments = []
        for seg in omi_data.get("transcript_segments", []):
            segments.append(TranscriptSegment(
                text=seg.get("text", ""),
                speaker=seg.get("speaker_name"),
                speaker_id=seg.get("speaker_id"),
                start_time=seg.get("start"),
                end_time=seg.get("end"),
                is_user=seg.get("is_user", False)
            ))
        
        action_items = []
        structured = omi_data.get("structured", {})
        for item in structured.get("action_items", []):
            action_items.append(ActionItem(
                description=item.get("description", ""),
                completed=item.get("completed", False)
            ))
        
        return ConversationCreate(
            title=structured.get("title"),
            overview=structured.get("overview"),
            category=structured.get("category", "other"),
            source="omi",
            source_id=omi_data.get("id"),
            started_at=datetime.fromisoformat(omi_data["started_at"]) if omi_data.get("started_at") else None,
            finished_at=datetime.fromisoformat(omi_data["finished_at"]) if omi_data.get("finished_at") else None,
            transcript_segments=segments,
            action_items=action_items,
            location_lat=omi_data.get("geolocation", {}).get("latitude"),
            location_lng=omi_data.get("geolocation", {}).get("longitude"),
            external_data=omi_data
        )


class OmiWebhookHandler:
    def __init__(self, conversation_service):
        self.conversation_service = conversation_service
    
    async def handle_conversation_created(self, user_id: str, payload: Dict[str, Any]):
        conversation_data = OmiClient.parse_omi_conversation(payload)
        conversation = await self.conversation_service.create_from_omi(
            user_id, 
            conversation_data
        )
        logger.info(f"Created conversation {conversation.id} from Omi webhook")
        return conversation
    
    async def handle_conversation_updated(self, user_id: str, payload: Dict[str, Any]):
        conversation_data = OmiClient.parse_omi_conversation(payload)
        conversation = await self.conversation_service.update_from_omi(
            user_id,
            payload.get("id"),
            conversation_data
        )
        logger.info(f"Updated conversation {conversation.id} from Omi webhook")
        return conversation
