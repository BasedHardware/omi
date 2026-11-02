"""Task scope and physical reads through production transactional/sync callers."""

from collections import Counter
from datetime import datetime, timezone
import json

from google.api_core.exceptions import Aborted
import pytest

from config import firestore_read_levers as levers
from database import batch_pipeline_privacy as privacy, batch_pipeline_store as storage
from database.batch_privacy_attempt import batch_privacy_attempt, current_attempt
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore, StrictFirestoreDocument
from utils.sync import completed_status

UID = 'wq26-owner'
TOKEN_PATH = ('batch_pipeline_privacy', privacy.privacy_owner_key(UID))
SOURCE_PATH = ('users', UID, 'conversations', 'source')


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.delenv('FIRESTORE_READ_LEVERS', raising=False)
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')


@pytest.fixture
def reads(monkeypatch):
    reads = []
    original = StrictFirestoreDocument.get

    def get(reference, transaction=None, **kwargs):
        reads.append(reference.path)
        snapshot = original(reference, transaction=transaction, **kwargs)
        # The narrow ordering fixture omits SDK metadata. Model only this read
        # metadata seam here; real revision changes/replay are emulator-tested.
        snapshot.update_time = datetime(2026, 10, 27, tzinfo=timezone.utc) if snapshot.exists else None
        return snapshot

    monkeypatch.setattr(StrictFirestoreDocument, 'get', get)
    return reads


def database():
    return StrictFirestore(
        {
            ('users', UID): {'data_protection_level': 'standard', 'private_cloud_sync_enabled': True},
            TOKEN_PATH: {'generation': 7, 'memo_token': 'a' * 32, 'memo_schema': 1},
            SOURCE_PATH: {'id': 'source', 'record_lane_owner': 'batch_live_v1', 'private_cloud_sync_enabled': True},
        }
    )


def enabled(monkeypatch, on=True):
    # Never edit runtime configuration literals: these are process-local test gates.
    monkeypatch.setattr(privacy, 'lever_enabled', lambda name, uid: on if name == 'bpp_generation_memo' else False)


def check(db, ids=('source',), generation=7, **kwargs):
    return privacy.assert_batch_write_allowed(
        db,
        db.transaction(),
        UID,
        conversation_ids=ids,
        expected_generation=generation,
        **kwargs,
    )


def test_real_store_transactions_100_to_24_and_retry_scope_reset(monkeypatch, reads):
    enabled(monkeypatch)
    db = database()
    store = storage.FirestoreStore('batch_pipeline_dev', firestore_client=db)
    with batch_privacy_attempt() as attempt:
        for _ in range(20):
            assert store.run(lambda view: view.check_privacy(UID, ['source'], 7)) == 7
        assert len(db.transactions) == 20
        assert len(reads) == 24
        assert Counter(reads)[TOKEN_PATH] == 20
        attempt.reset()
        assert store.run(lambda view: view.check_privacy(UID, ['source'], 7)) == 7
        assert len(reads) == 29
    with batch_privacy_attempt():
        assert store.run(lambda view: view.check_privacy(UID, ['source'], 7)) == 7
    assert len(reads) == 34
    assert current_attempt() is None


def test_actual_sync_durable_status_path_counts_and_identical_results(monkeypatch, reads):
    monkeypatch.setenv('SYNC_DURABLE_STATUS_RECONCILIATION', 'true')
    results, counts = [], []
    for on in (False, True):
        enabled(monkeypatch, on)
        db = database()
        db.rows[('users', UID, completed_status.collection_name('sync_content_ledger'), 'content')] = {
            'status': 'completed',
            'job_id': 'job',
            'result': {
                'total_segments': 1,
                'failed_segments': 0,
                'errors': [],
                'new_memories': ['source'],
                'updated_memories': [],
            },
        }
        monkeypatch.setattr(completed_status, 'get_firestore_client', lambda: db)
        reads.clear()
        with batch_privacy_attempt():
            outputs = [
                completed_status.get_completed_legacy_status(
                    'job',
                    UID,
                    {
                        'uid': UID,
                        'job_id': 'job',
                        'content_id': 'content',
                        'status': 'running',
                    },
                )
                for _ in range(20)
            ]
        assert all(value and value['status'] == 'completed' for value in outputs)
        counts.append(len(reads))
        results.append(json.dumps(outputs, sort_keys=True))
    assert counts == [120, 44]  # 20 unchanged ledger reads, privacy 100 -> 24.
    assert results[0] == results[1]


@pytest.mark.parametrize('raw', [None, '{}', '{"bpp_generation_memo": 0}'])
def test_exact_off_path_reads_and_rows_byte_identical(monkeypatch, reads, raw):
    if raw is not None:
        monkeypatch.setenv('FIRESTORE_READ_LEVERS', raw)
    assert 'bpp_generation_memo' in levers.KNOWN_LEVERS
    assert levers.lever_percent('bpp_generation_memo') == 0
    db = database()
    before = json.dumps(list(db.rows.items()), sort_keys=True)
    with batch_privacy_attempt():
        for _ in range(20):
            check(db)
    expected = [
        ('account_deletions', UID),
        ('users', UID),
        TOKEN_PATH,
        ('users', UID, 'deleted_conversations', 'source'),
        SOURCE_PATH,
    ]
    assert reads == expected * 20
    assert json.dumps(list(db.rows.items()), sort_keys=True) == before


@pytest.mark.parametrize(
    'row',
    [
        None,
        {},
        {'memo_token': 'bad', 'memo_schema': 1},
        {'memo_token': 'a' * 32, 'memo_schema': True},
        {'memo_token': 'a' * 32, 'memo_schema': 2},
        {'memo_token': 'a' * 32, 'memo_schema': 1, 'memo_blocked': True},
    ],
)
def test_missing_malformed_or_blocked_token_stays_live(monkeypatch, reads, row):
    enabled(monkeypatch)
    db = database()
    if row is None:
        db.rows.pop(TOKEN_PATH)
    else:
        db.rows[TOKEN_PATH] = {'generation': 7, **row}
    with batch_privacy_attempt():
        for _ in range(3):
            check(db, generation=None)
    assert len(reads) == 15


def test_changed_token_new_source_redirect_owner_and_plane(monkeypatch, reads):
    enabled(monkeypatch)
    db = database()
    with batch_privacy_attempt():
        check(db)
        db.rows[TOKEN_PATH]['memo_token'] = 'b' * 32
        db.rows[SOURCE_PATH] = {'deleted': True, 'sync_merged_into': 'target'}
        db.rows[('users', UID, 'conversations', 'target')] = {'id': 'target'}
        check(db)
        assert len(reads) == 12
        check(db)
        assert len(reads) == 13
        db.rows[('users', UID, 'deleted_conversations', 'new')] = {}
        with pytest.raises(privacy.BatchPrivacyBlocked, match='conversation_deleted'):
            check(db, ids=('source', 'new'))
        other = database()
        other.rows[('users', UID)]['data_protection_level'] = 'e2ee'
        with pytest.raises(privacy.BatchPrivacyBlocked, match='data_protection_changed'):
            check(other)
        db.rows[('users', 'other')] = {'data_protection_level': 'e2ee'}
        with pytest.raises(privacy.BatchPrivacyBlocked, match='data_protection_changed'):
            privacy.assert_batch_write_allowed(db, db.transaction(), 'other')


def test_snapshots_exports_stay_live_and_do_not_populate_decisions(monkeypatch, reads):
    enabled(monkeypatch)
    db = database()
    with batch_privacy_attempt():
        for i in range(3):
            db.rows[SOURCE_PATH]['title'] = f'fresh-{i}'
            output = {}
            check(db, snapshots=output)
            assert output['conversations']['source']['title'] == f'fresh-{i}'
        assert len(reads) == 15
        check(db)
        assert len(reads) == 20


@pytest.mark.parametrize('failure', [TOKEN_PATH, SOURCE_PATH])
def test_failed_reads_never_publish_partial_decisions(monkeypatch, reads, failure):
    enabled(monkeypatch)
    db = database()
    original = StrictFirestoreDocument.get
    failed = False

    def get(reference, **kwargs):
        nonlocal failed
        if reference.path == failure and not failed:
            failed = True
            raise RuntimeError('synthetic unavailable')
        return original(reference, **kwargs)

    monkeypatch.setattr(StrictFirestoreDocument, 'get', get)
    with batch_privacy_attempt():
        with pytest.raises(RuntimeError, match='unavailable'):
            check(db)
        reads.clear()
        check(db)
        assert len(reads) == 5
        db.rows[TOKEN_PATH]['memo_token'] = 'b' * 32
        db.rows[('account_deletions', UID)] = {}
        with pytest.raises(privacy.BatchPrivacyBlocked, match='account_deleted'):
            check(db)


def test_real_sdk_transaction_retry_revalidates_token_and_denies(monkeypatch, reads):
    enabled(monkeypatch)
    db = database()
    store = storage.FirestoreStore('batch_pipeline_dev', firestore_client=db)
    transaction = db.transaction()
    transaction._max_attempts = 2
    monkeypatch.setattr(db, 'transaction', lambda: transaction)
    commits = []

    def commit():
        commits.append(True)
        db.rows[TOKEN_PATH]['memo_token'] = 'b' * 32
        db.rows[('users', UID, 'deleted_conversations', 'source')] = {}
        raise Aborted('synthetic concurrent deletion')

    monkeypatch.setattr(transaction, '_commit', commit)
    with batch_privacy_attempt():
        with pytest.raises(privacy.BatchPrivacyBlocked, match='conversation_deleted'):
            store.run(lambda view: view.check_privacy(UID, ['source'], 7))
    assert len(commits) == 1
    assert Counter(reads)[TOKEN_PATH] == 2


def test_expected_generation_is_always_compared_and_no_cross_request_cache(monkeypatch, reads):
    enabled(monkeypatch)
    db = database()
    with batch_privacy_attempt():
        check(db)
        with pytest.raises(privacy.BatchPrivacyBlocked, match='privacy_generation_changed'):
            check(db, generation=8)
    # A new request is cold even if the token is unchanged.
    reads.clear()
    with batch_privacy_attempt():
        check(db)
    assert len(reads) == 5
    reads.clear()
    for _ in range(3):
        check(db)  # No explicitly owned scope => no memo.
    assert len(reads) == 15


@pytest.mark.asyncio
async def test_attempt_decorator_propagates_to_real_executor_and_retry_starts_cold(monkeypatch, reads):
    from database.batch_privacy_attempt import with_batch_privacy_attempt
    from utils.executors import db_executor, run_blocking

    enabled(monkeypatch)
    db = database()
    scopes = []

    @with_batch_privacy_attempt
    async def job(fail=False):
        scopes.append(current_attempt())
        for _ in range(2):
            await run_blocking(db_executor, check, db)
        if fail:
            raise RuntimeError('retry job')

    with pytest.raises(RuntimeError, match='retry job'):
        await job(fail=True)
    assert current_attempt() is None
    assert len(reads) == 6
    await job()
    assert len(reads) == 12 and scopes[0] is not scopes[1]
    # A captured executor context cannot keep using an ended attempt.
    assert scopes[0].get((db, UID, frozenset(['source'])), 'a' * 32) is None


def test_cross_request_mutation_is_denied_and_token_read_failure_discards_warm_entry(monkeypatch, reads):
    enabled(monkeypatch)
    db = database()
    with batch_privacy_attempt():
        check(db)
    db.rows[TOKEN_PATH]['memo_token'] = 'b' * 32
    db.rows[SOURCE_PATH]['deleted'] = True
    with batch_privacy_attempt():
        with pytest.raises(privacy.BatchPrivacyBlocked, match='conversation_deleted'):
            check(db)
    db.rows[SOURCE_PATH].pop('deleted')
    original = StrictFirestoreDocument.get
    with batch_privacy_attempt():
        check(db)

        def fail(reference, **kwargs):
            if reference.path == TOKEN_PATH:
                raise RuntimeError('token unavailable')
            return original(reference, **kwargs)

        with monkeypatch.context() as patch:
            patch.setattr(StrictFirestoreDocument, 'get', fail)
            with pytest.raises(RuntimeError, match='token unavailable'):
                check(db)
        reads.clear()
        check(db)
        assert len(reads) == 5


@pytest.mark.parametrize('revision', [None, 'bad', datetime(2026, 10, 27)])
def test_missing_or_malformed_server_revision_never_reuses_token(monkeypatch, reads, revision):
    enabled(monkeypatch)
    db = database()
    original = StrictFirestoreDocument.get

    def get(reference, **kwargs):
        snapshot = original(reference, **kwargs)
        if reference.path == TOKEN_PATH:
            snapshot.update_time = revision
        return snapshot

    monkeypatch.setattr(StrictFirestoreDocument, 'get', get)
    with batch_privacy_attempt():
        check(db)
        check(db)
    assert len(reads) == 10


def test_cached_hit_preserves_foreign_wq12_memo_validation(monkeypatch, reads):
    monkeypatch.setattr(privacy, 'lever_enabled', lambda *a: True)
    db = database()
    with batch_privacy_attempt():
        check(db)
        foreign = privacy.BatchPrivacyMemo(db, db.transaction())
        with pytest.raises(ValueError, match='another transaction'):
            check(db, memo=foreign)


@pytest.mark.parametrize('export_snapshots', [False, True])
def test_actual_artifact_authorize_path_read_counts_and_exact_off_order(monkeypatch, reads, export_snapshots):
    from types import SimpleNamespace
    from utils.batch_pipeline import retention

    item = SimpleNamespace(owner_id=UID, conversation_id='source', privacy_generation=7)
    counts, results = [], []
    for on in (False, True):
        enabled(monkeypatch, on)
        monkeypatch.setattr(retention, 'lever_enabled', lambda *a: on)
        db = database()
        store = SimpleNamespace(client=db)
        reads.clear()
        with batch_privacy_attempt():
            outputs = []
            for i in range(20):
                db.rows[SOURCE_PATH]['title'] = f'live-{i}'
                snapshots = {} if export_snapshots else None
                outputs.append(retention.batch_artifact_authorize(store, item, snapshots=snapshots))
                if snapshots is not None:
                    assert snapshots['conversations']['source']['title'] == f'live-{i}'
        counts.append(len(reads))
        results.append(outputs)
        if not on:
            assert (
                reads
                == [
                    ('account_deletions', UID),
                    ('users', UID),
                    TOKEN_PATH,
                    ('users', UID, 'deleted_conversations', 'source'),
                    SOURCE_PATH,
                ]
                * 20
            )
    assert results[0] == results[1]
    # Every call still reads the live protection level. Full-row consumers never hit.
    assert counts == ([100, 100] if export_snapshots else [100, 44])
