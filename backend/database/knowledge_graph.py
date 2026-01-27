from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
import uuid

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter
from google.api_core import exceptions as google_exceptions

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


def cleanup_for_memory(uid: str, memory_id: str):
    """
    Removes a memory_id from all nodes and edges in the knowledge graph atomically.
    If a node or edge is no longer associated with any memories, it is deleted.
    Also removes edges that point to a deleted node.
    Handles Firestore query limits and atomicity using transactions.
    """
    try:
        user_ref = db.collection(users_collection).document(uid)
        
        @firestore.transactional
        def update_in_transaction(transaction, nodes_to_delete_ids):
            # Fetch nodes and edges that currently contain memory_id
            nodes_query = user_ref.collection(knowledge_nodes_collection).where(filter=FieldFilter('memory_ids', 'array_contains', memory_id))
            edges_query = user_ref.collection(knowledge_edges_collection).where(filter=FieldFilter('memory_ids', 'array_contains', memory_id))

            # Fetch relevant documents within the transaction
            nodes_docs = list(nodes_query.stream())
            edges_docs = list(edges_query.stream())

            # Track nodes that will be deleted to clean up related edges
            nodes_fully_deleted_in_this_tx = set()

            # Process Nodes
            for doc in nodes_docs:
                node_data = doc.to_dict()
                memory_ids = node_data.get('memory_ids', [])
                
                if len(memory_ids) == 1 and memory_ids[0] == memory_id:
                    # Node will be deleted as this is its only remaining memory_id
                    transaction.delete(doc.reference)
                    nodes_fully_deleted_in_this_tx.add(doc.id)
                else:
                    # Only remove the memory_id
                    transaction.update(doc.reference, {'memory_ids': firestore.ArrayRemove([memory_id])})

            # Process Edges (those explicitly linked to this memory_id)
            for doc in edges_docs:
                edge_data = doc.to_dict()
                memory_ids = edge_data.get('memory_ids', [])
                
                if len(memory_ids) == 1 and memory_ids[0] == memory_id:
                    # Edge will be deleted as this is its only remaining memory_id
                    transaction.delete(doc.reference)
                else:
                    # Only remove the memory_id
                    transaction.update(doc.reference, {'memory_ids': firestore.ArrayRemove([memory_id])})

            # Process potentially orphaned edges (those whose source/target nodes are deleted in this transaction)
            if nodes_fully_deleted_in_this_tx:
                # Firestore 'in' query limit is 10, so chunk the node IDs if necessary
                chunk_size = 10
                nodes_chunks = [list(nodes_fully_deleted_in_this_tx)[i:i + chunk_size] for i in range(0, len(nodes_fully_deleted_in_this_tx), chunk_size)]

                for chunk in nodes_chunks:
                    # Delete edges where source node is in the chunk
                    source_edges_query = user_ref.collection(knowledge_edges_collection).where(filter=FieldFilter('source_id', 'in', chunk))
                    for doc in source_edges_query.stream():
                        transaction.delete(doc.reference)
                    
                    # Delete edges where target node is in the chunk
                    target_edges_query = user_ref.collection(knowledge_edges_collection).where(filter=FieldFilter('target_id', 'in', chunk))
                    for doc in target_edges_query.stream():
                        transaction.delete(doc.reference)
            
            print(f"Knowledge graph transaction complete for memory_id: {memory_id}")

        # Run the transaction
        transaction = db.transaction()
        update_in_transaction(transaction, set()) # Pass an empty set for initial call. Nodes to delete are determined inside.

    except google_exceptions.GoogleAPICallError as e:
        print(f"ERROR: Firestore API error during KG cleanup for memory_id {memory_id}: {e}")
        raise # Re-raise to indicate a critical failure

    except ValueError as e:
        print(f"ERROR: Data validation error during KG cleanup for memory_id {memory_id}: {e}")
        raise # Re-raise to indicate a critical failure
    
    except Exception as e: # Catch any other unexpected errors
        print(f"ERROR: Unexpected error during KG cleanup for memory_id {memory_id}: {e}")
        raise # Re-raise to indicate a critical failure
