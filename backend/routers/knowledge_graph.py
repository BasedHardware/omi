import importlib
import sys

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Callable, Literal, Optional, cast

from database import knowledge_graph as kg_db
from database.auth import get_user_name
from utils.memory import canonical_graph as canonical_graph_service
from utils.executors import db_executor, llm_executor, run_blocking
from utils.observability.fallback import record_fallback
from utils.other import endpoints as auth
from utils.subscription import is_trial_paywalled
from utils import knowledge_graph_sync as kg_sync

router = APIRouter()
LOCAL_KG_SYNC_MAX_ROWS = 100
RateLimitFactory = Callable[[Any, str], Any]
with_rate_limit: RateLimitFactory = cast(RateLimitFactory, getattr(auth, "with_rate_limit"))
CANONICAL_GRAPH_MUTATION_CONFLICT = (
    "Canonical knowledge graph state is derived from canonical memories and cannot be deleted or rebuilt directly."
)


def _knowledge_graph_llm_module() -> Any:
    return sys.modules.get("utils.llm.knowledge_graph") or importlib.import_module("utils.llm.knowledge_graph")


def _is_assertion_backed_graph_account(uid: str) -> bool:
    """All authenticated accounts use assertion-backed graph semantics."""
    return True


def _require_legacy_graph_mutation(uid: str) -> None:
    if _is_assertion_backed_graph_account(uid):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=CANONICAL_GRAPH_MUTATION_CONFLICT,
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


class LocalKgSyncRequest(BaseModel):
    table: Literal["local_kg_nodes", "local_kg_edges"]
    rows: List[Dict[str, Any]] = Field(min_length=0, max_length=LOCAL_KG_SYNC_MAX_ROWS)
    source_namespace: str = Field(min_length=1, max_length=256)
    reconcile_complete: bool = False


class LocalKgSyncResponse(BaseModel):
    table: str
    merged: int
    skipped: int
    nodes_evicted: int
    edges_evicted: int
    quarantined: int = 0
    deleted: int = 0


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


@router.post('/v1/knowledge-graph/rebuild', tags=['knowledge_graph'], response_model=RebuildResponse)
def rebuild_graph(
    background_tasks: BackgroundTasks,
    uid: str = Depends(with_rate_limit(auth.get_current_user_uid, "knowledge_graph:rebuild")),
):
    _require_legacy_graph_mutation(uid)


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
    return {"status": "deleted"}


@router.post('/v1/knowledge-graph/sync', tags=['knowledge_graph'], response_model=LocalKgSyncResponse)
def sync_local_knowledge_graph(
    payload: LocalKgSyncRequest,
    uid: str = Depends(with_rate_limit(auth.get_current_user_uid, "knowledge_graph:sync")),
):
    """Merge agent-VM synced local_kg_* rows into the user's Firestore graph projection."""
    try:
        _require_legacy_graph_mutation(uid)
    except HTTPException as exc:
        if exc.status_code == status.HTTP_409_CONFLICT:
            record_fallback(
                component="agent_tools",
                from_mode="cloud_promotion",
                to_mode="local_only",
                reason="policy",
                outcome="degraded",
            )
        raise
    try:
        result = kg_sync.merge_synced_local_kg(
            uid,
            payload.table,
            payload.rows,
            payload.source_namespace,
            reconcile_complete=payload.reconcile_complete,
        )
    except (kg_sync.MissingKnowledgeGraphEndpointsError, kg_db.InvalidKnowledgeGraphDocumentIdError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    return LocalKgSyncResponse(**result)
