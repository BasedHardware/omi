from fastapi import Request, APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import List, Dict, Any

from database import knowledge_graph as kg_db
from database import memories as memories_db
from database._client import db as firestore_db
from database.auth import get_user_name
from utils.llm.knowledge_graph import extract_knowledge_from_memory, rebuild_knowledge_graph
from utils.memory.memory_service import MemoryService
from utils.memory.memory_system import MemorySystem
from utils.memory.surface_routing import pin_memory_system
from utils.other.endpoints import rate_limit_dep
from utils.auth_middleware import require_firebase

router = APIRouter(dependencies=[Depends(require_firebase)])


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


@router.get('/v1/knowledge-graph', tags=['knowledge_graph'], response_model=KnowledgeGraphResponse)
def get_knowledge_graph(request: Request):
    uid = request.state.uid
    graph = kg_db.get_knowledge_graph(uid)
    return KnowledgeGraphResponse(nodes=graph.get('nodes', []), edges=graph.get('edges', []))


def _rebuild_graph_task(uid: str, user_name: str):
    memory_system = pin_memory_system(uid, db_client=firestore_db)
    if memory_system == MemorySystem.CANONICAL:
        memory_objects = MemoryService(db_client=firestore_db).read(uid, limit=500)
        memories = [
            {"id": memory.id, "content": memory.content}
            for memory in memory_objects
            if not getattr(memory, "is_locked", False)
        ]
    else:
        memories = memories_db.get_memories(uid, limit=500)
        memories = [m for m in memories if not m.get('is_locked', False)]
    rebuild_knowledge_graph(uid, memories, user_name)


@router.post(
    '/v1/knowledge-graph/rebuild',
    tags=['knowledge_graph'],
    response_model=RebuildResponse,
    dependencies=[Depends(rate_limit_dep("knowledge_graph:rebuild"))],
)
def rebuild_graph(request: Request, background_tasks: BackgroundTasks):
    uid = request.state.uid
    user_name = get_user_name(uid)

    kg_db.delete_knowledge_graph(uid)

    background_tasks.add_task(_rebuild_graph_task, uid, user_name)

    return RebuildResponse(status="rebuilding", nodes_count=0, edges_count=0)


@router.delete('/v1/knowledge-graph', tags=['knowledge_graph'])
def delete_knowledge_graph(request: Request):
    uid = request.state.uid
    kg_db.delete_knowledge_graph(uid)
    return {"status": "deleted"}
