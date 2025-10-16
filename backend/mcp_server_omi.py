#!/usr/bin/env python3
"""
Omi MCP Server - Model Context Protocol server for Omi AI Assistant

Provides tools for the agentic chat system to:
- Search and manage conversations
- Create and manage memories
- Create and track action items
- Extract insights and context
"""

import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# Add backend to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# Import Omi backend modules
import database.conversations as conversations_db
import database.memories as memories_db
import database.action_items as action_items_db
import database.users as users_db
from database.vector_db import query_vectors_by_metadata
from models.action_item import ActionItem, ActionItemStatus
from models.memories import MemoryDB, MemoryCategory
from models.conversation import CategoryEnum
from utils.llm.embeddings import generate_embedding
from utils.llm.memories import identify_category_for_memory
from utils.apps import update_personas_async
import threading
import uuid as uuid_lib

# Initialize MCP server
server = Server("omi-server")

# Global UID - will be set from environment variable
CURRENT_UID: Optional[str] = None


def get_uid() -> str:
    """Get the current user ID from environment or context"""
    global CURRENT_UID
    if CURRENT_UID:
        return CURRENT_UID
    uid = os.environ.get("UID")
    if not uid:
        raise ValueError("UID not set in environment")
    CURRENT_UID = uid
    return uid


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List all available tools for the Omi agent"""
    return [
        Tool(
            name="search_conversations",
            description="Search through the user's past conversations using semantic search. Use this when the user asks about previous discussions, topics, or wants to recall information from past conversations.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query (natural language question or keywords)"
                    },
                    "start_date": {
                        "type": "string",
                        "format": "date-time",
                        "description": "Start date filter (ISO 8601 format, optional)"
                    },
                    "end_date": {
                        "type": "string",
                        "format": "date-time",
                        "description": "End date filter (ISO 8601 format, optional)"
                    },
                    "categories": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": [
                                "personal", "education", "health", "finance", "legal",
                                "philosophy", "spiritual", "science", "technology", "business",
                                "social", "travel", "food", "entertainment", "sports", "other"
                            ]
                        },
                        "description": "Filter by conversation categories"
                    },
                    "limit": {
                        "type": "integer",
                        "default": 10,
                        "description": "Maximum number of results to return (1-50)"
                    }
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="get_conversation",
            description="Get the full details of a specific conversation by ID, including transcript and structured data.",
            inputSchema={
                "type": "object",
                "properties": {
                    "conversation_id": {
                        "type": "string",
                        "description": "The unique ID of the conversation"
                    }
                },
                "required": ["conversation_id"]
            }
        ),
        Tool(
            name="search_memories",
            description="Search through the user's memory bank (facts, preferences, important information). Use this to recall what you know about the user.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (optional - leave empty to list all)"
                    },
                    "categories": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": [
                                "core", "lifestyle", "interests_hobbies", "health_wellness",
                                "work_productivity", "relationships", "values_beliefs", "other"
                            ]
                        },
                        "description": "Filter by memory categories"
                    },
                    "limit": {
                        "type": "integer",
                        "default": 25,
                        "description": "Maximum number of results (1-100)"
                    }
                },
                "required": []
            }
        ),
        Tool(
            name="create_memory",
            description="Create a new memory/fact about the user. Use this proactively when the user shares important personal information, preferences, goals, or anything worth remembering.",
            inputSchema={
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "The memory content (clear, concise fact)"
                    },
                    "category": {
                        "type": "string",
                        "enum": [
                            "core", "lifestyle", "interests_hobbies", "health_wellness",
                            "work_productivity", "relationships", "values_beliefs", "other"
                        ],
                        "description": "Memory category (optional - will be auto-detected if not provided)"
                    }
                },
                "required": ["content"]
            }
        ),
        Tool(
            name="update_memory",
            description="Update an existing memory with new content.",
            inputSchema={
                "type": "object",
                "properties": {
                    "memory_id": {
                        "type": "string",
                        "description": "The ID of the memory to update"
                    },
                    "content": {
                        "type": "string",
                        "description": "The new memory content"
                    }
                },
                "required": ["memory_id", "content"]
            }
        ),
        Tool(
            name="delete_memory",
            description="Delete a memory. Only use this if the user explicitly asks to forget something.",
            inputSchema={
                "type": "object",
                "properties": {
                    "memory_id": {
                        "type": "string",
                        "description": "The ID of the memory to delete"
                    }
                },
                "required": ["memory_id"]
            }
        ),
        Tool(
            name="create_action_item",
            description="Create an action item/task for the user. Use this proactively when the user mentions something they need to do, a reminder they want, or any task.",
            inputSchema={
                "type": "object",
                "properties": {
                    "description": {
                        "type": "string",
                        "description": "Clear description of the action item"
                    },
                    "due_date": {
                        "type": "string",
                        "format": "date-time",
                        "description": "Optional due date (ISO 8601 format)"
                    },
                    "conversation_id": {
                        "type": "string",
                        "description": "Optional conversation ID this action item relates to"
                    }
                },
                "required": ["description"]
            }
        ),
        Tool(
            name="list_action_items",
            description="List the user's action items/tasks. Use this to check what's on their todo list.",
            inputSchema={
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["pending", "completed", "all"],
                        "default": "pending",
                        "description": "Filter by status"
                    },
                    "limit": {
                        "type": "integer",
                        "default": 25,
                        "description": "Maximum number of results"
                    }
                },
                "required": []
            }
        ),
        Tool(
            name="update_action_item",
            description="Update an action item (mark complete, change description, etc.)",
            inputSchema={
                "type": "object",
                "properties": {
                    "action_item_id": {
                        "type": "string",
                        "description": "The ID of the action item to update"
                    },
                    "completed": {
                        "type": "boolean",
                        "description": "Mark as completed (true) or pending (false)"
                    },
                    "description": {
                        "type": "string",
                        "description": "Update the description"
                    }
                },
                "required": ["action_item_id"]
            }
        ),
        Tool(
            name="get_user_context",
            description="Get comprehensive context about the user including their profile, timezone, and recent activity summary. Use this to better understand the user's situation.",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        Tool(
            name="get_conversation_summary",
            description="Get a summary of recent conversations (last N days). Useful for providing context or weekly summaries.",
            inputSchema={
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "default": 7,
                        "description": "Number of days to look back (1-30)"
                    }
                },
                "required": []
            }
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Handle tool calls from the agent"""
    try:
        uid = get_uid()

        if name == "search_conversations":
            result = await search_conversations_impl(uid, arguments)
            return [TextContent(type="text", text=json.dumps(result, default=str))]

        elif name == "get_conversation":
            result = await get_conversation_impl(uid, arguments)
            return [TextContent(type="text", text=json.dumps(result, default=str))]

        elif name == "search_memories":
            result = await search_memories_impl(uid, arguments)
            return [TextContent(type="text", text=json.dumps(result, default=str))]

        elif name == "create_memory":
            result = await create_memory_impl(uid, arguments)
            return [TextContent(type="text", text=json.dumps(result))]

        elif name == "update_memory":
            result = await update_memory_impl(uid, arguments)
            return [TextContent(type="text", text=json.dumps(result))]

        elif name == "delete_memory":
            result = await delete_memory_impl(uid, arguments)
            return [TextContent(type="text", text=json.dumps(result))]

        elif name == "create_action_item":
            result = await create_action_item_impl(uid, arguments)
            return [TextContent(type="text", text=json.dumps(result))]

        elif name == "list_action_items":
            result = await list_action_items_impl(uid, arguments)
            return [TextContent(type="text", text=json.dumps(result, default=str))]

        elif name == "update_action_item":
            result = await update_action_item_impl(uid, arguments)
            return [TextContent(type="text", text=json.dumps(result))]

        elif name == "get_user_context":
            result = await get_user_context_impl(uid)
            return [TextContent(type="text", text=json.dumps(result, default=str))]

        elif name == "get_conversation_summary":
            result = await get_conversation_summary_impl(uid, arguments)
            return [TextContent(type="text", text=json.dumps(result, default=str))]

        else:
            return [TextContent(
                type="text",
                text=json.dumps({"error": f"Unknown tool: {name}"})
            )]

    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"Error in tool {name}: {error_details}", file=sys.stderr)
        return [TextContent(
            type="text",
            text=json.dumps({"error": str(e), "tool": name})
        )]


# ========================================
# TOOL IMPLEMENTATIONS
# ========================================

async def search_conversations_impl(uid: str, args: dict) -> dict:
    """Search conversations using semantic search"""
    query = args.get("query", "")
    start_date = args.get("start_date")
    end_date = args.get("end_date")
    categories = args.get("categories", [])
    limit = min(args.get("limit", 10), 50)

    try:
        # Generate embedding for semantic search
        vector = generate_embedding(query)

        # Parse dates if provided
        start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00')) if start_date else None
        end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00')) if end_date else None

        # Query vector database
        conversation_ids = query_vectors_by_metadata(
            uid,
            vector,
            dates_filter=[start_dt, end_dt],
            topics=[],  # Topics handled separately in categories
            limit=limit,
        )

        # Fetch full conversations
        conversations = conversations_db.get_conversations_by_id(uid, conversation_ids)

        # Filter by categories if provided
        if categories:
            conversations = [
                c for c in conversations
                if c.get('structured', {}).get('category') in categories
            ]

        # Filter out locked conversations
        conversations = [c for c in conversations if not c.get('is_locked', False)]

        # Return simplified format
        results = []
        for conv in conversations[:limit]:
            results.append({
                "id": conv.get("id"),
                "title": conv.get("structured", {}).get("title", "Untitled"),
                "overview": conv.get("structured", {}).get("overview", ""),
                "category": conv.get("structured", {}).get("category"),
                "started_at": conv.get("started_at"),
                "finished_at": conv.get("finished_at"),
                "language": conv.get("language"),
            })

        return {
            "success": True,
            "count": len(results),
            "conversations": results
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


async def get_conversation_impl(uid: str, args: dict) -> dict:
    """Get full conversation details"""
    conversation_id = args.get("conversation_id")

    try:
        conversation = conversations_db.get_conversation(uid, conversation_id)

        if not conversation:
            return {"success": False, "error": "Conversation not found"}

        if conversation.get('is_locked', False):
            return {"success": False, "error": "Conversation locked (premium plan required)"}

        return {"success": True, "conversation": conversation}

    except Exception as e:
        return {"success": False, "error": str(e)}


async def search_memories_impl(uid: str, args: dict) -> dict:
    """Search through user's memories"""
    query = args.get("query", "")
    categories = args.get("categories", [])
    limit = min(args.get("limit", 25), 100)

    try:
        memories = memories_db.get_memories(
            uid,
            limit=limit,
            offset=0,
            categories=categories if categories else None
        )

        # Filter out locked memories
        memories = [m for m in memories if not m.get('is_locked', False)]

        # If query provided, do simple text matching (can be enhanced with semantic search)
        if query:
            query_lower = query.lower()
            memories = [
                m for m in memories
                if query_lower in m.get('content', '').lower()
            ]

        return {
            "success": True,
            "count": len(memories),
            "memories": memories
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


async def create_memory_impl(uid: str, args: dict) -> dict:
    """Create a new memory"""
    content = args.get("content", "").strip()
    category = args.get("category")

    if not content:
        return {"success": False, "error": "Content cannot be empty"}

    try:
        # Auto-categorize if not provided
        if not category:
            categories = [c.value for c in MemoryCategory]
            category = identify_category_for_memory(content, categories)

        # Create memory object
        memory = MemoryDB(
            id=str(uuid_lib.uuid4()),
            content=content,
            category=category,
            created_at=datetime.now(timezone.utc),
            structured={},
            external_integration_id=None,
            deleted=False,
            discarded=False
        )

        # Save to database
        memories_db.create_memory(uid, memory.model_dump())

        # Update personas asynchronously
        threading.Thread(target=update_personas_async, args=(uid,)).start()

        return {
            "success": True,
            "memory_id": memory.id,
            "category": category,
            "message": f"Memory created successfully"
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


async def update_memory_impl(uid: str, args: dict) -> dict:
    """Update an existing memory"""
    memory_id = args.get("memory_id")
    content = args.get("content", "").strip()

    if not memory_id or not content:
        return {"success": False, "error": "Memory ID and content are required"}

    try:
        memories_db.edit_memory(uid, memory_id, content)
        return {"success": True, "message": "Memory updated successfully"}

    except Exception as e:
        return {"success": False, "error": str(e)}


async def delete_memory_impl(uid: str, args: dict) -> dict:
    """Delete a memory"""
    memory_id = args.get("memory_id")

    if not memory_id:
        return {"success": False, "error": "Memory ID is required"}

    try:
        memories_db.delete_memory(uid, memory_id)
        return {"success": True, "message": "Memory deleted successfully"}

    except Exception as e:
        return {"success": False, "error": str(e)}


async def create_action_item_impl(uid: str, args: dict) -> dict:
    """Create a new action item"""
    description = args.get("description", "").strip()
    due_date = args.get("due_date")
    conversation_id = args.get("conversation_id")

    if not description:
        return {"success": False, "error": "Description cannot be empty"}

    try:
        # Parse due date if provided
        due_dt = None
        if due_date:
            due_dt = datetime.fromisoformat(due_date.replace('Z', '+00:00'))

        # Create action item
        action_item = {
            "id": str(uuid_lib.uuid4()),
            "description": description,
            "created_at": datetime.now(timezone.utc),
            "completed": False,
            "deleted": False,
            "status": "pending",
            "conversation_id": conversation_id,
            "due_date": due_dt
        }

        # Save to database
        action_items_db.create_action_item(uid, action_item)

        return {
            "success": True,
            "action_item_id": action_item["id"],
            "message": "Action item created successfully"
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


async def list_action_items_impl(uid: str, args: dict) -> dict:
    """List action items"""
    status = args.get("status", "pending")
    limit = min(args.get("limit", 25), 100)

    try:
        completed_filter = None
        if status == "completed":
            completed_filter = True
        elif status == "pending":
            completed_filter = False
        # status == "all" -> no filter

        action_items = action_items_db.get_action_items(
            uid,
            limit=limit,
            offset=0,
            completed=completed_filter
        )

        return {
            "success": True,
            "count": len(action_items),
            "action_items": action_items
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


async def update_action_item_impl(uid: str, args: dict) -> dict:
    """Update an action item"""
    action_item_id = args.get("action_item_id")
    completed = args.get("completed")
    description = args.get("description")

    if not action_item_id:
        return {"success": False, "error": "Action item ID is required"}

    try:
        if completed is not None:
            action_items_db.update_action_item_status(uid, action_item_id, completed)

        if description:
            action_items_db.update_action_item_description(uid, action_item_id, description)

        return {"success": True, "message": "Action item updated successfully"}

    except Exception as e:
        return {"success": False, "error": str(e)}


async def get_user_context_impl(uid: str) -> dict:
    """Get comprehensive user context"""
    try:
        # Get user profile
        user_data = users_db.get_user(uid)

        # Get recent memories (last 10)
        recent_memories = memories_db.get_memories(uid, limit=10, offset=0)

        # Get pending action items
        pending_actions = action_items_db.get_action_items(uid, limit=5, completed=False)

        return {
            "success": True,
            "user": {
                "name": user_data.get("name", "User"),
                "email": user_data.get("email"),
                "timezone": user_data.get("timezone", "UTC"),
            },
            "recent_memories_count": len(recent_memories),
            "pending_actions_count": len(pending_actions),
            "recent_memories": [m.get("content") for m in recent_memories[:3]],
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


async def get_conversation_summary_impl(uid: str, args: dict) -> dict:
    """Get summary of recent conversations"""
    days = min(args.get("days", 7), 30)

    try:
        from datetime import timedelta

        start_date = datetime.now(timezone.utc) - timedelta(days=days)

        conversations = conversations_db.get_conversations(
            uid,
            limit=50,
            offset=0,
            start_date=start_date,
            include_discarded=False
        )

        # Filter out locked
        conversations = [c for c in conversations if not c.get('is_locked', False)]

        # Summarize by category
        by_category = {}
        for conv in conversations:
            cat = conv.get("structured", {}).get("category", "other")
            by_category[cat] = by_category.get(cat, 0) + 1

        return {
            "success": True,
            "days": days,
            "total_conversations": len(conversations),
            "by_category": by_category,
            "recent_conversations": [
                {
                    "id": c.get("id"),
                    "title": c.get("structured", {}).get("title"),
                    "date": c.get("created_at")
                }
                for c in conversations[:5]
            ]
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


async def main():
    """Run the MCP server"""
    print("Starting Omi MCP Server...", file=sys.stderr)
    async with stdio_server() as streams:
        await server.run(
            streams[0],
            streams[1],
            server.create_initialization_options()
        )


if __name__ == "__main__":
    asyncio.run(main())
