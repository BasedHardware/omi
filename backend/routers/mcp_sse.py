"""
Pre-hosted MCP Server via Streamable HTTP Transport

This module provides a streamable HTTP transport for MCP (Model Context Protocol),
allowing clients to connect without running a local MCP server.

Implements the MCP 2025-03-26 Streamable HTTP Transport specification.
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime
from typing import Optional, Union, List, Any

from fastapi import APIRouter, HTTPException, Header, Request, Response
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel

import database.memories as memories_db
import database.conversations as conversations_db
import database.mcp_api_key as mcp_api_key_db
from models.memories import MemoryDB, Memory, MemoryCategory
from models.conversation import CategoryEnum
from utils.llm.memories import identify_category_for_memory

router = APIRouter()

# Store active sessions
active_sessions: dict = {}


class MCPSession:
    """Represents an active MCP session."""
    
    def __init__(self, session_id: str, user_id: str):
        self.session_id = session_id
        self.user_id = user_id
        self.created_at = datetime.utcnow()
        self.initialized = False


def authenticate_api_key(authorization: Optional[str]) -> Optional[str]:
    """Validate API key from Authorization header and return user_id if valid."""
    if not authorization:
        return None
    
    # Support both "Bearer <key>" and just "<key>" formats
    token = authorization
    if authorization.startswith("Bearer "):
        token = authorization[7:]
    
    if not token.startswith("omi_mcp_"):
        return None
    
    return mcp_api_key_db.get_user_id_by_api_key(token)


# MCP Tool Definitions
MCP_TOOLS = [
    {
        "name": "get_memories",
        "description": "Retrieve a list of memories. A memory is a known fact about the user across multiple domains.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "categories": {
                    "type": "array",
                    "items": {"type": "string", "enum": [c.value for c in MemoryCategory]},
                    "description": "Categories to filter by",
                    "default": []
                },
                "limit": {"type": "integer", "description": "Number of memories to retrieve", "default": 100},
                "offset": {"type": "integer", "description": "Offset for pagination", "default": 0}
            }
        }
    },
    {
        "name": "create_memory",
        "description": "Create a new memory. A memory is a known fact about the user across multiple domains.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "The content of the memory"},
                "category": {"type": "string", "enum": [c.value for c in MemoryCategory], "description": "The category of the memory"}
            },
            "required": ["content"]
        }
    },
    {
        "name": "delete_memory",
        "description": "Delete a memory by ID.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "memory_id": {"type": "string", "description": "The ID of the memory to delete"}
            },
            "required": ["memory_id"]
        }
    },
    {
        "name": "edit_memory",
        "description": "Edit a memory's content.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "memory_id": {"type": "string", "description": "The ID of the memory to edit"},
                "content": {"type": "string", "description": "The new content for the memory"}
            },
            "required": ["memory_id", "content"]
        }
    },
    {
        "name": "get_conversations",
        "description": "Retrieve a list of conversation metadata. To get full transcripts, use get_conversation_by_id.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description": "Filter after this date (yyyy-mm-dd)"},
                "end_date": {"type": "string", "description": "Filter before this date (yyyy-mm-dd)"},
                "categories": {
                    "type": "array",
                    "items": {"type": "string", "enum": [c.value for c in CategoryEnum]},
                    "description": "Categories to filter by",
                    "default": []
                },
                "limit": {"type": "integer", "description": "Number of conversations to retrieve", "default": 20},
                "offset": {"type": "integer", "description": "Offset for pagination", "default": 0}
            }
        }
    },
    {
        "name": "get_conversation_by_id",
        "description": "Retrieve a conversation by ID including each segment of the transcript.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "conversation_id": {"type": "string", "description": "The ID of the conversation to retrieve"}
            },
            "required": ["conversation_id"]
        }
    }
]


class ToolExecutionError(Exception):
    """Exception raised when a tool execution fails."""
    def __init__(self, message: str, code: int = -32000):
        self.message = message
        self.code = code
        super().__init__(self.message)


def execute_tool(user_id: str, tool_name: str, arguments: dict) -> dict:
    """Execute an MCP tool and return the result. Raises ToolExecutionError on failure."""
    
    if tool_name == "get_memories":
        categories = arguments.get("categories", [])
        limit = arguments.get("limit", 100)
        offset = arguments.get("offset", 0)
        
        # Validate categories
        valid_categories = []
        for cat in categories:
            try:
                valid_categories.append(MemoryCategory(cat).value)
            except ValueError:
                raise ToolExecutionError(f"Invalid memory category: '{cat}'", code=-32602)
        
        memories = memories_db.get_memories(user_id, limit, offset, valid_categories)
        # Apply locked content truncation
        for memory in memories:
            if memory.get('is_locked', False):
                content = memory.get('content', '')
                memory['content'] = (content[:70] + '...') if len(content) > 70 else content
        
        return {"memories": memories}
    
    elif tool_name == "create_memory":
        content = arguments.get("content")
        if not content:
            raise ToolExecutionError("Content is required")
        
        memory = Memory(content=content)
        categories = [category for category in MemoryCategory]
        memory.category = identify_category_for_memory(memory.content, categories)
        memory_db = MemoryDB.from_memory(memory, user_id, None, True)
        memories_db.create_memory(user_id, memory_db.model_dump())
        
        return {"success": True, "memory": memory_db.model_dump()}
    
    elif tool_name == "delete_memory":
        memory_id = arguments.get("memory_id")
        if not memory_id:
            raise ToolExecutionError("memory_id is required")
        
        memories_db.delete_memory(user_id, memory_id)
        return {"success": True}
    
    elif tool_name == "edit_memory":
        memory_id = arguments.get("memory_id")
        content = arguments.get("content")
        if not memory_id or not content:
            raise ToolExecutionError("memory_id and content are required")
        
        memories_db.edit_memory(user_id, memory_id, content)
        return {"success": True}
    
    elif tool_name == "get_conversations":
        start_date = arguments.get("start_date")
        end_date = arguments.get("end_date")
        categories = arguments.get("categories", [])
        limit = arguments.get("limit", 20)
        offset = arguments.get("offset", 0)
        
        # Parse dates
        start_dt = None
        end_dt = None
        if start_date:
            try:
                start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            except ValueError:
                raise ToolExecutionError(f"Invalid start_date format: '{start_date}'. Expected YYYY-MM-DD.", code=-32602)
        if end_date:
            try:
                end_dt = datetime.strptime(end_date, "%Y-%m-%d")
            except ValueError:
                raise ToolExecutionError(f"Invalid end_date format: '{end_date}'. Expected YYYY-MM-DD.", code=-32602)
        
        # Validate categories
        valid_categories = []
        for cat in categories:
            try:
                valid_categories.append(CategoryEnum(cat).value)
            except ValueError:
                pass
        
        conversations = conversations_db.get_conversations(
            user_id, limit, offset,
            include_discarded=False,
            statuses=["completed"],
            start_date=start_dt,
            end_date=end_dt,
            categories=valid_categories
        )
        
        # Simplify conversation data
        simple_conversations = []
        for conv in conversations:
            simple_conversations.append({
                "id": conv.get("id"),
                "started_at": conv.get("started_at"),
                "finished_at": conv.get("finished_at"),
                "structured": conv.get("structured"),
                "language": conv.get("language")
            })
        
        return {"conversations": simple_conversations}
    
    elif tool_name == "get_conversation_by_id":
        conversation_id = arguments.get("conversation_id")
        if not conversation_id:
            raise ToolExecutionError("conversation_id is required")
        
        conversation = conversations_db.get_conversation(user_id, conversation_id)
        if not conversation:
            raise ToolExecutionError("Conversation not found", code=-32001)
        
        if conversation.get('is_locked', False):
            raise ToolExecutionError("Unlimited Plan Required to access this conversation.", code=-32002)
        
        return {"conversation": conversation}
    
    else:
        raise ToolExecutionError(f"Unknown tool: {tool_name}", code=-32601)


def create_mcp_response(id: Any, result: dict) -> dict:
    """Create a JSON-RPC 2.0 response."""
    return {
        "jsonrpc": "2.0",
        "id": id,
        "result": result
    }


def create_mcp_error(id: Any, code: int, message: str) -> dict:
    """Create a JSON-RPC 2.0 error response."""
    return {
        "jsonrpc": "2.0",
        "id": id,
        "error": {
            "code": code,
            "message": message
        }
    }


def handle_mcp_message(user_id: str, message: dict, session: Optional[MCPSession] = None) -> tuple[Optional[dict], Optional[str]]:
    """
    Process an incoming MCP JSON-RPC message and return a response.
    Returns (response, new_session_id) tuple.
    """
    msg_id = message.get("id")
    method = message.get("method")
    params = message.get("params", {})
    new_session_id = None
    
    if method == "initialize":
        # Create a new session
        session_id = str(uuid.uuid4())
        new_session = MCPSession(session_id, user_id)
        new_session.initialized = True
        active_sessions[session_id] = new_session
        new_session_id = session_id
        
        return create_mcp_response(msg_id, {
            "protocolVersion": "2025-03-26",
            "capabilities": {
                "tools": {}
            },
            "serverInfo": {
                "name": "omi-mcp-server",
                "version": "1.0.0"
            }
        }), new_session_id
    
    elif method == "notifications/initialized":
        # This is a notification, no response needed
        return None, None
    
    elif method == "tools/list":
        return create_mcp_response(msg_id, {
            "tools": MCP_TOOLS
        }), None
    
    elif method == "tools/call":
        tool_name = params.get("name")
        arguments = params.get("arguments", {})
        
        if not tool_name:
            return create_mcp_error(msg_id, -32602, "Tool name is required"), None
        
        try:
            result = execute_tool(user_id, tool_name, arguments)
        except ToolExecutionError as e:
            return create_mcp_error(msg_id, e.code, e.message), None
        
        return create_mcp_response(msg_id, {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(result, indent=2, default=str)
                }
            ]
        }), None
    
    elif method == "ping":
        return create_mcp_response(msg_id, {}), None
    
    else:
        return create_mcp_error(msg_id, -32601, f"Method not found: {method}"), None


@router.post("/v1/mcp/sse", tags=["mcp"])
async def mcp_streamable_http(
    request: Request,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    mcp_session_id: Optional[str] = Header(None, alias="Mcp-Session-Id"),
    accept: Optional[str] = Header(None, alias="Accept"),
):
    """
    Streamable HTTP Transport endpoint for MCP clients.
    
    This implements the MCP 2025-03-26 Streamable HTTP Transport specification.
    
    - POST JSON-RPC messages to this endpoint
    - Responses are returned as SSE stream or JSON depending on Accept header
    - Session ID is returned in Mcp-Session-Id header after initialization
    """
    # Authenticate
    user_id = authenticate_api_key(authorization)
    if not user_id:
        raise HTTPException(
            status_code=401, 
            detail="Invalid or missing API key. Provide via Authorization header."
        )
    
    # Parse request body
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    
    # Get session if provided
    session = None
    if mcp_session_id and mcp_session_id in active_sessions:
        session = active_sessions[mcp_session_id]
        # Verify session belongs to this user
        if session.user_id != user_id:
            raise HTTPException(status_code=403, detail="Session does not belong to this user")
    
    # Handle batch requests (array of messages)
    messages = body if isinstance(body, list) else [body]
    
    # Check if all messages are notifications/responses (no id)
    all_notifications = all(msg.get("id") is None for msg in messages)
    
    if all_notifications:
        # Process notifications without response
        for msg in messages:
            handle_mcp_message(user_id, msg, session)
        return Response(status_code=202)
    
    # Process messages and collect responses
    responses = []
    new_session_id = None
    
    for msg in messages:
        response, session_id = handle_mcp_message(user_id, msg, session)
        if session_id:
            new_session_id = session_id
        if response:
            responses.append(response)
    
    # Prepare headers
    headers = {}
    if new_session_id:
        headers["Mcp-Session-Id"] = new_session_id
    
    # Check if client accepts SSE
    wants_sse = accept and "text/event-stream" in accept
    
    if wants_sse:
        # Return as SSE stream
        async def event_generator():
            for resp in responses:
                yield f"event: message\ndata: {json.dumps(resp, default=str)}\n\n"
        
        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                **headers,
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )
    else:
        # Return as JSON
        if len(responses) == 1:
            return JSONResponse(content=responses[0], headers=headers)
        else:
            return JSONResponse(content=responses, headers=headers)


@router.get("/v1/mcp/sse", tags=["mcp"])
async def mcp_sse_get(
    request: Request,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    mcp_session_id: Optional[str] = Header(None, alias="Mcp-Session-Id"),
):
    """
    SSE endpoint for server-initiated messages (optional).
    
    Clients can GET this endpoint to listen for server-initiated notifications.
    This is optional per the MCP spec and mainly used for long-polling scenarios.
    """
    # Authenticate
    user_id = authenticate_api_key(authorization)
    if not user_id:
        raise HTTPException(
            status_code=401, 
            detail="Invalid or missing API key. Provide via Authorization header."
        )
    
    # For backwards compatibility, also support the old SSE flow
    # Return an empty SSE stream that just sends keepalives
    async def event_generator():
        try:
            while True:
                if await request.is_disconnected():
                    break
                yield f"event: ping\ndata: {{}}\n\n"
                await asyncio.sleep(30)
        except asyncio.CancelledError:
            # Normal cancellation when client disconnects
            pass
        except Exception as e:
            logging.warning(f"MCP SSE event generator error: {e}")
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@router.delete("/v1/mcp/sse", tags=["mcp"])
async def mcp_delete_session(
    mcp_session_id: Optional[str] = Header(None, alias="Mcp-Session-Id"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
):
    """
    Delete/terminate an MCP session.
    """
    user_id = authenticate_api_key(authorization)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    
    if not mcp_session_id:
        raise HTTPException(status_code=400, detail="Mcp-Session-Id header required")
    
    if mcp_session_id not in active_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = active_sessions[mcp_session_id]
    if session.user_id != user_id:
        raise HTTPException(status_code=403, detail="Not authorized to delete this session")
    
    # Delete the session
    del active_sessions[mcp_session_id]
    return Response(status_code=204)


@router.get("/v1/mcp/sse/info", tags=["mcp"])
async def mcp_sse_info(request: Request):
    """
    Get information about the pre-hosted MCP server.
    """
    base_url = str(request.base_url).rstrip("/")
    return {
        "endpoint": "/v1/mcp/sse",
        "transport": "streamable-http",
        "protocol_version": "2025-03-26",
        "authentication": {
            "methods": ["api_key"],
            "api_key": {
                "header": "Authorization",
                "format": "Bearer <api_key>"
            }
        },
        "instructions": {
            "step1": "Create an MCP API key in the Omi app (Settings > Developer > MCP)",
            "step2": f"Set Server URL to: {base_url}/v1/mcp/sse",
            "step3": "Set Authorization header to your key"
        }
    }



