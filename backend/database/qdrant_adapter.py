import uuid

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchAny,
    MatchValue,
    PointIdsList,
    PointStruct,
    Range,
    VectorParams,
)

VECTOR_DIM = 3072  # text-embedding-3-large

COLLECTIONS = {
    "ns1": "ns1",  # conversations
    "ns2": "ns2",  # memories
}


def _ensure_collection(client: QdrantClient, name: str):
    try:
        if not client.collection_exists(name):
            client.create_collection(
                collection_name=name,
                vectors_config=VectorParams(size=VECTOR_DIM, distance=Distance.COSINE),
            )
    except Exception:
        if not client.collection_exists(name):
            raise


def _deterministic_point_id(string_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, string_id))


def _translate_filter(pinecone_filter: dict) -> Filter:
    if not pinecone_filter:
        return None

    conditions = []
    for key, value in pinecone_filter.items():
        if key == "$and":
            sub = [_translate_filter(f) for f in value]
            return Filter(must=[s for s in sub if s is not None])
        if key == "$or":
            sub = [_translate_filter(f) for f in value]
            return Filter(should=[s for s in sub if s is not None])
        if isinstance(value, dict):
            if "$eq" in value:
                conditions.append(FieldCondition(key=key, match=MatchValue(value=value["$eq"])))
            elif "$in" in value:
                conditions.append(FieldCondition(key=key, match=MatchAny(any=value["$in"])))
            elif "$gte" in value or "$lte" in value:
                conditions.append(
                    FieldCondition(
                        key=key,
                        range=Range(
                            gte=value.get("$gte"),
                            lte=value.get("$lte"),
                        ),
                    )
                )
        else:
            conditions.append(FieldCondition(key=key, match=MatchValue(value=value)))

    if not conditions:
        return None
    return Filter(must=conditions)


class QdrantIndex:
    def __init__(self, host: str = "localhost", port: int = 6333):
        self._client = QdrantClient(host=host, port=port)
        for name in COLLECTIONS.values():
            _ensure_collection(self._client, name)

    def upsert(self, vectors: list, namespace: str = "ns1"):
        col = COLLECTIONS.get(namespace, namespace)
        _ensure_collection(self._client, col)

        points = []
        for vec in vectors:
            point_id = _deterministic_point_id(vec["id"])
            payload = dict(vec.get("metadata", {}))
            payload["_original_id"] = vec["id"]
            points.append(PointStruct(id=point_id, vector=vec["values"], payload=payload))

        self._client.upsert(collection_name=col, points=points)
        return {"upserted_count": len(points)}

    def query(
        self,
        vector: list,
        top_k: int = 10,
        filter: dict = None,
        namespace: str = "ns1",
        include_metadata: bool = False,
        include_values: bool = False,
        **kwargs,
    ):
        col = COLLECTIONS.get(namespace, namespace)
        _ensure_collection(self._client, col)

        qdrant_filter = _translate_filter(filter)
        results = self._client.query_points(
            collection_name=col,
            query=vector,
            query_filter=qdrant_filter,
            limit=top_k,
            with_payload=True,
        )

        matches = []
        for point in results.points:
            match = {
                "id": point.payload.get("_original_id", str(point.id)),
                "score": point.score,
            }
            if include_metadata or kwargs.get("include_metadata"):
                match["metadata"] = {k: v for k, v in point.payload.items() if k != "_original_id"}
            matches.append(match)

        return {"matches": matches}

    def update(self, id: str, set_metadata: dict = None, namespace: str = "ns1"):
        col = COLLECTIONS.get(namespace, namespace)
        point_id = _deterministic_point_id(id)

        if set_metadata:
            self._client.set_payload(
                collection_name=col,
                payload=set_metadata,
                points=[point_id],
            )
        return {}

    def delete(self, ids: list = None, namespace: str = "ns1"):
        col = COLLECTIONS.get(namespace, namespace)
        if ids:
            point_ids = [_deterministic_point_id(i) for i in ids]
            self._client.delete(
                collection_name=col,
                points_selector=PointIdsList(points=point_ids),
            )
        return {}
