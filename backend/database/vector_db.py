import json
import os
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import List, Optional

# Check if Pinecone is properly configured
pinecone_api_key = os.getenv('PINECONE_API_KEY')
pinecone_index_name = os.getenv('PINECONE_INDEX_NAME')

# Only import Pinecone if the API key is available
if pinecone_api_key:
    from pinecone import Pinecone

# Create a mock index for development or when Pinecone is not configured
class MockPineconeIndex:
    def __init__(self):
        self.vectors = {}
        print("Using MockPineconeIndex - vector search will return empty results")

    def upsert(self, vectors, namespace=None):
        for vector in vectors:
            self.vectors[vector['id']] = {
                'values': vector['values'],
                'metadata': vector.get('metadata', {})
            }
        return {'upserted_count': len(vectors)}

    def query(self, vector=None, namespace=None, top_k=10, filter=None, include_metadata=True, include_values=True):
        # Return empty results for mock implementation
        return {'matches': []}

    def delete(self, ids, namespace=None):
        deleted_count = 0
        for id in ids:
            if id in self.vectors:
                del self.vectors[id]
                deleted_count += 1
        return {'deleted_count': deleted_count}

    def update(self, id, set_metadata=None, namespace=None):
        if id in self.vectors and set_metadata:
            self.vectors[id]['metadata'].update(set_metadata)
        return {'id': id}

# Initialize the index based on configuration
if pinecone_api_key and pinecone_index_name:
    # Both API key and index name are provided
    pc = Pinecone(api_key=pinecone_api_key)
    index = pc.Index(pinecone_index_name)
    print(f"Connected to Pinecone index: {pinecone_index_name}")
else:
    # Either API key or index name is missing or both
    if pinecone_api_key:
        print("WARNING: PINECONE_INDEX_NAME is not set in .env file. Using a mock index.")
    else:
        print("INFO: Pinecone is not configured. Vector search functionality will use mock implementation.")
    index = MockPineconeIndex()


def _get_data(uid: str, conversation_id: str, vector: List[float]):
    return {
        "id": f'{uid}-{conversation_id}',
        "values": vector,
        'metadata': {
            'uid': uid,
            'memory_id': conversation_id,
            'created_at': int(datetime.now(timezone.utc).timestamp()),
        }
    }


def upsert_vector(uid: str, conversation, vector: List[float]):
    try:
        res = index.upsert(vectors=[_get_data(uid, conversation.id, vector)], namespace="ns1")
        print('upsert_vector', res)
    except Exception as e:
        print(f"Error in upsert_vector: {e}")


def upsert_vector2(uid: str, conversation, vector: List[float], metadata: dict):
    try:
        data = _get_data(uid, conversation.id, vector)
        data['metadata'].update(metadata)
        res = index.upsert(vectors=[data], namespace="ns1")
        print('upsert_vector', res)
    except Exception as e:
        print(f"Error in upsert_vector2: {e}")


def update_vector_metadata(uid: str, conversation_id: str, metadata: dict):
    try:
        metadata['uid'] = uid
        metadata['memory_id'] = conversation_id
        return index.update(f'{uid}-{conversation_id}', set_metadata=metadata, namespace="ns1")
    except Exception as e:
        print(f"Error in update_vector_metadata: {e}")
        return {"error": str(e)}


def upsert_vectors(uid: str, vectors: List[List[float]], conversations: List):
    try:
        data = [
            _get_data(uid, conversation.id, vector) for conversation, vector in
            zip(conversations, vectors)
        ]
        res = index.upsert(vectors=data, namespace="ns1")
        print('upsert_vectors', res)
    except Exception as e:
        print(f"Error in upsert_vectors: {e}")


def query_vectors(query: str, uid: str, starts_at: int = None, ends_at: int = None, k: int = 5) -> List[str]:
    try:
        from utils.llm import embeddings

        filter_data = {'uid': uid}
        if starts_at is not None:
            filter_data['created_at'] = {'$gte': starts_at, '$lte': ends_at}

        xq = embeddings.embed_query(query)
        xc = index.query(vector=xq, top_k=k, include_metadata=False, filter=filter_data, namespace="ns1")
        return [item['id'].replace(f'{uid}-', '') for item in xc['matches']]
    except Exception as e:
        print(f"Error in query_vectors: {e}")
        return []


def query_vectors_by_metadata(
        uid: str, vector: List[float], dates_filter: List[datetime], people: List[str], topics: List[str],
    entities: List[str], dates: List[str], limit: int = 5,
):
    try:
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
    except Exception as e:
        print(f"Error in query_vectors_by_metadata: {e}")
        return []


def delete_vector(conversation_id: str):
    try:
        result = index.delete(ids=[conversation_id], namespace="ns1")
        print('delete_vector', result)
    except Exception as e:
        print(f"Error in delete_vector: {e}")
