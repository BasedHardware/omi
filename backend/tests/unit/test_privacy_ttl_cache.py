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
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{}')
    ttl_cache.reset_for_tests()
    monkeypatch.setattr(ttl_cache, '_read_kill_flag', lambda: False)
    privacy.PROCESS_DECISIONS.clear()
    redis = fakeredis.FakeRedis()
    yield db, reads, revision, clock
    ttl_cache.DECISIONS.clear()
    privacy.PROCESS_DECISIONS.clear()
    redis.close()


def enable(monkeypatch, *names):
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', json.dumps(dict.fromkeys(names, 100)))


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
