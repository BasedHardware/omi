"""An action item that never reaches the vector store must be counted (BACKLOG L20).

Three paths in `database/vector_db.py` swallow a vector failure and carry on. The fail-open is right —
the task is already saved, and turning a successful create into a 500 would make clients retry a write
that landed — but each was invisible, and the consequences are not equal:

    upsert_action_item_vector        the task is saved and permanently absent from semantic search.
    upsert_action_item_vectors_batch Nothing re-indexes it later.
    find_similar_action_items        the worst of the three, because its fail-open value is ALSO the
                                     most common honest answer. It feeds the extraction prompt with the
                                     user's open tasks so the LLM can suppress duplicates; `[]` reads as
                                     "you have nothing relevant", so a failed search produces DUPLICATE
                                     TASKS rather than an error.

That last one is the semantic half of the invariant the unique index guards structurally (ADR-0085):
the index stops two rows sharing an idempotency key, and this stops two tasks that mean the same thing.
When it fails silently, the product loses the second half and nobody is told.

Behaviour is unchanged on purpose. Every test asserts BOTH the value the caller still receives and the
event an operator now receives.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def events(monkeypatch):
    recorded: list[dict] = []
    import database.vector_db as vector_db

    monkeypatch.setattr(vector_db, 'record_fallback', lambda **kw: recorded.append(kw))
    monkeypatch.setattr(vector_db, 'is_vector_available', lambda: True)
    return recorded


def _break_embeddings(monkeypatch):
    import database.vector_db as vector_db

    class _Down:
        def embed_query(self, _text):
            raise RuntimeError('embeddings endpoint unreachable')

    monkeypatch.setattr(vector_db, 'embeddings', _Down())


# --- indexing ---------------------------------------------------------------------------------------


def test_a_task_that_could_not_be_indexed_is_recorded(events, monkeypatch):
    import database.vector_db as vector_db

    _break_embeddings(monkeypatch)

    assert vector_db.upsert_action_item_vector('u1', 'a1', 'buy milk') is None, 'the fail-open is unchanged'
    assert len(events) == 1
    assert events[0]['component'] == 'vector_store'
    assert events[0]['from_mode'] == 'action_item_index'
    assert events[0]['to_mode'] == 'unindexed'
    assert events[0]['outcome'] == 'degraded'


def test_a_failed_batch_records_once_not_once_per_item(events, monkeypatch):
    """The counter answers "is indexing broken". Per-item would let one bad batch drown the signal."""
    import database.vector_db as vector_db

    _break_embeddings(monkeypatch)
    items = [{'id': f'a{i}', 'description': f'task {i}'} for i in range(25)]

    assert vector_db.upsert_action_item_vectors_batch('u1', items) == 0
    assert len(events) == 1


def test_a_successful_index_records_nothing(events, monkeypatch):
    import database.vector_db as vector_db

    class _Fine:
        def embed_query(self, _text):
            return [0.1, 0.2, 0.3]

    class _Store:
        def upsert(self, _namespace, records):
            return len(records)

    monkeypatch.setattr(vector_db, 'embeddings', _Fine())
    monkeypatch.setattr(vector_db, '_vector_store', lambda: _Store())

    assert vector_db.upsert_action_item_vector('u1', 'a1', 'buy milk') == [0.1, 0.2, 0.3]
    assert events == [], 'a working index must not look like a broken one'


def test_an_empty_batch_is_not_a_failure(events, monkeypatch):
    """Nothing to index is not a degradation, and counting it would drown the signal."""
    import database.vector_db as vector_db

    assert vector_db.upsert_action_item_vectors_batch('u1', []) == 0
    assert events == []


# --- similarity search ------------------------------------------------------------------------------


def test_a_failed_similarity_search_is_recorded(events, monkeypatch):
    """The one whose fail-open value is indistinguishable from its honest answer."""
    import database.vector_db as vector_db

    _break_embeddings(monkeypatch)

    assert vector_db.find_similar_action_items('u1', 'buy milk') == [], 'the fail-open is unchanged'
    assert len(events) == 1
    assert events[0]['from_mode'] == 'similarity_search'
    assert events[0]['to_mode'] == 'no_candidates'


def test_a_genuinely_empty_result_is_not_recorded(events, monkeypatch):
    """The whole difficulty of this site: "no similar tasks" is the common, correct answer for most
    users. Recording it would make the counter useless for the case it exists to surface."""
    import database.vector_db as vector_db

    class _Fine:
        def embed_query(self, _text):
            return [0.1]

    class _Empty:
        def query(self, *_a, **_k):
            return []

    monkeypatch.setattr(vector_db, 'embeddings', _Fine())
    monkeypatch.setattr(vector_db, '_vector_store', lambda: _Empty())

    assert vector_db.find_similar_action_items('u1', 'buy milk') == []
    assert events == [], 'an honest empty result must not be reported as a degradation'


def test_matches_below_the_threshold_are_not_a_failure(events, monkeypatch):
    """Also empty, also honest: the store answered, nothing was similar enough."""
    import database.vector_db as vector_db

    class _Fine:
        def embed_query(self, _text):
            return [0.1]

    class _Weak:
        def query(self, *_a, **_k):
            return [{'score': 0.1, 'metadata': {'action_item_id': 'a1'}}]

    monkeypatch.setattr(vector_db, 'embeddings', _Fine())
    monkeypatch.setattr(vector_db, '_vector_store', lambda: _Weak())

    assert vector_db.find_similar_action_items('u1', 'buy milk', threshold=0.6) == []
    assert events == []


# --- the label vocabulary ----------------------------------------------------------------------


def test_the_three_sites_share_one_helper_so_their_labels_cannot_drift():
    """STATIC CHECK, labelled. Three call sites recording the same family by hand is how a label typo
    buckets one of them to 'other' — the exact defect ADR-0071 found in the push selector."""
    import inspect

    import database.vector_db as vector_db

    for name in ('upsert_action_item_vector', 'upsert_action_item_vectors_batch', 'find_similar_action_items'):
        source = inspect.getsource(getattr(vector_db, name))
        assert '_record_action_item_vector_fallback(' in source, f'{name} does not record its fail-open'
        assert 'record_fallback(' not in source, f'{name} records by hand instead of through the helper'
