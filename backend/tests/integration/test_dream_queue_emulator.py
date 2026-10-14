"""Real local Firestore contracts behind Dream's hermetic queue fixture.

Run only through test.sh with FIRESTORE_EMULATOR_HOST set to loopback and a
synthetic demo project. No cloud credentials or customer data are accepted.
"""

import os
import asyncio
import json
from datetime import datetime, timedelta, timezone
from functools import partial
from uuid import uuid4, uuid5, NAMESPACE_URL
from unittest.mock import Mock
from concurrent.futures import ThreadPoolExecutor

import pytest
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore

from config.dream_agent import Caps
from database import _client, conversations, dream_store, dream_history, review_store
from utils.agent_capabilities import reads as dream_reads
from utils.agent_capabilities import evidence as dream_context
from utils.dream_diagnostics import path_count
from utils.llm.shaped_agent import Turn
from models.dream_edit import Edit

pytestmark = pytest.mark.integration


def test_budget_settlement_user_isolation_and_duplicate_finish(monkeypatch):
    host = os.environ.get('FIRESTORE_EMULATOR_HOST', '')
    if not host.startswith(('127.0.0.1:', 'localhost:')):
        pytest.skip('local Firestore emulator required')
    database = firestore.Client(project='demo-dream-coalesce', credentials=AnonymousCredentials())
    uids = ['synthetic-budget-' + str(uuid4()) for _ in range(2)]
    monkeypatch.setenv('DREAM_AGENT_ENABLED', 'true')
    monkeypatch.setenv('DREAM_AGENT_ELIGIBILITY', 'all')
    monkeypatch.setenv('DREAM_AGENT_UID_ALLOWLIST', ','.join(uids))
    now = datetime.now(timezone.utc)
    caps = Caps(tokens=432768, passes=24, daily_usd=250)
    for uid in uids:
        database.collection('users').document(uid).set({})
        dream_store.mark_dirty(uid, [('conversations', 'synthetic')], firestore_client=database)
    first = dream_store.acquire(uids[0], caps, now=now, firestore_client=database)
    second = dream_store.acquire(uids[1], caps, now=now, firestore_client=database)

    def finish_once():
        try:
            dream_store.finish(
                uids[0], first, {'tokens': 820000, 'usage_unknown': False}, success=True, firestore_client=database
            )
            return 'finished'
        except RuntimeError as exc:
            assert str(exc) == 'dream_lease_lost'
            return 'duplicate'

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: finish_once(), range(2)))
    assert sorted(results) == ['duplicate', 'finished']
    first_spend = dream_store.spend_ref(database, uids[0], first['day'])
    second_spend = dream_store.spend_ref(database, uids[1], second['day'])
    assert first_spend.get().to_dict()['reserved_usd'] == pytest.approx(8.2)
    assert second_spend.get().to_dict()['reserved_usd'] == pytest.approx(caps.reservation_usd)
    assert dream_store.own_state(uids[0], firestore_client=database)['lease'] is None
    dream_store.finish(uids[1], second, {'tokens': 10, 'usage_unknown': True}, success=False, firestore_client=database)
    assert second_spend.get().to_dict()['reserved_usd'] == pytest.approx(caps.reservation_usd)


def test_fragment_spelling_round_trip_and_undo_preserve_other_segments(monkeypatch):
    from database import review_store, review_changes
    from utils.agent_capabilities import tools as dream_tools

    host = os.environ.get('FIRESTORE_EMULATOR_HOST', '')
    if not host.startswith(('127.0.0.1:', 'localhost:')):
        pytest.skip('local Firestore emulator required')
    database = firestore.Client(project='demo-dream-coalesce', credentials=AnonymousCredentials())
    monkeypatch.setattr(_client, '_firestore_client', database)
    monkeypatch.setenv('REVIEW_SURFACE_MODE', 'on')
    uid = 'synthetic-fragment-' + str(uuid4())
    row = {
        'id': 'synthetic',
        'data_protection_level': 'enhanced',
        'structured': {'title': 'Alise meeting'},
        'transcript_segments': [
            {'id': 's1', 'start': 12.5, 'end': 15, 'text': 'Alise met Alise.'},
            {'id': 's2', 'start': 20, 'end': 22, 'text': 'Alise elsewhere.'},
        ],
    }
    document = database.collection('users').document(uid).collection('conversations').document('synthetic')
    original = conversations.encode_conversation_for_write(uid, row, 'enhanced')
    document.set(original)
    records = {'conversations/synthetic': row}
    edit = Edit(
        kind='spelling',
        target='conversations/synthetic#s1',
        before='Alise',
        after='Alice',
        reason='Synthetic correction',
        evidence=['conversations/synthetic#s1'],
    )
    assert dream_tools.apply_edit(uid, edit, records) == 'applied'
    current = conversations.prepare_conversation_for_read(document.get().to_dict(), uid)
    assert current['transcript_segments'][0]['text'] == 'Alice met Alice.'
    assert current['transcript_segments'][1] == row['transcript_segments'][1]
    assert current['structured'] == row['structured']
    change_id = str(uuid5(NAMESPACE_URL, uid + ':' + dream_tools.edit_key(edit, records)))
    journal = review_store.decode_doc(
        uid,
        review_store.user(uid).collection('review_changes').document(review_store.safe_id(change_id)).get().to_dict(),
    )
    assert journal['transcript_overlay']['conversation_id'] == 'synthetic'
    assert document.get().to_dict()['transcript_segments'] == original['transcript_segments']
    assert journal['change']['refs'][0]['label'] == 'Conversation #s1'
    review_changes.set_undone(uid, change_id, True)
    restored = conversations.prepare_conversation_for_read(document.get().to_dict(), uid)
    assert restored['transcript_segments'] == row['transcript_segments']
    assert restored['structured'] == row['structured']
    assert (
        dream_tools.apply_edit(uid, edit.model_copy(update={'target': 'conversations/synthetic#12.5'}), records)
        == 'suppressed'
    )


@pytest.fixture(autouse=True)
def deterministic_cleanup_admission(monkeypatch):
    # Queue-only proofs must not draw a random cleanup page. The cleanup proof
    # explicitly enables seeding with its own deterministic draw.
    monkeypatch.setenv('DREAM_AGENT_BACKFILL_SHARE', '0')


def test_dirty_queue_transforms_queries_and_transaction_deletes(monkeypatch):
    host = os.environ.get('FIRESTORE_EMULATOR_HOST', '')
    if not host.startswith(('127.0.0.1:', 'localhost:')):
        pytest.skip('local Firestore emulator required')
    database = firestore.Client(project='demo-dream-coalesce', credentials=AnonymousCredentials())
    uid = 'synthetic-' + str(uuid4())
    monkeypatch.setenv('DREAM_AGENT_ENABLED', 'true')
    monkeypatch.setenv('DREAM_AGENT_ELIGIBILITY', 'all')
    monkeypatch.setenv('DREAM_AGENT_UID_ALLOWLIST', uid)
    database.collection('users').document(uid).set({})
    state = dream_store.state_ref(database, uid)
    dream_store.mark_dirty(uid, [('conversations', 'first')], firestore_client=database)
    dream_store.mark_dirty(uid, [('conversations', 'first')], firestore_client=database)
    assert dream_store.dirty_count(uid, firestore_client=database) == 1
    first = dream_store.dirty_refs(uid, firestore_client=database)[0].to_dict()
    assert first['change_count'] == 2
    assert isinstance(first['last_changed_at'], datetime)
    dream_store.mark_dirty(uid, [('conversations', str(i)) for i in range(501)], firestore_client=database)
    queued = dream_store.dirty_refs(uid, firestore_client=database)
    assert dream_store.dirty_count(uid, firestore_client=database) == 500
    assert all(s.to_dict()['id'] != 'first' for s in queued)
    assert state.get().to_dict()['dirty_dropped'] == 2
    assert [s.to_dict()['last_changed_at'] for s in queued] == sorted(
        (s.to_dict()['last_changed_at'] for s in queued), reverse=True
    )
    lease = dream_store.acquire(uid, Caps(), now=datetime.now(timezone.utc), firestore_client=database)
    consumed = [queued[0].to_dict()]
    dream_store.mark_dirty(uid, [('conversations', consumed[0]['id'])], firestore_client=database)
    dream_store.finish(uid, lease, {'tokens': 1}, success=True, consumed=consumed, firestore_client=database)
    # A refreshed version survives the transaction's acknowledgement.
    assert dream_store.dirty_count(uid, firestore_client=database) == 500
    lease = dream_store.acquire(uid, Caps(), firestore_client=database)
    consumed = [s.to_dict() for s in dream_store.dirty_refs(uid, limit=32, firestore_client=database)]
    dream_store.finish(
        uid, lease, {'tokens': 0}, success=True, consumed=consumed, refund=True, firestore_client=database
    )
    assert dream_store.dirty_count(uid, firestore_client=database) == 468
    assert state.get().to_dict()['passes'] == 1
    assert dream_store.spend_ref(database, uid, lease['day']).get().to_dict()['reserved_usd'] == pytest.approx(0.24)

    lease = dream_store.acquire(uid, Caps(), firestore_client=database)
    dream_store.finish(uid, lease, {'tokens': 0}, success=False, release=False, refund=True, firestore_client=database)
    data = state.get().to_dict()
    assert data['passes'] == 1 and data['lease']['run_id'] == lease['run_id']
    assert dream_store.spend_ref(database, uid, lease['day']).get().to_dict()['reserved_usd'] == pytest.approx(0.24)
    assert dream_store.acquire(uid, Caps(), firestore_client=database) is None
    runs = dream_store.own_runs(uid, limit=20, firestore_client=database)
    assert len(runs) >= 3
    assert [row['created_at'] for _, row in runs] == sorted((row['created_at'] for _, row in runs), reverse=True)


def test_manual_admission_race_uses_shared_lease(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    host = os.environ.get('FIRESTORE_EMULATOR_HOST', '')
    if not host.startswith(('127.0.0.1:', 'localhost:')):
        pytest.skip('local Firestore emulator required')
    database = firestore.Client(project='demo-dream-coalesce', credentials=AnonymousCredentials())
    uid = 'synthetic-' + str(uuid4())
    monkeypatch.setenv('DREAM_AGENT_ENABLED', 'true')
    monkeypatch.setenv('DREAM_AGENT_ELIGIBILITY', 'all')
    monkeypatch.setenv('DREAM_AGENT_UID_ALLOWLIST', uid)
    database.collection('users').document(uid).set({})
    dream_store.mark_dirty(uid, [('conversations', 'race')], firestore_client=database)
    barrier = Barrier(2)

    def acquire(trigger):
        barrier.wait()
        try:
            return dream_store.acquire(uid, Caps(), trigger=trigger, firestore_client=database)
        except dream_store.AdmissionDenied as exc:
            assert exc.reason == 'dream_run_in_progress'
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        scheduled = pool.submit(acquire, 'schedule')
        manual = pool.submit(acquire, 'manual')
        results = [scheduled.result(), manual.result()]
    assert sum(row is not None for row in results) == 1
    state = dream_store.own_state(uid, firestore_client=database)
    assert state['passes'] + state['manual_runs'] == 1


def test_poison_settlement_is_atomic_and_preserves_refreshed_version(monkeypatch):
    host = os.environ.get('FIRESTORE_EMULATOR_HOST', '')
    if not host.startswith(('127.0.0.1:', 'localhost:')):
        pytest.skip('local Firestore emulator required')
    database = firestore.Client(project='demo-dream-coalesce', credentials=AnonymousCredentials())
    uid = 'synthetic-' + str(uuid4())
    monkeypatch.setenv('DREAM_AGENT_ENABLED', 'true')
    monkeypatch.setenv('DREAM_AGENT_ELIGIBILITY', 'all')
    monkeypatch.setenv('DREAM_AGENT_UID_ALLOWLIST', uid)
    database.collection('users').document(uid).set({})
    caps = Caps(passes=10)
    dream_store.mark_dirty(uid, [('conversations', 'poison')], firestore_client=database)
    for attempt in range(2):
        lease = dream_store.acquire(uid, caps, firestore_client=database)
        consumed = [s.to_dict() for s in dream_store.dirty_refs(uid, firestore_client=database)]
        report = {'tokens': 10}
        dream_store.finish(
            uid, lease, report, success=False, consumed=consumed, count_failure=True, firestore_client=database
        )
        assert report['poisoned'] == 0
        assert dream_store.dirty_refs(uid, firestore_client=database)[0].to_dict()['failed_passes'] == attempt + 1
    lease = dream_store.acquire(uid, caps, firestore_client=database)
    consumed = [s.to_dict() for s in dream_store.dirty_refs(uid, firestore_client=database)]
    dream_store.mark_dirty(uid, [('conversations', 'poison')], firestore_client=database)
    dream_store.finish(
        uid, lease, report, success=False, consumed=consumed, count_failure=True, firestore_client=database
    )
    assert report['poisoned'] == 0
    assert dream_store.dirty_refs(uid, firestore_client=database)[0].to_dict()['failed_passes'] == 0
    for attempt in range(3):
        lease = dream_store.acquire(uid, caps, firestore_client=database)
        consumed = [s.to_dict() for s in dream_store.dirty_refs(uid, firestore_client=database)]
        dream_store.finish(
            uid, lease, report, success=False, consumed=consumed, count_failure=True, firestore_client=database
        )
    assert report['poisoned'] == 1 and report['records_queued_after'] == 0
    assert dream_store.dirty_count(uid, firestore_client=database) == 0
    state = dream_store.own_state(uid, firestore_client=database)
    assert state['poisoned'] == 1 and state['score'] == 0 and state['lease'] is None


@pytest.mark.parametrize('transient', [False, True])
def test_unavailable_settlement_fences_versions_and_expires_transients(monkeypatch, transient):
    host = os.environ.get('FIRESTORE_EMULATOR_HOST', '')
    if not host.startswith(('127.0.0.1:', 'localhost:')):
        pytest.skip('local Firestore emulator required')
    database = firestore.Client(project='demo-dream-coalesce', credentials=AnonymousCredentials())
    uid = 'synthetic-' + str(uuid4())
    monkeypatch.setenv('DREAM_AGENT_ENABLED', 'true')
    monkeypatch.setenv('DREAM_AGENT_ELIGIBILITY', 'all')
    monkeypatch.setenv('DREAM_AGENT_UID_ALLOWLIST', uid)
    database.collection('users').document(uid).set({})
    dream_store.mark_dirty(uid, [('conversations', 'unavailable')], firestore_client=database)
    lease = dream_store.acquire(uid, Caps(), firestore_client=database)
    item = dream_store.dirty_refs(uid, firestore_client=database)[0].to_dict()
    dream_store.mark_dirty(uid, [('conversations', 'unavailable')], firestore_client=database)
    report = {}
    dream_store.finish(
        uid,
        lease,
        report,
        success=False,
        refund=True,
        unavailable=[{**item, 'transient': transient}],
        firestore_client=database,
    )
    assert report['dirty_counts']['permanent_acknowledged'] == report['dirty_counts']['transient_expired'] == 0
    assert dream_store.dirty_refs(uid, firestore_client=database)[0].to_dict()['failed_passes'] == 0
    for attempt in range(3 if transient else 1):
        lease = dream_store.acquire(uid, Caps(), firestore_client=database)
        item = dream_store.dirty_refs(uid, firestore_client=database)[0].to_dict()
        dream_store.finish(
            uid,
            lease,
            report,
            success=False,
            refund=True,
            unavailable=[{**item, 'transient': transient}],
            firestore_client=database,
        )
        assert report['dirty_counts']['permanent_acknowledged'] == int(not transient)
        assert report['dirty_counts']['transient_expired'] == int(transient and attempt == 2)
    assert dream_store.dirty_count(uid, firestore_client=database) == 0
    assert dream_store.own_state(uid, firestore_client=database)['score'] == 0
    dream_store.mark_dirty(uid, [('conversations', 'unavailable')], firestore_client=database)
    assert dream_store.dirty_refs(uid, firestore_client=database)[0].to_dict()['version'] != item['version']


@pytest.mark.parametrize('legacy', [False, True])
def test_stale_reclamation_contended_admission_and_late_finish(monkeypatch, legacy):
    host = os.environ.get('FIRESTORE_EMULATOR_HOST', '')
    if not host.startswith(('127.0.0.1:', 'localhost:')):
        pytest.skip('local Firestore emulator required')
    database = firestore.Client(project='demo-dream-coalesce', credentials=AnonymousCredentials())
    uid = 'synthetic-abandoned-' + str(uuid4())
    monkeypatch.setenv('DREAM_AGENT_ENABLED', 'true')
    monkeypatch.setenv('DREAM_AGENT_ELIGIBILITY', 'all')
    monkeypatch.setenv('DREAM_AGENT_UID_ALLOWLIST', uid)
    monkeypatch.setenv('DREAM_AGENT_BACKFILL_SHARE', '0')
    old_time = datetime(2026, 10, 14, 23, 0, tzinfo=timezone.utc)
    now = old_time + timedelta(days=1)
    caps = Caps(tokens=24000, passes=24, daily_usd=250, global_daily_usd=1000)
    database.collection('users').document(uid).set({})
    dream_store.mark_dirty(uid, [('conversations', 'synthetic')], firestore_client=database)
    old = dream_store.acquire(uid, caps, now=old_time, firestore_client=database)
    state = dream_store.state_ref(database, uid)
    old_spend = dream_store.spend_ref(database, uid, old['day'])
    if legacy:
        old.pop('spend_scope')
        old.pop('context_mode', None)
        state.update({'lease': old})
        shared = database.collection('dream_spend').document(old['day'])
        shared.set(old_spend.get().to_dict())
        old_spend.delete()
        old_spend = shared
    # A retained lease with known partial usage must become fully charged again.
    dream_store.finish(
        uid,
        old,
        {'tokens': 100, 'usage_unknown': False},
        success=False,
        release=False,
        now=old_time,
        firestore_client=database,
    )
    assert old_spend.get().to_dict()['reserved_usd'] == pytest.approx(0.001)
    pending = [s.to_dict() for s in dream_store.dirty_refs(uid, firestore_client=database)]
    reclaimed = [{}, {}]
    with ThreadPoolExecutor(max_workers=2) as pool:
        leases = list(
            pool.map(
                lambda i: dream_store.acquire(uid, caps, now=now, firestore_client=database, reclaim_sink=reclaimed[i]),
                range(2),
            )
        )
    winners = [lease for lease in leases if lease is not None]
    assert len(winners) == 1
    new = winners[0]
    outcomes = [value for value in reclaimed if value]
    assert outcomes == [{'age_s': int((now - old_time).total_seconds()), 'size_bucket': 'light'}]
    current = state.get().to_dict()
    assert current['lease']['run_id'] == new['run_id'] and current['abandoned_passes'] == 1
    assert current['passes'] == 1  # New UTC day, one admission despite contention.
    assert old_spend.get().to_dict()['reserved_usd'] == pytest.approx(caps.reservation_usd)
    new_spend = dream_store.spend_ref(database, uid, new['day'])
    assert new_spend.get().to_dict()['reserved_usd'] == pytest.approx(caps.reservation_usd)
    assert [s.to_dict() for s in dream_store.dirty_refs(uid, firestore_client=database)] == pending
    report = review_store.decode_doc(uid, dream_store.own_run(uid, old['run_id'], firestore_client=database))
    assert report['source']['usage_unknown'] is True and report['source']['reason'] == 'abandoned'
    assert report['source']['budget_charge_usd'] == pytest.approx(caps.reservation_usd)
    with pytest.raises(RuntimeError, match='dream_lease_lost'):
        dream_store.finish(
            uid,
            old,
            {'tokens': 1, 'usage_unknown': False},
            success=True,
            consumed=pending,
            now=now,
            firestore_client=database,
        )
    assert state.get().to_dict() == current
    assert new_spend.get().to_dict()['reserved_usd'] == pytest.approx(caps.reservation_usd)
    assert [s.to_dict() for s in dream_store.dirty_refs(uid, firestore_client=database)] == pending
