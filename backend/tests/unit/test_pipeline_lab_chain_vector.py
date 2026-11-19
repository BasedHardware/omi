"""Pipeline lab, lane chain: numeric vector index, cached embedder and vector seeding."""

import math

import pytest

from testing.pipeline_lab.vector.embed import CachedEmbedder, FakeEmbedder, LangchainEmbeddingsAdapter, input_hash
from testing.pipeline_lab.vector.index import NumericVectorIndex, UnsupportedFilter, matches_filter
from testing.pipeline_lab.vector.seed import apply_direct, plan_vectors

UID = 'local-dev-user'


def _unit(*values):
    norm = math.sqrt(sum(v * v for v in values))
    return [v / norm for v in values]


def test_query_scores_by_cosine_and_respects_filters_and_top_k():
    index = NumericVectorIndex(3)
    index.upsert(
        vectors=[
            {'id': 'a', 'values': [1, 0, 0], 'metadata': {'uid': UID, 'created_at': 10}},
            {'id': 'b', 'values': [1, 1, 0], 'metadata': {'uid': UID, 'created_at': 20}},
            {'id': 'c', 'values': [0, 0, 1], 'metadata': {'uid': 'someone-else', 'created_at': 30}},
        ],
        namespace='ns4',
    )
    result = index.query(vector=[1, 0, 0], top_k=5, namespace='ns4', filter={'uid': UID}, include_metadata=True)
    assert [m['id'] for m in result['matches']] == ['a', 'b']
    assert result['matches'][0]['score'] == pytest.approx(1.0)
    assert result['matches'][1]['score'] == pytest.approx(1 / math.sqrt(2))
    assert result['matches'][0]['metadata']['created_at'] == 10
    ranged = index.query(vector=[1, 0, 0], top_k=5, namespace='ns4', filter={'created_at': {'$gte': 15, '$lte': 25}})
    assert [m['id'] for m in ranged['matches']] == ['b']
    assert index.query(vector=[1, 0, 0], top_k=1, namespace='ns4')['matches'][0]['id'] == 'a'
    assert index.query(vector=[1, 0, 0], top_k=5, namespace='other')['matches'] == []


def test_dimension_mismatch_is_refused():
    index = NumericVectorIndex(3)
    with pytest.raises(ValueError):
        index.upsert(vectors=[{'id': 'x', 'values': [1, 0], 'metadata': {}}], namespace='ns1')


def test_owner_index_call_shapes():
    """The shapes database/pinecone_partition_index.OwnerIndex relies on."""
    index = NumericVectorIndex(2)
    body, status, headers = index.upsert(
        vectors=[{'id': f'{UID}-1', 'values': [1, 0], 'metadata': {'uid': UID}}],
        namespace='ns1-p1-0a',
        _return_http_data_only=False,
    )
    assert status == 200 and int(headers['x-pinecone-request-lsn']) == 1
    fetched = index.fetch(ids=[f'{UID}-1', 'missing'], namespace='ns1-p1-0a')
    assert list(fetched['vectors']) == [f'{UID}-1']
    assert fetched['vectors'][f'{UID}-1']['metadata']['uid'] == UID
    index.update(f'{UID}-1', set_metadata={'title': 't'}, namespace='ns1-p1-0a', _return_http_data_only=False)
    assert index.fetch(ids=[f'{UID}-1'], namespace='ns1-p1-0a')['vectors'][f'{UID}-1']['metadata']['title'] == 't'
    assert list(index.list(prefix=f'{UID}-', namespace='ns1-p1-0a')) == [[f'{UID}-1']]
    assert index.describe_index_stats()['dimension'] == 2
    _, _, headers = index._query(
        namespace='ns1-p1-0a', vector=[1, 0], filter={'uid': UID}, top_k=1, _return_http_data_only=False
    )
    assert 'x-pinecone-max-indexed-lsn' in headers
    index.delete(namespace='ns1-p1-0a', filter={'uid': {'$eq': UID}}, _return_http_data_only=False)
    assert index.count('ns1-p1-0a') == 0


def test_delete_by_ids_and_persistence_round_trip(tmp_path):
    path = tmp_path / 'index.json'
    index = NumericVectorIndex.open(path, dimension=2)
    index.upsert(vectors=[('a', [1, 0], {'uid': UID}), ('b', [0, 1], {'uid': UID})], namespace='ns2')
    index.delete(ids=['a'], namespace='ns2')
    index.save()
    assert (path.stat().st_mode & 0o777) == 0o600
    loaded = NumericVectorIndex.open(path, dimension=2)
    assert loaded.namespaces() == {'ns2': 1}
    assert loaded.query(vector=[0, 1], top_k=1, namespace='ns2')['matches'][0]['id'] == 'b'
    with pytest.raises(ValueError):
        NumericVectorIndex.open(path, dimension=3)


@pytest.mark.parametrize(
    'expression,expected',
    [
        ({'k': 'v'}, True),
        ({'k': {'$ne': 'v'}}, False),
        ({'k': {'$in': ['x', 'v']}}, True),
        ({'k': {'$nin': ['v']}}, False),
        ({'tags': {'$in': ['b']}}, True),
        ({'missing': {'$exists': False}}, True),
        ({'n': {'$gt': 5, '$lt': 7}}, True),
        ({'$or': [{'k': 'nope'}, {'n': 6}]}, True),
        ({'$and': [{'k': 'v'}, {'n': {'$lt': 6}}]}, False),
    ],
)
def test_filter_operators(expression, expected):
    assert matches_filter({'k': 'v', 'n': 6, 'tags': ['a', 'b']}, expression) is expected


def test_unknown_filter_operator_is_refused():
    with pytest.raises(UnsupportedFilter):
        matches_filter({'k': 1}, {'k': {'$regex': '.*'}})


def test_fake_embedder_is_deterministic_and_similarity_tracks_shared_words():
    embedder = FakeEmbedder(dimension=64)
    a, b, c = embedder.embed(['buy hinges for the compost bin', 'buy hinges for compost', 'book the festival hall'])
    assert a == embedder.embed(['buy hinges for the compost bin'])[0]
    index = NumericVectorIndex(64)
    index.upsert(
        vectors=[{'id': 'b', 'values': b, 'metadata': {}}, {'id': 'c', 'values': c, 'metadata': {}}], namespace='n'
    )
    scores = {m['id']: m['score'] for m in index.query(vector=a, top_k=2, namespace='n')['matches']}
    assert scores['b'] > 0.6 > scores['c']


def test_cached_embedder_hits_disk_cache_across_instances(tmp_path):
    inner = FakeEmbedder(dimension=8)
    first = CachedEmbedder(inner, tmp_path)
    vectors = first.embed(['alpha', 'beta', 'alpha'])
    assert inner.texts_embedded == 3 and first.misses == 3
    second_inner = FakeEmbedder(dimension=8)
    second = CachedEmbedder(second_inner, tmp_path)
    assert second.embed(['beta', 'alpha']) == [vectors[1], vectors[0]]
    assert second_inner.calls == 0 and second.hits == 2
    key = input_hash(inner.model, 'alpha')
    assert (tmp_path / key[:2] / f'{key}.json').exists()
    adapter = LangchainEmbeddingsAdapter(second)
    assert adapter.embed_query('alpha') == vectors[0]


def test_seed_plan_uses_production_ids_namespaces_and_skips_dead_rows():
    records, report = plan_vectors(
        UID,
        conversations=[
            {'id': 'c1', 'structured': {'title': 'Seeds', 'overview': 'o'}, 'created_at': '2026-03-13T09:00:00Z'},
            {'id': 'c2', 'structured': {'title': 'Gone'}, 'discarded': True},
            {'id': 'c3', 'structured': {}},
        ],
        memories=[
            {'id': 'm1', 'content': 'Likes tomatoes', 'category': 'interesting'},
            {'id': 'm2', 'content': 'Old', 'invalid_at': '2026-01-01T00:00:00Z'},
        ],
        action_items=[{'id': 't1', 'description': 'Order seeds'}, {'id': 't2', 'description': '  '}],
        text_for_structured=lambda s: f"{s.get('title')} {s.get('overview')}",
    )
    by_ns = {(r.namespace, r.vector_id) for r in records}
    assert by_ns == {('ns1', f'{UID}-c1'), ('ns2', f'{UID}-m1'), ('ns4', f'{UID}-ai-t1')}
    assert report.skipped == {'conversations': 2, 'memories': 1, 'action_items': 1}
    ns1 = next(r for r in records if r.namespace == 'ns1')
    assert ns1.metadata['created_at'] == 1773392400 and ns1.metadata['uid'] == UID
    index = NumericVectorIndex(32)
    apply_direct(records, index, FakeEmbedder(32), report)
    assert report.written == {'ns1': 1, 'ns2': 1, 'ns4': 1}
    assert (
        index.query(vector=FakeEmbedder(32).embed(['Order seeds'])[0], top_k=1, namespace='ns4')['matches'][0]['id']
        == f'{UID}-ai-t1'
    )


class _Status(Exception):
    def __init__(self, status):
        super().__init__(f'http {status}')
        self.response = type('R', (), {'status_code': status})()


class _PoisonEmbedder(FakeEmbedder):
    """Fails with ``status`` whenever the batch contains ``poison`` (a real day saw one such batch)."""

    def __init__(self, poison, status=502):
        super().__init__(dimension=16)
        self.poison = poison
        self.status = status

    def embed(self, texts):
        if self.poison in texts:
            raise _Status(self.status)
        return super().embed(texts)


def test_cached_embedder_bisects_a_provider_failure_to_the_bad_text(tmp_path):
    inner = _PoisonEmbedder('bad text')
    embedder = CachedEmbedder(inner, tmp_path)
    texts = ['alpha', 'beta', 'bad text', 'gamma', 'delta']
    vectors = embedder.embed(texts)
    assert len(vectors) == 5 and embedder.failed == 1
    assert vectors[0] == FakeEmbedder(16).embed(['alpha'])[0]
    # the placeholder is a deterministic unit vector, not cached, near-orthogonal to real ones
    assert abs(sum(v * v for v in vectors[2]) - 1.0) < 1e-9
    assert vectors[2] == CachedEmbedder(_PoisonEmbedder('bad text'), tmp_path).embed(['bad text'])[0]
    assert not any(p.name.startswith(input_hash(embedder.model, 'bad text')) for p in tmp_path.rglob('*.json'))


def test_cached_embedder_never_swallows_a_spend_cap_or_client_error(tmp_path):
    for status in (402, 400):
        embedder = CachedEmbedder(_PoisonEmbedder('x', status=status), tmp_path)
        with pytest.raises(_Status):
            embedder.embed(['a', 'x'])


def test_cached_embedder_sends_small_batches(tmp_path, monkeypatch):
    from testing.pipeline_lab.vector import embed

    monkeypatch.setattr(embed, 'EMBED_BATCH_ITEMS', 4)
    sizes = []

    class Recording(FakeEmbedder):
        def embed(self, texts):
            sizes.append(len(texts))
            return super().embed(texts)

    vectors = CachedEmbedder(Recording(dimension=8), tmp_path).embed([f't{i}' for i in range(10)])
    assert len(vectors) == 10 and sizes == [4, 4, 2]
