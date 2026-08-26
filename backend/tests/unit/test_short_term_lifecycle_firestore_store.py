from datetime import datetime, timedelta, timezone

import pytest

from jobs.short_term_lifecycle_worker import (
    FirestoreShortTermLifecycleTransitionStore,
    ShortTermLifecycleTransitionRecord,
    fetch_expired_short_term_memory_items_firestore,
    fetch_expiry_urgent_short_term_memory_items_firestore,
    run_short_term_lifecycle_firestore,
)
from models.memory_evidence import ArtifactPreservationState, MemoryEvidence, SourceState
from models.product_memory import MemoryItemStatus, MemoryTier, ProcessingState, MemoryItem
from utils.memory.short_term_lifecycle import DEFAULT_SHORT_TERM_TTL_DAYS


class _Snapshot:
    def __init__(self, data=None):
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        return dict(self._data or {})


class _DocumentRef:
    def __init__(self, db_client, path):
        self._db_client = db_client
        self.path = path

    def get(self, transaction=None):
        return _Snapshot(self._db_client.docs.get(self.path))


class _CollectionRef:
    def __init__(
        self,
        db_client,
        path,
        filters=None,
        limit_count=None,
        order_fields=None,
        collection_group=False,
        selected_fields=None,
    ):
        self._db_client = db_client
        self.path = path
        self._filters = list(filters or [])
        self._limit_count = limit_count
        self._order_fields = list(order_fields or [])
        self._collection_group = collection_group
        self._selected_fields = tuple(selected_fields) if selected_fields is not None else None

    def where(self, field_path=None, op_string=None, value=None, *, filter=None):
        if filter is not None:
            field_path = filter.field_path
            op_string = filter.op_string
            value = filter.value
        assert field_path is not None
        assert op_string is not None
        return _CollectionRef(
            self._db_client,
            self.path,
            [*self._filters, (field_path, op_string, value)],
            limit_count=self._limit_count,
            order_fields=self._order_fields,
            collection_group=self._collection_group,
            selected_fields=self._selected_fields,
        )

    def select(self, field_paths):
        return _CollectionRef(
            self._db_client,
            self.path,
            self._filters,
            limit_count=self._limit_count,
            order_fields=self._order_fields,
            collection_group=self._collection_group,
            selected_fields=field_paths,
        )

    def order_by(self, field_path):
        return _CollectionRef(
            self._db_client,
            self.path,
            self._filters,
            limit_count=self._limit_count,
            order_fields=[*self._order_fields, field_path],
            collection_group=self._collection_group,
            selected_fields=self._selected_fields,
        )

    def limit(self, limit_count):
        return _CollectionRef(
            self._db_client,
            self.path,
            self._filters,
            limit_count=limit_count,
            order_fields=self._order_fields,
            collection_group=self._collection_group,
            selected_fields=self._selected_fields,
        )

    def stream(self):
        snapshots = []
        for path, data in sorted(self._db_client.docs.items()):
            if self._collection_group:
                parts = path.split('/')
                if len(parts) != 4 or parts[-2] != self.path:
                    continue
            else:
                prefix = f'{self.path}/'
                if not path.startswith(prefix) or '/' in path[len(prefix) :]:
                    continue
            if all(self._matches(data, field_path, op_string, value) for field_path, op_string, value in self._filters):
                selected = (
                    {field: data.get(field) for field in self._selected_fields}
                    if self._selected_fields is not None
                    else data
                )
                snapshots.append(_Snapshot(selected))
        for field_path in reversed(self._order_fields):
            snapshots.sort(key=lambda snapshot: self._nested_value(snapshot.to_dict(), field_path))
        if self._limit_count is not None:
            snapshots = snapshots[: self._limit_count]
        self._db_client.stream_limits.append(self._limit_count)
        self._db_client.streamed_snapshot_counts.append(len(snapshots))
        self._db_client.stream_filters.append(self._filters)
        self._db_client.stream_order_fields.append(self._order_fields)
        self._db_client.stream_selected_fields.append(self._selected_fields)
        return snapshots

    @staticmethod
    def _nested_value(data, field_path):
        value = data
        for part in field_path.split('.'):
            if not isinstance(value, dict):
                return None
            value = value.get(part)
        return value

    def _matches(self, data, field_path, op_string, value):
        actual = self._nested_value(data, field_path)
        if op_string == '==':
            return actual == value
        if op_string == 'in':
            return actual in value
        if op_string == '<=':
            if isinstance(actual, str) and isinstance(value, datetime):
                value = value.isoformat()
            return actual is not None and actual <= value
        raise AssertionError(f'unexpected query operator {op_string}')


class _Transaction:
    def __init__(self, db_client):
        self._db_client = db_client
        self._read_only = False
        self._max_attempts = 1
        self._id = None
        self._sets = []

    def set(self, document_ref, payload):
        self._sets.append((document_ref.path, dict(payload)))

    def _begin(self, retry_id=None):
        self._id = retry_id or 'txn-1'
        self._sets = []

    def _commit(self):
        for path, payload in self._sets:
            self._db_client.docs[path] = payload
        self._sets = []

    def _rollback(self):
        self._sets = []
        self._id = None

    def _clean_up(self):
        self._id = None


class _FirestoreFake:
    def __init__(self):
        self.docs = {}
        self.stream_limits = []
        self.streamed_snapshot_counts = []
        self.stream_filters = []
        self.stream_order_fields = []
        self.stream_selected_fields = []

    def transaction(self):
        return _Transaction(self)

    def document(self, path):
        return _DocumentRef(self, path)

    def collection(self, path):
        return _CollectionRef(self, path)

    def collection_group(self, collection_id):
        return _CollectionRef(self, collection_id, collection_group=True)


def _record(**overrides):
    data = {
        'uid': 'u1',
        'memory_item_id': 'stale-short-term',
        'outcome': 'remain_short_term',
        'reason': 'short_term_expired_requires_lifecycle_decision',
        'run_id': 'lifecycle-run-1',
        'evaluated_at': '2026-06-19T12:00:00+00:00',
        'audit_metadata': {
            'policy_version': 'short_term_lifecycle_v1',
            'source_refs': [
                {
                    'evidence_id': 'ev1',
                    'source_id': 'conversation-1',
                    'source_type': 'conversation',
                    'source_version': 'v1',
                    'source_state': 'active',
                }
            ],
            'default_access_allowed': False,
            'requires_lifecycle_decision': True,
        },
        'idempotency_key': 'short-term-lifecycle:u1:stale-short-term:remain_short_term:abc',
        'fingerprint': 'f' * 64,
    }
    data.update(overrides)
    return ShortTermLifecycleTransitionRecord(**data)


def _evidence(source_id='conv1'):
    return MemoryEvidence(
        evidence_id=f'ev-{source_id}',
        source_id=source_id,
        source_type='conversation',
        source_version='v1',
        quote_refs=[{'text': 'User prefers concise lifecycle audits.'}],
        content_hash='hash1',
        source_state=SourceState.active,
        artifact_preservation=ArtifactPreservationState.preserved,
    )


def _memory_item(memory_id: str, *, tier=MemoryTier.short_term, captured_at=None, **overrides) -> MemoryItem:
    captured_at = captured_at or datetime(2026, 6, 18, 12, 0, tzinfo=timezone.utc)
    data = {
        'memory_id': memory_id,
        'uid': 'u1',
        'version': 1,
        'tier': tier,
        'status': MemoryItemStatus.active,
        'processing_state': ProcessingState.processed,
        'content': f'{memory_id} content',
        'evidence': [_evidence(f'{memory_id}-source')],
        'source_state': SourceState.active,
        'sensitivity_labels': [],
        'visibility': 'private',
        'user_asserted': False,
        'captured_at': captured_at,
        'updated_at': captured_at,
        'expires_at': (
            captured_at + timedelta(days=DEFAULT_SHORT_TERM_TTL_DAYS) if tier == MemoryTier.short_term else None
        ),
        'ledger_commit_id': 'commit-1' if tier == MemoryTier.long_term else None,
        'ledger_sequence': 1 if tier == MemoryTier.long_term else None,
    }
    data.update(overrides)
    return MemoryItem(**data)


def _stored_item(item: MemoryItem):
    return item.model_dump(mode='json')


def test_firestore_lifecycle_transition_store_creates_deterministic_idempotent_record():
    db_client = _FirestoreFake()
    store = FirestoreShortTermLifecycleTransitionStore(
        db_client=db_client,
        now=datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc),
    )
    record = _record()

    first = store.persist_short_term_lifecycle_transition(record)
    second = store.persist_short_term_lifecycle_transition(record)

    assert first.created is True
    assert second.created is False
    assert second.record == record
    assert len(db_client.docs) == 1
    [(path, payload)] = list(db_client.docs.items())
    assert path.startswith('users/u1/short_term_lifecycle_transitions/stl_')
    assert payload['uid'] == 'u1'
    assert payload['memory_item_id'] == 'stale-short-term'
    assert payload['outcome'] == 'remain_short_term'
    assert payload['reason'] == 'short_term_expired_requires_lifecycle_decision'
    assert payload['run_id'] == 'lifecycle-run-1'
    assert payload['source_refs'] == record.audit_metadata['source_refs']
    assert payload['audit_metadata'] == record.audit_metadata
    assert payload['idempotency_key'] == record.idempotency_key
    assert payload['fingerprint'] == record.fingerprint
    assert payload['default_access_allowed'] is False
    assert payload['archive_default_visible'] is False
    assert payload['created_at'] == datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc).isoformat()


def test_firestore_lifecycle_transition_store_rejects_same_key_different_fingerprint():
    db_client = _FirestoreFake()
    store = FirestoreShortTermLifecycleTransitionStore(
        db_client=db_client,
        now=datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc),
    )
    record = _record()
    store.persist_short_term_lifecycle_transition(record)

    with pytest.raises(ValueError, match='idempotency key payload mismatch'):
        store.persist_short_term_lifecycle_transition(_record(fingerprint='e' * 64))

    assert len(db_client.docs) == 1
    [payload] = db_client.docs.values()
    assert payload['fingerprint'] == record.fingerprint


def test_fetch_expired_short_term_memory_items_firestore_queries_terminal_eligible_rows_only():
    db_client = _FirestoreFake()
    now = datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc)
    stale_short_term = _memory_item('stale-short-term', captured_at=datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc))
    fresh_short_term = _memory_item('fresh-short-term')
    archive = _memory_item('archive', tier=MemoryTier.archive)
    long_term = _memory_item('long-term', tier=MemoryTier.long_term)
    db_client.docs = {
        f'users/u1/memory_items/{stale_short_term.memory_id}': _stored_item(stale_short_term),
        f'users/u1/memory_items/{fresh_short_term.memory_id}': _stored_item(fresh_short_term),
        f'users/u1/memory_items/{archive.memory_id}': _stored_item(archive),
        f'users/u1/memory_items/{long_term.memory_id}': _stored_item(long_term),
    }

    items = fetch_expired_short_term_memory_items_firestore(uid='u1', db_client=db_client, now=now)

    assert [item.memory_id for item in items] == ['stale-short-term']
    assert all(item.tier == MemoryTier.short_term for item in items)
    assert db_client.stream_order_fields == [['expires_at', 'memory_id'], ['captured_at', 'memory_id']]
    assert ('status', '==', MemoryItemStatus.active.value) in db_client.stream_filters[0]
    assert ('processing_state', '==', ProcessingState.processed.value) in db_client.stream_filters[0]
    assert ('processing_state', '==', ProcessingState.processed.value) in db_client.stream_filters[1]


def test_fetch_expired_short_term_memory_items_firestore_applies_bounded_limit_before_runner_persistence():
    db_client = _FirestoreFake()
    now = datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc)
    stale_a = _memory_item('a-stale-short-term', captured_at=now - timedelta(days=45))
    stale_b = _memory_item('b-stale-short-term', captured_at=now - timedelta(days=45))
    db_client.docs = {
        f'users/u1/memory_items/{stale_a.memory_id}': _stored_item(stale_a),
        f'users/u1/memory_items/{stale_b.memory_id}': _stored_item(stale_b),
    }

    report = run_short_term_lifecycle_firestore(uid='u1', db_client=db_client, now=now, run_id='runner-1', limit=1)

    transition_docs = {
        path: payload
        for path, payload in db_client.docs.items()
        if path.startswith('users/u1/short_term_lifecycle_transitions/')
    }
    assert report.created_count == 1
    assert db_client.stream_limits == [1, 1]
    assert db_client.streamed_snapshot_counts == [1, 1]
    assert len(transition_docs) == 1
    [payload] = transition_docs.values()
    assert payload['memory_item_id'] == 'a-stale-short-term'
    assert payload['default_access_allowed'] is False
    assert payload['archive_default_visible'] is False


def test_fetch_expiry_urgent_short_term_items_is_global_policy_ordered_and_bounded():
    db_client = _FirestoreFake()
    now = datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc)
    deadline = now + timedelta(hours=24)
    earliest = _memory_item(
        'earliest',
        captured_at=now - timedelta(hours=36),
        uid='u2',
        expires_at=now + timedelta(hours=4),
    )
    legacy_policy_expiry = _memory_item(
        'legacy-policy-expiry',
        captured_at=now - timedelta(hours=25),
        expires_at=now + timedelta(days=29),
    )
    not_urgent = _memory_item('not-urgent', captured_at=now - timedelta(hours=1))
    blocked_with_terminal_review = _memory_item(
        'blocked-with-terminal-review',
        captured_at=now - timedelta(hours=40),
        processing_state=ProcessingState.blocked,
        promotion={'route': 'review'},
    )
    db_client.docs = {
        f'users/{item.uid}/memory_items/{item.memory_id}': _stored_item(item)
        for item in (not_urgent, blocked_with_terminal_review, legacy_policy_expiry, earliest)
    }

    items = fetch_expiry_urgent_short_term_memory_items_firestore(
        db_client=db_client,
        deadline=deadline,
        limit=2,
    )

    assert [(item.uid, item.memory_id) for item in items] == [
        ('u2', 'earliest'),
        ('u1', 'legacy-policy-expiry'),
    ]
    assert db_client.stream_order_fields == [['expires_at', 'memory_id'], ['captured_at', 'memory_id']]
    assert db_client.stream_selected_fields == [
        ('uid', 'memory_id', 'tier', 'status', 'processing_state', 'captured_at', 'expires_at'),
        ('uid', 'memory_id', 'tier', 'status', 'processing_state', 'captured_at', 'expires_at'),
    ]
    assert all(
        ('processing_state', 'in', [ProcessingState.pending.value, ProcessingState.processed.value]) in filters
        for filters in db_client.stream_filters
    )
    assert all(limit == 2 for limit in db_client.stream_limits)


def test_ineligible_earlier_ids_cannot_starve_expired_short_term_work_at_the_query_cap():
    db_client = _FirestoreFake()
    now = datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc)
    ineligible = [
        _memory_item(
            f'a-ineligible-{index:03d}',
            captured_at=now - timedelta(days=60, minutes=index),
            status=MemoryItemStatus.superseded,
        )
        for index in range(251)
    ]
    eligible = _memory_item('z-eligible-expired', captured_at=now - timedelta(days=45))
    db_client.docs = {f'users/u1/memory_items/{item.memory_id}': _stored_item(item) for item in [*ineligible, eligible]}

    items = fetch_expired_short_term_memory_items_firestore(
        uid='u1',
        db_client=db_client,
        now=now,
    )

    assert [item.memory_id for item in items] == ['z-eligible-expired']
    assert db_client.stream_limits == [250, 250]
    assert db_client.streamed_snapshot_counts == [1, 1]


def test_fetch_expired_includes_legacy_stamps_past_the_48_hour_policy() -> None:
    db_client = _FirestoreFake()
    now = datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc)
    policy_expired = _memory_item(
        'legacy-policy-expired',
        captured_at=now - timedelta(hours=49),
        expires_at=now + timedelta(days=28),
    )
    still_fresh = _memory_item(
        'legacy-still-fresh',
        captured_at=now - timedelta(hours=12),
        expires_at=now + timedelta(days=29),
    )
    db_client.docs = {
        f'users/u1/memory_items/{policy_expired.memory_id}': _stored_item(policy_expired),
        f'users/u1/memory_items/{still_fresh.memory_id}': _stored_item(still_fresh),
    }

    items = fetch_expired_short_term_memory_items_firestore(uid='u1', db_client=db_client, now=now)

    assert [item.memory_id for item in items] == ['legacy-policy-expired']


def test_concrete_firestore_lifecycle_runner_persists_only_required_short_term_transitions_idempotently():
    db_client = _FirestoreFake()
    now = datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc)
    stale_short_term = _memory_item('stale-short-term', captured_at=now - timedelta(days=45))
    fresh_short_term = _memory_item('fresh-short-term', captured_at=now - timedelta(days=1))
    archive = _memory_item('archive', tier=MemoryTier.archive)
    db_client.docs = {
        f'users/u1/memory_items/{stale_short_term.memory_id}': _stored_item(stale_short_term),
        f'users/u1/memory_items/{fresh_short_term.memory_id}': _stored_item(fresh_short_term),
        f'users/u1/memory_items/{archive.memory_id}': _stored_item(archive),
    }

    first = run_short_term_lifecycle_firestore(uid='u1', db_client=db_client, now=now, run_id='runner-1')
    second = run_short_term_lifecycle_firestore(uid='u1', db_client=db_client, now=now, run_id='runner-1')

    transition_docs = {
        path: payload
        for path, payload in db_client.docs.items()
        if path.startswith('users/u1/short_term_lifecycle_transitions/')
    }
    assert first.created_count == 1
    assert first.existing_count == 0
    assert first.skipped_memory_ids == []
    assert second.created_count == 0
    assert second.existing_count == 1
    assert second.skipped_memory_ids == []
    assert len(transition_docs) == 1
    [payload] = transition_docs.values()
    assert payload['memory_item_id'] == 'stale-short-term'
    assert payload['outcome'] == 'remain_short_term'
    assert payload['default_access_allowed'] is False
    assert payload['archive_default_visible'] is False
