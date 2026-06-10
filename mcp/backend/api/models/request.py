# backend/api/models/request.py

from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime


class ChatMessage(BaseModel):
    """
    Represents a single chat message.
    
    Why separate model? Reusable across different endpoints
    and ensures consistent message format.
    """
    role: str = Field(..., description="Either 'user' or 'assistant'")
    content: str = Field(..., min_length=1, description="Message content")
    timestamp: Optional[datetime] = Field(default_factory=datetime.utcnow)
    
    @validator('role')
    def validate_role(cls, v):
        """Ensures only valid roles are accepted"""
        if v not in ['user', 'assistant', 'system']:
            raise ValueError('Role must be user, assistant, or system')
        return v


class ChatRequest(BaseModel):
    """
    Request model for chat endpoint.
    
    This is what the frontend sends when user types a message.
    """
    message: str = Field(..., min_length=1, max_length=10000)
    conversation_id: Optional[str] = Field(
        None, 
        description="Optional ID to track conversation history"
    )
    stream: bool = Field(
        default=True, 
        description="Whether to stream response or return all at once"
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Additional context like user preferences"
    )
    
    class Config:
        # Example for API documentation
        schema_extra = {
            "example": {
                "message": "What's on my calendar today?",
                "conversation_id": "conv_123",
                "stream": True,
                "metadata": {"timezone": "UTC"}
            }
        }


class ToolExecutionRequest(BaseModel):
    """
    Request to manually execute a specific tool.
    
    Useful for testing individual MCP servers.
    """
    tool_name: str = Field(..., description="Name of the tool to execute")
    arguments: Dict[str, Any] = Field(
        default_factory=dict, 
        description="Arguments to pass to the tool"
    )
    
    class Config:
        schema_extra = {
            "example": {
                "tool_name": "gmail_get_messages",
                "arguments": {"max_results": 5, "query": "is:unread"}
            }
        }


class ConversationHistoryRequest(BaseModel):
    """
    Request to get conversation history.
    """
    conversation_id: str = Field(..., description="ID of the conversation")
    limit: int = Field(default=50, ge=1, le=100, description="Number of messages to return")
    offset: int = Field(default=0, ge=0, description="Pagination offset")


class FeedbackRequest(BaseModel):
    """
    Request to submit feedback on agent response.
    
    Helpful for improving the agent over time.
    """
    conversation_id: str
    message_id: str
    rating: int = Field(..., ge=1, le=5, description="Rating from 1-5")
    feedback_text: Optional[str] = Field(None, max_length=1000)
    issue_type: Optional[str] = Field(
        None, 
        description="Type of issue: 'incorrect', 'unhelpful', 'offensive', etc."
    )