from typing import List, Optional, Tuple, TYPE_CHECKING
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_, func, text
from sqlalchemy.sql import literal_column
import logging
import math

from ..models.memory import MemoryDB, MemoryCreate, MemoryResponse, MemoryCategory
from ..integrations.openai import OpenAIClient
from ..core.database import get_db_context

if TYPE_CHECKING:
    from .knowledge_graph_service import KnowledgeGraphService

logger = logging.getLogger(__name__)

SIMILARITY_THRESHOLD = 0.15


class MemoryService:
    def __init__(self, openai_client: Optional[OpenAIClient] = None, enable_graph_extraction: bool = True):
        self._openai = openai_client
        self._openai_initialized = openai_client is not None
        self._graph_service = None
        self._graph_service_initialized = False
        self._enable_graph_extraction = enable_graph_extraction
    
    @property
    def graph_service(self) -> Optional["KnowledgeGraphService"]:
        if not self._graph_service_initialized and self._enable_graph_extraction:
            try:
                from .knowledge_graph_service import KnowledgeGraphService
                self._graph_service = KnowledgeGraphService(self._openai)
                self._graph_service_initialized = True
            except Exception as e:
                logger.warning(f"Knowledge graph service not available: {e}")
                self._graph_service = None
        return self._graph_service
    
    @property
    def openai(self) -> Optional[OpenAIClient]:
        if not self._openai_initialized:
            try:
                self._openai = OpenAIClient()
                self._openai_initialized = True
            except Exception as e:
                logger.warning(f"OpenAI client not available: {e}")
                self._openai = None
        return self._openai
    
    def _require_openai(self) -> OpenAIClient:
        client = self.openai
        if client is None:
            raise RuntimeError("OpenAI client is required for this operation but is not available. Please set OPENAI_API_KEY.")
        return client
    
    async def find_similar(
        self,
        user_id: str,
        embedding: List[float],
        threshold: float = SIMILARITY_THRESHOLD
    ) -> Optional[MemoryDB]:
        with get_db_context() as db:
            distance_col = MemoryDB.embedding.cosine_distance(embedding).label('distance')
            result = db.query(MemoryDB, distance_col).filter(
                MemoryDB.uid == user_id,
                MemoryDB.embedding.isnot(None)
            ).order_by(
                distance_col
            ).first()
            
            if result:
                mem, distance = result
                if distance is not None and distance < threshold:
                    return mem
            return None
    
    async def create(
        self,
        user_id: str,
        content: str,
        category: str = "interesting",
        conversation_id: Optional[str] = None,
        manually_added: bool = False,
        deduplicate: bool = True,
        extract_graph: bool = True
    ) -> MemoryResponse:
        openai_client = self._require_openai()
        embedding = await openai_client.create_embedding(content)
        
        if deduplicate and not manually_added:
            existing = await self.find_similar(user_id, embedding)
            if existing:
                logger.info(f"Skipping duplicate memory similar to: {existing.content[:50]}...")
                return MemoryResponse.model_validate(existing)
        
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
            
            memory_response = MemoryResponse.model_validate(memory)
        
        if extract_graph and self.graph_service:
            try:
                await self.graph_service.extract_entities_and_relations(
                    text=content,
                    user_id=user_id,
                    memory_id=memory_response.id
                )
            except Exception as e:
                logger.warning(f"Graph extraction failed for memory {memory_response.id}: {e}")
        
        return memory_response
    
    def _compute_relevance_score(
        self,
        similarity: float,
        created_at: datetime,
        access_count: int,
        last_accessed: Optional[datetime],
        emotional_weight: float = 0.5,
        is_milestone: bool = False
    ) -> float:
        now = datetime.utcnow()
        age_hours = (now - created_at.replace(tzinfo=None)).total_seconds() / 3600
        recency_boost = math.exp(-age_hours / 168)
        
        frequency_boost = math.log(access_count + 1) / 10
        
        if last_accessed:
            last_access_hours = (now - last_accessed.replace(tzinfo=None)).total_seconds() / 3600
            access_recency_boost = math.exp(-last_access_hours / 24) * 0.1
        else:
            access_recency_boost = 0
        
        emotional_boost = emotional_weight * 0.3
        
        milestone_boost = 0.2 if is_milestone else 0
        
        score = (
            similarity * 0.5 +
            recency_boost * 0.15 +
            frequency_boost * 0.05 +
            access_recency_boost * 0.05 +
            emotional_boost * 0.15 +
            milestone_boost * 0.1
        )
        return min(max(score, 0.0), 1.0)
    
    async def search(
        self,
        user_id: str,
        query: str,
        limit: int = 10,
        category: Optional[str] = None,
        track_access: bool = True
    ) -> List[str]:
        openai_client = self._require_openai()
        query_embedding = await openai_client.create_embedding(query)
        
        with get_db_context() as db:
            distance_col = MemoryDB.embedding.cosine_distance(query_embedding).label('distance')
            base_query = db.query(MemoryDB, distance_col).filter(
                MemoryDB.uid == user_id,
                MemoryDB.embedding.isnot(None)
            )
            if category:
                base_query = base_query.filter(MemoryDB.category == category)
            
            candidates = base_query.order_by(distance_col).limit(limit * 3).all()
            
            scored_memories = []
            for mem, distance in candidates:
                raw_distance = float(distance) if distance else 1.0
                clamped_similarity = max(0.0, min(1.0, 1.0 - raw_distance))
                
                emo_weight = mem.emotional_weight if mem.emotional_weight is not None else 0.0
                
                score = self._compute_relevance_score(
                    similarity=clamped_similarity,
                    created_at=mem.created_at,
                    access_count=mem.access_count or 0,
                    last_accessed=mem.last_accessed,
                    emotional_weight=emo_weight,
                    is_milestone=mem.is_milestone or False
                )
                scored_memories.append((mem, score))
            
            scored_memories.sort(key=lambda x: x[1], reverse=True)
            top_memories = scored_memories[:limit]
            
            if track_access:
                now = datetime.utcnow()
                for mem, _ in top_memories:
                    mem.access_count = (mem.access_count or 0) + 1
                    mem.last_accessed = now
                db.flush()
            
            return [m.content for m, _ in top_memories]
    
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
                openai_client = self._require_openai()
                memory.content = content
                memory.embedding = await openai_client.create_embedding(content)
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

        openai_client = self._require_openai()
        response = await openai_client.chat_completion([
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
                    conversation_id=conversation_id,
                    extract_graph=True
                )
                created_memories.append(memory)
            
            if self.graph_service:
                try:
                    await self.graph_service.extract_entities_and_relations(
                        text=f"{overview}\n\n{transcript[:2000]}",
                        user_id=user_id,
                        memory_id=None
                    )
                except Exception as e:
                    logger.warning(f"Conversation graph extraction failed: {e}")
            
            return created_memories
            
        except Exception as e:
            logger.error(f"Failed to extract memories: {e}")
            return []
    
    async def search_with_graph(
        self,
        user_id: str,
        query: str,
        limit: int = 10,
        category: Optional[str] = None,
        include_graph_context: bool = True
    ) -> Tuple[List[str], str]:
        memories = await self.search(
            user_id=user_id,
            query=query,
            limit=limit,
            category=category
        )
        
        graph_context = ""
        if include_graph_context and self.graph_service:
            try:
                graph_result = await self.graph_service.graph_rag_search(
                    user_id=user_id,
                    query=query,
                    limit=5
                )
                graph_context = graph_result.context
            except Exception as e:
                logger.warning(f"Graph search failed: {e}")
                graph_context = ""
        
        return memories, graph_context
    
    async def get_context_for_query(
        self,
        user_id: str,
        query: str,
        memory_limit: int = 5,
        include_graph: bool = True
    ) -> str:
        memories, graph_context = await self.search_with_graph(
            user_id=user_id,
            query=query,
            limit=memory_limit,
            include_graph_context=include_graph
        )
        
        context_parts = []
        
        if memories:
            context_parts.append("Relevant memories:")
            for mem in memories:
                context_parts.append(f"- {mem}")
        
        if graph_context:
            context_parts.append("\nKnowledge Graph context:")
            context_parts.append(graph_context)
        
        return "\n".join(context_parts) if context_parts else ""
