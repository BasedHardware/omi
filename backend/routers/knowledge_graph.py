import importlib
import sys

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel
from typing import List, Dict, Any, Callable, Optional, cast

from database import knowledge_graph as kg_db
from database import memories as memories_db
from database._client import db as firestore_db
from database.auth import get_user_name
from utils.memory import canonical_graph as canonical_graph_service
from utils.memory.memory_system import MemorySystem
from utils.memory.surface_routing import pin_memory_system
from utils.other import endpoints as auth

router = APIRouter()
Payload = Dict[str, Any]
MemoryPayloads = List[Payload]
KnowledgeGraphLoader = Callable[[str], Payload]
CanonicalKnowledgeGraphLoader = Callable[..., Payload]
RateLimitFactory = Callable[[Any, str], Any]
RebuildKnowledgeGraph = Callable[[str, MemoryPayloads, str], Payload]
get_knowledge_graph_payload: KnowledgeGraphLoader = cast(KnowledgeGraphLoader, getattr(kg_db, "get_knowledge_graph"))
get_canonical_knowledge_graph_payload: CanonicalKnowledgeGraphLoader = cast(
    CanonicalKnowledgeGraphLoader,
    getattr(canonical_graph_service, "get_canonical_knowledge_graph"),
)
with_rate_limit: RateLimitFactory = cast(RateLimitFactory, getattr(auth, "with_rate_limit"))
CANONICAL_GRAPH_MUTATION_CONFLICT = (
    "Canonical knowledge graph state is derived from canonical memories and cannot be deleted or rebuilt directly."
)


def _knowledge_graph_llm_module() -> Any:
    return sys.modules.get("utils.llm.knowledge_graph") or importlib.import_module("utils.llm.knowledge_graph")


def _run_rebuild_knowledge_graph(uid: str, memories: MemoryPayloads, user_name: str) -> Payload:
    rebuild_knowledge_graph = cast(
        RebuildKnowledgeGraph, getattr(_knowledge_graph_llm_module(), "rebuild_knowledge_graph")
    )
    return rebuild_knowledge_graph(uid, memories, user_name)


def _is_assertion_backed_graph_account(uid: str) -> bool:
    if pin_memory_system(uid, db_client=firestore_db) == MemorySystem.CANONICAL:
        return True
    return kg_db.has_stored_memory_graph_assertions(uid, db_client=firestore_db)


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


class RebuildResponse(BaseModel):
    status: str
    nodes_count: int
    edges_count: int


class DeleteKnowledgeGraphResponse(BaseModel):
    status: str


@router.get('/v1/knowledge-graph', tags=['knowledge_graph'], response_model=KnowledgeGraphResponse)
def get_knowledge_graph(uid: str = Depends(auth.get_current_user_uid)):
    graph = get_knowledge_graph_payload(uid)
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
    )


def _rebuild_graph_task(uid: str, user_name: str):
    if _is_assertion_backed_graph_account(uid):
        return
    legacy_memories: MemoryPayloads = memories_db.get_memories(uid, limit=500)
    memories = [memory for memory in legacy_memories if not memory.get('is_locked', False)]
    if _is_assertion_backed_graph_account(uid):
        return
    _run_rebuild_knowledge_graph(uid, memories, user_name)


@router.post('/v1/knowledge-graph/rebuild', tags=['knowledge_graph'], response_model=RebuildResponse)
def rebuild_graph(
    background_tasks: BackgroundTasks,
    uid: str = Depends(with_rate_limit(auth.get_current_user_uid, "knowledge_graph:rebuild")),
):
    _require_legacy_graph_mutation(uid)
    user_name = get_user_name(uid) or ""

    kg_db.delete_knowledge_graph(uid)

    background_tasks.add_task(_rebuild_graph_task, uid, user_name)

    return RebuildResponse(status="rebuilding", nodes_count=0, edges_count=0)


@router.delete('/v1/knowledge-graph', tags=['knowledge_graph'], response_model=DeleteKnowledgeGraphResponse)
def delete_knowledge_graph(uid: str = Depends(auth.get_current_user_uid)):
    _require_legacy_graph_mutation(uid)
    kg_db.delete_knowledge_graph(uid)
    return {"status": "deleted"}
