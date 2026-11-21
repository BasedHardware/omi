"""Pipeline lab, lane chain: the lab index behind the real ``database.vector_db`` helpers.

Only the Firestore-backed owner routing and deletion fence are bypassed (they need an
emulator); the product's embedding inputs, ids, metadata, namespaces and thresholds run.
"""

from contextlib import ExitStack, nullcontext

import pytest

from testing.pipeline_lab.vector import install_vector_index
from testing.pipeline_lab.vector.embed import FakeEmbedder, install_embeddings
from testing.pipeline_lab.vector.index import NumericVectorIndex
from testing.pipeline_lab.vector.seed import apply_with_product, plan_vectors

UID = 'local-dev-user'


@pytest.fixture
def lab_vectors(monkeypatch):
    from database import vector_db

    monkeypatch.setattr(vector_db, 'owner_index', lambda index, uid, index_name=None, firestore_client=None: index)
    monkeypatch.setattr(vector_db, 'external_write_fence', lambda *a, **kw: nullcontext())
    embedder = FakeEmbedder(dimension=64)
    index = NumericVectorIndex(64)
    with ExitStack() as stack:
        install_vector_index(stack, index)
        install_embeddings(stack, embedder)
        yield vector_db, index, embedder


def test_without_a_lab_index_task_dedup_is_silently_empty():
    from database import vector_db

    assert vector_db.index is None
    assert vector_db.find_similar_action_items(UID, 'Order heirloom tomato seeds') == []


def test_seeded_tasks_feed_the_product_dedup_query(lab_vectors):
    vector_db, index, embedder = lab_vectors
    records, report = plan_vectors(
        UID,
        action_items=[
            {'id': 't1', 'description': 'Order heirloom tomato seeds'},
            {'id': 't2', 'description': 'Book the hall for the festival'},
        ],
        memories=[{'id': 'm1', 'content': 'The owner grows tomatoes', 'category': 'interesting'}],
    )
    apply_with_product(records, UID, report)
    assert report.written == {'ns2': 1, 'ns4': 2}
    hits = vector_db.find_similar_action_items(UID, 'order heirloom tomato seeds')
    assert [hit['action_item_id'] for hit in hits] == ['t1']
    assert hits[0]['score'] >= 0.6
    assert vector_db.find_similar_action_items(UID, 'renew the passport') == []
    assert index.count('ns4') == 2 and embedder.calls >= 3


def test_conversation_summary_vector_round_trip(lab_vectors):
    vector_db, index, embedder = lab_vectors
    vector = embedder.embed(['compost bin repair'])[0]
    assert vector_db.upsert_vector2(UID, 'c1', vector, {'created_at': 1_700_000_000}) is True
    record = index.fetch(ids=[f'{UID}-c1'], namespace='ns1')['vectors'][f'{UID}-c1']
    assert record['metadata'] == {'uid': UID, 'memory_id': 'c1', 'created_at': 1_700_000_000}
    assert vector_db.query_vectors('compost bin repair', UID, k=3) == ['c1']
    assert vector_db.query_vectors('compost bin repair', UID, starts_at=1_800_000_000, k=3) == []


def test_product_embedder_binds_the_real_client_before_install(monkeypatch, tmp_path):
    from utils.llm import clients

    from testing.pipeline_lab.vector.embed import CachedEmbedder, ProductEmbedder

    class FakeClient:
        calls = 0

        def embed_documents(self, texts):
            FakeClient.calls += 1
            return [[1.0, 0.0] for _ in texts]

    monkeypatch.setattr(clients, 'embeddings', FakeClient())
    embedder = CachedEmbedder(ProductEmbedder(dimension=2), tmp_path)
    with ExitStack() as stack:
        adapter = install_embeddings(stack, embedder)
        assert clients.embeddings is adapter
        # Through the swapped module name: adapter -> cache -> product client, no recursion.
        assert clients.generate_embedding('hello') == [1.0, 0.0]
        assert clients.generate_embedding('hello') == [1.0, 0.0]
    assert FakeClient.calls == 1 and embedder.hits == 1
    assert isinstance(clients.embeddings, FakeClient)
