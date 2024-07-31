import os
from datetime import datetime
from typing import List

from pinecone import Pinecone

from utils.llm import embeddings

if os.getenv('PINECONE_API_KEY') is not None:
    pc = Pinecone(api_key=os.getenv('PINECONE_API_KEY'))
    index = pc.Index(os.getenv('PINECONE_INDEX_NAME'))
else:
    index = None


def upsert_vector(memory_id: str, vector: List[float], uid: str, content: str):
    res = index.upsert(
        vectors=[{
            "id": f'{uid}-{memory_id}',
            "values": vector,
            'metadata': {'uid': uid, 'content': content, 'created_at': datetime.utcnow().timestamp() / 1000}
        }],
        namespace="ns1"
    )


def query_vectors(query: str, uid: str):
    xq = embeddings.embed_query(query)
    xc = index.query(vector=xq, top_k=5, include_metadata=False, filter={"uid": uid}, namespace="ns1")
    print(xc)
    return [item['id'] for item in xc['matches']]


def delete_vector(memory_id: str):
    index.delete(ids=[memory_id], namespace="ns1")
