"""Provider-boundary contracts required by the real owner-routing adapter."""

import pytest

from conftest import _clear_hermetic_vector_state
from fakes.vector_search import DeterministicEmbeddings, FakeVectorIndex


def record(vector_id, uid, values=None):
    return {'id': vector_id, 'values': values or [1.0] * 16, 'metadata': {'uid': uid, 'kind': 'memory'}}


@pytest.mark.parametrize('logical', ['$and', '$or'])
def test_logical_filter_does_not_skip_sibling_owner_constraint(logical):
    index = FakeVectorIndex(DeterministicEmbeddings())
    index.upsert([record('mine', 'owner'), record('foreign', 'other')], namespace='ns2')
    response = index.query(
        vector=[1.0] * 16,
        top_k=10,
        namespace='ns2',
        filter={logical: [{'kind': 'memory'}], 'uid': {'$eq': 'owner'}},
    )
    assert [match['id'] for match in response['matches']] == ['mine']


def test_numeric_existence_query_returns_records_without_source_text():
    index = FakeVectorIndex(DeterministicEmbeddings())
    index.upsert([record('negative', 'owner', [-1.0] * 16)], namespace='ns2')
    response = index.query(vector=[1.0] * 16, top_k=1, namespace='ns2', filter={'uid': 'owner'})
    assert response['matches'] == [{'id': 'negative', 'score': -16.0}]
    assert not index.query(vector=[1.0] * 16, top_k=1, namespace='other', filter={'uid': 'owner'})['matches']


def test_noop_delete_receipt_needs_actual_barrier_before_indexed_watermark_advances():
    from database.pinecone_provider_errors import barrier_record

    index = FakeVectorIndex(DeterministicEmbeddings())
    index.upsert([record('mine', 'owner')], namespace='ns2')
    _, _, deletion = index.delete(ids=['absent'], namespace='ns2', _return_http_data_only=False)
    query = dict(namespace='ns2', vector=[1.0] * 16, top_k=10, filter={'uid': 'owner'})
    _, _, stale = index._query(**query, _return_http_data_only=False)
    assert int(stale['x-pinecone-max-indexed-lsn']) < int(deletion['x-pinecone-request-lsn'])
    _, _, barrier = index.upsert(vectors=[barrier_record(16)], namespace='ns2', _return_http_data_only=False)
    response, _, fresh = index._query(**query, _return_http_data_only=False)
    assert int(fresh['x-pinecone-max-indexed-lsn']) == int(barrier['x-pinecone-request-lsn'])
    assert int(fresh['x-pinecone-max-indexed-lsn']) > int(deletion['x-pinecone-request-lsn'])
    assert [match['id'] for match in response['matches']] == ['mine']


def test_isolation_clears_routes_orphan_operations_and_both_provider_watermarks(fake_firestore, monkeypatch):
    import database.vector_db as vector_db

    refs = []
    for owner in ('owner', 'other'):
        route = fake_firestore.collection('pinecone_partition_routes').document(owner)
        operation = route.collection('operations').document('pending')
        route.set({'uid': owner, 'mode': 'copying', 'pending_count': 1, 'uncertain_count': 1})
        operation.set({'uid': owner, 'token': 'pending'})
        refs.extend([route, operation])
    refs[2].delete()  # The operation survives its missing route parent.
    assert refs[3].get().exists
    unrelated = fake_firestore.collection('unrelated').document('keep')
    unrelated.set({'keep': True})
    embeddings = DeterministicEmbeddings()
    index = FakeVectorIndex(embeddings)
    index.upsert([record('mine', 'owner', embeddings.embed_query('private text'))], namespace='ns2')
    index.upsert([record('retained', 'owner')], namespace='partition')
    index.delete(ids=['absent'], namespace='ns2')
    monkeypatch.setattr(vector_db, 'index', index)
    monkeypatch.setattr(vector_db, 'embeddings', embeddings)
    monkeypatch.setattr(vector_db, '_pinecone_index_name', 'hermetic-e2e-index')

    for _ in range(2):
        _clear_hermetic_vector_state()
        assert all(not ref.get().exists for ref in refs)
        assert not any(path[0] == 'pinecone_partition_routes' for path in fake_firestore._written_docs)
        assert vector_db.index is not index
        assert not vector_db.index._vectors
        assert not vector_db.index._lsns
        assert not vector_db.index._indexed_lsns
        assert vector_db.embeddings.text_for_id('mine') is None
        assert unrelated.get().to_dict() == {'keep': True}
    unrelated.delete()
