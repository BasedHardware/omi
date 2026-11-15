"""Decision comparisons and durable-token validation across real cache helpers."""

from datetime import datetime, timezone, timedelta
import json

import fakeredis
import pytest

from database import batch_pipeline_privacy as privacy, conversation_tombstones as tombstones
from database import fsr_read_cache as cache, legal_holds, privacy_check_metrics as metrics
from database.batch_privacy_attempt import batch_privacy_attempt
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore, StrictFirestoreDocument

UID = 'privacy-test-owner'
TOKEN = ('batch_pipeline_privacy', privacy.privacy_owner_key(UID))
SOURCE = ('users', UID, 'conversations', 'source')
TOMBSTONE = ('users', UID, 'deleted_conversations', 'source')


@pytest.fixture
def world(monkeypatch):
    db = StrictFirestore(
        {
            ('users', UID): {'data_protection_level': 'standard'},
            SOURCE: {'record_lane_owner': 'batch_live_v1', 'private_cloud_sync_enabled': True},
            TOKEN: {'memo_token': 'a' * 32, 'memo_schema': 1, 'generation': 7},
        }
    )
    reads = []
    revision = [datetime(2026, 11, 2, tzinfo=timezone.utc)]
    original = StrictFirestoreDocument.get

    def get(ref, **kwargs):
        reads.append(ref.path)
        result = original(ref, **kwargs)
        result.update_time = revision[0] if result.exists else None
        return result

    monkeypatch.setattr(StrictFirestoreDocument, 'get', get)
    monkeypatch.setattr(tombstones, 'db', db)
    monkeypatch.setattr(cache, '_redis', lambda: redis)
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{}')
    redis = fakeredis.FakeRedis()
    yield db, reads, revision, redis
    redis.close()


def enable(monkeypatch, *names):
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', json.dumps(dict.fromkeys(names, 100)))


def check(db, **kwargs):
    return privacy.assert_batch_write_allowed(db, db.transaction(), UID, conversation_ids=['source'], **kwargs)


def external(db, transaction=None):
    with legal_holds.external_write_fence(UID, firestore_client=db, transaction=transaction):
        return True


def test_counters_measure_live_check_reads_walks_and_absent_user_default(world):
    db, reads, _, _ = world
    checks = metrics.CHECKS.labels('batch', 'live', 'allow', 'unattributed')._value.get()
    walks = metrics.WALKS.labels('live')._value.get()
    assert check(db) == 7
    assert len(reads) == 5
    assert metrics.CHECKS.labels('batch', 'live', 'allow', 'unattributed')._value.get() == checks + 1
    assert metrics.WALKS.labels('live')._value.get() == walks + 1


def test_instrumentation_preserves_closed_historical_sdk_caller_labels(world, monkeypatch):
    from database import firestore_document_probe as probe

    db, _, _, _ = world
    original = StrictFirestoreDocument.get
    callers = []

    def get(reference, **kwargs):
        callers.append(probe.call_site())
        return original(reference, **kwargs)

    monkeypatch.setattr(StrictFirestoreDocument, 'get', get)
    check(db)
    assert callers == ['database.batch_pipeline_privacy:read'] * 5
    callers.clear()
    assert external(db)
    assert not tombstones.is_deleted(UID, 'source')
    assert callers == [
        'database.legal_holds:external_write_fence',
        'database.legal_holds:external_write_fence',
        'database.conversation_tombstones:is_deleted',
    ]
    assert metrics.current_read_caller() is None


def test_shadow_detects_unfenced_writer_and_keeps_live_block(world, monkeypatch):
    db, _, _, _ = world
    enable(monkeypatch, 'privacy_checks_shadow', 'bpp_generation_memo')
    before = metrics.DECISION_MISMATCH.labels('batch', 'stale_allow')._value.get()
    with batch_privacy_attempt():
        assert check(db) == 7
        # Mutation test: deliberately bypass the mandatory Commit token hook.
        db.rows[TOMBSTONE] = {}
        with pytest.raises(privacy.BatchPrivacyBlocked, match='conversation_deleted'):
            check(db)
    assert metrics.DECISION_MISMATCH.labels('batch', 'stale_allow')._value.get() == before + 1


def test_shadow_fault_never_changes_live_result_or_exception(world, monkeypatch):
    db, _, _, _ = world
    enable(monkeypatch, 'privacy_checks_shadow')

    def broken(*args, **kwargs):
        raise RuntimeError('synthetic shadow failure')

    monkeypatch.setattr(privacy, '_assert_batch_write_allowed_memo', broken)
    with batch_privacy_attempt():
        assert check(db) == 7
        db.rows[TOMBSTONE] = {}
        with pytest.raises(privacy.BatchPrivacyBlocked, match='conversation_deleted'):
            check(db)


def test_off_external_and_tombstone_paths_preserve_read_sequence(world):
    db, reads, _, _ = world
    assert external(db)
    assert not tombstones.is_deleted(UID, 'source')
    assert reads == [
        ('account_deletions', UID),
        ('legal_hold_deletion_gates', UID),
        TOMBSTONE,
    ]


def test_external_cache_validates_token_on_every_decision_and_survives_lost_invalidations(world, monkeypatch):
    db, reads, _, _ = world
    enable(monkeypatch, 'legal_hold_fence_cache')
    assert external(db)
    assert external(db)
    assert reads == [TOKEN, ('account_deletions', UID), ('legal_hold_deletion_gates', UID), TOKEN]
    # Both Redis invalidations were lost. The old envelope remains reachable.
    db.rows[('account_deletions', UID)] = {'wipe_status': 'pending'}
    db.rows[TOKEN]['memo_token'] = 'b' * 32
    with pytest.raises(legal_holds.DestructiveOperationInProgress):
        external(db)


def test_external_transactions_keep_authorities_in_the_conflict_set(world, monkeypatch):
    db, reads, _, _ = world
    enable(monkeypatch, 'privacy_checks_shadow', 'legal_hold_fence_cache', 'privacy_session_token')
    transaction = db.transaction()
    with legal_holds.external_write_fence(UID, firestore_client=db, transaction=transaction):
        assert external(db, transaction)
    assert reads == [('account_deletions', UID), ('legal_hold_deletion_gates', UID)]


@pytest.mark.asyncio
@pytest.mark.parametrize('session', [False, True])
async def test_stale_running_gate_clear_is_not_reused_after_clock_moves_back(world, monkeypatch, session):
    from utils.executors import db_executor, run_blocking

    db, _, _, _ = world
    enable(monkeypatch, 'legal_hold_fence_cache', *(['privacy_session_token'] if session else []))
    now = datetime(2026, 11, 2, 12, tzinfo=timezone.utc)
    clock = [now]
    db.rows[('legal_hold_deletion_gates', UID)] = {
        'schema_version': legal_holds.LEGAL_HOLD_DELETION_GATE_SCHEMA_VERSION,
        'uid': UID,
        'kind': 'account_deletion',
        'token': 'synthetic',
        'state': 'running',
        'started_at': now - timedelta(seconds=legal_holds.GATE_STALE_AFTER_SECONDS + 1),
    }
    original = legal_holds._gate_blocks
    monkeypatch.setattr(legal_holds, '_gate_blocks', lambda gate, observed: original(gate, clock[0]))

    @metrics.with_session_census('listen')
    async def exercise():
        assert await run_blocking(db_executor, external, db)
        clock[0] -= timedelta(seconds=2)
        with pytest.raises(legal_holds.DestructiveOperationInProgress):
            await run_blocking(db_executor, external, db)

    await exercise()


@pytest.mark.parametrize('token', [None, {}, {'memo_token': 'bad', 'memo_schema': 1}])
def test_missing_or_malformed_token_forces_live_negatives(world, monkeypatch, token):
    db, reads, _, _ = world
    enable(monkeypatch, 'tombstone_negative_cache')
    if token is None:
        db.rows.pop(TOKEN)
    else:
        db.rows[TOKEN] = token
    for _ in range(2):
        assert not tombstones.is_deleted(UID, 'source')
    assert reads == [TOKEN, TOMBSTONE] * 2


def test_tombstone_cache_is_per_id_positive_answers_live_and_revision_prevents_aba(world, monkeypatch):
    db, reads, revision, _ = world
    enable(monkeypatch, 'tombstone_negative_cache')
    assert not tombstones.is_deleted(UID, 'source')
    assert not tombstones.is_deleted(UID, 'source')
    assert len(reads) == 3
    db.rows[('users', UID, 'deleted_conversations', 'other')] = {}
    assert tombstones.is_deleted(UID, 'other')  # Never infer owner-wide absence from one ID.
    db.rows[TOMBSTONE] = {}
    revision[0] += timedelta(seconds=1)  # Replayed opaque token, new server revision.
    assert tombstones.is_deleted(UID, 'source')
    reads.clear()
    assert tombstones.is_deleted(UID, 'source')
    assert reads == [TOKEN, TOMBSTONE]  # Positive answer was never cached.


def test_shadow_tombstone_always_returns_live_and_reports_stale_allow(world, monkeypatch):
    db, _, _, _ = world
    enable(monkeypatch, 'privacy_checks_shadow')
    before = metrics.DECISION_MISMATCH.labels('tombstone', 'stale_allow')._value.get()
    assert not tombstones.is_deleted(UID, 'source')
    db.rows[TOMBSTONE] = {}  # Deliberately missing token bump: must be observable.
    assert tombstones.is_deleted(UID, 'source')
    assert metrics.DECISION_MISMATCH.labels('tombstone', 'stale_allow')._value.get() == before + 1


@pytest.mark.asyncio
async def test_session_scope_propagates_to_executor_censuses_and_closes(world, monkeypatch):
    from utils.executors import db_executor, run_blocking

    db, reads, _, _ = world
    enable(monkeypatch, 'privacy_session_token')
    holders = []

    @metrics.with_session_census('listen')
    async def session():
        holders.append(metrics.session_memo())
        assert await run_blocking(db_executor, external, db)
        assert await run_blocking(db_executor, external, db)
        histogram = metrics.CENSUS.labels('listen', 'external', 'live', 'reads')
        before = histogram._sum.get()
        metrics.flush_session_census()
        assert histogram._sum.get() == before + 4  # cold 3, warm token 1

    await session()
    assert len(reads) == 4
    assert metrics.session_memo() is None
    assert holders[0]._closed
    reads.clear()
    await session()
    assert len(reads) == 4 and holders[0] is not holders[1]


def test_metric_and_log_labels_cannot_contain_identifiers(caplog):
    unsafe = 'example@example.test/abcdefghijklmnopqrstuvwxyz12/conversation-id'
    metrics._LOG_AT.clear()
    with caplog.at_level('WARNING'):
        metrics.compare(unsafe, unsafe, 'allow')
    for identifier in unsafe.split('/'):
        assert identifier not in caplog.text
        assert identifier not in repr(metrics.DECISION_MISMATCH.collect())
        assert identifier not in repr(metrics._LOG_AT)
    assert 'family=batch' in caplog.text and 'live=unknown' in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize('cancelled', [False, True])
async def test_pusher_censuses_full_minute_and_collects_ticker_on_exit(world, monkeypatch, cancelled):
    import asyncio
    from utils.executors import db_executor, run_blocking

    db, _, _, _ = world
    waiting, tick, flushed, never = (asyncio.Event() for _ in range(4))
    tickers, holders = [], []

    async def wait_for_tick(event, seconds):
        assert seconds == 60
        if not tickers:
            tickers.append(asyncio.current_task())
            waiting.set()
            await tick.wait()
            return False
        else:
            flushed.set()  # A full flush completed before the next interval.
            await never.wait()

    monkeypatch.setattr(metrics, 'wait_for_event', wait_for_tick)
    histogram = metrics.CENSUS.labels('pusher', 'external', 'live', 'reads')
    before = histogram._sum.get()

    @metrics.with_session_census('pusher')
    async def session():
        holders.append(metrics.session_memo())
        await asyncio.wait_for(waiting.wait(), timeout=10)
        assert await run_blocking(db_executor, external, db)
        assert histogram._sum.get() == before
        tick.set()
        await asyncio.wait_for(flushed.wait(), timeout=10)
        assert histogram._sum.get() == before + 2
        if cancelled:
            raise asyncio.CancelledError
        return 'completed'

    if cancelled:
        with pytest.raises(asyncio.CancelledError):
            await session()
    else:
        assert await session() == 'completed'
    assert metrics.session_memo() is None
    assert holders[0]._closed
    assert tickers[0].cancelled()


@pytest.mark.asyncio
async def test_pusher_ticker_failure_is_observable_without_ending_socket(world, monkeypatch, caplog):
    import asyncio

    failed = asyncio.Event()

    async def failed_wait(event, seconds):
        failed.set()
        raise RuntimeError('synthetic private exception detail')

    monkeypatch.setattr(metrics, 'wait_for_event', failed_wait)

    @metrics.with_session_census('pusher')
    async def socket():
        await asyncio.wait_for(failed.wait(), timeout=10)
        await asyncio.sleep(0)  # Allow the task's done callback to run.
        return 'healthy'

    with caplog.at_level('WARNING'):
        assert await socket() == 'healthy'
    assert 'privacy pusher census ticker stopped unexpectedly' in caplog.text
    assert 'synthetic private exception detail' not in caplog.text
    assert metrics.session_memo() is None
