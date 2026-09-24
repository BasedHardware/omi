"""Memory tool handlers for the hosted MCP server."""

import logging
from typing import Any, Dict, List, Optional, cast

from fastapi import HTTPException

from database._client import db
from models.memories import MemoryDB, Memory, MemoryCategory
from testing.parity_pack_v0.live_capture import capture_memory_write
from utils.llm.memories import identify_category_for_memory
from utils.memory.memory_api_contract import MemoryApiExposure, memory_api_payload
from utils.memory.memory_service import MemoryService
from utils.memory.memory_system import MemorySystem
from utils.memory.product_authorization import (
    ProductAuthorizationContext,
    authorize_memory_external_default_memory_read,
    authorize_memory_external_default_memory_write,
)
from utils.mcp_memories import (
    collect_filtered_memories,
    parse_mcp_bool,
    parse_mcp_datetime,
    parse_mcp_int,
    parse_optional_mcp_bool,
)
from utils.mcp_server.constants import (
    MCP_MEMORY_LIST_DEFAULT_LIMIT,
    MCP_MEMORY_LIST_MAX_LIMIT,
    MCP_MEMORY_LIST_MAX_SCAN,
)
from utils.mcp_server.errors import (
    ToolExecutionError,
    authorization_denied_error,
    raise_tool_error_from_http,
)

logger = logging.getLogger(__name__)


def _log_grant_denial(tool: str, grant: Any) -> None:
    """Log a memory-grant denial's observability reason server-side.

    The model-visible error stays generic; the structured ``reason`` (missing
    grant, disabled key, rollout state) is what ops needs to tell "user has no
    memories" apart from "credential is not authorized". Only the reason field
    is logged — the rest of the observability payload can carry internal doc
    ids and must stay out of logs.
    """
    observability = getattr(grant, "observability", None)
    reason = (
        observability.get("reason")
        if isinstance(observability, dict)
        else observability if isinstance(observability, str) else getattr(grant, "reason", "unknown")
    )
    logger.warning("mcp memory grant denied tool=%s reason=%s", tool, reason)


def get_memories(
    uid: str,
    arguments: Dict[str, Any],
    auth_context: Optional[ProductAuthorizationContext] = None,
) -> Dict[str, Any]:
    raw_categories: object = arguments.get("categories", [])
    categories_list: List[Any] = cast(List[Any], raw_categories) if isinstance(raw_categories, list) else []
    try:
        limit = parse_mcp_int(
            arguments.get("limit"),
            "limit",
            default=MCP_MEMORY_LIST_DEFAULT_LIMIT,
            minimum=1,
            maximum=MCP_MEMORY_LIST_MAX_LIMIT,
        )
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

    valid_categories: List[str] = []
    for cat in categories_list:
        try:
            valid_categories.append(MemoryCategory(cat).value)
        except ValueError:
            raise ToolExecutionError(f"Invalid memory category: '{cat}'", code=-32602)

    if auth_context is None:
        raise authorization_denied_error("Missing MCP API app/key identity for memory read authorization")
    app_key_grant = authorize_memory_external_default_memory_read(auth_context, db_client=db)
    if not app_key_grant.allowed:
        _log_grant_denial("get_memories", app_key_grant)
        raise authorization_denied_error(
            "This credential is not permitted to read memories. Check that it has the "
            "memories.read permission, or reconnect the account."
        )

    result = collect_filtered_memories(
        lambda batch_offset, batch_limit: [
            memory.model_dump(mode='json')
            for memory in MemoryService(db_client=db).read(uid, limit=batch_limit, offset=batch_offset)
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
        max_scan=MCP_MEMORY_LIST_MAX_SCAN,
    )
    # Apply locked content truncation
    for memory in result["memories"]:
        if memory.get('is_locked', False):
            content = memory.get('content', '')
            memory['content'] = (content[:70] + '...') if len(content) > 70 else content

    return result


def create_memory(
    uid: str,
    arguments: Dict[str, Any],
    auth_context: Optional[ProductAuthorizationContext] = None,
) -> Dict[str, Any]:
    content = arguments.get("content")
    if not isinstance(content, str) or not content:
        raise ToolExecutionError("Content is required and must be a string")

    if auth_context is None:
        raise authorization_denied_error("Missing MCP API app/key identity for memory write authorization")
    write_grant = authorize_memory_external_default_memory_write(auth_context, db_client=db)
    if not write_grant.allowed:
        _log_grant_denial("create_memory", write_grant)
        raise authorization_denied_error(
            "This credential is not permitted to write memories. Check that it has the "
            "memories.write permission, or reconnect the account."
        )

    # Honor an explicit category when it names a real MemoryCategory; otherwise
    # keep the classifier fallback.
    category = None
    raw_category = arguments.get("category")
    if raw_category:
        try:
            category = MemoryCategory(str(raw_category))
        except ValueError:
            category = None
    if category is None:
        category = identify_category_for_memory(content)
    memory = Memory(content=content, category=category)
    memory_db = MemoryDB.from_memory(memory, uid, None, True)
    try:
        memory_db = MemoryService(db_client=db).create_external_memory(
            uid,
            memory_db,
            memory_system=MemorySystem.CANONICAL,
            consumer='mcp',
            operation="mcp_tool_memory_create",
            upsert_vector=False,
            require_canonical_promotion=True,
        )
    except HTTPException as exc:
        raise_tool_error_from_http(exc)

    capture_memory_write(
        principal_id=uid,
        source="mcp_tool_memory_create",
        session_id=memory_db.id,
        memories=[memory_db],
    )

    return {"success": True, "memory": memory_api_payload(memory_db, MemoryApiExposure.CANONICAL)}


def delete_memory(
    uid: str,
    arguments: Dict[str, Any],
    auth_context: Optional[ProductAuthorizationContext] = None,
) -> Dict[str, Any]:
    memory_id = arguments.get("memory_id")
    if not isinstance(memory_id, str) or not memory_id:
        raise ToolExecutionError("memory_id is required and must be a string")

    if auth_context is None:
        raise authorization_denied_error("Missing MCP API app/key identity for memory write authorization")
    write_grant = authorize_memory_external_default_memory_write(auth_context, db_client=db)
    if not write_grant.allowed:
        _log_grant_denial("delete_memory", write_grant)
        raise authorization_denied_error(
            "This credential is not permitted to write memories. Check that it has the "
            "memories.write permission, or reconnect the account."
        )

    try:
        MemoryService(db_client=db).delete_external_memory(
            uid,
            memory_id,
            memory_system=MemorySystem.CANONICAL,
            consumer='mcp',
            operation="mcp_tool_memory_delete",
            delete_vector=False,
        )
    except HTTPException as exc:
        raise_tool_error_from_http(exc)
    return {"success": True}


def edit_memory(
    uid: str,
    arguments: Dict[str, Any],
    auth_context: Optional[ProductAuthorizationContext] = None,
) -> Dict[str, Any]:
    memory_id = arguments.get("memory_id")
    content = arguments.get("content")
    if not isinstance(memory_id, str) or not isinstance(content, str) or not memory_id or not content:
        raise ToolExecutionError("memory_id and content are required and must be strings")

    if auth_context is None:
        raise authorization_denied_error("Missing MCP API app/key identity for memory write authorization")
    write_grant = authorize_memory_external_default_memory_write(auth_context, db_client=db)
    if not write_grant.allowed:
        _log_grant_denial("edit_memory", write_grant)
        raise authorization_denied_error(
            "This credential is not permitted to write memories. Check that it has the "
            "memories.write permission, or reconnect the account."
        )

    if not content.strip():
        raise ToolExecutionError("content must not be empty", code=-32602)
    try:
        MemoryService(db_client=db).update_external_memory_content(
            uid,
            memory_id,
            content,
            memory_system=MemorySystem.CANONICAL,
            consumer='mcp',
            operation="mcp_tool_memory_edit",
            upsert_vector=False,
        )
    except HTTPException as exc:
        raise_tool_error_from_http(exc)
    return {"success": True}


def search_memories(
    uid: str,
    arguments: Dict[str, Any],
    auth_context: Optional[ProductAuthorizationContext] = None,
) -> Dict[str, Any]:
    query = arguments.get("query")
    if not query:
        raise ToolExecutionError("query is required")

    try:
        limit = parse_mcp_int(arguments.get("limit"), "limit", default=10, minimum=1, maximum=20)
    except ValueError as e:
        raise ToolExecutionError(str(e), code=-32602)

    if auth_context is None:
        raise authorization_denied_error("Missing MCP API app/key identity for memory read authorization")
    app_key_grant = authorize_memory_external_default_memory_read(auth_context, db_client=db)
    if not app_key_grant.allowed:
        _log_grant_denial("search_memories", app_key_grant)
        raise authorization_denied_error(
            "This credential is not permitted to read memories. Check that it has the "
            "memories.read permission, or reconnect the account."
        )

    return {"memories": MemoryService(db_client=db).search_mcp(uid, query, limit=limit)}
