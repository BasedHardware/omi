import os
from datetime import datetime
from typing import List

from pinecone import Pinecone

from models.memory import Memory
from utils.llm import embeddings

if os.getenv('PINECONE_API_KEY') is not None:
    pc = Pinecone(api_key=os.getenv('PINECONE_API_KEY'))
    index = pc.Index(os.getenv('PINECONE_INDEX_NAME'))
else:
    index = None


def _get_data(uid: str, memory_id: str, vector: List[float], transcript: str, summary: str):
    return {
        "id": f'{uid}-{memory_id}',
        "values": vector,
        'metadata': {
            'uid': uid,
            'transcript': transcript,
            'summary': summary,
            'created_at': datetime.utcnow().timestamp() / 1000,
        }
    }


def upsert_vector(uid: str, memory: Memory, vector: List[float]):
    res = index.upsert(
        vectors=[_get_data(uid, memory.id, vector, memory.transcript, memory.structured)], namespace="ns1"
    )
    print('upsert_vector', res)


def upsert_vectors(
        uid: str, vectors: List[List[float]], memories: List[Memory]
):
    data = [
        _get_data(uid, memory.id, vector, memory.transcript, str(memory.structured)) for memory, vector in
        zip(memories, vectors)
    ]
    res = index.upsert(vectors=data, namespace="ns1")
    print('upsert_vectors', res)


def query_vectors(query: str, uid: str):
    xq = embeddings.embed_query(query)
    xc = index.query(vector=xq, top_k=5, include_metadata=False, filter={"uid": uid}, namespace="ns1")
    print(xc)
    return [item['id'] for item in xc['matches']]


def delete_vector(memory_id: str):
    index.delete(ids=[memory_id], namespace="ns1")
