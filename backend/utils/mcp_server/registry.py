"""Declarative registry for every hosted MCP tool.

One ``ToolSpec`` per tool is the single source of truth for ``tools/list``,
scope enforcement, write rate-limit buckets, analytics dimensions, and
dispatch. REST ``routers/mcp.py`` may read this registry for overlapping
metadata, but its response contracts stay its own.
"""

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

from models.conversation_enums import CategoryEnum
from models.memories import MemoryCategory
from utils.memory.product_authorization import ProductAuthorizationContext
from utils.mcp_server.constants import (
    MCP_CONVERSATION_BATCH_MAX_IDS,
    MCP_CONVERSATION_FETCH_DEFAULT_MAX_CHARS,
    MCP_CONVERSATION_FETCH_DEFAULT_MAX_SEGMENTS,
    MCP_CONVERSATION_FETCH_MAX_CHARS,
    MCP_CONVERSATION_FETCH_MAX_SEGMENTS,
    MCP_CONVERSATION_LIST_MAX_LIMIT,
    MCP_MEMORY_BATCH_MAX_ITEMS,
    MCP_MEMORY_LIST_DEFAULT_LIMIT,
    MCP_MEMORY_LIST_MAX_LIMIT,
)
from utils.mcp_server.errors import ToolExecutionError
from utils.mcp_server.handlers import action_items, conversations, memories, other, profile

ToolHandler = Callable[[str, Dict[str, Any], Optional[ProductAuthorizationContext]], Dict[str, Any]]

# Stable error branch shared by every tool output schema: both successful
# results and ``isError`` payloads must validate against ``outputSchema``.
TOOL_ERROR_OUTPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "required": ["error"],
    "properties": {
        "error": {
            "type": "object",
            "required": ["code", "message"],
            "properties": {
                "code": {"type": "string"},
                "message": {"type": "string"},
            },
        }
    },
}


def _output_schema(success_schema: Dict[str, Any]) -> Dict[str, Any]:
    return {"type": "object", "anyOf": [success_schema, TOOL_ERROR_OUTPUT_SCHEMA]}


def _object_schema(required: List[str], **properties: Any) -> Dict[str, Any]:
    return {"type": "object", "required": required, "properties": properties}


_ARRAY_OF_OBJECTS = {"type": "array", "items": {"type": "object"}}

_DATETIME_OR_NULL = {"type": ["string", "null"], "format": "date-time"}

_CONVERSATION_TIMESTAMPS: Dict[str, Any] = {
    "created_at": _DATETIME_OR_NULL,
    "started_at": _DATETIME_OR_NULL,
    "finished_at": _DATETIME_OR_NULL,
}

_ACTION_ITEM_TIMESTAMPS: Dict[str, Any] = {
    "created_at": _DATETIME_OR_NULL,
    "due_at": _DATETIME_OR_NULL,
    "completed_at": _DATETIME_OR_NULL,
    "updated_at": _DATETIME_OR_NULL,
}


def _object_array_with(**properties: Any) -> Dict[str, Any]:
    return {"type": "array", "items": {"type": "object", "properties": properties}}


def _read_annotations(title: str) -> Dict[str, Any]:
    return {
        "title": title,
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }


def _edit_annotations(title: str) -> Dict[str, Any]:
    # Non-destructive writes (edits, completions) that converge to one state.
    return {
        "title": title,
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }


def _create_annotations(title: str, *, idempotent: bool) -> Dict[str, Any]:
    return {
        "title": title,
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": idempotent,
        "openWorldHint": False,
    }


def _delete_annotations(title: str) -> Dict[str, Any]:
    return {
        "title": title,
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": True,
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

_SECURITY_BY_SCOPE = {
    entry["scopes"][0]: [{"type": "oauth2", "scopes": list(entry["scopes"])}]
    for security in (
        MEMORIES_READ_SECURITY,
        MEMORIES_WRITE_SECURITY,
        CONVERSATIONS_READ_SECURITY,
        ACTION_ITEMS_READ_SECURITY,
        ACTION_ITEMS_WRITE_SECURITY,
        GOALS_READ_SECURITY,
        CHAT_READ_SECURITY,
        SCREEN_ACTIVITY_READ_SECURITY,
        PEOPLE_READ_SECURITY,
    )
    for entry in security
}


@dataclass(frozen=True)
class ToolSpec:
    name: str
    title: str
    description: str
    input_schema: Dict[str, Any]
    output_schema: Dict[str, Any]
    annotations: Dict[str, Any]
    scope: str
    operation: str
    write_operation: str
    rate_bucket: Optional[str]
    handler: ToolHandler

    def list_entry(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "title": self.title,
            "description": self.description,
            "annotations": dict(self.annotations),
            # Released clients read the advertised scope from this field.
            "securitySchemes": _SECURITY_BY_SCOPE[self.scope],
            "inputSchema": self.input_schema,
            "outputSchema": self.output_schema,
        }


_MEMORY_CATEGORY_ENUM = [c.value for c in MemoryCategory]
_CONVERSATION_CATEGORY_ENUM = [c.value for c in CategoryEnum]

# Shared schema fragments: every list tool that pages emits ``next_cursor``
# and accepts it back as ``cursor`` (mutually exclusive with ``offset``).
_CURSOR_INPUT: Dict[str, Any] = {
    "type": "string",
    "description": "Opaque cursor from a previous response's next_cursor (mutually exclusive with offset)",
}
_NEXT_CURSOR_OUTPUT: Dict[str, Any] = {
    "type": "string",
    "description": "Pass back as cursor to fetch the next page; absent when no more results",
}

_READ = "none"
_MEMORY_CREATE = "memory_create"
_MEMORY_UPDATE = "memory_update"
_MEMORY_DELETE = "memory_delete"
_ACTION_ITEM_CREATE = "action_item_create"
_ACTION_ITEM_COMPLETE = "action_item_complete"
_ACTION_ITEM_UPDATE = "action_item_update"
_ACTION_ITEM_DELETE = "action_item_delete"

TOOL_SPECS: Tuple[ToolSpec, ...] = (
    ToolSpec(
        name="get_user_profile",
        title="Get user profile",
        description=(
            "Get Omi's cached high-level summary of the user, if one has been generated. Use this as a "
            "lightweight starting point, then search memories or conversations for task-specific evidence."
        ),
        annotations=_read_annotations("Get user profile"),
        input_schema={"type": "object", "properties": {}},
        output_schema=_output_schema(
            {
                "type": "object",
                "oneOf": [
                    _object_schema(
                        ["profile_text"],
                        profile_text={"type": "string"},
                        generated_at=_DATETIME_OR_NULL,
                        data_sources_used={
                            "anyOf": [
                                {"type": "integer", "minimum": 0},
                                {"type": "array", "items": {"type": "string"}},
                                {"type": "null"},
                            ]
                        },
                    ),
                    _object_schema(
                        ["profile", "message"],
                        profile={"type": "null"},
                        message={"type": "string"},
                    ),
                ],
            }
        ),
        scope="memories.read",
        operation="memory_get",
        write_operation=_READ,
        rate_bucket=None,
        handler=profile.get_user_profile,
    ),
    ToolSpec(
        name="get_memories",
        title="Get memories",
        description=(
            "Retrieve durable facts known about the user across domains. This is not recent conversation history; "
            "for today, yesterday, last week, or another time window use date-bounded get_conversations instead."
        ),
        annotations=_read_annotations("Get memories"),
        input_schema={
            "type": "object",
            "properties": {
                "categories": {
                    "type": "array",
                    "items": {"type": "string", "enum": _MEMORY_CATEGORY_ENUM},
                    "description": "Categories to filter by",
                    "default": [],
                },
                "limit": {
                    "type": "integer",
                    "description": "Number of durable memories to retrieve",
                    "default": MCP_MEMORY_LIST_DEFAULT_LIMIT,
                    "minimum": 1,
                    "maximum": MCP_MEMORY_LIST_MAX_LIMIT,
                },
                "offset": {
                    "type": "integer",
                    "description": "Offset for pagination",
                    "default": 0,
                    "minimum": 0,
                    "maximum": 100000,
                },
                "cursor": _CURSOR_INPUT,
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
        output_schema=_output_schema(
            _object_schema(
                ["memories"],
                memories=_ARRAY_OF_OBJECTS,
                filters={"type": "object"},
                next_cursor=_NEXT_CURSOR_OUTPUT,
                has_more={"type": "boolean"},
                more_in_window={"type": "boolean"},
                scanned_count={"type": "integer"},
                scan_truncated={"type": "boolean"},
            )
        ),
        scope="memories.read",
        operation="memory_list",
        write_operation=_READ,
        rate_bucket=None,
        handler=memories.get_memories,
    ),
    ToolSpec(
        name="create_memory",
        title="Create memory",
        description="Create a new memory. A memory is a known fact about the user across multiple domains.",
        annotations=_create_annotations("Create memory", idempotent=False),
        input_schema={
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "The content of the memory"},
                "category": {
                    "type": "string",
                    "enum": _MEMORY_CATEGORY_ENUM,
                    "description": "The category of the memory",
                },
            },
            "required": ["content"],
        },
        output_schema=_output_schema(
            _object_schema(["memory"], success={"type": "boolean"}, memory={"type": "object"})
        ),
        scope="memories.write",
        operation="other",
        write_operation=_MEMORY_CREATE,
        rate_bucket="memories:create",
        handler=memories.create_memory,
    ),
    ToolSpec(
        name="create_memories",
        title="Create memories",
        description=(
            "Create up to 25 memories in one call; prefer this over repeated create_memory calls when saving "
            "several facts. Each item takes content and an optional category. Every item is rate-limited "
            "individually and returns its own status: created, duplicate (exact content+category already "
            "created earlier in the same batch), or error."
        ),
        annotations=_create_annotations("Create memories", idempotent=False),
        input_schema={
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "description": "Memories to create",
                    "minItems": 1,
                    "maxItems": MCP_MEMORY_BATCH_MAX_ITEMS,
                    "items": {
                        "type": "object",
                        "properties": {
                            "content": {"type": "string", "description": "The content of the memory"},
                            "category": {
                                "type": "string",
                                "enum": _MEMORY_CATEGORY_ENUM,
                                "description": "The category of the memory",
                            },
                        },
                        "required": ["content"],
                    },
                },
            },
            "required": ["items"],
        },
        output_schema=_output_schema(
            _object_schema(
                ["results"],
                results={
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["index", "status"],
                        "properties": {
                            "index": {"type": "integer"},
                            "status": {"type": "string", "enum": ["created", "duplicate", "error"]},
                            "memory_id": {"type": "string"},
                            "error": {"type": "object"},
                        },
                    },
                },
            )
        ),
        scope="memories.write",
        operation="memories_batch",
        write_operation=_MEMORY_CREATE,
        # No transport-level bucket: the handler charges ``memories:create``
        # once per submitted item so a batch cannot bypass the write limit.
        rate_bucket=None,
        handler=memories.create_memories,
    ),
    ToolSpec(
        name="delete_memory",
        title="Delete memory",
        description="Delete a memory by ID.",
        annotations=_delete_annotations("Delete memory"),
        input_schema={
            "type": "object",
            "properties": {"memory_id": {"type": "string", "description": "The ID of the memory to delete"}},
            "required": ["memory_id"],
        },
        output_schema=_output_schema(_object_schema(["success"], success={"type": "boolean"})),
        scope="memories.write",
        operation="other",
        write_operation=_MEMORY_DELETE,
        rate_bucket="memories:delete",
        handler=memories.delete_memory,
    ),
    ToolSpec(
        name="edit_memory",
        title="Edit memory",
        description="Edit a memory's content.",
        annotations=_edit_annotations("Edit memory"),
        input_schema={
            "type": "object",
            "properties": {
                "memory_id": {"type": "string", "description": "The ID of the memory to edit"},
                "content": {"type": "string", "description": "The new content for the memory"},
            },
            "required": ["memory_id", "content"],
        },
        output_schema=_output_schema(_object_schema(["success"], success={"type": "boolean"})),
        scope="memories.write",
        operation="other",
        write_operation=_MEMORY_UPDATE,
        rate_bucket="memories:modify",
        handler=memories.edit_memory,
    ),
    ToolSpec(
        name="get_conversations",
        title="Get conversations",
        description=(
            "First choice for recency questions such as today, yesterday, or last week: pass start_date and "
            "end_date. Returns small conversation cards only. Deep-read only a few relevant ids with "
            "get_conversation_by_id."
        ),
        annotations=_read_annotations("Get conversations"),
        input_schema={
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description": "Filter after this date (yyyy-mm-dd)"},
                "end_date": {"type": "string", "description": "Filter before this date (yyyy-mm-dd)"},
                "categories": {
                    "type": "array",
                    "items": {"type": "string", "enum": _CONVERSATION_CATEGORY_ENUM},
                    "description": "Categories to filter by",
                    "default": [],
                },
                "limit": {
                    "type": "integer",
                    "description": "Number of conversation cards to retrieve",
                    "default": 20,
                    "minimum": 1,
                    "maximum": MCP_CONVERSATION_LIST_MAX_LIMIT,
                },
                "offset": {
                    "type": "integer",
                    "description": "Offset for pagination",
                    "default": 0,
                    "minimum": 0,
                    "maximum": 100000,
                },
                "cursor": _CURSOR_INPUT,
            },
        },
        output_schema=_output_schema(
            _object_schema(
                ["conversations"],
                conversations=_object_array_with(**_CONVERSATION_TIMESTAMPS),
                next_cursor=_NEXT_CURSOR_OUTPUT,
            )
        ),
        scope="conversations.read",
        operation="conversation_list",
        write_operation=_READ,
        rate_bucket=None,
        handler=conversations.get_conversations,
    ),
    ToolSpec(
        name="get_conversation_by_id",
        title="Get conversation by ID",
        description=(
            "Deep-read one conversation card and a bounded transcript. Use only for a few ids selected from "
            "get_conversations or search_conversations; the response reports truncated=true when clipped."
        ),
        annotations=_read_annotations("Get conversation by ID"),
        input_schema={
            "type": "object",
            "properties": {
                "conversation_id": {"type": "string", "description": "The ID of the conversation to retrieve"},
                "max_segments": {
                    "type": "integer",
                    "description": "Maximum transcript segments to return",
                    "default": MCP_CONVERSATION_FETCH_DEFAULT_MAX_SEGMENTS,
                    "minimum": 1,
                    "maximum": MCP_CONVERSATION_FETCH_MAX_SEGMENTS,
                },
                "max_chars": {
                    "type": "integer",
                    "description": "Maximum total transcript text characters to return",
                    "default": MCP_CONVERSATION_FETCH_DEFAULT_MAX_CHARS,
                    "minimum": 1,
                    "maximum": MCP_CONVERSATION_FETCH_MAX_CHARS,
                },
            },
            "required": ["conversation_id"],
        },
        output_schema=_output_schema(
            _object_schema(
                ["conversation"],
                conversation={"type": "object", "properties": dict(_CONVERSATION_TIMESTAMPS)},
                truncated={"type": "boolean"},
            )
        ),
        scope="conversations.read",
        operation="conversation_get",
        write_operation=_READ,
        rate_bucket=None,
        handler=conversations.get_conversation_by_id,
    ),
    ToolSpec(
        name="get_conversations_by_ids",
        title="Get conversations by IDs",
        description=(
            "Deep-read up to 20 conversations in one call — the preferred follow-up after "
            "get_conversations or search_conversations returns several relevant ids. Each item returns the "
            "same bounded card and transcript as get_conversation_by_id with its own truncated flag; ids "
            "that resolve to nothing are listed in not_found. When the response budget is hit, later items "
            "are omitted and truncated=true — retry them with smaller max_segments/max_chars."
        ),
        annotations=_read_annotations("Get conversations by IDs"),
        input_schema={
            "type": "object",
            "properties": {
                "conversation_ids": {
                    "type": "array",
                    "description": "Conversation IDs to retrieve (1-20; duplicates are fetched once)",
                    "minItems": 1,
                    "maxItems": MCP_CONVERSATION_BATCH_MAX_IDS,
                    "items": {"type": "string", "minLength": 1},
                },
                "max_segments": {
                    "type": "integer",
                    "description": "Maximum transcript segments to return per conversation",
                    "default": MCP_CONVERSATION_FETCH_DEFAULT_MAX_SEGMENTS,
                    "minimum": 1,
                    "maximum": MCP_CONVERSATION_FETCH_MAX_SEGMENTS,
                },
                "max_chars": {
                    "type": "integer",
                    "description": "Maximum total transcript text characters to return per conversation",
                    "default": MCP_CONVERSATION_FETCH_DEFAULT_MAX_CHARS,
                    "minimum": 1,
                    "maximum": MCP_CONVERSATION_FETCH_MAX_CHARS,
                },
            },
            "required": ["conversation_ids"],
        },
        output_schema=_output_schema(
            _object_schema(
                ["conversations", "not_found", "truncated"],
                conversations={
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "conversation": {"type": "object", "properties": dict(_CONVERSATION_TIMESTAMPS)},
                        },
                    },
                },
                not_found={"type": "array", "items": {"type": "string"}},
                truncated={"type": "boolean"},
            )
        ),
        scope="conversations.read",
        operation="conversation_get",
        write_operation=_READ,
        rate_bucket=None,
        handler=conversations.get_conversations_by_ids,
    ),
    ToolSpec(
        name="search_memories",
        title="Search memories",
        description=(
            "Semantic search across durable facts known about the user. This is not for recent conversations; "
            "use search_conversations with start_date and end_date for a topic inside a time window."
        ),
        annotations=_read_annotations("Search memories"),
        input_schema={
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
        output_schema=_output_schema(_object_schema(["memories"], memories=_ARRAY_OF_OBJECTS)),
        scope="memories.read",
        operation="memory_search",
        write_operation=_READ,
        rate_bucket=None,
        handler=memories.search_memories,
    ),
    ToolSpec(
        name="search_conversations",
        title="Search conversations",
        description=(
            "Search for a topic inside the user's conversations, preferably with start_date and end_date. "
            "Returns small cards plus short match snippets; deep-read only a few relevant ids with "
            "get_conversation_by_id."
        ),
        annotations=_read_annotations("Search conversations"),
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Natural language search query"},
                "start_date": {"type": "string", "description": "Filter after this date (yyyy-mm-dd)"},
                "end_date": {"type": "string", "description": "Filter before this date (yyyy-mm-dd)"},
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results to return",
                    "default": 10,
                    "minimum": 1,
                    "maximum": 100,
                },
            },
            "required": ["query"],
        },
        output_schema=_output_schema(
            _object_schema(["conversations"], conversations=_object_array_with(**_CONVERSATION_TIMESTAMPS))
        ),
        scope="conversations.read",
        operation="conversation_search",
        write_operation=_READ,
        rate_bucket=None,
        handler=conversations.search_conversations,
    ),
    ToolSpec(
        name="search_x_posts",
        title="Search X posts",
        description=(
            "Semantic search across the user's imported X (Twitter) posts — their actual tweets and "
            "bookmarks, not just extracted memories. Returns posts ranked by relevance to the query."
        ),
        annotations=_read_annotations("Search X posts"),
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Natural language search query"},
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results to return",
                    "default": 10,
                    "minimum": 1,
                    "maximum": 100,
                },
            },
            "required": ["query"],
        },
        output_schema=_output_schema(_object_schema(["posts"], posts=_object_array_with(created_at=_DATETIME_OR_NULL))),
        scope="memories.read",
        operation="x_post_search",
        write_operation=_READ,
        rate_bucket=None,
        handler=other.search_x_posts,
    ),
    ToolSpec(
        name="get_x_posts",
        title="Get X posts",
        description=(
            "Retrieve the user's imported X (Twitter) posts, newest first. Optionally filter by kind "
            "(tweet or bookmark). Returns the raw post text, created_at, and id."
        ),
        annotations=_read_annotations("Get X posts"),
        input_schema={
            "type": "object",
            "properties": {
                "kind": {
                    "type": "string",
                    "enum": ["tweet", "bookmark"],
                    "description": "Filter to only tweets or only bookmarks (omit for all)",
                },
                "limit": {
                    "type": "integer",
                    "description": "Number of posts to retrieve",
                    "default": 50,
                    "minimum": 1,
                    "maximum": 200,
                },
            },
        },
        output_schema=_output_schema(_object_schema(["posts"], posts=_object_array_with(created_at=_DATETIME_OR_NULL))),
        scope="memories.read",
        operation="x_post_list",
        write_operation=_READ,
        rate_bucket=None,
        handler=other.get_x_posts,
    ),
    ToolSpec(
        name="get_action_items",
        title="Get action items",
        description=(
            "Retrieve the user's action items (tasks/to-dos extracted from conversations), newest due first. "
            "Each item has a description, completion status, and optional due date. Use this to know what the "
            "user needs to do or has committed to."
        ),
        annotations=_read_annotations("Get action items"),
        input_schema={
            "type": "object",
            "properties": {
                "completed": {"type": "boolean", "description": "Filter by completion status (omit for all)"},
                "due_start_date": {"type": "string", "description": "Only items due on/after this date (yyyy-mm-dd)"},
                "due_end_date": {"type": "string", "description": "Only items due on/before this date (yyyy-mm-dd)"},
                "updated_since": {
                    "type": "string",
                    "description": (
                        "Incremental sync: only items updated on/after this ISO 8601 timestamp "
                        "(timezone offset required), ordered by (updated_at, id). Cannot be combined "
                        "with completed/due-date filters; page further with cursor."
                    ),
                },
                "limit": {
                    "type": "integer",
                    "description": "Number of action items to retrieve",
                    "default": 100,
                    "minimum": 1,
                    "maximum": 500,
                },
                "offset": {
                    "type": "integer",
                    "description": "Offset for pagination",
                    "default": 0,
                    "minimum": 0,
                    "maximum": 100000,
                },
                "cursor": _CURSOR_INPUT,
            },
        },
        output_schema=_output_schema(
            _object_schema(
                ["action_items"],
                action_items=_object_array_with(**_ACTION_ITEM_TIMESTAMPS),
                next_cursor=_NEXT_CURSOR_OUTPUT,
            )
        ),
        scope="action_items.read",
        operation="action_item_list",
        write_operation=_READ,
        rate_bucket=None,
        handler=action_items.get_action_items,
    ),
    ToolSpec(
        name="search_action_items",
        title="Search action items",
        description=(
            "Semantic search across the user's action items (tasks/to-dos). Returns tasks ranked by relevance to "
            "the query — use this to find a specific task by what it is about before completing or updating it."
        ),
        annotations=_read_annotations("Search action items"),
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What to search the user's tasks for"},
                "limit": {
                    "type": "integer",
                    "description": "Max number of tasks to return (1-50)",
                    "default": 10,
                    "minimum": 1,
                    "maximum": 50,
                },
            },
            "required": ["query"],
        },
        output_schema=_output_schema(
            _object_schema(["action_items"], action_items=_object_array_with(**_ACTION_ITEM_TIMESTAMPS))
        ),
        scope="action_items.read",
        operation="action_item_search",
        write_operation=_READ,
        rate_bucket=None,
        handler=action_items.search_action_items,
    ),
    ToolSpec(
        name="create_action_item",
        title="Create action item",
        description=(
            "Create a new action item (task/to-do) for the user — for example a follow-up you identified while "
            "helping them. Retries with the same description return the existing task instead of duplicating it."
        ),
        annotations=_create_annotations("Create action item", idempotent=True),
        input_schema={
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
        output_schema=_output_schema(
            _object_schema(
                ["action_item"],
                success={"type": "boolean"},
                action_item={"type": "object", "properties": dict(_ACTION_ITEM_TIMESTAMPS)},
            )
        ),
        scope="action_items.write",
        operation="other",
        write_operation=_ACTION_ITEM_CREATE,
        rate_bucket="action_items:write",
        handler=action_items.create_action_item,
    ),
    ToolSpec(
        name="complete_action_item",
        title="Complete action item",
        description="Mark an action item complete, or reopen it by passing completed=false.",
        annotations=_edit_annotations("Complete action item"),
        input_schema={
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
        output_schema=_output_schema(
            _object_schema(
                ["action_item"],
                success={"type": "boolean"},
                action_item={"type": "object", "properties": dict(_ACTION_ITEM_TIMESTAMPS)},
            )
        ),
        scope="action_items.write",
        operation="other",
        write_operation=_ACTION_ITEM_COMPLETE,
        rate_bucket="action_items:write",
        handler=action_items.complete_action_item,
    ),
    ToolSpec(
        name="update_action_item",
        title="Update action item",
        description=(
            "Update an action item's description and/or due date. Only the fields you pass are changed; an omitted "
            "due date is left unchanged."
        ),
        annotations=_edit_annotations("Update action item"),
        input_schema={
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
        output_schema=_output_schema(
            _object_schema(
                ["action_item"],
                success={"type": "boolean"},
                action_item={"type": "object", "properties": dict(_ACTION_ITEM_TIMESTAMPS)},
            )
        ),
        scope="action_items.write",
        operation="other",
        write_operation=_ACTION_ITEM_UPDATE,
        rate_bucket="action_items:write",
        handler=action_items.update_action_item,
    ),
    ToolSpec(
        name="delete_action_item",
        title="Delete action item",
        description="Delete an action item by ID. Use this to clean up a task that is no longer relevant.",
        annotations=_delete_annotations("Delete action item"),
        input_schema={
            "type": "object",
            "properties": {
                "action_item_id": {"type": "string", "description": "The ID of the action item to delete"},
            },
            "required": ["action_item_id"],
        },
        output_schema=_output_schema(_object_schema(["success"], success={"type": "boolean"})),
        scope="action_items.write",
        operation="other",
        write_operation=_ACTION_ITEM_DELETE,
        rate_bucket="action_items:write",
        handler=action_items.delete_action_item,
    ),
    ToolSpec(
        name="get_goals",
        title="Get goals",
        description=(
            "Retrieve the user's goals — their stated objectives and what they are working toward. Use this to "
            "ground long-horizon advice and prioritization in what actually matters to the user."
        ),
        annotations=_read_annotations("Get goals"),
        input_schema={
            "type": "object",
            "properties": {
                "include_inactive": {
                    "type": "boolean",
                    "description": "Include ended/inactive goals (default only active goals)",
                    "default": False,
                },
            },
        },
        output_schema=_output_schema(_object_schema(["goals"], goals=_ARRAY_OF_OBJECTS)),
        scope="goals.read",
        operation="goal_list",
        write_operation=_READ,
        rate_bucket=None,
        handler=other.get_goals,
    ),
    ToolSpec(
        name="get_chat_messages",
        title="Get chat messages",
        description=(
            "Retrieve the user's recent chat history with Omi, newest first. Reveals what the user has previously "
            "asked, their intent, and stated preferences. Returns message text, sender (human/ai), and timestamp."
        ),
        annotations=_read_annotations("Get chat messages"),
        input_schema={
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Number of messages to retrieve",
                    "default": 50,
                    "minimum": 1,
                    "maximum": 200,
                },
                "offset": {
                    "type": "integer",
                    "description": "Offset for pagination",
                    "default": 0,
                    "minimum": 0,
                    "maximum": 100000,
                },
                "cursor": _CURSOR_INPUT,
            },
        },
        output_schema=_output_schema(
            _object_schema(
                ["messages"],
                messages=_object_array_with(created_at=_DATETIME_OR_NULL),
                next_cursor=_NEXT_CURSOR_OUTPUT,
            )
        ),
        scope="chat.read",
        operation="chat_message_list",
        write_operation=_READ,
        rate_bucket=None,
        handler=other.get_chat_messages,
    ),
    ToolSpec(
        name="get_people",
        title="Get people",
        description=(
            "Retrieve the people/contacts the user interacts with (recurring speakers Omi has identified). "
            "Returns each person's name, id, and a few transcript samples of how they speak. Use this to reason "
            "about the user's relationships, not just raw text."
        ),
        annotations=_read_annotations("Get people"),
        input_schema={"type": "object", "properties": {}},
        output_schema=_output_schema(
            _object_schema(["people"], people=_object_array_with(created_at=_DATETIME_OR_NULL))
        ),
        scope="people.read",
        operation="people_list",
        write_operation=_READ,
        rate_bucket=None,
        handler=other.get_people,
    ),
    ToolSpec(
        name="get_screen_activity",
        title="Get screen activity",
        description=(
            "Retrieve synced desktop screen observations (Rewind): apps, windows and OCR text ordered by time. "
            "Use group_by=app|hour|day for aggregated buckets with counts, estimated observation seconds "
            "(bounded capture gaps, never actual usage duration), and top window titles; page through raw "
            "rows with cursor. Use summary=true for the legacy per-app counts and coverage. Counts do not "
            "measure usage duration or intent. Capture and sync completeness are unknown."
        ),
        annotations=_read_annotations("Get screen activity"),
        input_schema={
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description": "Filter on/after this date (yyyy-mm-dd)"},
                "end_date": {"type": "string", "description": "Filter on/before this date (yyyy-mm-dd)"},
                "app": {"type": "string", "description": "Filter to a single app name"},
                "group_by": {
                    "type": "string",
                    "enum": ["none", "app", "hour", "day"],
                    "description": "Aggregate rows into buckets by app, hour, or day instead of returning raw rows",
                    "default": "none",
                },
                "summary": {
                    "type": "boolean",
                    "description": "Return per-app observation counts and coverage instead of raw rows",
                    "default": False,
                },
                "limit": {
                    "type": "integer",
                    "description": "Max rows scanned per page (ignored when summary=true)",
                    "default": 200,
                    "minimum": 1,
                    "maximum": 1000,
                },
                "cursor": _CURSOR_INPUT,
            },
        },
        output_schema=_output_schema(
            {
                "type": "object",
                "oneOf": [
                    _object_schema(
                        ["screen_activity"],
                        screen_activity=_ARRAY_OF_OBJECTS,
                        next_cursor=_NEXT_CURSOR_OUTPUT,
                    ),
                    _object_schema(
                        ["buckets"],
                        group_by={"type": "string"},
                        buckets=_ARRAY_OF_OBJECTS,
                        next_cursor=_NEXT_CURSOR_OUTPUT,
                    ),
                    _object_schema(
                        ["apps", "total_screenshots", "coverage"],
                        apps={"type": "object"},
                        total_screenshots={"type": "integer"},
                        coverage={"type": "object"},
                    ),
                ],
            }
        ),
        scope="screen_activity.read",
        operation="screen_activity_get",
        write_operation=_READ,
        rate_bucket=None,
        handler=other.get_screen_activity,
    ),
    ToolSpec(
        name="get_daily_summaries",
        title="Get daily summaries",
        description=(
            "Retrieve Omi's per-day summaries of the user's life, newest first. A concise digest of what happened "
            "each day. Use for temporal context — 'what has the user been up to lately'."
        ),
        annotations=_read_annotations("Get daily summaries"),
        input_schema={
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description": "Filter on/after this date (yyyy-mm-dd)"},
                "end_date": {"type": "string", "description": "Filter on/before this date (yyyy-mm-dd)"},
                "limit": {
                    "type": "integer",
                    "description": "Number of summaries to retrieve",
                    "default": 30,
                    "minimum": 1,
                    "maximum": 100,
                },
                "offset": {
                    "type": "integer",
                    "description": "Offset for pagination",
                    "default": 0,
                    "minimum": 0,
                    "maximum": 100000,
                },
                "cursor": _CURSOR_INPUT,
            },
        },
        output_schema=_output_schema(
            _object_schema(
                ["daily_summaries"],
                daily_summaries=_ARRAY_OF_OBJECTS,
                next_cursor=_NEXT_CURSOR_OUTPUT,
            )
        ),
        scope="conversations.read",
        operation="daily_summary_list",
        write_operation=_READ,
        rate_bucket=None,
        handler=other.get_daily_summaries,
    ),
)

TOOLS_BY_NAME: Dict[str, ToolSpec] = {spec.name: spec for spec in TOOL_SPECS}

TOOL_REQUIRED_SCOPE: Dict[str, str] = {spec.name: spec.scope for spec in TOOL_SPECS}

# ``tools/list`` payload in stable registry order (deterministic for prompt
# caching across requests).
MCP_TOOLS: List[Dict[str, Any]] = [spec.list_entry() for spec in TOOL_SPECS]

WRITE_OPERATION_NONE = _READ


def spec_for_tool(tool_name: object) -> Optional[ToolSpec]:
    return TOOLS_BY_NAME.get(tool_name) if isinstance(tool_name, str) else None


def execute_tool(
    user_id: str,
    tool_name: str,
    arguments: Dict[str, Any],
    auth_context: Optional[ProductAuthorizationContext] = None,
) -> Dict[str, Any]:
    """Execute an MCP tool and return the result. Raises ToolExecutionError on failure."""
    spec = spec_for_tool(tool_name)
    if spec is None:
        raise ToolExecutionError(f"Unknown tool: {tool_name}", code=-32601)
    return spec.handler(user_id, arguments, auth_context)
