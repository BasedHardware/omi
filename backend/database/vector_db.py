import json
import os
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import List

from pinecone import Pinecone

from models.conversation import Conversation
from utils.llm.clients import embeddings

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
    print('upsert_vector', res)


def upsert_vector2(uid: str, conversation: Conversation, vector: List[float], metadata: dict):
    data = _get_data(uid, conversation.id, vector)
    data['metadata'].update(metadata)
    res = index.upsert(vectors=[data], namespace="ns1")
    print('upsert_vector', res)


def update_vector_metadata(uid: str, conversation_id: str, metadata: dict):
    metadata['uid'] = uid
    metadata['memory_id'] = conversation_id
    return index.update(f'{uid}-{conversation_id}', set_metadata=metadata, namespace="ns1")


def upsert_vectors(uid: str, vectors: List[List[float]], conversations: List[Conversation]):
    data = [_get_data(uid, conversation.id, vector) for conversation, vector in zip(conversations, vectors)]
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
        print('dates_filter', dates_filter)
        filter_data['$and'].append(
            {'created_at': {'$gte': int(dates_filter[0].timestamp()), '$lte': int(dates_filter[1].timestamp())}}
        )

    print('query_vectors_by_metadata:', json.dumps(filter_data))

    xc = index.query(
        vector=vector, filter=filter_data, namespace="ns1", include_values=False, include_metadata=True, top_k=10000
    )
    if not xc['matches']:
        if len(filter_data['$and']) == 3:
            filter_data['$and'].pop(1)
            print('query_vectors_by_metadata retrying without structured filters:', json.dumps(filter_data))
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
    print('query_vectors_by_metadata result:', conversations_id)
    return conversations_id[:limit] if len(conversations_id) > limit else conversations_id


def delete_vector(conversation_id: str):
    # TODO: does this work?
    result = index.delete(ids=[conversation_id], namespace="ns1")
    print('delete_vector', result)
