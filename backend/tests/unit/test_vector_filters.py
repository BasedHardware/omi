import importlib.util
import os
import sys
import types

from models.memory_search_gateway import SearchMode


class _FakeEmbeddings:
    def embed_query(self, text):
        assert text == "query text"
        return [0.1, 0.2, 0.3]


class _FakeIndex:
    def __init__(self):
        self.queries = []

    def query(self, **kwargs):
        self.queries.append(kwargs)
        return {
            "matches": [
                {
                    "score": 0.91,
                    "metadata": {
                        "memory_schema_version": 1,
                        "uid": "uid-1",
                        "memory_id": "mem-short",
                        "memory_layer": "short_term",
                        "status": "active",
                        "source_state": "active",
                        "restricted_sensitivity": False,
                        "projection_commit_id": "projection-1",
                        "vector_updated_at": "2026-06-19T12:05:00+00:00",
                        "account_generation": 4,
                        "item_revision": 2,
                    },
                },
                {
                    "score": 0.4,
                    "metadata": {
                        "memory_schema_version": 1,
                        "uid": "uid-1",
                        "memory_id": "bad-missing-projection",
                    },
                },
            ]
        }


def _load_vector_db_with_stubs():
    pinecone_module = types.ModuleType("pinecone")
    setattr(pinecone_module, "Pinecone", lambda api_key: None)
    sys.modules["pinecone"] = pinecone_module
    clients_module = types.ModuleType("utils.llm.clients")
    setattr(clients_module, "embeddings", _FakeEmbeddings())
    sys.modules["utils.llm.clients"] = clients_module
    projection_repair_module = types.ModuleType("database.projection_repair")
    setattr(projection_repair_module, "projection_metadata_for_fact", lambda memory, source_commit_id=None: {})
    sys.modules["database.projection_repair"] = projection_repair_module
    vector_db_path = os.path.join(os.path.dirname(__file__), "..", "..", "database", "vector_db.py")
    spec = importlib.util.spec_from_file_location("vector_filter_vector_db", vector_db_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(spec.name, None)
        raise
    return module


def test_query_memory_vector_candidates_uses_ns2_strict_default_filter_and_parses_hits(monkeypatch):
    vector_db = _load_vector_db_with_stubs()
    fake_index = _FakeIndex()
    monkeypatch.setattr(vector_db, "index", fake_index)
    monkeypatch.setattr(vector_db, "embeddings", _FakeEmbeddings())

    parsed = vector_db.query_memory_vector_candidates("uid-1", "query text", mode=SearchMode.default, limit=20)

    assert [hit.memory_id for hit in parsed.hits] == ["mem-short"]
    assert parsed.rejected_count == 1
    assert fake_index.queries[0]["namespace"] == "ns2"
    assert fake_index.queries[0]["top_k"] == 20
    assert fake_index.queries[0]["include_metadata"] is True
    assert {"memory_layer": {"$in": ["short_term", "long_term"]}} in fake_index.queries[0]["filter"]["$and"]
    assert {"restricted_sensitivity": {"$eq": False}} in fake_index.queries[0]["filter"]["$and"]


def test_query_memory_vector_candidates_requires_explicit_archive_mode_for_archive_filter(monkeypatch):
    vector_db = _load_vector_db_with_stubs()
    fake_index = _FakeIndex()
    monkeypatch.setattr(vector_db, "index", fake_index)
    monkeypatch.setattr(vector_db, "embeddings", _FakeEmbeddings())

    vector_db.query_memory_vector_candidates("uid-1", "query text", mode=SearchMode.archive_explicit)

    assert {"memory_layer": {"$eq": "archive"}} in fake_index.queries[0]["filter"]["$and"]
