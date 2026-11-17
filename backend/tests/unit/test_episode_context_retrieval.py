"""Owner-summary searches expand account context; chat defaults stay unchanged."""

from types import SimpleNamespace
import time
from unittest.mock import Mock, create_autospec

import pytest
from google.cloud.firestore_v1 import Client, CollectionReference, DocumentReference

from database import vector_db
from utils.memory import canonical_memory_adapter as canonical
from utils.memory.memory_service import CanonicalMemoryBackend, MemoryService
from utils.memory.product_memory_read_service import fetch_authoritative_product_memory_items_by_ids
from utils.other.list_budget import ListReadBudget, ListReadBudgetExhausted


def budget(documents=160):
    return ListReadBudget(deadline_monotonic=1000, max_documents=documents, clock=lambda: 990)


def test_default_vector_only_does_not_query_history_or_typesense(monkeypatch):
    repo = MemoryService(db_client=Mock())
    bounded = budget()
    repo._canonical.search = create_autospec(repo._canonical.search, return_value=[], spec_set=True)
    repo.history.search = create_autospec(
        repo.history.search, side_effect=AssertionError('redundant historical vector query'), spec_set=True
    )
    assert repo.search('synthetic', 'garden', vector_only=True, budget=bounded) == []
    assert repo._canonical.search.call_args.kwargs['vector_only'] is True
    assert repo._canonical.search.call_args.kwargs['budget'] is bounded
    repo.history.search.assert_not_called()

    from utils.memory import atom_keyword_index as keyword

    monkeypatch.setattr(keyword, 'keyword_search_memory_ids', Mock(side_effect=AssertionError('Typesense')))
    query = create_autospec(
        vector_db.query_memory_vector_candidates, return_value=SimpleNamespace(hits=[]), spec_set=True
    )
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


def test_optional_composer_search_does_not_repeat_embedding_vector_operation():
    from fastapi import HTTPException
    from google.api_core.exceptions import ServiceUnavailable

    repo = MemoryService(db_client=Mock())
    repo._canonical.search = create_autospec(
        repo._canonical.search, side_effect=ServiceUnavailable('synthetic provider failure'), spec_set=True
    )
    with pytest.raises(HTTPException):
        repo.search('synthetic', 'garden', vector_only=True, budget=budget(), single_attempt=True)
    assert repo._canonical.search.call_count == 1


def test_expired_embedding_cannot_start_a_vector_query(monkeypatch):
    from utils.llm.clients import _OpenAIEmbeddingsProxy

    clock = [100.0]
    monkeypatch.setattr(vector_db, 'time', SimpleNamespace(monotonic=lambda: clock[0]))
    monkeypatch.setattr(vector_db, 'index', object())
    provider = Mock(side_effect=AssertionError('no vector query after deadline'))
    monkeypatch.setattr(vector_db, 'owner_index', provider)

    def embed(_query):
        clock[0] += 9
        return [0.1]

    embeddings = create_autospec(_OpenAIEmbeddingsProxy, instance=True, spec_set=True)
    embeddings.embed_query.side_effect = embed
    monkeypatch.setattr(vector_db, 'embeddings', embeddings)
    with pytest.raises(TimeoutError):
        vector_db.query_memory_vector_candidates('synthetic', 'garden', timeout_seconds=8)
    provider.assert_not_called()
    embeddings.embed_query.assert_called_once_with('garden')


def test_budgeted_retrieval_matches_real_embedding_and_owner_index_signatures(monkeypatch):
    from utils.llm.clients import _OpenAIEmbeddingsProxy
    from database.pinecone_partition_index import OwnerIndex

    embeddings = create_autospec(_OpenAIEmbeddingsProxy, instance=True, spec_set=True)
    embeddings.embed_query.return_value = [0.1]
    owner = create_autospec(OwnerIndex, instance=True, spec_set=True)
    owner.query.return_value = {'matches': []}
    monkeypatch.setattr(vector_db, 'index', object())
    monkeypatch.setattr(vector_db, 'embeddings', embeddings)
    monkeypatch.setattr(
        vector_db, 'owner_index', create_autospec(vector_db.owner_index, return_value=owner, spec_set=True)
    )
    assert vector_db.query_memory_vector_candidates('synthetic', 'garden', timeout_seconds=8).hits == []
    embeddings.embed_query.assert_called_once_with('garden')
    assert owner.query.call_count == 1
    assert 0 < owner.query.call_args.kwargs['_request_timeout'] <= 8


def test_hydration_rejects_over_budget_batch_before_reading():
    db = create_autospec(Client, instance=True, spec_set=True)
    with pytest.raises(ListReadBudgetExhausted):
        fetch_authoritative_product_memory_items_by_ids('synthetic', ['one', 'two'], db_client=db, budget=budget(1))
    db.get_all.assert_not_called()


def test_hydration_uses_remaining_deadline_and_charges_documents():
    bounded = budget(1)
    db = create_autospec(Client, instance=True, spec_set=True)
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


def test_owner_people_projection_is_read_only_and_bounded(monkeypatch):
    from database import _client
    from utils.episodes import composer_context_io

    client = create_autospec(Client, instance=True, spec_set=True)
    users = create_autospec(CollectionReference, instance=True, spec_set=True)
    owner = create_autospec(DocumentReference, instance=True, spec_set=True)
    people = create_autospec(CollectionReference, instance=True, spec_set=True)
    client.collection.return_value = users
    users.document.return_value = owner
    owner.collection.return_value = people
    client.get_all.return_value = [SimpleNamespace(exists=True, to_dict=lambda: {'name': 'Synthetic person'})] * 20
    monkeypatch.setattr(_client, 'db', client)
    bounded = budget()
    assert len(composer_context_io.people('synthetic-owner', [f'person-{n}' for n in range(40)], bounded)) == 20
    client.collection.assert_called_once_with('users')
    client.collection.return_value.document.assert_called_once_with('synthetic-owner')
    client.collection.return_value.document.return_value.collection.assert_called_once_with('people')
    args, kwargs = client.get_all.call_args
    assert len(args[0]) == 20 and bounded.docs_scanned == 20
    assert kwargs == {
        'field_paths': ['name', 'relationship', 'description', 'is_dismissed'],
        'timeout': 10,
        'retry': None,
    }
    assert all(
        call[0].split('.')[-1] not in {'set', 'update', 'create', 'delete', 'batch', 'transaction'}
        for call in client.mock_calls
    )


def test_profile_projection_matches_real_document_client_signature(monkeypatch):
    from database import _client
    from utils.episodes import composer_context_io

    client = create_autospec(Client, instance=True, spec_set=True)
    users = create_autospec(CollectionReference, instance=True, spec_set=True)
    owner = create_autospec(DocumentReference, instance=True, spec_set=True)
    client.collection.return_value = users
    users.document.return_value = owner
    owner.get.return_value = SimpleNamespace(to_dict=lambda: {'ai_user_profile': {'profile_text': 'Gardener.'}})
    monkeypatch.setattr(_client, 'db', client)
    assert composer_context_io.profile('synthetic', budget()) == {'profile_text': 'Gardener.'}
    owner.get.assert_called_once_with(field_paths=['ai_user_profile'], timeout=10, retry=None)


def test_owner_summary_search_includes_historical_only_after_canonical_success():
    repo = MemoryService(db_client=Mock())
    bounded = budget(640)
    repo._canonical.search = create_autospec(repo._canonical.search, return_value=[], spec_set=True)
    repo.history.search = create_autospec(repo.history.search, return_value=[], spec_set=True)
    assert (
        repo.search('synthetic', 'garden', vector_only=True, owner_summary=True, budget=bounded, single_attempt=True)
        == []
    )
    assert repo._canonical.search.call_args.kwargs['owner_summary'] is True
    assert repo.history.search.call_args.kwargs['budget'] is bounded
    repo._canonical.search.side_effect = RuntimeError('canonical unavailable')
    repo.history.search.reset_mock()
    from fastapi import HTTPException

    with pytest.raises(HTTPException):
        repo.search('synthetic', 'garden', vector_only=True, owner_summary=True, budget=bounded, single_attempt=True)
    repo.history.search.assert_not_called()


@pytest.mark.parametrize('legacy', [False, True])
def test_owner_summary_vector_calls_match_real_proxy_and_scope_signatures(monkeypatch, legacy):
    from utils.llm.clients import _OpenAIEmbeddingsProxy
    from database.pinecone_partition_index import OwnerIndex

    embeddings = create_autospec(_OpenAIEmbeddingsProxy, instance=True, spec_set=True)
    once = create_autospec(vector_db.embed_query_once, return_value=[0.1], spec_set=True)
    monkeypatch.setattr(vector_db, 'embed_query_once', once)
    owner = create_autospec(OwnerIndex, instance=True, spec_set=True)
    owner.query.return_value = {'matches': []}
    monkeypatch.setattr(vector_db, 'index', object())
    monkeypatch.setattr(vector_db, 'embeddings', embeddings)
    monkeypatch.setattr(
        vector_db, 'owner_index', create_autospec(vector_db.owner_index, return_value=owner, spec_set=True)
    )
    if legacy:
        assert vector_db.find_similar_memories('synthetic', 'garden', timeout_seconds=8, owner_summary=True) == []
    else:
        assert not vector_db.query_memory_vector_candidates(
            'synthetic', 'garden', timeout_seconds=8, owner_summary=True
        ).hits
    embeddings.embed_query.assert_not_called()
    once.assert_called_once_with('garden', deadline_monotonic=pytest.approx(time.monotonic() + 8, abs=1))
    options = owner.query.call_args.kwargs
    assert {'uid': {'$eq': 'synthetic'}} in options['filter']['$and']
    assert 0 < options['_request_timeout'] <= 8
    if not legacy:
        assert all(
            'restricted_sensitivity' not in clause and 'memory_layer' not in clause
            for clause in options['filter']['$and']
        )


def test_owner_summary_hydration_includes_archive_and_attribution_but_not_deleted_or_other_accounts(monkeypatch):
    from datetime import datetime, timezone
    from models.product_memory import MemoryItem, MemoryItemStatus, MemoryLayer
    from models.memory_evidence import SourceState
    from models.product_memory import MemoryAccessPolicy

    rows = [
        MemoryItem.model_construct(
            uid=uid,
            memory_id=label,
            content='Garden ' + label,
            status=status,
            source_state=SourceState.active,
            tier=MemoryLayer.archive,
            promotion=promotion,
            valid_to=None,
        )
        for uid, label, status, promotion in [
            ('synthetic', 'archive', MemoryItemStatus.active, {}),
            (
                'synthetic',
                'third-party',
                MemoryItemStatus.active,
                {'source_attribution': {'subject_attribution': 'third_party'}},
            ),
            ('synthetic', 'locked', MemoryItemStatus.active, {'is_locked': True}),
            ('synthetic', 'rejected', MemoryItemStatus.active, {'user_review': False}),
            ('synthetic', 'deleted', MemoryItemStatus.tombstoned, {}),
            ('other', 'cross-account', MemoryItemStatus.active, {}),
        ]
    ]
    monkeypatch.setattr(
        canonical,
        'fetch_authoritative_product_memory_items_by_ids',
        create_autospec(fetch_authoritative_product_memory_items_by_ids, return_value=rows, spec_set=True),
    )
    hydration = canonical._hydrate_bounded_ledger_search_items(
        'synthetic',
        [row.memory_id for row in rows],
        db_client=Mock(),
        policy=MemoryAccessPolicy.for_omi_chat(),
        now=datetime.now(timezone.utc),
        device_scope='all',
        client_device_id=None,
        owner_summary=True,
        budget=budget(640),
    )
    assert set(hydration.survivor_items_by_id) == {'archive', 'third-party'}


def test_owner_summary_projection_preserves_attribution_without_changing_chat_defaults():
    raw = {
        'memory_id': 'same',
        'content': 'Garden advice',
        'category': 'system',
        'subject_attribution': 'third_party',
        'kind': 'document',
        'subject_scope': 'third_party',
    }
    shared = canonical.search_result_to_memorydb('synthetic', raw)
    summary = canonical.search_result_to_memorydb('synthetic', raw, owner_summary=True)
    assert shared.category.value == 'interesting' and shared.subject_attribution.value == 'unknown'
    assert summary.category.value == 'system' and summary.subject_attribution.value == 'third_party'
    assert summary.kind.value == 'document' and summary.subject_scope.value == 'third_party'
