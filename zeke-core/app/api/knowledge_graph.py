from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import logging

from ..services.knowledge_graph_service import KnowledgeGraphService
from ..models.knowledge_graph import (
    EntityResponse, RelationshipResponse, EntityWithRelations,
    GraphQueryResult
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/graph", tags=["knowledge-graph"])


def get_graph_service() -> KnowledgeGraphService:
    return KnowledgeGraphService()


class EntityCreate(BaseModel):
    name: str
    entity_type: str
    description: Optional[str] = None
    attributes: Dict[str, Any] = {}


class RelationCreate(BaseModel):
    source_entity_id: str
    target_entity_id: str
    relation_type: str
    description: Optional[str] = None
    properties: Dict[str, Any] = {}


class ExtractRequest(BaseModel):
    text: str
    memory_id: Optional[str] = None


class GraphSearchRequest(BaseModel):
    query: str
    entity_types: Optional[List[str]] = None
    limit: int = 10


@router.post("/entities", response_model=EntityResponse)
async def create_entity(
    entity: EntityCreate,
    user_id: str = "default_user"
):
    service = get_graph_service()
    
    result = await service.create_or_update_entity(
        user_id=user_id,
        name=entity.name,
        entity_type=entity.entity_type,
        description=entity.description,
        attributes=entity.attributes
    )
    
    if not result:
        raise HTTPException(status_code=500, detail="Failed to create entity")
    
    return EntityResponse.model_validate(result)


@router.get("/entities/search", response_model=List[EntityResponse])
async def search_entities(
    query: str,
    entity_types: Optional[str] = None,
    limit: int = Query(default=10, le=50),
    user_id: str = "default_user"
):
    service = get_graph_service()
    
    types_list = entity_types.split(",") if entity_types else None
    
    results = await service.search_entities(
        user_id=user_id,
        query=query,
        entity_types=types_list,
        limit=limit
    )
    
    return [EntityResponse.model_validate(e) for e in results]


@router.get("/entities/{entity_id}", response_model=EntityWithRelations)
async def get_entity(
    entity_id: str,
    user_id: str = "default_user"
):
    service = get_graph_service()
    
    result = await service.get_entity_with_relations(
        user_id=user_id,
        entity_id=entity_id
    )
    
    if not result:
        raise HTTPException(status_code=404, detail="Entity not found")
    
    return result


@router.post("/relationships", response_model=RelationshipResponse)
async def create_relationship(
    relation: RelationCreate,
    user_id: str = "default_user"
):
    service = get_graph_service()
    
    result = await service.create_or_update_relationship(
        user_id=user_id,
        source_entity_id=relation.source_entity_id,
        target_entity_id=relation.target_entity_id,
        relation_type=relation.relation_type,
        description=relation.description,
        properties=relation.properties
    )
    
    if not result:
        raise HTTPException(status_code=500, detail="Failed to create relationship")
    
    return RelationshipResponse.model_validate(result)


@router.post("/extract", response_model=Dict[str, Any])
async def extract_from_text(
    request: ExtractRequest,
    user_id: str = "default_user"
):
    service = get_graph_service()
    
    entities, relations = await service.extract_entities_and_relations(
        text=request.text,
        user_id=user_id,
        memory_id=request.memory_id
    )
    
    return {
        "entities_created": len(entities),
        "relationships_created": len(relations),
        "entities": [EntityResponse.model_validate(e) for e in entities],
        "relationships": [RelationshipResponse.model_validate(r) for r in relations]
    }


@router.get("/traverse/{entity_id}", response_model=GraphQueryResult)
async def traverse_graph(
    entity_id: str,
    relation_types: Optional[str] = None,
    max_depth: int = Query(default=2, le=4),
    max_nodes: int = Query(default=20, le=50),
    user_id: str = "default_user"
):
    service = get_graph_service()
    
    types_list = relation_types.split(",") if relation_types else None
    
    result = await service.traverse_graph(
        user_id=user_id,
        start_entity_id=entity_id,
        relation_types=types_list,
        max_depth=max_depth,
        max_nodes=max_nodes
    )
    
    return result


@router.post("/search", response_model=GraphQueryResult)
async def graph_rag_search(
    request: GraphSearchRequest,
    user_id: str = "default_user"
):
    service = get_graph_service()
    
    result = await service.graph_rag_search(
        user_id=user_id,
        query=request.query,
        limit=request.limit
    )
    
    return result


@router.get("/stats", response_model=Dict[str, Any])
async def get_graph_stats(
    user_id: str = "default_user"
):
    service = get_graph_service()
    return await service.get_user_stats(user_id)
