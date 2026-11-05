"""Per-call batch privacy attempt scope (lever bpp_attempt_scope, default off)."""

from datetime import datetime, timedelta, timezone
import json

import pytest

from database import batch_pipeline_privacy as privacy, privacy_check_metrics as metrics
from database.batch_privacy_attempt import batch_privacy_attempt, current_attempt, scoped_privacy_attempt
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore, StrictFirestoreDocument

UID = 'attempt-scope-owner'
TOKEN = ('batch_pipeline_privacy', privacy.privacy_owner_key(UID))
USER = ('users', UID)
SOURCE = ('users', UID, 'conversations', 'source')


def enable(monkeypatch, *names):
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', json.dumps(dict.fromkeys(names, 100)))


def test_lever_off_is_a_no_op(monkeypatch):
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{}')
    with scoped_privacy_attempt('key'):
        assert current_attempt() is None


def test_lever_on_opens_a_fresh_attempt_and_closes_it(monkeypatch):
    enable(monkeypatch, 'bpp_attempt_scope')
    with scoped_privacy_attempt('key'):
        inner = current_attempt()
        assert inner is not None
    assert current_attempt() is None
    inner.put('k', 'v', 1)  # a closed attempt never stores or returns anything
    assert inner.get('k', 'v') is None


def test_an_outer_attempt_is_reused_unchanged(monkeypatch):
    enable(monkeypatch, 'bpp_attempt_scope')
    with batch_privacy_attempt() as outer:
        with scoped_privacy_attempt('key'):
            assert current_attempt() is outer
        assert current_attempt() is outer


def test_retention_entry_points_execute_inside_the_scope(monkeypatch):
    from utils.batch_pipeline import retention

    seen = []
    monkeypatch.setattr(retention, '_register_batch_artifact', lambda *a, **k: seen.append(current_attempt()) or 'id')
    monkeypatch.setattr(retention, '_expire_completed_segment', lambda *a, **k: seen.append(current_attempt()) or True)
    enable(monkeypatch, 'bpp_attempt_scope')
    assert retention.register_batch_artifact(None, UID, 'seg', 'gs://b/o', 'audio', 3) == 'id'
    assert retention.expire_completed_segment(None, UID, 'seg', 0.0) is True
    assert all(attempt is not None for attempt in seen) and len(seen) == 2


@pytest.fixture
def world(monkeypatch):
    db = StrictFirestore(
        {
            USER: {'data_protection_level': 'standard'},
            SOURCE: {'record_lane_owner': 'batch_live_v1', 'private_cloud_sync_enabled': True},
            TOKEN: {'memo_token': 'a' * 32, 'memo_schema': 1, 'generation': 0},
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
    yield db, reads, revision


def check(db):
    return privacy.assert_batch_write_allowed(db, db.transaction(), UID, conversation_ids=['source'])


def test_scoped_decisions_become_memo_eligible_and_reuse_is_token_certified(world, monkeypatch):
    db, reads, _ = world
    enable(monkeypatch, 'bpp_attempt_scope', 'bpp_generation_memo')
    before = metrics.MEMO_INELIGIBLE.labels('no_attempt', 'other')._value.get()
    with scoped_privacy_attempt('key'):
        check(db)
        reads.clear()
        check(db)
    assert reads == [TOKEN]  # the second decision is certified by the token read alone
    assert metrics.MEMO_INELIGIBLE.labels('no_attempt', 'other')._value.get() == before


def test_a_revoke_inside_the_scope_is_seen_by_the_next_decision(world, monkeypatch):
    """Lead2 dcba0b: the scope never spans a privacy state change."""
    db, _, revision = world
    enable(monkeypatch, 'bpp_attempt_scope', 'bpp_generation_memo')
    with scoped_privacy_attempt('key'):
        assert check(db) == 0
        # An authority write: the write fence rotates the token in the same commit.
        db.rows[USER] = {'data_protection_level': 'e2ee'}
        db.rows[TOKEN] = {**db.rows[TOKEN], 'memo_token': 'b' * 32}
        revision[0] += timedelta(seconds=1)
        with pytest.raises(privacy.BatchPrivacyBlocked, match='data_protection_changed'):
            check(db)


def test_a_deletion_inside_the_scope_is_seen_by_the_next_decision(world, monkeypatch):
    db, _, revision = world
    enable(monkeypatch, 'bpp_attempt_scope', 'bpp_generation_memo')
    with scoped_privacy_attempt('key'):
        assert check(db) == 0
        db.rows[('users', UID, 'deleted_conversations', 'source')] = {}
        db.rows[TOKEN] = {**db.rows[TOKEN], 'memo_token': 'c' * 32}
        revision[0] += timedelta(seconds=1)
        with pytest.raises(privacy.BatchPrivacyBlocked, match='conversation_deleted'):
            check(db)
