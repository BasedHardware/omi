<content>
from typing import Any, Dict, List, Optional, Union
from uuid import UUID
from pydantic import BaseModel, Field, ValidationError
from backend.models.conversation import Conversation


class MessageConversation(BaseModel):
    """Represents a conversation in the context of a message."""
    id: UUID
    structured: Optional[Dict[str, Any]] = None
    created_at: Optional[float] = Field(None, alias="created_at")

    class Config:
        populate_by_name = True
        extra = "allow"

    @classmethod
    def from_memory_safe(cls, memory: Union[Dict[str, Any], Conversation, Any]) -> Optional["MessageConversation"]:
        """
        Safely converts a memory object to a MessageConversation instance.
        Handles:
        - Dictionaries (partial or complete)
        - Conversation model instances
        - Other objects by attempting to extract known fields
        Returns None if conversion fails.
        """
        if memory is None:
            return None

        try:
            if isinstance(memory, dict):
                # Handle dictionaries, including partial ones
                if "id" not in memory:
                    return None
                
                # Extract known fields, allowing for others
                data = {"id": memory["id"]}
                if "structured" in memory:
                    data["structured"] = memory["structured"]
                if "created_at" in memory:
                    data["created_at"] = memory["created_at"]
                
                return cls(**data)
            
            elif isinstance(memory, Conversation):
                # Handle Conversation model instances
                if not memory.id:
                    return None
                return cls(
                    id=memory.id,
                    structured=getattr(memory, "structured", None),
                    created_at=getattr(memory, "created_at", None)
                )
            
            else:
                # Handle other objects by attempting to extract known fields
                if not hasattr(memory, "id") or not memory.id:
                    return None
                
                data = {"id": memory.id}
                if hasattr(memory, "structured"):
                    data["structured"] = memory.structured
                if hasattr(memory, "created_at"):
                    data["created_at"] = memory.created_at
                
                return cls(**data)
                
        except (ValidationError, TypeError, ValueError):
            # Silently fail if object cannot be converted
            return None

    @classmethod
    def safe_build_many(cls, memories: List[Union[Dict[str, Any], Conversation, Any]]) -> List["MessageConversation"]:
        """
        Safely builds a list of MessageConversation instances from various memory types.
        Filters out any items that cannot be converted.
        """
        if not memories:
            return []
        
        valid_conversations = []
        for memory in memories:
            conv = cls.from_memory_safe(memory)
            if conv:
                valid_conversations.append(conv)
        
        return valid_conversations
</content>