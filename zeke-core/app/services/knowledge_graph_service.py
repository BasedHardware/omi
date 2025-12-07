from typing import List, Optional, Dict, Any, Tuple, Set
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_, or_, func
import logging
import json
import re

from ..models.knowledge_graph import (
    EntityDB, RelationshipDB, EntityType, RelationType,
    EntityResponse, RelationshipResponse, EntityWithRelations,
    GraphQueryResult, ExtractedEntity, ExtractedRelation
)
from ..integrations.openai import OpenAIClient
from ..core.database import get_db_context

logger = logging.getLogger(__name__)


ENTITY_EXTRACTION_PROMPT = """Analyze the following text and extract entities and their relationships.

Text to analyze:
{text}

Extract:
1. ENTITIES: People, organizations, locations, projects, topics, events, tasks, products, concepts
2. RELATIONSHIPS: How these entities relate to the user or each other

Return a JSON object with this exact structure:
{{
    "entities": [
        {{
            "name": "Entity Name",
            "entity_type": "person|organization|location|project|topic|event|task|product|concept|other",
            "description": "Brief description if available",
            "attributes": {{"key": "value"}},
            "confidence": 0.0-1.0
        }}
    ],
    "relations": [
        {{
            "source": "Source Entity Name",
            "target": "Target Entity Name", 
            "relation_type": "knows|works_with|works_at|manages|assigned_to|part_of|related_to|located_at|occurred_on|discussed|mentioned_in|created|owns|prefers|dislikes",
            "description": "How they're related",
            "properties": {{}},
            "confidence": 0.0-1.0
        }}
    ]
}}

Rules:
- Use "User" as entity name when the text refers to the user themselves
- Extract only clearly stated or strongly implied entities
- Be conservative with confidence scores
- Normalize names (e.g., "John" and "John Smith" should be the same if context implies it)

Return ONLY the JSON object, no other text."""


class KnowledgeGraphService:
    
    def __init__(self, openai_client: Optional[OpenAIClient] = None):
        self._openai = openai_client
        self._openai_initialized = openai_client is not None
    
    @property
    def openai(self) -> Optional[OpenAIClient]:
        if not self._openai_initialized:
            try:
                self._openai = OpenAIClient()
                self._openai_initialized = True
            except Exception as e:
                logger.warning(f"OpenAI client not available: {e}")
                self._openai = None
        return self._openai
    
    def _require_openai(self) -> OpenAIClient:
        client = self.openai
        if client is None:
            raise RuntimeError("OpenAI client is required but not available")
        return client
    
    def _normalize_name(self, name: str) -> str:
        normalized = name.lower().strip()
        normalized = re.sub(r'[^\w\s]', '', normalized)
        normalized = re.sub(r'\s+', ' ', normalized)
        return normalized
    
    async def extract_entities_and_relations(
        self,
        text: str,
        user_id: str,
        memory_id: Optional[str] = None
    ) -> Tuple[List[EntityDB], List[RelationshipDB]]:
        openai_client = self._require_openai()
        
        prompt = ENTITY_EXTRACTION_PROMPT.format(text=text[:4000])
        
        try:
            response = await openai_client.chat_completion([
                {"role": "user", "content": prompt}
            ], temperature=0.1, max_tokens=2000)
            
            content = response.choices[0].message.content.strip()
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            
            data = json.loads(content)
            
            entities_data = data.get("entities", [])
            relations_data = data.get("relations", [])
            
            created_entities = []
            entity_map = {}
            
            for ent_data in entities_data:
                entity = await self.create_or_update_entity(
                    user_id=user_id,
                    name=ent_data["name"],
                    entity_type=ent_data.get("entity_type", "other"),
                    description=ent_data.get("description"),
                    attributes=ent_data.get("attributes", {}),
                    confidence=ent_data.get("confidence", 0.8),
                    source_memory_id=memory_id
                )
                if entity:
                    created_entities.append(entity)
                    entity_map[self._normalize_name(ent_data["name"])] = entity
            
            created_relations = []
            for rel_data in relations_data:
                source_norm = self._normalize_name(rel_data["source"])
                target_norm = self._normalize_name(rel_data["target"])
                
                source_entity = entity_map.get(source_norm)
                target_entity = entity_map.get(target_norm)
                
                if not source_entity:
                    source_entity = await self.get_entity_by_name(user_id, rel_data["source"])
                if not target_entity:
                    target_entity = await self.get_entity_by_name(user_id, rel_data["target"])
                
                if source_entity and target_entity:
                    relation = await self.create_or_update_relationship(
                        user_id=user_id,
                        source_entity_id=source_entity.id,
                        target_entity_id=target_entity.id,
                        relation_type=rel_data.get("relation_type", "related_to"),
                        description=rel_data.get("description"),
                        properties=rel_data.get("properties", {}),
                        confidence=rel_data.get("confidence", 0.8),
                        source_memory_id=memory_id
                    )
                    if relation:
                        created_relations.append(relation)
            
            logger.info(f"Extracted {len(created_entities)} entities and {len(created_relations)} relations")
            return created_entities, created_relations
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse entity extraction response: {e}")
            return [], []
        except Exception as e:
            logger.error(f"Entity extraction failed: {e}")
            return [], []
    
    async def create_or_update_entity(
        self,
        user_id: str,
        name: str,
        entity_type: str,
        description: Optional[str] = None,
        attributes: Dict[str, Any] = None,
        confidence: float = 1.0,
        source_memory_id: Optional[str] = None
    ) -> Optional[EntityDB]:
        normalized_name = self._normalize_name(name)
        
        try:
            with get_db_context() as db:
                existing = db.query(EntityDB).filter(
                    EntityDB.uid == user_id,
                    EntityDB.normalized_name == normalized_name
                ).first()
                
                if existing:
                    existing.mention_count += 1
                    existing.last_mentioned = datetime.utcnow()
                    
                    if description and not existing.description:
                        existing.description = description
                    
                    if attributes:
                        current_attrs = existing.attributes or {}
                        current_attrs.update(attributes)
                        existing.attributes = current_attrs
                    
                    if source_memory_id:
                        memory_ids = existing.source_memory_ids or []
                        if source_memory_id not in memory_ids:
                            memory_ids.append(source_memory_id)
                            existing.source_memory_ids = memory_ids
                    
                    if name != existing.name:
                        aliases = existing.aliases or []
                        if name not in aliases and name != existing.name:
                            aliases.append(name)
                            existing.aliases = aliases
                    
                    db.flush()
                    db.refresh(existing)
                    return existing
                
                openai_client = self._require_openai()
                embedding = await openai_client.create_embedding(f"{name}: {description or entity_type}")
                
                entity = EntityDB(
                    uid=user_id,
                    name=name,
                    normalized_name=normalized_name,
                    entity_type=entity_type,
                    description=description,
                    attributes=attributes or {},
                    embedding=embedding,
                    confidence=confidence,
                    mention_count=1,
                    last_mentioned=datetime.utcnow(),
                    source_memory_ids=[source_memory_id] if source_memory_id else []
                )
                
                db.add(entity)
                db.flush()
                db.refresh(entity)
                return entity
                
        except Exception as e:
            logger.error(f"Failed to create/update entity: {e}")
            return None
    
    async def create_or_update_relationship(
        self,
        user_id: str,
        source_entity_id: str,
        target_entity_id: str,
        relation_type: str,
        description: Optional[str] = None,
        properties: Dict[str, Any] = None,
        confidence: float = 1.0,
        source_memory_id: Optional[str] = None
    ) -> Optional[RelationshipDB]:
        try:
            with get_db_context() as db:
                existing = db.query(RelationshipDB).filter(
                    RelationshipDB.uid == user_id,
                    RelationshipDB.source_entity_id == source_entity_id,
                    RelationshipDB.target_entity_id == target_entity_id,
                    RelationshipDB.relation_type == relation_type
                ).first()
                
                if existing:
                    existing.mention_count += 1
                    existing.strength = min(1.0, existing.strength + 0.1)
                    
                    if properties:
                        current_props = existing.properties or {}
                        current_props.update(properties)
                        existing.properties = current_props
                    
                    db.flush()
                    db.refresh(existing)
                    return existing
                
                relation = RelationshipDB(
                    uid=user_id,
                    source_entity_id=source_entity_id,
                    target_entity_id=target_entity_id,
                    relation_type=relation_type,
                    description=description,
                    properties=properties or {},
                    confidence=confidence,
                    source_memory_id=source_memory_id
                )
                
                db.add(relation)
                db.flush()
                db.refresh(relation)
                return relation
                
        except Exception as e:
            logger.error(f"Failed to create/update relationship: {e}")
            return None
    
    async def get_entity_by_name(
        self,
        user_id: str,
        name: str
    ) -> Optional[EntityDB]:
        normalized_name = self._normalize_name(name)
        
        with get_db_context() as db:
            entity = db.query(EntityDB).filter(
                EntityDB.uid == user_id,
                EntityDB.normalized_name == normalized_name
            ).first()
            return entity
    
    async def search_entities(
        self,
        user_id: str,
        query: str,
        entity_types: Optional[List[str]] = None,
        limit: int = 10
    ) -> List[EntityDB]:
        openai_client = self._require_openai()
        query_embedding = await openai_client.create_embedding(query)
        
        with get_db_context() as db:
            distance_col = EntityDB.embedding.cosine_distance(query_embedding).label('distance')
            
            base_query = db.query(EntityDB, distance_col).filter(
                EntityDB.uid == user_id,
                EntityDB.embedding.isnot(None)
            )
            
            if entity_types:
                base_query = base_query.filter(EntityDB.entity_type.in_(entity_types))
            
            results = base_query.order_by(distance_col).limit(limit).all()
            
            return [entity for entity, _ in results]
    
    async def get_entity_with_relations(
        self,
        user_id: str,
        entity_id: str,
        depth: int = 1
    ) -> Optional[EntityWithRelations]:
        with get_db_context() as db:
            entity = db.query(EntityDB).filter(
                EntityDB.id == entity_id,
                EntityDB.uid == user_id
            ).first()
            
            if not entity:
                return None
            
            outgoing = db.query(RelationshipDB).filter(
                RelationshipDB.uid == user_id,
                RelationshipDB.source_entity_id == entity_id
            ).all()
            
            incoming = db.query(RelationshipDB).filter(
                RelationshipDB.uid == user_id,
                RelationshipDB.target_entity_id == entity_id
            ).all()
            
            related_ids = set()
            for rel in outgoing:
                related_ids.add(rel.target_entity_id)
            for rel in incoming:
                related_ids.add(rel.source_entity_id)
            
            related_entities = []
            if related_ids:
                related_entities = db.query(EntityDB).filter(
                    EntityDB.id.in_(related_ids)
                ).all()
            
            return EntityWithRelations(
                id=entity.id,
                name=entity.name,
                entity_type=entity.entity_type,
                description=entity.description,
                attributes=entity.attributes or {},
                aliases=entity.aliases or [],
                mention_count=entity.mention_count,
                confidence=entity.confidence,
                created_at=entity.created_at,
                outgoing_relations=[RelationshipResponse.model_validate(r) for r in outgoing],
                incoming_relations=[RelationshipResponse.model_validate(r) for r in incoming],
                related_entities=[EntityResponse.model_validate(e) for e in related_entities]
            )
    
    async def traverse_graph(
        self,
        user_id: str,
        start_entity_id: str,
        relation_types: Optional[List[str]] = None,
        max_depth: int = 2,
        max_nodes: int = 20
    ) -> GraphQueryResult:
        visited_entities: Set[str] = set()
        visited_relations: Set[str] = set()
        all_entities: List[EntityDB] = []
        all_relationships: List[RelationshipDB] = []
        paths: List[List[str]] = []
        
        with get_db_context() as db:
            async def traverse(entity_id: str, current_path: List[str], depth: int):
                if depth > max_depth or len(visited_entities) >= max_nodes:
                    return
                
                if entity_id in visited_entities:
                    return
                
                visited_entities.add(entity_id)
                current_path = current_path + [entity_id]
                
                entity = db.query(EntityDB).filter(EntityDB.id == entity_id).first()
                if entity:
                    all_entities.append(entity)
                
                rel_query = db.query(RelationshipDB).filter(
                    RelationshipDB.uid == user_id,
                    or_(
                        RelationshipDB.source_entity_id == entity_id,
                        RelationshipDB.target_entity_id == entity_id
                    )
                )
                
                if relation_types:
                    rel_query = rel_query.filter(RelationshipDB.relation_type.in_(relation_types))
                
                relations = rel_query.all()
                
                for rel in relations:
                    if rel.id not in visited_relations:
                        visited_relations.add(rel.id)
                        all_relationships.append(rel)
                    
                    next_entity_id = (
                        rel.target_entity_id if rel.source_entity_id == entity_id
                        else rel.source_entity_id
                    )
                    
                    await traverse(next_entity_id, current_path, depth + 1)
                
                if len(current_path) > 1:
                    paths.append(current_path)
            
            await traverse(start_entity_id, [], 0)
        
        return GraphQueryResult(
            entities=[EntityResponse.model_validate(e) for e in all_entities],
            relationships=[RelationshipResponse.model_validate(r) for r in all_relationships],
            paths=paths,
            context=self._build_context_from_graph(all_entities, all_relationships)
        )
    
    def _build_context_from_graph(
        self,
        entities: List[EntityDB],
        relationships: List[RelationshipDB]
    ) -> str:
        if not entities:
            return ""
        
        entity_map = {e.id: e for e in entities}
        
        context_parts = []
        
        for entity in entities[:10]:
            parts = [f"- {entity.name} ({entity.entity_type})"]
            if entity.description:
                parts.append(f": {entity.description}")
            context_parts.append("".join(parts))
        
        if relationships:
            context_parts.append("\nRelationships:")
            for rel in relationships[:15]:
                source = entity_map.get(rel.source_entity_id)
                target = entity_map.get(rel.target_entity_id)
                if source and target:
                    rel_desc = rel.description or rel.relation_type.replace("_", " ")
                    context_parts.append(f"- {source.name} {rel_desc} {target.name}")
        
        return "\n".join(context_parts)
    
    async def graph_rag_search(
        self,
        user_id: str,
        query: str,
        limit: int = 5
    ) -> GraphQueryResult:
        relevant_entities = await self.search_entities(user_id, query, limit=limit)
        
        if not relevant_entities:
            return GraphQueryResult(context="No relevant entities found in knowledge graph.")
        
        all_entities = list(relevant_entities)
        all_relationships = []
        entity_ids = {e.id for e in relevant_entities}
        
        with get_db_context() as db:
            for entity in relevant_entities:
                rels = db.query(RelationshipDB).filter(
                    RelationshipDB.uid == user_id,
                    or_(
                        RelationshipDB.source_entity_id == entity.id,
                        RelationshipDB.target_entity_id == entity.id
                    )
                ).all()
                
                for rel in rels:
                    if rel not in all_relationships:
                        all_relationships.append(rel)
                    
                    other_id = (
                        rel.target_entity_id if rel.source_entity_id == entity.id
                        else rel.source_entity_id
                    )
                    
                    if other_id not in entity_ids:
                        other_entity = db.query(EntityDB).filter(
                            EntityDB.id == other_id
                        ).first()
                        if other_entity:
                            all_entities.append(other_entity)
                            entity_ids.add(other_id)
        
        return GraphQueryResult(
            entities=[EntityResponse.model_validate(e) for e in all_entities],
            relationships=[RelationshipResponse.model_validate(r) for r in all_relationships],
            paths=[],
            context=self._build_context_from_graph(all_entities, all_relationships)
        )
    
    async def get_user_stats(self, user_id: str) -> Dict[str, Any]:
        with get_db_context() as db:
            entity_count = db.query(func.count(EntityDB.id)).filter(
                EntityDB.uid == user_id
            ).scalar()
            
            relation_count = db.query(func.count(RelationshipDB.id)).filter(
                RelationshipDB.uid == user_id
            ).scalar()
            
            type_counts = db.query(
                EntityDB.entity_type,
                func.count(EntityDB.id)
            ).filter(
                EntityDB.uid == user_id
            ).group_by(EntityDB.entity_type).all()
            
            relation_type_counts = db.query(
                RelationshipDB.relation_type,
                func.count(RelationshipDB.id)
            ).filter(
                RelationshipDB.uid == user_id
            ).group_by(RelationshipDB.relation_type).all()
            
            top_entities = db.query(EntityDB).filter(
                EntityDB.uid == user_id
            ).order_by(desc(EntityDB.mention_count)).limit(10).all()
            
            return {
                "total_entities": entity_count,
                "total_relationships": relation_count,
                "entities_by_type": {t: c for t, c in type_counts},
                "relationships_by_type": {t: c for t, c in relation_type_counts},
                "top_entities": [
                    {"name": e.name, "type": e.entity_type, "mentions": e.mention_count}
                    for e in top_entities
                ]
            }
