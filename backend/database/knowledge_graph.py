from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, TypedDict, cast
import uuid

from google.cloud.firestore_v1 import FieldFilter

from ._client import db

users_collection = 'users'
knowledge_nodes_collection = 'knowledge_nodes'
knowledge_edges_collection = 'knowledge_edges'


def _firestore_client(db_client: Any = None) -> Any:
    return db_client if db_client is not None else db


def _typed_doc(doc: Any) -> Dict[str, Any]:
    raw: object = doc.to_dict()
    return cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}


class KnowledgeNodeDoc(TypedDict, total=False):
    id: str
    label: str
    node_type: str
    aliases: List[str]
    aliases_lower: List[str]
    label_lower: str
    memory_ids: List[str]
    created_at: datetime
    updated_at: datetime


class KnowledgeEdgeDoc(TypedDict, total=False):
    id: str
    source_id: str
    target_id: str
    label: str
    relationship: str
    memory_ids: List[str]
    created_at: datetime


class KnowledgeNode:
    def __init__(
        self,
        id: str,
        label: str,
        node_type: str = 'concept',
        aliases: Optional[List[str]] = None,
        memory_ids: Optional[List[str]] = None,
        created_at: Optional[datetime] = None,
        updated_at: Optional[datetime] = None,
    ) -> None:
        self.id = id
        self.label = label
        self.node_type = node_type
        self.aliases: List[str] = aliases or []
        self.memory_ids: List[str] = memory_ids or []
        self.created_at: datetime = created_at or datetime.now(timezone.utc)
        self.updated_at: datetime = updated_at or datetime.now(timezone.utc)
        self.label_lower: str = label.lower() if label else ""

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
            id=cast(str, data.get('id')),
            label=cast(str, data.get('label')),
            node_type=cast(str, data.get('node_type', 'concept')),
            aliases=cast(Optional[List[str]], data.get('aliases', [])),
            memory_ids=cast(Optional[List[str]], data.get('memory_ids', [])),
            created_at=cast(Optional[datetime], data.get('created_at')),
            updated_at=cast(Optional[datetime], data.get('updated_at')),
        )


class KnowledgeEdge:
    def __init__(
        self,
        id: str,
        source_id: str,
        target_id: str,
        label: str,
        memory_ids: Optional[List[str]] = None,
        created_at: Optional[datetime] = None,
    ) -> None:
        self.id = id
        self.source_id = source_id
        self.target_id = target_id
        self.label = label
        self.memory_ids: List[str] = memory_ids or []
        self.created_at: datetime = created_at or datetime.now(timezone.utc)

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
            id=cast(str, data.get('id')),
            source_id=cast(str, data.get('source_id')),
            target_id=cast(str, data.get('target_id')),
            label=cast(str, data.get('label')),
            memory_ids=cast(Optional[List[str]], data.get('memory_ids', [])),
            created_at=cast(Optional[datetime], data.get('created_at')),
        )


def get_knowledge_nodes(uid: str, *, db_client: Any = None) -> List[Dict[str, Any]]:
    client = _firestore_client(db_client)
    user_ref = client.collection(users_collection).document(uid)
    nodes_ref = user_ref.collection(knowledge_nodes_collection)
    return [_typed_doc(doc) for doc in nodes_ref.stream()]


def get_knowledge_node(uid: str, node_id: str, *, db_client: Any = None) -> Optional[Dict[str, Any]]:
    client = _firestore_client(db_client)
    user_ref = client.collection(users_collection).document(uid)
    node_ref = user_ref.collection(knowledge_nodes_collection).document(node_id)
    doc = node_ref.get()
    if not doc.exists:
        return None
    return _typed_doc(doc)


def upsert_knowledge_node(uid: str, node_data: Dict[str, Any], *, db_client: Any = None) -> Dict[str, Any]:
    client = _firestore_client(db_client)
    user_ref = client.collection(users_collection).document(uid)
    nodes_ref = user_ref.collection(knowledge_nodes_collection)

    node_id = node_data.get('id')
    if not node_id:
        existing_node = find_node_by_label_or_alias(uid, node_data.get('label', ''), db_client=client)
        if existing_node:
            node_id = existing_node['id']
            node_data['id'] = node_id
        else:
            node_id = str(uuid.uuid4())
        node_data['id'] = node_id

    node_ref = nodes_ref.document(node_id)
    existing = node_ref.get()

    if not existing.exists:
        existing_node_by_label = find_node_by_label_or_alias(uid, node_data.get('label', ''), db_client=client)
        if existing_node_by_label:
            node_id = existing_node_by_label['id']
            node_data['id'] = node_id
            node_ref = nodes_ref.document(node_id)
            existing = node_ref.get()

    if existing.exists:
        existing_data: KnowledgeNodeDoc = cast(KnowledgeNodeDoc, _typed_doc(existing))
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


def find_node_by_label_or_alias(uid: str, label: str, *, db_client: Any = None) -> Optional[Dict[str, Any]]:
    if not label:
        return None

    client = _firestore_client(db_client)
    nodes_ref = client.collection(users_collection).document(uid).collection(knowledge_nodes_collection)
    label_lower = label.lower()

    query = nodes_ref.where(filter=FieldFilter('label_lower', '==', label_lower)).limit(1)
    results = list(query.stream())
    if results:
        return _typed_doc(results[0])

    query = nodes_ref.where(filter=FieldFilter('aliases_lower', 'array_contains', label_lower)).limit(1)
    results = list(query.stream())
    if results:
        return _typed_doc(results[0])

    return None


def get_knowledge_edges(uid: str, *, db_client: Any = None) -> List[Dict[str, Any]]:
    client = _firestore_client(db_client)
    user_ref = client.collection(users_collection).document(uid)
    edges_ref = user_ref.collection(knowledge_edges_collection)
    return [_typed_doc(doc) for doc in edges_ref.stream()]


def upsert_knowledge_edge(uid: str, edge_data: Dict[str, Any], *, db_client: Any = None) -> Dict[str, Any]:
    client = _firestore_client(db_client)
    user_ref = client.collection(users_collection).document(uid)
    edges_ref = user_ref.collection(knowledge_edges_collection)

    edge_id = edge_data.get('id')
    if not edge_id:
        edge_id = f"{edge_data['source_id']}_{edge_data['label']}_{edge_data['target_id']}"
    edge_id = edge_id.replace('/', '_')
    edge_data['id'] = edge_id

    edge_ref = edges_ref.document(edge_id)
    existing = edge_ref.get()

    if existing.exists:
        existing_data: KnowledgeEdgeDoc = cast(KnowledgeEdgeDoc, _typed_doc(existing))
        existing_memory_ids = set(existing_data.get('memory_ids', []))
        new_memory_ids = set(edge_data.get('memory_ids', []))
        merged_memory_ids = list(existing_memory_ids | new_memory_ids)

        edge_data['memory_ids'] = merged_memory_ids
        edge_data['created_at'] = existing_data.get('created_at', datetime.now(timezone.utc))
    else:
        edge_data['created_at'] = datetime.now(timezone.utc)

    edge_ref.set(edge_data)
    return edge_data


def get_knowledge_graph(uid: str, *, db_client: Any = None) -> Dict[str, Any]:
    client = _firestore_client(db_client)
    return {
        'nodes': get_knowledge_nodes(uid, db_client=client),
        'edges': get_knowledge_edges(uid, db_client=client),
    }


def delete_knowledge_graph(uid: str, *, db_client: Any = None) -> None:
    client = _firestore_client(db_client)
    user_ref = client.collection(users_collection).document(uid)

    def _batch_delete(coll_ref: Any) -> None:
        while True:
            docs: List[Any] = list(coll_ref.limit(500).stream())
            if not docs:
                break
            batch: Any = client.batch()
            for doc in docs:
                batch.delete(doc.reference)
            batch.commit()

    nodes_ref = user_ref.collection(knowledge_nodes_collection)
    _batch_delete(nodes_ref)

    edges_ref = user_ref.collection(knowledge_edges_collection)
    _batch_delete(edges_ref)


def prune_memory_citations_from_kg(uid: str, memory_ids: List[str], *, db_client: Any = None) -> int:
    """Remove memory_ids from KG nodes/edges; delete entities with no remaining citations."""
    if not memory_ids:
        return 0
    retracted = set(memory_ids)
    client = _firestore_client(db_client)
    user_ref = client.collection(users_collection).document(uid)
    nodes_ref = user_ref.collection(knowledge_nodes_collection)
    edges_ref = user_ref.collection(knowledge_edges_collection)
    pruned = 0

    for doc in nodes_ref.stream():
        node_doc: KnowledgeNodeDoc = cast(KnowledgeNodeDoc, _typed_doc(doc))
        existing_ids = set(node_doc.get("memory_ids") or [])
        if not existing_ids.intersection(retracted):
            continue
        remaining = sorted(existing_ids - retracted)
        if remaining:
            doc.reference.set(
                {**node_doc, "memory_ids": remaining, "updated_at": datetime.now(timezone.utc)}, merge=True
            )
        else:
            doc.reference.delete()
        pruned += 1

    surviving_node_ids: set[str] = {cast(str, doc.id) for doc in nodes_ref.stream()}

    for doc in edges_ref.stream():
        edge_doc: KnowledgeEdgeDoc = cast(KnowledgeEdgeDoc, _typed_doc(doc))
        source_id = edge_doc.get("source_id")
        target_id = edge_doc.get("target_id")
        if source_id not in surviving_node_ids or target_id not in surviving_node_ids:
            doc.reference.delete()
            pruned += 1
            continue
        existing_ids = set(edge_doc.get("memory_ids") or [])
        if not existing_ids.intersection(retracted):
            continue
        remaining = sorted(existing_ids - retracted)
        if remaining:
            doc.reference.set({**edge_doc, "memory_ids": remaining}, merge=True)
        else:
            doc.reference.delete()
        pruned += 1

    return pruned
