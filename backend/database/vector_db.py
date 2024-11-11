import json
import os
from collections import defaultdict
from datetime import datetime, timezone
from typing import List

from pinecone import Pinecone

from models.memory import Memory
from utils.llm import embeddings

if os.getenv('PINECONE_API_KEY') is not None:
    pc = Pinecone(api_key=os.getenv('PINECONE_API_KEY', ''))
    index = pc.Index(os.getenv('PINECONE_INDEX_NAME', ''))
else:
    index = None


def _get_data(uid: str, memory_id: str, vector: List[float]):
    return {
        "id": f'{uid}-{memory_id}',
        "values": vector,
        'metadata': {
            'uid': uid,
            'memory_id': memory_id,
            'created_at': int(datetime.now(timezone.utc).timestamp()),
        }
    }


def upsert_vector(uid: str, memory: Memory, vector: List[float]):
    res = index.upsert(vectors=[_get_data(uid, memory.id, vector)], namespace="ns1")
    print('upsert_vector', res)


def upsert_vector2(uid: str, memory: Memory, vector: List[float], metadata: dict):
    data = _get_data(uid, memory.id, vector)
    data['metadata'].update(metadata)
    res = index.upsert(vectors=[data], namespace="ns1")
    print('upsert_vector', res)


def update_vector_metadata(uid: str, memory_id: str, metadata: dict):
    metadata['uid'] = uid
    metadata['memory_id'] = memory_id
    return index.update(f'{uid}-{memory_id}', set_metadata=metadata, namespace="ns1")


def upsert_vectors(
        uid: str, vectors: List[List[float]], memories: List[Memory]
):
    data = [
        _get_data(uid, memory.id, vector) for memory, vector in
        zip(memories, vectors)
    ]
    res = index.upsert(vectors=data, namespace="ns1")
    print('upsert_vectors', res)


def query_vectors(query: str, uid: str, starts_at: int = None, ends_at: int = None, k: int = 5) -> List[str]:
    filter_data = {'uid': uid}
    if starts_at is not None:
        filter_data['created_at'] = {'$gte': starts_at, '$lte': ends_at}

    # print('filter_data', filter_data)
    xq = embeddings.embed_query(query)
    xc = index.query(vector=xq, top_k=k, include_metadata=False, filter=filter_data, namespace="ns1")
    # print(xc)
    return [item['id'].replace(f'{uid}-', '') for item in xc['matches']]


def query_vectors_by_metadata(
        uid: str, vector: List[float], dates_filter: List[datetime], people: List[str], topics: List[str],
        entities: List[str], dates: List[str]
):
    filter_data = {'$and': [
        {'uid': {'$eq': uid}},
    ]}
    if people or topics or entities or dates:
        filter_data['$and'].append(
            {'$or': [
                {'people': {'$in': people}},
                {'topics': {'$in': topics}},
                {'entities': {'$in': entities}},
                # {'dates': {'$in': dates_mentioned}},
            ]}
        )
    if dates_filter and len(dates_filter) == 2 and dates_filter[0] and dates_filter[1]:
        print('dates_filter', dates_filter)
        filter_data['$and'].append(
            {'created_at': {'$gte': int(dates_filter[0].timestamp()), '$lte': int(dates_filter[1].timestamp())}}
        )

    print('query_vectors_by_metadata:', json.dumps(filter_data))

    xc = index.query(
        vector=vector, filter=filter_data, namespace="ns1", include_values=False,
        include_metadata=True,
        top_k=10000
    )
    if not xc['matches']:
        if len(filter_data['$and']) == 3:
            filter_data['$and'].pop(1)
            print('query_vectors_by_metadata retrying without structured filters:', json.dumps(filter_data))
            xc = index.query(
                vector=vector, filter=filter_data, namespace="ns1", include_values=False,
                include_metadata=True,
                top_k=20
            )
        else:
            return []

    memory_id_to_matches = defaultdict(int)
    for item in xc['matches']:
        metadata = item['metadata']
        memory_id = metadata['memory_id']
        for topic in topics:
            if topic in metadata.get('topics', []):
                memory_id_to_matches[memory_id] += 1
        for entity in entities:
            if entity in metadata.get('entities', []):
                memory_id_to_matches[memory_id] += 1
        for person in people:
            if person in metadata.get('people_mentioned', []):
                memory_id_to_matches[memory_id] += 1

    memories_id = [item['id'].replace(f'{uid}-', '') for item in xc['matches']]
    memories_id.sort(key=lambda x: memory_id_to_matches[x], reverse=True)
    print('query_vectors_by_metadata result:', memories_id)
    return memories_id[:5] if len(memories_id) > 5 else memories_id


def delete_vector(memory_id: str):
    # TODO: does this work?
    result = index.delete(ids=[memory_id], namespace="ns1")
    print('delete_vector', result)
