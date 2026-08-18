import logging
import uuid
from typing import Any, Callable, Dict, List, Literal, Optional, cast

import database._client as db_client_module
from utils.executors import db_executor, llm_executor, postprocess_executor, run_blocking, submit_with_context

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from database.memory_imports import ingest_memory_import_batch
from database import review_queue
from models.memories import MemoryDB, Memory, MemoryCategory
from models.memory_imports import MemoryImportBatchRequest, MemoryImportBatchResponse
from utils.apps import update_personas_async
from utils.memory.memory_service import (
    MEMORY_LIST_SCAN_BUDGET_DETAIL,
    MemoryPayload,
    MemoryService,
    fetch_memory_dict,
)
from testing.parity_pack_v0.live_capture import SurfaceParityCapture
from utils.memory.import_write_guard import (
    import_write_block_mode,
    import_write_violation_for_guard,
    is_per_file_local_import_tags,
)
from utils.memory.memory_api_contract import MemoryApiExposure
from utils.memory.memory_api_response import memory_item_response, memory_list_response
from utils.memory.memory_system import MemorySystem
from utils.client_device import DeviceScopeRequest, DeviceScopeValidationError, resolve_client_device_from_request
from utils.memory.device_scope_filter import device_scope_validation_error
from utils.other import endpoints as auth

logger = logging.getLogger(__name__)

router = APIRouter()
_auth_module = cast(Any, auth)


class MemoryMutationResponse(BaseModel):
    status: str


class MemoryValueRequest(BaseModel):
    """Canonical body for single-value memory mutations."""

    model_config = {"extra": "forbid"}

    value: str


class MemoryReadStatusRequest(BaseModel):
    """Durable UI read/dismiss mutation for a single memory."""

    model_config = {"extra": "forbid"}

    is_read: Optional[bool] = None
    is_dismissed: Optional[bool] = None


class ReviewResolutionResponse(BaseModel):
    model_config = {"extra": "allow"}

    status: str


# Hard cap on memories per batch request. Keep aligned with the corresponding
# Pydantic max_length validator below and with the Swift client chunker.
MEMORIES_BATCH_MAX = 100
# The released API contract accepts 100 IDs. Canonical deletion atomically
# fences each item and journals durable projection deletes; derived graph
# assertions are removed by the retryable outbox after reads fail closed.
MEMORIES_BATCH_DELETE_MAX = 100

_MEMORY_CANONICAL_LIFECYCLE_EXPOSED_HEADER = 'X-Omi-Memory-Canonical-Lifecycle-Exposed'
_MEMORY_DEVICE_SCOPE_SUPPORTED_HEADER = 'X-Omi-Memory-Device-Scope-Supported'
_MEMORY_DEFAULT_DELETE_SUPPORTED_HEADER = 'X-Omi-Memory-Default-Delete-Supported'
_MEMORY_NEXT_CURSOR_HEADER = 'X-Omi-Memory-Next-Cursor'


def _normalize_memory_list_cursor(cursor: Optional[str]) -> Optional[str]:
    """Treat missing/blank cursor as first-page so ``?cursor=`` cannot skip the fallback."""
    if cursor is None:
        return None
    stripped = cursor.strip()
    return stripped or None


class BatchMemoriesRequest(BaseModel):
    memories: List[Memory] = Field(
        description="List of memories to create in a single batch request",
        max_length=MEMORIES_BATCH_MAX,
    )


class BatchMemoriesResponse(BaseModel):
    memories: List[MemoryDB]
    created_count: int


class BatchDeleteMemoriesRequest(BaseModel):
    memory_ids: List[str] = Field(
        description="Memory IDs to delete in a single batch request",
        max_length=MEMORIES_BATCH_DELETE_MAX,
    )


def _parity_memory_payload(memories: List[MemoryDB]) -> list[dict[str, Any]]:
    """Small, redaction-ready accepted-memory view for restricted dev cassettes."""
    return [
        {
            "id": memory.id,
            "content": (memory.content or "")[:8192],
            "category": memory.category.value,
            "visibility": memory.visibility,
            "source_type": memory.evidence[0].source_type if memory.evidence else "unknown",
        }
        for memory in memories[:100]
    ]


def _start_memory_parity_capture(
    uid: str, *, source: str, session_id: str, memories: List[MemoryDB]
) -> SurfaceParityCapture:
    capture = SurfaceParityCapture.from_environ(
        principal_id=uid,
        session_id=session_id,
        surface="memory_write",
        source=source,
        provider_lane="memory",
        route_or_model="memory-write",
        request={"memory_count": len(memories), "source": source},
    )
    capture.observe("client", {"type": "memory_write_request", "memories": _parity_memory_payload(memories)})
    return capture


def _finish_memory_parity_capture(capture: SurfaceParityCapture, memories: List[MemoryDB]) -> None:
    capture.observe("inbound", {"type": "accepted_memories", "memories": _parity_memory_payload(memories)})
    capture.persist()


class ReviewResolutionRequest(BaseModel):
    decision: str = Field(description="accept, reject, correct, or timeout")
    correction: Optional[Dict[str, Any]] = None
    reason: str = ''
    current_veracity: Optional[float] = None


async def _guard_import_memory_write(request: Request, *, endpoint: str, uid: str) -> None:
    mode = import_write_block_mode()
    if mode == "off":
        return
    try:
        raw: object = await request.json()
    except Exception:
        return
    payloads: List[object]
    if isinstance(raw, dict):
        raw_payload = cast(Dict[str, Any], raw).get("memories")
        payloads = cast(List[object], raw_payload) if isinstance(raw_payload, list) else [raw]
    else:
        payloads = [raw]
    for payload in payloads:
        if not isinstance(payload, dict):
            continue
        # Per-file local-file items are exempt: the endpoints below
        # acknowledge-and-drop them without persisting, and a 409 here
        # (enforce mode) would fail an old desktop build's whole batch
        # before that drop can happen.
        violation = import_write_violation_for_guard(payload)  # type: ignore[reportUnknownArgumentType]  # payload narrowed from List[object] via isinstance
        if not violation:
            continue
        logger.warning(
            "memory_import.direct_memory_write_blocked endpoint=%s uid=%s mode=%s violation=%s",
            endpoint,
            uid,
            mode,
            violation,
        )
        if mode == "enforce":
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "import_must_use_evidence_ingress",
                    "use_endpoint": "/v3/memory-imports/batch",
                },
            )
        return


def _memory_response(memory: MemoryDB) -> JSONResponse:
    """Serialize the universal memory contract for released clients."""
    return memory_item_response(memory, MemoryApiExposure.CANONICAL)


def _resolve_get_memories_device_scope(
    device_scope: str,
    client_device_id: Optional[str],
    *,
    x_app_platform: Optional[str],
    x_device_id_hash: Optional[str],
) -> DeviceScopeRequest:
    try:
        return DeviceScopeRequest.resolve_from_headers(
            device_scope=device_scope,
            client_device_id=client_device_id,
            x_app_platform=x_app_platform,
            x_device_id_hash=x_device_id_hash,
        )
    except DeviceScopeValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _validate_device_scope_request(device_scope: str, resolved_device_id: Optional[str]) -> None:
    """Fail closed at the HTTP boundary when scoped filtering lacks a device id.

    Agents and API clients get an explicit 400 (not silent unfiltered data) so they
    can supply X-App-Platform / X-Device-Id-Hash or client_device_id as needed.
    """
    detail = device_scope_validation_error(device_scope, resolved_device_id)  # type: ignore[arg-type]
    if detail:
        raise HTTPException(status_code=400, detail=detail)


def _set_device_scope_capability_header(http_response: Response, *, supported: bool) -> None:
    http_response.headers[_MEMORY_DEVICE_SCOPE_SUPPORTED_HEADER] = 'true' if supported else 'false'


def _set_canonical_lifecycle_exposure_header(http_response: Response, *, exposed: bool) -> None:
    http_response.headers[_MEMORY_CANONICAL_LIFECYCLE_EXPOSED_HEADER] = 'true' if exposed else 'false'


def _set_default_delete_capability_header(http_response: Response, *, supported: bool) -> None:
    http_response.headers[_MEMORY_DEFAULT_DELETE_SUPPORTED_HEADER] = 'true' if supported else 'false'


def _validate_mutable_memory(uid: str, memory_id: str, *, db_client: Any) -> MemoryPayload:
    return fetch_memory_dict(uid, memory_id, db_client=db_client)


# Matches the helper's own truncation budget so a caller cannot send text whose tail
# the extractor would silently drop.
MAX_EXTRACT_TEXT_CHARS = 40_000
MAX_EXISTING_MEMORY_CHARS = 1_000


class ExtractMemoryLogRequest(BaseModel):
    model_config = {"extra": "forbid"}

    text: str = Field(..., min_length=1, max_length=MAX_EXTRACT_TEXT_CHARS)
    text_source: str = Field(default="memory_log", min_length=1, max_length=64)
    existing_memories: List[str] = Field(default_factory=list, max_length=200)


class ExtractMemoryLogResponse(BaseModel):
    model_config = {"extra": "forbid"}

    memories: List[str]
    profile: str = ""


@router.post('/v1/memories/extract', tags=['memories'], response_model=ExtractMemoryLogResponse)
async def extract_memory_log(
    body: ExtractMemoryLogRequest,
    uid: str = Depends(
        cast(Callable[..., str], _auth_module.with_rate_limit(auth.get_current_user_uid, "memories:extract"))
    ),
):
    """Return-only memory-log extraction through the managed memories feature (OpenRouter Luna).

    Does not write Firestore. Desktop onboarding/import should call this instead of inventing
    memories via Anthropic Haiku chat completions, then persist via the normal memory write APIs.
    """
    # Deferred with the LLM helper: this router is covered by a module-isolation test
    # that stubs a minimal dependency graph, and utils.subscription pulls database.users
    # in at import time.
    from utils.llm import memories as memories_llm
    from utils.subscription import is_trial_paywalled

    if await run_blocking(db_executor, is_trial_paywalled, uid, 'desktop'):
        raise HTTPException(status_code=402, detail='trial_expired')
    source = (body.text_source or "memory_log").strip() or "memory_log"
    existing = [m.strip()[:MAX_EXISTING_MEMORY_CHARS] for m in body.existing_memories if m.strip()][:200]
    extraction = await run_blocking(
        llm_executor,
        lambda: memories_llm.extract_memory_log_from_text(
            uid,
            body.text,
            text_source=source,
            existing_memories=existing,
        ),
    )
    if extraction is None:
        raise HTTPException(status_code=502, detail="memories_extract_failed")
    return ExtractMemoryLogResponse(memories=list(extraction.memories), profile=extraction.profile or "")


@router.post('/v3/memories', tags=['memories'], response_model=MemoryDB)
async def create_memory(
    request: Request,
    memory: Memory,
    uid: str = Depends(
        cast(Callable[..., str], _auth_module.with_rate_limit(auth.get_current_user_uid, "memories:create"))
    ),
):
    await _guard_import_memory_write(request, endpoint="/v3/memories", uid=uid)
    # Honor the client-supplied category (the Memory model defaults it to
    # `interesting`). Only memories the user explicitly typed in arrive as
    # `manual`; auto-extracted ones (system/interesting) keep their category so
    # the mobile app files them under "About You"/"Insights" instead of dumping
    # everything into "Manual". manually_added tracks human entry, so derive it
    # from the category rather than forcing it True for every API caller.
    manually_added = memory.category == MemoryCategory.manual
    device_context = resolve_client_device_from_request(request)
    memory_db = MemoryDB.from_memory(
        memory,
        uid,
        None,
        manually_added,
        source_type="manual" if manually_added else "api",
        source_signal="manual" if manually_added else "api",
        extractor_id="manual_memory_submission" if manually_added else "external_memory_submission",
        client_device_id=device_context.client_device_id,
    )

    # Old desktop builds fan out one create per indexed local file during
    # onboarding (up to 2800 path facts). Acknowledge without persisting:
    # a 4xx would make those clients surface/retry a failure for traffic we
    # simply do not want stored.
    if is_per_file_local_import_tags(memory.tags):
        logger.info("memory_import.per_file_item_dropped endpoint=/v3/memories uid=%s", uid)
        return _memory_response(memory_db)

    parity_capture = _start_memory_parity_capture(
        uid,
        source="v3_memory_create",
        session_id=memory_db.id,
        memories=[memory_db],
    )
    try:
        created = await run_blocking(
            db_executor,
            MemoryService(db_client=getattr(db_client_module, 'db', None)).create_external_memory,
            uid,
            memory_db,
            memory_system=MemorySystem.CANONICAL,
            consumer="v3_manual" if manually_added else "v3_api",
            operation="create_memory",
            upsert_vector=False,
            require_canonical_promotion=True,
        )
    except Exception:
        logger.exception("MemoryService create_memory failed uid=%s", uid)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    _finish_memory_parity_capture(parity_capture, [created])
    return created


@router.post(
    "/v3/memories/batch",
    tags=["memories"],
    response_model=BatchMemoriesResponse,
)
async def create_memories_batch(
    request_context: Request,
    request: BatchMemoriesRequest,
    uid: str = Depends(
        cast(
            Callable[..., str],
            _auth_module.with_rate_limit(auth.get_current_user_uid, "memories:batch"),
        )
    ),
):
    await _guard_import_memory_write(request_context, endpoint="/v3/memories/batch", uid=uid)
    """
    Create many memories in a single request.

    Solves the Cloud Armor throttling seen on onboarding: the desktop client
    used to fan out one `POST /v3/memories` per local-file memory (up to 2800
    per user), blowing through the 120 req/min per-Authorization Cloud Armor
    rule and collaterally 429-ing unrelated calls (goals, sync, chat).

    One HTTP request delegates the canonical batch write to MemoryService. The
    canonical outbox owns vector projection; this route never writes Pinecone.
    """
    if not request.memories:
        return BatchMemoriesResponse(memories=[], created_count=0)

    # Drop per-file local-file import items (one memory per indexed file, up
    # to 2800 per onboarding scan) regardless of block mode: they buried real
    # memories for every user who ran the scan and old desktop builds in the
    # wild still send them. Aggregate local_files facts pass through.
    accepted_memories = [m for m in request.memories if not is_per_file_local_import_tags(m.tags)]
    dropped_count = len(request.memories) - len(accepted_memories)
    if dropped_count:
        logger.info(
            "memory_import.per_file_items_dropped endpoint=/v3/memories/batch uid=%s dropped=%d kept=%d",
            uid,
            dropped_count,
            len(accepted_memories),
        )
    if not accepted_memories:
        return BatchMemoriesResponse(memories=[], created_count=0)

    # Honor each item's category (defaults to `interesting` per the Memory
    # model). Desktop import/extraction paths send `system`/`interesting` so
    # they land under "About You"/"Insights"; only user-typed memories send
    # `manual`. Derive manually_added from the category instead of forcing it.
    memory_dbs: List[MemoryDB] = []
    has_public = False
    device_context = resolve_client_device_from_request(request_context)
    for memory in accepted_memories:
        manually_added = memory.category == MemoryCategory.manual
        memory_db = MemoryDB.from_memory(
            memory,
            uid,
            None,
            manually_added,
            source_type="manual" if manually_added else "api",
            source_signal="manual" if manually_added else "api",
            extractor_id="manual_memory_submission" if manually_added else "external_memory_submission",
            client_device_id=device_context.client_device_id,
        )
        memory_dbs.append(memory_db)
        if memory.visibility == "public":
            has_public = True

    parity_capture = _start_memory_parity_capture(
        uid,
        source="v3_memory_batch_create",
        session_id=str(uuid.uuid4()),
        memories=memory_dbs,
    )

    try:
        server_memories = await run_blocking(
            db_executor,
            MemoryService(db_client=getattr(db_client_module, "db", None)).create_external_memory_batch,
            uid,
            memory_dbs,
            memory_system=MemorySystem.CANONICAL,
            consumer="v3_batch",
            operation="batch_create_memory",
            upsert_vectors=False,
            require_canonical_promotion=True,
        )
    except Exception:
        logger.exception("MemoryService create_memories_batch failed uid=%s count=%s", uid, len(memory_dbs))
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    if has_public:
        submit_with_context(postprocess_executor, update_personas_async, uid)
    _finish_memory_parity_capture(parity_capture, server_memories)
    return BatchMemoriesResponse(memories=server_memories, created_count=len(server_memories))


@router.post(
    '/v3/memory-imports/batch',
    tags=['memories'],
    response_model=MemoryImportBatchResponse,
)
async def create_memory_import_batch(
    request: MemoryImportBatchRequest,
    uid: str = Depends(
        cast(Callable[..., str], _auth_module.with_rate_limit(auth.get_current_user_uid, "memory_imports:batch"))
    ),
):
    """
    Ingest imported source artifacts without creating product memories.

    Importers produce durable evidence. Candidate extraction, acceptance,
    promotion, vector sync, keyword sync, and KG extraction are backend-owned
    later stages.
    """
    db_client = getattr(db_client_module, 'db', None)
    if db_client is None:
        logger.error("memory import ingest unavailable: firestore client missing uid=%s", uid)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    parity_capture = SurfaceParityCapture.from_environ(
        principal_id=uid,
        session_id=str(uuid.uuid4()),
        surface="memory_import",
        source="v3_memory_import_batch",
        provider_lane="memory",
        route_or_model="memory-import",
        request={"source_type": request.source_type, "item_count": len(request.items)},
    )
    parity_capture.observe(
        "client",
        {
            "type": "memory_import_artifacts",
            "items": [
                {
                    "title": (item.title or "")[:2048],
                    "snippet": (item.snippet or "")[:4096],
                    "content": (item.content or "")[:8192],
                }
                for item in request.items[:100]
            ],
        },
    )
    try:
        result = await run_blocking(db_executor, ingest_memory_import_batch, uid, request, db_client=db_client)
    except Exception:
        logger.exception("Memory import ingest failed uid=%s source_type=%s", uid, request.source_type)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")
    parity_capture.observe("inbound", {"type": "memory_import_result", **result.response.model_dump(mode="json")})
    parity_capture.persist()
    return result.response


@router.get('/v3/memories', tags=['memories'], response_model=List[MemoryDB])
def get_memories(
    response: Response,
    limit: int = 100,
    offset: int = 0,
    cursor: Optional[str] = None,
    include_archive: bool = Query(
        False,
        description="When true, include Archive-tier memories that are otherwise excluded from default reads.",
    ),
    device_scope: str = Query('all'),
    client_device_id: Optional[str] = Query(None),
    uid: str = Depends(auth.get_current_user_uid),
    x_app_platform: str = Header(None, alias='X-App-Platform'),
    x_device_id_hash: str = Header(None, alias='X-Device-Id-Hash'),
):
    scope_request = _resolve_get_memories_device_scope(
        device_scope,
        client_device_id,
        x_app_platform=x_app_platform,
        x_device_id_hash=x_device_id_hash,
    )
    _validate_device_scope_request(scope_request.device_scope, scope_request.client_device_id)
    _set_device_scope_capability_header(response, supported=True)
    _set_canonical_lifecycle_exposure_header(response, exposed=True)
    _set_default_delete_capability_header(response, supported=True)
    db_client = getattr(db_client_module, 'db', None)
    bounded_limit = max(1, min(limit, 500))
    bounded_offset = max(0, offset)

    response_headers = {
        _MEMORY_DEVICE_SCOPE_SUPPORTED_HEADER: 'true',
        _MEMORY_CANONICAL_LIFECYCLE_EXPOSED_HEADER: 'true',
        _MEMORY_DEFAULT_DELETE_SUPPORTED_HEADER: 'true',
        'Cache-Control': 'no-store',
    }

    # Cursor and legacy offset paging are mutually exclusive. Cursor mode owns
    # accounts beyond the bounded offset compatibility window.
    cursor = _normalize_memory_list_cursor(cursor)
    if cursor is not None and bounded_offset != 0:
        raise HTTPException(
            status_code=400,
            detail="Memory cursor pagination cannot be combined with offset",
        )

    if cursor is not None:
        page = MemoryService(db_client=db_client).read_page(
            uid,
            limit=bounded_limit,
            cursor=cursor,
            device_scope_request=scope_request,
            include_pending_processing=True,
            include_archive=include_archive,
        )
        if page.next_cursor:
            response_headers[_MEMORY_NEXT_CURSOR_HEADER] = page.next_cursor
        return memory_list_response(
            page.memories,
            MemoryApiExposure.CANONICAL,
            headers=response_headers,
        )

    if bounded_offset == 0:
        # Prefer the composite cursor on the first page so sync/export can continue
        # past the legacy 5000 offset window without a second request shape.
        try:
            page = MemoryService(db_client=db_client).read_page(
                uid,
                limit=bounded_limit,
                cursor=None,
                device_scope_request=scope_request,
                include_pending_processing=True,
                include_archive=include_archive,
            )
        except HTTPException as exc:
            # First page must succeed whenever the legacy offset read can serve
            # it. The cursor path 503s on a missing cursor secret
            # ("Memory cursor unavailable"); the canonical keyset scan wraps any
            # underlying failure as "Canonical memory unavailable"; the
            # historical keyset scan wraps its own as "Historical memory
            # unavailable". The keyset scans order by (updated_at DESC,
            # __name__) and so fail while that composite index is building,
            # which the offset read's single-field order does not — so all three
            # fall back to read(). The keyset scans also walk past every row they
            # must not emit before they can fill the page, so an account whose
            # historical set is fully suppressed by canonical exhausts the scan
            # row budget ("Memory scan budget exceeded") — that walk is what took
            # the first page past the 30s edge timeout in prod on 2026-08-18, and
            # the offset read serves it without the walk.
            # Unrelated errors (4xx, other 503s) propagate.
            if exc.status_code != 503 or exc.detail not in (
                "Memory cursor unavailable",
                "Canonical memory unavailable",
                "Historical memory unavailable",
                MEMORY_LIST_SCAN_BUDGET_DETAIL,
            ):
                raise
        else:
            if page.next_cursor:
                response_headers[_MEMORY_NEXT_CURSOR_HEADER] = page.next_cursor
            return memory_list_response(
                page.memories,
                MemoryApiExposure.CANONICAL,
                headers=response_headers,
            )

    memories = MemoryService(db_client=db_client).read(
        uid,
        limit=bounded_limit,
        offset=bounded_offset,
        device_scope_request=scope_request,
        include_pending_processing=True,
        include_archive=include_archive,
    )
    return memory_list_response(
        memories,
        MemoryApiExposure.CANONICAL,
        headers=response_headers,
    )


@router.get('/v3/memories/review-queue', tags=['memories'], response_model=List[Dict[str, Any]])
def list_memory_review_queue(
    status: str = Query('pending'),
    limit: int = Query(100, ge=1, le=500),
    uid: str = Depends(
        cast(Callable[..., str], _auth_module.with_rate_limit(auth.get_current_user_uid, "memories:review"))
    ),
):
    return review_queue.list_review_conflicts(uid, status=status, limit=limit)


class MemoryReviewItemResponse(BaseModel):
    model_config = {"extra": "allow"}

    review_id: str
    status: str = 'pending'


@router.get('/v3/memories/review-queue/{review_id}', response_model=MemoryReviewItemResponse, tags=['memories'])
def get_memory_review_item(
    review_id: str,
    uid: str = Depends(auth.with_rate_limit(auth.get_current_user_uid, "memories:review")),
):
    """Fetch a single memory review conflict by id.

    The list endpoint only returns conflicts in the 'pending' status, so once a conflict is
    resolved it can no longer be retrieved. This fetches any of the user's review conflicts
    by id regardless of status, returning 404 if it does not exist.
    """
    conflict = review_queue.get_review_conflict(uid, review_id)
    if conflict is None:
        raise HTTPException(status_code=404, detail='Review item not found')
    return conflict


@router.post(
    '/v3/memories/review-queue/{review_id}/resolve',
    tags=['memories'],
    response_model=ReviewResolutionResponse,
)
def resolve_memory_review_item(
    review_id: str,
    request: ReviewResolutionRequest,
    uid: str = Depends(
        cast(Callable[..., str], _auth_module.with_rate_limit(auth.get_current_user_uid, "memories:review"))
    ),
):
    if request.decision not in ('accept', 'reject', 'correct', 'timeout'):
        raise HTTPException(status_code=400, detail='Invalid review decision')
    result = review_queue.resolve_review_conflict(
        uid,
        review_id,
        request.decision,
        correction=request.correction,
        reason=request.reason,
        current_veracity=request.current_veracity,
    )
    if result.get('status') == 'not_found':
        raise HTTPException(status_code=404, detail='Review item not found')
    return result


@router.delete('/v3/memories/batch', tags=['memories'], response_model=MemoryMutationResponse)
def delete_memories_batch(
    data: BatchDeleteMemoriesRequest,
    uid: str = Depends(
        cast(Callable[..., str], _auth_module.with_rate_limit(auth.get_current_user_uid, "memories:delete_batch"))
    ),
):
    """Delete up to MEMORIES_BATCH_MAX memories in one request.

    Replaces the N concurrent DELETE /v3/memories/{id} calls the web UI used to fan out
    on bulk selection, which blew through the per-UID rate limiter and 429'd.

    Authorization parity with DELETE /v3/memories/{memory_id}: every requested id is
    validated with the SAME business rules as the single-delete path. Validation is
    all-or-nothing — if any id fails, nothing is deleted, so the batch route can never
    bypass the single-delete guardrails (missing/not-owned -> 404, locked paid-plan
    memory -> 402).
    """
    # Deduplicate while preserving first-seen order so repeated ids cannot inflate
    # counts or trigger redundant Firestore/Pinecone ops.
    memory_ids = list(dict.fromkeys(data.memory_ids))
    if not memory_ids:
        return {'status': 'ok'}

    service = MemoryService(db_client=getattr(db_client_module, 'db', None))
    try:
        # The service performs a complete read-only validation pass before any
        # canonical write, preserving the released all-or-nothing contract.
        service.delete_batch(uid, memory_ids)
    except HTTPException:
        # Preserve service-owned 402/404/413 mappings and observability details.
        raise
    except ValueError:
        raise HTTPException(status_code=404, detail='Memory not found')
    return {'status': 'ok'}


@router.delete('/v3/memories/{memory_id}', tags=['memories'], response_model=MemoryMutationResponse)
def delete_memory(
    memory_id: str,
    uid: str = Depends(
        cast(Callable[..., str], _auth_module.with_rate_limit(auth.get_current_user_uid, "memories:delete"))
    ),
):
    try:
        MemoryService(db_client=getattr(db_client_module, 'db', None)).delete(uid, memory_id)
    except ValueError:
        raise HTTPException(status_code=404, detail='Memory not found')
    return {'status': 'ok'}


@router.delete('/v3/memories', tags=['memories'], response_model=MemoryMutationResponse)
def delete_memories(
    scope: Literal['all', 'default'] = Query(
        'all',
        description="Delete all memories or only default-access Short-term and Long-term memories.",
    ),
    uid: str = Depends(
        cast(Callable[..., str], _auth_module.with_rate_limit(auth.get_current_user_uid, "memories:delete_all"))
    ),
):
    service = MemoryService(db_client=getattr(db_client_module, 'db', None))
    if scope == 'default':
        service.delete_default(uid)
    else:
        service.delete_all(uid)
    return {'status': 'ok'}


@router.post('/v3/memories/{memory_id}/review', tags=['memories'], response_model=MemoryMutationResponse)
def review_memory(
    memory_id: str,
    value: bool,
    uid: str = Depends(
        cast(Callable[..., str], _auth_module.with_rate_limit(auth.get_current_user_uid, "memories:modify"))
    ),
):
    service = MemoryService(db_client=getattr(db_client_module, 'db', None))
    _validate_mutable_memory(uid, memory_id, db_client=getattr(db_client_module, 'db', None))
    service.review(uid, memory_id, value)
    return {'status': 'ok'}


@router.patch('/v3/memories/{memory_id}', tags=['memories'], response_model=MemoryMutationResponse)
def edit_memory(
    memory_id: str,
    request: Optional[MemoryValueRequest] = Body(default=None),
    value: Optional[str] = Query(
        default=None,
        deprecated=True,
        description="Deprecated; send JSON body {'value': ...} instead",
    ),
    uid: str = Depends(
        cast(Callable[..., str], _auth_module.with_rate_limit(auth.get_current_user_uid, "memories:modify"))
    ),
):
    mutation_value = request.value if request is not None else value
    if mutation_value is None:
        raise HTTPException(status_code=422, detail="Missing memory mutation value")

    db_client = getattr(db_client_module, 'db', None)
    _validate_mutable_memory(uid, memory_id, db_client=db_client)
    try:
        MemoryService(db_client=db_client).update_content(uid, memory_id, mutation_value)
    except ValueError:
        raise HTTPException(status_code=404, detail='Memory not found')
    return {'status': 'ok'}


@router.patch('/v3/memories/{memory_id}/visibility', tags=['memories'], response_model=MemoryMutationResponse)
def update_memory_visibility(
    memory_id: str,
    request: Optional[MemoryValueRequest] = Body(default=None),
    value: Optional[str] = Query(
        default=None,
        deprecated=True,
        description="Deprecated; send JSON body {'value': ...} instead",
    ),
    uid: str = Depends(
        cast(Callable[..., str], _auth_module.with_rate_limit(auth.get_current_user_uid, "memories:modify"))
    ),
):
    mutation_value = request.value if request is not None else value
    if mutation_value is None:
        raise HTTPException(status_code=422, detail="Missing memory mutation value")
    if mutation_value not in ['public', 'private']:
        raise HTTPException(status_code=400, detail='Invalid visibility value')
    db_client = getattr(db_client_module, 'db', None)
    _validate_mutable_memory(uid, memory_id, db_client=db_client)
    MemoryService(db_client=db_client).update_visibility(uid, memory_id, mutation_value)
    submit_with_context(postprocess_executor, update_personas_async, uid)
    return {'status': 'ok'}


@router.patch('/v3/memories/{memory_id}/read', tags=['memories'], response_model=MemoryDB)
def update_memory_read_status(
    memory_id: str,
    request: MemoryReadStatusRequest,
    uid: str = Depends(
        cast(Callable[..., str], _auth_module.with_rate_limit(auth.get_current_user_uid, "memories:modify"))
    ),
):
    """Persist durable insight/memory read and dismiss state for desktop clients."""

    if request.is_read is None and request.is_dismissed is None:
        raise HTTPException(status_code=422, detail="Missing memory read mutation value")
    db_client = getattr(db_client_module, 'db', None)
    _validate_mutable_memory(uid, memory_id, db_client=db_client)
    try:
        memory = MemoryService(db_client=db_client).update_read_status(
            uid,
            memory_id,
            is_read=request.is_read,
            is_dismissed=request.is_dismissed,
        )
    except ValueError:
        raise HTTPException(status_code=404, detail='Memory not found')
    return _memory_response(memory)


@router.patch('/v3/memories/{memory_id}/baseline', tags=['memories'], response_model=MemoryMutationResponse)
def update_memory_baseline(
    memory_id: str,
    value: bool,
    uid: str = Depends(auth.with_rate_limit(auth.get_current_user_uid, "memories:modify")),
):
    """Preserve the released baseline flag through universal memory authority."""

    db_client = getattr(db_client_module, 'db', None)
    _validate_mutable_memory(uid, memory_id, db_client=db_client)
    MemoryService(db_client=db_client).update_baseline(uid, memory_id, value)
    return {'status': 'ok'}
