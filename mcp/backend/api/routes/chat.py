# backend/api/routes/chat.py

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
import logging

from auth.dependencies import CurrentUser
from core.agent import agent_manager
import memory.session_memory as mem

logger = logging.getLogger(__name__)
router = APIRouter()


# ============================================================================
# MODELS
# ============================================================================

class ChatRequest(BaseModel):
    message: str
    thread_id: Optional[str] = None


class ConfirmRequest(BaseModel):
    thread_id: str
    response: str
    user_response: Optional[str] = None


class ConfirmationRequired(BaseModel):
    message: str
    thread_id: str


class ChatResponse(BaseModel):
    message: Optional[str] = None
    thread_id: str
    message_id: str
    execution_time: float
    interrupted: bool = False
    confirmation_required: Optional[ConfirmationRequired] = None


class ThreadResponse(BaseModel):
    thread_id: str


class Message(BaseModel):
    id: str
    role: str
    content: str
    created_at: str


class PreferencesRequest(BaseModel):
    preferences: str


class PreferencesResponse(BaseModel):
    preferences: str


# ============================================================================
# GLOBAL MEMORY
# ============================================================================

@router.get("/memory/preferences", response_model=PreferencesResponse)
async def get_preferences(user: CurrentUser):
    prefs = await mem.get_global_memory(user["id"])
    return PreferencesResponse(preferences=prefs)


@router.put("/memory/preferences", response_model=PreferencesResponse)
async def set_preferences(request: PreferencesRequest, user: CurrentUser):
    ok = await mem.set_global_memory(user["id"], request.preferences)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to save preferences")
    return PreferencesResponse(preferences=request.preferences[:500])


# ============================================================================
# THREAD MANAGEMENT
# ============================================================================

@router.post("/thread", response_model=ThreadResponse)
async def create_thread(user: CurrentUser):
    thread_id = await mem.create_thread(user["id"])
    return ThreadResponse(thread_id=thread_id)


@router.get("/threads", response_model=List[dict])
async def list_threads(user: CurrentUser):
    return await mem.list_threads(user["id"])


@router.get("/threads/{thread_id}/messages", response_model=List[Message])
async def get_thread_messages(thread_id: str, user: CurrentUser):
    thread = await mem.get_thread(thread_id, user["id"])
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    messages = await mem.get_messages(thread_id, user["id"])
    return [
        Message(id=m["id"], role=m["role"], content=m["content"], created_at=m["created_at"])
        for m in messages
    ]


@router.delete("/thread/{thread_id}")
async def delete_thread(thread_id: str, user: CurrentUser):
    ok = await mem.delete_thread(thread_id, user["id"])
    if not ok:
        raise HTTPException(status_code=404, detail="Thread not found")
    return {"message": "Thread deleted", "thread_id": thread_id}


# ============================================================================
# CHAT
# ============================================================================

@router.post("/message", response_model=ChatResponse)
async def send_message(request: ChatRequest, user: CurrentUser):
    """
    Message flow (order matters for in-session memory):

      1. Resolve / create thread in Supabase
      2. Build context from PREVIOUS messages (history before this turn)
      3. Store the current user message
      4. Run orchestrator with history + current message
      5. Store assistant reply
    """
    if not agent_manager.is_initialized:
        raise HTTPException(status_code=503, detail="Agent not initialized.")

    user_id = user["id"]

    # ── 1. Resolve thread ─────────────────────────────────────────────────────
    thread_id = request.thread_id
    if not thread_id:
        thread_id = await mem.create_thread(user_id)
    else:
        thread = await mem.get_thread(thread_id, user_id)
        if not thread:
            # Stale ID from old in-memory system — silently create a new one
            thread_id = await mem.create_thread(user_id)

    # ── 2. Build context from history BEFORE this message ────────────────────
    #    This gives the LLM everything said so far in the session.
    context = await mem.build_context(thread_id, user_id)
    history_lines = [line for line in context.splitlines() if line.strip()]

    # ── 3. Persist user message NOW (will be history for the next turn) ───────
    await mem.add_message(thread_id, user_id, "user", request.message)

    # ── 4. Run orchestrator ───────────────────────────────────────────────────
    try:
        response = await agent_manager.chat(
            message=request.message,
            thread_id=thread_id,
            user_id=user_id,
            conversation_history=history_lines,
        )
    except Exception as e:
        logger.error(f"chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    # ── 5a. HITL interrupt — don't store assistant reply yet ─────────────────
    if response.get("interrupted"):
        conf = response["confirmation_required"]
        return ChatResponse(
            message=None,
            thread_id=thread_id,
            message_id=response["message_id"],
            execution_time=response["execution_time"],
            interrupted=True,
            confirmation_required=ConfirmationRequired(
                message=conf["message"],
                thread_id=conf["thread_id"],
            ),
        )

    # ── 5b. Persist assistant reply ───────────────────────────────────────────
    assistant_text = response["message"]
    await mem.add_message(thread_id, user_id, "assistant", assistant_text)

    return ChatResponse(
        message=assistant_text,
        thread_id=thread_id,
        message_id=response["message_id"],
        execution_time=response["execution_time"],
        interrupted=False,
    )


# ============================================================================
# CONFIRM  (HITL resume)
# ============================================================================

@router.post("/message/confirm", response_model=ChatResponse)
async def confirm_action(request: ConfirmRequest, user: CurrentUser):
    if not agent_manager.is_initialized:
        raise HTTPException(status_code=503, detail="Agent not initialized.")

    user_response = request.response or request.user_response or "reject"

    if not agent_manager.orchestrator.is_pending_confirmation(request.thread_id):
        raise HTTPException(
            status_code=400,
            detail=f"No pending confirmation for thread_id='{request.thread_id}'.",
        )

    try:
        response = await agent_manager.resume(
            thread_id=user["id"],
            user_response=user_response,
            user_id=user["id"],
        )
    except Exception as e:
        logger.error(f"confirm error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    if response.get("interrupted"):
        conf = response["confirmation_required"]
        return ChatResponse(
            message=None,
            thread_id=response["thread_id"],
            message_id=response["message_id"],
            execution_time=response["execution_time"],
            interrupted=True,
            confirmation_required=ConfirmationRequired(
                message=conf["message"],
                thread_id=conf["thread_id"],
            ),
        )

    assistant_text = response["message"]
    await mem.add_message(request.thread_id, user["id"], "assistant", assistant_text)

    return ChatResponse(
        message=assistant_text,
        thread_id=response["thread_id"],
        message_id=response["message_id"],
        execution_time=response["execution_time"],
        interrupted=False,
    )