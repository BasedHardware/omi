import importlib
import sys

from fastapi import APIRouter, Depends, BackgroundTasks
from pydantic import BaseModel
from typing import List, Dict, Any, Callable, cast

from database import knowledge_graph as kg_db
from database import memories as memories_db
from database._client import db as firestore_db
from database.auth import get_user_name
from utils.memory.memory_service import MemoryService
from utils.memory.memory_system import MemorySystem
from utils.memory.surface_routing import pin_memory_system
from utils.other import endpoints as auth

router = APIRouter()
Payload = Dict[str, Any]
MemoryPayloads = List[Payload]
KnowledgeGraphLoader = Callable[[str], Payload]
RateLimitFactory = Callable[[Any, str], Any]
RebuildKnowledgeGraph = Callable[[str, MemoryPayloads, str], Payload]
get_knowledge_graph_payload: KnowledgeGraphLoader = cast(KnowledgeGraphLoader, getattr(kg_db, "get_knowledge_graph"))
with_rate_limit: RateLimitFactory = cast(RateLimitFactory, getattr(auth, "with_rate_limit"))


def _knowledge_graph_llm_module() -> Any:
    return sys.modules.get("utils.llm.knowledge_graph") or importlib.import_module("utils.llm.knowledge_graph")


def _run_rebuild_knowledge_graph(uid: str, memories: MemoryPayloads, user_name: str) -> Payload:
    rebuild_knowledge_graph = cast(
        RebuildKnowledgeGraph, getattr(_knowledge_graph_llm_module(), "rebuild_knowledge_graph")
    )
    return rebuild_knowledge_graph(uid, memories, user_name)


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


class RebuildResponse(BaseModel):
    status: str
    nodes_count: int
    edges_count: int


class DeleteKnowledgeGraphResponse(BaseModel):
    status: str


@router.get('/v1/knowledge-graph', tags=['knowledge_graph'], response_model=KnowledgeGraphResponse)
def get_knowledge_graph(uid: str = Depends(auth.get_current_user_uid)):
    graph = get_knowledge_graph_payload(uid)
    return KnowledgeGraphResponse(nodes=graph.get('nodes', []), edges=graph.get('edges', []))


def _rebuild_graph_task(uid: str, user_name: str):
    memory_system = pin_memory_system(uid, db_client=firestore_db)
    if memory_system == MemorySystem.CANONICAL:
        memory_objects = MemoryService(db_client=firestore_db).read(uid, limit=500)
        memories: MemoryPayloads = [
            {"id": memory.id, "content": memory.content}
            for memory in memory_objects
            if not getattr(memory, "is_locked", False)
        ]
    else:
        legacy_memories: MemoryPayloads = memories_db.get_memories(uid, limit=500)
        memories = [memory for memory in legacy_memories if not memory.get('is_locked', False)]
    _run_rebuild_knowledge_graph(uid, memories, user_name)


@router.post('/v1/knowledge-graph/rebuild', tags=['knowledge_graph'], response_model=RebuildResponse)
def rebuild_graph(
    background_tasks: BackgroundTasks,
    uid: str = Depends(with_rate_limit(auth.get_current_user_uid, "knowledge_graph:rebuild")),
):
    user_name = get_user_name(uid) or ""

    kg_db.delete_knowledge_graph(uid)

    background_tasks.add_task(_rebuild_graph_task, uid, user_name)

    return RebuildResponse(status="rebuilding", nodes_count=0, edges_count=0)


@router.delete('/v1/knowledge-graph', tags=['knowledge_graph'], response_model=DeleteKnowledgeGraphResponse)
def delete_knowledge_graph(uid: str = Depends(auth.get_current_user_uid)):
    kg_db.delete_knowledge_graph(uid)
    return {"status": "deleted"}
