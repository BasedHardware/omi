"""
Pre-hosted MCP Server via Streamable HTTP Transport

This module provides a streamable HTTP transport for MCP (Model Context Protocol),
allowing clients to connect without running a local MCP server.

Implements the MCP 2025-03-26 Streamable HTTP Transport specification.
"""

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Any, Dict, List, Tuple, NoReturn, cast
from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qsl

from pydantic import BaseModel

import firebase_admin.auth
from google.api_core.exceptions import FailedPrecondition
from fastapi import APIRouter, HTTPException, Header, Request, Response, Form
from fastapi.responses import StreamingResponse, JSONResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from utils.other.endpoints import check_rate_limit_inline
from utils.executors import critical_executor, db_executor, run_blocking

import database.memories as memories_db
import database.conversations as conversations_db
import database.mcp_api_key as mcp_api_key_db
import database.mcp_oauth as mcp_oauth_db
import database.vector_db as vector_db
import database.x_posts as x_posts_db
import database.users as users_db
import database.action_items as action_items_db
import database.goals as goals_db
import database.chat as chat_db
import database.screen_activity as screen_activity_db
import database.daily_summaries as daily_summaries_db
from database._client import db
from models.memories import MemoryDB, Memory, MemoryCategory
from utils.conversations.render import redact_conversation_for_list
from models.conversation_enums import CategoryEnum
from utils.llm.memories import identify_category_for_memory
from utils.memory.default_read_rollout import (
    MemoryReadDecision,
    read_default_read_rollout,
)
from utils.memory.memory_service import (
    MemoryService,
    raise_if_legacy_write_blocked,
    resolve_external_memory_write_context,
)
from utils.memory.memory_api_contract import MemoryApiExposure, memory_api_payload
from utils.memory.memory_system import MemorySystem
from utils.memory.product_authorization import (
    ProductAuthorizationContext,
    authorize_memory_external_default_memory_read,
    authorize_memory_external_default_memory_write,
)
from utils.memory.surface_routing import pin_memory_system
from utils.mcp_data import clean_action_item, clean_chat_message, clean_person, clean_screen_activity_row
import utils.mcp_action_items as mcp_action_items
from utils.mcp_memories import (
    McpVerifiedAuth,
    build_mcp_default_memory_read_context,
    collect_filtered_memories,
    list_default_mcp_memories,
    parse_mcp_bool,
    parse_mcp_datetime,
    parse_mcp_int,
    parse_optional_mcp_bool,
    search_default_mcp_memories_vector,
)
from utils.mcp_scopes import MCP_FULL_ACCESS_SCOPES

router = APIRouter()
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

MCP_RESOURCE_URL = mcp_oauth_db.MCP_RESOURCE_URL
MCP_AUTHORIZATION_SERVER_URL = os.getenv("MCP_AUTHORIZATION_SERVER_URL", "https://api.omi.me")
MCP_AUTHORIZATION_ENDPOINT = f"{MCP_AUTHORIZATION_SERVER_URL}/authorize"
MCP_TOKEN_ENDPOINT = f"{MCP_AUTHORIZATION_SERVER_URL}/token"
MCP_PROTECTED_RESOURCE_METADATA_URL = f"{MCP_AUTHORIZATION_SERVER_URL}/.well-known/oauth-protected-resource/v1/mcp/sse"
OPENAI_APPS_CHALLENGE_TOKEN = "ZsVB_wpc4R35_tHloCZCokY6H2fBkKyBJrz-4MtXjYE"

MCP_SCOPES_SUPPORTED = list(MCP_FULL_ACCESS_SCOPES)
MCP_LEGACY_API_KEY_SCOPES = list(MCP_FULL_ACCESS_SCOPES)

READ_ONLY_ANNOTATIONS = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "openWorldHint": False,
}

WRITE_ANNOTATIONS = {
    "readOnlyHint": False,
    "destructiveHint": False,
    "openWorldHint": False,
}

DESTRUCTIVE_WRITE_ANNOTATIONS = {
    "readOnlyHint": False,
    "destructiveHint": True,
    "openWorldHint": False,
}

MEMORIES_READ_SECURITY = [{"type": "oauth2", "scopes": ["memories.read"]}]
MEMORIES_WRITE_SECURITY = [{"type": "oauth2", "scopes": ["memories.write"]}]
CONVERSATIONS_READ_SECURITY = [{"type": "oauth2", "scopes": ["conversations.read"]}]
ACTION_ITEMS_READ_SECURITY = [{"type": "oauth2", "scopes": ["action_items.read"]}]
ACTION_ITEMS_WRITE_SECURITY = [{"type": "oauth2", "scopes": ["action_items.write"]}]
GOALS_READ_SECURITY = [{"type": "oauth2", "scopes": ["goals.read"]}]
CHAT_READ_SECURITY = [{"type": "oauth2", "scopes": ["chat.read"]}]
SCREEN_ACTIVITY_READ_SECURITY = [{"type": "oauth2", "scopes": ["screen_activity.read"]}]
PEOPLE_READ_SECURITY = [{"type": "oauth2", "scopes": ["people.read"]}]


@dataclass
class MCPAuthContext:
    uid: str
    auth_type: str
    scopes: list[str]
    app_id: Optional[str] = None
    key_id: Optional[str] = None
    client_id: Optional[str] = None
    resource: Optional[str] = None
    grant_id: Optional[str] = None
    memory_context: Optional[ProductAuthorizationContext] = None


def _mcp_memory_context_from_api_key_user_data(user_data: Dict[str, Any]) -> ProductAuthorizationContext:
    verified_auth = McpVerifiedAuth(
        uid=user_data["user_id"],
        app_id=user_data.get("app_id"),
        key_id=user_data.get("key_id"),
        scopes=tuple(user_data.get("scopes") or ()),
    )
    return build_mcp_default_memory_read_context(verified_auth)


def authenticate_api_key_auth_context(authorization: Optional[str]) -> Optional[ProductAuthorizationContext]:
    """Validate an MCP API key and return its memory product auth context."""
    if not authorization:
        return None

    token = authorization
    if authorization.startswith("Bearer "):
        token = authorization[7:]

    if not token.startswith("omi_mcp_"):
        return None

    user_data = mcp_api_key_db.get_user_and_scopes_by_api_key(token)
    if not user_data or not user_data.get("user_id"):
        return None
    return _mcp_memory_context_from_api_key_user_data(user_data)


def authenticate_mcp_request(authorization: Optional[str]) -> Optional[MCPAuthContext]:
    """Validate Authorization and return an MCP auth context."""
    if not authorization:
        return None

    token = authorization
    if authorization.startswith("Bearer "):
        token = authorization[7:]

    if token.startswith("omi_mcp_"):
        user_data = mcp_api_key_db.get_user_and_scopes_by_api_key(token)
        if not user_data or not user_data.get("user_id"):
            return None
        return MCPAuthContext(
            uid=user_data["user_id"],
            auth_type="legacy_mcp_key",
            scopes=list(user_data.get("scopes") or MCP_LEGACY_API_KEY_SCOPES),
            app_id=user_data.get("app_id"),
            key_id=user_data.get("key_id"),
            memory_context=_mcp_memory_context_from_api_key_user_data(user_data),
        )

    oauth_context = mcp_oauth_db.validate_access_token(token, MCP_RESOURCE_URL)
    if not oauth_context:
        return None
    return MCPAuthContext(
        uid=oauth_context["uid"],
        auth_type="oauth",
        scopes=oauth_context.get("scopes") or [],
        client_id=oauth_context.get("client_id"),
        resource=oauth_context.get("resource"),
        grant_id=oauth_context.get("grant_id"),
    )


def authenticate_api_key(authorization: Optional[str]) -> Optional[str]:
    """Validate API key from Authorization header and return user_id if valid."""
    auth_context = authenticate_mcp_request(authorization)
    if not auth_context or auth_context.auth_type != "legacy_mcp_key":
        return None
    return auth_context.uid


def invalid_mcp_auth_exception(
    detail: str = "Invalid or missing API key. Provide via Authorization header.",
) -> HTTPException:
    """Return an MCP OAuth discovery hint for clients that need authorization."""
    return HTTPException(
        status_code=401,
        detail=detail,
        headers={
            "WWW-Authenticate": (
                f'Bearer resource_metadata="{MCP_PROTECTED_RESOURCE_METADATA_URL}", '
                'error="invalid_token", '
                'error_description="Valid Omi MCP OAuth bearer token required"'
            )
        },
    )


TOOL_REQUIRED_SCOPE = {
    "get_user_profile": "memories.read",
    "get_memories": "memories.read",
    "search_memories": "memories.read",
    "create_memory": "memories.write",
    "edit_memory": "memories.write",
    "delete_memory": "memories.write",
    "get_conversations": "conversations.read",
    "search_conversations": "conversations.read",
    "get_conversation_by_id": "conversations.read",
    "get_daily_summaries": "conversations.read",
    "search_x_posts": "memories.read",
    "get_x_posts": "memories.read",
    "get_action_items": "action_items.read",
    "search_action_items": "action_items.read",
    "create_action_item": "action_items.write",
    "complete_action_item": "action_items.write",
    "update_action_item": "action_items.write",
    "delete_action_item": "action_items.write",
    "get_goals": "goals.read",
    "get_chat_messages": "chat.read",
    "get_people": "people.read",
    "get_screen_activity": "screen_activity.read",
    "get_daily_summaries": "conversations.read",
}


SCOPE_PERMISSION_TEXT = {
    "memories.read": "Read your Omi memories",
    "memories.write": "Create, edit, and delete your Omi memories",
    "conversations.read": "Search and read your Omi conversations",
    "action_items.read": "Read your Omi action items",
    "action_items.write": "Create, update, and delete your Omi action items",
    "goals.read": "Read your Omi goals",
    "chat.read": "Read your Omi chat history",
    "screen_activity.read": "Read your Omi screen activity",
    "people.read": "Read people saved in your Omi account",
}


def _tools_for_scopes(scopes: List[str]) -> List[Dict[str, Any]]:
    scope_set = set(scopes)
    return [tool for tool in MCP_TOOLS if TOOL_REQUIRED_SCOPE.get(tool["name"]) in scope_set]


def _require_tool_scope(auth_context: MCPAuthContext, tool_name: str) -> None:
    required_scope = TOOL_REQUIRED_SCOPE.get(tool_name)
    if required_scope and required_scope not in set(auth_context.scopes):
        raise ToolExecutionError(f"Insufficient scope: {required_scope}", code=-32003)


# MCP Tool Definitions
MCP_TOOLS: List[Dict[str, Any]] = [
    {
        "name": "get_user_profile",
        "description": (
            "Get Omi's cached high-level summary of the user, if one has been generated. Use this as a "
            "lightweight starting point, then search memories or conversations for task-specific evidence."
        ),
        "annotations": READ_ONLY_ANNOTATIONS,
        "securitySchemes": MEMORIES_READ_SECURITY,
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_memories",
        "description": "Retrieve a list of memories. A memory is a known fact about the user across multiple domains.",
        "annotations": READ_ONLY_ANNOTATIONS,
        "securitySchemes": MEMORIES_READ_SECURITY,
        "inputSchema": {
            "type": "object",
            "properties": {
                "categories": {
                    "type": "array",
                    "items": {"type": "string", "enum": [c.value for c in MemoryCategory]},
                    "description": "Categories to filter by",
                    "default": [],
                },
                "limit": {"type": "integer", "description": "Number of memories to retrieve", "default": 100},
                "offset": {"type": "integer", "description": "Offset for pagination", "default": 0},
                "sort": {
                    "type": "string",
                    "enum": ["scoring_desc", "created_desc", "updated_desc", "manual_first"],
                    "description": "Ordering for returned memories",
                    "default": "created_desc",
                },
                "reviewed": {"type": "boolean", "description": "Filter by reviewed state"},
                "manually_added": {"type": "boolean", "description": "Filter by manually-added state"},
                "updated_after": {
                    "type": "string",
                    "description": "Only return memories updated after this ISO 8601 timestamp",
                },
                "include_activity": {
                    "type": "boolean",
                    "description": "Include obvious focus/screen/activity memories. Durable memory reads exclude these by default.",
                    "default": False,
                },
                "include_sensitive": {
                    "type": "boolean",
                    "description": "Include memories marked above standard data protection. Defaults to true for backward compatibility.",
                    "default": True,
                },
            },
        },
    },
    {
        "name": "create_memory",
        "description": "Create a new memory. A memory is a known fact about the user across multiple domains.",
        "annotations": WRITE_ANNOTATIONS,
        "securitySchemes": MEMORIES_WRITE_SECURITY,
        "inputSchema": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "The content of the memory"},
                "category": {
                    "type": "string",
                    "enum": [c.value for c in MemoryCategory],
                    "description": "The category of the memory",
                },
            },
            "required": ["content"],
        },
    },
    {
        "name": "delete_memory",
        "description": "Delete a memory by ID.",
        "annotations": DESTRUCTIVE_WRITE_ANNOTATIONS,
        "securitySchemes": MEMORIES_WRITE_SECURITY,
        "inputSchema": {
            "type": "object",
            "properties": {"memory_id": {"type": "string", "description": "The ID of the memory to delete"}},
            "required": ["memory_id"],
        },
    },
    {
        "name": "edit_memory",
        "description": "Edit a memory's content.",
        "annotations": DESTRUCTIVE_WRITE_ANNOTATIONS,
        "securitySchemes": MEMORIES_WRITE_SECURITY,
        "inputSchema": {
            "type": "object",
            "properties": {
                "memory_id": {"type": "string", "description": "The ID of the memory to edit"},
                "content": {"type": "string", "description": "The new content for the memory"},
            },
            "required": ["memory_id", "content"],
        },
    },
    {
        "name": "get_conversations",
        "description": "Retrieve a list of conversation metadata. To get full transcripts, use get_conversation_by_id.",
        "annotations": READ_ONLY_ANNOTATIONS,
        "securitySchemes": CONVERSATIONS_READ_SECURITY,
        "inputSchema": {
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description": "Filter after this date (yyyy-mm-dd)"},
                "end_date": {"type": "string", "description": "Filter before this date (yyyy-mm-dd)"},
                "categories": {
                    "type": "array",
                    "items": {"type": "string", "enum": [c.value for c in CategoryEnum]},
                    "description": "Categories to filter by",
                    "default": [],
                },
                "limit": {"type": "integer", "description": "Number of conversations to retrieve", "default": 20},
                "offset": {"type": "integer", "description": "Offset for pagination", "default": 0},
            },
        },
    },
    {
        "name": "get_conversation_by_id",
        "description": "Retrieve a conversation by ID including each segment of the transcript.",
        "annotations": READ_ONLY_ANNOTATIONS,
        "securitySchemes": CONVERSATIONS_READ_SECURITY,
        "inputSchema": {
            "type": "object",
            "properties": {
                "conversation_id": {"type": "string", "description": "The ID of the conversation to retrieve"}
            },
            "required": ["conversation_id"],
        },
    },
    {
        "name": "search_memories",
        "description": "Semantic search across the user's memories. Returns memories ranked by relevance to the query.",
        "annotations": READ_ONLY_ANNOTATIONS,
        "securitySchemes": MEMORIES_READ_SECURITY,
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Natural language search query"},
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results to return",
                    "default": 10,
                    "minimum": 1,
                    "maximum": 20,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "search_conversations",
        "description": "Semantic search across the user's conversations. Returns conversations ranked by relevance to the query.",
        "annotations": READ_ONLY_ANNOTATIONS,
        "securitySchemes": CONVERSATIONS_READ_SECURITY,
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Natural language search query"},
                "start_date": {"type": "string", "description": "Filter after this date (yyyy-mm-dd)"},
                "end_date": {"type": "string", "description": "Filter before this date (yyyy-mm-dd)"},
                "limit": {"type": "integer", "description": "Maximum number of results to return", "default": 10},
            },
            "required": ["query"],
        },
    },
    {
        "name": "search_x_posts",
        "description": (
            "Semantic search across the user's imported X (Twitter) posts — their actual tweets and "
            "bookmarks, not just extracted memories. Returns posts ranked by relevance to the query."
        ),
        "annotations": READ_ONLY_ANNOTATIONS,
        "securitySchemes": MEMORIES_READ_SECURITY,
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Natural language search query"},
                "limit": {"type": "integer", "description": "Maximum number of results to return", "default": 10},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_x_posts",
        "description": (
            "Retrieve the user's imported X (Twitter) posts, newest first. Optionally filter by kind "
            "(tweet or bookmark). Returns the raw post text, created_at, and id."
        ),
        "annotations": READ_ONLY_ANNOTATIONS,
        "securitySchemes": MEMORIES_READ_SECURITY,
        "inputSchema": {
            "type": "object",
            "properties": {
                "kind": {
                    "type": "string",
                    "enum": ["tweet", "bookmark"],
                    "description": "Filter to only tweets or only bookmarks (omit for all)",
                },
                "limit": {"type": "integer", "description": "Number of posts to retrieve", "default": 50},
            },
        },
    },
    {
        "name": "get_action_items",
        "description": (
            "Retrieve the user's action items (tasks/to-dos extracted from conversations), newest due first. "
            "Each item has a description, completion status, and optional due date. Use this to know what the "
            "user needs to do or has committed to."
        ),
        "annotations": READ_ONLY_ANNOTATIONS,
        "securitySchemes": ACTION_ITEMS_READ_SECURITY,
        "inputSchema": {
            "type": "object",
            "properties": {
                "completed": {"type": "boolean", "description": "Filter by completion status (omit for all)"},
                "due_start_date": {"type": "string", "description": "Only items due on/after this date (yyyy-mm-dd)"},
                "due_end_date": {"type": "string", "description": "Only items due on/before this date (yyyy-mm-dd)"},
                "limit": {"type": "integer", "description": "Number of action items to retrieve", "default": 100},
                "offset": {"type": "integer", "description": "Offset for pagination", "default": 0},
            },
        },
    },
    {
        "name": "search_action_items",
        "description": (
            "Semantic search across the user's action items (tasks/to-dos). Returns tasks ranked by relevance to "
            "the query — use this to find a specific task by what it is about before completing or updating it."
        ),
        "annotations": READ_ONLY_ANNOTATIONS,
        "securitySchemes": ACTION_ITEMS_READ_SECURITY,
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What to search the user's tasks for"},
                "limit": {"type": "integer", "description": "Max number of tasks to return (1-50)", "default": 10},
            },
            "required": ["query"],
        },
    },
    {
        "name": "create_action_item",
        "description": (
            "Create a new action item (task/to-do) for the user — for example a follow-up you identified while "
            "helping them. Retries with the same description return the existing task instead of duplicating it."
        ),
        "annotations": WRITE_ANNOTATIONS,
        "securitySchemes": ACTION_ITEMS_WRITE_SECURITY,
        "inputSchema": {
            "type": "object",
            "properties": {
                "description": {"type": "string", "description": "What the user needs to do"},
                "due_at": {
                    "type": "string",
                    "description": "Optional due date/time, ISO 8601 (2026-07-01T17:00:00Z) or YYYY-MM-DD",
                },
                "completed": {
                    "type": "boolean",
                    "description": "Create it already completed (default false)",
                    "default": False,
                },
            },
            "required": ["description"],
        },
    },
    {
        "name": "complete_action_item",
        "description": "Mark an action item complete, or reopen it by passing completed=false.",
        "annotations": WRITE_ANNOTATIONS,
        "securitySchemes": ACTION_ITEMS_WRITE_SECURITY,
        "inputSchema": {
            "type": "object",
            "properties": {
                "action_item_id": {"type": "string", "description": "The ID of the action item"},
                "completed": {
                    "type": "boolean",
                    "description": "True to complete (default), false to reopen",
                    "default": True,
                },
            },
            "required": ["action_item_id"],
        },
    },
    {
        "name": "update_action_item",
        "description": (
            "Update an action item's description and/or due date. Only the fields you pass are changed; an omitted "
            "due date is left unchanged."
        ),
        "annotations": WRITE_ANNOTATIONS,
        "securitySchemes": ACTION_ITEMS_WRITE_SECURITY,
        "inputSchema": {
            "type": "object",
            "properties": {
                "action_item_id": {"type": "string", "description": "The ID of the action item"},
                "description": {"type": "string", "description": "New description for the task"},
                "due_at": {
                    "type": "string",
                    "description": "New due date/time, ISO 8601 (2026-07-01T17:00:00Z) or YYYY-MM-DD",
                },
            },
            "required": ["action_item_id"],
        },
    },
    {
        "name": "delete_action_item",
        "description": "Delete an action item by ID. Use this to clean up a task that is no longer relevant.",
        "annotations": DESTRUCTIVE_WRITE_ANNOTATIONS,
        "securitySchemes": ACTION_ITEMS_WRITE_SECURITY,
        "inputSchema": {
            "type": "object",
            "properties": {
                "action_item_id": {"type": "string", "description": "The ID of the action item to delete"},
            },
            "required": ["action_item_id"],
        },
    },
    {
        "name": "get_goals",
        "description": (
            "Retrieve the user's goals — their stated objectives and what they are working toward. Use this to "
            "ground long-horizon advice and prioritization in what actually matters to the user."
        ),
        "annotations": READ_ONLY_ANNOTATIONS,
        "securitySchemes": GOALS_READ_SECURITY,
        "inputSchema": {
            "type": "object",
            "properties": {
                "include_inactive": {
                    "type": "boolean",
                    "description": "Include ended/inactive goals (default only active goals)",
                    "default": False,
                },
            },
        },
    },
    {
        "name": "get_chat_messages",
        "description": (
            "Retrieve the user's recent chat history with Omi, newest first. Reveals what the user has previously "
            "asked, their intent, and stated preferences. Returns message text, sender (human/ai), and timestamp."
        ),
        "annotations": READ_ONLY_ANNOTATIONS,
        "securitySchemes": CHAT_READ_SECURITY,
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Number of messages to retrieve", "default": 50},
                "offset": {"type": "integer", "description": "Offset for pagination", "default": 0},
            },
        },
    },
    {
        "name": "get_people",
        "description": (
            "Retrieve the people/contacts the user interacts with (recurring speakers Omi has identified). "
            "Returns each person's name, id, and a few transcript samples of how they speak. Use this to reason "
            "about the user's relationships, not just raw text."
        ),
        "annotations": READ_ONLY_ANNOTATIONS,
        "securitySchemes": PEOPLE_READ_SECURITY,
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_screen_activity",
        "description": (
            "Retrieve the user's desktop screen activity (Rewind) — what apps and windows they used and the OCR'd "
            "on-screen text, ordered by time. Pass summary=true for an aggregated per-app usage breakdown instead "
            "of raw rows. High-signal context on what the user actually does day to day."
        ),
        "annotations": READ_ONLY_ANNOTATIONS,
        "securitySchemes": SCREEN_ACTIVITY_READ_SECURITY,
        "inputSchema": {
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description": "Filter on/after this date (yyyy-mm-dd)"},
                "end_date": {"type": "string", "description": "Filter on/before this date (yyyy-mm-dd)"},
                "app": {"type": "string", "description": "Filter to a single app name"},
                "summary": {
                    "type": "boolean",
                    "description": "Return an aggregated per-app usage summary instead of raw rows",
                    "default": False,
                },
                "limit": {
                    "type": "integer",
                    "description": "Max raw rows to return (ignored when summary=true)",
                    "default": 200,
                },
            },
        },
    },
    {
        "name": "get_daily_summaries",
        "description": (
            "Retrieve Omi's per-day summaries of the user's life, newest first. A concise digest of what happened "
            "each day. Use for temporal context — 'what has the user been up to lately'."
        ),
        "annotations": READ_ONLY_ANNOTATIONS,
        "securitySchemes": CONVERSATIONS_READ_SECURITY,
        "inputSchema": {
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description": "Filter on/after this date (yyyy-mm-dd)"},
                "end_date": {"type": "string", "description": "Filter on/before this date (yyyy-mm-dd)"},
                "limit": {"type": "integer", "description": "Number of summaries to retrieve", "default": 30},
                "offset": {"type": "integer", "description": "Offset for pagination", "default": 0},
            },
        },
    },
]


@router.get("/.well-known/oauth-protected-resource", tags=["mcp"])
@router.get("/.well-known/oauth-protected-resource/v1/mcp/sse", tags=["mcp"])
def oauth_protected_resource_metadata():
    return {
        "resource": MCP_RESOURCE_URL,
        "authorization_servers": [MCP_AUTHORIZATION_SERVER_URL],
        "scopes_supported": MCP_SCOPES_SUPPORTED,
        "bearer_methods_supported": ["header"],
        "resource_documentation": "https://docs.omi.me/doc/developer/mcp/setup",
    }


@router.head("/.well-known/oauth-protected-resource", tags=["mcp"])
@router.head("/.well-known/oauth-protected-resource/v1/mcp/sse", tags=["mcp"])
def oauth_protected_resource_metadata_head():
    return Response(status_code=200)


@router.get("/.well-known/oauth-authorization-server", tags=["mcp"])
def oauth_authorization_server_metadata():
    return {
        "issuer": MCP_AUTHORIZATION_SERVER_URL,
        "authorization_endpoint": MCP_AUTHORIZATION_ENDPOINT,
        "token_endpoint": MCP_TOKEN_ENDPOINT,
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": mcp_oauth_db.token_endpoint_auth_methods_supported(),
        "scopes_supported": MCP_SCOPES_SUPPORTED,
    }


@router.head("/.well-known/oauth-authorization-server", tags=["mcp"])
def oauth_authorization_server_metadata_head():
    return Response(status_code=200)


@router.get("/.well-known/openai-apps-challenge", tags=["mcp"])
def openai_apps_challenge():
    return Response(content=OPENAI_APPS_CHALLENGE_TOKEN, media_type="text/plain")


class ToolExecutionError(Exception):
    """Exception raised when a tool execution fails."""

    def __init__(self, message: str, code: int = -32000):
        self.message = message
        self.code = code
        super().__init__(self.message)


def _raise_tool_error_from_http(exc: HTTPException) -> NoReturn:
    if exc.status_code == 404:
        raise ToolExecutionError("Memory not found", code=-32001) from exc
    if exc.status_code == 402:
        raise ToolExecutionError("A paid plan is required to access this memory.", code=-32002) from exc
    if exc.status_code in {403, 409, 503}:
        raise ToolExecutionError(str(exc.detail), code=-32009) from exc
    raise ToolExecutionError(str(exc.detail)) from exc


def _raise_screen_activity_index_error(exc: FailedPrecondition) -> NoReturn:
    """Turn a missing-Firestore-index failure into a typed, actionable tool error.

    The app-filtered screen activity query needs a composite index (appName +
    timestamp). Without it Firestore raises FailedPrecondition, which otherwise
    surfaces to the MCP client as an opaque 500 (see AGENTS.md gotcha #7).
    """
    raise ToolExecutionError(
        "Screen activity isn't queryable right now — its search index is still being built. "
        "Retry in a few minutes, or narrow the request by removing the app filter.",
        code=-32009,
    ) from exc


def _parse_mcp_date(value: Optional[str], field: str) -> Optional[datetime]:
    """Parse a yyyy-mm-dd MCP argument into a datetime, or None when absent."""
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        raise ToolExecutionError(f"Invalid {field} format: '{value}'. Expected YYYY-MM-DD.", code=-32602)


def execute_tool(
    user_id: str,
    tool_name: str,
    arguments: Dict[str, Any],
    auth_context: Optional[ProductAuthorizationContext] = None,
) -> Dict[str, Any]:
    """Execute an MCP tool and return the result. Raises ToolExecutionError on failure."""
    memory_system = pin_memory_system(user_id, db_client=db)

    if tool_name == "get_user_profile":
        profile = users_db.get_ai_user_profile(user_id)
        if not profile or not profile.get("profile_text"):
            return {"profile": None, "message": "No profile has been generated for this user yet."}
        return {
            "profile_text": profile.get("profile_text"),
            "generated_at": profile.get("generated_at"),
            "data_sources_used": profile.get("data_sources_used"),
        }

    elif tool_name == "get_memories":
        raw_categories: object = arguments.get("categories", [])
        categories_list: List[Any] = cast(List[Any], raw_categories) if isinstance(raw_categories, list) else []
        try:
            limit = parse_mcp_int(arguments.get("limit"), "limit", default=100, minimum=1, maximum=500)
            offset = parse_mcp_int(arguments.get("offset"), "offset", default=0, minimum=0, maximum=100000)
            reviewed = parse_optional_mcp_bool(arguments.get("reviewed"), "reviewed")
            manually_added = parse_optional_mcp_bool(arguments.get("manually_added"), "manually_added")
            include_activity = parse_mcp_bool(arguments.get("include_activity"), "include_activity", default=False)
            include_sensitive = parse_mcp_bool(arguments.get("include_sensitive"), "include_sensitive", default=True)
            updated_after = parse_mcp_datetime(arguments.get("updated_after"), "updated_after")
        except ValueError as e:
            raise ToolExecutionError(str(e), code=-32602)
        sort = arguments.get("sort", "created_desc")
        if sort not in {"scoring_desc", "created_desc", "updated_desc", "manual_first"}:
            raise ToolExecutionError(
                "Invalid sort. Expected one of: scoring_desc, created_desc, updated_desc, manual_first.",
                code=-32602,
            )

        # Validate categories
        valid_categories: List[str] = []
        for cat in categories_list:
            try:
                valid_categories.append(MemoryCategory(cat).value)
            except ValueError:
                raise ToolExecutionError(f"Invalid memory category: '{cat}'", code=-32602)

        if auth_context is None:
            raise ToolExecutionError("Missing MCP API app/key identity for memory read authorization", code=-32009)
        app_key_grant = authorize_memory_external_default_memory_read(auth_context, db_client=db)
        if not app_key_grant.allowed:
            raise ToolExecutionError(str(app_key_grant.observability), code=-32009)

        if memory_system == MemorySystem.CANONICAL:
            filtered = collect_filtered_memories(
                lambda batch_offset, batch_limit: [
                    m.model_dump(mode='json')
                    for m in MemoryService(db_client=db).read(user_id, limit=batch_limit, offset=batch_offset)
                ],
                limit=limit,
                offset=offset,
                reviewed=reviewed,
                manually_added=manually_added,
                include_activity=include_activity,
                include_sensitive=include_sensitive,
                updated_after=updated_after,
                sort=sort,
                categories=valid_categories or None,
            )
            memories = filtered['memories']
            for memory in memories:
                if memory.get('is_locked', False):
                    content = memory.get('content', '')
                    memory['content'] = (content[:70] + '...') if len(content) > 70 else content
            return {"memories": memories}

        memory_rollout = read_default_read_rollout(uid=user_id, db_client=db, consumer='mcp')
        memory_list_results = list_default_mcp_memories(
            uid=user_id,
            limit=limit,
            offset=offset,
            db_client=db,
            rollout_decision=memory_rollout,
            categories=valid_categories,
            reviewed=reviewed,
            manually_added=manually_added,
        )
        if memory_list_results.read_decision == MemoryReadDecision.USE_MEMORY:
            return {"memories": memory_list_results.memories}
        if memory_list_results.read_decision != MemoryReadDecision.USE_LEGACY_SAFE:
            return {"memories": []}

        result = collect_filtered_memories(
            lambda batch_offset, batch_limit: memories_db.get_memories(
                user_id, batch_limit, batch_offset, valid_categories, sort=sort
            ),
            limit=limit,
            offset=offset,
            reviewed=reviewed,
            manually_added=manually_added,
            include_activity=include_activity,
            include_sensitive=include_sensitive,
            updated_after=updated_after,
            sort=sort,
        )
        # Apply locked content truncation
        for memory in result["memories"]:
            if memory.get('is_locked', False):
                content = memory.get('content', '')
                memory['content'] = (content[:70] + '...') if len(content) > 70 else content

        return result

    elif tool_name == "create_memory":
        content = arguments.get("content")
        if not content:
            raise ToolExecutionError("Content is required")

        if auth_context is None:
            raise ToolExecutionError("Missing MCP API app/key identity for memory write authorization", code=-32009)
        write_grant = authorize_memory_external_default_memory_write(auth_context, db_client=db)
        if not write_grant.allowed:
            raise ToolExecutionError(str(write_grant.observability), code=-32009)
        try:
            write_context = resolve_external_memory_write_context(
                user_id,
                db_client=db,
                memory_system=memory_system,
                consumer='mcp',
                operation="mcp_tool_memory_create",
            )
            raise_if_legacy_write_blocked(write_context)
        except HTTPException as exc:
            _raise_tool_error_from_http(exc)

        category = identify_category_for_memory(content)
        memory = Memory(content=content, category=category)
        memory_db = MemoryDB.from_memory(memory, user_id, None, True)
        try:
            memory_db = MemoryService(db_client=db).create_external_memory(
                user_id,
                memory_db,
                memory_system=write_context.memory_system,
                consumer='mcp',
                operation="mcp_tool_memory_create",
                upsert_vector=False,
                require_canonical_promotion=True,
            )
        except HTTPException as exc:
            _raise_tool_error_from_http(exc)

        exposure = (
            MemoryApiExposure.CANONICAL
            if write_context.memory_system == MemorySystem.CANONICAL
            else MemoryApiExposure.LEGACY
        )
        return {"success": True, "memory": memory_api_payload(memory_db, exposure)}

    elif tool_name == "delete_memory":
        memory_id = arguments.get("memory_id")
        if not memory_id:
            raise ToolExecutionError("memory_id is required")

        if auth_context is None:
            raise ToolExecutionError("Missing MCP API app/key identity for memory write authorization", code=-32009)
        write_grant = authorize_memory_external_default_memory_write(auth_context, db_client=db)
        if not write_grant.allowed:
            raise ToolExecutionError(str(write_grant.observability), code=-32009)

        try:
            MemoryService(db_client=db).delete_external_memory(
                user_id,
                memory_id,
                memory_system=memory_system,
                consumer='mcp',
                operation="mcp_tool_memory_delete",
                delete_vector=False,
            )
        except HTTPException as exc:
            _raise_tool_error_from_http(exc)
        return {"success": True}

    elif tool_name == "edit_memory":
        memory_id = arguments.get("memory_id")
        content = arguments.get("content")
        if not memory_id or not content:
            raise ToolExecutionError("memory_id and content are required")

        if auth_context is None:
            raise ToolExecutionError("Missing MCP API app/key identity for memory write authorization", code=-32009)
        write_grant = authorize_memory_external_default_memory_write(auth_context, db_client=db)
        if not write_grant.allowed:
            raise ToolExecutionError(str(write_grant.observability), code=-32009)

        if not content.strip():
            raise ToolExecutionError("content must not be empty", code=-32602)
        try:
            MemoryService(db_client=db).update_external_memory_content(
                user_id,
                memory_id,
                content,
                memory_system=memory_system,
                consumer='mcp',
                operation="mcp_tool_memory_edit",
                upsert_vector=False,
            )
        except HTTPException as exc:
            _raise_tool_error_from_http(exc)
        return {"success": True}

    elif tool_name == "get_conversations":
        start_date = arguments.get("start_date")
        end_date = arguments.get("end_date")
        raw_categories = arguments.get("categories", [])
        categories_list: List[Any] = cast(List[Any], raw_categories) if isinstance(raw_categories, list) else []
        try:
            limit = parse_mcp_int(arguments.get("limit"), "limit", default=20, minimum=1, maximum=1000)
            offset = parse_mcp_int(arguments.get("offset"), "offset", default=0, minimum=0, maximum=100000)
        except ValueError as e:
            raise ToolExecutionError(str(e), code=-32602)

        # Parse dates
        start_dt = None
        end_dt = None
        if start_date:
            try:
                start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            except ValueError:
                raise ToolExecutionError(
                    f"Invalid start_date format: '{start_date}'. Expected YYYY-MM-DD.", code=-32602
                )
        if end_date:
            try:
                end_dt = datetime.strptime(end_date, "%Y-%m-%d")
            except ValueError:
                raise ToolExecutionError(f"Invalid end_date format: '{end_date}'. Expected YYYY-MM-DD.", code=-32602)

        # Validate categories
        valid_categories: List[str] = []
        for cat in categories_list:
            try:
                valid_categories.append(CategoryEnum(cat).value)
            except ValueError:
                pass

        conversations = conversations_db.get_conversations(
            user_id,
            limit,
            offset,
            include_discarded=False,
            statuses=["completed"],
            start_date=start_dt,
            end_date=end_dt,
            categories=valid_categories,
        )

        # Simplify conversation data
        simple_conversations: List[Dict[str, Any]] = []
        for conv in conversations:
            redact_conversation_for_list(conv)
            simple_conversations.append(
                {
                    "id": conv.get("id"),
                    "started_at": conv.get("started_at"),
                    "finished_at": conv.get("finished_at"),
                    "structured": conv.get("structured"),
                    "language": conv.get("language"),
                }
            )

        return {"conversations": simple_conversations}

    elif tool_name == "get_conversation_by_id":
        conversation_id = arguments.get("conversation_id")
        if not conversation_id:
            raise ToolExecutionError("conversation_id is required")

        conversation = conversations_db.get_conversation(user_id, conversation_id)
        if not conversation:
            raise ToolExecutionError("Conversation not found", code=-32001)

        if conversation.get('is_locked', False):
            raise ToolExecutionError("A paid plan is required to access this conversation.", code=-32002)

        return {"conversation": conversation}

    elif tool_name == "search_memories":
        query = arguments.get("query")
        if not query:
            raise ToolExecutionError("query is required")

        try:
            limit = parse_mcp_int(arguments.get("limit"), "limit", default=10, minimum=1, maximum=20)
        except ValueError as e:
            raise ToolExecutionError(str(e), code=-32602)
        fetch_limit = min(limit * 3, 60)

        if auth_context is None:
            raise ToolExecutionError("Missing MCP API app/key identity for memory read authorization", code=-32009)
        app_key_grant = authorize_memory_external_default_memory_read(auth_context, db_client=db)
        if not app_key_grant.allowed:
            raise ToolExecutionError(str(app_key_grant.observability), code=-32009)

        if memory_system == MemorySystem.CANONICAL:
            memory_service = MemoryService(db_client=db)
            return {"memories": memory_service.search_mcp(user_id, query, limit=limit)}

        memory_rollout = read_default_read_rollout(uid=user_id, db_client=db, consumer='mcp')
        vector_search_results = search_default_mcp_memories_vector(
            uid=user_id,
            query=query,
            limit=limit,
            db_client=db,
            rollout_decision=memory_rollout,
        )
        if vector_search_results.read_decision == MemoryReadDecision.USE_MEMORY:
            return {"memories": vector_search_results.memories}
        if vector_search_results.read_decision != MemoryReadDecision.USE_LEGACY_SAFE:
            return {"memories": []}

        matches = vector_db.find_similar_memories(user_id, query, threshold=0.0, limit=fetch_limit)
        if not matches:
            return {"memories": []}

        memory_ids = cast(List[str], [m.get('memory_id') for m in matches if m.get('memory_id')])
        if not memory_ids:
            return {"memories": []}
        memories = memories_db.get_memories_by_ids(user_id, memory_ids)

        # Mirror the REST MCP path so SSE search never surfaces rejected, locked,
        # or superseded facts, while fetching extra candidates before filtering.
        score_map = {m.get('memory_id'): m.get('score', 0) for m in matches if m.get('memory_id')}
        results: List[Dict[str, Any]] = []
        for mem in memories:
            if mem.get('user_review') is False or mem.get('is_locked', False) or mem.get('invalid_at') is not None:
                continue
            mem['relevance_score'] = round(score_map.get(mem.get('id'), 0), 4)
            results.append(mem)

        # Sort by relevance
        results.sort(key=lambda x: x.get('relevance_score', 0), reverse=True)

        return {"memories": results[:limit]}

    elif tool_name == "search_conversations":
        query = arguments.get("query")
        if not query:
            raise ToolExecutionError("query is required")

        try:
            limit = parse_mcp_int(arguments.get("limit"), "limit", default=10, minimum=1, maximum=100)
        except ValueError as e:
            raise ToolExecutionError(str(e), code=-32602)
        start_date = arguments.get("start_date")
        end_date = arguments.get("end_date")

        # Parse dates to epoch for vector search
        starts_at = None
        ends_at = None
        if start_date:
            try:
                starts_at = int(datetime.strptime(start_date, "%Y-%m-%d").timestamp())
            except ValueError:
                raise ToolExecutionError(
                    f"Invalid start_date format: '{start_date}'. Expected YYYY-MM-DD.", code=-32602
                )
        if end_date:
            try:
                ends_at = int(datetime.strptime(end_date, "%Y-%m-%d").timestamp())
            except ValueError:
                raise ToolExecutionError(f"Invalid end_date format: '{end_date}'. Expected YYYY-MM-DD.", code=-32602)

        conversation_ids = vector_db.query_vectors(query, user_id, starts_at=starts_at, ends_at=ends_at, k=limit)
        if not conversation_ids:
            return {"conversations": []}

        conversations = conversations_db.get_conversations_by_id(user_id, conversation_ids)

        # Simplify and handle locked content
        results: List[Dict[str, Any]] = []
        for conv in conversations:
            structured = conv.get("structured")
            if conv.get("is_locked", False) and structured:
                structured = dict(structured)
                structured['action_items'] = []
                structured['events'] = []
            results.append(
                {
                    "id": conv.get("id"),
                    "started_at": conv.get("started_at"),
                    "finished_at": conv.get("finished_at"),
                    "structured": structured,
                    "language": conv.get("language"),
                }
            )

        return {"conversations": results}

    elif tool_name == "search_x_posts":
        query = arguments.get("query")
        if not query:
            raise ToolExecutionError("query is required")
        try:
            limit = parse_mcp_int(arguments.get("limit"), "limit", default=10, minimum=1, maximum=100)
        except ValueError as e:
            raise ToolExecutionError(str(e), code=-32602)

        matches = vector_db.find_similar_x_posts(user_id, query, limit=limit)
        if not matches:
            return {"posts": []}

        score_map = {str(m['post_id']): m.get('score', 0) for m in matches}
        posts = x_posts_db.get_x_posts_by_ids(user_id, [m['post_id'] for m in matches])
        results: List[Dict[str, Any]] = []
        for p in posts:
            results.append(
                {
                    "id": p.get("id"),
                    "text": p.get("text"),
                    "kind": p.get("kind"),
                    "created_at": p.get("created_at"),
                    "relevance_score": round(score_map.get(str(p.get("id")), 0), 4),
                }
            )
        results.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
        return {"posts": results}

    elif tool_name == "get_x_posts":
        try:
            limit = parse_mcp_int(arguments.get("limit"), "limit", default=50, minimum=1, maximum=200)
        except ValueError as e:
            raise ToolExecutionError(str(e), code=-32602)
        kind = arguments.get("kind")
        posts = x_posts_db.get_x_posts(user_id, limit=limit, kind=kind)
        results = [
            {"id": p.get("id"), "text": p.get("text"), "kind": p.get("kind"), "created_at": p.get("created_at")}
            for p in posts
        ]
        return {"posts": results}

    elif tool_name == "get_action_items":
        try:
            limit = parse_mcp_int(arguments.get("limit"), "limit", default=100, minimum=1, maximum=500)
            offset = parse_mcp_int(arguments.get("offset"), "offset", default=0, minimum=0, maximum=100000)
            completed = parse_optional_mcp_bool(arguments.get("completed"), "completed")
        except ValueError as e:
            raise ToolExecutionError(str(e), code=-32602)
        due_start = _parse_mcp_date(arguments.get("due_start_date"), "due_start_date")
        due_end = _parse_mcp_date(arguments.get("due_end_date"), "due_end_date")
        items = action_items_db.get_action_items(
            user_id,
            completed=completed,
            due_start_date=due_start,
            due_end_date=due_end,
            limit=limit,
            offset=offset,
        )
        return {"action_items": [clean_action_item(i) for i in items if not i.get("deleted", False)]}

    elif tool_name == "search_action_items":
        try:
            items = mcp_action_items.search_action_items(
                user_id, arguments.get("query"), limit=arguments.get("limit", 10)
            )
        except ValueError as e:
            raise ToolExecutionError(str(e), code=-32602)
        return {"action_items": items}

    elif tool_name == "create_action_item":
        try:
            completed = parse_mcp_bool(arguments.get("completed"), "completed", default=False)
            item = mcp_action_items.create_action_item(
                user_id,
                arguments.get("description"),
                due_at=arguments.get("due_at"),
                completed=completed,
            )
        except ValueError as e:
            raise ToolExecutionError(str(e), code=-32602)
        return {"success": True, "action_item": item}

    elif tool_name == "complete_action_item":
        action_item_id = arguments.get("action_item_id")
        if not action_item_id:
            raise ToolExecutionError("action_item_id is required", code=-32602)
        try:
            completed = parse_mcp_bool(arguments.get("completed"), "completed", default=True)
            item = mcp_action_items.set_completed(user_id, action_item_id, completed=completed)
        except ValueError as e:
            raise ToolExecutionError(str(e), code=-32602)
        except mcp_action_items.ActionItemNotFound:
            raise ToolExecutionError("Action item not found", code=-32001)
        except mcp_action_items.ActionItemLocked:
            raise ToolExecutionError("A paid plan is required to modify this action item.", code=-32002)
        return {"success": True, "action_item": item}

    elif tool_name == "update_action_item":
        action_item_id = arguments.get("action_item_id")
        if not action_item_id:
            raise ToolExecutionError("action_item_id is required", code=-32602)
        try:
            item = mcp_action_items.update_action_item(
                user_id,
                action_item_id,
                description=arguments.get("description"),
                due_at=arguments.get("due_at"),
            )
        except ValueError as e:
            raise ToolExecutionError(str(e), code=-32602)
        except mcp_action_items.ActionItemNotFound:
            raise ToolExecutionError("Action item not found", code=-32001)
        except mcp_action_items.ActionItemLocked:
            raise ToolExecutionError("A paid plan is required to modify this action item.", code=-32002)
        return {"success": True, "action_item": item}

    elif tool_name == "delete_action_item":
        action_item_id = arguments.get("action_item_id")
        if not action_item_id:
            raise ToolExecutionError("action_item_id is required", code=-32602)
        try:
            mcp_action_items.delete_action_item(user_id, action_item_id)
        except mcp_action_items.ActionItemNotFound:
            raise ToolExecutionError("Action item not found", code=-32001)
        except mcp_action_items.ActionItemLocked:
            raise ToolExecutionError("A paid plan is required to modify this action item.", code=-32002)
        return {"success": True}

    elif tool_name == "get_goals":
        try:
            include_inactive = parse_mcp_bool(arguments.get("include_inactive"), "include_inactive", default=False)
        except ValueError as e:
            raise ToolExecutionError(str(e), code=-32602)
        return {"goals": goals_db.get_all_goals(user_id, include_inactive=include_inactive)}

    elif tool_name == "get_chat_messages":
        try:
            limit = parse_mcp_int(arguments.get("limit"), "limit", default=50, minimum=1, maximum=200)
            offset = parse_mcp_int(arguments.get("offset"), "offset", default=0, minimum=0, maximum=100000)
        except ValueError as e:
            raise ToolExecutionError(str(e), code=-32602)
        messages = chat_db.get_messages(user_id, limit=limit, offset=offset)
        return {"messages": [clean_chat_message(m) for m in messages]}

    elif tool_name == "get_people":
        return {"people": [clean_person(p) for p in users_db.get_people(user_id)]}

    elif tool_name == "get_screen_activity":
        start = _parse_mcp_date(arguments.get("start_date"), "start_date")
        end = _parse_mcp_date(arguments.get("end_date"), "end_date")
        app = arguments.get("app")
        try:
            summary = parse_mcp_bool(arguments.get("summary"), "summary", default=False)
        except ValueError as e:
            raise ToolExecutionError(str(e), code=-32602)
        if summary:
            try:
                return screen_activity_db.get_screen_activity_summary(user_id, start_date=start, end_date=end)
            except FailedPrecondition as e:
                _raise_screen_activity_index_error(e)
        try:
            limit = parse_mcp_int(arguments.get("limit"), "limit", default=200, minimum=1, maximum=1000)
        except ValueError as e:
            raise ToolExecutionError(str(e), code=-32602)
        try:
            rows = screen_activity_db.get_screen_activity(
                user_id, start_date=start, end_date=end, app_filter=app, limit=limit
            )
        except FailedPrecondition as e:
            _raise_screen_activity_index_error(e)
        return {"screen_activity": [clean_screen_activity_row(r) for r in rows]}

    elif tool_name == "get_daily_summaries":
        try:
            limit = parse_mcp_int(arguments.get("limit"), "limit", default=30, minimum=1, maximum=100)
            offset = parse_mcp_int(arguments.get("offset"), "offset", default=0, minimum=0, maximum=100000)
        except ValueError as e:
            raise ToolExecutionError(str(e), code=-32602)
        summaries = daily_summaries_db.get_daily_summaries(
            user_id,
            limit=limit,
            offset=offset,
            start_date=arguments.get("start_date"),
            end_date=arguments.get("end_date"),
        )
        return {"daily_summaries": summaries}

    else:
        raise ToolExecutionError(f"Unknown tool: {tool_name}", code=-32601)


def create_mcp_response(id: Any, result: Dict[str, Any]) -> Dict[str, Any]:
    """Create a JSON-RPC 2.0 response."""
    return {"jsonrpc": "2.0", "id": id, "result": result}


def create_mcp_error(id: Any, code: int, message: str) -> Dict[str, Any]:
    """Create a JSON-RPC 2.0 error response."""
    return {"jsonrpc": "2.0", "id": id, "error": {"code": code, "message": message}}


def handle_mcp_message(
    auth_context: MCPAuthContext, message: Dict[str, Any]
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Process an incoming MCP JSON-RPC message and return a response.
    Returns (response, new_session_id) tuple.
    """
    msg_id = message.get("id")
    method = message.get("method")
    raw_params: object = message.get("params", {})
    params: Dict[str, Any] = cast(Dict[str, Any], raw_params) if isinstance(raw_params, dict) else {}

    if method == "initialize":
        return (
            create_mcp_response(
                msg_id,
                {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "omi-mcp-server", "version": "1.0.0"},
                    "instructions": (
                        "This server exposes the user's Omi memory (their personal AI memory bank). "
                        "`get_user_profile` returns a cached high-level profile when available. Use it as a "
                        "starting point, then call `search_memories`, `get_memories`, or conversation tools for "
                        "task-specific evidence."
                    ),
                },
            ),
            None,
        )

    elif method == "notifications/initialized":
        # This is a notification, no response needed
        return None, None

    elif method == "tools/list":
        return create_mcp_response(msg_id, {"tools": _tools_for_scopes(auth_context.scopes)}), None

    elif method == "tools/call":
        tool_name = params.get("name")
        raw_arguments: object = params.get("arguments", {})
        arguments: Dict[str, Any] = cast(Dict[str, Any], raw_arguments) if isinstance(raw_arguments, dict) else {}

        if not tool_name:
            return create_mcp_error(msg_id, -32602, "Tool name is required"), None

        try:
            mcp_auth_context = auth_context
            _require_tool_scope(mcp_auth_context, tool_name)
            auth_context = mcp_auth_context.memory_context
            result = execute_tool(mcp_auth_context.uid, tool_name, arguments, auth_context=auth_context)
        except ToolExecutionError as e:
            error = create_mcp_error(msg_id, e.code, e.message)
            if e.code == -32003:
                required_scope = TOOL_REQUIRED_SCOPE.get(tool_name)
                error["error"]["data"] = {
                    "_meta": {
                        "mcp/www_authenticate": (
                            f'Bearer resource_metadata="{MCP_PROTECTED_RESOURCE_METADATA_URL}", '
                            f'error="insufficient_scope", scope="{required_scope}"'
                        )
                    }
                }
            return error, None

        return (
            create_mcp_response(
                msg_id, {"content": [{"type": "text", "text": json.dumps(result, indent=2, default=str)}]}
            ),
            None,
        )

    elif method == "ping":
        return create_mcp_response(msg_id, {}), None

    else:
        return create_mcp_error(msg_id, -32601, f"Method not found: {method}"), None


def _oauth_error(error: str, description: str, status_code: int = 400) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error": error, "error_description": description})


class McpSseAuthMethodResponse(BaseModel):
    header: Optional[str] = None
    format: Optional[str] = None
    authorization_endpoint: Optional[str] = None
    token_endpoint: Optional[str] = None
    resource: Optional[str] = None
    scopes: list[str] = []


class McpSseAuthenticationResponse(BaseModel):
    methods: list[str]
    api_key: McpSseAuthMethodResponse
    oauth2: McpSseAuthMethodResponse


class McpSseInstructionsResponse(BaseModel):
    step1: str
    step2: str
    step3: str


class McpSseInfoResponse(BaseModel):
    endpoint: str
    transport: str
    protocol_version: str
    authentication: McpSseAuthenticationResponse
    instructions: McpSseInstructionsResponse


class McpAuthorizeConsentResponse(BaseModel):
    redirect_uri: str


class McpTokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str
    expires_in: int
    scope: str


def _validate_authorize_request(
    response_type: str,
    client_id: str,
    redirect_uri: str,
    resource: str,
    scope: Optional[str],
    code_challenge: Optional[str],
    code_challenge_method: Optional[str],
) -> Tuple[Dict[str, Any], List[str]]:
    client = mcp_oauth_db.get_client(client_id)
    if response_type != "code":
        raise ValueError("response_type must be code")
    if not client or client.get("disabled_at"):
        raise ValueError("Unknown OAuth client")
    if not mcp_oauth_db.validate_redirect_uri(client, redirect_uri):
        raise ValueError("redirect_uri is not registered for this client")
    if not mcp_oauth_db.validate_resource(client, resource):
        raise ValueError("Invalid resource")
    if not mcp_oauth_db.validate_pkce_challenge(code_challenge, code_challenge_method):
        raise ValueError("PKCE S256 is required")
    scopes = mcp_oauth_db.normalize_scopes(scope, client)
    return client, scopes


def _redirect_with_code(redirect_uri: str, code: str, state: Optional[str]) -> str:
    parts = urlsplit(redirect_uri)
    params = dict(parse_qsl(parts.query, keep_blank_values=True))
    params["code"] = code
    if state:
        params["state"] = state
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(params), parts.fragment))


async def _get_token_request_data(request: Request) -> Dict[str, Any]:
    content_type = (request.headers.get("content-type") or "").split(";", 1)[0].strip().lower()
    if content_type == "application/json":
        body: object = await request.json()
        if not isinstance(body, dict):
            raise ValueError("Invalid request body")
        return cast(Dict[str, Any], body)

    form_data = await request.form()
    return dict(form_data)


@router.get("/authorize", response_class=HTMLResponse, tags=["mcp"])
def mcp_authorize(
    request: Request,
    response_type: str,
    client_id: str,
    redirect_uri: str,
    resource: str,
    state: Optional[str] = None,
    scope: Optional[str] = None,
    code_challenge: Optional[str] = None,
    code_challenge_method: Optional[str] = None,
):
    """OAuth authorize endpoint."""
    try:
        client, scopes = _validate_authorize_request(
            response_type, client_id, redirect_uri, resource, scope, code_challenge, code_challenge_method
        )
    except ValueError as e:
        return _oauth_error("invalid_request", str(e))

    client_name = str(client.get("name") or client_id)
    permissions = [SCOPE_PERMISSION_TEXT[item] for item in scopes]
    return templates.TemplateResponse(
        "mcp_oauth_authorize.html",
        {
            "request": request,
            "client_name": client_name,
            "oauth_params": {
                "response_type": response_type,
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "resource": resource,
                "scope": " ".join(scopes),
                "state": state or "",
                "code_challenge": code_challenge,
                "code_challenge_method": code_challenge_method,
            },
            "permissions": permissions,
            "firebase_config": {
                "apiKey": os.getenv("FIREBASE_API_KEY"),
                "authDomain": os.getenv("FIREBASE_AUTH_DOMAIN"),
                "projectId": os.getenv("FIREBASE_PROJECT_ID"),
            },
        },
    )


@router.post("/authorize", tags=["mcp"], response_model=McpAuthorizeConsentResponse)
def mcp_authorize_consent(
    response_type: str = Form(...),
    client_id: str = Form(...),
    redirect_uri: str = Form(...),
    resource: str = Form(...),
    firebase_id_token: str = Form(...),
    state: Optional[str] = Form(None),
    scope: Optional[str] = Form(None),
    code_challenge: Optional[str] = Form(None),
    code_challenge_method: Optional[str] = Form(None),
):
    try:
        _, scopes = _validate_authorize_request(
            response_type, client_id, redirect_uri, resource, scope, code_challenge, code_challenge_method
        )
        decoded_token: Dict[str, Any] = firebase_admin.auth.verify_id_token(firebase_id_token)  # type: ignore[reportUnknownMemberType]  # firebase_admin auth untyped
        uid = cast(str, decoded_token["uid"])
    except firebase_admin.auth.InvalidIdTokenError:
        return _oauth_error("access_denied", "Invalid Omi sign-in token", status_code=401)
    except Exception as e:
        if isinstance(e, ValueError):
            return _oauth_error("invalid_request", str(e))
        return _oauth_error("access_denied", "Could not verify Omi sign-in token", status_code=401)

    grant = mcp_oauth_db.create_or_update_grant(uid, client_id, resource, scopes)
    code = mcp_oauth_db.issue_authorization_code(
        uid, grant["id"], client_id, redirect_uri, resource, scopes, cast(str, code_challenge)
    )
    return {"redirect_uri": _redirect_with_code(redirect_uri, code, state)}


@router.post("/token", tags=["mcp"], response_model=McpTokenResponse)
async def mcp_token(request: Request):
    """OAuth token endpoint."""
    try:
        request_data = await _get_token_request_data(request)
    except Exception:
        return _oauth_error("invalid_request", "Invalid request body")

    client_secret = request_data.get("client_secret")
    client_id = request_data.get("client_id")
    grant_type = request_data.get("grant_type")
    code = request_data.get("code")
    redirect_uri = request_data.get("redirect_uri")
    resource = request_data.get("resource")
    code_verifier = request_data.get("code_verifier")
    refresh_token = request_data.get("refresh_token")
    scope = request_data.get("scope")

    client = await run_blocking(db_executor, mcp_oauth_db.get_client, client_id or "")
    if (
        not client
        or client.get("disabled_at")
        or not await run_blocking(db_executor, mcp_oauth_db.verify_client_auth, client, client_secret)
    ):
        return _oauth_error("invalid_client", "Invalid client", status_code=401)

    if grant_type == "authorization_code":
        if not code or not redirect_uri or not code_verifier or not resource:
            return _oauth_error("invalid_request", "code, redirect_uri, resource, and code_verifier are required")
        if not await run_blocking(db_executor, mcp_oauth_db.validate_resource, client, resource):
            return _oauth_error("invalid_target", "Invalid resource")
        token_pair = await run_blocking(
            db_executor,
            mcp_oauth_db.exchange_authorization_code_for_tokens,
            code,
            cast(str, client_id),
            redirect_uri,
            resource,
            code_verifier,
        )
        if not token_pair:
            return _oauth_error("invalid_grant", "Invalid authorization code")
        return token_pair

    if grant_type == "refresh_token":
        if not refresh_token or not resource:
            return _oauth_error("invalid_request", "refresh_token and resource are required")
        if not await run_blocking(db_executor, mcp_oauth_db.validate_resource, client, resource):
            return _oauth_error("invalid_target", "Invalid resource")
        token_pair = await run_blocking(
            db_executor, mcp_oauth_db.rotate_refresh_token, refresh_token, cast(str, client_id), resource, scope
        )
        if not token_pair:
            return _oauth_error("invalid_grant", "Invalid refresh token")
        return token_pair

    return _oauth_error("unsupported_grant_type", "grant_type must be authorization_code or refresh_token")


@router.post("/v1/mcp/sse", tags=["mcp"], response_class=Response)
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
    - This hosted transport is stateless; bearer-token auth scopes every request
    """
    # Authenticate
    auth_context = await run_blocking(db_executor, authenticate_mcp_request, authorization)
    if not auth_context:
        raise invalid_mcp_auth_exception()
    user_id = auth_context.uid

    # Rate limit per-user
    await run_blocking(critical_executor, check_rate_limit_inline, user_id, "mcp:sse")

    # Parse request body
    try:
        body: object = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    # Handle batch requests (array of messages)
    raw_messages: List[Dict[str, Any]] = (
        cast(List[Dict[str, Any]], body) if isinstance(body, list) else [cast(Dict[str, Any], body)]
    )
    messages: List[Dict[str, Any]] = raw_messages

    # Check if all messages are notifications/responses (no id)
    all_notifications = all(msg.get("id") is None for msg in messages)

    if all_notifications:
        # Process notifications without response
        for msg in messages:
            await run_blocking(db_executor, handle_mcp_message, auth_context, msg)
        return Response(status_code=202)

    # Process messages and collect responses
    responses: List[Dict[str, Any]] = []
    new_session_id: Optional[str] = None

    for msg in messages:
        response, session_id = await run_blocking(db_executor, handle_mcp_message, auth_context, msg)
        if session_id:
            new_session_id = session_id
        if response:
            responses.append(response)

    # Prepare headers
    headers: Dict[str, str] = {}
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
            headers={**headers, "Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
        )
    else:
        # Return as JSON
        if len(responses) == 1:
            return JSONResponse(content=responses[0], headers=headers)
        else:
            return JSONResponse(content=responses, headers=headers)


@router.get("/v1/mcp/sse", tags=["mcp"], response_class=Response)
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
    auth_context = await run_blocking(db_executor, authenticate_mcp_request, authorization)
    if not auth_context:
        raise invalid_mcp_auth_exception()

    await run_blocking(critical_executor, check_rate_limit_inline, auth_context.uid, "mcp:sse")

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
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@router.head("/v1/mcp/sse", tags=["mcp"], response_class=Response)
def mcp_sse_head(authorization: Optional[str] = Header(None, alias="Authorization")):
    if not authenticate_mcp_request(authorization):
        raise invalid_mcp_auth_exception()
    return Response(status_code=200)


@router.delete("/v1/mcp/sse", tags=["mcp"], response_class=Response)
def mcp_delete_session(
    mcp_session_id: Optional[str] = Header(None, alias="Mcp-Session-Id"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
):
    """
    Delete/terminate an MCP session.
    """
    auth_context = authenticate_mcp_request(authorization)
    if not auth_context:
        raise invalid_mcp_auth_exception("Invalid or missing API key")

    # Hosted MCP is stateless; terminate requests are best-effort so stale
    # or load-balanced session ids do not create client-visible errors.
    return Response(status_code=204)


@router.get("/v1/mcp/sse/info", tags=["mcp"], response_model=McpSseInfoResponse)
def mcp_sse_info(request: Request):
    """
    Get information about the pre-hosted MCP server.
    """
    base_url = str(request.base_url).rstrip("/")
    return {
        "endpoint": "/v1/mcp/sse",
        "transport": "streamable-http",
        "protocol_version": "2025-03-26",
        "authentication": {
            "methods": ["oauth2", "api_key"],
            "api_key": {"header": "Authorization", "format": "Bearer <api_key>"},
            "oauth2": {
                "authorization_endpoint": MCP_AUTHORIZATION_ENDPOINT,
                "token_endpoint": MCP_TOKEN_ENDPOINT,
                "resource": MCP_RESOURCE_URL,
                "scopes": MCP_SCOPES_SUPPORTED,
            },
        },
        "instructions": {
            "step1": "Create an MCP API key in the Omi app (Settings > Developer > MCP)",
            "step2": f"Set Server URL to: {base_url}/v1/mcp/sse",
            "step3": "Set Authorization header to your key",
        },
    }
