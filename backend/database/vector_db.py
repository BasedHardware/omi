import json
import os
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import List

from pinecone import Pinecone

from models.conversation import Conversation
from utils.llm.clients import embeddings
import logging

logger = logging.getLogger(__name__)

if os.getenv('PINECONE_API_KEY') is not None:
    pc = Pinecone(api_key=os.getenv('PINECONE_API_KEY', ''))
    index = pc.Index(os.getenv('PINECONE_INDEX_NAME', ''))
else:
    index = None


def _get_data(uid: str, conversation_id: str, vector: List[float]):
    return {
        "id": f'{uid}-{conversation_id}',
        "values": vector,
        'metadata': {
            'uid': uid,
            'memory_id': conversation_id,
            'created_at': int(datetime.now(timezone.utc).timestamp()),
        },
    }


def upsert_vector(uid: str, conversation: Conversation, vector: List[float]):
    res = index.upsert(vectors=[_get_data(uid, conversation.id, vector)], namespace="ns1")
    logger.info(f'upsert_vector {res}')


def upsert_vector2(uid: str, conversation: Conversation, vector: List[float], metadata: dict):
    data = _get_data(uid, conversation.id, vector)
    data['metadata'].update(metadata)
    res = index.upsert(vectors=[data], namespace="ns1")
    logger.info(f'upsert_vector {res}')


def update_vector_metadata(uid: str, conversation_id: str, metadata: dict):
    metadata['uid'] = uid
    metadata['memory_id'] = conversation_id
    return index.update(f'{uid}-{conversation_id}', set_metadata=metadata, namespace="ns1")


def upsert_vectors(uid: str, vectors: List[List[float]], conversations: List[Conversation]):
    data = [_get_data(uid, conversation.id, vector) for conversation, vector in zip(conversations, vectors)]
    res = index.upsert(vectors=data, namespace="ns1")
    logger.info(f'upsert_vectors {res}')


def query_vectors(query: str, uid: str, starts_at: int = None, ends_at: int = None, k: int = 5) -> List[str]:
    filter_data = {'uid': uid}
    if starts_at is not None:
        filter_data['created_at'] = {'$gte': starts_at, '$lte': ends_at}

    xq = embeddings.embed_query(query)
    xc = index.query(vector=xq, top_k=k, include_metadata=False, filter=filter_data, namespace="ns1")
    return [item['id'].replace(f'{uid}-', '') for item in xc['matches']]


def query_vectors_by_metadata(
    uid: str,
    vector: List[float],
    dates_filter: List[datetime],
    people: List[str],
    topics: List[str],
    entities: List[str],
    dates: List[str],
    limit: int = 5,
):
    filter_data = {
        '$and': [
            {'uid': {'$eq': uid}},
        ]
    }
    if people or topics or entities or dates:
        filter_data['$and'].append(
            {
                '$or': [
                    {'people': {'$in': people}},
                    {'topics': {'$in': topics}},
                    {'entities': {'$in': entities}},
                    # {'dates': {'$in': dates_mentioned}},
                ]
            }
        )
    if dates_filter and len(dates_filter) == 2 and dates_filter[0] and dates_filter[1]:
        logger.info(f'dates_filter {dates_filter}')
        filter_data['$and'].append(
            {'created_at': {'$gte': int(dates_filter[0].timestamp()), '$lte': int(dates_filter[1].timestamp())}}
        )

    xc = index.query(
        vector=vector, filter=filter_data, namespace="ns1", include_values=False, include_metadata=True, top_k=1000
    )
    if not xc['matches']:
        if len(filter_data['$and']) == 3:
            filter_data['$and'].pop(1)
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

    conversation_id_to_matches = defaultdict(int)
    for item in xc['matches']:
        metadata = item['metadata']
        conversation_id = metadata['memory_id']
        for topic in topics:
            if topic in metadata.get('topics', []):
                conversation_id_to_matches[conversation_id] += 1
        for entity in entities:
            if entity in metadata.get('entities', []):
                conversation_id_to_matches[conversation_id] += 1
        for person in people:
            if person in metadata.get('people_mentioned', []):
                conversation_id_to_matches[conversation_id] += 1

    conversations_id = [item['id'].replace(f'{uid}-', '') for item in xc['matches']]
    conversations_id.sort(key=lambda x: conversation_id_to_matches[x], reverse=True)
    return conversations_id[:limit] if len(conversations_id) > limit else conversations_id


def delete_vector(uid: str, conversation_id: str):
    """
    Delete a conversation vector from Pinecone.

    Note: Vectors are stored with ID format '{uid}-{conversation_id}'
    """
    vector_id = f'{uid}-{conversation_id}'
    result = index.delete(ids=[vector_id], namespace="ns1")
    logger.info(f'delete_vector {vector_id} {result}')


# ==========================================
# Memory Vector Functions
# For memory embeddings and semantic search
# ==========================================

MEMORIES_NAMESPACE = "ns2"


def upsert_memory_vector(uid: str, memory_id: str, content: str, category: str):
    """
    Upsert a memory embedding to Pinecone.
    """
    if index is None:
        logger.warning('Pinecone index not initialized, skipping memory vector upsert')
        return None

    vector = embeddings.embed_query(content)
    data = {
        "id": f'{uid}-{memory_id}',
        "values": vector,
        "metadata": {
            "uid": uid,
            "memory_id": memory_id,
            "category": category,
            "created_at": int(datetime.now(timezone.utc).timestamp()),
        },
    }
    res = index.upsert(vectors=[data], namespace=MEMORIES_NAMESPACE)
    logger.info(f'upsert_memory_vector {memory_id} {res}')
    return vector


def find_similar_memories(uid: str, content: str, threshold: float = 0.85, limit: int = 5) -> List[dict]:
    """
    Find memories similar to the given content.
    Returns list of matches with similarity scores.
    Used for duplicate detection and semantic search.
    """
    if index is None:
        logger.warning('Pinecone index not initialized, skipping similarity search')
        return []

    vector = embeddings.embed_query(content)
    filter_data = {'uid': uid}

    xc = index.query(
        vector=vector, top_k=limit, include_metadata=True, filter=filter_data, namespace=MEMORIES_NAMESPACE
    )

    results = []
    for match in xc.get('matches', []):
        if match['score'] >= threshold:
            results.append(
                {
                    'memory_id': match['metadata'].get('memory_id'),
                    'category': match['metadata'].get('category'),
                    'score': match['score'],
                }
            )

    return results


def check_memory_duplicate(uid: str, content: str, threshold: float = 0.85) -> dict | None:
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
    filter_data = {'uid': uid}

    xc = index.query(
        vector=vector, top_k=limit, include_metadata=True, filter=filter_data, namespace=MEMORIES_NAMESPACE
    )

    return [match['metadata'].get('memory_id') for match in xc.get('matches', [])]


def delete_memory_vector(uid: str, memory_id: str):
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
# Screen Activity Vector Functions
# For screenshot embeddings (Gemini embedding-001, 3072-dim)
# ==========================================

SCREEN_ACTIVITY_NAMESPACE = "ns3"


def upsert_screen_activity_vectors(uid: str, rows: List[dict]) -> int:
    """Batch upsert screenshot embeddings to Pinecone ns3."""
    if index is None:
        logger.warning('Pinecone index not initialized, skipping screen activity vector upsert')
        return 0

    vectors = []
    for row in rows:
        embedding = row.get('embedding')
        if not embedding:
            continue
        vectors.append(
            {
                "id": f'{uid}-sa-{row["id"]}',
                "values": embedding,
                "metadata": {
                    "uid": uid,
                    "screenshot_id": str(row['id']),
                    "timestamp": (
                        int(datetime.fromisoformat(row['timestamp'].replace('Z', '+00:00')).timestamp())
                        if isinstance(row['timestamp'], str)
                        else int(row['timestamp'])
                    ),
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
    start_date: int = None,
    end_date: int = None,
    app_filter: str = None,
    k: int = 10,
) -> List[dict]:
    """Vector search across screenshot embeddings in ns3."""
    if index is None:
        logger.warning('Pinecone index not initialized, skipping screen activity search')
        return []

    filter_data = {'uid': uid}
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

    return [
        {
            'screenshot_id': match['metadata'].get('screenshot_id'),
            'timestamp': match['metadata'].get('timestamp'),
            'appName': match['metadata'].get('appName'),
            'score': match['score'],
        }
        for match in xc.get('matches', [])
    ]


def delete_screen_activity_vectors(uid: str, ids: List[int]):
    """Delete screen activity vectors by screenshot IDs."""
    if index is None:
        return
    vector_ids = [f'{uid}-sa-{sid}' for sid in ids]
    index.delete(ids=vector_ids, namespace=SCREEN_ACTIVITY_NAMESPACE)
