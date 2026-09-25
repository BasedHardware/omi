from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from utils.executors import postprocess_executor
from utils.mcp_data import end_of_day_utc, parse_date_only_utc

from fastapi import APIRouter, HTTPException, Depends, Request, Response
from fastapi.routing import APIRoute
from pydantic import BaseModel

import database.users as users_db
from database._client import db
import database.phone_calls as phone_calls_db
from firebase_admin import auth as firebase_auth

# from database.redis_db import get_filter_category_items
# from database.vector_db import query_vectors_by_metadata
from models.memories import Memory, MemoryCategory
from models.conversation_enums import CategoryEnum
from models.conversation import AppResult
from models.screen_activity import ScreenActivityCoverage
from utils.conversations.render import populate_speaker_names
from utils.conversations.mcp_transcript_search import attach_match_snippets_to_conversations
from utils.apps import update_personas_async
from utils.llm.memories import identify_category_for_memory
from utils.memory.memory_service import fetch_memory_dict
from dependencies import (
    get_uid_from_mcp_api_key,
    get_current_user_id,
    get_mcp_memory_default_memory_read_context,
    get_mcp_memory_default_memory_write_context,
)
from utils.other.endpoints import with_rate_limit, with_rate_limit_context
from utils.log_sanitizer import sanitize_pii
from utils.memory.product_authorization import (
    ProductAuthorizationContext,
    authorize_memory_external_default_memory_read,
    authorize_memory_external_default_memory_write,
)
from utils.mcp_memories import (
    parse_mcp_bool,
    parse_mcp_datetime,
    parse_mcp_int,
    parse_optional_mcp_bool,
    parse_sync_timestamp,
)
import database.mcp_oauth as mcp_oauth_db
import database.mcp_token_cache as mcp_token_cache_db
from utils.mcp_server.constants import (
    MCP_REST_CONVERSATION_MAX_CHARS,
    MCP_REST_CONVERSATION_MAX_SEGMENTS,
)
from utils.mcp_server.errors import ToolExecutionError
from utils.mcp_server.handlers import action_items as mcp_action_item_handlers
from utils.mcp_server.handlers import conversations as mcp_conversation_handlers
from utils.mcp_server.handlers import memories as mcp_memory_handlers
from utils.mcp_server.handlers import other as mcp_other_handlers
from utils.mcp_server.helpers import bounded_transcript_segments, conversation_card
from utils.mcp_server.registry import spec_for_tool
import logging

logger = logging.getLogger(__name__)

# Generic retry hint on the incremental-sync 503 gates and mapped tool 429/503
# errors. The real per-credential window still reaches clients on every 429
# raised by the with_rate_limit* dependencies — this covers the rest.
_REST_RETRY_AFTER = "60"


class _McpRoute(APIRoute):
    """Ensure every 429 leaving this router carries a Retry-After hint.

    The Redis-backed limiter sets its own windowed value; the in-process
    fallback dependency raises a bare HTTPException(429) with no header, so
    the route layer fills it in without touching an existing one.
    """

    def get_route_handler(self):
        original = super().get_route_handler()

        async def route_handler(request: Request):
            try:
                return await original(request)
            except HTTPException as exc:
                if exc.status_code != 429:
                    raise
                headers = dict(exc.headers or {})
                headers.setdefault("Retry-After", _REST_RETRY_AFTER)
                raise HTTPException(status_code=exc.status_code, detail=exc.detail, headers=headers) from exc

        return route_handler


router = APIRouter(route_class=_McpRoute)

# REST detail/list reads project one extra card field beyond the hosted tool
# reads: the released desktop client consumes apps_results off the card.
_REST_CONVERSATION_EXTRA_FIELD_PATHS = ["apps_results"]

# Detail additionally fetches the manual speaker-assignment receipt so the
# shared prepare-for-read seam can decode it exactly like the legacy full-doc
# read did (it drives the released client's person->speaker_name mapping).
_REST_CONVERSATION_DETAIL_EXTRA_FIELD_PATHS = _REST_CONVERSATION_EXTRA_FIELD_PATHS + [
    "manual_speaker_assignments",
    "manual_speaker_assignments_compressed",
]


def _next_cursor_header(response: Response, next_cursor: Optional[str]) -> None:
    """Carry pagination state in ``X-Next-Cursor`` so list bodies stay arrays."""
    if next_cursor:
        response.headers["X-Next-Cursor"] = next_cursor


def _parse_updated_since(value: Optional[str]) -> Optional[datetime]:
    """Parse the strict ISO-8601 ``updated_since`` input; 400 on malformed/naive."""
    if value is None:
        return None
    try:
        return parse_sync_timestamp(value, "updated_since")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


def _incremental_sync_unsupported(resource: str, alternative: str) -> None:
    """Permanent capability gate: this resource cannot serve a revision-ordered
    feed at all, so the answer is a stable 400 — not a retryable 503."""
    raise HTTPException(
        status_code=400,
        detail=(
            f"incremental_sync_unsupported: {resource} do not persist a queryable "
            f"updated_at revision field, so updated_since cannot be served truthfully. "
            f"Supported alternative: {alternative}."
        ),
    )


def _http_error_from_tool_error(exc: ToolExecutionError) -> HTTPException:
    """Map a shared-handler failure back to the REST status surface."""
    if exc.http_status is not None:
        status_code = exc.http_status
    elif exc.analytics_authorization_denied:
        status_code = 403
    elif exc.analytics_rate_limited:
        status_code = 429
    else:
        status_code = {
            -32602: 400,
            -32000: 400,
            -32001: 404,
            -32002: 402,
            -32009: 503,
        }.get(exc.code, 500)
    headers = {"Retry-After": _REST_RETRY_AFTER} if status_code in (429, 503) else None
    return HTTPException(status_code=status_code, detail=exc.message, headers=headers)


def _call_tool_handler(
    tool_name: str,
    uid: str,
    arguments: Dict[str, Any],
    auth_context: Optional[ProductAuthorizationContext] = None,
) -> Dict[str, Any]:
    """Invoke the shared registry handler, translating its errors to HTTP."""
    spec = spec_for_tool(tool_name)
    assert spec is not None
    try:
        return spec.handler(uid, arguments, auth_context)
    except ToolExecutionError as e:
        raise _http_error_from_tool_error(e)


class McpStatusResponse(BaseModel):
    status: str


class McpOauthGrantsResponse(BaseModel):
    grants: List[Dict[str, Any]] = []


class McpScreenActivityRow(BaseModel):
    id: Optional[str] = None
    timestamp: Optional[datetime] = None
    app_name: Optional[str] = None
    window_title: Optional[str] = None
    ocr_text: Optional[str] = None


class McpScreenActivityAppSummary(BaseModel):
    count: int = 0
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None
    window_titles: List[str] = []


class McpScreenActivitySummaryResponse(BaseModel):
    apps: Dict[str, McpScreenActivityAppSummary] = {}
    total_screenshots: int = 0
    coverage: Optional[ScreenActivityCoverage] = None


@router.get("/v1/mcp/oauth/grants", tags=["mcp"], response_model=McpOauthGrantsResponse)
def get_oauth_grants(uid: str = Depends(get_current_user_id)):
    return {"grants": mcp_oauth_db.list_user_grants(uid)}


@router.delete("/v1/mcp/oauth/grants/{grant_id}", status_code=204, tags=["mcp"])
def revoke_oauth_grant(grant_id: str, uid: str = Depends(get_current_user_id)):
    try:
        revoked = mcp_oauth_db.revoke_user_grant(uid, grant_id)
    except mcp_token_cache_db.McpTokenStoreUnavailable as exc:
        # Revocation fails closed when the Redis marker cannot be written —
        # report a retryable 503, never a 204 for a revoke that did not stick.
        raise HTTPException(
            status_code=503, detail="OAuth token store unavailable", headers={"Retry-After": _REST_RETRY_AFTER}
        ) from exc
    if not revoked:
        raise HTTPException(status_code=404, detail="OAuth grant not found")
    return


@router.post("/v1/mcp/memories", tags=["mcp"], response_model=Memory)
def create_memory(
    memory: Memory,
    auth_context: ProductAuthorizationContext = Depends(
        with_rate_limit_context(get_mcp_memory_default_memory_write_context, "memories:create")
    ),
):
    # Fail closed: a legacy/read-only MCP key (no persisted memories.write grant)
    # must not mutate canonical memories.
    write_grant = authorize_memory_external_default_memory_write(auth_context, db_client=db)
    if not write_grant.allowed:
        raise HTTPException(
            status_code=write_grant.status_code,
            detail=write_grant.observability,
        )
    uid = auth_context.uid
    memory.category = identify_category_for_memory(memory.content)
    # Shared write core with the MCP memory tools; REST keeps its released
    # operation label. `upsert_vector` is wire-compat only — the canonical
    # write path deletes the flag, so this passes no extra behavior beyond
    # what the MCP tools' create_memory already performs.
    memory_db = mcp_memory_handlers._create_one_memory(
        uid,
        memory,
        operation="mcp_memory_create",
        upsert_vector=True,
    )
    postprocess_executor.submit(update_personas_async, uid)
    return memory_db


def _validate_mcp_memory(uid: str, memory_id: str) -> dict:
    return fetch_memory_dict(uid, memory_id, db_client=db)


@router.delete("/v1/mcp/memories/{memory_id}", tags=["mcp"], response_model=McpStatusResponse)
def delete_memory(
    memory_id: str,
    auth_context: ProductAuthorizationContext = Depends(get_mcp_memory_default_memory_write_context),
):
    # Fail closed: a legacy/read-only MCP key (no persisted memories.write grant)
    # must not mutate canonical memories.
    write_grant = authorize_memory_external_default_memory_write(auth_context, db_client=db)
    if not write_grant.allowed:
        raise HTTPException(
            status_code=write_grant.status_code,
            detail=write_grant.observability,
        )
    _call_tool_handler("delete_memory", auth_context.uid, {"memory_id": memory_id}, auth_context)
    return {"status": "ok"}


@router.patch("/v1/mcp/memories/{memory_id}", tags=["mcp"], response_model=McpStatusResponse)
def edit_memory(
    memory_id: str,
    value: str,
    auth_context: ProductAuthorizationContext = Depends(get_mcp_memory_default_memory_write_context),
):
    # Fail closed: a legacy/read-only MCP key (no persisted memories.write grant)
    # must not mutate canonical memories.
    write_grant = authorize_memory_external_default_memory_write(auth_context, db_client=db)
    if not write_grant.allowed:
        raise HTTPException(
            status_code=write_grant.status_code,
            detail=write_grant.observability,
        )
    uid = auth_context.uid
    _validate_mcp_memory(uid, memory_id)
    _call_tool_handler("edit_memory", uid, {"memory_id": memory_id, "content": value}, auth_context)
    return {"status": "ok"}


class UserProfile(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone_number: Optional[str] = None
    profile_text: Optional[str] = None
    generated_at: Optional[str] = None
    data_sources_used: Optional[int] = None


def _get_user_contact(uid: str) -> dict:
    """Best-effort name/email/phone for the profile. Never raises — a contact
    lookup failure must not break the profile response."""
    name = email = phone_number = None
    try:
        user = firebase_auth.get_user(uid)
        name = user.display_name or None
        email = user.email or None
        phone_number = user.phone_number or None
    except Exception as e:
        # Expected for uids with no Firebase Auth record; warn (no traceback).
        logger.warning("get_user_profile: firebase contact lookup failed uid=%s: %s", uid, e)
    if not phone_number:
        try:
            # get_phone_numbers returns decrypted dicts; prefer the primary one.
            numbers = phone_calls_db.get_phone_numbers(uid) or []
            primary = next((n for n in numbers if n.get("is_primary")), None) or (numbers[0] if numbers else None)
            if primary:
                phone_number = primary.get("phone_number")
        except Exception as e:
            logger.warning("get_user_profile: phone_numbers lookup failed uid=%s: %s", uid, e)
    return {"name": name, "email": email, "phone_number": phone_number}


@router.get("/v1/mcp/profile", tags=["mcp"], response_model=UserProfile)
def get_user_profile(uid: str = Depends(get_uid_from_mcp_api_key)):
    """Omi's cached high-level user profile, if one has been generated."""
    profile = users_db.get_ai_user_profile(uid) or {}
    generated_at = profile.get("generated_at")
    contact = _get_user_contact(uid)
    return UserProfile(
        name=contact["name"],
        email=contact["email"],
        phone_number=contact["phone_number"],
        profile_text=profile.get("profile_text"),
        generated_at=str(generated_at) if generated_at is not None else None,
        data_sources_used=profile.get("data_sources_used"),
    )


class CleanerMemory(BaseModel):
    id: str
    content: str
    category: MemoryCategory
    category_source: Optional[str] = None
    reviewed: Optional[bool] = None
    reviewed_source: Optional[str] = None
    manually_added: Optional[bool] = None
    manually_added_source: Optional[str] = None
    memory_default_memory: Optional[bool] = None
    archive_default_visible: Optional[bool] = None
    policy: Optional[dict] = None


class SearchedMemory(CleanerMemory):
    relevance_score: float


@router.get("/v1/mcp/memories/search", tags=["mcp"], response_model=List[SearchedMemory])
def search_memories(
    query: str,
    limit: int = 10,
    auth_context: ProductAuthorizationContext = Depends(get_mcp_memory_default_memory_read_context),
):
    app_key_grant = authorize_memory_external_default_memory_read(auth_context, db_client=db)
    if not app_key_grant.allowed:
        raise HTTPException(
            status_code=app_key_grant.status_code,
            detail=app_key_grant.observability,
        )

    uid = auth_context.uid
    logger.info(f"search_memories {uid} query={sanitize_pii(query)} limit={limit}")
    result = _call_tool_handler("search_memories", uid, {"query": query, "limit": limit}, auth_context)
    return result["memories"]


@router.get("/v1/mcp/memories", tags=["mcp"], response_model=List[CleanerMemory])
def get_memories(
    response: Response,
    auth_context: ProductAuthorizationContext = Depends(get_mcp_memory_default_memory_read_context),
    limit: int = 25,
    offset: int = 0,
    categories: Optional[str] = None,
    sort: str = "created_desc",
    reviewed: Optional[bool] = None,
    manually_added: Optional[bool] = None,
    updated_after: Optional[str] = None,
    updated_since: Optional[str] = None,
    include_activity: bool = False,
    include_sensitive: bool = True,
    cursor: Optional[str] = None,
):
    uid = auth_context.uid
    if _parse_updated_since(updated_since) is not None:
        # The mixed canonical+historical view cannot order on persisted
        # updated_at (legacy docs lack it), so a partial feed would silently
        # drop updates — a permanent capability gap, not a transient outage.
        _incremental_sync_unsupported(
            "memories",
            "page this endpoint without updated_since using sort, offset/limit, or the X-Next-Cursor cursor",
        )
    try:
        limit = parse_mcp_int(limit, "limit", default=25, minimum=1, maximum=500)
        offset = parse_mcp_int(offset, "offset", default=0, minimum=0, maximum=100000)
        reviewed = parse_optional_mcp_bool(reviewed, "reviewed")
        manually_added = parse_optional_mcp_bool(manually_added, "manually_added")
        include_activity = parse_mcp_bool(include_activity, "include_activity", default=False)
        include_sensitive = parse_mcp_bool(include_sensitive, "include_sensitive", default=True)
        parsed_updated_after = parse_mcp_datetime(updated_after, "updated_after")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if sort not in {"scoring_desc", "created_desc", "updated_desc", "manual_first"}:
        raise HTTPException(
            status_code=400,
            detail="Invalid sort. Expected one of: scoring_desc, created_desc, updated_desc, manual_first.",
        )
    category_list = []
    if categories:
        try:
            category_list = [MemoryCategory(c.strip()) for c in categories.split(",") if c.strip()]
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid category {str(e)}")

    app_key_grant = authorize_memory_external_default_memory_read(auth_context, db_client=db)
    if not app_key_grant.allowed:
        raise HTTPException(
            status_code=app_key_grant.status_code,
            detail=app_key_grant.observability,
        )

    try:
        result = mcp_memory_handlers.memories_page_core(
            uid,
            limit=limit,
            offset=offset,
            cursor_token=cursor,
            reviewed=reviewed,
            manually_added=manually_added,
            include_activity=include_activity,
            include_sensitive=include_sensitive,
            updated_after=parsed_updated_after,
            sort=sort,
            categories=[category.value for category in category_list],
            # The released REST list scanned up to 5000 raw rows through
            # collect_filtered_memories; keep that window instead of the
            # smaller MCP tool cap.
            max_scan=5000,
            cursor_kind="rest_get_memories",
        )
    except ToolExecutionError as e:
        raise _http_error_from_tool_error(e)
    _next_cursor_header(response, result.get("next_cursor"))
    if result.get("scan_truncated"):
        response.headers["X-Scan-Truncated"] = "true"
    return result["memories"]


class SimpleStructured(BaseModel):
    title: str
    overview: str
    category: CategoryEnum


class SimpleTranscriptSegment(BaseModel):
    id: Optional[str] = None
    text: str
    speaker_id: Optional[int] = None
    speaker_name: Optional[str] = None
    start: float
    end: float


class TranscriptMatchSnippet(BaseModel):
    """Grep-style transcript evidence for MCP search hits (#6621)."""

    text: str
    segment_id: Optional[str] = None
    start: Optional[float] = None
    end: Optional[float] = None
    start_ms: Optional[int] = None
    end_ms: Optional[int] = None
    speaker_id: Optional[int] = None


class SimpleConversation(BaseModel):
    id: str
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    structured: SimpleStructured
    language: Optional[str] = None
    apps_results: List[AppResult] = []
    match_snippets: List[TranscriptMatchSnippet] = []


class FullConversation(SimpleConversation):
    transcript_segments: List[SimpleTranscriptSegment] = []
    # Additive: true only when the bounded shared reader clipped the transcript.
    truncated: bool = False


# Step 2 do retrieval
# @router.get("/v1/mcp/conversations/available-filters", tags=["mcp"])
# def get_conversations_available_filters(uid: str = Header(None)):
#     return {
#         "people": get_filter_category_items(uid, "people"),
#         "topics": get_filter_category_items(uid, "topics"),
#         "entities": get_filter_category_items(uid, "entities"),
#     }


@router.get("/v1/mcp/conversations", response_model=List[SimpleConversation], tags=["mcp"])
def get_conversations(
    response: Response,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    categories: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    cursor: Optional[str] = None,
    updated_since: Optional[str] = None,
    uid: str = Depends(get_uid_from_mcp_api_key),
):
    logger.info(f"get_conversations {uid} {limit} {offset} {start_date} {end_date} {categories}")
    if _parse_updated_since(updated_since) is not None:
        # Generic writes do not persist a queryable updated_at on conversations,
        # so a revision-ordered feed would silently drop updates — a permanent
        # capability gap, not a transient outage.
        _incremental_sync_unsupported(
            "conversations",
            "page this endpoint with the opaque X-Next-Cursor cursor (created_at DESC, id keyset)",
        )
    # Clamp pagination so a negative value cannot reach Firestore .limit()/.offset() (which
    # raises -> HTTP 500) and an oversized value cannot stream/skip the whole collection.
    # Mirrors the sibling MCP tool (routers/mcp_sse.py get_conversations) and every other
    # paginated list endpoint in this file (get_action_items, get_chat_messages, etc.).
    limit = max(1, min(limit, 1000))
    offset = max(0, min(offset, 100000))
    try:
        category_list = (
            [CategoryEnum(c.strip()).value for c in categories.split(",") if c.strip()] if categories else []
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid category {str(e)}")

    try:
        page, next_cursor = mcp_conversation_handlers.conversation_cards_page_core(
            uid,
            limit=limit,
            offset=offset,
            cursor_token=cursor,
            start_dt=start_date,
            end_dt=end_date,
            categories=category_list,
            cursor_kind="rest_get_conversations",
            extra_field_paths=_REST_CONVERSATION_EXTRA_FIELD_PATHS,
        )
    except ToolExecutionError as e:
        raise _http_error_from_tool_error(e)
    _next_cursor_header(response, next_cursor)

    # Validate each record individually so one malformed conversation (e.g. a category
    # no longer in CategoryEnum) cannot 500 the whole page via response_model coercion.
    valid_conversations = []
    for conv in page:
        card = conversation_card(conv)
        card["apps_results"] = conv.get("apps_results") or []
        try:
            valid_conversations.append(SimpleConversation.model_validate(card))
        except Exception as e:  # noqa: BLE001 - one bad record must not 500 the page
            logger.warning(f"Skipping malformed conversation {conv.get('id', 'unknown')} in MCP list: {e}")
    return valid_conversations


@router.get("/v1/mcp/conversations/search", response_model=List[SimpleConversation], tags=["mcp"])
def search_conversations(
    query: str,
    limit: int = 10,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    uid: str = Depends(get_uid_from_mcp_api_key),
):
    logger.info(f"search_conversations {uid} query={sanitize_pii(query)} limit={limit}")

    start_dt = None
    end_dt = None
    if start_date:
        try:
            start_dt = parse_date_only_utc(start_date)
        except ValueError:
            raise HTTPException(
                status_code=400, detail=f"Invalid start_date format: '{start_date}'. Expected YYYY-MM-DD."
            )
    if end_date:
        try:
            end_dt = end_of_day_utc(parse_date_only_utc(end_date))
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid end_date format: '{end_date}'. Expected YYYY-MM-DD.")

    # Summary vectors miss transcript-only phrases; the shared resolver merges
    # transcript-chunk hits and returns lean docs (no photos) for shaping.
    try:
        conversations = mcp_conversation_handlers.search_conversations_core(
            uid,
            query,
            limit=limit,
            start_dt=start_dt,
            end_dt=end_dt,
            extra_field_paths=_REST_CONVERSATION_EXTRA_FIELD_PATHS,
        )
    except ToolExecutionError as e:
        raise _http_error_from_tool_error(e)
    if not conversations:
        return []

    # conversation_card() applies redact_conversation_for_list in place, so a
    # locked row reaches the snippet attacher already stripped of transcript.
    cards = [conversation_card(conv) for conv in conversations]
    # Snippets after redaction so locked list rows never leak transcript evidence (#6621).
    conversations = attach_match_snippets_to_conversations(conversations, query)
    for conv, card in zip(conversations, cards):
        card["apps_results"] = conv.get("apps_results") or []
        card["match_snippets"] = conv.get("match_snippets") or []
    valid = []
    for card in cards:
        try:
            valid.append(SimpleConversation.model_validate(card))
        except Exception as e:  # noqa: BLE001 - one malformed record must not 500 the page
            logger.warning(f"Skipping malformed conversation {card.get('id', 'unknown')} in MCP search: {e}")
    return valid


@router.get(
    "/v1/mcp/conversations/{conversation_id}",
    response_model=FullConversation,
    tags=["mcp"],
)
def get_conversation_by_id(
    conversation_id: str,
    uid: str = Depends(get_uid_from_mcp_api_key),
):
    logger.info(f"get_conversation_by_id {uid} {conversation_id}")
    if not mcp_conversation_handlers.is_safe_conversation_id(conversation_id):
        raise HTTPException(status_code=400, detail="conversation_id is not a valid document id")
    conversation = mcp_conversation_handlers.fetch_conversation_for_detail(
        uid,
        conversation_id,
        extra_field_paths=_REST_CONVERSATION_DETAIL_EXTRA_FIELD_PATHS,
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    if conversation.get('is_locked', False):
        raise HTTPException(status_code=402, detail="A paid plan is required to access this conversation.")

    populate_speaker_names(uid, [conversation])

    # The shared bounded reader keeps released clients' full-transcript reads
    # (4096 segments / 500k chars) while flagging clipped output.
    transcript_segments, truncated = bounded_transcript_segments(
        conversation.get("transcript_segments"),
        max_segments=MCP_REST_CONVERSATION_MAX_SEGMENTS,
        max_chars=MCP_REST_CONVERSATION_MAX_CHARS,
        extra_keys=("speaker_name",),
    )
    payload = conversation_card(conversation)
    payload["apps_results"] = conversation.get("apps_results") or []
    payload["transcript_segments"] = transcript_segments
    payload["truncated"] = truncated

    # A legacy/poisoned record (e.g. a structured.category no longer in CategoryEnum)
    # must not 500 this single-item fetch via response_model coercion — mirror the
    # per-record guard already used by the list/search siblings above.
    try:
        return FullConversation.model_validate(payload)
    except Exception as e:  # noqa: BLE001 - malformed legacy record must not 500
        logger.warning(f"Conversation {conversation_id} failed MCP response validation: {e}")
        raise HTTPException(status_code=404, detail="Conversation not found")


# ---------------------------------------------------------------------------
# Action items — the user's actionable task layer (to-dos with due dates)
# ---------------------------------------------------------------------------


class SimpleActionItem(BaseModel):
    id: str
    description: str
    completed: bool = False
    created_at: Optional[datetime] = None
    due_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    conversation_id: Optional[str] = None
    # Additive for the updated_since sync feed: the persisted revision
    # watermark, and a soft tombstone flag present only on rows that actually
    # carry deleted:true (hard deletes leave no row and are not reported).
    updated_at: Optional[datetime] = None
    deleted: Optional[bool] = None


@router.get("/v1/mcp/action-items", response_model=List[SimpleActionItem], tags=["mcp"])
def get_action_items(
    response: Response,
    completed: Optional[bool] = None,
    due_start_date: Optional[datetime] = None,
    due_end_date: Optional[datetime] = None,
    limit: int = 100,
    offset: int = 0,
    cursor: Optional[str] = None,
    updated_since: Optional[str] = None,
    uid: str = Depends(get_uid_from_mcp_api_key),
):
    logger.info(f"get_action_items {uid} completed={completed} limit={limit} offset={offset}")
    limit = max(1, min(limit, 500))
    offset = max(0, offset)

    if updated_since is not None:
        sync_since = _parse_updated_since(updated_since)
        if completed is not None or due_start_date is not None or due_end_date is not None:
            raise HTTPException(
                status_code=400,
                detail="completed/due-date filters are not supported with updated_since.",
            )
        if offset != 0:
            raise HTTPException(status_code=400, detail="offset is not supported with updated_since; use cursor.")
        try:
            items, next_cursor = mcp_action_item_handlers.action_items_sync_page_core(
                uid,
                updated_since=sync_since,
                limit=limit,
                cursor_token=cursor,
                cursor_kind="rest_get_action_items",
            )
        except ToolExecutionError as e:
            raise _http_error_from_tool_error(e)
        _next_cursor_header(response, next_cursor)
        return items

    try:
        items, next_cursor = mcp_action_item_handlers.action_items_list_page_core(
            uid,
            completed=completed,
            due_start=due_start_date,
            due_end=due_end_date,
            limit=limit,
            offset=offset,
            cursor_token=cursor,
            cursor_kind="rest_get_action_items",
        )
    except ToolExecutionError as e:
        raise _http_error_from_tool_error(e)
    _next_cursor_header(response, next_cursor)
    return items


class McpCreateActionItem(BaseModel):
    description: str
    due_at: Optional[datetime] = None
    completed: bool = False


class McpUpdateActionItem(BaseModel):
    description: Optional[str] = None
    due_at: Optional[datetime] = None


def _action_item_http_error(exc: ToolExecutionError) -> HTTPException:
    """Map a shared action-item handler error to the released REST statuses."""
    if exc.http_status is not None:
        status_code = exc.http_status
    elif exc.analytics_authorization_denied:
        status_code = 403
    elif exc.analytics_rate_limited:
        status_code = 429
    else:
        status_code = {
            -32602: 422,
            -32000: 422,
            -32001: 404,
            -32002: 402,
            # -32009 is the "temporarily unavailable" domain code (index still
            # building, store outage) — it maps to a retryable 503, not a 500.
            -32009: 503,
        }.get(exc.code, 500)
    headers = {"Retry-After": _REST_RETRY_AFTER} if status_code in (429, 503) else None
    return HTTPException(status_code=status_code, detail=exc.message, headers=headers)


def _call_action_item_handler(tool_name: str, uid: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    spec = spec_for_tool(tool_name)
    assert spec is not None
    try:
        return spec.handler(uid, arguments, None)
    except ToolExecutionError as e:
        raise _action_item_http_error(e)


@router.get("/v1/mcp/action-items/search", response_model=List[SimpleActionItem], tags=["mcp"])
def search_action_items(
    query: str,
    limit: int = 10,
    uid: str = Depends(get_uid_from_mcp_api_key),
):
    logger.info(f"search_action_items {uid} limit={limit}")
    result = _call_action_item_handler("search_action_items", uid, {"query": query, "limit": limit})
    return result["action_items"]


@router.post("/v1/mcp/action-items", response_model=SimpleActionItem, tags=["mcp"])
def create_action_item(
    body: McpCreateActionItem,
    uid: str = Depends(with_rate_limit(get_uid_from_mcp_api_key, "action_items:write")),
):
    logger.info(f"create_action_item {uid} completed={body.completed} has_due={body.due_at is not None}")
    result = _call_action_item_handler(
        "create_action_item",
        uid,
        {"description": body.description, "due_at": body.due_at, "completed": body.completed},
    )
    return result["action_item"]


@router.post("/v1/mcp/action-items/{action_item_id}/complete", response_model=SimpleActionItem, tags=["mcp"])
def complete_action_item(
    action_item_id: str,
    completed: bool = True,
    uid: str = Depends(with_rate_limit(get_uid_from_mcp_api_key, "action_items:write")),
):
    logger.info(f"complete_action_item {uid} id={action_item_id} completed={completed}")
    result = _call_action_item_handler(
        "complete_action_item", uid, {"action_item_id": action_item_id, "completed": completed}
    )
    return result["action_item"]


@router.patch("/v1/mcp/action-items/{action_item_id}", response_model=SimpleActionItem, tags=["mcp"])
def update_action_item(
    action_item_id: str,
    body: McpUpdateActionItem,
    uid: str = Depends(with_rate_limit(get_uid_from_mcp_api_key, "action_items:write")),
):
    logger.info(f"update_action_item {uid} id={action_item_id}")
    result = _call_action_item_handler(
        "update_action_item",
        uid,
        {"action_item_id": action_item_id, "description": body.description, "due_at": body.due_at},
    )
    return result["action_item"]


@router.delete("/v1/mcp/action-items/{action_item_id}", tags=["mcp"], response_model=McpStatusResponse)
def delete_action_item(
    action_item_id: str,
    uid: str = Depends(with_rate_limit(get_uid_from_mcp_api_key, "action_items:write")),
):
    logger.info(f"delete_action_item {uid} id={action_item_id}")
    _call_action_item_handler("delete_action_item", uid, {"action_item_id": action_item_id})
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Goals — the user's stated objectives
# ---------------------------------------------------------------------------


@router.get("/v1/mcp/goals", tags=["mcp"], response_model=List[Dict[str, Any]])
def get_goals(
    include_inactive: bool = False,
    uid: str = Depends(get_uid_from_mcp_api_key),
):
    logger.info(f"get_goals {uid} include_inactive={include_inactive}")
    # Shared with the hosted MCP tool of the same name; the REST response is
    # the unwrapped list while the tool wraps it in {"goals": [...]}.
    spec = spec_for_tool("get_goals")
    assert spec is not None
    return spec.handler(uid, {"include_inactive": include_inactive}, None)["goals"]


# ---------------------------------------------------------------------------
# Chat — the user's prior conversations with Omi (intent / preferences signal)
# ---------------------------------------------------------------------------


class SimpleChatMessage(BaseModel):
    id: str
    text: str
    sender: str
    type: Optional[str] = None
    created_at: Optional[datetime] = None


@router.get("/v1/mcp/chat", response_model=List[SimpleChatMessage], tags=["mcp"])
def get_chat_messages(
    response: Response,
    limit: int = 50,
    offset: int = 0,
    cursor: Optional[str] = None,
    uid: str = Depends(get_uid_from_mcp_api_key),
):
    logger.info(f"get_chat_messages {uid} limit={limit} offset={offset}")
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    result = _call_tool_handler(
        "get_chat_messages",
        uid,
        {"limit": limit, "offset": offset, "cursor": cursor},
    )
    _next_cursor_header(response, result.get("next_cursor"))
    return result["messages"]


# ---------------------------------------------------------------------------
# People — the contacts/speakers the user interacts with
# ---------------------------------------------------------------------------


class SimplePerson(BaseModel):
    id: str
    name: str
    created_at: Optional[datetime] = None
    speech_sample_transcripts: List[str] = []


@router.get("/v1/mcp/people", response_model=List[SimplePerson], tags=["mcp"])
def get_people(uid: str = Depends(get_uid_from_mcp_api_key)):
    logger.info(f"get_people {uid}")
    # Shared with the hosted MCP tool of the same name; identical privacy
    # cleaning via utils.mcp_data.clean_person, unwrapped to the REST list.
    spec = spec_for_tool("get_people")
    assert spec is not None
    return spec.handler(uid, {}, None)["people"]


# ---------------------------------------------------------------------------
# Screen activity — desktop Rewind (app, window title, OCR text)
# ---------------------------------------------------------------------------


@router.get(
    "/v1/mcp/screen-activity",
    tags=["mcp"],
    response_model=Union[List[McpScreenActivityRow], McpScreenActivitySummaryResponse],
)
def get_screen_activity(
    response: Response,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    app: Optional[str] = None,
    summary: bool = False,
    limit: int = 200,
    cursor: Optional[str] = None,
    uid: str = Depends(get_uid_from_mcp_api_key),
):
    logger.info(f"get_screen_activity {uid} summary={summary} app={app} limit={limit}")
    limit = max(1, min(limit, 200))
    try:
        result = mcp_other_handlers.screen_activity_core(
            uid,
            start=start_date,
            end=end_date,
            app=app,
            summary=summary,
            group_by="none",
            limit=limit,
            cursor_token=cursor,
            cursor_kind="rest_get_screen_activity",
        )
    except ToolExecutionError as e:
        raise _http_error_from_tool_error(e)
    _next_cursor_header(response, result.get("next_cursor"))
    if summary:
        return result
    return result["screen_activity"]


# ---------------------------------------------------------------------------
# Daily summaries — Omi's per-day digest of the user's life
# ---------------------------------------------------------------------------


@router.get("/v1/mcp/daily-summaries", tags=["mcp"], response_model=List[Dict[str, Any]])
def get_daily_summaries(
    response: Response,
    limit: int = 30,
    offset: int = 0,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    cursor: Optional[str] = None,
    uid: str = Depends(get_uid_from_mcp_api_key),
):
    logger.info(f"get_daily_summaries {uid} limit={limit} offset={offset}")
    limit = max(1, min(limit, 100))
    offset = max(0, offset)
    result = _call_tool_handler(
        "get_daily_summaries",
        uid,
        {
            "limit": limit,
            "offset": offset,
            "start_date": start_date,
            "end_date": end_date,
            "cursor": cursor,
        },
    )
    _next_cursor_header(response, result.get("next_cursor"))
    return result["daily_summaries"]
