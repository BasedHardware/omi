"""Decision comparisons and durable-token validation across real cache helpers."""

from contextlib import nullcontext
from datetime import datetime, timezone, timedelta
from pathlib import Path
import json
import re
import time
from types import SimpleNamespace

import fakeredis
from google.api_core import exceptions
import pytest
import yaml

from database import batch_pipeline_privacy as privacy, conversation_tombstones as tombstones
from database import batch_privacy_owner_cache as shared_cache
from database import fsr_read_cache as cache, legal_holds, privacy_check_metrics as metrics
from database.batch_privacy_attempt import batch_privacy_attempt
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore, StrictFirestoreDocument
from utils.batch_pipeline import artifact_reads
from utils.batch_pipeline.artifact_reads import ArtifactReadBudget

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
    # The shared owner cache merges dark (code default 0); this world exercises it enabled.
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"bpp_shared_owner_cache":100}')
    redis = fakeredis.FakeRedis()
    yield db, reads, revision, redis
    redis.close()


def test_shared_owner_cache_merges_dark_and_status_skip_ships_on(monkeypatch):
    from config.firestore_read_levers import lever_percent

    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{}')
    assert lever_percent('bpp_shared_owner_cache') == 0
    assert lever_percent('bpp_shared_owner_shadow') == 0
    assert lever_percent('bpp_status_skip') == 100


def enable(monkeypatch, *names):
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', json.dumps(dict.fromkeys(names, 100)))


def check(db, **kwargs):
    return privacy.assert_batch_write_allowed(db, db.transaction(), UID, conversation_ids=['source'], **kwargs)


def external(db, transaction=None):
    with legal_holds.external_write_fence(UID, firestore_client=db, transaction=transaction):
        return True


@pytest.fixture
def shared_owner_world(world, monkeypatch):
    db, _, _, redis = world
    db._database_string = 'projects/synthetic/databases/(default)'
    monkeypatch.setenv('REDIS_DB_HOST', 'synthetic')
    monkeypatch.setattr(shared_cache, '_redis_retry_at', 0.0)
    monkeypatch.setattr(shared_cache, '_redis', lambda: redis)
    monkeypatch.setattr(privacy, 'ttl_disabled', lambda: False)
    return world


def test_shared_owner_decision_saves_walk_across_client_instances(shared_owner_world, monkeypatch):
    db, reads, revision, _ = shared_owner_world
    assert check(db, shared_owner_cache=True) == 7
    assert TOKEN in reads and SOURCE in reads
    other = StrictFirestore(db.rows)
    other._database_string = db._database_string
    reads.clear()
    assert check(other, shared_owner_cache=True) == 7
    assert reads == [TOKEN]

    # The same opaque token may be replayed, but the server revision changes.
    revision[0] += timedelta(seconds=1)
    other.rows[TOMBSTONE] = {}
    reads.clear()
    with pytest.raises(privacy.BatchPrivacyBlocked, match='conversation_deleted'):
        check(other, shared_owner_cache=True)
    assert TOKEN in reads and TOMBSTONE in reads

    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"bpp_shared_owner_cache":0}')
    reads.clear()
    with pytest.raises(privacy.BatchPrivacyBlocked, match='conversation_deleted'):
        check(other, shared_owner_cache=True)
    assert TOMBSTONE in reads


def test_shared_owner_cache_expiry_coverage_and_plane(shared_owner_world, monkeypatch):
    db, reads, _, redis = shared_owner_world
    now = time.time()
    clock = SimpleNamespace(time=lambda: now, monotonic=time.monotonic)
    monkeypatch.setattr(shared_cache, 'time', clock)
    monkeypatch.setattr(privacy, 'time', clock)
    assert check(db, shared_owner_cache=True) == 7
    (key,) = redis.keys()
    assert 0 < redis.pttl(key) <= 300_000
    assert UID.encode() not in key and b'source' not in redis.get(key)
    owner = privacy.privacy_owner_key(UID)
    assert shared_cache.read(db, owner, frozenset({'new-id'}), None) is None
    assert shared_cache.read(db, owner, frozenset({'source'}), 8) is None
    other = SimpleNamespace(_database_string='projects/other/databases/(default)')
    assert shared_cache.read(other, owner, frozenset({'source'}), None) is None

    clock.time = lambda: now + 300
    reads.clear()
    assert check(db, shared_owner_cache=True) == 7
    assert SOURCE in reads


def test_shared_shadow_distinguishes_unfenced_mismatch_from_recent_revocation(shared_owner_world, monkeypatch):
    db, reads, revision, _ = shared_owner_world
    monkeypatch.setenv(
        'FIRESTORE_READ_LEVERS',
        '{"bpp_shared_owner_cache":0,"bpp_status_skip":0,"bpp_shared_owner_shadow":100,"privacy_checks_shadow":0}',
    )
    shadow_gets = shared_cache.OUTCOMES.labels('shadow_get_attempt')._value
    certified_gets = shared_cache.OUTCOMES.labels('certified_get_attempt')._value
    before_gets = shadow_gets.get(), certified_gets.get()
    changes = shared_cache.SHADOW.labels('authority_changed')
    mismatches = shared_cache.SHADOW.labels('mismatch')
    matches = shared_cache.SHADOW.labels('match')
    before = (changes._value.get(), mismatches._value.get(), matches._value.get())
    assert check(db, shared_owner_cache=True) == 7
    reads.clear()
    assert check(db, shared_owner_cache=True) == 7
    assert SOURCE in reads
    db.rows[TOMBSTONE] = {}
    with pytest.raises(privacy.BatchPrivacyBlocked, match='conversation_deleted'):
        check(db, shared_owner_cache=True)
    revision[0] = datetime.now(timezone.utc)
    db.rows[TOKEN]['memo_token'] = 'b' * 32
    with pytest.raises(privacy.BatchPrivacyBlocked, match='conversation_deleted'):
        check(db, shared_owner_cache=True)
    assert (changes._value.get(), mismatches._value.get(), matches._value.get()) == tuple(x + 1 for x in before)
    assert (shadow_gets.get(), certified_gets.get()) == (before_gets[0] + 4, before_gets[1])


def test_malformed_shadow_version_preserves_authoritative_allow(shared_owner_world, monkeypatch):
    db, reads, _, redis = shared_owner_world
    enable(monkeypatch, 'bpp_shared_owner_shadow')
    assert check(db, shared_owner_cache=True) == 7
    (key,) = redis.keys()
    original_candidate = redis.get(key)

    db.rows[TOKEN]['generation'] = 8
    monkeypatch.setattr(privacy, 'token_version', lambda snapshot: ('a' * 32, 'invalid-revision', 0))
    unavailable = shared_cache.SHADOW.labels('unavailable')._value
    mismatch = shared_cache.SHADOW.labels('mismatch')._value
    before = unavailable.get(), mismatch.get()
    reads.clear()

    assert check(db, shared_owner_cache=True) == 8
    assert TOKEN in reads and SOURCE in reads
    assert (unavailable.get(), mismatch.get()) == (before[0] + 1, before[1])
    assert redis.get(key) == original_candidate


def test_shared_owner_set_errors_do_not_inflate_get_attempts(shared_owner_world, monkeypatch):
    from redis.exceptions import ConnectionError

    db, _, _, redis = shared_owner_world
    attempts = shared_cache.OUTCOMES.labels('certified_get_attempt')._value
    hits = shared_cache.OUTCOMES.labels('certified_hit')._value
    set_errors = shared_cache.OUTCOMES.labels('set_error')._value
    before = attempts.get(), hits.get(), set_errors.get()
    assert check(db, shared_owner_cache=True) == 7
    assert check(db, shared_owner_cache=True) == 7

    def fail_set(*args, **kwargs):
        raise ConnectionError('test Redis SET failure')

    monkeypatch.setattr(redis, 'set', fail_set)
    shared_cache.store(db, privacy.privacy_owner_key(UID), frozenset(), ('a' * 32, '', 0), 7, started=time.time())
    assert (attempts.get(), hits.get(), set_errors.get()) == tuple(x + n for x, n in zip(before, (2, 1, 1)))


def test_shared_owner_redis_error_falls_back_to_the_live_walk(shared_owner_world, monkeypatch):
    from redis.exceptions import ConnectionError

    db, reads, _, redis = shared_owner_world

    calls = []

    def broken(*args, **kwargs):
        calls.append('get')
        raise ConnectionError('synthetic outage')

    def reject_store(*args, **kwargs):
        raise AssertionError('Redis cooldown must skip SET')

    monkeypatch.setattr(redis, 'get', broken)
    monkeypatch.setattr(redis, 'set', reject_store)
    attempts = shared_cache.OUTCOMES.labels('certified_get_attempt')._value
    get_errors = shared_cache.OUTCOMES.labels('get_error')._value
    before = attempts.get(), get_errors.get()
    assert check(db, shared_owner_cache=True) == 7
    assert SOURCE in reads and TOKEN in reads
    reads.clear()
    assert check(db, shared_owner_cache=True) == 7
    assert SOURCE in reads and calls == ['get']
    assert (attempts.get(), get_errors.get()) == (before[0] + 1, before[1] + 1)


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
    counter = metrics.OWNER_SHADOW_ERRORS.labels('attempt', 'runtime_error')
    before = counter._value.get()
    with batch_privacy_attempt():
        assert check(db) == 7
        db.rows[TOMBSTONE] = {}
        with pytest.raises(privacy.BatchPrivacyBlocked, match='conversation_deleted'):
            check(db)
    assert counter._value.get() == before + 2


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


@pytest.mark.parametrize('shape', ['attempt', 'no_attempt', 'snapshots'])
@pytest.mark.parametrize(
    'kind,label',
    [
        (TimeoutError, 'timeout'),
        (ValueError, 'value_error'),
        (TypeError, 'type_error'),
    ],
)
def test_owner_shadow_errors_preserve_live_allow_and_block(world, monkeypatch, shape, kind, label):

    db, _, _, _ = world
    enable(monkeypatch, 'privacy_checks_shadow')

    def broken(*args, **kwargs):
        raise kind('synthetic-private-owner/content')

    monkeypatch.setattr(privacy, '_assert_batch_write_allowed_memo', broken)
    counter = metrics.OWNER_SHADOW_ERRORS.labels(shape, label)
    before = counter._value.get()
    denominator = metrics.SHADOW_CHECKS.labels('batch', 'error')
    owners = metrics.OWNER_COMPARISONS.labels(shape, 'error', 'unknown')
    denominator_before, owners_before = denominator._value.get(), owners._value.get()
    with batch_privacy_attempt() if shape == 'attempt' else nullcontext():
        kwargs = {'snapshots': {}} if shape == 'snapshots' else {}
        assert check(db, **kwargs) == 7
        db.rows[TOMBSTONE] = {}
        with pytest.raises(privacy.BatchPrivacyBlocked, match='conversation_deleted'):
            check(db, **kwargs)
    assert counter._value.get() == before + 2
    assert denominator._value.get() == denominator_before + 2
    assert owners._value.get() == owners_before + 2


@pytest.mark.parametrize('function', ['compare', 'owner_comparison'])
def test_owner_shadow_metrics_fault_is_not_a_candidate_error_or_live_failure(world, monkeypatch, function):
    db, _, _, _ = world
    enable(monkeypatch, 'privacy_checks_shadow')
    before = sum(
        sample.value
        for family in metrics.OWNER_SHADOW_ERRORS.collect()
        for sample in family.samples
        if sample.name == 'privacy_owner_shadow_error_total'
    )

    def broken(*args, **kwargs):
        raise TimeoutError('synthetic private metrics detail')

    monkeypatch.setattr(metrics, function, broken)
    assert check(db) == 7
    db.rows[TOMBSTONE] = {}
    with pytest.raises(privacy.BatchPrivacyBlocked, match='conversation_deleted'):
        check(db)
    assert (
        sum(
            sample.value
            for family in metrics.OWNER_SHADOW_ERRORS.collect()
            for sample in family.samples
            if sample.name == 'privacy_owner_shadow_error_total'
        )
        == before
    )


def kept(name, rules, component=''):
    labels = {'__name__': name, 'component': component}
    for rule in rules:
        matched = re.fullmatch(rule['regex'], ';'.join(labels.get(k, '') for k in rule['sourceLabels']))
        if rule['action'] == 'keep' and not matched or rule['action'] == 'drop' and matched:
            return False
    return True


@pytest.mark.parametrize('action,pattern', [('keep', 'other_metric'), ('drop', 'privacy_.*')])
def test_scrape_rule_evaluation_rejects_later_rule_drops(action, pattern):
    rules = [
        {'action': 'keep', 'sourceLabels': ['__name__'], 'regex': 'privacy_.*'},
        {'action': action, 'sourceLabels': ['__name__', 'component'], 'regex': pattern + ';worker'},
    ]
    assert not kept('privacy_owner_shadow_error_total', rules, component='worker')


@pytest.mark.parametrize('config_name', ['cloud_run_gmp_sidecar.yaml', 'cloud_run_gmp_sync.yaml'])
def test_owner_shadow_error_classes_are_closed_and_kept_by_cloud_run(config_name):

    class PrivateOwnerContentError(Exception):
        pass

    for error, label in (
        (exceptions.DeadlineExceeded('private'), 'deadline_exceeded'),
        (exceptions.Aborted('private'), 'aborted'),
        (exceptions.FailedPrecondition('private'), 'failed_precondition'),
        (exceptions.PermissionDenied('private'), 'permission_denied'),
        (exceptions.ResourceExhausted('private'), 'resource_exhausted'),
        (exceptions.ServiceUnavailable('private'), 'service_unavailable'),
        (exceptions.InvalidArgument('private'), 'invalid_argument'),
        (PrivateOwnerContentError('private'), 'other'),
    ):
        counter = metrics.OWNER_SHADOW_ERRORS.labels('other', label)
        before = counter._value.get()
        metrics.owner_shadow_error('private-shape', error)
        assert counter._value.get() == before + 1
    rendered = repr(list(metrics.OWNER_SHADOW_ERRORS.collect()))
    assert 'private' not in rendered.lower()
    config = yaml.safe_load((Path(__file__).parents[2] / 'deploy' / config_name).read_text())
    for endpoint in config['spec']['endpoints']:
        for metric in (
            'privacy_owner_shadow_error_total',
            'privacy_ttl_cache_disabled',
            'privacy_ttl_cache_switch_reads_total',
        ):
            assert kept(metric, endpoint['metricRelabeling'])


def test_owner_candidate_can_exhaust_shared_artifact_deadline_after_live_allow(world, monkeypatch):

    db, reads, _, _ = world
    enable(monkeypatch, 'privacy_checks_shadow', 'bpp_generation_memo', 'bpp_decision_cache')
    monkeypatch.setattr(artifact_reads, 'time', SimpleNamespace(monotonic=lambda: 1.0))
    budget = ArtifactReadBudget(deadline=3.0, max_bytes=0, max_objects=0)
    original = privacy._assert_batch_write_allowed_memo
    live_reads = []

    def expired_candidate(*args, **kwargs):
        assert kwargs['owner_candidate'] is True
        live_reads.extend(reads)
        budget.deadline = 0  # Expire when shadow enters, independent of live read count.
        return original(*args, **kwargs)

    monkeypatch.setattr(privacy, '_assert_batch_write_allowed_memo', expired_candidate)
    counter = metrics.OWNER_SHADOW_ERRORS.labels('attempt', 'artifact_read_limit')
    before = counter._value.get()
    with batch_privacy_attempt():
        assert check(db, read_budget=budget) == 7
    assert TOKEN in live_reads and SOURCE in live_reads
    assert reads == live_reads  # Failed candidate budget checks issue no SDK reads.
    assert counter._value.get() == before + 1
