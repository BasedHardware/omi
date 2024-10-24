import json
import os
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
            'created_at': datetime.now(timezone.utc).timestamp() / 1000,  # TODO: check this
        }
    }


def upsert_vector(uid: str, memory: Memory, vector: List[float]):
    res = index.upsert(vectors=[_get_data(uid, memory.id, vector)], namespace="ns1")
    print('upsert_vector', res)


def update_vector_metadata(uid: str, memory_id: str, metadata: dict):
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
        uid: str, dates_filter: List[datetime], people_mentioned: List[str], topics_discussed: List[str],
        entities: List[str], dates_mentioned: List[str]
):
    print('query_vectors_by_metadata result:', uid)

    filter_data = {'$and': [
        {'uid': {'$eq': uid}},
        {'$or': [
            {'people': {'$in': people_mentioned}},
            {'topics': {'$in': topics_discussed}},
            {'entities': {'$in': entities}},
            {'dates': {'$in': dates_mentioned}},
        ]},
        {'created_at': {'$gte': int(dates_filter[0].timestamp()), '$lte': int(dates_filter[1].timestamp())} if len(
            dates_filter) == 2 else {}},
    ]}

    # TODO: improve search, don't use 0,0, can use smth better?, also topk 1k would make it slower.
    xc = index.query(
        vector=[0] * 3072, filter=filter_data, namespace="ns1", include_values=False,
        include_metadata=True,
        top_k=50
    )
    memories_id = [item['id'].replace(f'{uid}-', '') for item in xc['matches']]

    print('query_vectors_by_metadata result:', memories_id)
    return memories_id


def delete_vector(memory_id: str):
    # TODO: does this work?
    result = index.delete(ids=[memory_id], namespace="ns1")
    print('delete_vector', result)
