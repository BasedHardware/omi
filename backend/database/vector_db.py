from __future__ import annotations

import json
import logging
import os
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import wraps
from typing import Any, Callable, Dict, List, Optional, TypedDict, TypeVar, cast

from pinecone import Pinecone

from database import projection_repair
from database._client import data_plane_db as default_db_client
from database.legal_holds import external_write_fence
from database.memory_vector_metadata import (
    build_archive_memory_vector_filter,
    build_canonical_memory_vector_delete_filter,
    build_default_memory_vector_filter,
    build_ledger_memory_vector_filter,
    build_memory_vector_metadata,
    canonical_memory_provider_id,
    parse_memory_search_vector_hit,
    strip_null_metadata_values,
)
from models.conversation_metadata import ConversationMetadataKeys, metadata_list
from models.product_memory import MemoryItem
from models.memory_search_gateway import SearchMode, SearchVectorHit
from utils.llm.clients import embeddings

logger = logging.getLogger(__name__)

R = TypeVar("R")


def _account_external_data_write(func: Callable[..., R]) -> Callable[..., R]:
    """Linearize provider mutations against explicit/account deletion."""

    @wraps(func)
    def wrapped(account: Any, *args: Any, **kwargs: Any) -> R:
        # With no provider configured there is no external mutation to fence.
        # Let the function's established fail-open return contract run without
        # touching Firestore (important for offline/local deployments).
        if index is None:
            return func(account, *args, **kwargs)
        uid = account.uid if isinstance(account, MemoryItem) else account
        if not isinstance(uid, str) or not uid:
            raise ValueError("provider mutation requires an account identity")
        with external_write_fence(uid, firestore_client=default_db_client):
            return func(account, *args, **kwargs)

    return wrapped


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
    canonical memory projection keys (added by ``build_memory_vector_metadata``)
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


@_account_external_data_write
def upsert_vector2(uid: str, conversation_id: str, vector: List[float], metadata: Dict[str, Any]) -> None:
    if index is None:
        return
    data: VectorRecordDoc = _get_data(uid, conversation_id, vector)
    typed_metadata: Dict[str, Any] = data['metadata']
    typed_metadata.update(metadata)
    res = index.upsert(vectors=[data], namespace="ns1")
    logger.info(f'upsert_vector {res}')


@_account_external_data_write
def update_vector_metadata(uid: str, conversation_id: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
    if index is None:
        return {}
    metadata['uid'] = uid
    metadata['memory_id'] = conversation_id
    result: Dict[str, Any] = index.update(f'{uid}-{conversation_id}', set_metadata=metadata, namespace="ns1")
    return result


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
    query_vector: Optional[List[float]] = None,
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

    xq = query_vector if query_vector is not None else embeddings.embed_query(query)
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
    if index is None:
        return []
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
        # Relax-retry when the structured people/topics/entities $or clause produced no hits, dropping
        # it and re-querying uid-only. The $or clause, when present, is always and_clauses[1] (the date
        # range is appended after it). The previous len == 3 guard only relaxed when a date filter was
        # ALSO present, so the common no-date query (uid + $or, len == 2) fell through to return [] and
        # never broadened. Never pop a date-only clause.
        if len(and_clauses) > 1 and '$or' in and_clauses[1]:
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


@_account_external_data_write
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


@_account_external_data_write
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
            or projection_repair.projection_metadata_for_fact(
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


@_account_external_data_write
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
                or projection_repair.projection_metadata_for_fact(
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


@_account_external_data_write
def upsert_canonical_memory_vector(
    item: MemoryItem,
    *,
    projection_commit_id: str | None = None,
) -> List[float] | None:
    """Upsert one canonical memory vector using a user-scoped provider id."""
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
        "id": canonical_memory_provider_id(item.uid, item.memory_id),
        "values": vector,
        "metadata": metadata,
    }
    # Migration cleanup is metadata-fenced: remove both the former bare
    # ``memory_id`` row and any prior ``memproj:`` row for this user only.
    # A failed cleanup must abort the upsert so the durable outbox retries.
    index.delete(
        filter=build_canonical_memory_vector_delete_filter(item.uid, item.memory_id),
        namespace=MEMORIES_NAMESPACE,
    )
    res = index.upsert(vectors=[data], namespace=MEMORIES_NAMESPACE)
    logger.info('upsert_canonical_memory_vector %s %s', item.memory_id, res)
    return vector


def delete_canonical_memory_vectors(uid: str, memory_id: str | None = None) -> bool:
    """Delete canonical vectors by authoritative UID metadata, including legacy bare-ID rows."""
    if index is None:
        logger.warning('Pinecone index not initialized, skipping canonical memory vector filter delete')
        return False
    delete_filter = build_canonical_memory_vector_delete_filter(uid, memory_id)
    index.delete(filter=delete_filter, namespace=MEMORIES_NAMESPACE)
    logger.info(
        'delete_canonical_memory_vectors uid=%s memory_id=%s',
        uid,
        memory_id or '*',
    )
    return True


def query_memory_vector_candidates(
    uid: str,
    query: str,
    *,
    mode: SearchMode = SearchMode.default,
    limit: int = 10,
    ledger_kinds: Optional[List[str]] = None,
) -> VectorCandidateQueryResult:
    """Query ns2 for canonical neutral-metadata memory vector candidates."""
    if index is None:
        logger.warning('Pinecone index not initialized, skipping canonical memory vector candidate search')
        return VectorCandidateQueryResult()

    bounded_limit = max(1, min(int(limit or 10), 60))
    vector = embeddings.embed_query(query)
    if ledger_kinds is not None and mode == SearchMode.default:
        filter_data = build_ledger_memory_vector_filter(uid, ledger_kinds)
    else:
        filter_data = (
            build_archive_memory_vector_filter(uid)
            if mode == SearchMode.archive_explicit
            else build_default_memory_vector_filter(uid)
        )
    response = index.query(
        vector=vector,
        top_k=bounded_limit,
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


# ==========================================
# X (Twitter) Post Vector Functions
# Semantic search over the user's raw imported tweets/bookmarks.
# ==========================================

X_POSTS_NAMESPACE = "ns_x"


@_account_external_data_write
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


@_account_external_data_write
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
        if isinstance(ts_value, str):
            parsed_timestamp = datetime.fromisoformat(ts_value.replace('Z', '+00:00'))
            if parsed_timestamp.tzinfo is None:
                parsed_timestamp = parsed_timestamp.replace(tzinfo=timezone.utc)
            timestamp = int(parsed_timestamp.timestamp())
        else:
            timestamp = int(ts_value)
        metadata = {
            "uid": uid,
            "screenshot_id": str(row.get("storageId") or row['id']),
            "timestamp": timestamp,
            "appName": row.get('appName', ''),
        }
        if row.get('deviceName'):
            metadata['deviceName'] = row['deviceName']
        if row.get('clientDeviceId'):
            metadata['clientDeviceId'] = row['clientDeviceId']
        vectors.append(
            {"id": f'{uid}-sa-{row.get("storageId") or row["id"]}', "values": embedding, "metadata": metadata}
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
    # Chunk to stay within Pinecone's per-delete id limit (1,000).
    for i in range(0, len(vector_ids), 1000):
        index.delete(ids=vector_ids[i : i + 1000], namespace=SCREEN_ACTIVITY_NAMESPACE)


# ==========================================
# Action Item Vector Functions
# ==========================================

ACTION_ITEMS_NAMESPACE = "ns4"


@_account_external_data_write
def upsert_action_item_vector(uid: str, action_item_id: str, description: str) -> List[float] | None:
    """Index one action item for semantic search.

    Every caller runs this *after* the Firestore write has already committed, so an
    embedding/Pinecone failure must not propagate: it would turn a successful
    create/update into an HTTP 500 (and make clients retry a write that landed).
    Degrades to ``None`` — the task is simply absent from semantic search until it
    is next indexed, matching ``find_similar_action_items``.
    """
    if index is None:
        logger.warning('Pinecone index not initialized, skipping action item vector upsert')
        return None

    try:
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
    except Exception as e:
        logger.exception(
            f'upsert_action_item_vector failed uid={uid} action_item_id={action_item_id} '
            f'(task saved, vector missing): {e}'
        )
        return None


@_account_external_data_write
def upsert_action_item_vectors_batch(uid: str, items: List[Dict[str, Any]]) -> int:
    """Index a batch of action items. Best-effort, for the same reason as
    ``upsert_action_item_vector``: returns 0 instead of raising into a caller
    whose Firestore writes already succeeded."""
    if index is None:
        logger.warning('Pinecone index not initialized, skipping action item vector batch upsert')
        return 0

    if not items:
        return 0

    try:
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
    except Exception as e:
        logger.exception(
            f'upsert_action_item_vectors_batch failed uid={uid} count={len(items)} '
            f'(tasks saved, vectors missing): {e}'
        )
        return 0


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
    # Chunk to stay within Pinecone's per-delete id limit (1,000).
    for i in range(0, len(vector_ids), 1000):
        index.delete(ids=vector_ids[i : i + 1000], namespace=ACTION_ITEMS_NAMESPACE)
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

    Canonical cleanup uses ``delete_canonical_memory_vectors`` so legacy
    provider identities are removed by UID metadata instead of guessed IDs.
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


@_account_external_data_write
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
    query_vector: Optional[List[float]] = None,
) -> List[Dict[str, Any]]:
    """Semantic search over transcript chunks. Returns chunk references
    [{conversation_id, chunk_index, created_at, score}] — hydrate text from
    Firestore (utils.conversations.transcript_chunks.hydrate_chunk_texts)."""
    if index is None:
        return []
    filter_data: Dict[str, Any] = {'uid': uid}
    # Same one-sided / invalid-range rules as summary vector search (_created_at_filter).
    created_at = _created_at_filter(starts_at, ends_at)
    if (starts_at is not None or ends_at is not None) and created_at is None:
        return []
    if created_at is not None:
        filter_data['created_at'] = created_at
    vector = query_vector if query_vector is not None else embeddings.embed_query(query)
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
