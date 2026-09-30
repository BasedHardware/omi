```python
from typing import List, Optional, Dict
from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from ..models.mcp import (
    SimpleChatMessage,
    CleanerMemory,
    SearchedMemory,
    MemoryCategory,
)

router = APIRouter()

@router.get("/v1/mcp/chat", tags=["mcp"])
async def get_chat_messages(
    uid: str,
) -> Dict:
    messages = await get_raw_chat_messages(uid)
    validated = _validate_simple_chat_messages(messages, uid)
    return {"messages": validated}

def _validate_simple_chat_messages(messages, uid) -> List[Dict]:
    validated: List[Dict] = []
    for msg in messages:
        try:
            if not isinstance(msg, SimpleChatMessage):
                msg = SimpleChatMessage(**msg)
            validated.append(
                {
                    "id": msg.id,
                    "text": msg.text,
                    "sender": msg.sender,
                }
            )
        except Exception as e:
            print(f"Warning: Chat message validation error: {type(e).__name__}")
    return validated

@router.get("/v1/mcp/memories", tags=["mcp"])
async def get_memories(
    uid: str,
) -> Dict:
    memories = await get_raw_memories(uid)
    validated = _validate_cleaner_memories(memories, uid)
    return {"memories": validated}

def _validate_cleaner_memories(memories, uid) -> List[Dict]:
    validated: List[Dict] = []
    for mem in memories:
        try:
            if not isinstance(mem, CleanerMemory):
                mem = CleanerMemory(**mem)
            validated.append(
                {
                    "id": mem.id,
                    "content": mem.content,
                    "category": mem.category.value,
                }
            )
        except Exception as e:
            print(f"Warning: Memory validation error: {type(e).__name__}")
    return validated

@router.get("/v1/mcp/memories/search", tags=["mcp"])
async def search_memories(
    uid: str,
    text: Optional[str] = None,
) -> Dict:
    memories = await get_raw_searched_memories(uid)
    validated = _validate_searched_memories(memories, uid)
    return {"memories": validated}

def _validate_searched_memories(memories, uid) -> List[Dict]:
    validated: List[Dict] = []
    for mem in memories:
        try:
            if not isinstance(mem, SearchedMemory):
                mem = SearchedMemory(**mem)
            validated.append(
                {
                    "id": mem.id,
                    "content": mem.content,
                    "category": mem.category.value,
                    "relevance_score": mem.relevance_score,
                }
            )
        except Exception as e:
            print(f"Warning: Searched memory validation error: {type(e).__name__}")
    return validated
```