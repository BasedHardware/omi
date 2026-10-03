<content>
from typing import Any, Dict, List, Optional, Union
import logging
from fastapi import APIRouter, Depends, Query, Response, status
from firebase_admin import firestore
from pydantic import BaseModel, Field

from backend.auth import get_current_user
from backend.models.mcp import (
    ChatMessage,
    CleanerMemory,
    MemoryCategory,
    SearchedMemory,
    SimpleChatMessage,
)
from backend.tools.firestore import get_chat_messages, get_memories, search_memories

router = APIRouter()
logger = logging.getLogger(__name__)


class SimpleChatMessage(BaseModel):
    id: str
    text: str
    sender: str

    def __getitem__(self, item: str) -> Any:
        return getattr(self, item)


class CleanerMemory(BaseModel):
    id: str
    content: str
    category: MemoryCategory

    def __getitem__(self, item: str) -> Any:
        return getattr(self, item)


class SearchedMemory(BaseModel):
    id: str
    content: str
    category: MemoryCategory
    relevance_score: float

    def __getitem__(self, item: str) -> Any:
        return getattr(self, item)


def _validate_simple_chat_messages(
    messages: List[Dict[str, Any]], uid: str
) -> List[SimpleChatMessage]:
    """Safely validate chat messages, skipping malformed records."""
    validated_messages = []
    for msg in messages:
        try:
            validated_messages.append(
                SimpleChatMessage(
                    id=msg["id"],
                    text=msg["text"],
                    sender=msg["sender"],
                )
            )
        except Exception as e:
            logger.warning(
                f"Skipping malformed chat message for user {uid}: {type(e).__name__}"
            )
    return validated_messages


def _validate_cleaner_memories(
    memories: List[Dict[str, Any]], uid: str
) -> List[CleanerMemory]:
    """Safely validate memories, skipping malformed records."""
    validated_memories = []
    for memory in memories:
        try:
            validated_memories.append(
                CleanerMemory(
                    id=memory["id"],
                    content=memory["content"],
                    category=memory["category"],
                )
            )
        except Exception as e:
            logger.warning(
                f"Skipping malformed memory for user {uid}: {type(e).__name__}"
            )
    return validated_memories


def _validate_searched_memories(
    memories: List[Dict[str, Any]], uid: str
) -> List[SearchedMemory]:
    """Safely validate searched memories, skipping malformed records."""
    validated_memories = []
    for memory in memories:
        try:
            validated_memories.append(
                SearchedMemory(
                    id=memory["id"],
                    content=memory["content"],
                    category=memory["category"],
                    relevance_score=memory["relevance_score"],
                )
            )
        except Exception as e:
            logger.warning(
                f"Skipping malformed searched memory for user {uid}: {type(e).__name__}"
            )
    return validated_memories


@router.get("/v1/mcp/chat")
def get_chat_messages_endpoint(
    response: Response,
    cursor: Optional[str] = Query(None),
    limit: int = Query(50, gt=0, le=100),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    uid = current_user["uid"]
    messages, next_cursor, truncated = get_chat_messages(uid, cursor, limit)
    validated_messages = _validate_simple_chat_messages(messages, uid)
    response.headers["X-Next-Cursor"] = next_cursor or ""
    response.headers["X-Scan-Truncated"] = "true" if truncated else "false"
    return [msg.model_dump() for msg in validated_messages]


@router.get("/v1/mcp/memories")
def get_memories_endpoint(
    response: Response,
    cursor: Optional[str] = Query(None),
    limit: int = Query(50, gt=0, le=100),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    uid = current_user["uid"]
    memories, next_cursor, truncated = get_memories(uid, cursor, limit)
    validated_memories = _validate_cleaner_memories(memories, uid)
    response.headers["X-Next-Cursor"] = next_cursor or ""
    response.headers["X-Scan-Truncated"] = "true" if truncated else "false"
    return [memory.model_dump() for memory in validated_memories]


@router.get("/v1/mcp/memories/search")
def search_memories_endpoint(
    response: Response,
    query: str = Query(..., min_length=1),
    limit: int = Query(10, gt=0, le=100),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    uid = current_user["uid"]
    memories, next_cursor, truncated = search_memories(uid, query, limit)
    validated_memories = _validate_searched_memories(memories, uid)
    response.headers["X-Next-Cursor"] = next_cursor or ""
    response.headers["X-Scan-Truncated"] = "true" if truncated else "false"
    return [memory.model_dump() for memory in validated_memories]
</content>