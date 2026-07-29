"""Generation ownership contracts for conversation search vectors."""

from __future__ import annotations

from types import SimpleNamespace

from database import vector_db


class _Index:
    def __init__(self, matches=()):
        self.matches = list(matches)
        self.deleted: list[tuple[str, tuple[str, ...]]] = []
        self.upserted: list[tuple[str, list[dict]]] = []
        self.list_calls = 0
        self.query_top_ks: list[int] = []

    def query(self, **kwargs):
        top_k = int(kwargs['top_k'])
        self.query_top_ks.append(top_k)
        return {'matches': list(self.matches[:top_k])}

    def delete(self, *, ids, namespace):
        self.deleted.append((namespace, tuple(ids)))

    def upsert(self, *, vectors, namespace):
        self.upserted.append((namespace, list(vectors)))
        return {'upserted_count': len(vectors)}

    def list(self, **_kwargs):
        self.list_calls += 1
        raise AssertionError('exact generation cleanup must not depend on eventually consistent listing')


class _ListingIndex:
    def __init__(self, vector_ids):
        self.vector_ids = set(vector_ids)
        self.listed_prefixes: list[str] = []
        self.deleted: list[tuple[str, tuple[str, ...]]] = []

    def list(self, *, prefix, namespace):
        assert namespace == vector_db.TRANSCRIPT_CHUNKS_NAMESPACE
        self.listed_prefixes.append(prefix)
        return [[vector_id for vector_id in sorted(self.vector_ids) if vector_id.startswith(prefix)]]

    def delete(self, *, ids, namespace):
        self.deleted.append((namespace, tuple(ids)))


def _mixed_matches():
    return [
        {'id': 'uid-1-conversation-1', 'metadata': {'memory_id': 'conversation-1'}},
        {
            'id': 'uid-1-conversation-1-gold-generation',
            'metadata': {
                'memory_id': 'conversation-1',
                'finalization_vector_generation_id': 'old-generation',
            },
        },
        {'id': 'uid-1-conversation-2', 'metadata': {'memory_id': 'conversation-2'}},
    ]


def test_query_vectors_maps_mixed_physical_generations_to_unique_logical_ids(monkeypatch):
    fake = _Index(_mixed_matches())
    monkeypatch.setattr(vector_db, 'index', fake)
    monkeypatch.setattr(vector_db, 'embeddings', SimpleNamespace(embed_query=lambda _query: [0.1]))

    assert vector_db.query_vectors('query', 'uid-1', k=10) == ['conversation-1', 'conversation-2']


def test_query_vectors_oversamples_before_deduplicating_physical_generations(monkeypatch):
    fake = _Index(
        [
            {'id': 'uid-1-conversation-1', 'metadata': {'memory_id': 'conversation-1'}},
            {
                'id': 'uid-1-conversation-1-ggeneration-1',
                'metadata': {'memory_id': 'conversation-1'},
            },
            {'id': 'uid-1-conversation-2', 'metadata': {'memory_id': 'conversation-2'}},
        ]
    )
    monkeypatch.setattr(vector_db, 'index', fake)
    monkeypatch.setattr(vector_db, 'embeddings', SimpleNamespace(embed_query=lambda _query: [0.1]))

    assert vector_db.query_vectors('query', 'uid-1', k=2) == ['conversation-1', 'conversation-2']
    assert fake.query_top_ks == [4]


def test_metadata_query_maps_mixed_physical_generations_to_unique_logical_ids(monkeypatch):
    monkeypatch.setattr(vector_db, 'index', _Index(_mixed_matches()))

    result = vector_db.query_vectors_by_metadata(
        'uid-1',
        [0.1],
        [],
        [],
        [],
        [],
        [],
        limit=10,
    )

    assert result == ['conversation-1', 'conversation-2']


def test_metadata_query_scores_each_logical_conversation_once(monkeypatch):
    fake = _Index(
        [
            {
                'id': 'uid-1-conversation-1',
                'metadata': {'memory_id': 'conversation-1', 'topics': ['alpha']},
            },
            {
                'id': 'uid-1-conversation-1-ggeneration-1',
                'metadata': {'memory_id': 'conversation-1', 'topics': ['alpha']},
            },
            {
                'id': 'uid-1-conversation-2',
                'metadata': {'memory_id': 'conversation-2', 'topics': ['alpha', 'beta']},
            },
        ]
    )
    monkeypatch.setattr(vector_db, 'index', fake)

    result = vector_db.query_vectors_by_metadata(
        'uid-1',
        [0.1],
        [],
        [],
        ['alpha', 'beta'],
        [],
        [],
        limit=2,
    )

    assert result == ['conversation-2', 'conversation-1']


def test_transcript_search_oversamples_and_deduplicates_logical_chunks(monkeypatch):
    fake = _Index(
        [
            {
                'id': 'uid-1-conversation-1-c0',
                'score': 0.99,
                'metadata': {'conversation_id': 'conversation-1', 'chunk_index': 0, 'created_at': 1},
            },
            {
                'id': 'uid-1-conversation-1-ggeneration-1-c0',
                'score': 0.98,
                'metadata': {'conversation_id': 'conversation-1', 'chunk_index': 0, 'created_at': 1},
            },
            {
                'id': 'uid-1-conversation-2-c0',
                'score': 0.97,
                'metadata': {'conversation_id': 'conversation-2', 'chunk_index': 0, 'created_at': 2},
            },
        ]
    )
    monkeypatch.setattr(vector_db, 'index', fake)
    monkeypatch.setattr(vector_db, 'embeddings', SimpleNamespace(embed_query=lambda _query: [0.1]))

    result = vector_db.search_transcript_chunks('uid-1', 'query', limit=2)

    assert [(item['conversation_id'], item['chunk_index']) for item in result] == [
        ('conversation-1', 0),
        ('conversation-2', 0),
    ]
    assert fake.query_top_ks == [4]


def test_structured_and_transcript_writers_share_the_persisted_generation(monkeypatch):
    fake = _Index()
    monkeypatch.setattr(vector_db, 'index', fake)
    monkeypatch.setattr(
        vector_db,
        'embeddings',
        SimpleNamespace(embed_documents=lambda values: [[float(index)] for index, _ in enumerate(values)]),
    )

    vector_db.upsert_vector2(
        'uid-1',
        'conversation-1',
        [0.1],
        {'created_at': 1},
        'generation-1',
    )
    vector_db.upsert_transcript_chunk_vectors(
        'uid-1',
        'conversation-1',
        [
            {'text': 'first', 'created_at': 1, 'chunk_index': 0},
            {'text': 'second', 'created_at': 1, 'chunk_index': 1},
        ],
        'generation-1',
    )

    structured = fake.upserted[0][1][0]
    transcript = fake.upserted[1][1]
    assert structured['id'] == 'uid-1-conversation-1-ggeneration-1'
    assert structured['metadata']['finalization_vector_generation_id'] == 'generation-1'
    assert [item['id'] for item in transcript] == [
        'uid-1-conversation-1-ggeneration-1-c0',
        'uid-1-conversation-1-ggeneration-1-c1',
    ]
    assert {item['metadata']['finalization_vector_generation_id'] for item in transcript} == {'generation-1'}


def test_exact_cleanup_ignores_stale_provider_listing_and_removes_every_declared_id(monkeypatch):
    fake = _Index()
    monkeypatch.setattr(vector_db, 'index', fake)

    vector_db.delete_finalization_enrichment_vectors(
        'uid-1',
        'conversation-1',
        'generation-1',
        3,
    )

    assert fake.list_calls == 0
    assert fake.deleted == [
        ('ns1', ('uid-1-conversation-1-ggeneration-1',)),
        (
            vector_db.TRANSCRIPT_CHUNKS_NAMESPACE,
            (
                'uid-1-conversation-1-ggeneration-1-c0',
                'uid-1-conversation-1-ggeneration-1-c1',
                'uid-1-conversation-1-ggeneration-1-c2',
            ),
        ),
    ]


def test_old_generation_cleanup_cannot_target_a_recreated_conversation_generation(monkeypatch):
    fake = _Index()
    monkeypatch.setattr(vector_db, 'index', fake)

    vector_db.delete_finalization_enrichment_vectors(
        'uid-1',
        'conversation-1',
        'deleted-generation',
        2,
    )

    deleted_ids = {item for _, ids in fake.deleted for item in ids}
    assert 'uid-1-conversation-1-grecreated-generation' not in deleted_ids
    assert 'uid-1-conversation-1-grecreated-generation-c0' not in deleted_ids
    assert deleted_ids == {
        'uid-1-conversation-1-gdeleted-generation',
        'uid-1-conversation-1-gdeleted-generation-c0',
        'uid-1-conversation-1-gdeleted-generation-c1',
    }


def test_conversation_delete_targets_legacy_and_captured_structured_generations(monkeypatch):
    fake = _Index()
    monkeypatch.setattr(vector_db, 'index', fake)

    vector_db.delete_vector('uid-1', 'conversation-1', 'deleted-generation')

    assert fake.deleted == [
        (
            'ns1',
            (
                'uid-1-conversation-1',
                'uid-1-conversation-1-gdeleted-generation',
            ),
        )
    ]
    assert 'uid-1-conversation-1-grecreated-generation' not in fake.deleted[0][1]


def test_generation_only_structured_cleanup_never_targets_shared_legacy_ids(monkeypatch):
    fake = _Index()
    monkeypatch.setattr(vector_db, 'index', fake)

    vector_db.delete_vector(
        'uid-1',
        'conversation-1',
        'deleted-generation',
        include_legacy=False,
    )

    assert fake.deleted == [
        (
            'ns1',
            ('uid-1-conversation-1-gdeleted-generation',),
        )
    ]


def test_transcript_delete_prefixes_exclude_a_recreated_generation(monkeypatch):
    fake = _ListingIndex(
        {
            'uid-1-conversation-1-c0',
            'uid-1-conversation-1-gdeleted-generation-c0',
            'uid-1-conversation-1-gdeleted-generation-c1',
            'uid-1-conversation-1-grecreated-generation-c0',
        }
    )
    monkeypatch.setattr(vector_db, 'index', fake)

    vector_db.delete_transcript_chunk_vectors(
        'uid-1',
        'conversation-1',
        finalization_vector_generation_id='deleted-generation',
    )

    assert fake.listed_prefixes == [
        'uid-1-conversation-1-c',
        'uid-1-conversation-1-gdeleted-generation-c',
    ]
    assert fake.deleted == [
        (
            vector_db.TRANSCRIPT_CHUNKS_NAMESPACE,
            (
                'uid-1-conversation-1-c0',
                'uid-1-conversation-1-gdeleted-generation-c0',
                'uid-1-conversation-1-gdeleted-generation-c1',
            ),
        )
    ]
    assert 'uid-1-conversation-1-grecreated-generation-c0' not in fake.deleted[0][1]


def test_known_transcript_count_deletes_generation_by_exact_id_without_listing_it(monkeypatch):
    fake = _ListingIndex(
        {
            'uid-1-conversation-1-c0',
            'uid-1-conversation-1-ggeneration-1-c0',
            'uid-1-conversation-1-ggeneration-1-c1',
            'uid-1-conversation-1-gnewer-generation-c0',
        }
    )
    monkeypatch.setattr(vector_db, 'index', fake)

    vector_db.delete_transcript_chunk_vectors(
        'uid-1',
        'conversation-1',
        finalization_vector_generation_id='generation-1',
        transcript_vector_count=2,
        raise_on_failure=True,
    )

    assert fake.listed_prefixes == ['uid-1-conversation-1-c']
    deleted_ids = {vector_id for _, vector_ids in fake.deleted for vector_id in vector_ids}
    assert deleted_ids == {
        'uid-1-conversation-1-c0',
        'uid-1-conversation-1-ggeneration-1-c0',
        'uid-1-conversation-1-ggeneration-1-c1',
    }


def test_generation_only_transcript_cleanup_excludes_legacy_and_recreated_generations(monkeypatch):
    fake = _ListingIndex(
        {
            'uid-1-conversation-1-c0',
            'uid-1-conversation-1-gdeleted-generation-c0',
            'uid-1-conversation-1-grecreated-generation-c0',
        }
    )
    monkeypatch.setattr(vector_db, 'index', fake)

    vector_db.delete_transcript_chunk_vectors(
        'uid-1',
        'conversation-1',
        finalization_vector_generation_id='deleted-generation',
        include_legacy=False,
    )

    assert fake.listed_prefixes == ['uid-1-conversation-1-gdeleted-generation-c']
    assert fake.deleted == [
        (
            vector_db.TRANSCRIPT_CHUNKS_NAMESPACE,
            ('uid-1-conversation-1-gdeleted-generation-c0',),
        )
    ]


def test_account_batch_delete_includes_each_persisted_structured_generation(monkeypatch):
    fake = _Index()
    monkeypatch.setattr(vector_db, 'index', fake)

    vector_db.delete_conversation_vectors_batch(
        'uid-1',
        ['conversation-1', 'conversation-2'],
        finalization_vector_generation_ids={
            'conversation-1': 'generation-1',
            'conversation-2': None,
        },
    )

    assert fake.deleted == [
        (
            'ns1',
            (
                'uid-1-conversation-1',
                'uid-1-conversation-1-ggeneration-1',
                'uid-1-conversation-2',
            ),
        )
    ]


def test_account_transcript_batch_uses_each_persisted_generation(monkeypatch):
    fake = _ListingIndex(
        {
            'uid-1-conversation-1-c0',
            'uid-1-conversation-1-ggeneration-1-c0',
            'uid-1-conversation-1-grecreated-generation-c0',
            'uid-1-conversation-2-c0',
        }
    )
    monkeypatch.setattr(vector_db, 'index', fake)

    deleted = vector_db.delete_transcript_chunk_vectors_batch(
        'uid-1',
        ['conversation-1', 'conversation-2'],
        finalization_vector_generation_ids={
            'conversation-1': 'generation-1',
            'conversation-2': None,
        },
        raise_on_failure=True,
    )

    assert deleted == 3
    assert fake.listed_prefixes == [
        'uid-1-conversation-1-c',
        'uid-1-conversation-1-ggeneration-1-c',
        'uid-1-conversation-2-c',
    ]
    deleted_ids = {vector_id for _, vector_ids in fake.deleted for vector_id in vector_ids}
    assert deleted_ids == {
        'uid-1-conversation-1-c0',
        'uid-1-conversation-1-ggeneration-1-c0',
        'uid-1-conversation-2-c0',
    }
    assert 'uid-1-conversation-1-grecreated-generation-c0' not in deleted_ids
