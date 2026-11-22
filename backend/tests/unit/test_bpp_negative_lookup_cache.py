"""Physical reads through the live walk, with strict transaction ordering."""

from collections import Counter
from datetime import datetime, timezone, timedelta
import json

import pytest

from database import batch_pipeline_privacy as privacy, batch_privacy_negative_cache as cache
from database import privacy_check_metrics as metrics
from database.batch_privacy_attempt import batch_privacy_attempt
from config.firestore_read_levers import KNOWN_LEVERS, lever_enabled
from database.privacy_ttl_cache import BoundedTTLCache, is_missing
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore, StrictFirestoreDocument

UID = 'negative-owner'
TOKEN = ('batch_pipeline_privacy', privacy.privacy_owner_key(UID))
CONVERSATION = ('users', UID, 'conversations', 'source')
TOMBSTONE = ('users', UID, 'deleted_conversations', 'source')
MARKER = ('account_deletions', UID)


@pytest.fixture
def world(monkeypatch):
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"privacy_negative_lookup_cache":100}')
    now = [0.0]
    monkeypatch.setattr(cache, 'LOOKUPS', BoundedTTLCache(max_entries=6, clock=lambda: now[0]))
    db = StrictFirestore(
        {
            ('users', UID): {'data_protection_level': 'standard'},
            TOKEN: {
                'generation': 7,
                'memo_token': 'a' * 32,
                'memo_schema': 1,
            },
        }
    )
    reads = []
    original = StrictFirestoreDocument.get
    revision = [datetime(2026, 11, 6, tzinfo=timezone.utc)]

    def get(reference, transaction=None, **kwargs):
        assert transaction is not None
        reads.append(reference.path)
        snapshot = original(reference, transaction=transaction, **kwargs)
        snapshot.update_time = revision[0] if snapshot.exists else None
        return snapshot

    monkeypatch.setattr(StrictFirestoreDocument, 'get', get)
    return db, reads, now, revision


def check(db, **kwargs):
    return privacy.assert_batch_write_allowed(db, db.transaction(), UID, conversation_ids=['source'], **kwargs)


def test_unchanged_token_skips_only_not_found_and_rereads_token_per_decision(world):
    db, reads, _, _ = world
    assert check(db) == 7
    assert len(reads) == 5
    reads.clear()
    assert check(db) == 7
    assert reads == [TOKEN, ('users', UID)]
    db.rows[CONVERSATION] = {'title': 'live'}
    db.rows[TOKEN]['memo_token'] = 'b' * 32
    reads.clear()
    assert check(db) == 7
    assert CONVERSATION in reads
    reads.clear()
    assert check(db) == 7
    assert reads == [TOKEN, ('users', UID), CONVERSATION]  # positives never cached


@pytest.mark.parametrize('writer', ['record_deletion', 'account_deletion', 'legal_hold', 'create', 'update'])
def test_rotating_writer_family_invalidates_on_next_check(world, writer):
    db, reads, _, _ = world
    check(db)
    # The SDK/fence suite and emulator matrix prove the atomic writer half.
    # Model its resulting authority state here; the strict fake has no commits.
    db.rows[TOKEN]['memo_token'] = 'b' * 32
    reason = None
    if writer == 'record_deletion':
        db.rows[TOMBSTONE] = {}
        reason = 'conversation_deleted'
    elif writer == 'account_deletion':
        db.rows[MARKER] = {'wipe_status': 'in_progress'}
        reason = 'account_deleted'
    elif writer == 'legal_hold':
        db.rows[('legal_holds', UID)] = {'state': 'active'}
        # The batch walk does not adjudicate holds; the external fence does.
    else:
        db.rows[CONVERSATION] = {'deleted': writer == 'update'}
        reason = 'conversation_deleted' if writer == 'update' else None
    reads.clear()
    if reason:
        with pytest.raises(privacy.BatchPrivacyBlocked, match=reason):
            check(db)
    else:
        assert check(db) == 7
    assert MARKER in reads
    if writer != 'account_deletion':
        assert TOMBSTONE in reads
    if writer in {'legal_hold', 'create', 'update'}:
        assert CONVERSATION in reads


def test_server_revision_prevents_same_token_replay(world):
    db, reads, _, revision = world
    check(db)
    revision[0] += timedelta(microseconds=1)
    db.rows[TOMBSTONE] = {}
    reads.clear()
    with pytest.raises(privacy.BatchPrivacyBlocked, match='conversation_deleted'):
        check(db)
    assert TOMBSTONE in reads


@pytest.mark.parametrize('field,value', [('memo_token', None), ('memo_schema', 2), ('memo_blocked', True)])
def test_uncertified_tokens_never_seed_or_hit(world, field, value):
    db, reads, _, _ = world
    db.rows[TOKEN][field] = value
    check(db)
    check(db)
    assert len(reads) == 10 and len(cache.LOOKUPS) == 0


def test_ttl_expiry_and_lru_bound(world):
    db, reads, now, _ = world
    check(db)
    now[0] = 60.0
    reads.clear()
    check(db)
    assert len(reads) == 5
    for i in range(10):
        privacy.assert_batch_write_allowed(db, db.transaction(), UID, conversation_ids=[f'c{i}'])
    assert len(cache.LOOKUPS) == 6
    reads.clear()
    check(db)
    assert CONVERSATION in reads and TOMBSTONE in reads


@pytest.mark.parametrize(
    'collection,path',
    [('account_deletions', MARKER), ('deleted_conversations', TOMBSTONE), ('conversations', CONVERSATION)],
)
def test_shadow_compares_live_and_counts_bypass_mismatch_even_with_generation_memo(
    world, monkeypatch, collection, path
):
    db, reads, _, _ = world
    monkeypatch.setenv(
        'FIRESTORE_READ_LEVERS',
        json.dumps(
            {
                'privacy_negative_lookup_cache': 100,
                'privacy_checks_shadow': 100,
                'bpp_generation_memo': 100,
            }
        ),
    )
    mismatch = metrics.NEGATIVE_LOOKUPS.labels(collection, 'shadow', 'mismatch')
    before = mismatch._value.get()
    with batch_privacy_attempt():
        check(db)
        db.rows[path] = {}  # Deliberately bypass WQ26: real absence must never be returned by shadow.
        reads.clear()
        if path == CONVERSATION:
            check(db)
        else:
            with pytest.raises(privacy.BatchPrivacyBlocked):
                check(db)
    assert path in reads
    assert mismatch._value.get() == before + 1


def test_levers_off_preserve_original_reads_even_with_warm_cache(world, monkeypatch):
    db, reads, _, _ = world
    check(db)
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{}')
    reads.clear()
    check(db)
    assert reads == [MARKER, ('users', UID), TOKEN, TOMBSTONE, CONVERSATION]


def test_full_row_exports_stay_live_and_do_not_seed(world):
    db, reads, _, _ = world
    snapshots = {}
    check(db, snapshots=snapshots)
    assert len(cache.LOOKUPS) == 0
    assert snapshots['conversations']['source'] == {}
    assert reads == [MARKER, ('users', UID), TOKEN, TOMBSTONE, CONVERSATION]


def test_cache_isolated_by_client_owner_and_document(world):
    db, reads, _, _ = world
    check(db)
    other = StrictFirestore(db.rows)
    reads.clear()
    check(other)
    assert len(reads) == 5
    other.rows[('users', 'other')] = {'data_protection_level': 'standard'}
    other.rows[('batch_pipeline_privacy', privacy.privacy_owner_key('other'))] = db.rows[TOKEN].copy()
    reads.clear()
    privacy.assert_batch_write_allowed(other, other.transaction(), 'other', conversation_ids=['source'])
    assert len(reads) == 5


def test_counter_labels_are_bounded():
    metrics.negative_lookup('users/secret/path', 'secret-mode', 'secret-result')
    assert metrics.NEGATIVE_LOOKUPS.labels('other', 'enforce', 'miss')._value.get() >= 1


def test_slow_absence_read_cannot_extend_ttl(world, monkeypatch):
    db, reads, now, _ = world
    original = StrictFirestoreDocument.get

    def slow(reference, **kwargs):
        result = original(reference, **kwargs)
        if reference.path == CONVERSATION:
            now[0] += 61
        return result

    monkeypatch.setattr(StrictFirestoreDocument, 'get', slow)
    check(db)
    reads.clear()
    check(db)
    assert CONVERSATION in reads


def test_failed_token_read_never_serves_warm_cache(world, monkeypatch):
    db, reads, _, _ = world
    check(db)
    original = StrictFirestoreDocument.get

    def fail(reference, **kwargs):
        if reference.path == TOKEN:
            raise RuntimeError('token unavailable')
        return original(reference, **kwargs)

    monkeypatch.setattr(StrictFirestoreDocument, 'get', fail)
    with pytest.raises(RuntimeError, match='token unavailable'):
        check(db)


def test_failed_shadow_read_is_not_a_completed_comparison(world, monkeypatch):
    db, _, _, _ = world
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"privacy_negative_lookup_cache":100,"privacy_checks_shadow":100}')
    check(db)
    hits = metrics.NEGATIVE_LOOKUPS.labels('account_deletions', 'shadow', 'hit')
    before = hits._value.get()
    original = StrictFirestoreDocument.get

    def fail(reference, **kwargs):
        if reference.path == MARKER:
            raise RuntimeError('lookup unavailable')
        return original(reference, **kwargs)

    monkeypatch.setattr(StrictFirestoreDocument, 'get', fail)
    with pytest.raises(RuntimeError, match='lookup unavailable'):
        check(db)
    assert hits._value.get() == before


def test_lru_access_preserves_recent_hint(world):
    bounded = BoundedTTLCache(max_entries=2, clock=lambda: 0)
    bounded.put('first', 'v', started=0)
    bounded.put('second', 'v', started=0)
    assert bounded.get('first')[0] == 'v'
    bounded.put('third', 'v', started=0)
    assert is_missing(bounded.get('second')[0])
    assert bounded.get('first')[0] == 'v'


def test_percent_cohorts_use_existing_mechanics(world, monkeypatch):
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"privacy_negative_lookup_cache":10}')
    decisions = [lever_enabled('privacy_negative_lookup_cache', f'owner-{i}') for i in range(2000)]
    assert 0.07 < sum(decisions) / len(decisions) < 0.13
    assert decisions == [lever_enabled('privacy_negative_lookup_cache', f'owner-{i}') for i in range(2000)]


def test_repeated_decision_in_same_transaction_rereads_token(world):
    db, reads, _, _ = world
    tx = db.transaction()
    for _ in range(2):
        privacy.assert_batch_write_allowed(db, tx, UID, conversation_ids=['source'])
    assert Counter(reads)[TOKEN] == 2
    assert Counter(reads)[MARKER] == 1
    assert len(reads) == 7


def test_one_new_lever_replaces_wq12_and_off_preserves_existing_shadow(world, monkeypatch):
    assert 'privacy_negative_lookup_cache' in KNOWN_LEVERS
    assert 'batch_privacy_memoize' not in KNOWN_LEVERS
    assert 'privacy_negative_lookup_shadow' not in KNOWN_LEVERS
    db, _, _, _ = world
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"privacy_checks_shadow":100}')

    def unexpected_cache(*args, **kwargs):
        raise AssertionError('lever 0 must disable the negative cache even in existing decision shadow')

    monkeypatch.setattr(cache, 'read', unexpected_cache)
    with batch_privacy_attempt():
        assert check(db) == 7
        assert check(db) == 7
    assert len(cache.LOOKUPS) == 0
