from __future__ import annotations

import json
import logging
import os
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, TypedDict, cast

from pinecone import Pinecone

from database import projection_repair
from database.memory_vector_metadata import (
    build_archive_memory_vector_filter,
    build_default_memory_vector_filter,
    build_memory_vector_metadata,
    parse_memory_search_vector_hit,
    parse_search_vector_hit,
    strip_null_metadata_values,
)
from models.conversation_metadata import ConversationMetadataKeys, metadata_list
from models.product_memory import MemoryItem
from models.memory_search_gateway import SearchMode, SearchVectorHit
from utils.llm.clients import embeddings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# TypedDict contracts for Pinecone vector records.
#
# Pinecone SDK types are partially untyped at the SDK boundary, so the module-
# level ``index`` handle below is typed as ``Any`` and every Pinecone call
# funnels through it. These TypedDicts document the document contracts we
# build (``VectorRecordDoc``) and consume (``VectorMatchDoc``) at that
# boundary; ``total=False`` because keys vary by namespace.
# ---------------------------------------------------------------------------


class VectorMetadataDoc(TypedDict, total=False):
    """Metadata sub-document attached to a Pinecone vector record.

    Captures the union of metadata keys written across this module's
    namespaces (ns1 conversations, ns2 memories, ns3 screen activity,
    ns4 action items, ns_tchunks transcript chunks, ns_x X posts).
    Canonical memory vectors (built by ``build_memory_vector_metadata``)
    add further projection keys not enumerated here, which is why the
    ``metadata`` field on ``VectorRecordDoc`` stays ``Dict[str, Any]``.
    """

    uid: str
    memory_id: str
    conversation_id: str
    action_item_id: str
    post_id: str
    screenshot_id: str
    chunk_index: int
    created_at: int
    timestamp: int
    category: str
    subject_entity_id: str
    kind: str
    appName: str


class VectorRecordDoc(TypedDict):
    """Pinecone upsert payload: ``id`` + ``values`` + ``metadata``.

    All three keys are always populated by every upsert site in this module,
    so the contract is total=True. ``metadata`` stays ``Dict[str, Any]`` so
    canonical-cohort projection keys (added by ``build_memory_vector_metadata``)
    remain representable without enumerating every metadata field.
    """

    id: str
    values: List[float]
    metadata: Dict[str, Any]


class VectorMatchDoc(TypedDict, total=False):
    """Single match returned by a Pinecone ``query`` response."""

    id: str
    score: float
    values: List[float]
    metadata: Dict[str, Any]


_pinecone_api_key: Optional[str] = os.getenv('PINECONE_API_KEY')
_pinecone_index_name: Optional[str] = os.getenv('PINECONE_INDEX_NAME')

# Pinecone Index methods (upsert/query/update/delete/list) are partially
# untyped at the SDK boundary (e.g. ``**kwargs: Unknown``). Typing the
# handles as ``Any`` isolates that boundary so downstream call sites stay
# warning-clean without per-call ignores.
pc: Any = None
index: Any = None
if _pinecone_api_key and _pinecone_index_name:
    pc = Pinecone(api_key=_pinecone_api_key)
    index = pc.Index(_pinecone_index_name)


def _get_data(uid: str, conversation_id: str, vector: List[float]) -> VectorRecordDoc:
    metadata: VectorMetadataDoc = {
        'uid': uid,
        'memory_id': conversation_id,
        'created_at': int(datetime.now(timezone.utc).timestamp()),
    }
    return {
        "id": f'{uid}-{conversation_id}',
        "values": vector,
        'metadata': dict(metadata),
    }


def upsert_vector(uid: str, conversation_id: str, vector: List[float]) -> None:
    res = index.upsert(vectors=[_get_data(uid, conversation_id, vector)], namespace="ns1")
    logger.info(f'upsert_vector {res}')


def upsert_vector2(uid: str, conversation_id: str, vector: List[float], metadata: Dict[str, Any]) -> None:
    data: VectorRecordDoc = _get_data(uid, conversation_id, vector)
    typed_metadata: Dict[str, Any] = data['metadata']
    typed_metadata.update(metadata)
    res = index.upsert(vectors=[data], namespace="ns1")
    logger.info(f'upsert_vector {res}')


def update_vector_metadata(uid: str, conversation_id: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
    metadata['uid'] = uid
    metadata['memory_id'] = conversation_id
    result: Dict[str, Any] = index.update(f'{uid}-{conversation_id}', set_metadata=metadata, namespace="ns1")
    return result


def upsert_vectors(uid: str, vectors: List[List[float]], conversation_ids: List[str]) -> None:
    data: List[VectorRecordDoc] = [_get_data(uid, cid, vector) for cid, vector in zip(conversation_ids, vectors)]
    res = index.upsert(vectors=data, namespace="ns1")
    logger.info(f'upsert_vectors {res}')


def _created_at_filter(starts_at: Optional[int] = None, ends_at: Optional[int] = None) -> Optional[Dict[str, int]]:
    if starts_at is None and ends_at is None:
        return None
    if starts_at is not None and ends_at is not None and starts_at > ends_at:
        return None

    created_at: Dict[str, int] = {}
    if starts_at is not None:
        created_at['$gte'] = starts_at
    if ends_at is not None:
        created_at['$lte'] = ends_at
    return created_at


def query_vectors(
    query: str,
    uid: str,
    starts_at: Optional[int] = None,
    ends_at: Optional[int] = None,
    k: int = 5,
) -> List[str]:
    if index is None:
        return []

    filter_data: Dict[str, Any] = {'uid': uid}
    created_at = _created_at_filter(starts_at, ends_at)
    if (starts_at is not None or ends_at is not None) and created_at is None:
        logger.warning('Skipping conversation vector search with invalid date filter')
        return []
    if created_at is not None:
        filter_data['created_at'] = created_at

    xq = embeddings.embed_query(query)
    xc = index.query(vector=xq, top_k=k, include_metadata=False, filter=filter_data, namespace="ns1")
    matches: List[Any] = xc['matches']
    return [item['id'].replace(f'{uid}-', '') for item in matches]


def query_vectors_by_metadata(
    uid: str,
    vector: List[float],
    dates_filter: List[datetime],
    people: List[str],
    topics: List[str],
    entities: List[str],
    dates: List[str],
    limit: int = 5,
) -> List[str]:
    and_clauses: List[Dict[str, Any]] = [{'uid': {'$eq': uid}}]
    filter_data: Dict[str, Any] = {'$and': and_clauses}
    if people or topics or entities or dates:
        and_clauses.append(
            {
                '$or': [
                    {ConversationMetadataKeys.PEOPLE: {'$in': people}},
                    {ConversationMetadataKeys.TOPICS: {'$in': topics}},
                    {ConversationMetadataKeys.ENTITIES: {'$in': entities}},
                    # {'dates': {'$in': dates_mentioned}},
                ]
            }
        )
    if dates_filter and len(dates_filter) == 2 and dates_filter[0] and dates_filter[1]:
        logger.info(f'dates_filter {dates_filter}')
        and_clauses.append(
            {'created_at': {'$gte': int(dates_filter[0].timestamp()), '$lte': int(dates_filter[1].timestamp())}}
        )

    xc = index.query(
        vector=vector, filter=filter_data, namespace="ns1", include_values=False, include_metadata=True, top_k=1000
    )
    if not xc['matches']:
        if len(and_clauses) == 3:
            and_clauses.pop(1)
            logger.warning(f'query_vectors_by_metadata retrying without structured filters: {json.dumps(filter_data)}')
            xc = index.query(
                vector=vector,
                filter=filter_data,
                namespace="ns1",
                include_values=False,
                include_metadata=True,
                top_k=20,
            )
        else:
            return []

    conversation_id_to_matches: defaultdict[str, int] = defaultdict(int)
    matches: List[Any] = xc['matches']
    for item in matches:
        metadata: Dict[str, Any] = item['metadata']
        conversation_id: str = metadata['memory_id']
        for topic in topics:
            if topic in metadata_list(metadata, ConversationMetadataKeys.TOPICS):
                conversation_id_to_matches[conversation_id] += 1
        for entity in entities:
            if entity in metadata_list(metadata, ConversationMetadataKeys.ENTITIES):
                conversation_id_to_matches[conversation_id] += 1
        for person in people:
            if person in metadata_list(metadata, ConversationMetadataKeys.PEOPLE):
                conversation_id_to_matches[conversation_id] += 1

    conversations_id: List[str] = [item['id'].replace(f'{uid}-', '') for item in matches]
    conversations_id.sort(key=lambda x: conversation_id_to_matches[x], reverse=True)
    return conversations_id[:limit] if len(conversations_id) > limit else conversations_id


def delete_vector(uid: str, conversation_id: str) -> None:
    """
    Delete a conversation vector from Pinecone.

    Note: Vectors are stored with ID format '{uid}-{conversation_id}'
    """
    if index is None:
        logger.warning('Pinecone index not initialized, skipping conversation vector delete')
        return
    vector_id = f'{uid}-{conversation_id}'
    result = index.delete(ids=[vector_id], namespace="ns1")
    logger.info(f'delete_vector {vector_id} {result}')


# ==========================================
# Memory Vector Functions
# For memory embeddings and semantic search
# ==========================================

MEMORIES_NAMESPACE = "ns2"
WORKSTREAM_ASSOCIATION_NAMESPACE = "workstream-association-v1"
WORKSTREAM_ASSOCIATION_SCHEMA_VERSION = 1


def upsert_workstream_association_vector(
    uid: str,
    workstream_id: str,
    *,
    objective: str,
    current_state_summary: str,
    account_generation: int = 0,
) -> bool:
    """Write a rebuildable retrieval projection for one open workstream."""
    if index is None:
        return False
    content = f"Objective: {objective.strip()}\nCurrent state: {current_state_summary.strip()}".strip()
    if not content:
        return False
    data: VectorRecordDoc = {
        'id': f'{uid}:workstream:{account_generation}:{workstream_id}',
        'values': embeddings.embed_query(content),
        'metadata': {
            'uid': uid,
            'workstream_id': workstream_id,
            'status': 'open',
            'account_generation': account_generation,
            'schema_version': WORKSTREAM_ASSOCIATION_SCHEMA_VERSION,
        },
    }
    index.upsert(vectors=[data], namespace=WORKSTREAM_ASSOCIATION_NAMESPACE)
    return True


def query_workstream_association_candidates(
    uid: str, summary: str, *, account_generation: int = 0, limit: int = 5
) -> List[str]:
    """Return derived candidate IDs only; callers must hydrate authority."""
    if index is None or not summary.strip():
        return []
    response = index.query(
        vector=embeddings.embed_query(summary),
        top_k=max(1, min(limit, 20)),
        include_metadata=True,
        include_values=False,
        filter={
            'uid': {'$eq': uid},
            'status': {'$eq': 'open'},
            'account_generation': {'$eq': account_generation},
            'schema_version': {'$eq': WORKSTREAM_ASSOCIATION_SCHEMA_VERSION},
        },
        namespace=WORKSTREAM_ASSOCIATION_NAMESPACE,
    )
    result: List[str] = []
    for match in response.get('matches', []):
        metadata = match.get('metadata') if isinstance(match, dict) else None
        workstream_id = metadata.get('workstream_id') if isinstance(metadata, dict) else None
        if isinstance(workstream_id, str) and workstream_id not in result:
            result.append(workstream_id)
    return result


def delete_workstream_association_vector(uid: str, workstream_id: str, *, account_generation: int = 0) -> bool:
    if index is None:
        return False
    index.delete(
        ids=[f'{uid}:workstream:{account_generation}:{workstream_id}'],
        namespace=WORKSTREAM_ASSOCIATION_NAMESPACE,
    )
    return True


def reset_workstream_association_vectors(uid: str, *, account_generation: int = 0) -> bool:
    if index is None:
        return False
    index.delete(
        filter={
            '$and': [
                {'uid': {'$eq': uid}},
                {'account_generation': {'$eq': account_generation}},
            ]
        },
        namespace=WORKSTREAM_ASSOCIATION_NAMESPACE,
    )
    return True


def build_legacy_memory_vector_filter(uid: str, subject_entity_id: str | None = None) -> Dict[str, Any]:
    """Return the legacy ns2 memory-search filter with an explicit memory schema barrier.

    Legacy memory vectors in ``ns2`` do not carry ``memory_schema_version``. memory
    vectors intentionally do, so every legacy search path must exclude that
    field before top-k is selected. This prevents memory Short-term, Long-term,
    Archive, stale-revision, or tombstoned candidates from occupying legacy
    result slots or being hydrated as legacy memories.
    """
    and_clauses: List[Dict[str, Any]] = [
        {'uid': {'$eq': uid}},
        {'memory_schema_version': {'$exists': False}},
    ]
    filter_data: Dict[str, Any] = {'$and': and_clauses}
    if subject_entity_id:
        and_clauses.append({'subject_entity_id': {'$eq': subject_entity_id}})
    return filter_data


@dataclass(frozen=True)
class VectorCandidateQueryResult:
    hits: List[SearchVectorHit] = field(default_factory=list)
    rejected_count: int = 0


def upsert_memory_vector(
    uid: str,
    memory_id: str,
    content: str,
    category: str,
    subject_entity_id: str | None = None,
    projection_metadata: Dict[str, Any] | None = None,
) -> List[float] | None:
    """
    Upsert a memory embedding to Pinecone.
    """
    if index is None:
        logger.warning('Pinecone index not initialized, skipping memory vector upsert')
        return None

    vector = embeddings.embed_query(content)
    metadata: Dict[str, Any] = {
        "uid": uid,
        "memory_id": memory_id,
        "category": category,
        "created_at": int(datetime.now(timezone.utc).timestamp()),
    }
    metadata.update(
        strip_null_metadata_values(
            projection_metadata
            or memory_projection_metadata(
                {'id': memory_id, 'category': category, 'subject_entity_id': subject_entity_id, 'status': 'accepted'}
            )
        )
    )
    if subject_entity_id:
        metadata["subject_entity_id"] = subject_entity_id
    data: VectorRecordDoc = {
        "id": f'{uid}-{memory_id}',
        "values": vector,
        "metadata": metadata,
    }
    res = index.upsert(vectors=[data], namespace=MEMORIES_NAMESPACE)
    logger.info(f'upsert_memory_vector {memory_id} {res}')
    return vector


def upsert_memory_vectors_batch(uid: str, items: List[Dict[str, Any]]) -> int:
    """
    Upsert many memory embeddings to Pinecone in a single request.

    Each item must be a dict with keys: 'memory_id', 'content', 'category'.
    Batching cuts latency from N embedding calls + N upserts to one embedding
    call + one upsert. Used by POST /v3/memories/batch and the dev batch API.
    Returns the number of vectors written (0 if Pinecone is not configured).
    """
    if index is None:
        logger.warning('Pinecone index not initialized, skipping memory vector batch upsert')
        return 0

    if not items:
        return 0

    contents: List[str] = [item['content'] for item in items]
    vectors: List[List[float]] = embeddings.embed_documents(contents)

    now_ts = int(datetime.now(timezone.utc).timestamp())
    payload: List[VectorRecordDoc] = []
    for i, item in enumerate(items):
        metadata: Dict[str, Any] = {
            "uid": uid,
            "memory_id": item['memory_id'],
            "category": item['category'],
            "created_at": now_ts,
        }
        metadata.update(
            strip_null_metadata_values(
                item.get('projection_metadata')
                or memory_projection_metadata(
                    {
                        'id': item['memory_id'],
                        'category': item['category'],
                        'subject_entity_id': item.get('subject_entity_id'),
                        'status': item.get('status', 'accepted'),
                    }
                )
            )
        )
        if item.get('subject_entity_id'):
            metadata['subject_entity_id'] = item['subject_entity_id']
        payload.append(
            {
                "id": f"{uid}-{item['memory_id']}",
                "values": vectors[i],
                "metadata": metadata,
            },
        )
    res = index.upsert(vectors=payload, namespace=MEMORIES_NAMESPACE)
    logger.info(f'upsert_memory_vectors_batch count={len(payload)} {res}')
    return len(payload)


def find_similar_memories(
    uid: str, content: str, threshold: float = 0.85, limit: int = 5, subject_entity_id: str | None = None
) -> List[Dict[str, Any]]:
    """
    Find memories similar to the given content.
    Returns list of matches with similarity scores.
    Used for duplicate detection and semantic search.
    """
    if index is None:
        logger.warning('Pinecone index not initialized, skipping similarity search')
        return []

    vector = embeddings.embed_query(content)
    filter_data = build_legacy_memory_vector_filter(uid, subject_entity_id=subject_entity_id)

    xc = index.query(
        vector=vector, top_k=limit, include_metadata=True, filter=filter_data, namespace=MEMORIES_NAMESPACE
    )

    results: List[Dict[str, Any]] = []
    matches: List[Any] = xc.get('matches', [])
    for match in matches:
        match_metadata: Dict[str, Any] = match['metadata']
        if match['score'] >= threshold:
            results.append(
                {
                    'memory_id': match_metadata.get('memory_id'),
                    'category': match_metadata.get('category'),
                    'score': match['score'],
                }
            )

    return results


def check_memory_duplicate(uid: str, content: str, threshold: float = 0.85) -> Optional[Dict[str, Any]]:
    """
    Check if a similar memory already exists.
    Returns the duplicate info if found, None otherwise.
    """
    similar = find_similar_memories(uid, content, threshold=threshold, limit=1)
    if similar:
        logger.warning(f'Found duplicate memory: {similar[0]}')
        return similar[0]
    return None


def search_memories_by_vector(uid: str, query: str, limit: int = 10) -> List[str]:
    """
    Semantic search for memories.
    Returns list of memory_ids ordered by relevance.
    """
    if index is None:
        logger.warning('Pinecone index not initialized, skipping memory search')
        return []

    vector = embeddings.embed_query(query)
    filter_data = build_legacy_memory_vector_filter(uid)

    xc = index.query(
        vector=vector, top_k=limit, include_metadata=True, filter=filter_data, namespace=MEMORIES_NAMESPACE
    )

    matches: List[Any] = xc.get('matches', [])
    return [match['metadata'].get('memory_id') for match in matches]


def query_memory_vector_candidates(  # type: ignore[reportRedeclaration]  # intentional: shadowed by a later def with the same name; preserved to keep both call paths reachable in isolation
    uid: str, query: str, *, mode: SearchMode = SearchMode.default, limit: int = 10
) -> VectorCandidateQueryResult:
    """Query existing ns2 for memory candidates using strict tier-safe metadata filters.

    The returned hits are vector candidates only. Product callers must still
    hydrate authoritative ``memory_items`` and run the memory search gateway before
    returning any memory to a user or integration.
    """
    if index is None:
        logger.warning('Pinecone index not initialized, skipping memory memory vector candidate search')
        return VectorCandidateQueryResult()

    vector = embeddings.embed_query(query)
    filter_data = (
        build_archive_memory_vector_filter(uid)
        if mode == SearchMode.archive_explicit
        else build_default_memory_vector_filter(uid)
    )
    response = index.query(
        vector=vector,
        top_k=limit,
        include_metadata=True,
        include_values=False,
        filter=filter_data,
        namespace=MEMORIES_NAMESPACE,
    )

    hits: List[SearchVectorHit] = []
    rejected_count = 0
    matches: List[Any] = response.get('matches', [])
    for match in matches:
        parsed = parse_search_vector_hit(match)
        if parsed.hit is None:
            rejected_count += 1
            continue
        hits.append(parsed.hit)
    return VectorCandidateQueryResult(hits=hits, rejected_count=rejected_count)


def upsert_canonical_memory_vector(
    item: MemoryItem,
    *,
    projection_commit_id: str | None = None,
) -> List[float] | None:
    """Upsert one canonical-cohort memory vector using neutral id + neutral metadata."""
    if index is None:
        logger.warning('Pinecone index not initialized, skipping canonical memory vector upsert')
        return None

    content = (item.content or "").strip()
    if not content:
        logger.warning('canonical memory vector upsert skipped: empty content memory_id=%s', item.memory_id)
        return None

    commit_id = projection_commit_id or item.ledger_commit_id
    if not commit_id:
        logger.warning(
            'canonical memory vector upsert skipped: missing projection_commit_id memory_id=%s', item.memory_id
        )
        return None

    vector = embeddings.embed_query(content)
    vector_updated_at = datetime.now(timezone.utc)
    metadata = build_memory_vector_metadata(
        item,
        projection_commit_id=commit_id,
        vector_updated_at=vector_updated_at,
    )
    data: VectorRecordDoc = {
        "id": item.memory_id,
        "values": vector,
        "metadata": metadata,
    }
    res = index.upsert(vectors=[data], namespace=MEMORIES_NAMESPACE)
    logger.info('upsert_canonical_memory_vector %s %s', item.memory_id, res)
    return vector


def query_memory_vector_candidates(
    uid: str, query: str, *, mode: SearchMode = SearchMode.default, limit: int = 10
) -> VectorCandidateQueryResult:
    """Query ns2 for canonical neutral-metadata memory vector candidates."""
    if index is None:
        logger.warning('Pinecone index not initialized, skipping canonical memory vector candidate search')
        return VectorCandidateQueryResult()

    vector = embeddings.embed_query(query)
    filter_data = (
        build_archive_memory_vector_filter(uid)
        if mode == SearchMode.archive_explicit
        else build_default_memory_vector_filter(uid)
    )
    response = index.query(
        vector=vector,
        top_k=limit,
        include_metadata=True,
        include_values=False,
        filter=filter_data,
        namespace=MEMORIES_NAMESPACE,
    )

    hits: List[SearchVectorHit] = []
    rejected_count = 0
    matches: List[Any] = response.get('matches', [])
    for match in matches:
        parsed = parse_memory_search_vector_hit(match)
        if parsed.hit is None:
            rejected_count += 1
            continue
        hits.append(parsed.hit)
    return VectorCandidateQueryResult(hits=hits, rejected_count=rejected_count)


def delete_memory_vector(uid: str, memory_id: str) -> None:
    """
    Delete a memory vector from Pinecone.
    """
    if index is None:
        logger.warning('Pinecone index not initialized, skipping memory vector delete')
        return

    vector_id = f'{uid}-{memory_id}'
    result = index.delete(ids=[vector_id], namespace=MEMORIES_NAMESPACE)
    logger.info(f'delete_memory_vector {vector_id} {result}')


def enqueue_projection_repair(uid: str, fact_id: str, reason: str, source_commit_id: str | None = None) -> List[str]:
    return projection_repair.enqueue_projection_repairs(
        uid,
        {
            'commit_id': source_commit_id or 'manual',
            'mutations': [{'type': reason, 'fact_id': fact_id}],
        },
    )


def memory_projection_metadata(memory: Dict[str, Any], source_commit_id: str | None = None) -> Dict[str, Any]:
    return projection_repair.projection_metadata_for_fact(memory, source_commit_id=source_commit_id)


def repair_memory_projection(uid: str, memory: Dict[str, Any] | None) -> str:
    if not memory or projection_repair.projection_action_for_fact(memory) == 'delete':
        memory_id = (memory or {}).get('id')
        if memory_id:
            delete_memory_vector(uid, memory_id)
        return 'delete'

    upsert_memory_vector(
        uid,
        memory['id'],
        memory.get('content', ''),
        memory.get('category', 'system'),
        subject_entity_id=memory.get('subject_entity_id'),
        projection_metadata=memory_projection_metadata(memory),
    )
    return projection_repair.projection_action_for_fact(memory)


def reconcile_projections(uid: str, facts: List[Dict[str, Any]], vector_fact_ids: List[str]) -> Dict[str, Any]:
    return projection_repair.reconcile_memory_projection(uid, facts, vector_fact_ids)


def process_projection_repair_queue(
    uid: str,
    fact_loader: Callable[[str], Optional[Dict[str, Any]]],
    limit: int = 100,
) -> Dict[str, Any]:
    return projection_repair.process_projection_repairs(
        uid,
        fact_loader=fact_loader,
        repair_func=repair_memory_projection,
        limit=limit,
    )


# ==========================================
# X (Twitter) Post Vector Functions
# Semantic search over the user's raw imported tweets/bookmarks.
# ==========================================

X_POSTS_NAMESPACE = "ns_x"


def upsert_x_post_vectors_batch(uid: str, items: List[Dict[str, Any]]) -> int:
    """Upsert X post embeddings in one request. Each item: {'post_id', 'content', 'kind'}.
    Returns the number of vectors written (0 if Pinecone is not configured)."""
    if index is None:
        logger.warning('Pinecone index not initialized, skipping x_post vector batch upsert')
        return 0
    filtered: List[Dict[str, Any]] = [it for it in items if (it.get('content') or '').strip()]
    if not filtered:
        return 0

    vectors: List[List[float]] = embeddings.embed_documents([it['content'] for it in filtered])
    now_ts = int(datetime.now(timezone.utc).timestamp())
    payload: List[VectorRecordDoc] = [
        {
            "id": f"{uid}-x-{it['post_id']}",
            "values": vectors[i],
            "metadata": {
                "uid": uid,
                "post_id": str(it['post_id']),
                "kind": it.get('kind', 'tweet'),
                "created_at": now_ts,
            },
        }
        for i, it in enumerate(filtered)
    ]
    res = index.upsert(vectors=payload, namespace=X_POSTS_NAMESPACE)
    logger.info(f'upsert_x_post_vectors_batch count={len(payload)} {res}')
    return len(payload)


def find_similar_x_posts(uid: str, content: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Semantic search over the user's X posts. Returns [{post_id, kind, score}]."""
    if index is None:
        logger.warning('Pinecone index not initialized, skipping x_post similarity search')
        return []
    vector = embeddings.embed_query(content)
    xc = index.query(
        vector=vector, top_k=limit, include_metadata=True, filter={'uid': uid}, namespace=X_POSTS_NAMESPACE
    )
    matches: List[Any] = xc.get('matches', [])
    return [
        {
            'post_id': m['metadata'].get('post_id'),
            'kind': m['metadata'].get('kind'),
            'score': m['score'],
        }
        for m in matches
    ]


# ==========================================
# Screen Activity Vector Functions
# For screenshot embeddings (Gemini embedding-001, 3072-dim)
# ==========================================

SCREEN_ACTIVITY_NAMESPACE = "ns3"


def upsert_screen_activity_vectors(uid: str, rows: List[Dict[str, Any]]) -> int:
    """Batch upsert screenshot embeddings to Pinecone ns3."""
    if index is None:
        logger.warning('Pinecone index not initialized, skipping screen activity vector upsert')
        return 0

    vectors: List[VectorRecordDoc] = []
    for row in rows:
        embedding = row.get('embedding')
        if not embedding:
            continue
        ts_value: Any = row['timestamp']
        timestamp = (
            int(datetime.fromisoformat(ts_value.replace('Z', '+00:00')).timestamp())
            if isinstance(ts_value, str)
            else int(ts_value)
        )
        vectors.append(
            {
                "id": f'{uid}-sa-{row["id"]}',
                "values": embedding,
                "metadata": {
                    "uid": uid,
                    "screenshot_id": str(row['id']),
                    "timestamp": timestamp,
                    "appName": row.get('appName', ''),
                },
            }
        )

    if not vectors:
        return 0

    # Pinecone upsert limit is 100 vectors per call
    upserted = 0
    for i in range(0, len(vectors), 100):
        chunk = vectors[i : i + 100]
        index.upsert(vectors=chunk, namespace=SCREEN_ACTIVITY_NAMESPACE)
        upserted += len(chunk)

    logger.info(f'upsert_screen_activity_vectors uid={uid} count={upserted}')
    return upserted


def search_screen_activity_vectors(
    uid: str,
    query_vector: List[float],
    start_date: Optional[int] = None,
    end_date: Optional[int] = None,
    app_filter: Optional[str] = None,
    k: int = 10,
) -> List[Dict[str, Any]]:
    """Vector search across screenshot embeddings in ns3."""
    if index is None:
        logger.warning('Pinecone index not initialized, skipping screen activity search')
        return []

    filter_data: Dict[str, Any] = {'uid': uid}
    if start_date and end_date:
        filter_data['timestamp'] = {'$gte': start_date, '$lte': end_date}
    elif start_date:
        filter_data['timestamp'] = {'$gte': start_date}
    elif end_date:
        filter_data['timestamp'] = {'$lte': end_date}
    if app_filter:
        filter_data['appName'] = app_filter

    xc = index.query(
        vector=query_vector,
        top_k=k,
        include_metadata=True,
        filter=filter_data,
        namespace=SCREEN_ACTIVITY_NAMESPACE,
    )

    matches: List[Any] = xc.get('matches', [])
    return [
        {
            'screenshot_id': match['metadata'].get('screenshot_id'),
            'timestamp': match['metadata'].get('timestamp'),
            'appName': match['metadata'].get('appName'),
            'score': match['score'],
        }
        for match in matches
    ]


def delete_screen_activity_vectors(uid: str, ids: List[str]) -> None:
    """Delete screen activity vectors by screenshot IDs."""
    if index is None:
        return
    vector_ids = [f'{uid}-sa-{sid}' for sid in ids]
    index.delete(ids=vector_ids, namespace=SCREEN_ACTIVITY_NAMESPACE)


# ==========================================
# Action Item Vector Functions
# ==========================================

ACTION_ITEMS_NAMESPACE = "ns4"


def upsert_action_item_vector(uid: str, action_item_id: str, description: str) -> List[float] | None:
    if index is None:
        logger.warning('Pinecone index not initialized, skipping action item vector upsert')
        return None

    vector = embeddings.embed_query(description)
    data: VectorRecordDoc = {
        "id": f'{uid}-ai-{action_item_id}',
        "values": vector,
        "metadata": {
            "uid": uid,
            "action_item_id": action_item_id,
            "created_at": int(datetime.now(timezone.utc).timestamp()),
        },
    }
    res = index.upsert(vectors=[data], namespace=ACTION_ITEMS_NAMESPACE)
    logger.info(f'upsert_action_item_vector {action_item_id} {res}')
    return vector


def upsert_action_item_vectors_batch(uid: str, items: List[Dict[str, Any]]) -> int:
    if index is None:
        logger.warning('Pinecone index not initialized, skipping action item vector batch upsert')
        return 0

    if not items:
        return 0

    descriptions: List[str] = [item['description'] for item in items]
    vectors: List[List[float]] = embeddings.embed_documents(descriptions)

    now_ts = int(datetime.now(timezone.utc).timestamp())
    payload: List[VectorRecordDoc] = [
        {
            "id": f"{uid}-ai-{item['action_item_id']}",
            "values": vectors[i],
            "metadata": {
                "uid": uid,
                "action_item_id": item['action_item_id'],
                "created_at": now_ts,
            },
        }
        for i, item in enumerate(items)
    ]
    res = index.upsert(vectors=payload, namespace=ACTION_ITEMS_NAMESPACE)
    logger.info(f'upsert_action_item_vectors_batch count={len(payload)} {res}')
    return len(payload)


def search_action_items_by_vector(uid: str, query: str, limit: int = 10, min_score: float = 0.3) -> List[str]:
    if index is None:
        logger.warning('Pinecone index not initialized, skipping action item search')
        return []

    vector = embeddings.embed_query(query)
    filter_data: Dict[str, Any] = {'uid': uid}

    xc = index.query(
        vector=vector, top_k=limit, include_metadata=True, filter=filter_data, namespace=ACTION_ITEMS_NAMESPACE
    )

    matches: List[Any] = xc.get('matches', [])
    top_score = matches[0]['score'] if matches else None
    kept = [m for m in matches if m.get('score', 0.0) >= min_score]
    logger.info(
        f'search_action_items_by_vector uid={uid} matches={len(matches)} kept={len(kept)} '
        f'top_score={top_score} min_score={min_score}'
    )
    return [m['metadata'].get('action_item_id') for m in kept]


def find_similar_action_items(uid: str, query: str, threshold: float = 0.6, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Find action items semantically similar to the given query text. Used to
    feed the conversation extraction prompt with potentially-duplicate open
    tasks so the LLM can suppress true duplicates.

    Returns matches at or above the threshold. Each result is
    `{'action_item_id': str, 'score': float}` ordered by Pinecone relevance.
    Pinecone or embedding failures degrade silently to an empty list — the
    caller treats "no candidates" as "user has nothing relevant," which is
    the same behavior as a brand-new user.
    """
    if index is None:
        return []

    try:
        vector = embeddings.embed_query(query)
        xc = index.query(
            vector=vector,
            top_k=limit,
            include_metadata=True,
            filter={'uid': uid},
            namespace=ACTION_ITEMS_NAMESPACE,
        )
        matches: List[Any] = xc.get('matches', [])
        kept: List[Dict[str, Any]] = []
        dropped_no_id = 0
        for m in matches:
            if m.get('score', 0.0) < threshold:
                continue
            aid = m.get('metadata', {}).get('action_item_id')
            if not aid:
                dropped_no_id += 1
                continue
            kept.append({'action_item_id': aid, 'score': m.get('score', 0.0)})
        top_score = matches[0]['score'] if matches else None
        logger.info(
            f'find_similar_action_items uid={uid} matches={len(matches)} '
            f'kept={len(kept)} dropped_no_id={dropped_no_id} '
            f'top_score={top_score} threshold={threshold}'
        )
        return kept
    except Exception as e:
        logger.exception(f'find_similar_action_items failed uid={uid}: {e}')
        return []


def delete_action_item_vector(uid: str, action_item_id: str) -> None:
    if index is None:
        logger.warning('Pinecone index not initialized, skipping action item vector delete')
        return

    vector_id = f'{uid}-ai-{action_item_id}'
    result = index.delete(ids=[vector_id], namespace=ACTION_ITEMS_NAMESPACE)
    logger.info(f'delete_action_item_vector {vector_id} {result}')


def delete_action_item_vectors_batch(uid: str, action_item_ids: List[str]) -> None:
    if index is None:
        return
    if not action_item_ids:
        return
    vector_ids = [f'{uid}-ai-{aid}' for aid in action_item_ids]
    index.delete(ids=vector_ids, namespace=ACTION_ITEMS_NAMESPACE)
    logger.info(f'delete_action_item_vectors_batch count={len(vector_ids)}')


def delete_conversation_vectors_batch(uid: str, conversation_ids: List[str]) -> None:
    """Delete a user's conversation vectors (ns1) in one batched, chunked call.

    Chunked so a single failure can't abandon the rest (and to stay under Pinecone's per-delete id
    limit). Used by account deletion to purge all of a user's conversation vectors.
    """
    if index is None:
        logger.warning('Pinecone index not initialized, skipping conversation vector batch delete')
        return
    if not conversation_ids:
        return
    vector_ids = [f'{uid}-{cid}' for cid in conversation_ids]
    for i in range(0, len(vector_ids), 1000):
        index.delete(ids=vector_ids[i : i + 1000], namespace="ns1")
    logger.info(f'delete_conversation_vectors_batch count={len(vector_ids)}')


def delete_pinecone_memory_vectors_by_id(vector_ids: List[str]) -> int:
    """Delete ns2 memory vectors by exact Pinecone id.

    Supports legacy ``{uid}-{memory_id}``, memory ``memvec:…``, and canonical neutral ``mem_…`` ids.
    Used by canonical account-delete purge; legacy batch delete keeps ``{uid}-{id}`` scheme unchanged.
    """
    if index is None:
        logger.warning("Pinecone index not initialized, skipping memory vector delete by id")
        return 0
    if not vector_ids:
        return 0
    total_deleted = 0
    for i in range(0, len(vector_ids), 1000):
        chunk = vector_ids[i : i + 1000]
        try:
            index.delete(ids=chunk, namespace=MEMORIES_NAMESPACE)
            total_deleted += len(chunk)
        except Exception:
            logger.warning("delete_pinecone_memory_vectors_by_id chunk failed chunk=%d", i // 1000)
    logger.info("delete_pinecone_memory_vectors_by_id total_deleted=%d", total_deleted)
    return total_deleted


def delete_memory_vectors_batch(uid: str, memory_ids: List[str]) -> int:
    """Delete a user's memory vectors (ns2) in batched, chunked calls.

    Each chunk is individually wrapped in try/except so a transient failure
    on one chunk does not abandon the rest. Returns the number of vectors
    successfully deleted (0 if Pinecone is not configured).
    """
    if index is None:
        logger.warning('Pinecone index not initialized, skipping memory vector batch delete')
        return 0
    if not memory_ids:
        return 0
    vector_ids = [f'{uid}-{mid}' for mid in memory_ids]
    total_deleted = 0
    for i in range(0, len(vector_ids), 1000):
        chunk = vector_ids[i : i + 1000]
        try:
            index.delete(ids=chunk, namespace=MEMORIES_NAMESPACE)
            total_deleted += len(chunk)
        except Exception:
            logger.warning(f'delete_memory_vectors_batch chunk failed uid={uid} chunk={i // 1000}')
    logger.info(f'delete_memory_vectors_batch uid={uid} total_deleted={total_deleted}')
    return total_deleted


# ---------------------------------------------------------------------------
# Transcript chunks ("ns_tchunks"): verbatim retrieval over raw conversation
# transcripts. Conversation vectors (ns1) embed only the structured SUMMARY, so
# specific details (exact dates, names, numbers, one-off mentions) are not
# findable semantically. Chunk vectors make the raw transcript searchable.
#
# Privacy: chunk TEXT is embedded but never stored in Pinecone metadata —
# transcripts are encrypted at rest in Firestore, and mirroring them as
# plaintext metadata would bypass that. Readers re-hydrate the text from
# Firestore via (conversation_id, chunk_index).
TRANSCRIPT_CHUNKS_NAMESPACE = "ns_tchunks"


def upsert_transcript_chunk_vectors(uid: str, conversation_id: str, chunks: List[Dict[str, Any]]) -> int:
    """chunks: [{'text': str, 'created_at': int unix ts, 'chunk_index': int}]"""
    if index is None:
        logger.warning('Pinecone index not initialized, skipping transcript chunk upsert')
        return 0
    filtered: List[Dict[str, Any]] = [c for c in chunks if (c.get('text') or '').strip()]
    if not filtered:
        return 0

    vectors: List[List[float]] = embeddings.embed_documents([c['text'] for c in filtered])
    payload: List[VectorRecordDoc] = []
    for c, v in zip(filtered, vectors):
        metadata: VectorMetadataDoc = {
            'uid': uid,
            'conversation_id': conversation_id,
            'chunk_index': c['chunk_index'],
            'created_at': int(c['created_at']),
        }
        payload.append(
            {
                'id': f"{uid}-{conversation_id}-c{c['chunk_index']}",
                'values': v,
                'metadata': dict(metadata),
            }
        )

    upserted = 0
    for i in range(0, len(payload), 100):
        index.upsert(vectors=payload[i : i + 100], namespace=TRANSCRIPT_CHUNKS_NAMESPACE)
        upserted += len(payload[i : i + 100])
    logger.info(f'upsert_transcript_chunk_vectors uid={uid} conversation={conversation_id} count={upserted}')
    return upserted


def search_transcript_chunks(
    uid: str,
    query: str,
    limit: int = 20,
    starts_at: Optional[int] = None,
    ends_at: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Semantic search over transcript chunks. Returns chunk references
    [{conversation_id, chunk_index, created_at, score}] — hydrate text from
    Firestore (utils.conversations.transcript_chunks.hydrate_chunk_texts)."""
    if index is None:
        return []
    vector = embeddings.embed_query(query)
    filter_data: Dict[str, Any] = {'uid': uid}
    if starts_at is not None and ends_at is not None:
        filter_data['created_at'] = {'$gte': int(starts_at), '$lte': int(ends_at)}
    xc = index.query(
        vector=vector,
        top_k=limit,
        include_metadata=True,
        filter=filter_data,
        namespace=TRANSCRIPT_CHUNKS_NAMESPACE,
    )
    results: List[Dict[str, Any]] = []
    matches: List[Any] = xc.get('matches', [])
    for m in matches:
        raw_md: object = m.get('metadata')
        md: Dict[str, Any] = cast(Dict[str, Any], raw_md) if isinstance(raw_md, dict) else {}
        results.append(
            {
                'created_at': int(md['created_at']) if md.get('created_at') is not None else None,
                'conversation_id': md.get('conversation_id'),
                'chunk_index': int(md['chunk_index']) if md.get('chunk_index') is not None else None,
                'score': m.get('score', 0),
            }
        )
    return results


def delete_transcript_chunk_vectors(uid: str, conversation_id: str) -> None:
    """Delete all chunk vectors for one conversation (id-prefix listing on serverless)."""
    if index is None:
        return
    prefix = f'{uid}-{conversation_id}-c'
    try:
        ids: List[str] = []
        for page in index.list(prefix=prefix, namespace=TRANSCRIPT_CHUNKS_NAMESPACE):
            ids.extend(cast(List[str], page if isinstance(page, list) else [page]))
        for i in range(0, len(ids), 1000):
            index.delete(ids=ids[i : i + 1000], namespace=TRANSCRIPT_CHUNKS_NAMESPACE)
        if ids:
            logger.info(f'delete_transcript_chunk_vectors uid={uid} conversation={conversation_id} count={len(ids)}')
    except Exception:
        logger.warning(f'delete_transcript_chunk_vectors failed uid={uid} conversation={conversation_id}')


def delete_transcript_chunk_vectors_batch(
    uid: str, conversation_ids: List[str], *, raise_on_failure: bool = False
) -> int:
    """Account-deletion purge: drop all transcript-chunk vectors for the user's conversations."""
    if index is None:
        if raise_on_failure and conversation_ids:
            raise RuntimeError('Pinecone index not initialized for transcript chunk vector delete')
        return 0
    if not conversation_ids:
        return 0
    deleted = 0
    failures = 0
    for conversation_id in conversation_ids:
        prefix = f'{uid}-{conversation_id}-c'
        try:
            ids: List[str] = []
            for page in index.list(prefix=prefix, namespace=TRANSCRIPT_CHUNKS_NAMESPACE):
                ids.extend(cast(List[str], page if isinstance(page, list) else [page]))
            for i in range(0, len(ids), 1000):
                index.delete(ids=ids[i : i + 1000], namespace=TRANSCRIPT_CHUNKS_NAMESPACE)
            deleted += len(ids)
        except Exception:
            failures += 1
            logger.warning(f'delete_transcript_chunk_vectors_batch failed uid={uid} conversation={conversation_id}')
    if failures and raise_on_failure:
        raise RuntimeError(f'transcript chunk vector delete failed for {failures} conversation(s)')
    logger.info(f'delete_transcript_chunk_vectors_batch uid={uid} total_deleted={deleted}')
    return deleted
