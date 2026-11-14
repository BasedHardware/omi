"""Token-certified privacy reuse: a 60s upper bound never substitutes for the revoke fence."""

from datetime import datetime, timezone, timedelta
from functools import partial
import json
from types import SimpleNamespace

import fakeredis
from google.api_core.exceptions import Aborted
import pytest

from database import account_deletion_marker as marker
from database import batch_pipeline_privacy as privacy, conversation_tombstones as tombstones
from database import batch_pipeline_store as storage
from database import fsr_read_cache as cache, legal_holds, privacy_check_metrics as metrics
from database import privacy_negative_cache as negative, privacy_ttl_cache as ttl_cache
from database.batch_privacy_attempt import batch_privacy_attempt, current_attempt
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore, StrictFirestoreDocument

UID = 'privacy-ttl-owner'
TOKEN = ('batch_pipeline_privacy', privacy.privacy_owner_key(UID))
SOURCE = ('users', UID, 'conversations', 'source')
OTHER = ('users', UID, 'conversations', 'other')
TOMBSTONE = ('users', UID, 'deleted_conversations', 'source')
MARKER = ('account_deletions', UID)


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


@pytest.fixture
def world(monkeypatch):
    db = StrictFirestore(
        {
            ('users', UID): {'data_protection_level': 'standard'},
            SOURCE: {'record_lane_owner': 'batch_live_v1', 'private_cloud_sync_enabled': True},
            OTHER: {'record_lane_owner': 'batch_live_v1', 'private_cloud_sync_enabled': True},
            TOKEN: {'memo_token': 'a' * 32, 'memo_schema': 1, 'generation': 7},
        }
    )
    reads = []
    revision = [datetime(2026, 11, 4, tzinfo=timezone.utc)]
    original = StrictFirestoreDocument.get

    def get(ref, **kwargs):
        reads.append(ref.path)
        result = original(ref, **kwargs)
        result.update_time = revision[0] if result.exists else None
        return result

    clock = Clock()
    monkeypatch.setattr(StrictFirestoreDocument, 'get', get)
    monkeypatch.setattr(tombstones, 'db', db)
    monkeypatch.setattr(cache, '_redis', lambda: redis)
    monkeypatch.setattr(ttl_cache.DECISIONS, 'clock', clock)
    monkeypatch.setattr(privacy.PROCESS_DECISIONS, 'clock', clock)
    monkeypatch.setattr(privacy.PROCESS_OWNERS, 'clock', clock)
    # These tests pin the id-set memo paths; the owner-level memo (default on in
    # production) has its own section below and is disabled here explicitly.
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"bpp_owner_memo": 0}')
    ttl_cache.reset_for_tests()
    monkeypatch.setattr(ttl_cache, '_read_kill_flag', lambda: False)
    privacy.PROCESS_DECISIONS.clear()
    privacy.PROCESS_OWNERS.clear()
    redis = fakeredis.FakeRedis()
    yield db, reads, revision, clock
    ttl_cache.DECISIONS.clear()
    privacy.PROCESS_DECISIONS.clear()
    privacy.PROCESS_OWNERS.clear()
    redis.close()


def enable(monkeypatch, *names):
    levers = dict.fromkeys(names, 100)
    levers.setdefault('bpp_owner_memo', 0)  # id-set tests; owner tests name it explicitly
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', json.dumps(levers))


def external(db):
    with legal_holds.external_write_fence(UID, firestore_client=db):
        return True


def check(db, ids=('source',)):
    return privacy.assert_batch_write_allowed(db, db.transaction(), UID, conversation_ids=list(ids))


# --- the bound itself ---------------------------------------------------------


def test_reuse_window_is_the_ruling_bound():
    assert ttl_cache.ttl_seconds() == ttl_cache.MAX_SECONDS == metrics.TTL_BOUND_SECONDS == 60


def test_entry_expires_sixty_seconds_after_the_read_started():
    clock = Clock()
    store = ttl_cache.BoundedTTLCache(clock=clock)
    started = clock.now
    clock.now += 5  # a slow read must not extend the bound
    assert store.put('k', True, started=started)
    clock.now = started + 59.999
    value, age = store.get('k')
    assert value is True and age == pytest.approx(59.999)
    clock.now = started + 60
    assert ttl_cache.is_missing(store.get('k')[0])
    # A read that took longer than the bound is never stored at all.
    assert not store.put('late', True, started=clock.now - 61)
    assert ttl_cache.is_missing(store.get('late')[0])


def test_cache_is_lru_bounded():
    clock = Clock()
    store = ttl_cache.BoundedTTLCache(max_entries=2, clock=clock)
    for key in 'abc':
        store.put(key, True, started=clock.now)
    assert len(store) == 2 and ttl_cache.is_missing(store.get('a')[0])


# --- tombstones -------------------------------------------------------------------


def test_tombstone_clear_requires_current_token_even_within_sixty_seconds(world, monkeypatch):
    db, reads, revision, clock = world
    enable(monkeypatch, 'privacy_ttl60')
    assert not tombstones.is_deleted(UID, 'source')
    assert len(reads) == 2
    assert not tombstones.is_deleted(UID, 'source')
    assert len(reads) == 3  # reuse still reads the authority token
    db.rows[TOMBSTONE] = {}
    db.rows[TOKEN]['memo_token'] = 'b' * 32
    revision[0] += timedelta(seconds=1)
    clock.now += 1
    assert tombstones.is_deleted(UID, 'source')
    reads.clear()
    assert tombstones.is_deleted(UID, 'source')
    assert tombstones.is_deleted(UID, 'source')
    assert reads == [TOKEN, TOMBSTONE] * 2  # BLOCK is never stored


def test_tombstone_cache_never_answers_for_another_conversation_or_plane(world, monkeypatch):
    db, reads, _, _ = world
    enable(monkeypatch, 'privacy_ttl60')
    assert not tombstones.is_deleted(UID, 'source')
    db.rows[('users', UID, 'deleted_conversations', 'other')] = {}
    assert tombstones.is_deleted(UID, 'other')
    assert tombstones.is_deleted(UID, 'other')
    assert not tombstones.is_deleted(UID, 'source')
    other_plane = StrictFirestore({})
    assert ttl_cache.DECISIONS.get(negative._ttl_key('tombstone', UID, db, 'source'))[0]['clear'] is True
    assert ttl_cache.is_missing(ttl_cache.DECISIONS.get(negative._ttl_key('tombstone', UID, other_plane, 'source'))[0])


def test_lever_off_keeps_every_read_live(world):
    _, reads, _, _ = world
    for _ in range(3):
        assert not tombstones.is_deleted(UID, 'source')
    assert len(reads) == 3


# --- legal-hold / deletion external write fence -------------------------------


def test_external_fence_reuses_clear_and_never_caches_a_block(world, monkeypatch):
    db, reads, _, clock = world
    enable(monkeypatch, 'privacy_ttl60')
    assert external(db)
    assert len(reads) == 3
    assert external(db)
    assert len(reads) == 4
    db.rows[MARKER] = {'wipe_status': 'pending'}
    clock.now += 60
    reads.clear()
    for _ in range(2):
        with pytest.raises(legal_holds.DestructiveOperationInProgress):
            external(db)
    assert len(reads) == 4  # every blocked decision reads token plus marker


def test_external_fence_inside_a_transaction_always_reads_live(world, monkeypatch):
    db, reads, _, _ = world
    enable(monkeypatch, 'privacy_ttl60')
    assert external(db)
    reads.clear()
    transaction = db.transaction()
    with legal_holds.external_write_fence(UID, firestore_client=db, transaction=transaction):
        pass
    assert len(reads) == 2


def test_gate_owner_pass_is_never_cached_for_other_writers(world, monkeypatch):
    """The owning request may write through its own running gate; that pass must never be reused by others."""
    import contextvars

    db, reads, _, _ = world
    enable(monkeypatch, 'privacy_ttl60')

    def fresh_writer():
        with legal_holds.external_write_fence(UID, firestore_client=db):
            raise AssertionError('a writer outside the owning request must stay fenced')

    with legal_holds.destructive_operation_gate(UID, firestore_client=db):
        for _ in range(2):
            with legal_holds.external_write_fence(UID, firestore_client=db):
                pass
        for _ in range(3):
            reads.clear()
            with pytest.raises(legal_holds.DestructiveOperationInProgress):
                contextvars.Context().run(fresh_writer)
            # Live marker + gate reads every time: no cached owner pass.
            assert MARKER in reads and ('legal_hold_deletion_gates', UID) in reads


@pytest.mark.parametrize('cache_lever', ['legal_hold_fence_cache', 'privacy_ttl60'])
def test_external_revoke_then_check_blocks_cached_allow_within_ttl(world, monkeypatch, cache_lever):
    """P0 qualification: a committed revoke must fence an already cached ALLOW."""
    db, reads, revision, clock = world
    enable(monkeypatch, cache_lever)
    assert external(db)
    # Prime and prove reuse before revocation, without depending on Redis TTL time.
    reads.clear()
    assert external(db)
    assert reads == [TOKEN]

    # Model the completed authority commit, including the writer's same-commit
    # token rotation and a new server revision. No write is left in flight.
    db.rows[MARKER] = {'wipe_status': 'pending'}
    db.rows[TOKEN] = {**db.rows[TOKEN], 'memo_token': 'b' * 32, 'generation': 8}
    revision[0] += timedelta(seconds=1)
    clock.now += 1

    # Control: the real live fence sees this marker and blocks immediately.
    with pytest.raises(legal_holds.DestructiveOperationInProgress):
        with legal_holds.external_write_fence(UID, firestore_client=db, transaction=db.transaction()):
            pytest.fail('live authority incorrectly allowed the revoked account')

    reads.clear()
    try:
        external(db)
    except legal_holds.DestructiveOperationInProgress:
        assert MARKER in reads
    else:
        pytest.fail(
            f'{cache_lever} returned cached ALLOW 1s after revoke despite rotated token/generation; '
            f'authority reads after revoke: {len(reads)}'
        )


# --- deletion marker ----------------------------------------------------------


def test_shadow_rejects_rotated_token_within_bound_and_emits_cache_evidence(world, monkeypatch):
    db, _, revision, clock = world
    enable(monkeypatch, 'privacy_checks_shadow', 'privacy_ttl60')
    assert not tombstones.is_deleted(UID, 'source')
    db.rows[TOMBSTONE] = {}
    db.rows[TOKEN]['memo_token'] = 'b' * 32
    revision[0] += timedelta(seconds=1)
    clock.now += 30
    counter = metrics.COMPARISONS.labels(
        'tombstone', 'match', 'fresh_read', '30_60s', 'same', 'same', 'false', 'mismatch'
    )
    before = counter._value.get()
    assert tombstones.is_deleted(UID, 'source')
    assert counter._value.get() == before + 1


@pytest.mark.parametrize('age', [1, 60.5])
def test_compare_never_excuses_a_stale_allow_based_on_age(age):
    before = metrics.DECISION_MISMATCH.labels('external', 'stale_allow')._value.get()
    metrics.compare('external', 'destructive_operation', 'allow', cached_age=age)
    assert metrics.DECISION_MISMATCH.labels('external', 'stale_allow')._value.get() == before + 1


def test_batch_generation_is_reused_across_attempts_with_one_token_read(world, monkeypatch):
    db, reads, _, _ = world
    enable(monkeypatch, 'bpp_generation_memo', 'bpp_decision_cache')
    with batch_privacy_attempt():
        assert check(db) == 7
    assert len(reads) == 5
    reads.clear()
    with batch_privacy_attempt():
        assert check(db) == 7
    assert reads == [TOKEN]


def test_batch_reuse_misses_after_any_token_rotation(world, monkeypatch):
    db, reads, revision, _ = world
    enable(monkeypatch, 'bpp_generation_memo', 'bpp_decision_cache')
    with batch_privacy_attempt():
        check(db)
    # An authority writer commits a new token (same commit as its write).
    db.rows[TOKEN] = {**db.rows[TOKEN], 'memo_token': 'b' * 32}
    db.rows[TOMBSTONE] = {}
    revision[0] += timedelta(seconds=1)
    reads.clear()
    with batch_privacy_attempt():
        with pytest.raises(privacy.BatchPrivacyBlocked, match='conversation_deleted'):
            check(db)
    assert len(reads) > 1


def test_batch_reuse_expires_after_sixty_seconds_and_keys_on_conversation_set(world, monkeypatch):
    db, reads, _, clock = world
    enable(monkeypatch, 'bpp_generation_memo', 'bpp_decision_cache')
    with batch_privacy_attempt():
        check(db)
        reads.clear()
        clock.now += 1
    with batch_privacy_attempt():
        check(db, ids=('source', 'other'))  # a different set walks again
    assert len(reads) > 1
    clock.now += 60
    reads.clear()
    with batch_privacy_attempt():
        check(db)
    assert len(reads) == 5


def test_batch_reuse_honours_expected_generation_and_lever_off(world, monkeypatch):
    db, reads, _, _ = world
    enable(monkeypatch, 'bpp_generation_memo', 'bpp_decision_cache')
    with batch_privacy_attempt():
        check(db)
    with batch_privacy_attempt():
        with pytest.raises(privacy.BatchPrivacyBlocked, match='privacy_generation_changed'):
            privacy.assert_batch_write_allowed(
                db, db.transaction(), UID, conversation_ids=['source'], expected_generation=8
            )
    enable(monkeypatch, 'bpp_generation_memo')
    reads.clear()
    with batch_privacy_attempt():
        check(db)
    assert len(reads) == 5


def test_batch_shadow_compares_cached_candidate_against_live(world, monkeypatch):
    db, _, _, _ = world
    enable(monkeypatch, 'privacy_checks_shadow', 'bpp_generation_memo', 'bpp_decision_cache')
    before = metrics.SHADOW_CHECKS.labels('batch', 'match')._value.get()
    with batch_privacy_attempt():
        assert check(db) == 7
    with batch_privacy_attempt():
        assert check(db) == 7
    assert metrics.SHADOW_CHECKS.labels('batch', 'match')._value.get() == before + 2


# --- runtime kill switch ---------------------------------------------------------


def test_kill_switch_turns_every_cache_off_without_a_deploy(world, monkeypatch):
    db, reads, _, _ = world
    enable(monkeypatch, 'privacy_ttl60', 'bpp_generation_memo', 'bpp_decision_cache')
    assert not tombstones.is_deleted(UID, 'source')
    with batch_privacy_attempt():
        check(db)
    killed = [True]
    monkeypatch.setattr(ttl_cache, '_read_kill_flag', lambda: killed[0])
    ttl_cache.reset_for_tests()
    reads.clear()
    assert not tombstones.is_deleted(UID, 'source')
    assert not tombstones.is_deleted(UID, 'source')
    with batch_privacy_attempt():
        check(db)
    assert len(reads) == 2 + 5  # every decision read live
    assert len(ttl_cache.DECISIONS) == 0


def test_unreadable_kill_switch_fails_closed_and_is_polled_at_most_every_interval(monkeypatch):
    calls = []

    def broken():
        calls.append(1)
        raise RuntimeError('firestore unavailable')

    ttl_cache.reset_for_tests()
    monkeypatch.setattr(ttl_cache, '_read_kill_flag', broken)
    assert ttl_cache.disabled() and ttl_cache.disabled()
    assert len(calls) == 1
    ttl_cache.reset_for_tests()


def test_privacy_ttl60_leaves_the_deletion_marker_on_its_shared_redis_cache(world, monkeypatch):
    """Cost regression 2026-11-04 22:13Z: per-process 60s reuse of the marker missed ~30% on Cloud Run
    and forced direct reads, 10x the shared Redis negative cache's reads. The marker never uses privacy_ttl60."""
    db, reads, _, _ = world
    enable(monkeypatch, 'deletion_marker_cache', 'privacy_ttl60')
    for _ in range(5):
        assert marker.get_user_deletion_wipe_status(UID, firestore_client=db) is None
    assert len(reads) == 1  # the Redis negative cache answered the repeats
    assert len(ttl_cache.DECISIONS) == 0


@pytest.mark.parametrize('change', ['missing', 'malformed', 'unreadable', 'revision', 'generation', 'legacy'])
def test_uncertified_ttl_allow_falls_through_to_live_block(world, monkeypatch, change):
    db, reads, revision, clock = world
    enable(monkeypatch, 'privacy_ttl60')
    assert external(db)
    db.rows[MARKER] = {'wipe_status': 'pending'}
    if change == 'missing':
        del db.rows[TOKEN]
    elif change == 'malformed':
        db.rows[TOKEN]['memo_token'] = 'bad'
    elif change == 'unreadable':

        def broken(*args):
            raise RuntimeError('synthetic token read outage')

        monkeypatch.setattr(negative, '_certificate', broken)
    elif change == 'revision':
        revision[0] += timedelta(seconds=1)  # same opaque token, new server revision
    elif change == 'generation':
        db.rows[TOKEN]['generation'] = 8  # mutation proof even if the revision fake is unchanged
    else:
        ttl_cache.DECISIONS.put(negative._ttl_key('external', UID, db, 'external'), True, started=clock.now)
    clock.now += 1
    reads.clear()
    with pytest.raises(legal_holds.DestructiveOperationInProgress):
        external(db)
    assert MARKER in reads


@pytest.mark.parametrize('first_block', [True, False])
def test_fresh_comparison_race_preserves_live_and_labels_marker_transition(world, monkeypatch, caplog, first_block):
    db, _, revision, _ = world
    enable(monkeypatch, 'privacy_checks_shadow')
    if first_block:
        db.rows[MARKER] = {'wipe_status': 'pending'}
    original = StrictFirestoreDocument.get
    changed = False

    def get(ref, **kwargs):
        nonlocal changed
        snapshot = original(ref, **kwargs)
        if ref.path == MARKER and not changed:
            changed = True
            if first_block:
                db.rows.pop(MARKER)
            else:
                db.rows[MARKER] = {'wipe_status': 'pending'}
            db.rows[TOKEN].update(memo_token='b' * 32, generation=8)
            revision[0] += timedelta(seconds=1)
        return snapshot

    monkeypatch.setattr(StrictFirestoreDocument, 'get', get)
    labels = ('external', 'mismatch', 'fresh_read', 'unknown', 'changed', 'changed', 'true', 'miss')
    counter = metrics.COMPARISONS.labels(*labels)
    before = counter._value.get()
    metrics._LOG_AT.clear()
    with caplog.at_level('WARNING'):
        if first_block:
            with pytest.raises(legal_holds.DestructiveOperationInProgress):
                external(db)
        else:
            assert external(db)
    assert counter._value.get() == before + 1
    assert ('reason=stale_allow' if first_block else 'reason=stale_block') in caplog.text
    for field in (
        'candidate_source=fresh_read',
        'cache_age=unknown',
        'token_versions=changed',
        'generation_versions=changed',
        'marker_changed=true',
        'cache_certification=miss',
    ):
        assert field in caplog.text
    assert UID not in caplog.text and 'b' * 32 not in caplog.text


@pytest.mark.parametrize('source', ['ttl_hit', 'token_hit', 'session_hit'])
def test_cached_comparison_evidence_and_rate_limit_for_unfenced_writer(world, monkeypatch, caplog, source):
    db, _, _, clock = world
    enable(monkeypatch, 'privacy_checks_shadow', *(['privacy_ttl60'] if source == 'ttl_hit' else []))
    monkeypatch.setattr(negative, 'time', SimpleNamespace(time=clock))
    holder = metrics.SessionCensus('listen') if source == 'session_hit' else None
    token = metrics._SESSION.set(holder)
    try:
        assert external(db)
        # Deliberately bypass the mandatory Commit token hook: shadow must
        # expose a genuine cached stale ALLOW, never excuse it due to age.
        db.rows[MARKER] = {'wipe_status': 'pending'}
        clock.now += 2
        counter = metrics.COMPARISONS.labels('external', 'mismatch', source, '1_10s', 'same', 'same', 'true', 'matched')
        before = counter._value.get()
        metrics._LOG_AT.clear()
        with caplog.at_level('WARNING'):
            for _ in range(2):
                with pytest.raises(legal_holds.DestructiveOperationInProgress):
                    external(db)
        assert counter._value.get() == before + 2
        assert caplog.text.count('privacy shadow decision_mismatch') == 1
        assert f'candidate_source={source}' in caplog.text
        assert 'reason=stale_allow' in caplog.text and 'marker_changed=true' in caplog.text
        assert UID not in caplog.text and 'a' * 32 not in caplog.text
    finally:
        if holder:
            holder.memo.close()
        metrics._SESSION.reset(token)


@pytest.mark.parametrize('invalid', [True, (None, 7), ('legacy', 7), ({'bad': True}, 7, {})])
def test_batch_uncertified_process_entry_cannot_allow_revoked_owner(world, monkeypatch, invalid):
    db, reads, _, clock = world
    enable(monkeypatch, 'bpp_generation_memo', 'bpp_decision_cache')
    key = (db, UID, frozenset({'source'}))
    privacy.PROCESS_DECISIONS.put(key, invalid, started=clock.now)
    db.rows[MARKER] = {'wipe_status': 'pending'}
    with batch_privacy_attempt(), pytest.raises(privacy.BatchPrivacyBlocked, match='account_deleted'):
        check(db)
    assert TOKEN in reads and MARKER in reads


def test_batch_revoke_within_ttl_is_a_live_block_after_token_rotation(world, monkeypatch):
    db, reads, revision, clock = world
    enable(monkeypatch, 'bpp_generation_memo', 'bpp_decision_cache')
    with batch_privacy_attempt():
        assert check(db) == 7
    db.rows[MARKER] = {'wipe_status': 'pending'}
    db.rows[TOKEN].update(memo_token='b' * 32, generation=8)
    revision[0] += timedelta(seconds=1)
    clock.now += 1
    reads.clear()
    with batch_privacy_attempt(), pytest.raises(privacy.BatchPrivacyBlocked, match='account_deleted'):
        check(db)
    assert reads == [TOKEN, MARKER]


def test_batch_certificate_outage_falls_through_to_live_marker(world, monkeypatch):
    db, reads, _, _ = world
    enable(monkeypatch, 'bpp_generation_memo', 'bpp_decision_cache')
    with batch_privacy_attempt():
        assert check(db) == 7
    db.rows[MARKER] = {'wipe_status': 'pending'}
    original = StrictFirestoreDocument.get

    def get(ref, **kwargs):
        if ref.path == TOKEN:
            reads.append(ref.path)
            raise RuntimeError('synthetic certificate outage')
        return original(ref, **kwargs)

    monkeypatch.setattr(StrictFirestoreDocument, 'get', get)
    reads.clear()
    with batch_privacy_attempt(), pytest.raises(privacy.BatchPrivacyBlocked, match='account_deleted'):
        check(db)
    assert reads == [TOKEN, MARKER]


def test_evidence_fields_never_emit_supplied_identifiers(caplog):
    unsafe = 'owner@example.test/raw-token-or-document-path'
    evidence = metrics.DecisionEvidence(
        source=unsafe, certification=unsafe, token_seen=True, token=unsafe, generation=unsafe, markers={unsafe: unsafe}
    )
    metrics._LOG_AT.clear()
    with caplog.at_level('WARNING'):
        metrics.compare(unsafe, unsafe, 'allow', live_evidence=evidence, candidate_evidence=evidence)
    assert unsafe not in caplog.text
    assert unsafe not in repr(metrics.COMPARISONS.collect())
    assert 'candidate_source=unknown' in caplog.text
    assert 'token_versions=same' in caplog.text and 'generation_versions=same' in caplog.text


def test_session_allow_reuse_has_a_sixty_second_upper_bound(world, monkeypatch):
    db, reads, _, clock = world
    enable(monkeypatch, 'privacy_session_token')
    wall = [1000.0]
    monkeypatch.setattr(negative, 'time', SimpleNamespace(time=lambda: wall[0]))
    holder = metrics.SessionCensus('listen')
    token = metrics._SESSION.set(holder)
    try:
        assert external(db)
        clock.now += 60
        wall[0] -= 3600  # a backwards wall clock must not extend authorization
        # Force Redis unavailable so an expired session entry must read live.
        monkeypatch.setattr(cache, '_redis', lambda: None)
        reads.clear()
        assert external(db)
        assert MARKER in reads
    finally:
        holder.memo.close()
        metrics._SESSION.reset(token)


@pytest.mark.parametrize('token', [None, {}, {'memo_token': 'bad', 'memo_schema': 1}])
def test_ttl_missing_certificate_allows_only_fresh_authority_and_never_stores(world, monkeypatch, token):
    db, reads, _, _ = world
    enable(monkeypatch, 'privacy_ttl60')
    if token is None:
        db.rows.pop(TOKEN)
    else:
        db.rows[TOKEN] = token
    assert external(db) and external(db)
    assert reads == [TOKEN, MARKER, ('legal_hold_deletion_gates', UID)] * 2
    assert len(ttl_cache.DECISIONS) == 0


def test_delayed_redis_hit_cannot_extend_the_sixty_second_bound(world, monkeypatch):
    db, reads, revision, clock = world
    enable(monkeypatch, 'legal_hold_fence_cache')
    assert external(db)
    original = negative.cached_read

    def delayed(*args, **kwargs):
        value = original(*args, **kwargs)
        # The server returned the old clear before this completed revoke, but
        # its reply reaches the caller another 30 seconds later.
        db.rows[MARKER] = {'wipe_status': 'pending'}
        db.rows[TOKEN].update(memo_token='b' * 32, generation=8)
        revision[0] += timedelta(seconds=1)
        clock.now += 30
        return value

    monkeypatch.setattr(negative, 'cached_read', delayed)
    reads.clear()
    with pytest.raises(legal_holds.DestructiveOperationInProgress):
        external(db)
    assert reads == [TOKEN, MARKER]


# --- no-attempt transactional process-cache eligibility -----------------------


def test_no_attempt_transactional_cold_walk_then_certified_warm_reuse(world, monkeypatch):
    db, reads, _, _ = world
    enable(monkeypatch, 'bpp_generation_memo', 'bpp_decision_cache')
    assert current_attempt() is None
    assert check(db) == 7
    assert len(reads) == 5  # token plus the full live walk
    assert current_attempt() is None
    assert len(privacy.PROCESS_DECISIONS) == 1
    reads.clear()
    assert check(db) == 7
    assert reads == [TOKEN]  # certified by this transaction's fresh token read
    assert current_attempt() is None


def test_no_attempt_revoke_before_check_rotates_token_and_blocks(world, monkeypatch):
    db, reads, revision, clock = world
    enable(monkeypatch, 'bpp_generation_memo', 'bpp_decision_cache')
    assert check(db) == 7
    db.rows[MARKER] = {'wipe_status': 'pending'}
    db.rows[TOKEN].update(memo_token='b' * 32, generation=8)
    revision[0] += timedelta(seconds=1)
    clock.now += 1
    reads.clear()
    with pytest.raises(privacy.BatchPrivacyBlocked, match='account_deleted'):
        check(db)
    assert reads == [TOKEN, MARKER]
    assert len(privacy.PROCESS_DECISIONS) == 0  # BLOCK is never cached


def test_no_attempt_nontransactional_never_consults_process_cache(world, monkeypatch):
    db, reads, _, _ = world
    enable(monkeypatch, 'bpp_generation_memo', 'bpp_decision_cache')

    def fail(*args, **kwargs):
        raise AssertionError('process cache consulted for a nontransactional check')

    monkeypatch.setattr(privacy.PROCESS_DECISIONS, 'get', fail)
    monkeypatch.setattr(privacy, 'ttl_enabled', fail)
    db.rows[MARKER] = {'wipe_status': 'pending'}
    reads.clear()
    with pytest.raises(privacy.BatchPrivacyBlocked, match='account_deleted'):
        privacy.assert_batch_write_allowed(db, None, UID, conversation_ids=['source'])
    assert MARKER in reads


def test_no_attempt_snapshots_export_never_consults_or_populates_process_cache(world, monkeypatch):
    db, reads, _, _ = world
    enable(monkeypatch, 'bpp_generation_memo', 'bpp_decision_cache')

    def fail(*args, **kwargs):
        raise AssertionError('process cache consulted for a snapshots export')

    monkeypatch.setattr(privacy.PROCESS_DECISIONS, 'get', fail)
    monkeypatch.setattr(privacy.PROCESS_DECISIONS, 'put', fail)
    monkeypatch.setattr(privacy, 'ttl_enabled', fail)
    output = {}
    assert (
        privacy.assert_batch_write_allowed(db, db.transaction(), UID, conversation_ids=['source'], snapshots=output)
        == 7
    )
    assert output['conversations']['source']['record_lane_owner'] == 'batch_live_v1'
    assert len(privacy.PROCESS_DECISIONS) == 0


def test_no_attempt_lever_off_stays_live_and_ineligible(world, monkeypatch):
    db, reads, _, _ = world
    enable(monkeypatch, 'bpp_generation_memo')
    before = metrics.MEMO_INELIGIBLE.labels('no_attempt', 'other')._value.get()
    for _ in range(2):
        assert check(db) == 7
    assert len(reads) == 10  # every decision reads live
    assert metrics.MEMO_INELIGIBLE.labels('no_attempt', 'other')._value.get() == before + 2
    assert len(privacy.PROCESS_DECISIONS) == 0


def test_no_attempt_expected_generation_mismatch_stays_live(world, monkeypatch):
    db, reads, _, _ = world
    enable(monkeypatch, 'bpp_generation_memo', 'bpp_decision_cache')
    assert check(db) == 7
    reads.clear()
    with pytest.raises(privacy.BatchPrivacyBlocked, match='privacy_generation_changed'):
        privacy.assert_batch_write_allowed(
            db, db.transaction(), UID, conversation_ids=['source'], expected_generation=8
        )
    # Token plus the live walk up to the generation check; never a cached ALLOW.
    assert reads == [TOKEN, MARKER, ('users', UID)]


def test_no_attempt_certificate_outage_falls_through_to_live_marker(world, monkeypatch):
    db, reads, _, _ = world
    enable(monkeypatch, 'bpp_generation_memo', 'bpp_decision_cache')
    assert check(db) == 7
    db.rows[MARKER] = {'wipe_status': 'pending'}
    original = StrictFirestoreDocument.get

    def get(ref, **kwargs):
        if ref.path == TOKEN:
            reads.append(ref.path)
            raise RuntimeError('synthetic certificate outage')
        return original(ref, **kwargs)

    monkeypatch.setattr(StrictFirestoreDocument, 'get', get)
    reads.clear()
    with pytest.raises(privacy.BatchPrivacyBlocked, match='account_deleted'):
        check(db)
    assert reads == [TOKEN, MARKER]


def test_no_attempt_concurrent_revoke_aborts_then_retries_into_live_block(world, monkeypatch):
    db, reads, revision, clock = world
    enable(monkeypatch, 'bpp_generation_memo', 'bpp_decision_cache')
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    store = storage.FirestoreStore('batch_pipeline_dev', firestore_client=db)
    monkeypatch.setattr(storage, 'contention_retry_enabled', lambda: True)
    monkeypatch.setattr(
        storage,
        'run_with_transaction_contention_retry',
        partial(storage.run_with_transaction_contention_retry, sleep=lambda delay: None, random_value=lambda: 0.0),
    )
    # Cold walk populates the process cache for this owner.
    assert store.run(lambda view: view.check_privacy(UID, ['source'], 7)) == 7
    assert current_attempt() is None
    transactions_before = len(db.transactions)
    original_transaction = db.transaction
    commits = []

    def transaction(max_attempts=None):
        tx = original_transaction(max_attempts=max_attempts)

        def commit():
            commits.append(True)
            if len(commits) == 1:
                # A concurrent revoke commits between this transaction's token
                # read and its commit, so Firestore aborts the whole attempt.
                db.rows[MARKER] = {'wipe_status': 'pending'}
                db.rows[TOKEN].update(memo_token='b' * 32, generation=8)
                revision[0] += timedelta(seconds=1)
                clock.now += 1
                raise Aborted('synthetic concurrent revoke')

        monkeypatch.setattr(tx, '_commit', commit)
        return tx

    monkeypatch.setattr(db, 'transaction', transaction)
    reads.clear()
    with pytest.raises(privacy.BatchPrivacyBlocked, match='account_deleted'):
        store.run(lambda view: view.check_privacy(UID, ['source'], 7))
    assert len(commits) == 1
    assert len(db.transactions) - transactions_before == 2  # fresh transaction on retry
    assert reads == [TOKEN, TOKEN, MARKER]  # warm hit aborted, retry walks live
    assert current_attempt() is None


# --- owner-level memo (bpp_owner_memo, default on) ---------------------------


def owner_enable(monkeypatch, *names):
    levers = dict.fromkeys(names, 100)
    levers['bpp_owner_memo'] = 100
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', json.dumps(levers))


def test_owner_memo_is_on_by_default(world, monkeypatch):
    db, reads, _, _ = world
    monkeypatch.delenv('FIRESTORE_READ_LEVERS', raising=False)
    with batch_privacy_attempt():
        assert check(db) == 7
        reads.clear()
        assert check(db) == 7
    assert reads == [TOKEN]


def test_owner_memo_serves_repeat_checks_and_verifies_only_new_ids(world, monkeypatch):
    db, reads, _, _ = world
    owner_enable(monkeypatch)
    with batch_privacy_attempt():
        assert check(db) == 7
        assert len(reads) == 5  # token plus the full live walk
        reads.clear()
        assert check(db) == 7
        assert reads == [TOKEN]  # certified by this transaction's fresh token read
        reads.clear()
        assert check(db, ids=('source', 'other')) == 7
        # The certified id is not walked again; the new id pays its own two reads.
        assert reads == [TOKEN, ('users', UID, 'deleted_conversations', 'other'), OTHER]


def test_owner_memo_never_serves_a_block(world, monkeypatch):
    db, reads, revision, clock = world
    owner_enable(monkeypatch)
    with batch_privacy_attempt():
        assert check(db) == 7
    db.rows[TOMBSTONE] = {}
    db.rows[TOKEN].update(memo_token='b' * 32)
    revision[0] += timedelta(seconds=1)
    clock.now += 1
    reads.clear()
    with batch_privacy_attempt():
        with pytest.raises(privacy.BatchPrivacyBlocked, match='conversation_deleted'):
            check(db)
    assert len(privacy.PROCESS_OWNERS) == 0  # BLOCK is never stored


def test_owner_memo_kill_switch_forces_the_live_walk(world, monkeypatch):
    db, reads, _, _ = world
    owner_enable(monkeypatch)
    with batch_privacy_attempt():
        assert check(db) == 7
    monkeypatch.setattr(ttl_cache, '_read_kill_flag', lambda: True)
    ttl_cache.reset_for_tests()
    reads.clear()
    with batch_privacy_attempt():
        assert check(db) == 7
    assert len(reads) == 5


def test_owner_memo_expected_generation_mismatch_walks_live(world, monkeypatch):
    db, reads, _, _ = world
    owner_enable(monkeypatch)
    with batch_privacy_attempt():
        assert check(db) == 7
    reads.clear()
    with batch_privacy_attempt():
        with pytest.raises(privacy.BatchPrivacyBlocked, match='privacy_generation_changed'):
            privacy.assert_batch_write_allowed(
                db, db.transaction(), UID, conversation_ids=['source'], expected_generation=8
            )
    assert reads == [TOKEN, MARKER, ('users', UID)]


def test_owner_memo_serves_a_snapshots_call_without_exporting_rows(world, monkeypatch):
    db, reads, _, _ = world
    owner_enable(monkeypatch)
    with batch_privacy_attempt():
        assert check(db) == 7
    output = {}
    reads.clear()
    with batch_privacy_attempt():
        assert (
            privacy.assert_batch_write_allowed(db, db.transaction(), UID, conversation_ids=['source'], snapshots=output)
            == 7
        )
    assert reads == [TOKEN]
    assert output == {}  # the caller reads the rows it needs itself


# --- owner-level memo (lever bpp_owner_memo, default on) -------------------------


def owner_enable(monkeypatch, *names):
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', json.dumps(dict.fromkeys(('bpp_owner_memo', *names), 100)))


def test_owner_memo_repeat_check_reads_only_the_token(world, monkeypatch):
    db, reads, _, _ = world
    owner_enable(monkeypatch)
    assert check(db) == 7
    assert reads == [TOKEN, MARKER, ('users', UID), TOMBSTONE, SOURCE]
    reads.clear()
    assert check(db) == 7
    assert reads == [TOKEN]  # certified by this transaction's fresh token read


def test_owner_memo_new_id_sets_verify_only_the_new_ids(world, monkeypatch):
    db, reads, _, _ = world
    owner_enable(monkeypatch)
    assert check(db) == 7
    reads.clear()
    OTHER_TOMB = ('users', UID, 'deleted_conversations', 'other')
    assert check(db, ids=('other',)) == 7
    assert reads == [TOKEN, OTHER_TOMB, OTHER]
    reads.clear()
    assert check(db, ids=('source', 'other')) == 7
    assert reads == [TOKEN]  # the certified union now covers both sets


def test_owner_memo_revoke_rotates_token_and_blocks_live(world, monkeypatch):
    db, reads, revision, clock = world
    owner_enable(monkeypatch)
    assert check(db) == 7
    db.rows[MARKER] = {'wipe_status': 'pending'}
    db.rows[TOKEN].update(memo_token='b' * 32, generation=8)
    revision[0] += timedelta(seconds=1)
    clock.now += 1
    reads.clear()
    with pytest.raises(privacy.BatchPrivacyBlocked, match='account_deleted'):
        check(db)
    assert reads == [TOKEN, MARKER]
    assert len(privacy.PROCESS_OWNERS) == 0  # BLOCK is never cached


def test_owner_memo_tombstone_on_a_new_id_blocks_and_forgets(world, monkeypatch):
    db, reads, _, _ = world
    owner_enable(monkeypatch)
    # The tombstone predates the certified walk, so the token stays valid and
    # only the new id's own verification can catch it.
    db.rows[('users', UID, 'deleted_conversations', 'other')] = {}
    assert check(db, ids=('source',)) == 7
    reads.clear()
    with pytest.raises(privacy.BatchPrivacyBlocked, match='conversation_deleted'):
        check(db, ids=('other',))
    assert reads == [TOKEN, ('users', UID, 'deleted_conversations', 'other')]
    assert len(privacy.PROCESS_OWNERS) == 0
    reads.clear()
    assert check(db, ids=('source',)) == 7  # the certified union died with the refusal
    assert MARKER in reads


def test_owner_memo_serves_snapshots_calls_with_an_empty_export(world, monkeypatch):
    db, reads, _, _ = world
    owner_enable(monkeypatch)
    first = {}
    assert (
        privacy.assert_batch_write_allowed(db, db.transaction(), UID, conversation_ids=['source'], snapshots=first) == 7
    )
    assert first['user'] == {'data_protection_level': 'standard'}
    assert first['conversations']['source']['record_lane_owner'] == 'batch_live_v1'
    reads.clear()
    second = {}
    assert (
        privacy.assert_batch_write_allowed(db, db.transaction(), UID, conversation_ids=['source'], snapshots=second)
        == 7
    )
    assert second == {}  # a served decision exports no rows; the caller reads what it needs
    assert reads == [TOKEN]


def test_owner_memo_kill_switch_returns_to_live_reads(world, monkeypatch):
    db, reads, _, _ = world
    owner_enable(monkeypatch)
    assert check(db) == 7
    monkeypatch.setattr(ttl_cache, '_read_kill_flag', lambda: True)
    ttl_cache.reset_for_tests()
    privacy.PROCESS_OWNERS.clear()
    reads.clear()
    assert check(db) == 7
    assert check(db) == 7
    assert len(reads) == 10  # every decision walks live again


def test_owner_memo_expected_generation_mismatch_never_serves_a_cached_allow(world, monkeypatch):
    db, reads, _, _ = world
    owner_enable(monkeypatch)
    assert check(db) == 7
    reads.clear()
    with pytest.raises(privacy.BatchPrivacyBlocked, match='privacy_generation_changed'):
        privacy.assert_batch_write_allowed(
            db, db.transaction(), UID, conversation_ids=['source'], expected_generation=8
        )
    assert reads == [TOKEN, MARKER, ('users', UID)]


def test_owner_memo_attempt_scope_reuses_across_id_sets_and_survives_it(world, monkeypatch):
    from database.batch_privacy_attempt import batch_privacy_attempt

    db, reads, _, _ = world
    owner_enable(monkeypatch)
    with batch_privacy_attempt():
        assert check(db, ids=('source',)) == 7
        reads.clear()
        assert check(db, ids=('other',)) == 7
        assert reads == [TOKEN, ('users', UID, 'deleted_conversations', 'other'), OTHER]
    reads.clear()
    assert check(db, ids=('source', 'other')) == 7
    assert reads == [TOKEN]  # the process entry outlives the attempt, still token-certified


def test_owner_memo_lane_check_uses_the_certified_user_sync_default(world, monkeypatch):
    db, reads, _, _ = world
    owner_enable(monkeypatch)
    db.rows[('users', UID)] = {'data_protection_level': 'standard', 'private_cloud_sync_enabled': False}
    db.rows[('users', UID, 'conversations', 'plain')] = {}
    assert check(db, ids=('plain',)) == 7  # cold walk stores the user opt-out
    reads.clear()
    with pytest.raises(privacy.BatchPrivacyBlocked, match='recording_privacy_changed'):
        check(db, ids=('source',))
    assert reads == [TOKEN, TOMBSTONE, SOURCE]


def test_owner_memo_follows_redirect_chains_when_verifying_new_ids(world, monkeypatch):
    db, reads, _, _ = world
    owner_enable(monkeypatch)
    db.rows[('users', UID, 'conversations', 'donor')] = {
        'deleted': True,
        'sync_merged_into': 'source',
    }
    assert check(db, ids=('source',)) == 7
    reads.clear()
    assert check(db, ids=('donor',)) == 7
    DONOR_TOMB = ('users', UID, 'deleted_conversations', 'donor')
    assert reads == [TOKEN, DONOR_TOMB, ('users', UID, 'conversations', 'donor'), TOMBSTONE, SOURCE]


def test_owner_memo_snapshot_export_is_filled_when_the_walk_runs_live(world, monkeypatch):
    db, reads, _, _ = world
    owner_enable(monkeypatch)
    output = {}
    assert (
        privacy.assert_batch_write_allowed(db, db.transaction(), UID, conversation_ids=['other'], snapshots=output) == 7
    )
    assert output['conversations']['other']['record_lane_owner'] == 'batch_live_v1'
    assert len(reads) == 5  # a miss pays the full walk and exports its rows


def test_owner_memo_ineligible_labels_stay_for_nontransactional_calls(world, monkeypatch):
    db, _, _, _ = world
    owner_enable(monkeypatch)
    before = metrics.MEMO_INELIGIBLE.labels('no_attempt', 'other')._value.get()
    with pytest.raises(privacy.BatchPrivacyBlocked, match='account_deleted'):
        db.rows[MARKER] = {'wipe_status': 'pending'}
        privacy.assert_batch_write_allowed(db, None, UID, conversation_ids=['source'])
    assert metrics.MEMO_INELIGIBLE.labels('no_attempt', 'other')._value.get() == before + 1


def test_owner_memo_shadow_comparison_labels_the_owner_source(world, monkeypatch):
    db, reads, _, _ = world
    owner_enable(monkeypatch, 'privacy_checks_shadow')
    from database.batch_privacy_attempt import batch_privacy_attempt

    before = metrics.COMPARISONS.labels(
        'batch', 'match', 'owner_hit', 'unknown', 'same', 'same', 'unknown', 'matched'
    )._value.get()
    with batch_privacy_attempt():
        assert check(db) == 7
        reads.clear()
        assert check(db) == 7
        # Live decides (observation token, marker, user, privacy, tombstone,
        # source); the shadow candidate then serves its owner-memo hit.
        assert reads == [TOKEN, MARKER, ('users', UID), TOKEN, TOMBSTONE, SOURCE, TOKEN]
    after = metrics.COMPARISONS.labels(
        'batch', 'match', 'owner_hit', 'unknown', 'same', 'same', 'unknown', 'matched'
    )._value.get()
    assert after > before


def test_owner_memo_shadow_covers_the_no_attempt_store_and_retention_paths(world, monkeypatch):
    """The store/retention mass runs without an attempt scope; those calls must
    still serve the live decision and compare an owner-memo candidate."""
    db, reads, _, _ = world
    owner_enable(monkeypatch, 'privacy_checks_shadow')
    matches = metrics.SHADOW_CHECKS.labels('batch', 'match')
    owner_hits = metrics.COMPARISONS.labels(
        'batch', 'match', 'owner_hit', 'lt_1s', 'same', 'same', 'unknown', 'matched'
    )
    matches_before, owner_before = matches._value.get(), owner_hits._value.get()
    # No batch_privacy_attempt: the no_attempt mass must never enforce unshadowed.
    assert check(db) == 7
    assert check(db) == 7
    assert matches._value.get() == matches_before + 2
    assert owner_hits._value.get() == owner_before + 1
    # Both calls served live (full walk each time); the second compared a
    # process owner-memo candidate that read only the token.
    assert reads[-1] == TOKEN


def test_owner_memo_shadow_compares_snapshot_callers_with_a_throwaway_export(world, monkeypatch):
    db, reads, _, _ = world
    owner_enable(monkeypatch, 'privacy_checks_shadow')
    calls = []
    original = privacy._assert_batch_write_allowed_memo

    def spy(*args, **kwargs):
        calls.append(kwargs.get('snapshots'))
        return original(*args, **kwargs)

    monkeypatch.setattr(privacy, '_assert_batch_write_allowed_memo', spy)
    matches = metrics.SHADOW_CHECKS.labels('batch', 'match')
    before = matches._value.get()
    output = {}
    assert (
        privacy.assert_batch_write_allowed(db, db.transaction(), UID, conversation_ids=['source'], snapshots=output)
        == 7
    )
    # The live decision still exports the rows it read.
    assert output['user'] == {'data_protection_level': 'standard'}
    assert output['conversations']['source']['record_lane_owner'] == 'batch_live_v1'
    assert matches._value.get() == before + 1
    # The compared candidate got its own throwaway export: never the caller's.
    # (It may fill that copy in place; the caller's dict is a different object.)
    assert len(calls) == 1 and calls[0] is not output
    assert output['user'] == {'data_protection_level': 'standard'}


def test_owner_memo_partial_export_covers_only_unseen_ids(world, monkeypatch):
    """Contract: a served decision exports nothing for certified ids; unseen ids
    are walked live and their rows are exported, so exports can be partial."""
    db, reads, _, _ = world
    owner_enable(monkeypatch)
    assert check(db) == 7  # certify 'source'
    output = {}
    assert (
        privacy.assert_batch_write_allowed(
            db, db.transaction(), UID, conversation_ids=['source', 'other'], snapshots=output
        )
        == 7
    )
    assert set(output) == {'conversations'}
    assert set(output['conversations']) == {'other'}  # the certified id is not re-exported
    assert reads[-2:] == [('users', UID, 'deleted_conversations', 'other'), OTHER]


def test_owner_memo_growth_cannot_extend_the_sixty_second_bound(world, monkeypatch):
    db, reads, _, clock = world
    owner_enable(monkeypatch)
    assert check(db, ids=('source',)) == 7
    clock.now += 40
    reads.clear()
    assert check(db, ids=('other',)) == 7  # partial verify at 40s: union grows, bound does not
    assert reads == [TOKEN, ('users', UID, 'deleted_conversations', 'other'), OTHER]
    clock.now += 30  # 70s after the authority walk that certified the owner
    reads.clear()
    assert check(db, ids=('source',)) == 7
    assert MARKER in reads and ('users', UID) in reads  # the entry expired; a fresh walk certifies


def test_retention_authorize_fills_rows_when_the_owner_memo_serves_the_check(world, monkeypatch):
    from types import SimpleNamespace

    from utils.batch_pipeline import retention

    db, reads, _, _ = world
    owner_enable(monkeypatch)
    store = SimpleNamespace(client=db)
    item = SimpleNamespace(owner_id=UID, conversation_id='source', privacy_generation=7)
    output = {}
    context = retention.batch_artifact_authorize(store, item, snapshots=output)
    assert context.level == 'standard' and context.generation == 7
    assert output['user'] == {'data_protection_level': 'standard'}
    assert output['conversations']['source']['record_lane_owner'] == 'batch_live_v1'
    assert len(reads) == 5  # cold: the walk exported everything
    reads.clear()
    output = {}
    context = retention.batch_artifact_authorize(store, item, snapshots=output)
    assert context.level == 'standard' and context.generation == 7
    assert output['user'] == {'data_protection_level': 'standard'}
    assert output['conversations']['source']['record_lane_owner'] == 'batch_live_v1'
    # Served decision: token read, then the two rows the callback needs.
    assert reads == [TOKEN, ('users', UID), SOURCE]
