from typing import Optional

from pydantic import BaseModel, Field


class DatabaseToolSelection(BaseModel):
    """
    Model for selecting which database tools to execute in the chat graph.
    Used by the LLM to determine which tools are needed based on the user's question.
    """

    use_memories: bool = Field(default=False, description="Whether to retrieve memories (facts about the user)")
    use_conversations: bool = Field(
        default=False, description="Whether to retrieve conversations and meeting transcripts"
    )
    use_action_items: bool = Field(default=False, description="Whether to retrieve tasks and action items")
    memories_length: Optional[int] = Field(
        default=None, description="Number of memories to retrieve (optional, defaults to 10 if not specified)"
    )
    conversations_length: Optional[int] = Field(
        default=None, description="Number of conversations to retrieve (optional, defaults to 10 if not specified)"
    )
    action_items_length: Optional[int] = Field(
        default=None, description="Number of action items to retrieve (optional, defaults to 20 if not specified)"
    )
