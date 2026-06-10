# backend/api/models/response.py

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class ResponseStatus(str, Enum):
    """Enumeration for response status"""
    SUCCESS = "success"
    ERROR = "error"
    PARTIAL = "partial"


class ToolInfo(BaseModel):
    """Information about available tools"""
    name: str
    description: str
    parameters: Dict[str, Any]
    server: str = Field(..., description="Which MCP server provides this tool")


class ToolsListResponse(BaseModel):
    """Response containing list of available tools"""
    status: ResponseStatus = ResponseStatus.SUCCESS
    tools: List[ToolInfo]
    total_count: int
    servers_active: List[str] = Field(
        ..., 
        description="List of active MCP server names"
    )


class ChatChunk(BaseModel):
    """
    Single chunk in a streaming response.
    
    Why chunks? Allows real-time display of agent thinking,
    better user experience than waiting for full response.
    """
    type: str = Field(..., description="'token', 'tool_call', 'tool_result', 'done'")
    content: Optional[str] = None
    tool_name: Optional[str] = None
    tool_input: Optional[Dict[str, Any]] = None
    tool_output: Optional[Any] = None
    metadata: Optional[Dict[str, Any]] = None
    
    class Config:
        schema_extra = {
            "example": {
                "type": "token",
                "content": "Let me check your calendar...",
                "metadata": {"timestamp": "2024-01-08T10:30:00Z"}
            }
        }


class ChatResponse(BaseModel):
    """
    Complete response for non-streaming chat.
    
    Contains the full agent response and metadata.
    """
    status: ResponseStatus = ResponseStatus.SUCCESS
    message: str = Field(..., description="Agent's response message")
    conversation_id: str
    message_id: str = Field(..., description="Unique ID for this message")
    tools_used: List[str] = Field(
        default_factory=list,
        description="Names of tools the agent used"
    )
    execution_time: float = Field(..., description="Time taken in seconds")
    token_count: Optional[int] = Field(None, description="Number of tokens used")
    metadata: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        schema_extra = {
            "example": {
                "status": "success",
                "message": "You have 3 events today: Morning standup at 9am...",
                "conversation_id": "conv_123",
                "message_id": "msg_456",
                "tools_used": ["google_calendar_list_events"],
                "execution_time": 2.3,
                "token_count": 245,
                "timestamp": "2024-01-08T10:30:00Z"
            }
        }


class ErrorDetail(BaseModel):
    """Detailed error information"""
    code: str
    message: str
    details: Optional[Dict[str, Any]] = None


class ErrorResponse(BaseModel):
    """Standardized error response"""
    status: ResponseStatus = ResponseStatus.ERROR
    error: ErrorDetail
    conversation_id: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        schema_extra = {
            "example": {
                "status": "error",
                "error": {
                    "code": "TOOL_EXECUTION_FAILED",
                    "message": "Failed to connect to Gmail API",
                    "details": {"server": "gmail", "reason": "Authentication failed"}
                },
                "timestamp": "2024-01-08T10:30:00Z"
            }
        }


class HealthResponse(BaseModel):
    """Health check response"""
    status: str = "healthy"
    version: str
    uptime_seconds: float
    mcp_servers: Dict[str, str] = Field(
        ..., 
        description="Status of each MCP server: 'active', 'inactive', 'error'"
    )
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ServerStatusResponse(BaseModel):
    """Status of individual MCP server"""
    server_name: str
    status: str = Field(..., description="'connected', 'disconnected', 'error'")
    tools_count: int
    last_check: datetime
    error_message: Optional[str] = None