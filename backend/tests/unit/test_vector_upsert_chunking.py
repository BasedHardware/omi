"""A vector upsert larger than Pinecone's per-call limit must not silently lose the tail (BACKLOG L3).

`database/vector_db.py` knows the limit and says so — "Pinecone upsert limit is 100 vectors per call" —
and two of its three batch writers loop at 100. The third, `upsert_action_item_vectors_batch`, sends the
whole payload in one call, and its caller is bounded at **500** items
(`routers/action_items.py`: `items: List[...] = Field(..., max_length=500)`). Worse, the write is
deliberately best-effort: the exception is caught, 0 is returned and the caller carries on, because the
Firestore write already committed. So the vectors are LOST rather than partially written, and nothing
surfaces to the user.

The fix belongs in the adapter, not in a fourth hand-rolled loop. The vendor's request limit is the
vendor's business: hiding it is what the port is for (ADR-0033/0004), and putting it there fixes every
caller — the one that was broken, and the next one nobody has written yet. It also removes the reason for
the domain layer to know a Pinecone number at all.

Asymmetry worth stating: this only ever broke the CLOUD backend. Qdrant has no such cap, so on-prem the
same call always worked — the inverse of the usual direction, and the reason it went unnoticed here.
"""

from __future__ import annotations

from typing import Any, Dict, List

import pytest

from utils.vector.adapters.pinecone import PineconeVectorStore


class _FakeIndex:
    """Records each upsert call the way Pinecone would receive it."""

    def __init__(self) -> None:
        self.calls: List[Dict[str, Any]] = []

    def upsert(self, vectors: Any, namespace: str) -> None:
        self.calls.append({'count': len(vectors), 'namespace': namespace, 'ids': [v['id'] for v in vectors]})


def _records(count: int) -> List[Dict[str, Any]]:
    return [{'id': f'u-ai-{i}', 'values': [0.1, 0.2], 'metadata': {'uid': 'u'}} for i in range(count)]


@pytest.fixture
def index(monkeypatch) -> _FakeIndex:
    fake = _FakeIndex()
    monkeypatch.setattr('utils.vector.adapters.pinecone._get_index', lambda: fake)
    return fake


def test_a_batch_over_the_limit_is_split_and_all_of_it_is_written(index):
    """250 records: the tail must reach Pinecone, not disappear into a rejected request."""
    written = PineconeVectorStore().upsert('ns2', _records(250))

    assert [call['count'] for call in index.calls] == [100, 100, 50]
    assert written == 250, 'the return value is what the caller logs as indexed'


def test_the_worst_documented_case_is_covered(index):
    """The caller's own bound is 500 (`Field(..., max_length=500)`), which is exactly the payload that
    used to be sent as a single 500-vector request."""
    written = PineconeVectorStore().upsert('ns2', _records(500))

    assert [call['count'] for call in index.calls] == [100, 100, 100, 100, 100]
    assert written == 500


def test_every_record_is_written_exactly_once_and_in_order(index):
    """Splitting must not drop or duplicate: an off-by-one in the slice is the obvious way to
    reintroduce the same silent loss."""
    records = _records(213)

    PineconeVectorStore().upsert('ns2', records)

    seen = [record_id for call in index.calls for record_id in call['ids']]
    assert seen == [record['id'] for record in records]


def test_a_batch_at_or_under_the_limit_is_still_one_call(index):
    """No behaviour change for the common case — including exactly 100, where an off-by-one would add a
    pointless empty request."""
    assert PineconeVectorStore().upsert('ns2', _records(100)) == 100
    assert [call['count'] for call in index.calls] == [100]


def test_an_empty_batch_touches_nothing(index):
    assert PineconeVectorStore().upsert('ns2', []) == 0
    assert index.calls == []


def test_the_namespace_travels_with_every_chunk(index):
    """A chunk written to the wrong namespace is invisible to search, which looks exactly like loss."""
    PineconeVectorStore().upsert('ns2', _records(150))

    assert {call['namespace'] for call in index.calls} == {'ns2'}


def test_qdrant_needs_no_chunking_and_gets_none(monkeypatch):
    """Parity check in the honest direction: the cap is Pinecone's, so the Qdrant adapter must NOT grow a
    limit it does not have. One call, all 250 points."""
    from utils.vector.adapters import qdrant as qdrant_adapter

    calls: List[int] = []

    class _FakeClient:
        def upsert(self, collection_name: str, points: Any, **_kwargs: Any) -> None:
            calls.append(len(points))

        def get_collections(self) -> Any:  # pragma: no cover - only if the adapter probes first
            class _Result:
                collections: List[Any] = []

            return _Result()

    monkeypatch.setattr(qdrant_adapter, '_get_client', lambda: _FakeClient())
    monkeypatch.setattr(qdrant_adapter, '_ensure_collection', lambda *_a, **_k: None)

    written = qdrant_adapter.QdrantVectorStore().upsert('ns2', _records(250))

    assert written == 250
    assert calls == [250], 'no artificial cap on a backend that has none'
