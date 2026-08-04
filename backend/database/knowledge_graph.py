from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple, TypedDict, cast
import uuid

from google.cloud.firestore_v1 import FieldFilter

from models.memory_contracts import deterministic_contract_id
from models.memory_promotion import MemoryGraphAssertion
from models.product_memory import RESTRICTED_SENSITIVITY_LABELS

from ._client import db
from .read_boundary import parse_snapshot_or_none

users_collection = 'users'
knowledge_nodes_collection = 'knowledge_nodes'
knowledge_edges_collection = 'knowledge_edges'
memory_graph_assertions_collection = 'memory_graph_assertions'
memory_items_collection = 'memory_items'

# GET /v1/knowledge-graph feeds force-graph UIs, so a compact snapshot is both
# cheaper to read and more usable than thousands of rendered entities. The
# previous 2,000-node / 5,000-edge bounds still produced prod 30s GET 504s.
MAX_KNOWLEDGE_GRAPH_NODES = 500
MAX_KNOWLEDGE_GRAPH_EDGES = 1000
MAX_KNOWLEDGE_GRAPH_ASSERTIONS = 500
MAX_KNOWLEDGE_GRAPH_CITATION_FENCES = 500
MEMORY_GRAPH_ASSERTION_BATCH_SIZE = 100
KNOWLEDGE_GRAPH_DOCUMENT_ORDER = '__name__'


def _firestore_client(db_client: Any = None) -> Any:
    return db_client if db_client is not None else db


def delete_memory_graph_assertion(uid: str, memory_id: str, *, db_client: Any = None) -> None:
    """Delete one derived assertion after its authoritative memory is fenced."""
    if not uid.strip() or not memory_id.strip():
        raise ValueError("uid and memory_id are required")
    client = _firestore_client(db_client)
    client.document(f"{users_collection}/{uid}/{memory_graph_assertions_collection}/{memory_id}").delete()


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


def get_knowledge_nodes(
    uid: str,
    *,
    db_client: Any = None,
    limit: int = MAX_KNOWLEDGE_GRAPH_NODES,
) -> List[Dict[str, Any]]:
    client = _firestore_client(db_client)
    user_ref = client.collection(users_collection).document(uid)
    nodes_ref = user_ref.collection(knowledge_nodes_collection)
    # Allow callers (get_knowledge_graph) to request one past the public cap for truncation probes.
    capped = max(0, min(int(limit), MAX_KNOWLEDGE_GRAPH_NODES + 1))
    if capped == 0:
        return []
    query = nodes_ref.order_by(KNOWLEDGE_GRAPH_DOCUMENT_ORDER).limit(capped)
    return [_typed_doc(doc) for doc in query.stream()]


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


def get_knowledge_edges(
    uid: str,
    *,
    db_client: Any = None,
    limit: int = MAX_KNOWLEDGE_GRAPH_EDGES,
) -> List[Dict[str, Any]]:
    client = _firestore_client(db_client)
    user_ref = client.collection(users_collection).document(uid)
    edges_ref = user_ref.collection(knowledge_edges_collection)
    capped = max(0, min(int(limit), MAX_KNOWLEDGE_GRAPH_EDGES + 1))
    if capped == 0:
        return []
    query = edges_ref.order_by(KNOWLEDGE_GRAPH_DOCUMENT_ORDER).limit(capped)
    return [_typed_doc(doc) for doc in query.stream()]


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


def _enum_value(value: Any) -> Any:
    return getattr(value, 'value', value)


def _string_values(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return sorted({item.strip() for item in cast(List[Any], value) if isinstance(item, str) and item.strip()})


def assertion_matches_active_item(
    uid: str,
    assertion: MemoryGraphAssertion,
    item: Dict[str, Any],
) -> bool:
    promotion = item.get('promotion')
    raw_evidence = item.get('evidence')
    evidence_ids = (
        sorted(
            {
                evidence_id
                for raw in cast(List[Any], raw_evidence)
                if isinstance(raw, dict)
                for evidence_id in [cast(Dict[str, Any], raw).get('evidence_id')]
                if isinstance(evidence_id, str) and evidence_id
            }
        )
        if isinstance(raw_evidence, list)
        else []
    )
    sensitivity_labels = {label.casefold() for label in _string_values(item.get('sensitivity_labels'))}
    return (
        item.get('uid') == uid
        and item.get('memory_id') == assertion.memory_id
        and _enum_value(item.get('status')) == 'active'
        and _enum_value(item.get('tier')) == 'long_term'
        and _enum_value(item.get('processing_state')) == 'processed'
        and _enum_value(item.get('source_state')) in {'active', 'missing'}
        and item.get('graph_ready') is True
        and item.get('graph_assertion_id') == assertion.assertion_id
        and item.get('graph_plan_hash') == assertion.graph_plan_hash
        and item.get('item_revision') == assertion.item_revision
        and item.get('content_hash') == assertion.content_hash
        and item.get('ledger_commit_id') == assertion.commit_id
        and item.get('ledger_sequence') == assertion.commit_sequence
        and item.get('subject_entity_id') == assertion.subject_entity_id
        and item.get('predicate') == assertion.predicate
        and item.get('arguments') == assertion.arguments
        and evidence_ids == assertion.evidence_ids
        and not sensitivity_labels.intersection(RESTRICTED_SENSITIVITY_LABELS)
        and not (isinstance(promotion, dict) and cast(Dict[str, Any], promotion).get('user_review') is False)
    )


def _memory_item_matches_account_generation(item: Dict[str, Any], account_generation: int) -> bool:
    item_account_generation = item.get('account_generation')
    return (
        not isinstance(item_account_generation, bool)
        and isinstance(item_account_generation, int)
        and item_account_generation == account_generation
    )


def _parse_assertion_snapshot(uid: str, snapshot: Any) -> Optional[MemoryGraphAssertion]:
    assertion = parse_snapshot_or_none(
        MemoryGraphAssertion,
        snapshot,
        payload_from_snapshot=_typed_doc,
    )
    if assertion is None:
        return None
    snapshot_id = getattr(snapshot, 'id', assertion.memory_id)
    if assertion.uid != uid or snapshot_id != assertion.memory_id:
        return None
    return assertion


def _chunked_get_all(client: Any, refs: List[Any], *, batch_size: int) -> Iterable[Any]:
    for start in range(0, len(refs), batch_size):
        yield from client.get_all(refs[start : start + batch_size])


def _load_assertions_by_memory_ids(
    uid: str,
    memory_ids: List[str],
    *,
    db_client: Any,
) -> Dict[str, MemoryGraphAssertion]:
    if not memory_ids:
        return {}
    client = _firestore_client(db_client)
    user_ref = client.collection(users_collection).document(uid)
    assertion_refs = [
        user_ref.collection(memory_graph_assertions_collection).document(memory_id) for memory_id in memory_ids
    ]
    assertions_by_id: Dict[str, MemoryGraphAssertion] = {}
    for snapshot in _chunked_get_all(client, assertion_refs, batch_size=MEMORY_GRAPH_ASSERTION_BATCH_SIZE):
        assertion = _parse_assertion_snapshot(uid, snapshot)
        if assertion is not None:
            assertions_by_id[assertion.memory_id] = assertion
    return assertions_by_id


def _load_memory_items_by_ids(
    uid: str,
    memory_ids: List[str],
    *,
    db_client: Any,
) -> Dict[str, Dict[str, Any]]:
    if not memory_ids:
        return {}
    client = _firestore_client(db_client)
    user_ref = client.collection(users_collection).document(uid)
    item_refs = [user_ref.collection(memory_items_collection).document(memory_id) for memory_id in memory_ids]
    items_by_id: Dict[str, Dict[str, Any]] = {}
    for snapshot in _chunked_get_all(client, item_refs, batch_size=MEMORY_GRAPH_ASSERTION_BATCH_SIZE):
        if not getattr(snapshot, 'exists', False):
            continue
        snapshot_id = getattr(snapshot, 'id', None)
        item = _typed_doc(snapshot)
        memory_id = item.get('memory_id')
        if not isinstance(snapshot_id, str) or not isinstance(memory_id, str) or snapshot_id != memory_id:
            continue
        items_by_id[memory_id] = item
    return items_by_id


def load_fenced_assertions_for_memory_items(
    uid: str,
    memory_ids: Iterable[str],
    *,
    account_generation: int,
    db_client: Any = None,
) -> List[MemoryGraphAssertion]:
    """Load assertions fenced to active memory items for explicit memory IDs.

    Callers provide memory_ids in the order they want results; only IDs that pass
    account_generation and active-item fencing are returned, in that same order.
    """
    ordered_ids = [memory_id for memory_id in memory_ids if memory_id.strip()]
    if not ordered_ids:
        return []
    unique_ids = list(dict.fromkeys(ordered_ids))
    client = _firestore_client(db_client)
    assertions_by_id = _load_assertions_by_memory_ids(uid, unique_ids, db_client=client)
    items_by_id = _load_memory_items_by_ids(uid, unique_ids, db_client=client)
    return [
        assertion
        for memory_id in ordered_ids
        if (assertion := assertions_by_id.get(memory_id)) is not None
        and _memory_item_matches_account_generation(items_by_id.get(memory_id, {}), account_generation)
        and assertion_matches_active_item(uid, assertion, items_by_id.get(memory_id, {}))
    ]


def _load_active_memory_graph_assertions(
    uid: str,
    *,
    db_client: Any = None,
    scan_limit: Optional[int] = None,
) -> Tuple[List[MemoryGraphAssertion], bool]:
    """Load fenced assertions with an optional bounded Firestore scan."""
    client = _firestore_client(db_client)
    user_ref = client.collection(users_collection).document(uid)
    assertions_ref = user_ref.collection(memory_graph_assertions_collection)
    candidates: Dict[str, MemoryGraphAssertion] = {}

    if scan_limit is None:
        snapshots = list(assertions_ref.stream())
        truncated = False
    else:
        bounded_limit = max(0, int(scan_limit))
        query = assertions_ref.order_by(KNOWLEDGE_GRAPH_DOCUMENT_ORDER).limit(bounded_limit + 1)
        snapshots = list(query.stream())
        truncated = len(snapshots) > bounded_limit
        snapshots = snapshots[:bounded_limit]

    for snapshot in snapshots:
        assertion = _parse_assertion_snapshot(uid, snapshot)
        if assertion is None:
            continue
        current = candidates.get(assertion.memory_id)
        if current is None or (
            assertion.commit_sequence,
            assertion.item_revision,
            assertion.assertion_id,
        ) > (
            current.commit_sequence,
            current.item_revision,
            current.assertion_id,
        ):
            candidates[assertion.memory_id] = assertion

    if not candidates:
        return [], truncated

    items_by_id = _load_memory_items_by_ids(uid, sorted(candidates), db_client=client)

    return (
        [
            assertion
            for memory_id, assertion in sorted(candidates.items())
            if assertion_matches_active_item(uid, assertion, items_by_id.get(memory_id, {}))
        ],
        truncated,
    )


def get_active_memory_graph_assertions(
    uid: str,
    *,
    db_client: Any = None,
) -> List[MemoryGraphAssertion]:
    """Load only assertions fenced to their current active Long-term memory item."""
    assertions, _ = _load_active_memory_graph_assertions(uid, db_client=db_client)
    return assertions


def _authoritative_legacy_citation_ids(
    uid: str,
    *,
    legacy_nodes: Iterable[Dict[str, Any]],
    legacy_edges: Iterable[Dict[str, Any]],
    db_client: Any,
) -> Tuple[set[str], bool]:
    """Fence legacy citations that already belong to canonical item state.

    Projection cleanup is asynchronous. A tombstoned canonical item therefore
    has to suppress its old shared-graph citation at read time, before the
    retryable prune succeeds. Legacy-only users avoid the citation probes
    entirely because they have no canonical apply-control document.
    """

    cited_ids = sorted(
        {
            memory_id
            for record in [*legacy_nodes, *legacy_edges]
            for memory_id in _string_values(record.get('memory_ids'))
        }
    )
    if not cited_ids:
        return set(), False

    user_ref = db_client.collection(users_collection).document(uid)
    control_snapshot = user_ref.collection('memory_state').document('apply_control').get()
    if not getattr(control_snapshot, 'exists', False):
        return set(), False

    bounded_ids = cited_ids[:MAX_KNOWLEDGE_GRAPH_CITATION_FENCES]
    # If a legacy record carries more citations than can be authoritatively
    # checked in one request, suppress the unchecked tail and mark the graph
    # truncated. This is the privacy-safe failure mode.
    authoritative_ids = set(cited_ids[MAX_KNOWLEDGE_GRAPH_CITATION_FENCES:])
    if not bounded_ids:
        return authoritative_ids, bool(authoritative_ids)
    item_refs = [user_ref.collection(memory_items_collection).document(memory_id) for memory_id in bounded_ids]
    for snapshot in db_client.get_all(item_refs):
        if getattr(snapshot, 'exists', False):
            snapshot_id = getattr(snapshot, 'id', None)
            if isinstance(snapshot_id, str) and snapshot_id:
                authoritative_ids.add(snapshot_id)
    return authoritative_ids, len(cited_ids) > len(bounded_ids)


def has_stored_memory_graph_assertions(uid: str, *, db_client: Any = None) -> bool:
    """Return whether any assertion document exists using a one-document probe."""
    client = _firestore_client(db_client)
    assertions_ref = client.collection(users_collection).document(uid).collection(memory_graph_assertions_collection)
    return next(iter(assertions_ref.limit(1).stream()), None) is not None


def _node_terms(node: Dict[str, Any]) -> List[str]:
    terms: List[str] = []
    label = node.get('label')
    if isinstance(label, str) and label.strip():
        terms.append(label.strip().casefold())
    aliases = node.get('aliases')
    if isinstance(aliases, list):
        terms.extend(
            alias.strip().casefold() for alias in cast(List[Any], aliases) if isinstance(alias, str) and alias.strip()
        )
    return sorted(set(terms))


def _merge_node(existing: Optional[Dict[str, Any]], incoming: Dict[str, Any]) -> Dict[str, Any]:
    if existing is None:
        merged = dict(incoming)
    else:
        merged = dict(existing)
        if not merged.get('label') and incoming.get('label'):
            merged['label'] = incoming['label']
        if not merged.get('node_type') and incoming.get('node_type'):
            merged['node_type'] = incoming['node_type']
    merged['id'] = incoming['id']
    merged['aliases'] = sorted(set(_string_values(merged.get('aliases')) + _string_values(incoming.get('aliases'))))
    merged['memory_ids'] = sorted(
        set(_string_values(merged.get('memory_ids')) + _string_values(incoming.get('memory_ids')))
    )
    return merged


def _edge_key(edge: Dict[str, Any]) -> Optional[Tuple[str, str, str]]:
    source_id = edge.get('source_id')
    target_id = edge.get('target_id')
    label = edge.get('label')
    if not all(isinstance(value, str) and value for value in (source_id, target_id, label)):
        return None
    return cast(Tuple[str, str, str], (source_id, target_id, label))


def _deterministic_edge_id(source_id: str, target_id: str, label: str) -> str:
    return (
        'edge_'
        + deterministic_contract_id(
            'canonical-graph-edge',
            {
                'source_id': source_id,
                'target_id': target_id,
                'label': label,
            },
        )[:24]
    )


def _merge_edge(
    existing: Optional[Dict[str, Any]],
    incoming: Dict[str, Any],
    *,
    canonical: bool,
) -> Dict[str, Any]:
    if existing is None:
        merged = dict(incoming)
    else:
        merged = dict(existing)
    incoming_id = incoming.get('id')
    existing_id = merged.get('id')
    if canonical and isinstance(incoming_id, str) and incoming_id:
        merged['id'] = incoming_id
    elif isinstance(incoming_id, str) and incoming_id:
        ids = [item for item in (existing_id, incoming_id) if isinstance(item, str) and item]
        merged['id'] = min(ids)
    merged['source_id'] = incoming['source_id']
    merged['target_id'] = incoming['target_id']
    merged['label'] = incoming['label']
    merged['memory_ids'] = sorted(
        set(_string_values(merged.get('memory_ids')) + _string_values(incoming.get('memory_ids')))
    )
    return merged


def merge_knowledge_graph_records(
    legacy_graph: Dict[str, Any],
    assertions: Iterable[MemoryGraphAssertion],
    *,
    authoritative_memory_ids: Optional[Iterable[str]] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """Merge legacy shared graph projections with authoritative per-memory assertions."""
    ordered_assertions = sorted(
        assertions,
        key=lambda item: (item.commit_sequence, item.memory_id, item.assertion_id),
    )
    authoritative_ids = {
        *(authoritative_memory_ids or []),
        *(assertion.memory_id for assertion in ordered_assertions),
    }
    raw_nodes = legacy_graph.get('nodes')
    raw_edges = legacy_graph.get('edges')
    legacy_nodes = cast(List[Any], raw_nodes) if isinstance(raw_nodes, list) else []
    legacy_edges = cast(List[Any], raw_edges) if isinstance(raw_edges, list) else []

    nodes_by_id: Dict[str, Dict[str, Any]] = {}
    node_ids_by_term: Dict[str, set[str]] = {}
    stripped_only_node_ids: set[str] = set()
    retained_legacy_node_ids: set[str] = set()
    canonical_node_ids: set[str] = set()

    for raw_node in sorted(
        (cast(Dict[str, Any], node) for node in legacy_nodes if isinstance(node, dict)),
        key=lambda node: (str(node.get('id') or ''), str(node.get('label') or '')),
    ):
        node_id = raw_node.get('id')
        if not isinstance(node_id, str) or not node_id:
            continue
        incoming = dict(raw_node)
        original_memory_ids = _string_values(incoming.get('memory_ids'))
        incoming['memory_ids'] = [memory_id for memory_id in original_memory_ids if memory_id not in authoritative_ids]
        if original_memory_ids and not incoming['memory_ids']:
            stripped_only_node_ids.add(node_id)
        else:
            retained_legacy_node_ids.add(node_id)
        nodes_by_id[node_id] = _merge_node(nodes_by_id.get(node_id), incoming)
        for term in _node_terms(nodes_by_id[node_id]):
            node_ids_by_term.setdefault(term, set()).add(node_id)

    edges_by_key: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    for raw_edge in sorted(
        (cast(Dict[str, Any], edge) for edge in legacy_edges if isinstance(edge, dict)),
        key=lambda edge: (
            str(edge.get('source_id') or ''),
            str(edge.get('target_id') or ''),
            str(edge.get('label') or ''),
            str(edge.get('id') or ''),
        ),
    ):
        incoming = dict(raw_edge)
        original_memory_ids = _string_values(incoming.get('memory_ids'))
        incoming['memory_ids'] = [memory_id for memory_id in original_memory_ids if memory_id not in authoritative_ids]
        if original_memory_ids and not incoming['memory_ids']:
            continue
        key = _edge_key(incoming)
        if key is None:
            continue
        if not isinstance(incoming.get('id'), str) or not incoming.get('id'):
            incoming['id'] = _deterministic_edge_id(*key)
        edges_by_key[key] = _merge_edge(edges_by_key.get(key), incoming, canonical=False)

    for assertion in ordered_assertions:
        records = assertion.graph_records()
        node_id_map: Dict[str, str] = {}
        for raw_node in sorted(records['nodes'], key=lambda node: (str(node.get('label')), str(node.get('id')))):
            original_id = cast(str, raw_node['id'])
            matching_ids = {node_id for term in _node_terms(raw_node) for node_id in node_ids_by_term.get(term, set())}
            resolved_id = original_id if original_id in nodes_by_id else min(matching_ids, default=original_id)
            node_id_map[original_id] = resolved_id
            incoming = {**raw_node, 'id': resolved_id, 'memory_ids': [assertion.memory_id]}
            nodes_by_id[resolved_id] = _merge_node(nodes_by_id.get(resolved_id), incoming)
            canonical_node_ids.add(resolved_id)
            for term in _node_terms(nodes_by_id[resolved_id]):
                node_ids_by_term.setdefault(term, set()).add(resolved_id)

        for raw_edge in records['edges']:
            source_id = node_id_map.get(cast(str, raw_edge['source_id']), cast(str, raw_edge['source_id']))
            target_id = node_id_map.get(cast(str, raw_edge['target_id']), cast(str, raw_edge['target_id']))
            label = cast(str, raw_edge['label'])
            incoming = {
                **raw_edge,
                'id': _deterministic_edge_id(source_id, target_id, label),
                'source_id': source_id,
                'target_id': target_id,
                'memory_ids': [assertion.memory_id],
            }
            key = (source_id, target_id, label)
            edges_by_key[key] = _merge_edge(edges_by_key.get(key), incoming, canonical=True)

    referenced_node_ids = {
        cast(str, edge[field])
        for edge in edges_by_key.values()
        for field in ('source_id', 'target_id')
        if isinstance(edge.get(field), str)
    }
    included_node_ids = {
        node_id
        for node_id in nodes_by_id
        if node_id not in stripped_only_node_ids
        or node_id in retained_legacy_node_ids
        or node_id in canonical_node_ids
        or node_id in referenced_node_ids
    }
    nodes = [nodes_by_id[node_id] for node_id in sorted(included_node_ids)]
    edges = [
        edges_by_key[key]
        for key in sorted(edges_by_key, key=lambda item: (item[0], item[1], item[2], edges_by_key[item].get('id', '')))
    ]
    return {'nodes': nodes, 'edges': edges}


def get_knowledge_graph(uid: str, *, db_client: Any = None) -> Dict[str, Any]:
    """Return a bounded graph snapshot for GET /v1/knowledge-graph.

    Full-collection streams of nodes+edges previously unbounded-read large accounts
    into the 30s GET timeout. Caps keep the response bounded; `truncated` signals
    that denser graphs need a follow-up pagination/summarization API.
    """
    client = _firestore_client(db_client)
    # Fetch one extra row past the cap to detect truncation without a count() round-trip.
    legacy_nodes = get_knowledge_nodes(uid, db_client=client, limit=MAX_KNOWLEDGE_GRAPH_NODES + 1)
    legacy_edges = get_knowledge_edges(uid, db_client=client, limit=MAX_KNOWLEDGE_GRAPH_EDGES + 1)
    assertions, assertions_truncated = _load_active_memory_graph_assertions(
        uid,
        db_client=client,
        scan_limit=MAX_KNOWLEDGE_GRAPH_ASSERTIONS,
    )
    legacy_node_page = legacy_nodes[:MAX_KNOWLEDGE_GRAPH_NODES]
    legacy_edge_page = legacy_edges[:MAX_KNOWLEDGE_GRAPH_EDGES]
    authoritative_citation_ids, citation_fences_truncated = _authoritative_legacy_citation_ids(
        uid,
        legacy_nodes=legacy_node_page,
        legacy_edges=legacy_edge_page,
        db_client=client,
    )
    merged = merge_knowledge_graph_records(
        {
            'nodes': legacy_node_page,
            'edges': legacy_edge_page,
        },
        assertions,
        authoritative_memory_ids=authoritative_citation_ids,
    )
    merged_nodes = merged['nodes']
    merged_edges = merged['edges']
    node_page = merged_nodes[:MAX_KNOWLEDGE_GRAPH_NODES]
    node_page_ids: set[str] = {
        cast(str, node.get('id')) for node in node_page if isinstance(node.get('id'), str) and node.get('id')
    }
    referentially_closed_edges = [
        edge
        for edge in merged_edges
        if edge.get('source_id') in node_page_ids and edge.get('target_id') in node_page_ids
    ]
    referential_edges_dropped = len(referentially_closed_edges) != len(merged_edges)
    nodes_truncated = (
        len(legacy_nodes) > MAX_KNOWLEDGE_GRAPH_NODES
        or len(merged_nodes) > MAX_KNOWLEDGE_GRAPH_NODES
        or assertions_truncated
        or citation_fences_truncated
    )
    edges_truncated = (
        len(legacy_edges) > MAX_KNOWLEDGE_GRAPH_EDGES
        or len(merged_edges) > MAX_KNOWLEDGE_GRAPH_EDGES
        or referential_edges_dropped
        or assertions_truncated
        or citation_fences_truncated
    )
    edge_page = referentially_closed_edges[:MAX_KNOWLEDGE_GRAPH_EDGES]
    return {
        'nodes': node_page,
        'edges': edge_page,
        'truncated': nodes_truncated or edges_truncated,
        'node_count': len(node_page),
        'edge_count': len(edge_page),
        'node_limit': MAX_KNOWLEDGE_GRAPH_NODES,
        'edge_limit': MAX_KNOWLEDGE_GRAPH_EDGES,
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
