from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any

from database import knowledge_graph as kg_db
from database import memories as memories_db
from database import users as users_db
from utils.llm.knowledge_graph import extract_knowledge_from_memory
from utils.other import endpoints as auth


router = APIRouter()


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
def get_knowledge_graph(uid: str = Depends(auth.get_current_user_uid)):
    graph = kg_db.get_knowledge_graph(uid)
    return KnowledgeGraphResponse(
        nodes=graph.get('nodes', []),
        edges=graph.get('edges', [])
    )





@router.delete('/v1/knowledge-graph', tags=['knowledge_graph'])
def delete_knowledge_graph(uid: str = Depends(auth.get_current_user_uid)):
    kg_db.delete_knowledge_graph(uid)
    return {"status": "deleted"}
