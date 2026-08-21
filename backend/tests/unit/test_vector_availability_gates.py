"""Three defects of one shape: "this dependency is not configured" told as "this operation failed".

L10 — `is_vector_available()` treated any backend that is not `qdrant` as pinecone, so
      VECTOR_STORE_BACKEND=weaviate with PINECONE_* set made the gate say "available" while
      `get_vector_store()` raises ValueError. The gate and the factory disagreed, so 24 callers that
      degrade politely on `not is_vector_available()` would instead crash mid-request.
L11 — `upsert_vector` and `upsert_vectors` lacked the gate their immediate neighbours have
      (`upsert_vector2`, `update_vector_metadata`), so with no vector store they raise from the adapter
      instead of skipping.
L38 — `delete_canonical_memory_vectors` logged "skipping" and returned **False** when no store is
      configured. The memory outbox reads False as "delivery failed", so the event burned its five
      attempts and DEAD-LETTERED — five retries and a silent give-up for a state that already held:
      with no vector store there are no vectors, so the desired absence is confirmed.
"""

from __future__ import annotations

import pytest

from database import vector_db


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in ('VECTOR_STORE_BACKEND', 'QDRANT_URL', 'PINECONE_API_KEY', 'PINECONE_INDEX_NAME'):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def store_calls(monkeypatch):
    """Record every call that reaches the vector store, so "skipped" is provable."""
    calls: list[str] = []

    class _Spy:
        def upsert(self, namespace, records):
            calls.append(f'upsert:{namespace}:{len(records)}')
            return {'upserted': len(records)}

        def delete_by_filter(self, namespace, filter_obj):
            calls.append(f'delete_by_filter:{namespace}')

    monkeypatch.setattr(vector_db, '_vector_store', lambda: _Spy())
    return calls


# --- L10: the gate must agree with the factory ---------------------------------------------------


def test_an_unknown_backend_is_not_available_however_it_is_configured(monkeypatch):
    monkeypatch.setenv('VECTOR_STORE_BACKEND', 'weaviate')
    monkeypatch.setenv('PINECONE_API_KEY', 'k')
    monkeypatch.setenv('PINECONE_INDEX_NAME', 'i')
    assert vector_db.is_vector_available() is False


def test_the_factory_would_have_raised_for_that_backend():
    """Why False is the right answer: the two must not disagree."""
    import utils.vector.factory as factory

    factory._instance = None
    try:
        with pytest.raises(ValueError, match='unknown VECTOR_STORE_BACKEND'):
            factory.get_vector_store(env={'VECTOR_STORE_BACKEND': 'weaviate'})
    finally:
        factory._instance = None


@pytest.mark.parametrize(
    'env,expected',
    [
        ({}, False),
        ({'PINECONE_API_KEY': 'k'}, False),
        ({'PINECONE_API_KEY': 'k', 'PINECONE_INDEX_NAME': 'i'}, True),
        ({'VECTOR_STORE_BACKEND': 'qdrant'}, False),
        ({'VECTOR_STORE_BACKEND': 'qdrant', 'QDRANT_URL': 'http://qdrant:6333'}, True),
        ({'VECTOR_STORE_BACKEND': 'PINECONE', 'PINECONE_API_KEY': 'k', 'PINECONE_INDEX_NAME': 'i'}, True),
    ],
)
def test_the_supported_backends_still_answer_as_before(monkeypatch, env, expected):
    """Legacy principals: the two backends we ship must keep their existing answers."""
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    assert vector_db.is_vector_available() is expected


# --- L11: the two ungated writers ---------------------------------------------------------------


def test_upsert_vector_skips_instead_of_raising(store_calls):
    vector_db.upsert_vector('u1', 'c1', [0.1, 0.2])
    assert store_calls == [], 'the write reached the store with no store configured'


def test_upsert_vectors_skips_instead_of_raising(store_calls):
    vector_db.upsert_vectors('u1', [[0.1], [0.2]], ['c1', 'c2'])
    assert store_calls == []


def test_both_still_write_when_a_store_is_configured(monkeypatch, store_calls):
    """Legacy principal: the gate must not disable the feature for a configured deployment."""
    monkeypatch.setenv('VECTOR_STORE_BACKEND', 'qdrant')
    monkeypatch.setenv('QDRANT_URL', 'http://qdrant:6333')
    vector_db.upsert_vector('u1', 'c1', [0.1])
    vector_db.upsert_vectors('u1', [[0.1], [0.2]], ['c1', 'c2'])
    assert store_calls == ['upsert:ns1:1', 'upsert:ns1:2']


# --- L38: absence with no store is confirmed, not failed ----------------------------------------


def test_deleting_vectors_with_no_store_is_success_not_failure(store_calls):
    """The memory outbox reads False as "delivery failed" and dead-letters after five attempts. With no
    vector store there are no vectors, so the desired absence holds — the same reasoning
    delete_atom_keyword_doc already uses for a missing document."""
    assert vector_db.delete_canonical_memory_vectors('u1', 'm1') is True
    assert store_calls == [], 'it tried to talk to a store that is not configured'


def test_deleting_vectors_with_no_store_records_the_capability_loss(monkeypatch, store_calls):
    """Success must not be silent: an operator has to be able to see that vector deletes are a no-op."""
    events: list[dict] = []
    monkeypatch.setattr(vector_db, 'record_fallback', lambda **kw: events.append(kw))
    vector_db.delete_canonical_memory_vectors('u1', 'm1')
    assert len(events) == 1
    assert events[0]['reason'] == 'config_incomplete'
    assert events[0]['outcome'] == 'degraded'
    assert events[0]['component'] == 'vector_store'


def test_deleting_vectors_still_goes_to_the_store_when_configured(monkeypatch, store_calls):
    monkeypatch.setenv('VECTOR_STORE_BACKEND', 'qdrant')
    monkeypatch.setenv('QDRANT_URL', 'http://qdrant:6333')
    assert vector_db.delete_canonical_memory_vectors('u1', 'm1') is True
    assert store_calls == ['delete_by_filter:ns2']
