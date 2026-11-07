"""60s-bounded privacy decision reuse (David ruling 2026-11-04): levers privacy_ttl60 and bpp_decision_cache."""

from datetime import datetime, timezone, timedelta
import json

import fakeredis
import pytest

from database import account_deletion_marker as marker
from database import batch_pipeline_privacy as privacy, conversation_tombstones as tombstones
from database import fsr_read_cache as cache, legal_holds, privacy_check_metrics as metrics
from database import privacy_negative_cache as negative, privacy_ttl_cache as ttl_cache
from database.batch_privacy_attempt import batch_privacy_attempt
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


def test_tombstone_clear_is_reused_then_deletion_takes_effect_within_sixty_seconds(world, monkeypatch):
    db, reads, _, clock = world
    enable(monkeypatch, 'privacy_ttl60')
    assert not tombstones.is_deleted(UID, 'source')
    assert len(reads) == 1
    assert not tombstones.is_deleted(UID, 'source')
    assert len(reads) == 1  # reused, no token read either
    db.rows[TOMBSTONE] = {}
    clock.now += 59
    assert not tombstones.is_deleted(UID, 'source')  # accepted staleness, < 60s
    clock.now += 1
    assert tombstones.is_deleted(UID, 'source')
    # A deleted answer is never cached.
    reads.clear()
    assert tombstones.is_deleted(UID, 'source')
    assert tombstones.is_deleted(UID, 'source')
    assert len(reads) == 2


def test_tombstone_cache_never_answers_for_another_conversation_or_plane(world, monkeypatch):
    db, reads, _, _ = world
    enable(monkeypatch, 'privacy_ttl60')
    assert not tombstones.is_deleted(UID, 'source')
    db.rows[('users', UID, 'deleted_conversations', 'other')] = {}
    assert tombstones.is_deleted(UID, 'other')
    assert tombstones.is_deleted(UID, 'other')
    assert not tombstones.is_deleted(UID, 'source')
    other_plane = StrictFirestore({})
    assert ttl_cache.DECISIONS.get(negative._ttl_key('tombstone', UID, db, 'source'))[0] is True
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
    assert len(reads) == 2
    assert external(db)
    assert len(reads) == 2
    db.rows[MARKER] = {'wipe_status': 'pending'}
    clock.now += 60
    reads.clear()
    for _ in range(2):
        with pytest.raises(legal_holds.DestructiveOperationInProgress):
            external(db)
    assert len(reads) == 2  # each blocked decision re-read the marker


def test_external_fence_inside_a_transaction_always_reads_live(world, monkeypatch):
    db, reads, _, _ = world
    enable(monkeypatch, 'privacy_ttl60')
    assert external(db)
    reads.clear()
    transaction = db.transaction()
    with legal_holds.external_write_fence(UID, firestore_client=db, transaction=transaction):
        pass
    assert len(reads) == 2


# --- deletion marker ----------------------------------------------------------


def test_shadow_keeps_live_authority_and_labels_within_bound_staleness(world, monkeypatch):
    db, reads, _, clock = world
    enable(monkeypatch, 'privacy_checks_shadow', 'privacy_ttl60')
    within = metrics.DECISION_MISMATCH.labels('tombstone', 'stale_within_ttl')._value.get()
    stale = metrics.DECISION_MISMATCH.labels('tombstone', 'stale_allow')._value.get()
    assert not tombstones.is_deleted(UID, 'source')
    assert not tombstones.is_deleted(UID, 'source')
    assert len(reads) == 2  # shadow: live decides every time, and costs no extra read
    db.rows[TOMBSTONE] = {}
    clock.now += 30
    assert tombstones.is_deleted(UID, 'source')  # live authority wins in shadow
    assert metrics.DECISION_MISMATCH.labels('tombstone', 'stale_within_ttl')._value.get() == within + 1
    assert metrics.DECISION_MISMATCH.labels('tombstone', 'stale_allow')._value.get() == stale
    clock.now += 31
    assert tombstones.is_deleted(UID, 'source')
    assert metrics.DECISION_MISMATCH.labels('tombstone', 'stale_within_ttl')._value.get() == within + 1


def test_compare_counts_a_stale_allow_older_than_the_bound_as_a_real_mismatch():
    before = metrics.DECISION_MISMATCH.labels('external', 'stale_allow')._value.get()
    metrics.compare('external', 'destructive_operation', 'allow', cached_age=60.5)
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
