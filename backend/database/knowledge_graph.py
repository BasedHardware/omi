from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
import uuid

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

from ._client import db

users_collection = 'users'
knowledge_nodes_collection = 'knowledge_nodes'
knowledge_edges_collection = 'knowledge_edges'


class KnowledgeNode:
    def __init__(
        self,
        id: str,
        label: str,
        node_type: str = 'concept',
        aliases: List[str] = None,
        memory_ids: List[str] = None,
        created_at: datetime = None,
        updated_at: datetime = None,
    ):
        self.id = id
        self.label = label
        self.node_type = node_type
        self.aliases = aliases or []
        self.memory_ids = memory_ids or []
        self.created_at = created_at or datetime.now(timezone.utc)
        self.updated_at = updated_at or datetime.now(timezone.utc)
        self.label_lower = label.lower() if label else ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'label': self.label,
            'node_type': self.node_type,
            'aliases': self.aliases,
            'memory_ids': self.memory_ids,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'label_lower': self.label_lower,
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'KnowledgeNode':
        return KnowledgeNode(
            id=data.get('id'),
            label=data.get('label'),
            node_type=data.get('node_type', 'concept'),
            aliases=data.get('aliases', []),
            memory_ids=data.get('memory_ids', []),
            created_at=data.get('created_at'),
            updated_at=data.get('updated_at'),
        )


class KnowledgeEdge:
    def __init__(
        self,
        id: str,
        source_id: str,
        target_id: str,
        label: str,
        memory_ids: List[str] = None,
        created_at: datetime = None,
    ):
        self.id = id
        self.source_id = source_id
        self.target_id = target_id
        self.label = label
        self.memory_ids = memory_ids or []
        self.created_at = created_at or datetime.now(timezone.utc)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'source_id': self.source_id,
            'target_id': self.target_id,
            'label': self.label,
            'memory_ids': self.memory_ids,
            'created_at': self.created_at,
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'KnowledgeEdge':
        return KnowledgeEdge(
            id=data.get('id'),
            source_id=data.get('source_id'),
            target_id=data.get('target_id'),
            label=data.get('label'),
            memory_ids=data.get('memory_ids', []),
            created_at=data.get('created_at'),
        )




def get_knowledge_nodes(uid: str) -> List[Dict[str, Any]]:
    user_ref = db.collection(users_collection).document(uid)
    nodes_ref = user_ref.collection(knowledge_nodes_collection)
    return [doc.to_dict() for doc in nodes_ref.stream()]


def get_knowledge_node(uid: str, node_id: str) -> Optional[Dict[str, Any]]:
    user_ref = db.collection(users_collection).document(uid)
    node_ref = user_ref.collection(knowledge_nodes_collection).document(node_id)
    doc = node_ref.get()
    return doc.to_dict() if doc.exists else None


def upsert_knowledge_node(uid: str, node_data: Dict[str, Any]) -> Dict[str, Any]:
    user_ref = db.collection(users_collection).document(uid)
    nodes_ref = user_ref.collection(knowledge_nodes_collection)
    
    node_id = node_data.get('id')
    if not node_id:
        existing_node = find_node_by_label_or_alias(uid, node_data.get('label', ''))
        if existing_node:
            node_id = existing_node['id']
            node_data['id'] = node_id
        else:
            node_id = str(uuid.uuid4())
        node_data['id'] = node_id
    
    node_ref = nodes_ref.document(node_id)
    existing = node_ref.get()
    
    if not existing.exists:
        existing_node_by_label = find_node_by_label_or_alias(uid, node_data.get('label', ''))
        if existing_node_by_label:
            node_id = existing_node_by_label['id']
            node_data['id'] = node_id
            node_ref = nodes_ref.document(node_id)
            existing = node_ref.get()

    if existing.exists:
        existing_data = existing.to_dict()
        existing_memory_ids = set(existing_data.get('memory_ids', []))
        new_memory_ids = set(node_data.get('memory_ids', []))
        merged_memory_ids = list(existing_memory_ids | new_memory_ids)
        
        existing_aliases = set(existing_data.get('aliases', []))
        new_aliases = set(node_data.get('aliases', []))
        merged_aliases = list(existing_aliases | new_aliases)
        
        node_data['memory_ids'] = merged_memory_ids
        node_data['aliases'] = merged_aliases
        node_data['updated_at'] = datetime.now(timezone.utc)
        node_data['created_at'] = existing_data.get('created_at', datetime.now(timezone.utc))
        node_data['label_lower'] = node_data.get('label', '').lower()
        node_data['aliases_lower'] = [a.lower() for a in node_data.get('aliases', [])]
    else:
        node_data['created_at'] = datetime.now(timezone.utc)
        node_data['updated_at'] = datetime.now(timezone.utc)
        node_data['label_lower'] = node_data.get('label', '').lower()
        node_data['aliases_lower'] = [a.lower() for a in node_data.get('aliases', [])]
    
    node_ref.set(node_data)
    return node_data


def find_node_by_label_or_alias(uid: str, label: str) -> Optional[Dict[str, Any]]:
    if not label:
        return None
        
    nodes_ref = db.collection(users_collection).document(uid).collection(knowledge_nodes_collection)
    label_lower = label.lower()
    
    query = nodes_ref.where(filter=FieldFilter('label_lower', '==', label_lower)).limit(1)
    results = list(query.stream())
    if results:
        return results[0].to_dict()
    
    query = nodes_ref.where(filter=FieldFilter('aliases_lower', 'array_contains', label_lower)).limit(1)
    results = list(query.stream())
    if results:
        return results[0].to_dict()
    
    return None




def get_knowledge_edges(uid: str) -> List[Dict[str, Any]]:
    user_ref = db.collection(users_collection).document(uid)
    edges_ref = user_ref.collection(knowledge_edges_collection)
    return [doc.to_dict() for doc in edges_ref.stream()]


def upsert_knowledge_edge(uid: str, edge_data: Dict[str, Any]) -> Dict[str, Any]:
    user_ref = db.collection(users_collection).document(uid)
    edges_ref = user_ref.collection(knowledge_edges_collection)
    
    edge_id = edge_data.get('id')
    if not edge_id:
        edge_id = f"{edge_data['source_id']}_{edge_data['label']}_{edge_data['target_id']}"
        edge_data['id'] = edge_id
    
    edge_ref = edges_ref.document(edge_id)
    existing = edge_ref.get()
    
    if existing.exists:
        existing_data = existing.to_dict()
        existing_memory_ids = set(existing_data.get('memory_ids', []))
        new_memory_ids = set(edge_data.get('memory_ids', []))
        merged_memory_ids = list(existing_memory_ids | new_memory_ids)
        
        edge_data['memory_ids'] = merged_memory_ids
        edge_data['created_at'] = existing_data.get('created_at', datetime.now(timezone.utc))
    else:
        edge_data['created_at'] = datetime.now(timezone.utc)
    
    edge_ref.set(edge_data)
    return edge_data




def get_knowledge_graph(uid: str) -> Dict[str, Any]:
    return {
        'nodes': get_knowledge_nodes(uid),
        'edges': get_knowledge_edges(uid),
    }


def delete_knowledge_graph(uid: str) -> None:
    user_ref = db.collection(users_collection).document(uid)
    
    def _batch_delete(coll_ref):
        while True:
            docs = list(coll_ref.limit(500).stream())
            if not docs:
                break
            batch = db.batch()
            for doc in docs:
                batch.delete(doc.reference)
            batch.commit()
    
    nodes_ref = user_ref.collection(knowledge_nodes_collection)
    _batch_delete(nodes_ref)
    
    edges_ref = user_ref.collection(knowledge_edges_collection)
    _batch_delete(edges_ref)
