from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

import database.context_buckets as context_buckets_db
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
        if transaction is not None and transaction.has_written:
            raise ReadAfterWriteError(f'read of {self.path} after a write in the same transaction')
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


class ReadAfterWriteError(AssertionError):
    """Firestore rejects a read issued after a write inside a transaction."""


class FakeTransaction:
    """Buffers writes and enforces Firestore's read-before-write rule.

    Writing straight through would make every atomicity assertion vacuous and
    would let a read-after-write ordering bug pass here and fail in production.
    """

    def __init__(self, database):
        self.database = database
        self.has_written = False
        self.pending = []

    def set(self, ref, payload):
        self.has_written = True
        self.pending.append(('set', ref, payload))

    def delete(self, ref):
        self.has_written = True
        self.pending.append(('delete', ref, None))

    def commit(self):
        for kind, ref, payload in self.pending:
            if kind == 'set':
                ref.set(payload)
            else:
                ref.delete()
        self.pending = []


FIRESTORE_MAX_BATCH_OPERATIONS = 500


class BatchTooLargeError(AssertionError):
    """Firestore rejects a commit carrying more than 500 operations."""


class FakeBatch:
    def __init__(self, database):
        self.database = database
        self.operations = []

    def set(self, ref, payload):
        self.operations.append(('set', ref, payload))

    def delete(self, ref):
        self.operations.append(('delete', ref, None))

    def commit(self):
        if len(self.operations) > FIRESTORE_MAX_BATCH_OPERATIONS:
            raise BatchTooLargeError(f'{len(self.operations)} operations in one commit')
        self.database.committed_batch_sizes.append(len(self.operations))
        for kind, ref, payload in self.operations:
            if kind == 'set':
                ref.set(payload)
            else:
                ref.delete()
        self.operations = []


class FakeDB:
    def __init__(self):
        self.rows = {}
        self.committed_batch_sizes = []

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
            result = function(transaction)
            transaction.commit()
            return result

        return run

    monkeypatch.setattr(context_buckets_db.firestore, 'transactional', transactional)
    return FakeDB()


def build_fact(fact_id: str, *, device_updated_at=NOW, statement='Ship the parity pack', **overrides):
    return ContextFactSync(
        fact_id=fact_id,
        statement=statement,
        confidence=0.9,
        device_updated_at=device_updated_at,
        **overrides,
    )


def build_bucket(bucket_id='bucket-1', *, facts=None, device_updated_at=NOW, **overrides):
    return ContextBucketSync(
        bucket_id=bucket_id,
        subject_kind=BucketSubjectKind.document,
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
    facts = context_buckets_db.list_context_facts('u1', account_generation=3, now=NOW, firestore_client=fake_db)
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
    assert [fact.fact_id for fact in facts] == ['fact-3']
    assert ('users', 'u1', 'context_buckets', 'bucket-1') not in fake_db.rows


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
    assert [fact.fact_id for fact in facts] == ['fact-1']
    assert fake_db.rows[('users', 'u1', 'context_buckets', 'bucket-1')]['account_generation'] == 4


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


def test_purge_is_account_wide_and_not_scoped_to_the_calling_device(fake_db):
    """Excluding an app is a privacy action, so it must reach copies from every device.

    Retracting only the caller's rows would leave the same content readable by
    chat and by the user's other devices, which is the opposite of what asking
    to exclude an app means.
    """

    sync(fake_db, [build_bucket('bucket-1', facts=[build_fact('from-mac')])], device_id='macos_one')
    sync(fake_db, [build_bucket('bucket-1', facts=[build_fact('from-other')])], device_id='macos_two')

    report = context_buckets_db.purge_context_buckets('u1', ['bucket-1'], firestore_client=fake_db)

    assert report.buckets_deleted == 1
    assert report.facts_deleted == 2
    assert context_buckets_db.list_context_facts('u1', account_generation=3, now=NOW, firestore_client=fake_db) == []


def seed_facts(fake_db, count, *, prefix, bucket_id='bucket-1', expires_at=None):
    """Seed past the per-request fact cap, which is lower than one Firestore batch."""

    sync(fake_db, [build_bucket(bucket_id, facts=[])], generation=3)
    for index in range(count):
        fake_db.rows[('users', 'u1', 'context_bucket_facts', f'{prefix}-{index}')] = {
            'fact_id': f'{prefix}-{index}',
            'bucket_id': bucket_id,
            'statement': 'Ship the parity pack',
            'identifiers': [],
            'confidence': 0.9,
            'disposition_state': 'open',
            'evidence_refs': [],
            'expires_at': expires_at,
            'device_id': 'mac-1',
            'device_updated_at': NOW,
            'account_generation': 3,
            'created_at': NOW,
            'updated_at': NOW,
        }


def test_purge_of_a_bucket_larger_than_one_batch_still_deletes_everything(fake_db):
    """A rejected commit would leave excluded-app data readable on the server."""

    fact_count = context_buckets_db.MAX_BATCH_OPERATIONS + FIRESTORE_MAX_BATCH_OPERATIONS
    seed_facts(fake_db, fact_count, prefix='fact')
    fake_db.committed_batch_sizes.clear()

    report = context_buckets_db.purge_context_buckets('u1', ['bucket-1'], firestore_client=fake_db)

    assert (report.buckets_deleted, report.facts_deleted) == (1, fact_count)
    assert max(fake_db.committed_batch_sizes) <= context_buckets_db.MAX_BATCH_OPERATIONS
    assert ('users', 'u1', 'context_buckets', 'bucket-1') not in fake_db.rows
    assert context_buckets_db.list_context_facts('u1', account_generation=3, now=NOW, firestore_client=fake_db) == []


def test_expired_facts_are_deleted_rather_than_only_filtered(fake_db):
    sync(
        fake_db,
        [
            build_bucket(
                facts=[
                    build_fact('dead-1', expires_at=NOW - timedelta(minutes=1)),
                    build_fact('live-1', expires_at=NOW + timedelta(hours=1)),
                    build_fact('forever-1'),
                ]
            )
        ],
    )

    deleted = context_buckets_db.collect_expired_context_facts('u1', now=NOW, firestore_client=fake_db)

    assert deleted == 1
    assert ('users', 'u1', 'context_bucket_facts', 'dead-1') not in fake_db.rows
    facts = context_buckets_db.list_context_facts('u1', account_generation=3, now=NOW, firestore_client=fake_db)
    assert sorted(fact.fact_id for fact in facts) == ['forever-1', 'live-1']


def test_expired_fact_collection_larger_than_one_batch_commits_in_chunks(fake_db):
    expired_count = context_buckets_db.MAX_BATCH_OPERATIONS + FIRESTORE_MAX_BATCH_OPERATIONS
    seed_facts(fake_db, expired_count, prefix='dead', expires_at=NOW - timedelta(minutes=1))
    fake_db.committed_batch_sizes.clear()

    deleted = context_buckets_db.collect_expired_context_facts(
        'u1', now=NOW, limit=expired_count, firestore_client=fake_db
    )

    assert deleted == expired_count
    assert max(fake_db.committed_batch_sizes) <= context_buckets_db.MAX_BATCH_OPERATIONS


def test_expired_fact_collection_is_bounded_so_one_sweep_cannot_stall_a_request(fake_db):
    over_limit = context_buckets_db.EXPIRED_FACT_COLLECT_LIMIT + 50
    seed_facts(fake_db, over_limit, prefix='dead', expires_at=NOW - timedelta(minutes=1))

    deleted = context_buckets_db.collect_expired_context_facts('u1', now=NOW, firestore_client=fake_db)

    assert deleted == context_buckets_db.EXPIRED_FACT_COLLECT_LIMIT


def test_expired_fact_collection_stops_at_the_requested_limit(fake_db):
    sync(
        fake_db,
        [
            build_bucket(
                facts=[build_fact(f'dead-{index}', expires_at=NOW - timedelta(minutes=1)) for index in range(5)]
            )
        ],
    )

    assert context_buckets_db.collect_expired_context_facts('u1', now=NOW, limit=2, firestore_client=fake_db) == 2


def test_no_synced_field_can_carry_text_copied_from_the_screen(fake_db):
    """Window titles, URLs, file paths, and extracted identifiers stay on device.

    These are the fields that used to carry them. If a future change reintroduces
    one, the boundary claim in docs/agents/context-buckets.md becomes false again.
    """

    sync(fake_db, [build_bucket()])

    stored_bucket = fake_db.rows[('users', 'u1', 'context_buckets', 'bucket-1')]
    stored_fact = fake_db.rows[('users', 'u1', 'context_bucket_facts', 'fact-1')]
    for forbidden in ('display_label', 'subject_id'):
        assert forbidden not in stored_bucket, f'{forbidden} carries screen text'
    for forbidden in ('identifiers', 'evidence_refs', 'evidence_text', 'narrative'):
        assert forbidden not in stored_fact, f'{forbidden} carries screen text'
