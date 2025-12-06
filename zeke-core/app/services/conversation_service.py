from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_
import logging

from ..models.conversation import (
    ConversationDB, 
    ConversationCreate, 
    ConversationResponse,
    TranscriptSegment
)
from ..core.database import get_db_context
from ..core.events import event_bus, Event, EventTypes

logger = logging.getLogger(__name__)


class ConversationService:
    async def create(
        self,
        user_id: str,
        data: ConversationCreate
    ) -> ConversationResponse:
        with get_db_context() as db:
            conversation = ConversationDB(
                uid=user_id,
                title=data.title,
                overview=data.overview,
                category=data.category.value if hasattr(data.category, 'value') else data.category,
                source=data.source.value if hasattr(data.source, 'value') else data.source,
                source_id=data.source_id,
                started_at=data.started_at,
                finished_at=data.finished_at,
                transcript_segments=[seg.model_dump() for seg in data.transcript_segments],
                action_items=[item.model_dump() for item in data.action_items],
                location_lat=data.location_lat,
                location_lng=data.location_lng,
                location_name=data.location_name,
                participants=data.participants,
                external_data=data.external_data
            )
            db.add(conversation)
            db.flush()
            db.refresh(conversation)
            
            result = ConversationResponse.model_validate(conversation)
        
        event_bus.publish(Event(
            type=EventTypes.CONVERSATION_CREATED,
            data={"conversation_id": result.id, "user_id": user_id}
        ))
        
        return result
    
    async def create_from_omi(
        self,
        user_id: str,
        data: ConversationCreate
    ) -> ConversationResponse:
        return await self.create(user_id, data)
    
    async def update_from_omi(
        self,
        user_id: str,
        source_id: str,
        data: ConversationCreate
    ) -> Optional[ConversationResponse]:
        with get_db_context() as db:
            conversation = db.query(ConversationDB).filter(
                and_(
                    ConversationDB.uid == user_id,
                    ConversationDB.source == "omi",
                    ConversationDB.source_id == source_id
                )
            ).first()
            
            if not conversation:
                return await self.create(user_id, data)
            
            conversation.title = data.title
            conversation.overview = data.overview
            conversation.transcript_segments = [seg.model_dump() for seg in data.transcript_segments]
            conversation.action_items = [item.model_dump() for item in data.action_items]
            conversation.finished_at = data.finished_at
            conversation.updated_at = datetime.utcnow()
            
            db.flush()
            db.refresh(conversation)
            
            return ConversationResponse.model_validate(conversation)
    
    async def get_by_id(self, conversation_id: str) -> Optional[ConversationResponse]:
        with get_db_context() as db:
            conversation = db.query(ConversationDB).filter(
                ConversationDB.id == conversation_id
            ).first()
            
            if conversation:
                return ConversationResponse.model_validate(conversation)
            return None
    
    async def get_by_source_id(
        self,
        user_id: str,
        source: str,
        source_id: str
    ) -> Optional[ConversationResponse]:
        with get_db_context() as db:
            conversation = db.query(ConversationDB).filter(
                and_(
                    ConversationDB.uid == user_id,
                    ConversationDB.source == source,
                    ConversationDB.source_id == source_id
                )
            ).first()
            
            if conversation:
                return ConversationResponse.model_validate(conversation)
            return None
    
    async def get_recent(
        self,
        user_id: str,
        limit: int = 20,
        days_back: Optional[int] = None
    ) -> List[ConversationResponse]:
        with get_db_context() as db:
            query = db.query(ConversationDB).filter(
                ConversationDB.uid == user_id,
                ConversationDB.discarded == False
            )
            
            if days_back:
                cutoff = datetime.utcnow() - timedelta(days=days_back)
                query = query.filter(ConversationDB.created_at >= cutoff)
            
            conversations = query.order_by(
                desc(ConversationDB.created_at)
            ).limit(limit).all()
            
            return [ConversationResponse.model_validate(c) for c in conversations]
    
    async def search(
        self,
        user_id: str,
        query: str,
        days_back: int = 30,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        with get_db_context() as db:
            cutoff = datetime.utcnow() - timedelta(days=days_back)
            
            conversations = db.query(ConversationDB).filter(
                and_(
                    ConversationDB.uid == user_id,
                    ConversationDB.created_at >= cutoff,
                    ConversationDB.discarded == False
                )
            ).order_by(desc(ConversationDB.created_at)).limit(100).all()
            
            query_lower = query.lower()
            results = []
            
            for conv in conversations:
                score = 0
                
                if conv.title and query_lower in conv.title.lower():
                    score += 10
                
                if conv.overview and query_lower in conv.overview.lower():
                    score += 5
                
                for seg in conv.transcript_segments:
                    if query_lower in seg.get("text", "").lower():
                        score += 1
                
                if score > 0:
                    results.append({
                        "id": conv.id,
                        "title": conv.title,
                        "overview": conv.overview,
                        "score": score,
                        "created_at": conv.created_at.isoformat()
                    })
            
            results.sort(key=lambda x: x["score"], reverse=True)
            return results[:limit]
    
    async def delete(self, conversation_id: str) -> bool:
        with get_db_context() as db:
            conversation = db.query(ConversationDB).filter(
                ConversationDB.id == conversation_id
            ).first()
            
            if conversation:
                conversation.discarded = True
                return True
            return False
    
    def get_transcript_text(self, conversation: ConversationResponse) -> str:
        lines = []
        for seg in conversation.transcript_segments:
            speaker = seg.speaker or "Speaker"
            lines.append(f"{speaker}: {seg.text}")
        return "\n".join(lines)
