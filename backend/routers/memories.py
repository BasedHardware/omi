import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Literal, Optional, cast

import database._client as db_client_module
from utils.executors import db_executor, postprocess_executor, run_blocking, submit_with_context

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError

import database.memories as memories_db
from database.memory_imports import ingest_memory_import_batch
from database import review_queue
from database.vector_db import (
    delete_memory_vector,
    delete_memory_vectors_batch,
    upsert_memory_vector,
    upsert_memory_vectors_batch,
)
from models.memories import MemoryDB, Memory, MemoryCategory
from models.memory_imports import MemoryImportBatchRequest, MemoryImportBatchResponse
from utils.apps import update_personas_async
from utils.memory.v3.composed_get_service import V3ComposedRequestParams, V3ComposedResponse
from utils.memory.v3.production_runtime import build_v3_production_runtime
from utils.memory.canonical_activation import canonical_read_enabled, canonical_write_decision, canonical_write_enabled
from utils.memory.canonical_memory_adapter import (
    memory_item_to_memorydb,
    read_canonical_memory_item,
)
from utils.memory.memory_service import MemoryPayload, MemoryService, fetch_memory_dict
from utils.memory.import_write_guard import (
    import_write_block_mode,
    import_write_violation_for_guard,
    is_per_file_local_import_tags,
)
from utils.memory.memory_api_contract import (
    MemoryApiExposure,
    memory_write_payload,
)
from utils.memory.memory_api_response import memory_batch_response, memory_item_response, memory_list_response
from utils.memory.memory_system import MemorySystem, resolve_memory_system
from utils.client_device import DeviceScopeRequest, DeviceScopeValidationError, resolve_client_device_from_request
from utils.memory.device_scope_filter import device_scope_validation_error
from utils.log_sanitizer import sanitize_pii
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


class ReviewResolutionResponse(BaseModel):
    model_config = {"extra": "allow"}

    status: str


# Hard cap on memories per batch request. Keep aligned with the corresponding
# Pydantic max_length validator below and with the Swift client chunker.
MEMORIES_BATCH_MAX = 100

V3GetSourceDecision = Literal['disabled', 'legacy_primary', 'memory_read']

_MEMORY_GET_ALLOWLISTED_RESPONSE_HEADERS = frozenset(
    {
        'X-Omi-Memory-Read-Source',
        'X-Omi-Memory-Read-Decision',
        'X-Omi-Memory-Next-Cursor',
        'X-Omi-Memory-Device-Scope-Supported',
        'X-Omi-Memory-Canonical-Lifecycle-Exposed',
        'Link',
        'Cache-Control',
    }
)

_MEMORY_CANONICAL_LIFECYCLE_EXPOSED_HEADER = 'X-Omi-Memory-Canonical-Lifecycle-Exposed'
_MEMORY_DEVICE_SCOPE_SUPPORTED_HEADER = 'X-Omi-Memory-Device-Scope-Supported'


@dataclass(frozen=True)
class V3GetRuntime:
    """Lazy, overrideable F4 runtime bundle for GET `/v3/memories`.

    The production/default dependency below is structurally disabled in F4. TestClient
    may override the exact dependency to supply a composed service and typed source
    decision. This bundle intentionally does not construct Firestore clients, cursor
    keyrings, projection adapters, production readers, or telemetry emitters at import.
    """

    enabled: bool = False
    source_decision: V3GetSourceDecision = 'disabled'
    service: Optional[Callable[[V3ComposedRequestParams, object], object]] = None
    adapters: object = None
    source_selector: object = None
    control_reader: object = None
    legacy_reader: object = None
    projection_reader: object = None
    cursor_keyring: object = None
    cursor_codec: object = None
    clock: object = None
    deadline: object = None
    observer: object = None


def get_v3_get_runtime(uid: str = Depends(auth.get_current_user_uid)):
    """Return the production/default runtime bundle for GET `/v3/memories`.

    Default production behavior is still disabled. Server-owned configuration can
    only enter memory when all of these are true: `MEMORY_MODE` is not off,
    `MEMORY_ENABLED_USERS` contains the authenticated uid, the persisted
    control state is read-mode, and global/read-convergence gates allow the
    composed service to proceed. Client headers, query params, request bodies,
    and persisted user docs alone cannot activate memory.
    """

    return build_v3_production_runtime(uid=uid, db_client=getattr(db_client_module, 'db', None))


class BatchMemoriesRequest(BaseModel):
    memories: List[Memory] = Field(
        description="List of memories to create in a single batch request",
        max_length=MEMORIES_BATCH_MAX,
    )


class BatchMemoriesResponse(BaseModel):
    memories: List[MemoryDB]
    created_count: int


class ReviewResolutionRequest(BaseModel):
    decision: str = Field(description="accept, reject, correct, or timeout")
    correction: Optional[Dict[str, Any]] = None
    reason: str = ''
    current_veracity: Optional[float] = None


async def _guard_import_memory_write(request: Request, *, endpoint: str, uid: str) -> None:
    mode = import_write_block_mode()
    db_client = getattr(db_client_module, 'db', None)
    # Canonical users must never fall back from evidence ingress into a direct
    # product-memory write, regardless of the legacy rollout env default.
    if resolve_memory_system(uid, db_client=db_client) == MemorySystem.CANONICAL:
        mode = "enforce"
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


def _legacy_get_memories(uid: str, limit: int, offset: int) -> List[MemoryDB]:
    # Clamp pagination so an out-of-range value cannot reach Firestore .limit()/.offset(), which raises
    # on a negative argument and would otherwise 500 the request.
    offset = max(0, offset)
    # Use high limits for the first page
    # Warn: should remove
    if offset == 0:
        limit = 5000
    limit = max(1, min(limit, 5000))
    memories = memories_db.get_memories(uid, limit, offset)

    valid_memories: List[MemoryDB] = []
    for memory in memories:
        if memory.get('is_locked', False):
            content = memory.get('content', '')
            memory['content'] = (content[:70] + '...') if len(content) > 70 else content
        try:
            valid_memories.append(MemoryDB.model_validate(memory))
        except ValidationError as e:
            missing_fields = [err['loc'][0] for err in e.errors() if err.get('loc')]
            logger.warning(
                f"Skipping invalid memory doc {memory.get('id', 'unknown')}: missing/invalid fields {missing_fields}"
            )
            continue
    return valid_memories


def _legacy_memories_response(memories: List[MemoryDB]) -> JSONResponse:
    """Serialize legacy memories without canonical lifecycle fields.

    The single source of truth for which fields are canonical-only lives in
    ``utils.memory.memory_api_contract``. Keep this wrapper small so every
    legacy response takes the same field contract.
    """

    return memory_list_response(
        memories,
        MemoryApiExposure.LEGACY,
        headers={
            _MEMORY_DEVICE_SCOPE_SUPPORTED_HEADER: 'false',
            _MEMORY_CANONICAL_LIFECYCLE_EXPOSED_HEADER: 'false',
        },
    )


def _legacy_memory_response(memory: MemoryDB) -> JSONResponse:
    return memory_item_response(memory, MemoryApiExposure.LEGACY)


def _legacy_batch_memories_response(memories: List[MemoryDB]) -> JSONResponse:
    return memory_batch_response(memories, MemoryApiExposure.LEGACY, created_count=len(memories))


def _apply_memory_response_headers(http_response: Response, memory_response: V3ComposedResponse) -> None:
    for name, value in memory_response.headers.items():
        if name in _MEMORY_GET_ALLOWLISTED_RESPONSE_HEADERS:
            http_response.headers[name] = value
    http_response.headers['Cache-Control'] = 'no-store'


def _memory_allowlisted_headers(memory_response: V3ComposedResponse) -> Dict[str, str]:
    return {
        name: value
        for name, value in memory_response.headers.items()
        if name in _MEMORY_GET_ALLOWLISTED_RESPONSE_HEADERS
    }


def _raise_memory_http_exception(memory_response: V3ComposedResponse) -> None:
    raise HTTPException(
        status_code=memory_response.http_status,
        detail=memory_response.public_error or 'memory_read_failed',
        headers=_memory_allowlisted_headers(memory_response),
    )


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


def _canonical_lifecycle_exposed_for(memory_response: V3ComposedResponse) -> bool:
    return memory_response.http_status == 200 and memory_response.source in {
        'memory',
        'memory_compatibility_projection',
    }


def _canonical_write_enabled_or_fail_closed(uid: str, *, db_client: Any) -> bool:
    decision = canonical_write_decision(uid, db_client=db_client)
    if decision.enabled:
        return True
    if decision.fail_closed:
        logger.warning("canonical_write fail_closed uid=%s reason=%s", sanitize_pii(uid), decision.reason)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")
    return False


def _validate_memory(uid: str, memory_id: str) -> MemoryPayload:
    return fetch_memory_dict(uid, memory_id, db_client=getattr(db_client_module, 'db', None))


def _validate_mutable_memory(uid: str, memory_id: str, *, db_client: Any) -> MemoryPayload:
    if canonical_write_enabled(uid, db_client=db_client):
        item = read_canonical_memory_item(uid, memory_id, db_client=db_client)
        if item is None:
            raise HTTPException(status_code=404, detail='Memory not found')
        return memory_item_to_memorydb(item).dict()
    return fetch_memory_dict(uid, memory_id, db_client=db_client)


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
        return _legacy_memory_response(memory_db)

    db_client = getattr(db_client_module, 'db', None)
    if _canonical_write_enabled_or_fail_closed(uid, db_client=db_client):
        try:
            memory_service = MemoryService(db_client=db_client)
            return await run_blocking(
                db_executor,
                memory_service.create_external_memory,
                uid,
                memory_db,
                memory_system=MemorySystem.CANONICAL,
                consumer="v3_manual" if manually_added else "v3_api",
                operation="create_memory",
                upsert_vector=False,
                require_canonical_promotion=True,
            )
        except Exception:
            logger.exception("Canonical create_memory failed uid=%s", uid)
            raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    try:
        await run_blocking(
            db_executor,
            memories_db.create_memory,
            uid,
            memory_write_payload(memory_db, MemoryApiExposure.LEGACY),
        )
    except Exception:
        logger.exception("Firestore create_memory failed uid=%s", uid)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    try:
        await run_blocking(
            postprocess_executor,
            upsert_memory_vector,
            uid,
            memory_db.id,
            memory_db.content,
            memory_db.category.value,
            memory_db.subject_entity_id,
        )
    except Exception:
        logger.exception("Vector upsert failed uid=%s memory_id=%s (memory saved, vector missing)", uid, memory_db.id)

    return _legacy_memory_response(memory_db)


@router.post(
    '/v3/memories/batch',
    tags=['memories'],
    response_model=BatchMemoriesResponse,
)
async def create_memories_batch(
    request_context: Request,
    request: BatchMemoriesRequest,
    uid: str = Depends(
        cast(Callable[..., str], _auth_module.with_rate_limit(auth.get_current_user_uid, "memories:batch"))
    ),
):
    await _guard_import_memory_write(request_context, endpoint="/v3/memories/batch", uid=uid)
    """
    Create many memories in a single request.

    Solves the Cloud Armor throttling seen on onboarding: the desktop client
    used to fan out one `POST /v3/memories` per local-file memory (up to 2800
    per user), blowing through the 120 req/min per-Authorization Cloud Armor
    rule and collaterally 429-ing unrelated calls (goals, sync, chat).

    One HTTP request here = one Firestore batch write + one embeddings call +
    one Pinecone upsert, regardless of batch size.
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
        if memory.visibility == 'public':
            has_public = True

    db_client = getattr(db_client_module, 'db', None)
    if _canonical_write_enabled_or_fail_closed(uid, db_client=db_client):
        memory_service = MemoryService(db_client=db_client)
        # Pre-validate the entire batch so a whitespace-only (or otherwise
        # canonical-rejected) item fails fast *before* any per-item write
        # commits. This preserves the legacy single-batch-write semantics:
        # either all items persist or none do, so client retries never observe
        # partial results.
        for memory_db in memory_dbs:
            if not (memory_db.content or '').strip():
                raise HTTPException(
                    status_code=400,
                    detail='Memory content cannot be empty or whitespace-only.',
                )
        committed_ids: List[str] = []
        for memory_db in memory_dbs:
            created = await run_blocking(
                db_executor,
                memory_service.create_external_memory,
                uid,
                memory_db,
                memory_system=MemorySystem.CANONICAL,
                consumer="v3_manual" if memory_db.manually_added else "v3_api",
                operation="batch_create_memory",
                upsert_vector=False,
                require_canonical_promotion=True,
            )
            committed_ids.append(created.id)
        if has_public:
            submit_with_context(postprocess_executor, update_personas_async, uid)
        server_memories: List[MemoryDB] = []
        for memory_id in committed_ids:
            item = await run_blocking(db_executor, read_canonical_memory_item, uid, memory_id, db_client=db_client)
            if item is not None:
                server_memories.append(memory_item_to_memorydb(item))
            else:
                logger.error("Canonical create_memories_batch readback missing uid=%s memory_id=%s", uid, memory_id)
                raise HTTPException(status_code=503, detail="Service temporarily unavailable")
        return BatchMemoriesResponse(memories=server_memories, created_count=len(server_memories))

    # Persist to Firestore first — that write is the authoritative result.
    # Mirror create_memory above: isolate the best-effort vector upsert so a
    # transient/BYOK embedding failure (e.g. an OpenAI key without
    # text-embedding-3-large access -> 403) can't 500 a request whose memories
    # were already saved, which would make the client retry and duplicate them.
    try:
        await run_blocking(
            db_executor,
            memories_db.save_memories,
            uid,
            [memory_write_payload(m, MemoryApiExposure.LEGACY) for m in memory_dbs],
        )
    except Exception:
        logger.exception("Firestore save_memories failed uid=%s count=%s", uid, len(memory_dbs))
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    # Pinecone batch upsert runs on a worker thread (postprocess pool, like the
    # single-create path) so a slow embeddings/Pinecone call can't starve the
    # FastAPI sync threadpool.
    try:
        await run_blocking(
            postprocess_executor,
            upsert_memory_vectors_batch,
            uid,
            [
                {
                    "memory_id": m.id,
                    "content": m.content,
                    "category": m.category.value,
                    "subject_entity_id": m.subject_entity_id,
                }
                for m in memory_dbs
            ],
        )
    except Exception:
        logger.exception(
            "Batch vector upsert failed uid=%s count=%s (memories saved, vectors missing)", uid, len(memory_dbs)
        )

    return _legacy_batch_memories_response(memory_dbs)


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

    write_decision = await run_blocking(db_executor, canonical_write_decision, uid, db_client=db_client)
    if write_decision.memory_system != MemorySystem.CANONICAL:
        raise HTTPException(status_code=403, detail="memory_import_requires_canonical")
    if not write_decision.enabled:
        logger.warning("memory import ingest disabled uid=%s reason=%s", uid, write_decision.reason)
        raise HTTPException(status_code=503, detail="memory_import_canonical_not_ready")

    try:
        result = await run_blocking(db_executor, ingest_memory_import_batch, uid, request, db_client=db_client)
    except Exception:
        logger.exception("Memory import ingest failed uid=%s source_type=%s", uid, request.source_type)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")
    return result.response


@router.get('/v3/memories', tags=['memories'], response_model=List[MemoryDB])
def get_memories(
    response: Response,
    limit: int = 100,
    offset: int = 0,
    cursor: Optional[str] = None,
    device_scope: str = Query('all'),
    client_device_id: Optional[str] = Query(None),
    uid: str = Depends(auth.get_current_user_uid),
    memory_runtime: V3GetRuntime = Depends(get_v3_get_runtime),
    x_app_platform: str = Header(None, alias='X-App-Platform'),
    x_device_id_hash: str = Header(None, alias='X-Device-Id-Hash'),
):
    scope_request = _resolve_get_memories_device_scope(
        device_scope,
        client_device_id,
        x_app_platform=x_app_platform,
        x_device_id_hash=x_device_id_hash,
    )
    db_client = getattr(db_client_module, 'db', None)
    is_canonical = canonical_read_enabled(
        uid,
        db_client=db_client,
        source_decision=memory_runtime.source_decision,
        cursor_memory_read_requested=bool(cursor),
    )

    if scope_request.device_scope != 'all' and not is_canonical:
        raise HTTPException(
            status_code=400,
            detail='device_scope filtering is only supported for canonical memory users',
            headers={
                _MEMORY_DEVICE_SCOPE_SUPPORTED_HEADER: 'false',
                _MEMORY_CANONICAL_LIFECYCLE_EXPOSED_HEADER: 'false',
            },
        )

    if is_canonical:
        _validate_device_scope_request(scope_request.device_scope, scope_request.client_device_id)
        _set_device_scope_capability_header(response, supported=True)
        _set_canonical_lifecycle_exposure_header(response, exposed=True)
        # Clamp pagination parameters so the canonical branch (which bypasses
        # _legacy_get_memories clamping) never receives values that would
        # slice the visible list incorrectly — e.g. limit=-1 returning nearly
        # the entire list or negative offsets producing inconsistent pages.
        clamped_offset = max(0, offset)
        clamped_limit = max(1, min(limit, 5000))
        # Preserve the historical first-page load for the mobile MemoriesProvider,
        # which calls getMemoriesResult() with its default limit and has no
        # load-more path. Legacy users get this expansion via _legacy_get_memories;
        # canonical users must get the same first-page behavior so accounts with
        # more than 100 memories do not silently see only the newest 100.
        if clamped_offset == 0:
            clamped_limit = 5000
        return MemoryService(db_client=db_client).read(
            uid,
            limit=clamped_limit,
            offset=clamped_offset,
            device_scope_request=scope_request,
            include_pending_processing=True,
        )

    if memory_runtime.source_decision != 'memory_read':
        return _legacy_memories_response(_legacy_get_memories(uid, limit, offset))

    _set_device_scope_capability_header(response, supported=False)
    _set_canonical_lifecycle_exposure_header(response, exposed=False)

    if memory_runtime.service is None:
        logger.info("v3_get route=GET /v3/memories source=none status=503 decision=malformed_runtime_dependency")
        raise HTTPException(status_code=503, detail='infrastructure_failure')

    params = V3ComposedRequestParams(limit=limit, offset=offset, cursor=cursor)
    memory_response = memory_runtime.service(params, memory_runtime.adapters)
    if not isinstance(memory_response, V3ComposedResponse):
        logger.info("v3_get route=GET /v3/memories source=none status=503 decision=adapter_contract")
        raise HTTPException(status_code=503, detail='infrastructure_failure')

    canonical_lifecycle_exposed = _canonical_lifecycle_exposed_for(memory_response)
    memory_response.headers[_MEMORY_DEVICE_SCOPE_SUPPORTED_HEADER] = 'true' if canonical_lifecycle_exposed else 'false'
    memory_response.headers[_MEMORY_CANONICAL_LIFECYCLE_EXPOSED_HEADER] = (
        'true' if canonical_lifecycle_exposed else 'false'
    )
    _apply_memory_response_headers(response, memory_response)
    logger.info(
        "v3_get route=GET /v3/memories source=%s status=%s decision=%s",
        memory_response.source,
        memory_response.http_status,
        memory_response.public_error or memory_response.decision,
    )
    if memory_response.http_status != 200:
        _raise_memory_http_exception(memory_response)
    headers = _memory_allowlisted_headers(memory_response)
    headers['Cache-Control'] = 'no-store'
    exposure = MemoryApiExposure.CANONICAL if canonical_lifecycle_exposed else MemoryApiExposure.LEGACY
    return memory_list_response(memory_response.body or [], exposure, headers=headers)


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


@router.delete('/v3/memories/{memory_id}', tags=['memories'], response_model=MemoryMutationResponse)
def delete_memory(
    memory_id: str,
    uid: str = Depends(
        cast(Callable[..., str], _auth_module.with_rate_limit(auth.get_current_user_uid, "memories:delete"))
    ),
):
    db_client = getattr(db_client_module, 'db', None)
    if _canonical_write_enabled_or_fail_closed(uid, db_client=db_client):
        try:
            MemoryService(db_client=db_client).delete(uid, memory_id)
        except ValueError:
            raise HTTPException(status_code=404, detail='Memory not found')
        return {'status': 'ok'}

    _validate_memory(uid, memory_id)
    memories_db.delete_memory(uid, memory_id)
    try:
        delete_memory_vector(uid, memory_id)
    except Exception:
        logger.exception("Vector delete failed uid=%s memory_id=%s (Firestore deleted)", uid, memory_id)
    return {'status': 'ok'}


@router.delete('/v3/memories', tags=['memories'], response_model=MemoryMutationResponse)
def delete_memories(
    uid: str = Depends(
        cast(Callable[..., str], _auth_module.with_rate_limit(auth.get_current_user_uid, "memories:delete_all"))
    ),
):
    db_client = getattr(db_client_module, 'db', None)
    if _canonical_write_enabled_or_fail_closed(uid, db_client=db_client):
        MemoryService(db_client=db_client).delete_all(uid)
        return {'status': 'ok'}

    # Collect all memory IDs before Firestore delete so we can also purge
    # their Pinecone vectors — otherwise orphaned vectors become search
    # noise that never gets cleaned up.
    memory_ids: List[str] = []
    offset = 0
    batch_size = 1000
    while True:
        memories = memories_db.get_memories(uid, limit=batch_size, offset=offset, include_invalidated=True)
        if not memories:
            break
        batch_ids = [memory_id for m in memories if isinstance((memory_id := m.get('id')), str) and memory_id]
        memory_ids.extend(batch_ids)
        offset += batch_size

    memories_db.delete_all_memories(uid)

    if memory_ids:
        delete_memory_vectors_batch(uid, memory_ids)

    return {'status': 'ok'}


@router.post('/v3/memories/{memory_id}/review', tags=['memories'], response_model=MemoryMutationResponse)
def review_memory(
    memory_id: str,
    value: bool,
    uid: str = Depends(
        cast(Callable[..., str], _auth_module.with_rate_limit(auth.get_current_user_uid, "memories:modify"))
    ),
):
    db_client = getattr(db_client_module, 'db', None)
    if _canonical_write_enabled_or_fail_closed(uid, db_client=db_client):
        _validate_mutable_memory(uid, memory_id, db_client=db_client)
        MemoryService(db_client=db_client).review(uid, memory_id, value)
        return {'status': 'ok'}
    _validate_mutable_memory(uid, memory_id, db_client=db_client)
    memories_db.review_memory(uid, memory_id, value)
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
    if _canonical_write_enabled_or_fail_closed(uid, db_client=db_client):
        _validate_mutable_memory(uid, memory_id, db_client=db_client)
        MemoryService(db_client=db_client).update_content(uid, memory_id, mutation_value)
        return {'status': 'ok'}

    memory = _validate_mutable_memory(uid, memory_id, db_client=db_client)
    memories_db.edit_memory(uid, memory_id, mutation_value)
    # Re-embed so semantic search reflects the new content. Without this the Pinecone
    # vector keeps matching the OLD text — a silent staleness bug that breaks the
    # "constantly updated brain" (search would still surface the pre-edit fact).
    try:
        upsert_memory_vector(
            uid,
            memory_id,
            mutation_value,
            memory.get('category', 'system'),
            subject_entity_id=memory.get('subject_entity_id'),
        )
    except Exception:
        logger.exception("Vector upsert failed uid=%s memory_id=%s (memory edited, vector stale)", uid, memory_id)
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
    if _canonical_write_enabled_or_fail_closed(uid, db_client=db_client):
        _validate_mutable_memory(uid, memory_id, db_client=db_client)
        MemoryService(db_client=db_client).update_visibility(uid, memory_id, mutation_value)
        submit_with_context(postprocess_executor, update_personas_async, uid)
        return {'status': 'ok'}
    _validate_mutable_memory(uid, memory_id, db_client=db_client)
    memories_db.change_memory_visibility(uid, memory_id, mutation_value)
    return {'status': 'ok'}


@router.patch('/v3/memories/{memory_id}/baseline', tags=['memories'], response_model=MemoryMutationResponse)
def update_memory_baseline(
    memory_id: str,
    value: bool,
    uid: str = Depends(auth.with_rate_limit(auth.get_current_user_uid, "memories:modify")),
):
    """Toggle the baseline flag for a memory.

    Baseline memories are always injected first into the AI context window.
    Not supported for canonical-path users: MemoryItem has no is_baseline field,
    so writing to the legacy store would silently have no effect for canonical readers.
    Canonical users receive 503 explicitly rather than a silent wrong-store write.
    """
    db_client = getattr(db_client_module, 'db', None)
    if _canonical_write_enabled_or_fail_closed(uid, db_client=db_client):
        raise HTTPException(status_code=503, detail='Service temporarily unavailable')
    _validate_mutable_memory(uid, memory_id, db_client=db_client)
    memories_db.update_memory_fields(uid, memory_id, {'is_baseline': value})
    submit_with_context(postprocess_executor, update_personas_async, uid)
    return {'status': 'ok'}
