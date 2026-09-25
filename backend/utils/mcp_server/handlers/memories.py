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
    filter_and_sort_memories,
    parse_mcp_bool,
    parse_mcp_datetime,
    parse_mcp_int,
    parse_optional_mcp_bool,
)
from utils.mcp_server.constants import (
    MCP_MEMORY_BATCH_MAX_ITEMS,
    MCP_MEMORY_LIST_DEFAULT_LIMIT,
    MCP_MEMORY_LIST_MAX_LIMIT,
    MCP_MEMORY_LIST_MAX_SCAN,
)
from utils.mcp_server.cursors import (
    decode_cursor,
    encode_cursor,
    offset_position,
    uml_position,
)
from utils.mcp_server.errors import (
    ToolExecutionError,
    authorization_denied_error,
    raise_tool_error_from_http,
    stable_error_code,
    tool_error_from_http,
)
from utils.other.endpoints import check_rate_limit_context, check_rate_limit_inline

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


_MEMORY_KEYSET_SORTS = frozenset({"scoring_desc", "updated_desc"})
_MEMORY_KEYSET_MAX_ROUNDS = 4


def _read_memories_keyset_page(
    uid: str,
    *,
    limit: int,
    uml_cursor: Optional[str],
    reviewed: Optional[bool],
    manually_added: Optional[bool],
    include_activity: bool,
    include_sensitive: bool,
    updated_after: Any,
    sort: str,
    categories: Optional[List[str]],
) -> tuple[Dict[str, Any], Optional[str]]:
    """Page the mixed memory view through ``MemoryService.read_page``.

    Eligible only for the sorts that match the view's natural order
    (``scoring_desc`` preserves it; ``updated_desc`` equals it); global
    reorders like ``created_desc`` still need the bounded full-scan path.
    Each round requests only what the page still needs so no filtered row is
    ever collected past the emitted limit — the inner cursor always sits
    after every row it scanned, so collected rows must all be emitted.
    Returns ``(result, resume_uml_cursor)``.
    """
    service = MemoryService(db_client=db)
    filtered: List[Dict[str, Any]] = []
    scanned = 0
    scan_truncated = False
    rounds = 0
    while len(filtered) < limit and rounds < _MEMORY_KEYSET_MAX_ROUNDS:
        try:
            page = service.read_page(uid, limit=limit - len(filtered), cursor=uml_cursor)
        except HTTPException as exc:
            raise_tool_error_from_http(exc)
        uml_cursor = page.next_cursor
        scan_truncated = scan_truncated or page.truncated
        scanned += len(page.memories)
        filtered.extend(
            filter_and_sort_memories(
                [memory.model_dump(mode='json') for memory in page.memories],
                reviewed=reviewed,
                manually_added=manually_added,
                include_activity=include_activity,
                include_sensitive=include_sensitive,
                updated_after=updated_after,
                sort=sort,
                categories=categories,
            )
        )
        rounds += 1
        if page.next_cursor is None:
            break
    result = {
        'memories': filtered,
        'returned_count': len(filtered),
        'has_more': uml_cursor is not None,
        'more_in_window': False,
        'offset': 0,
        'limit': limit,
        'sort': sort,
        'include_activity': include_activity,
        'include_sensitive': include_sensitive,
        'scanned_count': scanned,
        'scan_truncated': scan_truncated,
    }
    return result, uml_cursor


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

    return memories_page_core(
        uid,
        limit=limit,
        offset=offset,
        cursor_token=arguments.get("cursor"),
        reviewed=reviewed,
        manually_added=manually_added,
        include_activity=include_activity,
        include_sensitive=include_sensitive,
        updated_after=updated_after,
        sort=sort,
        categories=valid_categories,
        cursor_kind="get_memories",
    )


def memories_page_core(
    uid: str,
    *,
    limit: int,
    offset: int = 0,
    cursor_token: Optional[str] = None,
    reviewed: Optional[bool] = None,
    manually_added: Optional[bool] = None,
    include_activity: bool = False,
    include_sensitive: bool = True,
    updated_after: Any = None,
    sort: str = "created_desc",
    categories: Optional[List[str]] = None,
    max_scan: int = MCP_MEMORY_LIST_MAX_SCAN,
    cursor_kind: str,
) -> Dict[str, Any]:
    """Shared validated memory page for the MCP ``get_memories`` tool and REST list.

    ``cursor_kind`` binds the opaque cursor to the calling surface so tokens
    minted on one surface cannot resume the other. ``max_scan`` bounds the
    filtered-scan path — REST keeps its released 5000-row window while the
    tool uses the smaller MCP cap. Callers must authorize the read grant
    first — this function performs no product authorization.
    """
    valid_categories = list(categories or [])
    filters = {
        "categories": sorted(valid_categories),
        "sort": sort,
        "reviewed": reviewed,
        "manually_added": manually_added,
        "updated_after": updated_after.isoformat() if updated_after else None,
        "include_activity": include_activity,
        "include_sensitive": include_sensitive,
    }
    uml_cursor = None
    if cursor_token is not None:
        if offset != 0:
            raise ToolExecutionError("cursor and offset are mutually exclusive.", code=-32602)
        position = decode_cursor(cursor_token, kind=cursor_kind, uid=uid, filters=filters)
        if "uml" in position:
            uml_cursor = uml_position(position)
        else:
            offset = offset_position(position)

    if uml_cursor is not None or (cursor_token is None and offset == 0 and sort in _MEMORY_KEYSET_SORTS):
        result, resume_uml = _read_memories_keyset_page(
            uid,
            limit=limit,
            uml_cursor=uml_cursor,
            reviewed=reviewed,
            manually_added=manually_added,
            include_activity=include_activity,
            include_sensitive=include_sensitive,
            updated_after=updated_after,
            sort=sort,
            categories=valid_categories or None,
        )
    else:
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
            max_scan=max_scan,
        )
        resume_uml = None
        # The bounded scan walks at most max_scan raw rows per call, so an
        # offset beyond the collected window could never be reached: emit a
        # cursor only for in-window continuation and let scan_truncated mark
        # the boundary instead of a dangling position.
        if result.get("more_in_window"):
            result["next_cursor"] = encode_cursor(
                kind=cursor_kind,
                uid=uid,
                position={"offset": offset + len(result["memories"])},
                filters=filters,
            )
    # Apply locked content truncation
    for memory in result["memories"]:
        if memory.get('is_locked', False):
            content = memory.get('content') or ''
            memory['content'] = (content[:70] + '...') if len(content) > 70 else content

    if resume_uml is not None:
        result["next_cursor"] = encode_cursor(
            kind=cursor_kind,
            uid=uid,
            position={"uml": resume_uml},
            filters=filters,
        )
    return result


def _require_memory_write_grant(
    tool: str,
    auth_context: Optional[ProductAuthorizationContext],
) -> None:
    """Authorize the credential's external default-memory write grant."""
    if auth_context is None:
        raise authorization_denied_error("Missing MCP API app/key identity for memory write authorization")
    write_grant = authorize_memory_external_default_memory_write(auth_context, db_client=db)
    if not write_grant.allowed:
        _log_grant_denial(tool, write_grant)
        raise authorization_denied_error(
            "This credential is not permitted to write memories. Check that it has the "
            "memories.write permission, or reconnect the account."
        )


def _resolve_memory_category(raw_category: Any, content: str) -> MemoryCategory:
    # Honor an explicit category when it names a real MemoryCategory; otherwise
    # keep the classifier fallback.
    category = None
    if raw_category:
        try:
            category = MemoryCategory(str(raw_category))
        except ValueError:
            category = None
    if category is None:
        category = identify_category_for_memory(content)
    return category


def _create_one_memory(
    uid: str,
    memory: Memory,
    *,
    operation: str,
    upsert_vector: bool = False,
) -> MemoryDB:
    """Create one memory through the same external write path as ``create_memory``."""
    memory_db = MemoryDB.from_memory(memory, uid, None, True)
    memory_db = MemoryService(db_client=db).create_external_memory(
        uid,
        memory_db,
        memory_system=MemorySystem.CANONICAL,
        consumer='mcp',
        operation=operation,
        upsert_vector=upsert_vector,
        require_canonical_promotion=True,
    )
    capture_memory_write(
        principal_id=uid,
        source=operation,
        session_id=memory_db.id,
        memories=[memory_db],
    )
    return memory_db


def _charge_memories_create(uid: str, auth_context: Optional[ProductAuthorizationContext]) -> None:
    """Charge one item against the shared ``memories:create`` write bucket.

    Mirrors the transport's per-call write charge: OAuth/API-key grants are
    limited per credential via the product context, with a per-UID fallback —
    and the same fail-closed limiter errors (429/503) as a singular write.
    """
    if auth_context is not None:
        check_rate_limit_context(auth_context, "memories:create")
    else:
        check_rate_limit_inline(uid, "memories:create")


def _batch_item_error(exc: HTTPException) -> Dict[str, str]:
    """Map a limiter/write HTTPException to a per-item error object."""
    if exc.status_code == 429:
        return {"code": "rate_limited", "message": f"{exc.detail}"}
    if exc.status_code == 403:
        return {
            "code": "authorization_denied",
            "message": "This credential is not permitted to perform this write.",
        }
    tool_error = tool_error_from_http(exc)
    return {"code": stable_error_code(tool_error), "message": tool_error.message}


def create_memory(
    uid: str,
    arguments: Dict[str, Any],
    auth_context: Optional[ProductAuthorizationContext] = None,
) -> Dict[str, Any]:
    content = arguments.get("content")
    if not isinstance(content, str) or not content:
        raise ToolExecutionError("Content is required and must be a string")

    _require_memory_write_grant("create_memory", auth_context)

    category = _resolve_memory_category(arguments.get("category"), content)
    try:
        memory_db = _create_one_memory(
            uid,
            Memory(content=content, category=category),
            operation="mcp_tool_memory_create",
        )
    except HTTPException as exc:
        raise_tool_error_from_http(exc)

    return {"success": True, "memory": memory_api_payload(memory_db, MemoryApiExposure.CANONICAL)}


def create_memories(
    uid: str,
    arguments: Dict[str, Any],
    auth_context: Optional[ProductAuthorizationContext] = None,
) -> Dict[str, Any]:
    """Create 1..25 memories in one call with per-item results.

    Every VALID item — including duplicates and items that later fail to
    store — is charged once against the ``memories:create`` bucket, so a
    batch of 25 cannot bypass the singular write limit; malformed items are
    rejected before their charge. The write bucket is charged
    inside this handler (the tool spec carries no transport-level
    ``rate_bucket``), preserving the fail-closed 429/503 limiter errors as
    per-item failures rather than aborting the whole batch. Within-batch
    exact ``(content, category)`` duplicates answer ``duplicate`` pointing at
    the first created id — dedupe is batch-local only; it never assumes a
    cross-request/cross-user cache.
    """
    raw_items = arguments.get("items")
    if not isinstance(raw_items, list):
        raise ToolExecutionError("items must be an array of memory objects", code=-32602)
    if not 1 <= len(raw_items) <= MCP_MEMORY_BATCH_MAX_ITEMS:
        raise ToolExecutionError(
            f"items must contain between 1 and {MCP_MEMORY_BATCH_MAX_ITEMS} memories",
            code=-32602,
        )

    _require_memory_write_grant("create_memories", auth_context)

    results: List[Dict[str, Any]] = []
    first_created_id_by_key: Dict[Any, str] = {}
    for index, item in enumerate(raw_items):
        if not isinstance(item, dict):
            results.append(
                {
                    "index": index,
                    "status": "error",
                    "error": {"code": "invalid_arguments", "message": "Each item must be an object."},
                }
            )
            continue
        content = item.get("content")
        if not isinstance(content, str) or not content:
            results.append(
                {
                    "index": index,
                    "status": "error",
                    "error": {
                        "code": "invalid_arguments",
                        "message": "Each item requires a non-empty content string.",
                    },
                }
            )
            continue

        try:
            _charge_memories_create(uid, auth_context)
        except HTTPException as exc:
            results.append({"index": index, "status": "error", "error": _batch_item_error(exc)})
            continue

        dedupe_key = (content, item.get("category") if isinstance(item.get("category"), str) else None)
        first_created_id = first_created_id_by_key.get(dedupe_key)
        if first_created_id is not None:
            results.append({"index": index, "status": "duplicate", "memory_id": first_created_id})
            continue

        category = _resolve_memory_category(item.get("category"), content)
        try:
            memory_db = _create_one_memory(
                uid,
                Memory(content=content, category=category),
                operation="mcp_tool_memories_create",
            )
        except HTTPException as exc:
            results.append({"index": index, "status": "error", "error": _batch_item_error(exc)})
            continue
        except Exception:
            # Unexpected store failures must not abort the rest of the batch;
            # the stack trace stays server-side like the singular tool error.
            logger.exception("mcp create_memories item failed index=%d", index)
            results.append(
                {
                    "index": index,
                    "status": "error",
                    "error": {"code": "internal", "message": "Memory could not be created. Retry shortly."},
                }
            )
            continue
        memory_id = str(memory_db.id)
        first_created_id_by_key[dedupe_key] = memory_id
        results.append({"index": index, "status": "created", "memory_id": memory_id})

    return {"results": results}


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
