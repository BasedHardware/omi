from datetime import datetime, timedelta, timezone

from models.memory_evidence import ArtifactPreservationState, MemoryEvidence, SourceState
from models.memory_search_gateway import SearchMode, SearchVectorHit, VectorRepairPurgeReason
from models.product_memory import MemoryAccessPolicy, MemoryItemStatus, MemoryTier, ProcessingState, MemoryItem
from database.memory_vector_repair_outbox import (
    build_vector_repair_purge_outbox_records,
    write_vector_repair_purge_outbox_records,
)
from utils.memory.vector_search_service import fetch_default_vector_memory_search
from utils.memory.vector_search_telemetry import VectorSearchTelemetryConfig


class _Snapshot:
    def __init__(self, data=None):
        self._data = data

    def to_dict(self):
        return dict(self._data or {})

    @property
    def exists(self):
        return self._data is not None


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
        self.document_paths = []
        self.set_paths = []

    def collection(self, path):
        self.collection_paths.append(path)
        return _CollectionRef(self, path)

    def document(self, path):
        self.document_paths.append(path)
        return _DocumentRef(self, path)


class _DocumentRef:
    def __init__(self, db_client, path):
        self._db_client = db_client
        self.path = path

    def set(self, data):
        self._db_client.set_paths.append(self.path)
        self._db_client.docs[self.path] = dict(data)

    def get(self):
        return _Snapshot(self._db_client.docs.get(self.path))


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
    return MemoryItem(**data)


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


def test_default_memory_vector_search_hydrates_authoritative_items_and_filters_stale_short_term_and_archive():
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

    response = fetch_default_vector_memory_search(
        uid='u1',
        query='coffee',
        db_client=db_client,
        policy=MemoryAccessPolicy.for_omi_chat(),
        vector_query=fake_vector_query,
        limit=10,
        required_projection_commit_id='projection-1',
        required_account_generation=0,
    )

    assert vector_calls == [{'uid': 'u1', 'query': 'coffee', 'mode': SearchMode.default, 'limit': 30}]
    assert db_client.collection_paths == []
    assert set(db_client.document_paths) == {
        'users/u1/memory_items/stale-short-term',
        'users/u1/memory_items/archive',
        'users/u1/memory_items/long-term',
        'users/u1/memory_items/fresh-short-term',
    }
    assert [item['memory_id'] for item in response['items']] == ['long-term', 'fresh-short-term']
    assert response['scores_by_memory_id'] == {'long-term': 0.9, 'fresh-short-term': 0.8}
    assert response['decisions']['stale-short-term'] == 'access_denied'
    assert response['decisions']['archive'] == 'access_denied'
    assert response['vector_rejected_count'] == 2
    assert response['archive_default_visible'] is False


def test_default_memory_vector_search_rejects_missing_freshness_fence_before_vector_query_or_repair_callback():
    vector_calls = []
    repair_batches = []

    def fake_vector_query(uid, query, *, mode, limit):
        vector_calls.append({'uid': uid, 'query': query, 'mode': mode, 'limit': limit})
        return _VectorCandidateResult(hits=[], rejected_count=0)

    try:
        fetch_default_vector_memory_search(
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


def test_default_memory_vector_search_rejects_hits_missing_mandatory_freshness_fence_fields():
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

    response = fetch_default_vector_memory_search(
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


def test_default_memory_vector_search_rejects_vectors_from_purged_account_generation_even_when_item_matches_hit():
    now = datetime.now(timezone.utc)
    stale_generation_item = _memory_item('stale-generation', tier=MemoryTier.long_term, now=now, account_generation=2)
    db_client = _FirestoreFake(
        {f'users/u1/memory_items/{stale_generation_item.memory_id}': _stored_item(stale_generation_item)}
    )

    def fake_vector_query(uid, query, *, mode, limit):
        return _VectorCandidateResult(hits=[_hit(stale_generation_item, score=0.99)], rejected_count=0)

    response = fetch_default_vector_memory_search(
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


def test_default_memory_vector_search_dispatches_repair_purge_candidates_for_hydration_rejects():
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
                _hit(missing_authoritative, score=0.99, vector_id='memvec:missing-authoritative'),
                _hit(
                    stale_projection,
                    score=0.98,
                    vector_id='memvec:stale-projection',
                    projection_commit_id='projection-old',
                ),
                _hit(missing_metadata, score=0.97, vector_id='memvec:missing-metadata', uid=None),
                _hit(old_generation, score=0.96, vector_id='memvec:old-generation'),
                _hit(valid, score=0.95, vector_id='memvec:valid'),
            ],
            rejected_count=0,
        )

    response = fetch_default_vector_memory_search(
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
        ('memvec:missing-authoritative', 'missing-authoritative', VectorRepairPurgeReason.missing_authoritative_item),
        ('memvec:stale-projection', 'stale-projection', VectorRepairPurgeReason.stale_projection_commit),
        ('memvec:missing-metadata', 'missing-metadata', VectorRepairPurgeReason.missing_vector_freshness_metadata),
        ('memvec:old-generation', 'old-generation', VectorRepairPurgeReason.stale_account_generation),
    ]
    assert 'valid' not in {candidate['memory_id'] for candidate in repair_batches[0]}


def test_default_memory_vector_search_writes_deterministic_repair_purge_outbox_records_once():
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
                    vector_id='memvec:stale-projection',
                    projection_commit_id='projection-old',
                ),
                _hit(valid, score=0.95, vector_id='memvec:valid'),
            ],
            rejected_count=0,
        )

    response = fetch_default_vector_memory_search(
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
    assert record['record_id'].startswith('memvrp_')
    assert record['idempotency_key'] == record['record_id']
    assert record['uid'] == 'u1'
    assert record['event_type'] == 'vector_repair_purge'
    assert record['status'] == 'pending'
    assert record['vector_id'] == 'memvec:stale-projection'
    assert record['memory_id'] == 'stale-projection'
    assert record['reason'] == VectorRepairPurgeReason.stale_projection_commit
    assert record['required_projection_commit_id'] == 'projection-1'
    assert record['observed_projection_commit_id'] == 'projection-old'
    assert record['required_account_generation'] == 0
    assert record['outbox_path'] == f"users/u1/memory_outbox/{record['record_id']}"

    rebuilt = build_vector_repair_purge_outbox_records(uid='u1', candidates=response['repair_purge_candidates'])
    assert [record['record_id'] for record in rebuilt] == [record['record_id']]


def test_memory_vector_repair_purge_outbox_persistence_sets_stable_user_outbox_path_idempotently():
    candidate = {
        'vector_id': 'memvec:stale-projection',
        'memory_id': 'stale-projection',
        'reason': VectorRepairPurgeReason.stale_projection_commit,
        'required_projection_commit_id': 'projection-1',
        'observed_projection_commit_id': 'projection-old',
        'required_account_generation': 3,
    }
    records = build_vector_repair_purge_outbox_records(uid='u1', candidates=[candidate])
    db_client = _FirestoreFake()

    first_write = write_vector_repair_purge_outbox_records(db_client=db_client, records=records)
    second_write = write_vector_repair_purge_outbox_records(db_client=db_client, records=records)

    record = records[0]
    expected_path = f"users/u1/memory_outbox/{record['record_id']}"
    assert first_write == records
    assert second_write == records
    assert record['outbox_path'] == expected_path
    assert db_client.document_paths == [expected_path, expected_path]
    assert db_client.set_paths == [expected_path, expected_path]
    assert db_client.docs[expected_path]['record_id'] == record['record_id']
    assert db_client.docs[expected_path]['idempotency_key'] == record['record_id']


def test_default_memory_vector_search_does_not_write_outbox_for_no_candidates_or_missing_fence():
    now = datetime.now(timezone.utc)
    valid = _memory_item('valid', tier=MemoryTier.long_term, now=now)
    db_client = _FirestoreFake({f'users/u1/memory_items/{valid.memory_id}': _stored_item(valid)})
    writer_batches = []
    vector_calls = []

    def fake_vector_query(uid, query, *, mode, limit):
        vector_calls.append({'uid': uid, 'query': query, 'mode': mode, 'limit': limit})
        return _VectorCandidateResult(hits=[_hit(valid, score=0.95, vector_id='memvec:valid')], rejected_count=0)

    response = fetch_default_vector_memory_search(
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
        fetch_default_vector_memory_search(
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


def test_default_memory_vector_search_preserves_vector_ranking_after_authoritative_filtering():
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

    response = fetch_default_vector_memory_search(
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


def test_default_memory_vector_search_overfetches_and_refills_when_early_candidates_are_rejected():
    now = datetime.now(timezone.utc)
    stale_short_term = _memory_item(
        'stale-short-term',
        now=now,
        captured_at=now - timedelta(days=45),
        content='coffee stale short term',
    )
    archive = _memory_item('archive', tier=MemoryTier.archive, now=now, content='coffee archived memory')
    missing_authoritative = _memory_item('missing-authoritative', tier=MemoryTier.long_term, now=now)
    valid_one = _memory_item('valid-one', tier=MemoryTier.long_term, now=now, content='coffee valid one')
    valid_two = _memory_item('valid-two', tier=MemoryTier.long_term, now=now, content='coffee valid two')
    valid_three = _memory_item('valid-three', tier=MemoryTier.long_term, now=now, content='coffee valid three')
    ranked_hits = [
        _hit(stale_short_term, score=0.99, vector_id='memvec:stale-short-term'),
        _hit(archive, score=0.98, vector_id='memvec:archive'),
        _hit(missing_authoritative, score=0.97, vector_id='memvec:missing-authoritative'),
        _hit(valid_one, score=0.96, vector_id='memvec:valid-one'),
        _hit(valid_two, score=0.95, vector_id='memvec:valid-two'),
        _hit(valid_three, score=0.94, vector_id='memvec:valid-three'),
    ]
    db_client = _FirestoreFake(
        {
            f'users/u1/memory_items/{item.memory_id}': _stored_item(item)
            for item in [stale_short_term, archive, valid_one, valid_two, valid_three]
        }
    )
    vector_limits = []

    def fake_vector_query(uid, query, *, mode, limit):
        vector_limits.append(limit)
        return _VectorCandidateResult(hits=ranked_hits[:limit], rejected_count=0)

    response = fetch_default_vector_memory_search(
        uid='u1',
        query='coffee',
        db_client=db_client,
        policy=MemoryAccessPolicy.for_omi_chat(),
        vector_query=fake_vector_query,
        limit=3,
        overfetch_factor=1,
        max_candidates=6,
        required_projection_commit_id='projection-1',
        required_account_generation=0,
    )

    assert vector_limits == [3, 6]
    assert [item['memory_id'] for item in response['items']] == ['valid-one', 'valid-two', 'valid-three']
    assert response['limit'] == 3
    assert response['candidate_request_limit'] == 6
    assert response['candidate_budget'] == 6
    assert response['vector_query_count'] == 2
    assert response['queried_candidate_count'] == 6
    assert response['hydrated_candidate_count'] == 5
    assert response['hydration_rejected_missing_count'] == 1
    assert response['hydration_rejected_access_denied_count'] == 2
    assert response['returned_count'] == 3
    assert set(db_client.document_paths) == {
        'users/u1/memory_items/stale-short-term',
        'users/u1/memory_items/archive',
        'users/u1/memory_items/missing-authoritative',
        'users/u1/memory_items/valid-one',
        'users/u1/memory_items/valid-two',
        'users/u1/memory_items/valid-three',
    }
    assert db_client.collection_paths == []


def test_default_memory_vector_search_stops_at_candidate_budget_without_unbounded_refill_or_reads():
    now = datetime.now(timezone.utc)
    stale_short_term = _memory_item(
        'stale-short-term',
        now=now,
        captured_at=now - timedelta(days=45),
        content='coffee stale short term',
    )
    archive = _memory_item('archive', tier=MemoryTier.archive, now=now, content='coffee archived memory')
    valid_one = _memory_item('valid-one', tier=MemoryTier.long_term, now=now, content='coffee valid one')
    valid_two = _memory_item('valid-two', tier=MemoryTier.long_term, now=now, content='coffee valid two')
    ranked_hits = [
        _hit(stale_short_term, score=0.99, vector_id='memvec:stale-short-term'),
        _hit(archive, score=0.98, vector_id='memvec:archive'),
        _hit(valid_one, score=0.97, vector_id='memvec:valid-one'),
        _hit(valid_two, score=0.96, vector_id='memvec:valid-two'),
    ]
    db_client = _FirestoreFake(
        {
            f'users/u1/memory_items/{item.memory_id}': _stored_item(item)
            for item in [stale_short_term, archive, valid_one, valid_two]
        }
    )
    vector_limits = []

    def fake_vector_query(uid, query, *, mode, limit):
        vector_limits.append(limit)
        return _VectorCandidateResult(hits=ranked_hits[:limit], rejected_count=0)

    response = fetch_default_vector_memory_search(
        uid='u1',
        query='coffee',
        db_client=db_client,
        policy=MemoryAccessPolicy.for_omi_chat(),
        vector_query=fake_vector_query,
        limit=3,
        overfetch_factor=1,
        max_candidates=4,
        required_projection_commit_id='projection-1',
        required_account_generation=0,
    )

    assert vector_limits == [3, 4]
    assert [item['memory_id'] for item in response['items']] == ['valid-one', 'valid-two']
    assert response['returned_count'] == 2
    assert response['candidate_budget_exhausted'] is True
    assert response['candidate_budget'] == 4
    assert response['candidate_request_limit'] == 4
    assert response['queried_candidate_count'] == 4
    assert len(db_client.document_paths) == 4
    assert db_client.collection_paths == []


def test_default_memory_vector_search_emits_low_cardinality_telemetry_without_identifiers():
    now = datetime.now(timezone.utc)
    stale_short_term = _memory_item('stale-short-term', now=now, captured_at=now - timedelta(days=45))
    archive = _memory_item('archive', tier=MemoryTier.archive, now=now)
    valid = _memory_item('valid', tier=MemoryTier.long_term, now=now)
    db_client = _FirestoreFake(
        {f'users/u1/memory_items/{item.memory_id}': _stored_item(item) for item in [stale_short_term, archive, valid]}
    )
    emitted = []

    def fake_vector_query(uid, query, *, mode, limit):
        return _VectorCandidateResult(
            hits=[
                _hit(stale_short_term, score=0.99, vector_id='memvec:stale-short-term'),
                _hit(archive, score=0.98, vector_id='memvec:archive'),
                _hit(valid, score=0.97, vector_id='memvec:valid'),
            ],
            rejected_count=7,
        )

    response = fetch_default_vector_memory_search(
        uid='u1',
        query='coffee raw query text',
        db_client=db_client,
        policy=MemoryAccessPolicy.for_omi_chat(),
        vector_query=fake_vector_query,
        telemetry_emitter=lambda payload: emitted.append(payload),
        telemetry_config=VectorSearchTelemetryConfig(enabled=True),
        limit=3,
        overfetch_factor=1,
        max_candidates=3,
        required_projection_commit_id='projection-1',
        required_account_generation=0,
    )

    assert response['telemetry'] == {'enabled': True, 'emitted_count': len(emitted), 'failed_count': 0, 'errors': []}
    metric_names = {payload['name'] for payload in emitted if payload['kind'] == 'metric'}
    assert {
        'vector_search_candidates_total',
        'vector_search_hydration_rejects_total',
        'vector_search_result_count',
        'vector_search_empty_after_hydration_total',
        'vector_search_budget_exhausted_total',
    }.issubset(metric_names)
    rendered = repr(emitted)
    for forbidden in {
        'u1',
        'coffee raw query text',
        'stale-short-term',
        'archive',
        'valid',
        'memvec:stale-short-term',
    }:
        assert forbidden not in rendered
    for payload in emitted:
        assert set(payload['labels']).issubset(
            {'component', 'consumer', 'surface', 'mode', 'status', 'reason', 'event_type'}
        )


def test_default_memory_vector_search_telemetry_failure_is_recorded_without_masking_results():
    now = datetime.now(timezone.utc)
    valid = _memory_item('valid', tier=MemoryTier.long_term, now=now)
    db_client = _FirestoreFake({f'users/u1/memory_items/{valid.memory_id}': _stored_item(valid)})

    def fake_vector_query(uid, query, *, mode, limit):
        return _VectorCandidateResult(hits=[_hit(valid, score=0.95, vector_id='memvec:valid')], rejected_count=0)

    def failing_emitter(payload):
        raise RuntimeError(f"central telemetry unavailable for {payload['name']}")

    response = fetch_default_vector_memory_search(
        uid='u1',
        query='coffee',
        db_client=db_client,
        policy=MemoryAccessPolicy.for_omi_chat(),
        vector_query=fake_vector_query,
        telemetry_emitter=failing_emitter,
        telemetry_config=VectorSearchTelemetryConfig(enabled=True),
        limit=3,
        required_projection_commit_id='projection-1',
        required_account_generation=0,
    )

    assert [item['memory_id'] for item in response['items']] == ['valid']
    assert response['telemetry']['enabled'] is True
    assert response['telemetry']['emitted_count'] == 0
    assert response['telemetry']['failed_count'] > 0
    assert response['telemetry']['errors'][0] == {
        'stage': 'telemetry',
        'name': 'vector_search_candidates_total',
        'error': 'central telemetry unavailable for vector_search_candidates_total',
    }


def test_default_memory_vector_search_stops_refill_at_vector_query_budget_and_returns_validated_results():
    now = datetime.now(timezone.utc)
    stale_short_term = _memory_item('stale-short-term', now=now, captured_at=now - timedelta(days=45))
    valid_one = _memory_item('valid-one', tier=MemoryTier.long_term, now=now)
    valid_two = _memory_item('valid-two', tier=MemoryTier.long_term, now=now)
    ranked_hits = [
        _hit(stale_short_term, score=0.99, vector_id='memvec:stale-short-term'),
        _hit(valid_one, score=0.98, vector_id='memvec:valid-one'),
        _hit(valid_two, score=0.97, vector_id='memvec:valid-two'),
    ]
    db_client = _FirestoreFake(
        {
            f'users/u1/memory_items/{item.memory_id}': _stored_item(item)
            for item in [stale_short_term, valid_one, valid_two]
        }
    )
    vector_limits = []

    def fake_vector_query(uid, query, *, mode, limit):
        vector_limits.append(limit)
        return _VectorCandidateResult(hits=ranked_hits[:limit], rejected_count=0)

    response = fetch_default_vector_memory_search(
        uid='u1',
        query='coffee',
        db_client=db_client,
        policy=MemoryAccessPolicy.for_omi_chat(),
        vector_query=fake_vector_query,
        limit=2,
        overfetch_factor=1,
        max_candidates=3,
        max_vector_queries=1,
        required_projection_commit_id='projection-1',
        required_account_generation=0,
    )

    assert vector_limits == [2]
    assert [item['memory_id'] for item in response['items']] == ['valid-one']
    assert response['returned_count'] == 1
    assert response['vector_query_count'] == 1
    assert response['max_vector_queries'] == 1
    assert response['vector_query_budget_exhausted'] is True
    assert response['search_status'] == 'vector_query_budget_exhausted'
    assert response['legacy_fallback_used'] is False
    assert response['archive_default_visible'] is False


def test_default_memory_vector_search_stops_hydration_at_read_budget_without_unbounded_firestore_reads():
    now = datetime.now(timezone.utc)
    valid_one = _memory_item('valid-one', tier=MemoryTier.long_term, now=now)
    valid_two = _memory_item('valid-two', tier=MemoryTier.long_term, now=now)
    valid_three = _memory_item('valid-three', tier=MemoryTier.long_term, now=now)
    db_client = _FirestoreFake(
        {f'users/u1/memory_items/{item.memory_id}': _stored_item(item) for item in [valid_one, valid_two, valid_three]}
    )

    def fake_vector_query(uid, query, *, mode, limit):
        return _VectorCandidateResult(
            hits=[
                _hit(valid_one, score=0.99, vector_id='memvec:valid-one'),
                _hit(valid_two, score=0.98, vector_id='memvec:valid-two'),
                _hit(valid_three, score=0.97, vector_id='memvec:valid-three'),
            ][:limit],
            rejected_count=0,
        )

    response = fetch_default_vector_memory_search(
        uid='u1',
        query='coffee',
        db_client=db_client,
        policy=MemoryAccessPolicy.for_omi_chat(),
        vector_query=fake_vector_query,
        limit=3,
        overfetch_factor=1,
        max_candidates=3,
        max_candidate_hydration_reads=2,
        required_projection_commit_id='projection-1',
        required_account_generation=0,
    )

    assert db_client.document_paths == ['users/u1/memory_items/valid-one', 'users/u1/memory_items/valid-two']
    assert [item['memory_id'] for item in response['items']] == ['valid-one', 'valid-two']
    assert response['hydrated_candidate_count'] == 2
    assert response['candidate_hydration_read_count'] == 2
    assert response['max_candidate_hydration_reads'] == 2
    assert response['hydration_read_budget_exhausted'] is True
    assert response['search_status'] == 'hydration_read_budget_exhausted'
    assert 'valid-three' not in response['decisions']
    assert 'valid-three' not in {candidate['memory_id'] for candidate in response['repair_purge_candidates']}


def test_default_memory_vector_search_uses_injected_clock_to_timeout_before_vector_query_without_sleeping():
    clock_values = iter([10.0, 10.2])
    vector_calls = []

    def fake_clock():
        return next(clock_values)

    def fake_vector_query(uid, query, *, mode, limit):
        vector_calls.append(limit)
        return _VectorCandidateResult(hits=[], rejected_count=0)

    response = fetch_default_vector_memory_search(
        uid='u1',
        query='coffee',
        db_client=_FirestoreFake(),
        policy=MemoryAccessPolicy.for_omi_chat(),
        vector_query=fake_vector_query,
        timeout_seconds=0.1,
        clock=fake_clock,
        limit=3,
        required_projection_commit_id='projection-1',
        required_account_generation=0,
    )

    assert vector_calls == []
    assert response['items'] == []
    assert response['vector_query_count'] == 0
    assert response['timeout_seconds'] == 0.1
    assert response['timeout_exhausted'] is True
    assert response['search_status'] == 'timeout_exhausted'
    assert response['legacy_fallback_used'] is False


def test_default_memory_vector_search_telemetry_includes_bounded_timeout_and_budget_status_without_identifiers():
    clock_values = iter([10.0, 11.0])
    emitted = []

    response = fetch_default_vector_memory_search(
        uid='u1',
        query='coffee raw query text',
        db_client=_FirestoreFake(),
        policy=MemoryAccessPolicy.for_omi_chat(),
        vector_query=lambda uid, query, *, mode, limit: _VectorCandidateResult(hits=[], rejected_count=0),
        telemetry_emitter=lambda payload: emitted.append(payload),
        telemetry_config=VectorSearchTelemetryConfig(enabled=True, consumer='omi_chat', surface='chat'),
        timeout_seconds=0.1,
        clock=lambda: next(clock_values),
        limit=3,
        required_projection_commit_id='projection-1',
        required_account_generation=0,
    )

    assert response['timeout_exhausted'] is True
    metric_names = {payload['name'] for payload in emitted if payload['kind'] == 'metric'}
    event_names = {payload['name'] for payload in emitted if payload['kind'] == 'event'}
    assert 'vector_search_timeout_exhausted_total' in metric_names
    assert 'vector_search_control_exhausted_total' in metric_names
    assert 'vector_search_timeout_exhausted' in event_names
    rendered = repr(emitted)
    for forbidden in {'u1', 'coffee raw query text'}:
        assert forbidden not in rendered
    for payload in emitted:
        assert set(payload['labels']).issubset(
            {'component', 'consumer', 'surface', 'mode', 'status', 'reason', 'event_type'}
        )
