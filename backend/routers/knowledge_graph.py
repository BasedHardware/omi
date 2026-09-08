import importlib
import sys
from enum import Enum

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Callable, Optional, cast

from database import knowledge_graph as kg_db
from database._client import get_firestore_client
from database.auth import get_user_name
from utils.memory import canonical_graph as canonical_graph_service
from utils.memory.memory_service import MemoryService
from utils.executors import db_executor, llm_executor, run_blocking
from utils.observability.fallback import record_fallback
from utils.other import endpoints as auth
from utils.subscription import is_trial_paywalled

router = APIRouter()
Payload = Dict[str, Any]
MemoryPayloads = List[Payload]
RebuildKnowledgeGraph = Callable[[str, MemoryPayloads, str], Payload]
RateLimitFactory = Callable[[Any, str], Any]
with_rate_limit: RateLimitFactory = cast(RateLimitFactory, getattr(auth, "with_rate_limit"))
CANONICAL_GRAPH_MUTATION_CONFLICT = (
    "Canonical knowledge graph state is derived from canonical memories and cannot be deleted or rebuilt directly."
)
CANONICAL_GRAPH_STATE_UNVERIFIED = (
    "Knowledge graph state could not be verified right now, so it was left untouched. Please try again."
)


def _knowledge_graph_llm_module() -> Any:
    return sys.modules.get("utils.llm.knowledge_graph") or importlib.import_module("utils.llm.knowledge_graph")


def _run_rebuild_knowledge_graph(uid: str, memories: MemoryPayloads, user_name: str) -> Payload:
    rebuild_knowledge_graph = cast(
        RebuildKnowledgeGraph, getattr(_knowledge_graph_llm_module(), "rebuild_knowledge_graph")
    )
    return rebuild_knowledge_graph(uid, memories, user_name)


class LegacyGraphMutation(str, Enum):
    """Whether the legacy rebuild/delete path may run for this account."""

    ALLOWED = 'allowed'
    #: Derived state exists and owns this graph — the legacy mutation is a conflict.
    CONFLICT = 'conflict'
    #: We could not establish whether derived state exists. Not the same as "it does not".
    UNVERIFIED = 'unverified'


def _legacy_graph_mutation_decision(uid: str) -> LegacyGraphMutation:
    """Decide, per account, whether the legacy graph may still be rebuilt or deleted.

    This must stay a real per-account probe. Answering ``CONFLICT`` unconditionally
    protects derived state that does not exist and denies every account the legacy
    rebuild/delete their graph still needs.

    The probe is deliberately tri-state. ``GET`` may fail open on any unavailable
    canonical read because the worst case is a stale view; these routes destroy the
    legacy store, so only a *positive* "there is no state head" answer may unlock
    them. A read timeout, a corrupt head, or an unsupported schema is an unanswered
    question, and answering it as "unestablished" would let a transient Firestore
    blip delete the graph.
    """
    state = canonical_graph_service.probe_canonical_graph_state(uid)
    if state is canonical_graph_service.CanonicalGraphState.ESTABLISHED:
        return LegacyGraphMutation.CONFLICT
    if state is canonical_graph_service.CanonicalGraphState.INDETERMINATE:
        return LegacyGraphMutation.UNVERIFIED
    if kg_db.has_stored_memory_graph_assertions(uid, db_client=get_firestore_client()):
        return LegacyGraphMutation.CONFLICT
    return LegacyGraphMutation.ALLOWED


def _require_legacy_graph_mutation(uid: str) -> None:
    decision = _legacy_graph_mutation_decision(uid)
    if decision is LegacyGraphMutation.CONFLICT:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=CANONICAL_GRAPH_MUTATION_CONFLICT,
        )
    if decision is LegacyGraphMutation.UNVERIFIED:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=CANONICAL_GRAPH_STATE_UNVERIFIED,
        )
    # Fail-open path: this account has no canonical state, so the mutation is
    # served by the pre-canonical store instead of the derived one.
    record_fallback(
        component='knowledge_graph',
        from_mode='canonical_graph',
        to_mode='legacy_graph',
        reason='unmigrated_principal',
        outcome='degraded',
    )


class KnowledgeNode(BaseModel):
    id: str
    label: str
    node_type: str = 'concept'
    aliases: List[str] = []
    memory_ids: List[str] = []


class KnowledgeEdge(BaseModel):
    id: str
    source_id: str
    target_id: str
    label: str
    memory_ids: List[str] = []


class KnowledgeGraphResponse(BaseModel):
    nodes: List[Dict[str, Any]]
    edges: List[Dict[str, Any]]
    truncated: bool = False
    node_count: int = 0
    edge_count: int = 0
    node_limit: int | None = None
    edge_limit: int | None = None


class CanonicalKnowledgeGraphResponse(BaseModel):
    nodes: List[Dict[str, Any]]
    edges: List[Dict[str, Any]]
    has_more: bool
    next_cursor: Optional[str] = None
    catalog_nodes: List[Dict[str, Any]] = []


class RebuildResponse(BaseModel):
    status: str
    nodes_count: int
    edges_count: int


class DeleteKnowledgeGraphResponse(BaseModel):
    status: str


class ExtractKnowledgeGraphRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=100_000)
    user_name: Optional[str] = None
    include_existing: bool = False


class ExtractKnowledgeGraphResponse(BaseModel):
    nodes: List[Dict[str, Any]]
    edges: List[Dict[str, Any]]


def _legacy_knowledge_graph_response(uid: str) -> "KnowledgeGraphResponse":
    """Bounded read of the pre-canonical graph, used when canonical is unavailable."""
    graph = kg_db.get_knowledge_graph(uid)
    nodes = graph.get('nodes', [])
    edges = graph.get('edges', [])
    return KnowledgeGraphResponse(
        nodes=nodes,
        edges=edges,
        truncated=bool(graph.get('truncated', False)),
        node_count=graph.get('node_count', len(nodes)),
        edge_count=graph.get('edge_count', len(edges)),
        node_limit=graph.get('node_limit'),
        edge_limit=graph.get('edge_limit'),
    )


@router.get(
    "/v1/knowledge-graph",
    tags=["knowledge_graph"],
    response_model=KnowledgeGraphResponse,
)
def get_knowledge_graph(uid: str = Depends(auth.get_current_user_uid)):
    # Hard page cap: this legacy GET has no cursor. Clients that need the full
    # graph must page `/v1/knowledge-graph/canonical`. Always report the cap so
    # truncated responses are distinguishable from complete small graphs.
    page_limit = canonical_graph_service.MAX_CANONICAL_GRAPH_PAGE_LIMIT
    try:
        page = canonical_graph_service.get_canonical_knowledge_graph(
            uid,
            limit=page_limit,
            cursor=None,
        )
        # One memory page may expand into more graph records than the memory
        # page limit. Bound the returned graph itself, not only its source page.
        nodes = page.nodes[:page_limit]
        node_ids = {node.get("id") for node in nodes if node.get("id")}
        bounded_edges = page.edges[:page_limit]
        edges = [
            edge for edge in bounded_edges if edge.get("source_id") in node_ids and edge.get("target_id") in node_ids
        ]
        dropped_edges = len(bounded_edges) - len(edges)
        truncated = (
            bool(page.has_more) or len(page.nodes) > page_limit or len(page.edges) > page_limit or dropped_edges > 0
        )
    except canonical_graph_service.CanonicalGraphReadUnavailable:
        # Canonical intake is fenced off in production (MEMORY_MODE), so most
        # accounts have no memory_state/head and the canonical read is
        # permanently unavailable for them. Their graph still exists in the
        # legacy store, so serve that instead of failing the feature outright.
        return _legacy_knowledge_graph_response(uid)
    return KnowledgeGraphResponse(
        nodes=nodes,
        edges=edges,
        truncated=truncated,
        node_count=len(nodes),
        edge_count=len(edges),
        node_limit=page_limit,
        edge_limit=page_limit,
    )


@router.get(
    '/v1/knowledge-graph/canonical',
    tags=['knowledge_graph'],
    response_model=CanonicalKnowledgeGraphResponse,
)
def get_canonical_knowledge_graph(
    limit: int = Query(
        canonical_graph_service.DEFAULT_CANONICAL_GRAPH_PAGE_LIMIT,
        ge=1,
        le=canonical_graph_service.MAX_CANONICAL_GRAPH_PAGE_LIMIT,
    ),
    cursor: Optional[str] = Query(default=None),
    uid: str = Depends(with_rate_limit(auth.get_current_user_uid, "knowledge_graph:canonical")),
):
    try:
        page = canonical_graph_service.get_canonical_knowledge_graph(
            uid,
            limit=limit,
            cursor=cursor,
        )
    except canonical_graph_service.CanonicalGraphCursorError as exc:
        raise HTTPException(status_code=400, detail='invalid_or_stale_cursor') from exc
    except canonical_graph_service.CanonicalGraphReadUnavailable as exc:
        raise HTTPException(status_code=503, detail='canonical_graph_unavailable') from exc
    return CanonicalKnowledgeGraphResponse(
        nodes=page.nodes,
        edges=page.edges,
        has_more=page.has_more,
        next_cursor=page.next_cursor,
        catalog_nodes=getattr(page, 'catalog_nodes', []),
    )


def _rebuild_graph_task(uid: str, user_name: str) -> None:
    # The gate is re-checked here because it was last answered before the response
    # was returned. Bailing out must leave the graph exactly as it was, so nothing
    # upstream of `rebuild_knowledge_graph` may delete it.
    if _legacy_graph_mutation_decision(uid) is not LegacyGraphMutation.ALLOWED:
        return
    memories: MemoryPayloads = [
        {"id": memory.id, "content": memory.content}
        for memory in MemoryService(db_client=get_firestore_client()).read(uid, limit=500)
        if not getattr(memory, "is_locked", False)
    ]
    _run_rebuild_knowledge_graph(uid, memories, user_name)


@router.post('/v1/knowledge-graph/rebuild', tags=['knowledge_graph'], response_model=RebuildResponse)
def rebuild_graph(
    background_tasks: BackgroundTasks,
    uid: str = Depends(with_rate_limit(auth.get_current_user_uid, "knowledge_graph:rebuild")),
):
    _require_legacy_graph_mutation(uid)
    user_name = get_user_name(uid) or ""
    # No eager delete here: `rebuild_knowledge_graph` clears the graph itself as its
    # first step, so deleting before scheduling only widens the window where the user
    # has no graph and nothing is rebuilding one — a task that never runs, or one that
    # bails on the re-checked gate, would leave them with nothing.
    background_tasks.add_task(_rebuild_graph_task, uid, user_name)
    return RebuildResponse(status="rebuilding", nodes_count=0, edges_count=0)


@router.post(
    '/v1/knowledge-graph/extract',
    tags=['knowledge_graph'],
    response_model=ExtractKnowledgeGraphResponse,
)
async def extract_knowledge_graph(
    body: ExtractKnowledgeGraphRequest,
    uid: str = Depends(with_rate_limit(auth.get_current_user_uid, "knowledge_graph:extract")),
):
    """Return-only KG extraction through the managed knowledge_graph feature (OpenRouter Luna).

    Does not write Firestore. Desktop onboarding/file-index should call this instead of
    inventing nodes/edges via chat_agent, then persist locally via save_knowledge_graph.

    ``strict_parse`` is on at this HTTP boundary so a malformed model response fails
    closed (502) instead of returning 200 with an empty graph, which a client cannot
    tell apart from a genuine "no entities" answer.
    """
    if await run_blocking(db_executor, is_trial_paywalled, uid, 'desktop'):
        raise HTTPException(status_code=402, detail='trial_expired')
    kg_mod = _knowledge_graph_llm_module()
    resolved_name = body.user_name or await run_blocking(db_executor, get_user_name, uid)
    user_name = (resolved_name or "User").strip() or "User"
    extraction = await run_blocking(
        llm_executor,
        lambda: getattr(kg_mod, "extract_kg_from_text")(
            uid,
            body.text,
            user_name=user_name,
            load_existing_from_db=body.include_existing,
            strict_parse=True,
            usage_memory_id="http-extract",
        ),
    )
    if extraction is None:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="knowledge_graph_extract_failed")
    graph = getattr(kg_mod, "extraction_to_client_graph")(extraction, uid=uid)
    return ExtractKnowledgeGraphResponse(nodes=graph['nodes'], edges=graph['edges'])


@router.delete('/v1/knowledge-graph', tags=['knowledge_graph'], response_model=DeleteKnowledgeGraphResponse)
def delete_knowledge_graph(uid: str = Depends(auth.get_current_user_uid)):
    _require_legacy_graph_mutation(uid)
    kg_db.delete_knowledge_graph(uid)
    return DeleteKnowledgeGraphResponse(status="deleted")
