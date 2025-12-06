from typing import List, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_
import logging

from ..models.memory import MemoryDB, MemoryCreate, MemoryResponse, MemoryCategory
from ..integrations.openai import OpenAIClient
from ..core.database import get_db_context

logger = logging.getLogger(__name__)


class MemoryService:
    def __init__(self, openai_client: Optional[OpenAIClient] = None):
        self.openai = openai_client or OpenAIClient()
    
    async def create(
        self,
        user_id: str,
        content: str,
        category: str = "interesting",
        conversation_id: Optional[str] = None,
        manually_added: bool = False
    ) -> MemoryResponse:
        embedding = await self.openai.create_embedding(content)
        
        with get_db_context() as db:
            memory = MemoryDB(
                uid=user_id,
                content=content,
                category=category,
                conversation_id=conversation_id,
                manually_added=manually_added,
                embedding=embedding
            )
            db.add(memory)
            db.flush()
            db.refresh(memory)
            
            return MemoryResponse.model_validate(memory)
    
    async def search(
        self,
        user_id: str,
        query: str,
        limit: int = 10,
        category: Optional[str] = None
    ) -> List[str]:
        query_embedding = await self.openai.create_embedding(query)
        
        with get_db_context() as db:
            filters = [MemoryDB.uid == user_id]
            if category:
                filters.append(MemoryDB.category == category)
            
            results = db.query(MemoryDB).filter(
                and_(*filters)
            ).order_by(
                MemoryDB.embedding.cosine_distance(query_embedding)
            ).limit(limit).all()
            
            return [m.content for m in results]
    
    async def get_recent(
        self,
        user_id: str,
        limit: int = 20,
        category: Optional[str] = None
    ) -> List[MemoryResponse]:
        with get_db_context() as db:
            query = db.query(MemoryDB).filter(MemoryDB.uid == user_id)
            
            if category:
                query = query.filter(MemoryDB.category == category)
            
            memories = query.order_by(desc(MemoryDB.created_at)).limit(limit).all()
            
            return [MemoryResponse.model_validate(m) for m in memories]
    
    async def get_by_id(self, memory_id: str) -> Optional[MemoryResponse]:
        with get_db_context() as db:
            memory = db.query(MemoryDB).filter(MemoryDB.id == memory_id).first()
            if memory:
                return MemoryResponse.model_validate(memory)
            return None
    
    async def delete(self, memory_id: str) -> bool:
        with get_db_context() as db:
            result = db.query(MemoryDB).filter(MemoryDB.id == memory_id).delete()
            return result > 0
    
    async def update(
        self,
        memory_id: str,
        content: Optional[str] = None,
        category: Optional[str] = None
    ) -> Optional[MemoryResponse]:
        with get_db_context() as db:
            memory = db.query(MemoryDB).filter(MemoryDB.id == memory_id).first()
            if not memory:
                return None
            
            if content:
                memory.content = content
                memory.embedding = await self.openai.create_embedding(content)
                memory.edited = True
            
            if category:
                memory.category = category
            
            memory.updated_at = datetime.utcnow()
            db.flush()
            db.refresh(memory)
            
            return MemoryResponse.model_validate(memory)
    
    async def extract_from_conversation(
        self,
        user_id: str,
        conversation_id: str,
        transcript: str,
        overview: str
    ) -> List[MemoryResponse]:
        prompt = f"""Analyze this conversation and extract important facts, preferences, or learnings about the user.
Return a JSON array of memories to store. Each memory should be a single, clear fact.

Conversation overview: {overview}

Transcript:
{transcript[:3000]}

Extract memories that are:
- Personal preferences (food, activities, etc.)
- Important facts about people mentioned
- Decisions or plans made
- Learnings or insights

Return JSON array like: [{{"content": "memory text", "category": "interesting"}}]
Categories: interesting, system, manual

Only return the JSON array, no other text."""

        response = await self.openai.chat_completion([
            {"role": "user", "content": prompt}
        ], temperature=0.3)
        
        try:
            import json
            memories_data = json.loads(response.choices[0].message.content)
            
            created_memories = []
            for mem_data in memories_data[:5]:
                memory = await self.create(
                    user_id=user_id,
                    content=mem_data["content"],
                    category=mem_data.get("category", "interesting"),
                    conversation_id=conversation_id
                )
                created_memories.append(memory)
            
            return created_memories
            
        except Exception as e:
            logger.error(f"Failed to extract memories: {e}")
            return []
