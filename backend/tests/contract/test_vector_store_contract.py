"""Dual-backend contract test for the neutral vector-store port (WP4, ADR-0033/0004).

The SAME assertions run against every adapter — the in-memory fake (always, hermetic) and the Qdrant
adapter (against a real Qdrant). Parity here is the proof that ``utils.vector`` abstracts the backend
rather than leaking one, especially for the neutral ``$``-DSL filter (bare-eq / $in / range / $and /
$or and the hard **$exists:false** legacy-ns2 barrier).

Pinecone has no offline emulator, so the FAKE encodes the reference semantics and Qdrant must match it;
the ``pinecone`` backend runs only when ``PINECONE_API_KEY`` + ``PINECONE_INDEX_NAME`` are set (skipped
otherwise). Live services (skipped when env absent, so the file is safe to collect anywhere):
  * ``QDRANT_URL`` — a Qdrant instance (image ``qdrant/qdrant``).
  * ``PINECONE_API_KEY`` / ``PINECONE_INDEX_NAME`` — a real Pinecone index (optional).
The fake needs nothing and always runs. Not hermetic (qdrant/pinecone need live services); not run by
``backend/test.sh``. Vectors are 8-dim here (``QDRANT_VECTOR_DIM=8``) for speed.
"""

from __future__ import annotations

import os
import uuid

import pytest


def _ns() -> str:
    return f"ct_{uuid.uuid4().hex[:12]}"


@pytest.fixture(params=["fake", "qdrant", "pinecone"])
def store_ns(request):
    """Yield ``(store, namespace)`` per configured backend; drop the Qdrant collection on teardown."""
    backend = request.param

    if backend == "fake":
        from tests.vector_store_fakes import FakeVectorStore

        yield FakeVectorStore(), _ns()
        return

    if backend == "qdrant":
        if not os.environ.get("QDRANT_URL"):
            pytest.skip("QDRANT_URL not set")
        os.environ.setdefault("QDRANT_VECTOR_DIM", "8")
        from utils.vector.adapters import qdrant as qmod

        qmod._client = None
        qmod.reset_ensured_cache_for_tests()
        namespace = _ns()
        try:
            yield qmod.QdrantVectorStore(), namespace
        finally:
            try:
                qmod._get_client().delete_collection(qmod._collection(namespace))
            except Exception:
                pass
        return

    if not os.environ.get("PINECONE_API_KEY") or not os.environ.get("PINECONE_INDEX_NAME"):
        pytest.skip("PINECONE_API_KEY / PINECONE_INDEX_NAME not set")
    from utils.vector.adapters import pinecone as pmod

    pmod._index = None
    yield pmod.PineconeVectorStore(), _ns()


def _rec(vid, values, **metadata):
    return {"id": vid, "values": values, "metadata": metadata}


# --- upsert / query ----------------------------------------------------------


def test_upsert_and_nearest_neighbor(store_ns):
    store, ns = store_ns
    store.upsert(ns, [_rec("a", [1, 0, 0, 0, 0, 0, 0, 0], uid="u1")])
    store.upsert(ns, [_rec("b", [0, 1, 0, 0, 0, 0, 0, 0], uid="u1")])
    hits = store.query(ns, [0.9, 0.1, 0, 0, 0, 0, 0, 0], top_k=1)
    assert [h["id"] for h in hits] == ["a"]


def test_query_bare_equality_filter(store_ns):
    store, ns = store_ns
    store.upsert(ns, [_rec("a", [1, 0, 0, 0, 0, 0, 0, 0], uid="u1")])
    store.upsert(ns, [_rec("b", [1, 0, 0, 0, 0, 0, 0, 0], uid="u2")])
    hits = store.query(ns, [1, 0, 0, 0, 0, 0, 0, 0], top_k=10, filter={"uid": "u1"})
    assert {h["id"] for h in hits} == {"a"}


def test_query_in_on_list_valued_metadata(store_ns):
    store, ns = store_ns
    store.upsert(ns, [_rec("a", [1, 0, 0, 0, 0, 0, 0, 0], uid="u1", topics=["x", "y"])])
    store.upsert(ns, [_rec("b", [1, 0, 0, 0, 0, 0, 0, 0], uid="u1", topics=["z"])])
    hits = store.query(ns, [1, 0, 0, 0, 0, 0, 0, 0], top_k=10, filter={"topics": {"$in": ["y", "w"]}})
    assert {h["id"] for h in hits} == {"a"}


def test_query_range_filter(store_ns):
    store, ns = store_ns
    for vid, ts in [("a", 100), ("b", 200), ("c", 300)]:
        store.upsert(ns, [_rec(vid, [1, 0, 0, 0, 0, 0, 0, 0], uid="u1", created_at=ts)])
    hits = store.query(ns, [1, 0, 0, 0, 0, 0, 0, 0], top_k=10, filter={"created_at": {"$gte": 150, "$lte": 250}})
    assert {h["id"] for h in hits} == {"b"}


# --- $exists (the legacy ns2 barrier) ----------------------------------------


def test_query_exists_false_selects_missing_field(store_ns):
    """The hard one: $exists:false must return only records that LACK the field (legacy barrier)."""
    store, ns = store_ns
    store.upsert(ns, [_rec("legacy", [1, 0, 0, 0, 0, 0, 0, 0], uid="u1")])  # no schema_version
    store.upsert(ns, [_rec("canon", [1, 0, 0, 0, 0, 0, 0, 0], uid="u1", schema_version=2)])
    hits = store.query(ns, [1, 0, 0, 0, 0, 0, 0, 0], top_k=10, filter={"schema_version": {"$exists": False}})
    assert {h["id"] for h in hits} == {"legacy"}


def test_query_exists_true_selects_present_field(store_ns):
    store, ns = store_ns
    store.upsert(ns, [_rec("legacy", [1, 0, 0, 0, 0, 0, 0, 0], uid="u1")])
    store.upsert(ns, [_rec("canon", [1, 0, 0, 0, 0, 0, 0, 0], uid="u1", schema_version=2)])
    hits = store.query(ns, [1, 0, 0, 0, 0, 0, 0, 0], top_k=10, filter={"schema_version": {"$exists": True}})
    assert {h["id"] for h in hits} == {"canon"}


def test_query_and_or_combination(store_ns):
    store, ns = store_ns
    store.upsert(ns, [_rec("a", [1, 0, 0, 0, 0, 0, 0, 0], uid="u1", status="open")])
    store.upsert(ns, [_rec("b", [1, 0, 0, 0, 0, 0, 0, 0], uid="u1", status="closed")])
    store.upsert(ns, [_rec("c", [1, 0, 0, 0, 0, 0, 0, 0], uid="u2", status="open")])
    flt = {"$and": [{"uid": "u1"}, {"$or": [{"status": "open"}, {"status": "archived"}]}]}
    hits = store.query(ns, [1, 0, 0, 0, 0, 0, 0, 0], top_k=10, filter=flt)
    assert {h["id"] for h in hits} == {"a"}


# --- mutations ---------------------------------------------------------------


def test_update_metadata(store_ns):
    store, ns = store_ns
    store.upsert(ns, [_rec("a", [1, 0, 0, 0, 0, 0, 0, 0], uid="u1", status="open")])
    store.update_metadata(ns, "a", {"status": "closed"})
    assert store.query(ns, [1, 0, 0, 0, 0, 0, 0, 0], top_k=10, filter={"status": "closed"})
    assert not store.query(ns, [1, 0, 0, 0, 0, 0, 0, 0], top_k=10, filter={"status": "open"})


def test_delete_by_ids(store_ns):
    store, ns = store_ns
    store.upsert(ns, [_rec("a", [1, 0, 0, 0, 0, 0, 0, 0], uid="u1")])
    store.upsert(ns, [_rec("b", [1, 0, 0, 0, 0, 0, 0, 0], uid="u1")])
    store.delete_by_ids(ns, ["a"])
    assert {h["id"] for h in store.query(ns, [1, 0, 0, 0, 0, 0, 0, 0], top_k=10)} == {"b"}


def test_delete_by_filter(store_ns):
    store, ns = store_ns
    store.upsert(ns, [_rec("a", [1, 0, 0, 0, 0, 0, 0, 0], uid="u1")])
    store.upsert(ns, [_rec("b", [1, 0, 0, 0, 0, 0, 0, 0], uid="u2")])
    store.delete_by_filter(ns, {"uid": "u1"})
    assert {h["id"] for h in store.query(ns, [1, 0, 0, 0, 0, 0, 0, 0], top_k=10)} == {"b"}


def test_list_ids_by_prefix(store_ns):
    store, ns = store_ns
    store.upsert(ns, [_rec("u1-c1-0", [1, 0, 0, 0, 0, 0, 0, 0], uid="u1")])
    store.upsert(ns, [_rec("u1-c1-1", [1, 0, 0, 0, 0, 0, 0, 0], uid="u1")])
    store.upsert(ns, [_rec("u1-c2-0", [1, 0, 0, 0, 0, 0, 0, 0], uid="u1")])
    got = set()
    for page in store.list_ids(ns, prefix="u1-c1-"):
        got.update(page)
    assert got == {"u1-c1-0", "u1-c1-1"}


def test_namespace_isolation(store_ns):
    store, ns = store_ns
    other = ns + "_other"
    store.upsert(ns, [_rec("a", [1, 0, 0, 0, 0, 0, 0, 0], uid="u1")])
    hits = store.query(other, [1, 0, 0, 0, 0, 0, 0, 0], top_k=10)
    assert hits == []
