"""Regression tests for the vector-repair outbox worker's backend-aware dependency resolution.

The worker must build its dependencies for whatever vector + embeddings backend is configured, not a
fixed cloud Pinecone/OpenAI pair — so the documented on-prem Qdrant + OMI_EMBEDDINGS path works and an
enabled worker fails deterministically on a key the *selected* backend never reads (PR 10887 review).
"""

from __future__ import annotations

import types
from typing import Any, Dict, List

import pytest

from scripts.vector_repair_outbox_worker_entrypoint import (
    build_vector_repair_outbox_production_dependencies,
)


class _RecordingVectorStore:
    """Minimal neutral VectorStore stand-in that records the port calls the worker makes."""

    def __init__(self) -> None:
        self.deleted: List[tuple[str, Dict[str, Any]]] = []
        self.upserted: List[tuple[str, List[Dict[str, Any]]]] = []

    def delete_by_filter(self, namespace: str, filter: Dict[str, Any]) -> None:
        self.deleted.append((namespace, filter))

    def upsert(self, namespace: str, records: List[Dict[str, Any]]) -> int:
        self.upserted.append((namespace, records))
        return len(records)


def _module_loader(store: _RecordingVectorStore, *, embed=lambda text: [0.1, 0.2]):
    """Return a module_loader that hands back fakes for the three imported modules — no real
    Firestore/embeddings/vector client is ever constructed."""
    selected_env: Dict[str, Any] = {}

    def get_vector_store(env):
        selected_env["env"] = env
        return store

    modules = {
        "database._client": types.SimpleNamespace(db=object()),
        "utils.llm.clients": types.SimpleNamespace(embeddings=types.SimpleNamespace(embed_query=embed)),
        "utils.vector.factory": types.SimpleNamespace(get_vector_store=get_vector_store),
    }

    def loader(name: str):
        return modules[name]

    return loader, selected_env


def test_qdrant_with_local_embeddings_needs_no_openai_or_pinecone_key():
    # The exact on-prem posture the review flagged: Qdrant vector store + an OpenAI-compatible local
    # embeddings endpoint. No OPENAI_API_KEY and no PINECONE_* — building deps must still succeed.
    store = _RecordingVectorStore()
    loader, selected = _module_loader(store)
    env = {
        "VECTOR_STORE_BACKEND": "qdrant",
        "QDRANT_URL": "http://qdrant:6333",
        "OMI_EMBEDDINGS_BASE_URL": "http://ollama:11434/v1",
    }

    deps = build_vector_repair_outbox_production_dependencies(env, module_loader=loader)

    assert deps.vector_deleter is not None and deps.vector_repairer is not None
    # The worker selected the SAME backend it validated (get_vector_store received the worker env).
    assert selected["env"] is env


def test_qdrant_missing_url_fails_before_any_client():
    loader, _ = _module_loader(_RecordingVectorStore())
    env = {"VECTOR_STORE_BACKEND": "qdrant", "OMI_EMBEDDINGS_BASE_URL": "http://ollama:11434/v1"}
    with pytest.raises(ValueError, match="QDRANT_URL"):
        build_vector_repair_outbox_production_dependencies(env, module_loader=loader)


def test_unknown_backend_is_rejected():
    loader, _ = _module_loader(_RecordingVectorStore())
    env = {"VECTOR_STORE_BACKEND": "weaviate", "OMI_EMBEDDINGS_BASE_URL": "http://e"}
    with pytest.raises(ValueError, match="pinecone.*qdrant|qdrant.*pinecone"):
        build_vector_repair_outbox_production_dependencies(env, module_loader=loader)


def test_pinecone_default_still_requires_pinecone_and_cloud_openai_key():
    # Legacy/cloud principal: no OMI_EMBEDDINGS_BASE_URL and default backend -> Pinecone + OPENAI_API_KEY
    # are still mandatory (the cloud path is unchanged).
    loader, _ = _module_loader(_RecordingVectorStore())
    with pytest.raises(ValueError, match="PINECONE_API_KEY"):
        build_vector_repair_outbox_production_dependencies({}, module_loader=loader)
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        build_vector_repair_outbox_production_dependencies(
            {"PINECONE_API_KEY": "k", "PINECONE_INDEX_NAME": "i"}, module_loader=loader
        )


def test_cloud_pinecone_with_all_keys_builds():
    store = _RecordingVectorStore()
    loader, selected = _module_loader(store)
    env = {"PINECONE_API_KEY": "k", "PINECONE_INDEX_NAME": "i", "OPENAI_API_KEY": "sk-x"}
    deps = build_vector_repair_outbox_production_dependencies(env, module_loader=loader)
    assert deps.vector_deleter is not None
    assert selected["env"] is env


def test_vector_deleter_routes_to_the_neutral_store_delete_by_filter():
    # Proves the deleter the entrypoint builds is bound to the neutral port (not a raw Pinecone client):
    # invoking it calls delete_by_filter on the configured store with the neutral $-DSL fence + ns2.
    store = _RecordingVectorStore()
    loader, _ = _module_loader(store)
    env = {"VECTOR_STORE_BACKEND": "qdrant", "QDRANT_URL": "http://q", "OMI_EMBEDDINGS_BASE_URL": "http://e"}
    deps = build_vector_repair_outbox_production_dependencies(env, module_loader=loader)

    deps.vector_deleter({"vector_id": "v1", "uid": "u1", "memory_id": "m1"})

    assert len(store.deleted) == 1
    namespace, flt = store.deleted[0]
    assert namespace == "ns2"
    assert flt == {"$and": [{"uid": {"$eq": "u1"}}, {"memory_id": {"$eq": "m1"}}]}
