"""
Deterministic vector/search fakes for hermetic backend e2e tests.

The production code talks to database.vector_db, which reaches the backend through the neutral
vector-store port (`get_vector_store()`, ADR-0033) and embeds through its module-level `embeddings`
(an OpenAI embeddings client). These fakes replace those two seams — the neutral store factory and
`embeddings` — without touching routers or database call sites.
"""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from typing import Any
from utils.vector import filters as neutral_filters

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


class FakeVectorStore:
    """In-memory implementation of the neutral vector-store port (utils.vector, ADR-0033).

    Replaces the old Pinecone-shaped ``FakeVectorIndex``: database.vector_db no longer holds a
    module-level ``index`` — it reaches the backend through ``get_vector_store()`` and speaks the
    neutral surface (``upsert(namespace, records)`` / ``query(...) -> List[VectorMatch]`` /
    ``update_metadata`` / ``delete_by_ids`` / ``delete_by_filter`` / ``list_ids``). Scoring stays the
    deterministic token-overlap Dice used before, so retrieval e2e assertions remain meaningful."""

    def __init__(self, embeddings: DeterministicEmbeddings):
        self.embeddings = embeddings
        self._vectors: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)

    def upsert(self, namespace: str, records: list[dict[str, Any]]) -> int:
        for item in records:
            vector_id = item["id"]
            values = item.get("values", [])
            self.embeddings.remember_vector_text(vector_id, values)
            self._vectors[namespace][vector_id] = {
                "id": vector_id,
                "values": values,
                "metadata": dict(item.get("metadata") or {}),
                "text": getattr(values, "text", "") or self.embeddings.text_for_id(vector_id) or "",
            }
        return len(records)

    def update_metadata(self, namespace: str, id: str, set_metadata: dict[str, Any]) -> None:
        if id in self._vectors[namespace]:
            self._vectors[namespace][id]["metadata"].update(set_metadata)

    def delete_by_ids(self, namespace: str, ids: list[str]) -> int:
        deleted = 0
        for vector_id in list(ids or []):
            if self._vectors[namespace].pop(vector_id, None) is not None:
                deleted += 1
            self.embeddings.forget_vector_text(vector_id)
        return deleted

    def delete_by_filter(self, namespace: str, filter: dict[str, Any]) -> None:
        vector_ids = [
            vector_id
            for vector_id, item in self._vectors[namespace].items()
            if self._matches_filter(item.get("metadata") or {}, filter or {})
        ]
        for vector_id in vector_ids:
            self._vectors[namespace].pop(vector_id, None)
            self.embeddings.forget_vector_text(vector_id)

    def list_ids(self, namespace: str, *, prefix: str):
        ids = [vector_id for vector_id in self._vectors[namespace] if vector_id.startswith(prefix)]
        if ids:
            yield ids

    def query(
        self,
        namespace: str,
        vector: Any,
        *,
        top_k: int,
        include_metadata: bool = True,
        include_values: bool = False,
        filter: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
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
        return matches[:top_k]

    def count(self, namespace: str | None = None) -> int:
        """Vectors stored. Bare ``count()`` sums every namespace (production writes only ``ns1`` today,
        but summing keeps the assertion correct if a caller adds another)."""
        if namespace is None:
            return sum(len(bucket) for bucket in self._vectors.values())
        return len(self._vectors[namespace])

    def _matches_filter(self, metadata: dict[str, Any], filter_data: dict[str, Any]) -> bool:
        """Delegate to the neutral filter contract (ADR-0033) — the SAME interpreter the real adapters
        and the unit-test fake (tests/vector_store_fakes.py) use.

        This used to be a hand-rolled copy, and it had drifted three ways, one of them load-bearing:
          * an operator it did not know fell through to ``return True``, so
            ``{'memory_schema_version': {'$exists': False}}`` — the ns2 legacy barrier — matched
            EVERYTHING, and every retrieval e2e asserting that barrier proved nothing;
          * ``$and``/``$or`` did ``return all(...)``/``return any(...)``, ending the loop, so a clause
            sitting next to them was silently discarded;
          * nothing validated the filter, so an out-of-contract operator passed here and would have been
            rejected by both real adapters.
        A fake more permissive than the real thing does not just miss bugs — it makes assertions lie.
        """
        if not filter_data:
            return True
        neutral_filters.validate(filter_data)
        return neutral_filters.matches(filter_data, metadata)


def install_vector_search_fakes(monkeypatch, vector_db_module):
    """Install the deterministic embeddings + in-memory neutral vector store for one e2e test.

    database.vector_db embeds through its module-level ``embeddings`` and reaches the backend through
    the neutral factory ``get_vector_store()`` (ADR-0033) — there is no longer a module-level ``index``
    to patch. Replace both seams: ``embeddings`` on the module, and ``get_vector_store`` on both the
    package re-export and the factory (callers import it either way) so every ``_vector_store()`` yields
    the fake. Returns ``(store, embeddings)`` — the store keeps ``count()`` for e2e assertions."""
    import utils.vector as vector_pkg
    import utils.vector.factory as vector_factory

    embeddings = DeterministicEmbeddings()
    store = FakeVectorStore(embeddings)
    monkeypatch.setattr(vector_db_module, "embeddings", embeddings)
    monkeypatch.setattr(vector_pkg, "get_vector_store", lambda: store)
    monkeypatch.setattr(vector_factory, "get_vector_store", lambda: store)
    # ``is_vector_available()`` now gates upsert/search on the backend's env (PINECONE_API_KEY / QDRANT_URL),
    # which the e2e conftest strips — the old fake tripped the module-level ``index is not None`` guard
    # instead. Force it True so the fake-backed store is treated as wired (the analog of the old seam).
    monkeypatch.setattr(vector_db_module, "is_vector_available", lambda: True)
    return store, embeddings
