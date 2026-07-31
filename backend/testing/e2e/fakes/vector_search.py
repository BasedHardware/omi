"""
Deterministic vector/search fakes for hermetic backend e2e tests.

The production code talks to database.vector_db, whose module-level `index`
is a Pinecone client and whose `embeddings` object is an OpenAI embeddings
client. These fakes replace those two service-client seams without touching
routers or database call sites.
"""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from typing import Any

_TOKEN_RE = re.compile(r"[a-z0-9]+")


class DeterministicVector(list):
    """List-like vector that carries its source text for the fake index.

    Pinecone receives plain lists in production. The e2e fake can retain extra
    local metadata because no serialization boundary is crossed.
    """

    def __init__(self, values: list[float], text: str):
        super().__init__(values)
        self.text = text


def _tokens(text: str) -> set[str]:
    return set(_TOKEN_RE.findall((text or "").lower()))


def _stable_vector(text: str, dimensions: int = 16) -> list[float]:
    digest = hashlib.sha256((text or "").encode("utf-8")).digest()
    values = []
    for idx in range(dimensions):
        byte = digest[idx % len(digest)]
        values.append(round((byte / 255.0) * 2 - 1, 6))
    return values


def _score(query: str, candidate: str) -> float:
    query_tokens = _tokens(query)
    candidate_tokens = _tokens(candidate)
    if not query_tokens or not candidate_tokens:
        return 0.0
    overlap = query_tokens & candidate_tokens
    if not overlap:
        return 0.0
    # Dice-style score gives intuitive 0..1 relevance while keeping exact
    # multi-token matches above action-item min_score=0.3.
    return (2.0 * len(overlap)) / (len(query_tokens) + len(candidate_tokens))


class DeterministicEmbeddings:
    """Small deterministic replacement for LangChain/OpenAI embeddings."""

    def __init__(self):
        self._texts_by_vector_id: dict[str, str] = {}

    def embed_query(self, text: str) -> DeterministicVector:
        return DeterministicVector(_stable_vector(text), text or "")

    def embed_documents(self, texts: list[str]) -> list[DeterministicVector]:
        return [self.embed_query(text) for text in texts]

    def remember_vector_text(self, vector_id: str, vector: Any):
        text = getattr(vector, "text", "") or ""
        self._texts_by_vector_id[vector_id] = text

    def forget_vector_text(self, vector_id: str):
        self._texts_by_vector_id.pop(vector_id, None)

    def text_for_id(self, vector_id: str) -> str | None:
        return self._texts_by_vector_id.get(vector_id)


class FakeVectorIndex:
    """In-memory Pinecone-like index with namespace isolation."""

    def __init__(self, embeddings: DeterministicEmbeddings):
        self.embeddings = embeddings
        self._vectors: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)

    def upsert(self, vectors: list[dict[str, Any]], namespace: str = "") -> dict[str, int]:
        for item in vectors:
            vector_id = item["id"]
            values = item.get("values", [])
            self.embeddings.remember_vector_text(vector_id, values)
            self._vectors[namespace][vector_id] = {
                "id": vector_id,
                "values": values,
                "metadata": dict(item.get("metadata") or {}),
                "text": getattr(values, "text", "") or self.embeddings.text_for_id(vector_id) or "",
            }
        return {"upserted_count": len(vectors)}

    def update(self, id: str, set_metadata: dict[str, Any], namespace: str = "") -> dict[str, int]:
        if id in self._vectors[namespace]:
            self._vectors[namespace][id]["metadata"].update(set_metadata)
            return {"updated_count": 1}
        return {"updated_count": 0}

    def delete(
        self,
        ids: list[str] | None = None,
        namespace: str = "",
        filter: dict[str, Any] | None = None,
    ) -> dict[str, int]:
        if ids is not None and filter is not None:
            raise ValueError("delete accepts ids or filter, not both")
        vector_ids = list(ids or [])
        if filter is not None:
            vector_ids = [
                vector_id
                for vector_id, item in self._vectors[namespace].items()
                if self._matches_filter(item.get("metadata") or {}, filter)
            ]
        deleted = 0
        for vector_id in vector_ids:
            if self._vectors[namespace].pop(vector_id, None) is not None:
                deleted += 1
            self.embeddings.forget_vector_text(vector_id)
        return {"deleted_count": deleted}

    def list(self, prefix: str = "", namespace: str = ""):
        ids = [vector_id for vector_id in self._vectors[namespace] if vector_id.startswith(prefix)]
        if ids:
            yield ids

    def query(
        self,
        vector: Any,
        top_k: int,
        include_metadata: bool = False,
        include_values: bool = False,
        filter: dict[str, Any] | None = None,
        namespace: str = "",
    ) -> dict[str, list[dict[str, Any]]]:
        query_text = getattr(vector, "text", "") or ""
        matches = []
        for vector_id, item in self._vectors[namespace].items():
            metadata = item.get("metadata") or {}
            if not self._matches_filter(metadata, filter or {}):
                continue
            score = _score(query_text, item.get("text", ""))
            if score <= 0.0:
                continue
            match = {"id": vector_id, "score": score}
            if include_metadata:
                match["metadata"] = dict(metadata)
            if include_values:
                match["values"] = item.get("values")
            matches.append(match)
        matches.sort(key=lambda row: (-row["score"], row["id"]))
        return {"matches": matches[:top_k]}

    def count(self, namespace: str = "") -> int:
        return len(self._vectors[namespace])

    def _matches_filter(self, metadata: dict[str, Any], filter_data: dict[str, Any]) -> bool:
        if not filter_data:
            return True
        for key, expected in filter_data.items():
            if key == "$and":
                return all(self._matches_filter(metadata, clause) for clause in expected)
            if key == "$or":
                return any(self._matches_filter(metadata, clause) for clause in expected)

            actual = metadata.get(key)
            if isinstance(expected, dict):
                for op, value in expected.items():
                    if op == "$eq" and actual != value:
                        return False
                    if op == "$in":
                        actual_values = actual if isinstance(actual, list) else [actual]
                        if not any(item in value for item in actual_values):
                            return False
                    if op == "$gte" and (actual is None or actual < value):
                        return False
                    if op == "$lte" and (actual is None or actual > value):
                        return False
                    if op == "$exists":
                        present = key in metadata and metadata.get(key) is not None
                        if bool(value) != present:
                            return False
            elif actual != expected:
                return False
        return True


class _FakeVectorStoreOverIndex:
    """Port-shaped facade over ``FakeVectorIndex`` (ADR-0033). vector_db.py migrated from the raw
    Pinecone ``index`` to the neutral ``_vector_store()`` seam, so the fake is installed there; this
    reuses FakeVectorIndex's storage/scoring/filter and translates the 6 port verbs to it."""

    def __init__(self, index: "FakeVectorIndex"):
        self._index = index

    def upsert(self, namespace, records):
        self._index.upsert(list(records), namespace=namespace)
        return len(records)

    def query(self, namespace, vector, *, top_k, filter=None, include_metadata=True, include_values=False):
        return self._index.query(
            vector,
            top_k,
            include_metadata=include_metadata,
            include_values=include_values,
            filter=filter,
            namespace=namespace,
        )["matches"]

    def update_metadata(self, namespace, id, set_metadata):
        self._index.update(id, set_metadata, namespace=namespace)

    def delete_by_ids(self, namespace, ids):
        self._index.delete(ids=list(ids), namespace=namespace)
        return len(ids)

    def delete_by_filter(self, namespace, filter):
        self._index.delete(filter=filter, namespace=namespace)

    def list_ids(self, namespace, *, prefix):
        yield from self._index.list(prefix=prefix, namespace=namespace)


def install_vector_search_fakes(monkeypatch, vector_db_module):
    """Patch database.vector_db's vector-store and embedding seams for one test.

    Points the neutral ``_vector_store()`` seam at a port-shaped fake and marks the store available
    (``is_vector_available()`` reads env), so the vector_db guards pass regardless of PINECONE_* env.
    Returns the underlying FakeVectorIndex (for count/_vectors introspection) + embeddings, unchanged."""
    embeddings = DeterministicEmbeddings()
    index = FakeVectorIndex(embeddings)
    store = _FakeVectorStoreOverIndex(index)
    monkeypatch.setattr(vector_db_module, "embeddings", embeddings)
    monkeypatch.setattr(vector_db_module, "_vector_store", lambda: store)
    monkeypatch.setenv("PINECONE_API_KEY", "fake-e2e-key")
    monkeypatch.setenv("PINECONE_INDEX_NAME", "fake-e2e-index")
    return index, embeddings
