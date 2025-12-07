"""
Limitless to Omi Bridge - TEMPORARY

This bridge syncs Limitless lifelogs to Omi's conversation format.
It should be removed when native Limitless-to-Omi hardware support is available.

To disable: Set LIMITLESS_SYNC_ENABLED=false in environment variables
"""

from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import httpx
import logging

from ..core.config import get_settings
from ..models.conversation import ConversationCreate, TranscriptSegment

logger = logging.getLogger(__name__)
settings = get_settings()


class LimitlessClient:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.limitless_api_key
        self.base_url = "https://api.limitless.ai"
        self.headers = {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json"
        }
    
    async def get_lifelogs(
        self,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        limit: int = 100,
        cursor: Optional[str] = None,
        timezone: str = "America/New_York"
    ) -> Dict[str, Any]:
        async with httpx.AsyncClient() as client:
            params = {
                "timezone": timezone,
                "limit": limit,
                "includeMarkdown": True,
                "includeContents": True
            }
            
            if start:
                params["start"] = start.strftime("%Y-%m-%d %H:%M:%S")
            if end:
                params["end"] = end.strftime("%Y-%m-%d %H:%M:%S")
            if cursor:
                params["cursor"] = cursor
            
            response = await client.get(
                f"{self.base_url}/v1/lifelogs",
                headers=self.headers,
                params=params
            )
            response.raise_for_status()
            return response.json()
    
    async def get_lifelog(self, lifelog_id: str) -> Optional[Dict[str, Any]]:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/v1/lifelogs/{lifelog_id}",
                headers=self.headers
            )
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return response.json().get("data", {}).get("lifelog")
    
    async def search_lifelogs(self, query: str, limit: int = 100) -> List[Dict[str, Any]]:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/v1/lifelogs",
                headers=self.headers,
                params={"search": query, "limit": limit}
            )
            response.raise_for_status()
            return response.json().get("data", {}).get("lifelogs", [])


class LimitlessToOmiConverter:
    @staticmethod
    def convert_lifelog(lifelog: Dict[str, Any]) -> ConversationCreate:
        segments = []
        
        for content_node in lifelog.get("contents", []):
            if content_node.get("type") == "blockquote":
                text = content_node.get("content", "")
                speaker = content_node.get("speakerName", "Unknown")
                is_user = content_node.get("speakerIdentifier") == "user"
                
                segments.append(TranscriptSegment(
                    text=text,
                    speaker=speaker,
                    start_time=content_node.get("startOffsetMs", 0) / 1000.0,
                    end_time=content_node.get("endOffsetMs", 0) / 1000.0,
                    is_user=is_user
                ))
            
            for child in content_node.get("children", []):
                if child.get("type") == "blockquote":
                    segments.append(TranscriptSegment(
                        text=child.get("content", ""),
                        speaker=child.get("speakerName", "Unknown"),
                        start_time=child.get("startOffsetMs", 0) / 1000.0,
                        end_time=child.get("endOffsetMs", 0) / 1000.0,
                        is_user=child.get("speakerIdentifier") == "user"
                    ))
        
        started_at = None
        finished_at = None
        if lifelog.get("startTime"):
            started_at = datetime.fromisoformat(lifelog["startTime"].replace("Z", "+00:00"))
        if lifelog.get("endTime"):
            finished_at = datetime.fromisoformat(lifelog["endTime"].replace("Z", "+00:00"))
        
        return ConversationCreate(
            title=lifelog.get("title", "Limitless Conversation"),
            overview=lifelog.get("markdown", "")[:500] if lifelog.get("markdown") else None,
            source="limitless",
            source_id=lifelog.get("id"),
            started_at=started_at,
            finished_at=finished_at,
            transcript_segments=segments,
            external_data={
                "limitless_id": lifelog.get("id"),
                "is_starred": lifelog.get("isStarred", False),
                "markdown": lifelog.get("markdown"),
                "bridge_synced_at": datetime.utcnow().isoformat()
            }
        )


class LimitlessBridge:
    def __init__(self, conversation_service, limitless_client: Optional[LimitlessClient] = None):
        self.conversation_service = conversation_service
        self.limitless = limitless_client or LimitlessClient()
        self.converter = LimitlessToOmiConverter()
        self._last_sync_cursor: Optional[str] = None
    
    @property
    def is_enabled(self) -> bool:
        return settings.limitless_sync_enabled and bool(settings.limitless_api_key)
    
    async def sync_recent(self, user_id: str, hours: int = 24) -> List[str]:
        if not self.is_enabled:
            logger.info("Limitless bridge is disabled")
            return []
        
        start = datetime.utcnow() - timedelta(hours=hours)
        
        try:
            result = await self.limitless.get_lifelogs(start=start)
            lifelogs = result.get("data", {}).get("lifelogs", [])
            
            synced_ids = []
            for lifelog in lifelogs:
                existing = await self.conversation_service.get_by_source_id(
                    user_id, 
                    "limitless", 
                    lifelog["id"]
                )
                
                if existing:
                    logger.debug(f"Skipping already synced lifelog {lifelog['id']}")
                    continue
                
                conversation_data = self.converter.convert_lifelog(lifelog)
                conversation = await self.conversation_service.create(
                    user_id,
                    conversation_data
                )
                synced_ids.append(conversation.id)
                logger.info(f"Synced Limitless lifelog {lifelog['id']} -> {conversation.id}")
            
            return synced_ids
            
        except Exception as e:
            logger.error(f"Error syncing Limitless lifelogs: {e}")
            return []
    
    async def sync_all(self, user_id: str) -> int:
        if not self.is_enabled:
            return 0
        
        total_synced = 0
        cursor = None
        
        while True:
            try:
                result = await self.limitless.get_lifelogs(cursor=cursor, limit=100)
                lifelogs = result.get("data", {}).get("lifelogs", [])
                
                if not lifelogs:
                    break
                
                for lifelog in lifelogs:
                    existing = await self.conversation_service.get_by_source_id(
                        user_id,
                        "limitless",
                        lifelog["id"]
                    )
                    
                    if not existing:
                        conversation_data = self.converter.convert_lifelog(lifelog)
                        await self.conversation_service.create(user_id, conversation_data)
                        total_synced += 1
                
                cursor = result.get("meta", {}).get("lifelogs", {}).get("nextCursor")
                if not cursor:
                    break
                    
            except Exception as e:
                logger.error(f"Error in sync_all: {e}")
                break
        
        logger.info(f"Synced {total_synced} Limitless lifelogs total")
        return total_synced
