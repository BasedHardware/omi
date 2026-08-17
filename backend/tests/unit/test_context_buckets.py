from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

import database.context_buckets as context_buckets_db
from models.action_item import EvidenceKind, EvidenceRef, EvidenceScope
from models.context_bucket import (
    BucketSubjectKind,
    ContextBucketSync,
    ContextBucketSyncRequest,
    ContextFactSync,
)

NOW = datetime(2026, 8, 16, 12, 0, tzinfo=timezone.utc)


class FakeSnapshot:
    def __init__(self, path, data=None):
        self.path = path
        self.id = path[-1]
        self._data = deepcopy(data)
        self.exists = data is not None
        self.reference = FakeRef(None, path)

    def to_dict(self):
        return deepcopy(self._data)


class FakeRef:
    def __init__(self, database, path):
        self.database = database
        self.path = path
        self.id = path[-1]

    def collection(self, name):
        return FakeCollection(self.database, (*self.path, name))

    def get(self, transaction=None):
        return FakeSnapshot(self.path, self.database.rows.get(self.path))

    def set(self, payload):
        self.database.rows[self.path] = deepcopy(payload)

    def delete(self):
        self.database.rows.pop(self.path, None)


class FakeQuery:
    def __init__(self, database, path, filters=None, order=None, limit_value=None):
        self.database = database
        self.path = path
        self.filters = list(filters or [])
        self.order = order
        self.limit_value = limit_value

    def where(self, filter):
        return FakeQuery(
            self.database,
            self.path,
            [*self.filters, (filter.field_path, filter.op_string, filter.value)],
            self.order,
            self.limit_value,
        )

    def order_by(self, field, direction=None):
        return FakeQuery(self.database, self.path, self.filters, (field, direction), self.limit_value)

    def limit(self, value):
        return FakeQuery(self.database, self.path, self.filters, self.order, value)

    def stream(self, transaction=None):
        rows = []
        expected_length = len(self.path) + 1
        for path, payload in self.database.rows.items():
            if len(path) != expected_length or path[:-1] != self.path:
                continue
            if all(payload.get(field) == value for field, operator, value in self.filters):
                snapshot = FakeSnapshot(path, payload)
                snapshot.reference = FakeRef(self.database, path)
                rows.append(snapshot)
        if self.order is not None:
            field, direction = self.order
            reverse = str(direction).endswith('DESCENDING')
            rows.sort(key=lambda snapshot: snapshot.to_dict().get(field), reverse=reverse)
        return iter(rows[: self.limit_value] if self.limit_value is not None else rows)


class FakeCollection(FakeQuery):
    def document(self, name):
        return FakeRef(self.database, (*self.path, name))


class FakeTransaction:
    def __init__(self, database):
        self.database = database

    def set(self, ref, payload):
        ref.set(payload)

    def delete(self, ref):
        ref.delete()


class FakeBatch:
    def __init__(self, database):
        self.database = database
        self.operations = []

    def set(self, ref, payload):
        self.operations.append(('set', ref, payload))

    def delete(self, ref):
        self.operations.append(('delete', ref, None))

    def commit(self):
        for kind, ref, payload in self.operations:
            if kind == 'set':
                ref.set(payload)
            else:
                ref.delete()
        self.operations = []


class FakeDB:
    def __init__(self):
        self.rows = {}

    def collection(self, name):
        return FakeCollection(self, (name,))

    def batch(self):
        return FakeBatch(self)

    def transaction(self):
        return FakeTransaction(self)


@pytest.fixture
def fake_db(monkeypatch):
    def transactional(function):
        def run(transaction):
            return function(transaction)

        return run

    monkeypatch.setattr(context_buckets_db.firestore, 'transactional', transactional)
    return FakeDB()


def screen_evidence(fact_id: str) -> EvidenceRef:
    return EvidenceRef(
        kind=EvidenceKind.local_screen,
        id=fact_id,
        scope=EvidenceScope.device_local,
        device_id='mac-1',
    )


def build_fact(fact_id: str, *, device_updated_at=NOW, statement='Ship the parity pack', **overrides):
    return ContextFactSync(
        fact_id=fact_id,
        statement=statement,
        identifiers=['parity-pack'],
        confidence=0.9,
        evidence_refs=[screen_evidence(fact_id)],
        device_updated_at=device_updated_at,
        **overrides,
    )


def build_bucket(bucket_id='bucket-1', *, facts=None, device_updated_at=NOW, **overrides):
    return ContextBucketSync(
        bucket_id=bucket_id,
        subject_kind=BucketSubjectKind.document,
        subject_id='design-doc',
        display_label='Design doc',
        device_updated_at=device_updated_at,
        facts=facts if facts is not None else [build_fact('fact-1')],
        **overrides,
    )


def sync(fake_db, buckets, *, generation=3, device_id='mac-1'):
    return context_buckets_db.sync_context_buckets(
        'u1',
        ContextBucketSyncRequest(device_id=device_id, buckets=buckets),
        account_generation=generation,
        firestore_client=fake_db,
    )


def test_sync_persists_buckets_and_facts_readable_by_consumers(fake_db):
    report = sync(fake_db, [build_bucket()])

    assert (report.buckets_written, report.facts_written) == (1, 1)
    buckets = context_buckets_db.list_context_buckets('u1', account_generation=3, firestore_client=fake_db)
    facts = context_buckets_db.list_context_facts('u1', account_generation=3, now=NOW, firestore_client=fake_db)
    assert [bucket.bucket_id for bucket in buckets] == ['bucket-1']
    assert [fact.statement for fact in facts] == ['Ship the parity pack']
    assert facts[0].bucket_id == 'bucket-1'
    assert facts[0].device_id == 'mac-1'


def test_replayed_sync_never_regresses_a_newer_device_write(fake_db):
    later = NOW + timedelta(minutes=5)
    sync(fake_db, [build_bucket(facts=[build_fact('fact-1', statement='Newer', device_updated_at=later)])])

    report = sync(fake_db, [build_bucket(facts=[build_fact('fact-1', statement='Older', device_updated_at=NOW)])])

    assert (report.buckets_skipped_stale, report.facts_skipped_stale) == (1, 1)
    facts = context_buckets_db.list_context_facts('u1', account_generation=3, now=NOW, firestore_client=fake_db)
    assert [fact.statement for fact in facts] == ['Newer']


def test_newer_device_write_replaces_stored_statement(fake_db):
    sync(fake_db, [build_bucket()])
    later = NOW + timedelta(minutes=5)

    sync(
        fake_db,
        [
            build_bucket(
                device_updated_at=later,
                facts=[build_fact('fact-1', statement='Revised', device_updated_at=later)],
            )
        ],
    )

    facts = context_buckets_db.list_context_facts('u1', account_generation=3, now=NOW, firestore_client=fake_db)
    assert [fact.statement for fact in facts] == ['Revised']


def test_reads_are_fenced_by_account_generation(fake_db):
    sync(fake_db, [build_bucket()], generation=3)

    assert context_buckets_db.list_context_buckets('u1', account_generation=4, firestore_client=fake_db) == []
    assert context_buckets_db.list_context_facts('u1', account_generation=4, now=NOW, firestore_client=fake_db) == []


def test_expired_facts_are_withheld_before_collection_runs(fake_db):
    sync(
        fake_db,
        [build_bucket(facts=[build_fact('fact-1', expires_at=NOW - timedelta(minutes=1))])],
    )

    facts = context_buckets_db.list_context_facts('u1', account_generation=3, now=NOW, firestore_client=fake_db)
    assert facts == []


def test_purge_removes_the_bucket_and_every_fact_it_owns(fake_db):
    sync(
        fake_db,
        [
            build_bucket('bucket-1', facts=[build_fact('fact-1'), build_fact('fact-2')]),
            build_bucket('bucket-2', facts=[build_fact('fact-3')]),
        ],
    )

    report = context_buckets_db.purge_context_buckets('u1', ['bucket-1'], firestore_client=fake_db)

    assert (report.buckets_deleted, report.facts_deleted) == (1, 2)
    facts = context_buckets_db.list_context_facts('u1', account_generation=3, now=NOW, firestore_client=fake_db)
    buckets = context_buckets_db.list_context_buckets('u1', account_generation=3, firestore_client=fake_db)
    assert [fact.fact_id for fact in facts] == ['fact-3']
    assert [bucket.bucket_id for bucket in buckets] == ['bucket-2']


def test_canonical_evidence_is_rejected_so_screen_refs_stay_device_local():
    with pytest.raises(ValidationError):
        ContextFactSync(
            fact_id='fact-1',
            statement='Ship the parity pack',
            confidence=0.9,
            device_updated_at=NOW,
            evidence_refs=[
                EvidenceRef(kind=EvidenceKind.conversation, id='conv-1', scope=EvidenceScope.canonical),
            ],
        )


def test_sync_contract_rejects_duplicate_ids():
    with pytest.raises(ValidationError):
        ContextBucketSync(
            bucket_id='bucket-1',
            subject_kind=BucketSubjectKind.app,
            subject_id='app',
            device_updated_at=NOW,
            facts=[build_fact('fact-1'), build_fact('fact-1')],
        )
    with pytest.raises(ValidationError):
        ContextBucketSyncRequest(device_id='mac-1', buckets=[build_bucket('bucket-1'), build_bucket('bucket-1')])
    with pytest.raises(ValidationError):
        ContextBucketSyncRequest(
            device_id='mac-1',
            buckets=[
                build_bucket('bucket-1', facts=[build_fact('fact-1')]),
                build_bucket('bucket-2', facts=[build_fact('fact-1')]),
            ],
        )


def test_generation_change_republishes_rather_than_skipping_as_stale(fake_db):
    """A row stranded at the old generation is invisible, so it must not read as current."""

    sync(fake_db, [build_bucket()], generation=3)

    report = sync(fake_db, [build_bucket()], generation=4)

    assert (report.buckets_skipped_stale, report.facts_skipped_stale) == (0, 0)
    assert (report.buckets_written, report.facts_written) == (1, 1)
    facts = context_buckets_db.list_context_facts('u1', account_generation=4, now=NOW, firestore_client=fake_db)
    buckets = context_buckets_db.list_context_buckets('u1', account_generation=4, firestore_client=fake_db)
    assert [fact.fact_id for fact in facts] == ['fact-1']
    assert [bucket.bucket_id for bucket in buckets] == ['bucket-1']


def test_a_fast_device_clock_cannot_lock_out_later_writes(fake_db):
    far_future = NOW + timedelta(days=365)
    sync(fake_db, [build_bucket(facts=[build_fact('fact-1', statement='Skewed', device_updated_at=far_future)])])

    stored = fake_db.rows[('users', 'u1', 'context_bucket_facts', 'fact-1')]['device_updated_at']
    assert stored <= datetime.now(timezone.utc) + context_buckets_db.MAX_DEVICE_CLOCK_SKEW

    later = datetime.now(timezone.utc) + context_buckets_db.MAX_DEVICE_CLOCK_SKEW + timedelta(minutes=1)
    sync(
        fake_db,
        [
            build_bucket(
                device_updated_at=later,
                facts=[build_fact('fact-1', statement='Recovered', device_updated_at=later)],
            )
        ],
    )

    facts = context_buckets_db.list_context_facts('u1', account_generation=3, now=NOW, firestore_client=fake_db)
    assert [fact.statement for fact in facts] == ['Recovered']


def test_expired_rows_ahead_of_a_live_fact_do_not_starve_it(fake_db):
    """Over-fetching bounds post-query starvation; it does not eliminate it.

    Dead rows inside the over-fetch window can no longer consume the caller's
    budget. More dead rows than that window can still hide a live fact, which is
    why expiry is also collected rather than only filtered.
    """

    dead_count = context_buckets_db.FACT_OVERFETCH_FACTOR - 1
    facts = [build_fact(f'dead-{index}', expires_at=NOW - timedelta(minutes=1)) for index in range(dead_count)]
    facts.append(build_fact('live-1'))
    sync(fake_db, [build_bucket(facts=facts)])

    live = context_buckets_db.list_context_facts('u1', account_generation=3, limit=1, now=NOW, firestore_client=fake_db)

    assert [fact.fact_id for fact in live] == ['live-1']


def test_fact_read_never_exceeds_the_requested_limit(fake_db):
    sync(fake_db, [build_bucket(facts=[build_fact(f'fact-{index}') for index in range(5)])])

    live = context_buckets_db.list_context_facts('u1', account_generation=3, limit=2, now=NOW, firestore_client=fake_db)

    assert len(live) == 2


def test_non_screen_evidence_is_rejected_even_when_device_local():
    with pytest.raises(ValidationError):
        ContextFactSync(
            fact_id='fact-1',
            statement='Ship the parity pack',
            confidence=0.9,
            device_updated_at=NOW,
            evidence_refs=[
                EvidenceRef(
                    kind=EvidenceKind.conversation,
                    id='conv-1',
                    scope=EvidenceScope.device_local,
                    device_id='mac-1',
                )
            ],
        )
