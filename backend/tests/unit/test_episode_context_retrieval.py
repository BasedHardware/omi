"""Composer search stays canonical, budgeted, and separate from chat defaults."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from database import vector_db
from utils.memory import canonical_memory_adapter as canonical
from utils.memory.memory_service import CanonicalMemoryBackend, MemoryService
from utils.memory.product_memory_read_service import fetch_authoritative_product_memory_items_by_ids
from utils.other.list_budget import ListReadBudget, ListReadBudgetExhausted


def budget(documents=160):
    return ListReadBudget(deadline_monotonic=1000, max_documents=documents, clock=lambda: 990)


def test_composer_vector_only_does_not_query_history_or_typesense(monkeypatch):
    repo = MemoryService(db_client=Mock())
    bounded = budget()
    repo._canonical.search = Mock(return_value=[])
    repo.history.search = Mock(side_effect=AssertionError('redundant historical vector query'))
    assert repo.search('synthetic', 'garden', vector_only=True, budget=bounded) == []
    assert repo._canonical.search.call_args.kwargs['vector_only'] is True
    assert repo._canonical.search.call_args.kwargs['budget'] is bounded
    repo.history.search.assert_not_called()

    from utils.memory import atom_keyword_index as keyword

    monkeypatch.setattr(keyword, 'keyword_search_memory_ids', Mock(side_effect=AssertionError('Typesense')))
    query = Mock(return_value=SimpleNamespace(hits=[]))
    assert (
        canonical.search_canonical_memories(
            'synthetic', 'garden', db_client=Mock(), vector_query=query, vector_only=True, budget=bounded
        )
        == []
    )
    assert query.call_count == 1
    assert query.call_args.kwargs['timeout_seconds'] == 10


def test_chat_search_does_not_gain_composer_options(monkeypatch):
    from utils.memory import memory_service as module

    query = Mock(return_value=[])
    monkeypatch.setattr(module, 'search_canonical_memories', query)
    backend = CanonicalMemoryBackend(db_client=Mock())
    assert backend.search('synthetic', 'garden') == []
    assert 'vector_only' not in query.call_args.kwargs
    assert 'budget' not in query.call_args.kwargs


def test_expired_embedding_cannot_start_a_vector_query(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(vector_db, 'time', SimpleNamespace(monotonic=lambda: clock[0]))
    monkeypatch.setattr(vector_db, 'index', object())
    provider = Mock(side_effect=AssertionError('no vector query after deadline'))
    monkeypatch.setattr(vector_db, 'owner_index', provider)

    def embed(_query, **kwargs):
        assert kwargs == {'timeout': 8}
        clock[0] += 9
        return [0.1]

    monkeypatch.setattr(vector_db, 'embeddings', SimpleNamespace(embed_query=embed))
    with pytest.raises(TimeoutError):
        vector_db.query_memory_vector_candidates('synthetic', 'garden', timeout_seconds=8)
    provider.assert_not_called()


def test_hydration_rejects_over_budget_batch_before_reading():
    db = Mock()
    with pytest.raises(ListReadBudgetExhausted):
        fetch_authoritative_product_memory_items_by_ids('synthetic', ['one', 'two'], db_client=db, budget=budget(1))
    db.get_all.assert_not_called()


def test_hydration_uses_remaining_deadline_and_charges_documents():
    bounded = budget(1)
    db = Mock()
    db.get_all.return_value = [SimpleNamespace(id='one', exists=False)]
    assert fetch_authoritative_product_memory_items_by_ids('synthetic', ['one'], db_client=db, budget=bounded) == []
    assert db.get_all.call_args.kwargs['timeout'] == 10
    assert bounded.docs_scanned == 1


def test_owner_routing_cannot_start_vector_rpc_after_deadline(monkeypatch):
    from database import pinecone_partition_index as module

    index = Mock()
    owner = module.OwnerIndex(index, 'synthetic', index_name='synthetic-index')
    monkeypatch.setattr(owner, '_route', lambda _family: 'owner-namespace')
    monkeypatch.setattr(module, 'time', SimpleNamespace(monotonic=lambda: 109))
    with pytest.raises(TimeoutError):
        owner.query(namespace='ns2', filter={'uid': 'synthetic'}, deadline_monotonic=108)
    index.query.assert_not_called()


def test_strict_context_read_budget_caps_stream_before_fetching():
    from utils.other.list_budget import budgeted_stream_list, budgeted_get_all

    class Query:
        def __init__(self, limit=100):
            self._limit = limit

        def limit(self, limit):
            return Query(limit)

        def stream(self, **kwargs):
            return iter(range(self._limit))

    bounded = ListReadBudget(deadline_monotonic=1000, max_documents=1, clock=lambda: 990, strict_documents=True)
    assert budgeted_stream_list(Query(), bounded) == [0]
    db = Mock()
    with pytest.raises(ListReadBudgetExhausted):
        budgeted_get_all(db, [object()], bounded)
    db.get_all.assert_not_called()
