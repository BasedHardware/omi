from datetime import datetime, timedelta, timezone

from models.memory_evidence import ArtifactPreservationState, MemoryEvidence, SourceState
from models.v17_memory_search_gateway import SearchMode, SearchVectorHit, VectorRepairPurgeReason
from models.v17_product_memory import MemoryAccessPolicy, MemoryItemStatus, MemoryTier, ProcessingState, V17MemoryItem
from database.v17_vector_repair_outbox import (
    build_v17_vector_repair_purge_outbox_records,
    write_v17_vector_repair_purge_outbox_records,
)
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


def _hit(item, *, score, projection_commit_id='projection-1', vector_id=None, **overrides):
    data = {
        'memory_id': item.memory_id,
        'score': score,
        'projection_commit_id': projection_commit_id,
        'vector_updated_at': item.updated_at + timedelta(minutes=1),
        'uid': item.uid,
        'account_generation': item.account_generation,
        'item_revision': item.item_revision,
        'source_commit_id': item.source_commit_id,
        'content_hash': item.content_hash,
    }
    if vector_id is not None:
        data['vector_id'] = vector_id
    data.update(overrides)
    return SearchVectorHit(**data)


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
        required_account_generation=0,
    )

    assert vector_calls == [{'uid': 'u1', 'query': 'coffee', 'mode': SearchMode.default, 'limit': 10}]
    assert db_client.collection_paths == ['users/u1/memory_items']
    assert [item['memory_id'] for item in response['items']] == ['long-term', 'fresh-short-term']
    assert response['scores_by_memory_id'] == {'long-term': 0.9, 'fresh-short-term': 0.8}
    assert response['decisions']['stale-short-term'] == 'access_denied'
    assert response['decisions']['archive'] == 'access_denied'
    assert response['vector_rejected_count'] == 2
    assert response['archive_default_visible'] is False


def test_default_v17_vector_search_rejects_missing_freshness_fence_before_vector_query_or_repair_callback():
    vector_calls = []
    repair_batches = []

    def fake_vector_query(uid, query, *, mode, limit):
        vector_calls.append({'uid': uid, 'query': query, 'mode': mode, 'limit': limit})
        return _VectorCandidateResult(hits=[], rejected_count=0)

    try:
        fetch_default_v17_vector_memory_search(
            uid='u1',
            query='coffee',
            db_client=_FirestoreFake(),
            policy=MemoryAccessPolicy.for_omi_chat(),
            vector_query=fake_vector_query,
            repair_purge_callback=lambda candidates: repair_batches.append(candidates),
            limit=5,
            required_projection_commit_id='',
            required_account_generation=0,
        )
    except ValueError as exc:
        assert str(exc) == 'required_projection_commit_id is required'
    else:
        raise AssertionError('expected missing projection fence to fail closed')

    assert vector_calls == []
    assert repair_batches == []


def test_default_v17_vector_search_rejects_hits_missing_mandatory_freshness_fence_fields():
    now = datetime.now(timezone.utc)
    item = _memory_item('missing-fence-fields', tier=MemoryTier.long_term, now=now)
    db_client = _FirestoreFake({f'users/u1/memory_items/{item.memory_id}': _stored_item(item)})

    def fake_vector_query(uid, query, *, mode, limit):
        return _VectorCandidateResult(
            hits=[
                SearchVectorHit(
                    memory_id=item.memory_id,
                    score=0.99,
                    projection_commit_id='projection-1',
                    vector_updated_at=item.updated_at + timedelta(minutes=1),
                )
            ],
            rejected_count=0,
        )

    response = fetch_default_v17_vector_memory_search(
        uid='u1',
        query='coffee',
        db_client=db_client,
        policy=MemoryAccessPolicy.for_omi_chat(),
        vector_query=fake_vector_query,
        limit=5,
        required_projection_commit_id='projection-1',
        required_account_generation=0,
    )

    assert response['items'] == []
    assert response['decisions'] == {'missing-fence-fields': 'stale_vector'}


def test_default_v17_vector_search_rejects_vectors_from_purged_account_generation_even_when_item_matches_hit():
    now = datetime.now(timezone.utc)
    stale_generation_item = _memory_item('stale-generation', tier=MemoryTier.long_term, now=now, account_generation=2)
    db_client = _FirestoreFake(
        {f'users/u1/memory_items/{stale_generation_item.memory_id}': _stored_item(stale_generation_item)}
    )

    def fake_vector_query(uid, query, *, mode, limit):
        return _VectorCandidateResult(hits=[_hit(stale_generation_item, score=0.99)], rejected_count=0)

    response = fetch_default_v17_vector_memory_search(
        uid='u1',
        query='coffee',
        db_client=db_client,
        policy=MemoryAccessPolicy.for_omi_chat(),
        vector_query=fake_vector_query,
        limit=5,
        required_projection_commit_id='projection-1',
        required_account_generation=3,
    )

    assert response['items'] == []
    assert response['decisions'] == {'stale-generation': 'stale_vector'}


def test_default_v17_vector_search_dispatches_repair_purge_candidates_for_hydration_rejects():
    now = datetime.now(timezone.utc)
    missing_authoritative = _memory_item('missing-authoritative', tier=MemoryTier.long_term, now=now)
    stale_projection = _memory_item('stale-projection', tier=MemoryTier.long_term, now=now)
    missing_metadata = _memory_item('missing-metadata', tier=MemoryTier.long_term, now=now)
    old_generation = _memory_item('old-generation', tier=MemoryTier.long_term, now=now, account_generation=1)
    valid = _memory_item('valid', tier=MemoryTier.long_term, now=now)
    db_client = _FirestoreFake(
        {
            f'users/u1/memory_items/{item.memory_id}': _stored_item(item)
            for item in [stale_projection, missing_metadata, old_generation, valid]
        }
    )
    repair_batches = []

    def fake_vector_query(uid, query, *, mode, limit):
        return _VectorCandidateResult(
            hits=[
                _hit(missing_authoritative, score=0.99, vector_id='v17mem:missing-authoritative'),
                _hit(
                    stale_projection,
                    score=0.98,
                    vector_id='v17mem:stale-projection',
                    projection_commit_id='projection-old',
                ),
                _hit(missing_metadata, score=0.97, vector_id='v17mem:missing-metadata', uid=None),
                _hit(old_generation, score=0.96, vector_id='v17mem:old-generation'),
                _hit(valid, score=0.95, vector_id='v17mem:valid'),
            ],
            rejected_count=0,
        )

    response = fetch_default_v17_vector_memory_search(
        uid='u1',
        query='coffee',
        db_client=db_client,
        policy=MemoryAccessPolicy.for_omi_chat(),
        vector_query=fake_vector_query,
        repair_purge_callback=lambda candidates: repair_batches.append(candidates),
        limit=5,
        required_projection_commit_id='projection-1',
        required_account_generation=0,
    )

    assert [item['memory_id'] for item in response['items']] == ['valid']
    assert repair_batches == [response['repair_purge_candidates']]
    assert response['repair_purge_candidate_count'] == 4
    assert [
        (candidate['vector_id'], candidate['memory_id'], candidate['reason']) for candidate in repair_batches[0]
    ] == [
        ('v17mem:missing-authoritative', 'missing-authoritative', VectorRepairPurgeReason.missing_authoritative_item),
        ('v17mem:stale-projection', 'stale-projection', VectorRepairPurgeReason.stale_projection_commit),
        ('v17mem:missing-metadata', 'missing-metadata', VectorRepairPurgeReason.missing_vector_freshness_metadata),
        ('v17mem:old-generation', 'old-generation', VectorRepairPurgeReason.stale_account_generation),
    ]
    assert 'valid' not in {candidate['memory_id'] for candidate in repair_batches[0]}


def test_default_v17_vector_search_writes_deterministic_repair_purge_outbox_records_once():
    now = datetime.now(timezone.utc)
    stale_projection = _memory_item('stale-projection', tier=MemoryTier.long_term, now=now)
    valid = _memory_item('valid', tier=MemoryTier.long_term, now=now)
    db_client = _FirestoreFake(
        {f'users/u1/memory_items/{item.memory_id}': _stored_item(item) for item in [stale_projection, valid]}
    )
    writer_batches = []

    def fake_vector_query(uid, query, *, mode, limit):
        return _VectorCandidateResult(
            hits=[
                _hit(
                    stale_projection,
                    score=0.98,
                    vector_id='v17mem:stale-projection',
                    projection_commit_id='projection-old',
                ),
                _hit(valid, score=0.95, vector_id='v17mem:valid'),
            ],
            rejected_count=0,
        )

    response = fetch_default_v17_vector_memory_search(
        uid='u1',
        query='coffee',
        db_client=db_client,
        policy=MemoryAccessPolicy.for_omi_chat(),
        vector_query=fake_vector_query,
        repair_purge_outbox_writer=lambda records: writer_batches.append(records),
        limit=5,
        required_projection_commit_id='projection-1',
        required_account_generation=0,
    )

    assert [item['memory_id'] for item in response['items']] == ['valid']
    assert len(writer_batches) == 1
    assert writer_batches[0] == response['repair_purge_outbox_records']
    assert response['repair_purge_outbox_record_count'] == 1
    record = writer_batches[0][0]
    assert record['record_id'].startswith('v17vrp_')
    assert record['idempotency_key'] == record['record_id']
    assert record['uid'] == 'u1'
    assert record['event_type'] == 'vector_repair_purge'
    assert record['status'] == 'pending'
    assert record['vector_id'] == 'v17mem:stale-projection'
    assert record['memory_id'] == 'stale-projection'
    assert record['reason'] == VectorRepairPurgeReason.stale_projection_commit
    assert record['required_projection_commit_id'] == 'projection-1'
    assert record['observed_projection_commit_id'] == 'projection-old'
    assert record['required_account_generation'] == 0
    assert record['outbox_path'] == f"users/u1/memory_outbox/{record['record_id']}"

    rebuilt = build_v17_vector_repair_purge_outbox_records(uid='u1', candidates=response['repair_purge_candidates'])
    assert [record['record_id'] for record in rebuilt] == [record['record_id']]


def test_default_v17_vector_search_does_not_write_outbox_for_no_candidates_or_missing_fence():
    now = datetime.now(timezone.utc)
    valid = _memory_item('valid', tier=MemoryTier.long_term, now=now)
    db_client = _FirestoreFake({f'users/u1/memory_items/{valid.memory_id}': _stored_item(valid)})
    writer_batches = []
    vector_calls = []

    def fake_vector_query(uid, query, *, mode, limit):
        vector_calls.append({'uid': uid, 'query': query, 'mode': mode, 'limit': limit})
        return _VectorCandidateResult(hits=[_hit(valid, score=0.95, vector_id='v17mem:valid')], rejected_count=0)

    response = fetch_default_v17_vector_memory_search(
        uid='u1',
        query='coffee',
        db_client=db_client,
        policy=MemoryAccessPolicy.for_omi_chat(),
        vector_query=fake_vector_query,
        repair_purge_outbox_writer=lambda records: writer_batches.append(records),
        limit=5,
        required_projection_commit_id='projection-1',
        required_account_generation=0,
    )

    assert [item['memory_id'] for item in response['items']] == ['valid']
    assert response['repair_purge_candidates'] == []
    assert response['repair_purge_outbox_records'] == []
    assert writer_batches == []

    try:
        fetch_default_v17_vector_memory_search(
            uid='u1',
            query='coffee',
            db_client=db_client,
            policy=MemoryAccessPolicy.for_omi_chat(),
            vector_query=fake_vector_query,
            repair_purge_outbox_writer=lambda records: writer_batches.append(records),
            limit=5,
            required_projection_commit_id=None,
            required_account_generation=0,
        )
    except ValueError as exc:
        assert str(exc) == 'required_projection_commit_id is required'
    else:
        raise AssertionError('expected missing projection fence to fail closed')

    assert len(vector_calls) == 1
    assert writer_batches == []


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
        required_account_generation=0,
    )

    assert [item['memory_id'] for item in response['items']] == ['older-higher-score', 'newer-lower-score']
