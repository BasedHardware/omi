"""Smart-merge audit sibling and false-merge counters over the real absorb transaction.

Reuses the end-to-end ``World`` (strict in-memory Firestore, real absorb/claim
transactions, faked Jev/processing seams). All text is synthetic.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from config import conversation_smart_merge as config
from config.jev_decisions import JEV_MODEL
from database import smart_merge as smart_merge_db
from database import smart_merge_audit as audit_db
from database.legal_holds import LEGAL_HOLD_DELETION_GATE_SCHEMA_VERSION
from tests.unit.fixtures.strict_firestore_transaction import (
    StrictFirestore,
    StrictFirestoreDocument,
    StrictFirestoreTransaction,
)
from tests.unit.test_conversation_smart_merge import UID, World
from utils import metrics
from utils.conversations import merge_conversations
from utils.conversations import smart_merge
from utils.conversations import smart_merge_audit

AUDIT_KEYS = {
    'version',
    'donor_id',
    'survivor_id',
    'survivor_revision',
    'ledger_position',
    'source',
    'merged_at',
    'expire_at',
    'stretch_count',
    'p_same',
    'threshold',
    'gap_seconds',
    'speech_gap_seconds',
    'model',
    'question_version',
    'mode',
    'flattened_ancestor_count',
}
GATE = ('legal_hold_deletion_gates', UID)
MARKER = ('account_deletions', UID)


def _audit_path(donor_id):
    return ('users', UID, 'smart_merge_audit', donor_id)


def _conversation_rows(store):
    return {key: value for key, value in store.rows.items() if key[:3] == ('users', UID, 'conversations')}


class _Recorder:
    def __init__(self):
        self.audit = []
        self.deleted = []


@pytest.fixture
def world(monkeypatch):
    monkeypatch.setenv(config.SMART_MERGE_MODE_ENV, 'off')
    monkeypatch.delenv(config.SMART_MERGE_UID_ALLOWLIST_ENV, raising=False)
    monkeypatch.delenv(config.SMART_MERGE_AUDIT_ENV, raising=False)
    return World(monkeypatch)


@pytest.fixture
def recorded(monkeypatch):
    seen = _Recorder()
    monkeypatch.setattr(smart_merge, 'record_conversation_smart_merge_audit', seen.audit.append)
    monkeypatch.setattr(smart_merge_audit, 'record_conversation_smart_merge_survivor_deleted', seen.deleted.append)
    return seen


@pytest.fixture
def reads(monkeypatch):
    """Every transaction-bound document read, as (transaction, path)."""
    log = []
    real = StrictFirestoreDocument.get

    def get(self, transaction=None, **kwargs):
        if transaction is not None:
            log.append((transaction, self.path))
        return real(self, transaction, **kwargs)

    monkeypatch.setattr(StrictFirestoreDocument, 'get', get)
    return log


def _gate(state='running', *, started_at=None, kind='account_deletion', **overrides):
    row = {
        'schema_version': LEGAL_HOLD_DELETION_GATE_SCHEMA_VERSION,
        'uid': UID,
        'kind': kind,
        'token': f'account-deletion:{UID}',
        'state': state,
        'started_at': started_at or datetime.now(timezone.utc),
        'finished_at': None,
    }
    row.update(overrides)
    return row


def _absorb_transaction(store, donor_id='n'):
    donor = ('users', UID, 'conversations', donor_id)
    # The tombstone write, not the earlier decision-record update on the same row.
    return next(t for t in store.transactions if any(path == donor and 'deleted' in p for path, p in t.updates))


def _merge(world, donor='n'):
    world.add('p', 0, 10)
    world.add(donor, 15, 10)
    return world.finish(donor)


# --------------------------------------------------------------------------- written once, in the transaction


def test_audit_is_written_once_inside_the_absorb_transaction(world, recorded, reads):
    assert _merge(world) is True
    audit = world.store.rows[_audit_path('n')]
    marker = world.raw('n')['smart_merge']
    decision = world.raw('n')['smart_merge_decision']
    assert set(audit) == AUDIT_KEYS
    assert audit['donor_id'] == 'n' and audit['survivor_id'] == 'p' and audit['version'] == 1
    assert audit['survivor_revision'] == marker['survivor_revision'] == 1
    assert audit['ledger_position'] == 2 and audit['source'] == 'omi' and audit['mode'] == 'merge'
    assert audit['merged_at'] == marker['merged_at']
    assert audit['expire_at'] == marker['merged_at'] + timedelta(days=60)
    assert audit['p_same'] == decision['p_same'] == 0.5 and audit['threshold'] == config.MERGE_THRESHOLD
    assert audit['model'] == JEV_MODEL and audit['question_version'] == config.QUESTION_VERSION
    # Same transaction as the donor tombstone: committed together or not at all.
    absorb = _absorb_transaction(world.store)
    assert [path for path, _ in absorb.sets] == [_audit_path('n')]
    assert len(absorb.updates) == 2
    # Durable deletion marker plus the destructive-operation gate.
    assert [path for txn, path in reads if txn is absorb] == [
        ('users', UID, 'conversations', 'p'),
        ('users', UID, 'conversations', 'n'),
        MARKER,
        GATE,
    ]
    assert recorded.audit == ['written']
    # The survivor ledger carries the merge time the deletion counter reads.
    assert world.raw('p')['smart_merge']['last_merged_at'] == marker['merged_at']


@pytest.mark.parametrize(
    'setup',
    [
        pytest.param(lambda w: setattr(w, 'jev_answers', [0.1]), id='kept'),
        pytest.param(lambda w: setattr(w, 'jev_answers', [None]), id='jev_unavailable'),
        pytest.param(lambda w: w.monkeypatch.setattr(w, 'finish', _shadow_finish(w)), id='shadow'),
    ],
)
def test_no_audit_for_kept_shadow_or_unanswered_pairs(world, recorded, setup):
    setup(world)
    assert _merge(world) is False
    assert not any(key[:3] == ('users', UID, 'smart_merge_audit') for key in world.store.rows)
    assert recorded.audit == []


def _shadow_finish(w):
    real = w.finish
    return lambda cid, **kwargs: real(cid, mode='shadow', **kwargs)


def test_no_audit_and_no_gate_read_when_the_pair_is_skipped_or_rejected(world, recorded, reads):
    world.add('p', 0, 10)
    world.add('n', 71, 10)  # gap outside the window: never reaches Jev
    assert world.finish('n') is False
    result = smart_merge_db.absorb_conversation(
        UID, 'p', 'n', expected_revision=0, plan=lambda *a: ('survivor_changed', None, None, {})
    )
    assert result.outcome == 'rejected' and result.audit == 'none'
    assert GATE not in [path for _, path in reads]
    assert _audit_path('n') not in world.store.rows and recorded.audit == []


def test_replay_and_retry_never_write_a_second_audit(world, recorded):
    assert _merge(world) is True
    first = dict(world.store.rows[_audit_path('n')])
    # Finalization retry of the donor, a repeat decision and a direct absorb replay.
    smart_merge.finish_absorb(UID, 'n', owner='job', resumed=True)
    assert world.finish('n') is False  # a repeat decision on the tombstone never absorbs again
    replay = smart_merge_db.absorb_conversation(
        UID, 'p', 'n', expected_revision=0, plan=lambda *a: (_ for _ in ()).throw(AssertionError('no replan'))
    )
    assert replay.outcome == 'already_absorbed' and replay.audit == 'none'
    audit_writes = [path for txn in world.store.transactions for path, _ in txn.sets if path == _audit_path('n')]
    assert audit_writes == [_audit_path('n')]
    assert world.store.rows[_audit_path('n')] == first
    assert recorded.audit == ['written']


def test_audit_document_id_is_the_donor_id(world):
    # A re-run of the staging after contention targets the same document (set, not add).
    assert audit_db.audit_ref(world.store, UID, 'n').path == _audit_path('n')


# --------------------------------------------------------------------------- failure semantics


def test_invalid_projection_commits_the_merge_without_the_audit(world, recorded, monkeypatch):
    def broken(**kwargs):
        raise ValueError('synthetic projection failure')

    monkeypatch.setattr(audit_db, 'audit_record', broken)
    assert _merge(world) is True
    assert world.raw('n')['deleted'] is True and len(world.transcript('p')) == 4
    assert _audit_path('n') not in world.store.rows
    assert recorded.audit == ['skipped_invalid']


class _AtomicTransaction(StrictFirestoreTransaction):
    """Buffers writes until commit, like Firestore; can fail a commit that stages the audit."""

    def __init__(self, database, **kwargs):
        super().__init__(database, **kwargs)
        self._staged = []

    def set(self, ref, data):
        self._assert_reference_belongs(ref)
        self.has_written = True
        self.sets.append((ref.path, dict(data)))
        self._staged.append(('set', ref.path, dict(data)))

    def update(self, ref, patch):
        self._assert_reference_belongs(ref)
        self.has_written = True
        self.updates.append((ref.path, dict(patch)))
        self._staged.append(('update', ref.path, dict(patch)))

    def _commit(self):
        if self._database.fail_audit_commit and any('smart_merge_audit' in path for _, path, _ in self._staged):
            raise RuntimeError('synthetic commit failure')
        for kind, path, data in self._staged:
            if kind == 'set':
                self._database.rows[path] = data
            elif path not in self._database.rows:
                raise RuntimeError('missing row')
            else:
                self._database.rows[path].update(data)


class _AtomicFirestore(StrictFirestore):
    fail_audit_commit = False

    def transaction(self):
        transaction = _AtomicTransaction(self)
        self.transactions.append(transaction)
        return transaction


def test_a_failed_commit_aborts_merge_and_audit_together(world, recorded):
    world.store = _AtomicFirestore()
    world.store.fail_audit_commit = True
    assert _merge(world) is False
    # Nothing of the absorb committed: no tombstone, no transcript change, no audit.
    assert not world.raw('n').get('deleted') and len(world.transcript('p')) == 2
    assert _audit_path('n') not in world.store.rows
    assert world.raw('n')['smart_merge_decision']['decision'] == 'kept'
    assert world.raw('n')['smart_merge_decision']['reason'] == 'error'
    assert recorded.audit == []


def test_the_atomic_store_commits_merge_and_audit_together(world, recorded):
    world.store = _AtomicFirestore()
    assert _merge(world) is True
    assert world.raw('n')['deleted'] is True and _audit_path('n') in world.store.rows


# --------------------------------------------------------------------------- account-wipe gate


@pytest.mark.parametrize(
    'gate',
    [
        pytest.param(_gate(), id='account_wipe_running'),
        pytest.param(_gate(kind='explicit_memory_deletion'), id='memory_deletion_running'),
        pytest.param(_gate(schema_version=-1), id='malformed_gate'),
    ],
)
def test_live_or_malformed_gate_merges_without_creating_the_audit(world, recorded, gate):
    world.store.rows[GATE] = gate
    assert _merge(world) is True  # the merge decision never depends on the audit
    assert world.raw('n')['deleted'] is True and len(world.transcript('p')) == 4
    assert _audit_path('n') not in world.store.rows
    assert recorded.audit == ['skipped_gate']


@pytest.mark.parametrize(
    'gate',
    [
        pytest.param(_gate(state='completed'), id='finished_gate'),
        pytest.param(_gate(started_at=datetime.now(timezone.utc) - timedelta(hours=7)), id='stale_gate'),
    ],
)
def test_historical_gate_does_not_block_the_audit(world, recorded, gate):
    world.store.rows[GATE] = gate
    assert _merge(world) is True
    assert _audit_path('n') in world.store.rows and recorded.audit == ['written']


def test_unreadable_gate_skips_the_audit_but_not_the_merge(world, recorded, monkeypatch):
    def unreadable(transaction, client, *, uid):
        raise ConnectionError('synthetic gate read failure')

    monkeypatch.setattr(audit_db, 'assert_no_destructive_operation_transaction', unreadable)
    assert _merge(world) is True
    assert _audit_path('n') not in world.store.rows and recorded.audit == ['skipped_error']
    assert len(world.jev_calls) == 1


@pytest.mark.parametrize('status', ['pending', 'running', 'failed', 'completed', None, 'bogus'])
def test_durable_deletion_marker_blocks_audit_after_gate_expires(world, recorded, status):
    world.store.rows[MARKER] = {'wipe_status': status}
    world.store.rows[GATE] = _gate(started_at=datetime.now(timezone.utc) - timedelta(hours=7))
    assert _merge(world) is True
    assert _audit_path('n') not in world.store.rows and recorded.audit == ['skipped_gate']


@pytest.mark.parametrize('status', ['cancelled', 'billing_failed'])
def test_cancelled_deletion_allows_audit(world, status):
    world.store.rows[MARKER] = {'wipe_status': status}
    assert _merge(world) is True
    assert _audit_path('n') in world.store.rows


# --------------------------------------------------------------------------- kill switch


@pytest.mark.parametrize(
    'raw, enabled',
    [
        (None, True),
        ('', True),
        (' ON ', True),
        ('true', True),
        ('1', True),
        ('off', False),
        ('false', False),
        ('of', False),
        ('bogus', False),
    ],
)
def test_audit_flag_parsing_is_typo_safe(monkeypatch, raw, enabled):
    if raw is None:
        monkeypatch.delenv(config.SMART_MERGE_AUDIT_ENV, raising=False)
    else:
        monkeypatch.setenv(config.SMART_MERGE_AUDIT_ENV, raw)
    assert config.smart_merge_audit_enabled() is enabled


@pytest.mark.parametrize('raw', ['off', 'of', 'bogus'])
def test_flag_off_is_the_pre_audit_absorb(world, recorded, reads, monkeypatch, raw):
    monkeypatch.setenv(config.SMART_MERGE_AUDIT_ENV, raw)

    def forbidden(*args, **kwargs):
        raise AssertionError('flag off must not read the gate')

    monkeypatch.setattr(audit_db, 'assert_no_destructive_operation_transaction', forbidden)
    assert _merge(world) is True
    absorb = _absorb_transaction(world.store)
    assert absorb.sets == [] and len(absorb.updates) == 2
    assert [path for txn, path in reads if txn is absorb] == [
        ('users', UID, 'conversations', 'p'),
        ('users', UID, 'conversations', 'n'),
    ]
    assert not any(key[:3] == ('users', UID, 'smart_merge_audit') for key in world.store.rows)
    assert recorded.audit == ['disabled']


def _strip_times(rows):
    def clean(value):
        if isinstance(value, dict):
            return {k: clean(v) for k, v in value.items() if k not in ('merged_at', 'last_merged_at', 'decided_at')}
        if isinstance(value, list):
            return [clean(v) for v in value]
        return value

    return {key: clean(value) for key, value in rows.items()}


def test_audit_outcome_does_not_change_any_conversation_write(monkeypatch):
    results = {}
    for scenario in ('on', 'off', 'gate', 'deletion', 'invalid', 'read_error'):
        with monkeypatch.context() as patch:
            patch.setenv(config.SMART_MERGE_MODE_ENV, 'off')
            patch.delenv(config.SMART_MERGE_UID_ALLOWLIST_ENV, raising=False)
            patch.setenv(config.SMART_MERGE_AUDIT_ENV, 'off' if scenario == 'off' else 'on')
            world = World(patch)
            if scenario == 'gate':
                world.store.rows[GATE] = _gate()
            elif scenario == 'deletion':
                world.store.rows[MARKER] = {'wipe_status': 'running'}
            elif scenario == 'invalid':
                patch.setattr(audit_db, 'audit_record', lambda **kw: (_ for _ in ()).throw(ValueError('invalid')))
            elif scenario == 'read_error':
                patch.setattr(
                    audit_db,
                    'assert_no_destructive_operation_transaction',
                    lambda *a, **kw: (_ for _ in ()).throw(ConnectionError('unavailable')),
                )
            assert _merge(world) is True
            # Decoded: encrypted transcript blobs carry a random nonce per write.
            results[scenario] = _strip_times({key: world.get(UID, key[-1]) for key in _conversation_rows(world.store)})
            assert len(world.jev_calls) == 1
    assert all(rows == results['off'] for rows in results.values())


# --------------------------------------------------------------------------- content-free


MARKERS = ('synthetic', 'title', 'overview', 'SPEAKER', UID)


def _scan(value, path=()):
    if isinstance(value, dict):
        for key, item in value.items():
            yield from _scan(item, (*path, key))
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            yield from _scan(item, (*path, index))
    else:
        yield path, value


def test_audit_document_and_labels_are_content_free(world, monkeypatch):
    labels = []
    for counter in (
        metrics.CONVERSATION_SMART_MERGE_AUDIT_TOTAL,
        metrics.CONVERSATION_SMART_MERGE_SURVIVOR_DELETED_TOTAL,
    ):
        monkeypatch.setattr(counter, 'labels', lambda **kw: SimpleNamespace(inc=lambda: labels.append(kw)))
    assert _merge(world) is True
    audit = world.store.rows[_audit_path('n')]
    assert set(audit) == AUDIT_KEYS
    for path, value in _scan(audit):
        assert len(path) == 1, f'nested value at {path}'
        assert value is None or isinstance(value, (int, float, str, datetime)), path
        if isinstance(value, str):
            assert value in audit_db._DECISION_ENUMS.values() or audit_db._TOKEN.fullmatch(value), path
            assert not any(marker in value for marker in MARKERS), path
    # Arbitrary or uid-shaped values never become a label.
    metrics.record_conversation_smart_merge_audit(UID)
    metrics.record_conversation_smart_merge_survivor_deleted('synthetic words')
    for entry in labels:
        for value in entry.values():
            assert value in (
                metrics.CONVERSATION_SMART_MERGE_AUDIT_OUTCOMES
                | metrics.CONVERSATION_SMART_MERGE_SURVIVOR_AGE_BUCKETS
                | {'other'}
            )
            assert UID not in value
    assert {'outcome': 'other'} in labels and {'age_bucket': 'other'} in labels


@pytest.mark.parametrize('field, value', [('model', 'title with words'), ('mode', 'x' * 129), ('p_same', 'high')])
def test_projection_rejects_prose_and_non_numbers(field, value):
    merged_at = datetime(2026, 10, 1, tzinfo=timezone.utc)
    decision = {
        'p_same': 0.5,
        'threshold': 0.35,
        'gap_seconds': 900.0,
        'speech_gap_seconds': 900.0,
        'model': JEV_MODEL,
        'question_version': config.QUESTION_VERSION,
        'mode': 'merge',
        'stretch_count': 0,
    }
    decision[field] = value
    with pytest.raises(ValueError):
        audit_db.audit_record(
            donor_id='n',
            survivor_id='p',
            survivor_state={'fragments': [{}, {}]},
            donor_update={
                'smart_merge': {'merged_at': merged_at, 'survivor_revision': 1},
                'smart_merge_decision': decision,
            },
            source='omi',
        )


# --------------------------------------------------------------------------- survivor-deleted counter

NOW = datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    'age, bucket',
    [
        (timedelta(minutes=5), 'lt_1h'),
        (timedelta(hours=3), 'lt_24h'),
        (timedelta(days=2), 'lt_7d'),
        (timedelta(days=9), 'gte_7d'),
    ],
)
def test_survivor_age_bucket_from_last_merged_at(age, bucket):
    row = {'smart_merge': {'role': 'survivor', 'last_merged_at': NOW - age, 'fragments': [{}, {}]}}
    assert smart_merge_audit.survivor_age_bucket(row, now=NOW) == bucket


def test_survivor_age_bucket_falls_back_to_the_newest_fragment_end():
    fragments = [{'finished_at': NOW - timedelta(days=3)}, {'finished_at': NOW - timedelta(minutes=10)}]
    row = {'smart_merge': {'role': 'survivor', 'fragments': fragments}}
    assert smart_merge_audit.survivor_age_bucket(row, now=NOW) == 'lt_1h'
    assert smart_merge_audit.survivor_age_bucket({'smart_merge': {'role': 'survivor'}}, now=NOW) == 'unknown'


@pytest.mark.parametrize(
    'row',
    [
        {},
        {'smart_merge': {'role': 'donor', 'merged_at': NOW}},
        {'smart_merge': {'role': 'survivor', 'last_merged_at': NOW}, 'deleted': True},
        {'smart_merge': 'not-a-map'},
    ],
)
def test_only_live_survivors_are_counted(row):
    assert smart_merge_audit.survivor_age_bucket(row, now=NOW) is None


def test_survivor_purge_counts_once_after_the_delete(recorded, monkeypatch):
    row = {
        'id': 'p',
        'sync_merged_from': ['n'],
        'smart_merge': {'role': 'survivor', 'last_merged_at': datetime.now(timezone.utc) - timedelta(minutes=5)},
    }
    purged = []
    monkeypatch.setattr(merge_conversations.conversations_db, 'get_conversation', lambda uid, cid: row)
    monkeypatch.setattr(
        merge_conversations, '_delete_conversation_and_related_data', lambda uid, cid, **kw: purged.append(cid)
    )
    monkeypatch.setattr(
        merge_conversations.conversations_db, 'delete_conversation', lambda uid, cid: purged.append(cid)
    )
    merge_conversations.delete_conversation_with_sync_sources(UID, 'p')
    assert purged == ['n', 'p'] and recorded.deleted == ['lt_1h']


def test_failed_survivor_delete_is_not_counted(recorded, monkeypatch):
    row = {'smart_merge': {'role': 'survivor', 'last_merged_at': datetime.now(timezone.utc)}}
    monkeypatch.setattr(merge_conversations.conversations_db, 'get_conversation', lambda uid, cid: row)

    def fail(uid, cid):
        raise RuntimeError('synthetic delete failure')

    monkeypatch.setattr(merge_conversations.conversations_db, 'delete_conversation', fail)
    with pytest.raises(RuntimeError):
        merge_conversations.delete_conversation_with_sync_sources(UID, 'p')
    assert recorded.deleted == []


def test_plain_conversation_delete_is_not_counted(recorded, monkeypatch):
    monkeypatch.setattr(merge_conversations.conversations_db, 'get_conversation', lambda uid, cid: {'id': 'c'})
    monkeypatch.setattr(merge_conversations.conversations_db, 'delete_conversation', lambda uid, cid: None)
    merge_conversations.delete_conversation_with_sync_sources(UID, 'c')
    assert recorded.deleted == []
