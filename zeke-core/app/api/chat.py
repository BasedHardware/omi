from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import logging
import time
import asyncio

from ..core.orchestrator import SkillOrchestrator, OrchestratorContext
from ..services.semantic_cache import get_semantic_cache

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    message: str
    conversation_history: Optional[List[Dict[str, str]]] = None


class ChatResponse(BaseModel):
    message: str
    intent: str
    actions_taken: List[str] = []
    data: Dict[str, Any] = {}
    cached: bool = False
    latency_ms: float = 0.0


def get_orchestrator() -> SkillOrchestrator:
    from ..integrations.openai import OpenAIClient
    from ..services.memory_service import MemoryService
    from ..services.conversation_service import ConversationService
    from ..services.task_service import TaskService
    from ..services.location_service import LocationService
    
    return SkillOrchestrator(
        openai_client=OpenAIClient(),
        memory_service=MemoryService(),
        conversation_service=ConversationService(),
        task_service=TaskService(),
        location_service=LocationService()
    )


@router.post("/", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    orchestrator: SkillOrchestrator = Depends(get_orchestrator),
    use_cache: bool = True
):
    start_time = time.time()
    cache = get_semantic_cache()
    user_id = "default_user"
    
    if use_cache and not request.conversation_history:
        cached_result = await cache.get(request.message, user_context=user_id)
        if cached_result:
            latency_ms = (time.time() - start_time) * 1000
            logger.info(f"Cache hit for query: {request.message[:50]}...")
            return ChatResponse(
                message=cached_result["response"],
                intent="cached",
                actions_taken=[],
                data={"similarity": cached_result.get("similarity", 1.0)},
                cached=True,
                latency_ms=latency_ms
            )
    
    context = OrchestratorContext(
        user_message=request.message,
        user_id=user_id,
        channel="web",
        conversation_history=request.conversation_history or []
    )
    
    response = await orchestrator.process(context)
    
    if use_cache and not request.conversation_history:
        await cache.set(request.message, response.message, user_context=user_id)
    
    latency_ms = (time.time() - start_time) * 1000
    
    return ChatResponse(
        message=response.message,
        intent=response.intent.value,
        actions_taken=response.actions_taken or [],
        data=response.data or {},
        cached=False,
        latency_ms=latency_ms
    )


@router.get("/cache/metrics")
async def get_cache_metrics():
    cache = get_semantic_cache()
    metrics = await asyncio.to_thread(cache.get_metrics)
    return metrics


@router.delete("/cache")
async def clear_cache():
    cache = get_semantic_cache()
    deleted = await asyncio.to_thread(cache.clear)
    return {"status": "cleared", "entries_deleted": deleted}
