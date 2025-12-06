from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

from ..core.orchestrator import SkillOrchestrator, OrchestratorContext

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    message: str
    conversation_history: Optional[List[Dict[str, str]]] = None


class ChatResponse(BaseModel):
    message: str
    intent: str
    actions_taken: List[str] = []
    data: Dict[str, Any] = {}


def get_orchestrator() -> SkillOrchestrator:
    from ..integrations.openai import OpenAIClient
    from ..services.memory_service import MemoryService
    from ..services.conversation_service import ConversationService
    from ..services.task_service import TaskService
    
    return SkillOrchestrator(
        openai_client=OpenAIClient(),
        memory_service=MemoryService(),
        conversation_service=ConversationService(),
        task_service=TaskService()
    )


@router.post("/", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    orchestrator: SkillOrchestrator = Depends(get_orchestrator)
):
    context = OrchestratorContext(
        user_message=request.message,
        user_id="default_user",
        channel="web",
        conversation_history=request.conversation_history or []
    )
    
    response = await orchestrator.process(context)
    
    return ChatResponse(
        message=response.message,
        intent=response.intent.value,
        actions_taken=response.actions_taken,
        data=response.data
    )
