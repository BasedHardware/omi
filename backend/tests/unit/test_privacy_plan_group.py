"""Plan attribution consumes existing observations and preserves physical reads."""

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import time
from unittest.mock import MagicMock

import pytest

from config.plan_catalog import PlanType
from database import _client, batch_pipeline_privacy as privacy, firestore_tier_context as tier
from database import conversation_tombstones, fsr_read_cache, legal_holds, privacy_check_metrics as metrics
from database.batch_privacy_attempt import batch_privacy_attempt
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore, StrictFirestoreDocument

UID = 'synthetic-plan-owner'
TOKEN = ('batch_pipeline_privacy', privacy.privacy_owner_key(UID))


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{}')
    token = tier._request_owner.set(None)
    yield
    tier._request_owner.reset(token)


EXPECTED_SEGMENTS = {
    PlanType.basic: 'free',
    PlanType.architect: 'paid',
    PlanType.operator: 'paid',
    PlanType.plus: 'paid',
    PlanType.unlimited: 'paid',
    PlanType.unlimited_v2: 'unlimited_v2',
}


def test_every_catalog_plan_has_an_explicit_meter_segment():
    assert set(PlanType) == set(EXPECTED_SEGMENTS) == set(metrics._PLAN_SEGMENTS)


@pytest.mark.parametrize(
    'plan,segment',
    [(p, s) for p, s in EXPECTED_SEGMENTS.items()] + [(p.value, s) for p, s in EXPECTED_SEGMENTS.items()],
)
def test_catalog_segments(plan, segment):
    assert metrics.plan_group(plan) == segment


@pytest.mark.parametrize('plan', [PlanType.basic, 'basic', 'free'])
def test_basic_and_legacy_free(plan):
    assert metrics.plan_group(plan) == 'free'


@pytest.mark.parametrize('plan', [None, '', 'pro', 'enterprise', 'uid-secret', [], {}, 1])
def test_unknown_plan_is_bounded(plan):
    assert metrics.plan_group(plan) == 'unattributed'


def test_labeling_has_zero_firestore_or_redis_calls(monkeypatch):
    client, redis = MagicMock(), MagicMock()
    for name in ('get_firestore_client', 'get_customer_firestore_client', 'get_data_plane_firestore_client'):
        monkeypatch.setattr(_client, name, client)
    monkeypatch.setattr(fsr_read_cache, '_redis', redis)
    with tier_owner('plus'):
        for family in metrics.FAMILIES:
            metrics.decision(family, uid=UID)
        assert metrics.plan_group(tier.current_tier(UID)) == 'paid'

        @metrics.with_batch_plan
        def check(client, transaction, uid):
            metrics.observe_batch_plan('basic')
            metrics.decision('batch')

        check(client, None, UID)
    assert client.mock_calls == []
    assert redis.mock_calls == []


@contextmanager
def tier_owner(plan, *, uid=UID, closed=False, expired=False):
    owner = tier._RequestOwner(uid, plan, time.monotonic() + (-1 if expired else 60), closed)
    token = tier._request_owner.set(owner)
    try:
        yield
    finally:
        tier._request_owner.reset(token)


@pytest.fixture
def world(monkeypatch):
    db = StrictFirestore(
        {
            ('users', UID): {'subscription': {'plan': 'unlimited_v2'}},
            TOKEN: {
                'generation': 7,
                'memo_token': 'a' * 32,
                'memo_schema': 1,
            },
        }
    )
    reads = []
    original = StrictFirestoreDocument.get

    def get(reference, **kwargs):
        reads.append(reference.path)
        snapshot = original(reference, **kwargs)
        snapshot.update_time = datetime(2026, 11, 10, tzinfo=timezone.utc) if snapshot.exists else None
        return snapshot

    monkeypatch.setattr(StrictFirestoreDocument, 'get', get)
    monkeypatch.setattr(conversation_tombstones, 'db', db)
    return db, reads


def read_value(family, mode, result, group):
    return metrics.READS.labels(family, mode, result, group)._value.get()


@pytest.mark.parametrize(
    'plan,group',
    [
        ('plus', 'paid'),
        ('unlimited_v2', 'unlimited_v2'),
        ('basic', 'free'),
        ('free', 'free'),
        (None, 'unattributed'),
        ('bad', 'unattributed'),
    ],
)
@pytest.mark.parametrize('path', ['transaction', 'preflight', 'snapshots', 'shadow', 'memo_miss'])
def test_batch_labels_all_existing_reads_and_decision(world, monkeypatch, plan, group, path):
    db, reads = world
    db.rows[('users', UID)] = {'subscription': {'plan': plan}} if plan is not None else {}
    flags = {'shadow': ['privacy_checks_shadow'], 'memo_miss': ['bpp_generation_memo']}.get(path, [])
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', json.dumps(dict.fromkeys(flags, 100)))
    before = {result: read_value('batch', 'live', result, group) for result in ('hit', 'miss')}
    checks = metrics.CHECKS.labels('batch', 'live', 'allow', group)._value.get()
    shadow_before = {result: read_value('batch', 'shadow', result, group) for result in ('hit', 'miss')}
    with batch_privacy_attempt():
        assert (
            privacy.assert_batch_write_allowed(
                db,
                None if path == 'preflight' else db.transaction(),
                UID,
                snapshots={} if path == 'snapshots' else None,
            )
            == 7
        )
    expected = [('account_deletions', UID), ('users', UID), TOKEN]
    if path == 'memo_miss':
        expected = [TOKEN, *expected[:-1]]
    if path == 'shadow':
        expected = [TOKEN, *expected, TOKEN, *expected[:-1]]
    assert reads == expected  # Exactly the pre-existing sequence, including shadow/token reads.
    assert read_value('batch', 'live', 'hit', group) == before['hit'] + 2 + (path == 'shadow')
    assert read_value('batch', 'live', 'miss', group) == before['miss'] + 1
    assert metrics.CHECKS.labels('batch', 'live', 'allow', group)._value.get() == checks + 1
    if path == 'shadow':
        assert read_value('batch', 'shadow', 'hit', group) == shadow_before['hit'] + 2
        assert read_value('batch', 'shadow', 'miss', group) == shadow_before['miss'] + 1


@pytest.mark.parametrize('request_plan,group', [(None, 'unattributed'), ('plus', 'paid')])
def test_memo_hit_uses_only_matching_request_plan(world, monkeypatch, request_plan, group):
    db, reads = world
    monkeypatch.setattr(privacy, 'lever_enabled', lambda name, uid: name == 'bpp_generation_memo')
    with batch_privacy_attempt():
        assert privacy.assert_batch_write_allowed(db, db.transaction(), UID) == 7
        reads.clear()
        before = read_value('batch', 'live', 'hit', group)
        with tier_owner(request_plan):
            assert privacy.assert_batch_write_allowed(db, db.transaction(), UID) == 7
        assert reads == [TOKEN]
        assert read_value('batch', 'live', 'hit', group) == before + 1


def test_process_memo_does_not_reuse_prior_plan_observation(world, monkeypatch):
    db, reads = world
    monkeypatch.setattr(privacy, 'lever_enabled', lambda name, uid: name == 'bpp_generation_memo')
    monkeypatch.setattr(privacy, 'ttl_enabled', lambda name, uid: True)
    privacy.PROCESS_DECISIONS.clear()
    try:
        assert privacy.assert_batch_write_allowed(db, db.transaction(), UID) == 7
        reads.clear()
        before = read_value('batch', 'live', 'hit', 'unattributed')
        assert privacy.assert_batch_write_allowed(db, db.transaction(), UID) == 7
        assert reads == [TOKEN]
        assert read_value('batch', 'live', 'hit', 'unattributed') == before + 1
    finally:
        privacy.PROCESS_DECISIONS.clear()


def test_metric_flush_failure_preserves_authority_and_read_sequence(world, monkeypatch):
    db, reads = world
    monkeypatch.setattr(metrics.READS, 'labels', MagicMock(side_effect=RuntimeError('synthetic metric fault')))
    assert privacy.assert_batch_write_allowed(db, db.transaction(), UID) == 7
    assert reads == [('account_deletions', UID), ('users', UID), TOKEN]
    assert metrics._BATCH_PLAN.get() is None


@pytest.mark.parametrize('raises', [False, True])
def test_flush_iteration_fault_never_changes_return_or_exception(raises):
    class BrokenReads:
        def items(self):
            yield ('live', 'hit'), 1
            raise RuntimeError('synthetic iteration fault')

    original = ValueError('synthetic authority failure')
    result = object()

    @metrics.with_batch_plan
    def check(client, transaction, uid):
        metrics._BATCH_PLAN.get().reads = BrokenReads()
        if raises:
            raise original
        return result

    if raises:
        with pytest.raises(ValueError) as caught:
            check(None, None, UID)
        assert caught.value is original
    else:
        assert check(None, None, UID) is result
    assert metrics._BATCH_PLAN.get() is None


@pytest.mark.parametrize('style', ['positional', 'keyword_uid', 'all_keywords'])
def test_batch_decorator_accepts_keyword_uid(world, style):
    db, reads = world
    before = read_value('batch', 'live', 'hit', 'unlimited_v2')
    if style == 'positional':
        result = privacy.assert_batch_write_allowed(db, db.transaction(), UID)
    elif style == 'keyword_uid':
        result = privacy.assert_batch_write_allowed(db, db.transaction(), uid=UID)
    else:
        result = privacy.assert_batch_write_allowed(client=db, transaction=db.transaction(), uid=UID)
    assert result == 7
    assert reads == [('account_deletions', UID), ('users', UID), TOKEN]
    assert read_value('batch', 'live', 'hit', 'unlimited_v2') == before + 2


@pytest.mark.parametrize('family', ['batch', 'not-a-family'])
def test_batch_holder_is_normalized_and_never_attributes_foreign_uid(world, family):
    db, reads = world
    paid = read_value('batch', 'live', 'miss', 'paid')
    unattributed = read_value('batch', 'live', 'miss', 'unattributed')

    @metrics.with_batch_plan
    def check(client, transaction, uid):
        metrics.observe_batch_plan('plus')
        for owner in (None, uid, 'other'):
            metrics.read_snapshot(family, db.collection('account_deletions').document(uid), uid=owner)
        assert metrics._plan_label(family, uid) == 'paid'
        assert metrics._plan_label(family, 'other') == 'unattributed'

    # Even a known paid request for the other UID cannot override the holder boundary.
    with tier_owner('plus', uid='other'):
        check(db, None, UID)
    assert reads == [('account_deletions', UID)] * 3
    assert read_value('batch', 'live', 'miss', 'paid') == paid + 2
    assert read_value('batch', 'live', 'miss', 'unattributed') == unattributed + 1


def test_work_with_no_plan_in_memory_emits_only_unattributed(world):
    db, reads = world
    db.rows[('users', UID)] = {}
    before = {
        group: read_value('batch', 'live', 'hit', group) for group in ('free', 'paid', 'unlimited_v2', 'unattributed')
    }
    assert privacy.assert_batch_write_allowed(db, db.transaction(), UID) == 7
    assert reads == [('account_deletions', UID), ('users', UID), TOKEN]
    for group in ('free', 'paid', 'unlimited_v2'):
        assert read_value('batch', 'live', 'hit', group) == before[group]
    assert read_value('batch', 'live', 'hit', 'unattributed') == before['unattributed'] + 2


@pytest.mark.parametrize('failure', ['deleted', 'error'])
def test_before_user_read_and_errors_flush_unknown_without_leaking(world, monkeypatch, failure):
    db, reads = world
    if failure == 'deleted':
        db.rows[('account_deletions', UID)] = {'wipe_status': 'pending'}
    else:
        monkeypatch.setattr(StrictFirestoreDocument, 'get', MagicMock(side_effect=RuntimeError('synthetic')))
    # Deleted marker exists, so its single read is a hit.
    result = 'hit' if failure == 'deleted' else 'error'
    before = read_value('batch', 'live', result, 'unattributed')
    with pytest.raises(privacy.BatchPrivacyBlocked if failure == 'deleted' else RuntimeError):
        privacy.assert_batch_write_allowed(db, db.transaction(), UID)
    assert read_value('batch', 'live', result, 'unattributed') == before + 1
    assert metrics._BATCH_PLAN.get() is None
    assert reads == ([('account_deletions', UID)] if failure == 'deleted' else [])


@pytest.mark.parametrize('family', ['external', 'tombstone'])
@pytest.mark.parametrize(
    'owner,group',
    [
        ('matching', 'paid'),
        ('cold', 'unattributed'),
        ('foreign', 'unattributed'),
        ('closed', 'unattributed'),
        ('expired', 'unattributed'),
    ],
)
def test_nonbatch_paths_use_only_live_matching_request_context(world, family, owner, group):
    db, reads = world
    with tier_owner(
        'plus' if owner != 'cold' else 'unattributed',
        uid='other' if owner == 'foreign' else UID,
        closed=owner == 'closed',
        expired=owner == 'expired',
    ):
        before = read_value(family, 'live', 'miss', group)
        checks = metrics.CHECKS.labels(family, 'live', 'allow', group)._value.get()
        if family == 'external':
            with legal_holds.external_write_fence(UID, firestore_client=db):
                pass
            assert reads == [('account_deletions', UID), ('legal_hold_deletion_gates', UID)]
        else:
            assert not conversation_tombstones.is_deleted(UID, 'source')
            assert reads == [('users', UID, 'deleted_conversations', 'source')]
        assert read_value(family, 'live', 'miss', group) == before + (2 if family == 'external' else 1)
        assert metrics.CHECKS.labels(family, 'live', 'allow', group)._value.get() == checks + 1


@pytest.mark.parametrize('family', ['external', 'tombstone'])
def test_nonbatch_shadow_certificate_reads_keep_request_group(world, monkeypatch, family):
    db, reads = world
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"privacy_checks_shadow":100}')
    with tier_owner('basic'):
        before = read_value(family, 'shadow', 'hit', 'free')
        if family == 'external':
            with legal_holds.external_write_fence(UID, firestore_client=db):
                pass
            assert reads == [
                TOKEN,
                ('account_deletions', UID),
                ('legal_hold_deletion_gates', UID),
                TOKEN,
                ('account_deletions', UID),
                ('legal_hold_deletion_gates', UID),
            ]
        else:
            assert not conversation_tombstones.is_deleted(UID, 'source')
            tombstone = ('users', UID, 'deleted_conversations', 'source')
            assert reads == [TOKEN, tombstone, TOKEN, tombstone]
        assert read_value(family, 'shadow', 'hit', 'free') == before + 1
