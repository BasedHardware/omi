from datetime import datetime, timedelta, timezone

from models.memory_evidence import ArtifactPreservationState, MemoryEvidence, SourceState
from models.v17_memory_search_gateway import SearchMode, SearchVectorHit
from models.v17_product_memory import MemoryAccessPolicy, MemoryItemStatus, MemoryTier, ProcessingState, V17MemoryItem
from utils.memory.v17_vector_search_service import fetch_default_v17_vector_memory_search


class _Snapshot:
    def __init__(self, data=None):
        self._data = data

    def to_dict(self):
        return dict(self._data or {})


class _CollectionRef:
    def __init__(self, db_client, path):
        self._db_client = db_client
        self.path = path

    def stream(self):
        prefix = f'{self.path}/'
        snapshots = []
        for path, data in sorted(self._db_client.docs.items()):
            if not path.startswith(prefix) or '/' in path[len(prefix) :]:
                continue
            snapshots.append(_Snapshot(data))
        return snapshots


class _FirestoreFake:
    def __init__(self, docs=None):
        self.docs = docs or {}
        self.collection_paths = []

    def collection(self, path):
        self.collection_paths.append(path)
        return _CollectionRef(self, path)


class _VectorCandidateResult:
    def __init__(self, hits, rejected_count=0):
        self.hits = hits
        self.rejected_count = rejected_count


def _evidence(source_id='conv1'):
    return MemoryEvidence(
        evidence_id=f'ev-{source_id}',
        source_id=source_id,
        source_type='conversation',
        source_version='v1',
        quote_refs=[{'text': 'User prefers hydrated vector memory search.'}],
        content_hash='hash1',
        source_state=SourceState.active,
        artifact_preservation=ArtifactPreservationState.preserved,
    )


def _memory_item(memory_id: str, *, tier=MemoryTier.short_term, now=None, captured_at=None, content=None, **overrides):
    now = now or datetime.now(timezone.utc)
    captured_at = captured_at or (now - timedelta(days=1))
    data = {
        'memory_id': memory_id,
        'uid': 'u1',
        'version': 1,
        'tier': tier,
        'status': MemoryItemStatus.active,
        'processing_state': ProcessingState.pending if tier == MemoryTier.short_term else ProcessingState.processed,
        'content': content or f'{memory_id} coffee preference',
        'evidence': [_evidence(f'{memory_id}-source')],
        'source_state': SourceState.active,
        'sensitivity_labels': [],
        'visibility': 'private',
        'user_asserted': False,
        'captured_at': captured_at,
        'updated_at': now - timedelta(minutes=10),
        'expires_at': captured_at + timedelta(days=30) if tier == MemoryTier.short_term else None,
        'ledger_commit_id': 'commit-1' if tier == MemoryTier.long_term else None,
        'ledger_sequence': 1 if tier == MemoryTier.long_term else None,
        'item_revision': 1,
        'source_commit_id': 'source-commit-1',
        'content_hash': f'hash-{memory_id}',
    }
    data.update(overrides)
    return V17MemoryItem(**data)


def _stored_item(item):
    return item.model_dump(mode='json')


def _hit(item, *, score, projection_commit_id='projection-1'):
    return SearchVectorHit(
        memory_id=item.memory_id,
        score=score,
        projection_commit_id=projection_commit_id,
        vector_updated_at=item.updated_at + timedelta(minutes=1),
        uid=item.uid,
        account_generation=item.account_generation,
        item_revision=item.item_revision,
        source_commit_id=item.source_commit_id,
        content_hash=item.content_hash,
    )


def test_default_v17_vector_search_hydrates_authoritative_items_and_filters_stale_short_term_and_archive():
    now = datetime.now(timezone.utc)
    fresh_short_term = _memory_item('fresh-short-term', now=now, content='coffee fresh short term')
    stale_short_term = _memory_item(
        'stale-short-term',
        now=now,
        captured_at=now - timedelta(days=45),
        content='coffee stale short term',
    )
    long_term = _memory_item('long-term', tier=MemoryTier.long_term, now=now, content='coffee long term')
    archive = _memory_item('archive', tier=MemoryTier.archive, now=now, content='coffee archived memory')
    hits = [
        _hit(stale_short_term, score=0.99),
        _hit(archive, score=0.98),
        _hit(long_term, score=0.90),
        _hit(fresh_short_term, score=0.80),
    ]
    db_client = _FirestoreFake(
        {
            f'users/u1/memory_items/{item.memory_id}': _stored_item(item)
            for item in [fresh_short_term, stale_short_term, long_term, archive]
        }
    )
    vector_calls = []

    def fake_vector_query(uid, query, *, mode, limit):
        vector_calls.append({'uid': uid, 'query': query, 'mode': mode, 'limit': limit})
        return _VectorCandidateResult(hits=hits, rejected_count=2)

    response = fetch_default_v17_vector_memory_search(
        uid='u1',
        query='coffee',
        db_client=db_client,
        policy=MemoryAccessPolicy.for_omi_chat(),
        vector_query=fake_vector_query,
        limit=10,
        required_projection_commit_id='projection-1',
    )

    assert vector_calls == [{'uid': 'u1', 'query': 'coffee', 'mode': SearchMode.default, 'limit': 10}]
    assert db_client.collection_paths == ['users/u1/memory_items']
    assert [item['memory_id'] for item in response['items']] == ['long-term', 'fresh-short-term']
    assert response['scores_by_memory_id'] == {'long-term': 0.9, 'fresh-short-term': 0.8}
    assert response['decisions']['stale-short-term'] == 'access_denied'
    assert response['decisions']['archive'] == 'access_denied'
    assert response['vector_rejected_count'] == 2
    assert response['archive_default_visible'] is False


def test_default_v17_vector_search_preserves_vector_ranking_after_authoritative_filtering():
    now = datetime.now(timezone.utc)
    lower_updated_newer = _memory_item('newer-lower-score', tier=MemoryTier.long_term, now=now, updated_at=now)
    higher_score_older = _memory_item(
        'older-higher-score',
        tier=MemoryTier.long_term,
        now=now,
        captured_at=now - timedelta(days=6),
        updated_at=now - timedelta(days=5),
    )
    db_client = _FirestoreFake(
        {
            f'users/u1/memory_items/{item.memory_id}': _stored_item(item)
            for item in [lower_updated_newer, higher_score_older]
        }
    )

    def fake_vector_query(uid, query, *, mode, limit):
        return _VectorCandidateResult(
            hits=[_hit(lower_updated_newer, score=0.40), _hit(higher_score_older, score=0.95)], rejected_count=0
        )

    response = fetch_default_v17_vector_memory_search(
        uid='u1',
        query='coffee',
        db_client=db_client,
        policy=MemoryAccessPolicy.for_omi_chat(),
        vector_query=fake_vector_query,
        limit=5,
        required_projection_commit_id='projection-1',
    )

    assert [item['memory_id'] for item in response['items']] == ['older-higher-score', 'newer-lower-score']
