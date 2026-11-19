"""Lazy memo-token mint for batch privacy decisions (lever bpp_token_mint, default off)."""

from datetime import datetime, timezone, timedelta
import json

import pytest

from database import batch_pipeline_privacy as privacy, privacy_check_metrics as metrics
from database.batch_privacy_attempt import batch_privacy_attempt
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore, StrictFirestoreDocument

REAL_SCHEDULE = privacy.schedule_token_mint

UID = 'token-mint-owner'
TOKEN = ('batch_pipeline_privacy', privacy.privacy_owner_key(UID))
USER = ('users', UID)
SOURCE = ('users', UID, 'conversations', 'source')


@pytest.fixture
def world(monkeypatch):
    db = StrictFirestore(
        {
            USER: {'data_protection_level': 'standard'},
            SOURCE: {'record_lane_owner': 'batch_live_v1', 'private_cloud_sync_enabled': True},
        }
    )
    reads = []
    revision = [datetime(2026, 11, 5, tzinfo=timezone.utc)]
    original = StrictFirestoreDocument.get

    def get(ref, **kwargs):
        reads.append(ref.path)
        result = original(ref, **kwargs)
        result.update_time = revision[0] if result.exists else None
        return result

    monkeypatch.setattr(StrictFirestoreDocument, 'get', get)
    scheduled = []
    monkeypatch.setattr(privacy, 'schedule_token_mint', lambda client, ref, uid: scheduled.append((client, ref, uid)))
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', json.dumps({'bpp_generation_memo': 100}))
    yield db, reads, revision, scheduled


def check(db, transaction=None):
    return privacy.assert_batch_write_allowed(db, transaction or db.transaction(), UID, conversation_ids=['source'])


def mint(db):
    return privacy.mint_token(db, db.collection(TOKEN[0]).document(TOKEN[1]))


def test_tokenless_owner_is_counted_and_scheduled_then_becomes_memo_eligible(world):
    db, reads, _, scheduled = world
    before = metrics.MEMO_REQUESTS.labels('batch', 'no_token')._value.get()
    with batch_privacy_attempt():
        assert check(db) == 0
    assert metrics.MEMO_REQUESTS.labels('batch', 'no_token')._value.get() == before + 1
    assert [s[2] for s in scheduled] == [UID]
    assert mint(db) is True
    row = db.rows[TOKEN]
    assert row['generation'] == 0 and row['blocked'] is False and row['purging'] is False
    assert len(row['memo_token']) == 32 and row['memo_schema'] == 1
    reads.clear()
    with batch_privacy_attempt():
        assert check(db) == 0
        walked = len(reads)
        reads.clear()
        assert check(db) == 0
    assert walked == 5 and reads == [TOKEN]  # second decision certified by the token alone


def test_minter_never_writes_blocked_purging_or_already_tokened_owners(world):
    db, _, _, _ = world
    for state in (
        {'generation': 3, 'blocked': True, 'purging': False},
        {'generation': 3, 'blocked': False, 'purging': True},
        {'generation': 3, 'blocked': False, 'purging': False, 'memo_blocked': True},
    ):
        db.rows[TOKEN] = dict(state)
        assert mint(db) is False
        assert db.rows[TOKEN] == state
    db.rows[TOKEN] = {'generation': 3, 'blocked': False, 'purging': False, 'memo_token': 'a' * 32, 'memo_schema': 1}
    assert mint(db) is False
    assert db.rows[TOKEN]['memo_token'] == 'a' * 32


def test_existing_document_gets_a_masked_token_update_and_keeps_its_state(world):
    db, _, _, _ = world
    db.rows[TOKEN] = {'generation': 4, 'blocked': False, 'purging': False}
    assert mint(db) is True
    assert {k: db.rows[TOKEN][k] for k in ('generation', 'blocked', 'purging')} == {
        'generation': 4,
        'blocked': False,
        'purging': False,
    }


def test_revoke_racing_the_mint_is_always_seen(world):
    """Revoke lands after the decision but before the mint: the mint's new token never certifies the old walk."""
    db, _, revision, _ = world
    with batch_privacy_attempt():
        assert check(db) == 0
        db.rows[USER] = {
            'data_protection_level': 'e2ee'
        }  # authority write (fence would rotate a token; none exists yet)
        assert mint(db) is True
        revision[0] += timedelta(seconds=1)
        with pytest.raises(privacy.BatchPrivacyBlocked, match='data_protection_changed'):
            check(db)


def test_revoke_after_the_mint_invalidates_the_minted_token(world):
    db, _, revision, _ = world
    assert mint(db) is True
    with batch_privacy_attempt():
        assert check(db) == 0
        # The write fence rotates the token in the same commit as the authority write.
        db.rows[USER] = {'data_protection_level': 'e2ee'}
        db.rows[TOKEN] = {**db.rows[TOKEN], 'memo_token': 'f' * 32}
        revision[0] += timedelta(seconds=1)
        with pytest.raises(privacy.BatchPrivacyBlocked, match='data_protection_changed'):
            check(db)


def test_schedule_is_lever_gated_and_deduplicated_per_owner(monkeypatch):
    real = REAL_SCHEDULE
    db = StrictFirestore({})
    ref = db.collection(TOKEN[0]).document(TOKEN[1])
    monkeypatch.setattr(privacy, '_mint_thread', ['worker-stub'])  # never start the background worker in tests
    monkeypatch.setattr(privacy, '_mint_queue', __import__('collections').deque())
    monkeypatch.setattr(privacy, '_mint_seen', __import__('collections').OrderedDict())
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{}')
    real(db, ref, UID)
    assert not privacy._mint_queue
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"bpp_token_mint":100}')
    real(db, ref, UID)
    real(db, ref, UID)
    assert len(privacy._mint_queue) == 1


def test_both_mint_write_shapes_pass_the_real_write_fence_validator():
    from google.cloud.firestore_v1 import _helpers
    from google.cloud.firestore_v1.types import Document, DocumentMask, Precondition, Write
    from database.batch_privacy_write_fence import _validate_authority_write

    name = 'projects/p/databases/(default)/documents/batch_pipeline_privacy/' + privacy.privacy_owner_key(UID)
    token = {'memo_token': 'b' * 32, 'memo_schema': 1}
    created = Write(
        update=Document(
            name=name, fields=_helpers.encode_dict({'generation': 0, 'blocked': False, 'purging': False, **token})
        ),
        current_document=Precondition(exists=False),
    )
    masked = Write(
        update=Document(name=name, fields=_helpers.encode_dict(token)),
        update_mask=DocumentMask(field_paths=['memo_token', 'memo_schema']),
        current_document=Precondition(exists=True),
    )
    _validate_authority_write(created)
    _validate_authority_write(masked)
    token_only_create = Write(
        update=Document(name=name, fields=_helpers.encode_dict(token)), current_document=Precondition(exists=False)
    )
    with pytest.raises(ValueError):
        _validate_authority_write(token_only_create)  # why the create path carries the default state


def test_a_worker_that_cannot_start_never_breaks_the_decision_and_is_retried(world, monkeypatch):
    """Luna r1 P2 on #24658: thread start failure raised through the privacy check and stuck."""
    db, _, _, _ = world
    import collections
    import threading

    monkeypatch.setattr(privacy, 'schedule_token_mint', REAL_SCHEDULE)
    monkeypatch.setattr(privacy, '_mint_thread', [])
    monkeypatch.setattr(privacy, '_mint_queue', collections.deque())
    monkeypatch.setattr(privacy, '_mint_seen', collections.OrderedDict())
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"bpp_generation_memo":100,"bpp_token_mint":100}')
    starts = []

    def fail_start(self):
        starts.append(1)
        raise RuntimeError("can't start new thread")

    monkeypatch.setattr(threading.Thread, 'start', fail_start)
    with batch_privacy_attempt():
        assert check(db) == 0  # the live decision still runs and allows
    assert starts == [1] and privacy._mint_thread == []  # not registered as running
    assert not privacy._mint_queue and not privacy._mint_seen  # nothing stranded (Luna r2 P2)
    with batch_privacy_attempt():
        assert check(db) == 0
    assert starts == [1, 1]  # the same owner retries the start, no manual reset
