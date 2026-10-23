"""WQ12: physical privacy document reads, scoped to a transaction attempt."""

from collections import Counter
from dataclasses import asdict
from types import SimpleNamespace
from unittest.mock import Mock

from google.api_core.exceptions import Aborted
from google.cloud import firestore
import pytest

from config import firestore_read_levers as levers
from database import batch_pipeline_store as storage
from database.batch_pipeline_privacy import (
    BatchPrivacyBlocked,
    BatchPrivacyMemo,
    assert_batch_write_allowed,
    privacy_owner_key,
)
from database.batch_pipeline_projection_session import ProjectionSession
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore, StrictFirestoreDocument
from utils.batch_pipeline.contracts import ProjectionBinding, WorkItem, Priority
from utils.batch_pipeline.scheduler import owner_key

UID = 'wq12-owner'
LEVER = 'batch_privacy_memoize'
NAMESPACE = 'batch_pipeline_dev'


@pytest.fixture(autouse=True)
def environment(monkeypatch):
    monkeypatch.delenv('FIRESTORE_READ_LEVERS', raising=False)
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')


@pytest.fixture
def reads(monkeypatch):
    paths = []
    original = StrictFirestoreDocument.get

    def get(reference, transaction=None, **kwargs):
        paths.append(reference.path)
        return original(reference, transaction=transaction, **kwargs)

    monkeypatch.setattr(StrictFirestoreDocument, 'get', get)
    return paths


def enable(monkeypatch, on):
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"batch_privacy_memoize": %d}' % (100 if on else 0))


def database():
    return StrictFirestore({('users', UID): {'data_protection_level': 'standard'}})


@pytest.mark.parametrize('raw', [None, '{}', '{"batch_privacy_memoize": 0}'])
def test_default_off_retains_exact_reads_and_no_memo(monkeypatch, reads, raw):
    if raw is not None:
        monkeypatch.setenv('FIRESTORE_READ_LEVERS', raw)
    assert LEVER in levers.KNOWN_LEVERS
    assert levers.lever_percent(LEVER) == 0
    db = database()
    tx = storage.FirestoreTransaction(db, NAMESPACE, db.transaction())
    for _ in range(2):
        assert tx.check_privacy(UID, ['a', 'a']) == 0
    expected = [
        ('account_deletions', UID),
        ('users', UID),
        ('batch_pipeline_privacy', privacy_owner_key(UID)),
        ('users', UID, 'deleted_conversations', 'a'),
        ('users', UID, 'conversations', 'a'),
    ]
    assert reads == expected * 2
    assert not hasattr(tx, '_privacy_memo')


@pytest.mark.parametrize('count,distinct', [(1, True), (20, True), (20, False)])
def test_batch_read_counts_and_assertions_per_write(monkeypatch, reads, count, distinct):
    """Caller checks jobs, then flush independently guards job/result writes."""
    observed = []
    assertion = Mock(wraps=storage.assert_batch_write_allowed)
    monkeypatch.setattr(storage, 'assert_batch_write_allowed', assertion)
    for on in (False, True):
        enable(monkeypatch, on)
        reads.clear()
        assertion.reset_mock()
        db = database()
        transaction = db.transaction()
        view = storage.FirestoreTransaction(db, NAMESPACE, transaction)
        for i in range(count):
            conversation = f'c-{i}' if distinct else 'shared'
            view.check_privacy(UID, [conversation], 0)
            view.put('jobs', f's-{i}', {'owner_id': UID, 'conversation_id': conversation, 'privacy_generation': 0})
            view.put('results', f's-{i}', {'outcome': 'success'})
        view.flush()
        assertions = count + (count if distinct else 1)
        assert assertion.call_count == assertions
        assert len(transaction.sets) == 2 * count
        # flush also reads each job once to resolve result ownership. These
        # non-privacy reads are unchanged by the lever.
        privacy_reads = 3 + 2 * (count if distinct else 1) if on else 5 * assertions
        assert len(reads) == count + privacy_reads
        path_counts = Counter(reads)
        assert path_counts[('account_deletions', UID)] == (1 if on else assertions)
        observed.append([payload for _, payload in transaction.sets])
    assert observed[0] == observed[1]


def projection_session(db):
    binding = ProjectionBinding(UID, 'job', 'content', ('segment',), target_conversation_id='source')
    store = SimpleNamespace(client=db, store=SimpleNamespace(namespace=NAMESPACE))
    store.ref = lambda table, key: db.collection(f'{NAMESPACE}_{table}').document(key)
    session = ProjectionSession(store, 'segment', binding, 0, policy=SimpleNamespace())
    db.rows[store.ref('jobs', 'segment').path] = {
        'projection_binding': asdict(binding),
        'owner_id': UID,
        'capture_at': 0,
        'privacy_generation': 0,
        'result': {'outcome': 'success'},
    }
    db.rows[session.result_ref.path] = {
        'owner_key': owner_key(UID),
        'protocol_version': 1,
        'segment_id': 'segment',
        'capture_at': 0,
        'result': {'outcome': 'success'},
        'previous_segment_id': None,
        'projection': {'state': 'persisted'},
    }
    db.rows[session.ledger_ref.path] = {
        'dispatch_protocol': 'batch_v1',
        'batch_pipeline': {'protocol_version': 1, 'namespace': NAMESPACE, 'segment_ids': ['segment']},
        'job_id': 'job',
        'status': 'completed',
    }
    return session


def test_real_intake_batch_counts(monkeypatch, reads):
    from config.batch_pipeline import scheduler_control_key
    from config.policy import BatchUnitPolicy
    from database.batch_pipeline_intake import admit

    assertions = Mock(wraps=storage.assert_batch_write_allowed)
    monkeypatch.setattr(storage, 'assert_batch_write_allowed', assertions)
    results = []
    for on in (False, True):
        enable(monkeypatch, on)
        db = database()
        # An already-active shard avoids the unrelated service-frontier query;
        # this fixture deliberately models document transactions, not queries.
        db.rows[(f'{NAMESPACE}_control', scheduler_control_key(owner_key(UID)))] = {'p2_active': True}
        store = storage.FirestoreStore(NAMESPACE, firestore_client=db)
        works = [
            WorkItem(
                f's-{i}',
                UID,
                i * 60,
                'gs://synthetic/audio',
                60,
                Priority.DEEP,
                conversation_id=f'c-{i}',
                privacy_generation=0,
            )
            for i in range(20)
        ]
        binding = ProjectionBinding(UID, 'job', 'content', tuple(work.segment_id for work in works))
        reads.clear()
        assertions.reset_mock()
        result = admit(store, works, binding, 1200, namespace=NAMESPACE, policy=BatchUnitPolicy(batch_enabled=True))
        assert result == {'outcome': 'batch', 'job_id': 'job'}
        # Production admission has no explicit body privacy check; flush makes
        # 20 assertions for 20 distinct source conversations.
        assert assertions.call_count == 20
        assert len(db.transactions[0].sets) == 24  # jobs + owner, queue, control, content
        assert len(reads) == (67 if on else 124)  # 24 unchanged scheduler/content reads
        results.append(db.rows)
    assert results[0] == results[1]


def test_projection_prepare_and_plan_counts(monkeypatch, reads):
    for on, total in [(False, 18), (True, 13)]:
        enable(monkeypatch, on)
        db = database()
        session = projection_session(db)
        transaction = db.transaction()
        reads.clear()
        session.prepare(transaction, replay=False)
        session.validate_plan(transaction, {'id': 'source', 'sync_merged_from': ['donor']})
        # Four protocol reads plus 14 -> 9 privacy reads (7 + 7 -> 7 + 2).
        assert len(reads) == total
        session.write_receipt(transaction, {'state': 'ready'})
        assert len(transaction.updates) == 1


@pytest.mark.parametrize('scope', ['store', 'projection'])
@pytest.mark.parametrize(
    'change,reason',
    [
        (('account_deletions', UID), 'account_deleted'),
        (('batch_pipeline_privacy', privacy_owner_key(UID)), 'privacy_generation_changed'),
        (('users', UID, 'deleted_conversations', 'source'), 'conversation_deleted'),
    ],
)
def test_real_sdk_retry_reloads_every_fence(monkeypatch, reads, scope, change, reason):
    """SDK reuses its transaction object and retry ID; callback scope must reset."""
    enable(monkeypatch, True)
    db = database()
    session = projection_session(db)
    transaction = db.transaction()
    transaction._max_attempts = 2
    commits = []

    def commit():
        commits.append(True)
        db.rows[change] = {'generation': 1} if change[0] == 'batch_pipeline_privacy' else {}
        raise Aborted('concurrent privacy mutation')

    monkeypatch.setattr(transaction, '_commit', commit)
    if scope == 'projection':

        @firestore.transactional
        def callback(tx):
            session.prepare(tx, replay=False)
            session.validate_plan(tx, {'id': 'source'})

        run = lambda: callback(transaction)
    else:
        monkeypatch.setattr(db, 'transaction', lambda: transaction)
        store = storage.FirestoreStore(NAMESPACE, firestore_client=db)

        def body(view):
            view.check_privacy(UID, ['source'], 0)
            view.check_privacy(UID, ['source'], 0)

        run = lambda: store.run(body)
    with pytest.raises(BatchPrivacyBlocked, match=reason):
        run()
    assert len(commits) == 1  # Second attempt denies before it can commit.
    assert Counter(reads)[change] == 2


def test_new_transaction_and_owner_do_not_reuse_absence(monkeypatch, reads):
    enable(monkeypatch, True)
    db = database()
    view = storage.FirestoreTransaction(db, NAMESPACE, db.transaction())
    view.check_privacy(UID, ['source'])
    db.rows[('users', 'other')] = {'data_protection_level': 'e2ee'}
    with pytest.raises(BatchPrivacyBlocked, match='data_protection_changed'):
        view.check_privacy('other', ['source'])
    db.rows[('account_deletions', UID)] = {}
    new_view = storage.FirestoreTransaction(db, NAMESPACE, db.transaction())
    with pytest.raises(BatchPrivacyBlocked, match='account_deleted'):
        new_view.check_privacy(UID, ['source'])
    assert Counter(reads)[('account_deletions', UID)] == 2


def test_generation_is_compared_even_with_cached_documents(monkeypatch, reads):
    enable(monkeypatch, True)
    db = database()
    view = storage.FirestoreTransaction(db, NAMESPACE, db.transaction())
    assert view.check_privacy(UID, [], 0) == 0
    with pytest.raises(BatchPrivacyBlocked, match='privacy_generation_changed'):
        view.check_privacy(UID, [], 1)
    assert len(reads) == 3


def test_new_source_is_checked_after_success(monkeypatch, reads):
    enable(monkeypatch, True)
    db = database()
    db.rows[('users', UID, 'deleted_conversations', 'deleted')] = {}
    view = storage.FirestoreTransaction(db, NAMESPACE, db.transaction())
    view.check_privacy(UID, ['safe'])
    with pytest.raises(BatchPrivacyBlocked, match='conversation_deleted'):
        view.check_privacy(UID, ['deleted'])
    assert len(reads) == 6


@pytest.mark.parametrize('on', [False, True])
@pytest.mark.parametrize(
    'path,row,reason',
    [
        (('account_deletions', UID), {}, 'account_deleted'),
        (('users', UID), None, 'account_missing'),
        (('users', UID), {'data_protection_level': 'e2ee'}, 'data_protection_changed'),
        (('users', UID), {'migration_status': 'migrating'}, 'data_protection_changed'),
        (('batch_pipeline_privacy', privacy_owner_key(UID)), {'blocked': True}, 'privacy_generation_changed'),
        (('batch_pipeline_privacy', privacy_owner_key(UID)), {'purging': True}, 'privacy_generation_changed'),
        (('users', UID, 'deleted_conversations', 'source'), {}, 'conversation_deleted'),
        (('users', UID, 'conversations', 'source'), {'deleted': True}, 'conversation_deleted'),
        (
            ('users', UID, 'conversations', 'source'),
            {'deleted': True, 'sync_merged_into': 'source'},
            'conversation_redirect_cycle',
        ),
        (
            ('users', UID, 'conversations', 'source'),
            {'deleted': True, 'sync_merged_into': 'missing'},
            'conversation_redirect_missing',
        ),
        (
            ('users', UID, 'conversations', 'source'),
            {'record_lane_owner': 'batch_live_v1'},
            'recording_privacy_changed',
        ),
    ],
)
def test_denial_parity_even_after_a_prior_check(monkeypatch, on, path, row, reason):
    enable(monkeypatch, on)
    db = database()
    if row is None:
        db.rows.pop(path, None)
    else:
        db.rows[path] = row
    view = storage.FirestoreTransaction(db, NAMESPACE, db.transaction())
    for _ in range(2):
        with pytest.raises(BatchPrivacyBlocked, match=reason):
            view.check_privacy(UID, ['source'])


def test_snapshots_redirects_and_budget_are_rechecked(monkeypatch, reads):
    enable(monkeypatch, True)
    db = database()
    db.rows[('users', UID, 'conversations', 'source')] = {'deleted': True, 'sync_merged_into': 'target'}
    db.rows[('users', UID, 'conversations', 'target')] = {'id': 'target'}
    transaction = db.transaction()
    memo = BatchPrivacyMemo(db, transaction)
    outputs = []
    for _ in range(2):
        snapshots = {}
        assert_batch_write_allowed(db, transaction, UID, conversation_ids=['source'], snapshots=snapshots, memo=memo)
        outputs.append(snapshots)
    assert outputs[0] == outputs[1]
    assert set(outputs[1]['conversations']) == {'source', 'target'}
    assert len(reads) == 7
    outputs[0]['user']['data_protection_level'] = 'e2ee'
    assert outputs[1]['user']['data_protection_level'] == 'standard'
    # Previous small checks must not let a larger call bypass its 256-doc budget.
    with pytest.raises(BatchPrivacyBlocked, match='conversation_fence_budget'):
        assert_batch_write_allowed(db, transaction, UID, conversation_ids=[f'c-{i}' for i in range(257)], memo=memo)


def test_memo_cannot_cross_client_or_transaction(monkeypatch):
    enable(monkeypatch, True)
    db = database()
    memo = BatchPrivacyMemo(db, db.transaction())
    with pytest.raises(ValueError, match='another transaction attempt'):
        assert_batch_write_allowed(db, db.transaction(), UID, memo=memo)
    other = database()
    with pytest.raises(ValueError, match='another transaction attempt'):
        assert_batch_write_allowed(other, memo.transaction, UID, memo=memo)
    with pytest.raises(ValueError, match='requires a transaction'):
        BatchPrivacyMemo(db, None)


def test_off_ignores_even_explicit_memo(monkeypatch, reads):
    db = database()
    transaction = db.transaction()
    memo = BatchPrivacyMemo(db, transaction)
    for _ in range(2):
        assert_batch_write_allowed(db, transaction, UID, conversation_ids=['source'], memo=memo)
    assert len(reads) == 10
    assert memo.snapshots == {}


def test_read_error_is_not_cached(monkeypatch, reads):
    enable(monkeypatch, True)
    db = database()
    view = storage.FirestoreTransaction(db, NAMESPACE, db.transaction())
    original = StrictFirestoreDocument.get
    failed = []

    def fail_once(reference, **kwargs):
        if not failed:
            failed.append(True)
            raise RuntimeError('unavailable')
        return original(reference, **kwargs)

    monkeypatch.setattr(StrictFirestoreDocument, 'get', fail_once)
    with pytest.raises(RuntimeError, match='unavailable'):
        view.check_privacy(UID, ['source'])
    assert view.check_privacy(UID, ['source']) == 0
    assert len(reads) == 5
