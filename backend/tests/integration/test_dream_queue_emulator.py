"""Real local Firestore contracts behind Dream's hermetic queue fixture.

Run only through test.sh with FIRESTORE_EMULATOR_HOST set to loopback and a
synthetic demo project. No cloud credentials or customer data are accepted.
"""

import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore

from config.dream_agent import Caps
from database import dream_store

pytestmark = pytest.mark.integration


def test_dirty_queue_transforms_queries_and_transaction_deletes(monkeypatch):
    host = os.environ.get('FIRESTORE_EMULATOR_HOST', '')
    if not host.startswith(('127.0.0.1:', 'localhost:')):
        pytest.skip('local Firestore emulator required')
    database = firestore.Client(project='demo-dream-coalesce', credentials=AnonymousCredentials())
    uid = 'synthetic-' + str(uuid4())
    monkeypatch.setenv('DREAM_AGENT_MODE', 'shadow')
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
    assert database.collection('dream_spend').document(lease['day']).get().to_dict()['reserved_usd'] == pytest.approx(
        0.24
    )

    lease = dream_store.acquire(uid, Caps(), firestore_client=database)
    dream_store.finish(uid, lease, {'tokens': 0}, success=False, release=False, refund=True, firestore_client=database)
    data = state.get().to_dict()
    assert data['passes'] == 1 and data['lease']['run_id'] == lease['run_id']
    assert database.collection('dream_spend').document(lease['day']).get().to_dict()['reserved_usd'] == pytest.approx(
        0.24
    )
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
    monkeypatch.setenv('DREAM_AGENT_MODE', 'shadow')
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
    monkeypatch.setenv('DREAM_AGENT_MODE', 'shadow')
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
    monkeypatch.setenv('DREAM_AGENT_MODE', 'shadow')
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


@pytest.mark.parametrize('collection', ['conversations', 'screen_activity'])
def test_temporal_neighbours_exclude_eight_inputs_before_nearest_selection(collection):
    from datetime import timedelta
    from database.dream_context_reads import temporal_neighbours
    from database.screen_activity import normalize_screen_activity_timestamp

    host = os.environ.get('FIRESTORE_EMULATOR_HOST', '')
    if not host.startswith(('127.0.0.1:', 'localhost:')):
        pytest.skip('local Firestore emulator required')
    database = firestore.Client(project='demo-dream-coalesce', credentials=AnonymousCredentials())
    uid = 'synthetic-' + str(uuid4())
    now = datetime(2030, 1, 1, 12, tzinfo=timezone.utc)
    source = database.collection('users').document(uid).collection(collection)
    database.collection('users').document(uid).collection('task_intelligence_control').document('state').set(
        {'account_generation': 2}
    )

    def put(key, minutes, **extra):
        when = now + timedelta(minutes=minutes)
        row = (
            {'created_at': when}
            if collection == 'conversations'
            else {
                'timestamp': normalize_screen_activity_timestamp(when),
                'captureEligible': True,
                'accountGeneration': 2,
            }
        )
        source.document(key).set({**row, **extra})

    for i in range(8):
        put(f'target-{i}', -i)
    for i, minutes in enumerate((-10, -20, -600, 5, 30, 1800)):
        put(f'context-{i}', minutes)
    if collection == 'screen_activity':
        put('ineligible', 0, captureEligible=False)
        put('old-generation', 0, accountGeneration=1)
    window = timedelta(hours=24 if collection == 'conversations' else 2)
    rows = temporal_neighbours(
        uid,
        collection,
        now - window,
        now,
        now + window,
        excluded_ids={f'target-{i}' for i in range(8)},
        firestore_client=database,
    )
    assert [row['id'] for row in rows] == ['context-3', 'context-0', 'context-1', 'context-4']
    # No targets, wrong-generation/opted-out screens or out-of-window rows.
    assert all(row['id'].startswith('context-') for row in rows)
