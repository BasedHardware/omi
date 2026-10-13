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
from utils import dream_reads, dream_agent, dream_cleanup, dream_context
from utils.dream_diagnostics import path_count
from utils.llm.shaped_agent import Turn
from models.dream_agent import Triage, Cluster, Plan, Edit

pytestmark = pytest.mark.integration


def test_budget_settlement_user_isolation_and_duplicate_finish(monkeypatch):
    host = os.environ.get('FIRESTORE_EMULATOR_HOST', '')
    if not host.startswith(('127.0.0.1:', 'localhost:')):
        pytest.skip('local Firestore emulator required')
    database = firestore.Client(project='demo-dream-coalesce', credentials=AnonymousCredentials())
    uids = ['synthetic-budget-' + str(uuid4()) for _ in range(2)]
    monkeypatch.setenv('DREAM_AGENT_MODE', 'shadow')
    monkeypatch.setenv('DREAM_AGENT_UID_ALLOWLIST', ','.join(uids))
    now = datetime.now(timezone.utc)
    caps = Caps(context_mode='full', tokens=432768, samples=3, passes=24, daily_usd=250)
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
    from utils import dream_tools

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
    assert journal['edits'][0]['document_id'] == 'synthetic'
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


def test_retrieved_sections_ground_spelling_and_settle_unavailable_refs(monkeypatch):
    host = os.environ.get('FIRESTORE_EMULATOR_HOST', '')
    if not host.startswith(('127.0.0.1:', 'localhost:')):
        pytest.skip('local Firestore emulator required')
    database = firestore.Client(project='demo-dream-coalesce', credentials=AnonymousCredentials())
    monkeypatch.setattr(_client, '_firestore_client', database)
    uid = 'synthetic-' + str(uuid4())
    monkeypatch.setenv('DREAM_AGENT_MODE', 'shadow')
    monkeypatch.setenv('DREAM_AGENT_UID_ALLOWLIST', uid)
    monkeypatch.setenv('DREAM_AGENT_AUTO_APPLY_KINDS', 'title,overview,spelling')
    database.collection('users').document(uid).set({})
    source = database.collection('users').document(uid).collection('conversations')
    source.document('film').set({'transcript_segments': [{'text': 'The invented film is called Zuvra.'}]})
    neighbours = [f'conversations/neighbour-{i}' for i in range(6)]
    for ref in neighbours:
        row = conversations.encode_conversation_for_write(
            uid,
            {
                'transcript_segments': [],
                'structured': {
                    'sections': [{'heading': 'Invented reference', 'body_markdown': 'The spelling is Zuvrah.'}]
                },
            },
            'enhanced',
        )
        source.document(ref.split('/')[1]).set({**row, 'data_protection_level': 'enhanced'})
    dream_store.mark_dirty(
        uid,
        [('conversations', 'film')] + [('conversations', f'missing-{i}') for i in range(31)],
        firestore_client=database,
    )

    def candidates(uid, records, vocabulary, *, read_record, diagnostics, **kwargs):
        path_count(diagnostics, 'semantic', 'attempted')
        path_count(diagnostics, 'semantic', 'found', len(neighbours))
        for ref in neighbours:
            yield ref, partial(read_record, uid, ref), 'semantic'

    monkeypatch.setattr(dream_reads, 'context_candidates', candidates)
    caps = Caps()
    lease = dream_store.acquire(uid, caps, firestore_client=database)
    report, unavailable = {}, []
    evidence, consumed = dream_reads.read_changes(uid, lease, caps, diagnostics=report, unavailable=unavailable)
    assert evidence.targets == {'conversations/film'} and neighbours[0] in evidence
    assert len(unavailable) == report['dirty_counts']['permanent'] == 31

    async def turn(uid, lane, mount, messages):
        if mount.schema is Triage:
            value = Triage(clusters=[Cluster(refs=['conversations/film'], problem='spelling')])
        else:
            payload = json.loads(messages[-1]['content'])
            assert payload['roles'][neighbours[0]] == 'context'
            assert 'Zuvrah' in payload['records'][neighbours[0]]
            value = Plan(
                edits=[
                    Edit(
                        kind='spelling',
                        target='conversations/film',
                        before='Zuvra',
                        after='Zuvrah',
                        reason='Invented independent reference',
                        evidence=['conversations/film', neighbours[0]],
                    ),
                    Edit(
                        kind='spelling',
                        target=neighbours[0],
                        before='Zuvrah',
                        after='Zuvra',
                        reason='Invented invalid context edit',
                        evidence=[neighbours[0]],
                    ),
                ]
            )
        return Turn(value=value, tokens=10)

    result = asyncio.run(dream_agent.dry_run(uid, evidence, caps=caps, turn=turn, vocabulary=[]))
    assert len(result['plan']['edits']) == 1 and result['plan']['edits'][0]['policy'] == 'auto'
    assert result['role_counts']['target'] == 1 and result['role_counts']['context'] >= 1
    assert not result['plan']['questions']
    dream_store.finish(
        uid,
        lease,
        report,
        success=True,
        refund=True,
        consumed=consumed,
        unavailable=unavailable,
        firestore_client=database,
    )
    assert report['dirty_counts']['permanent_acknowledged'] == 31
    assert dream_store.dirty_count(uid, firestore_client=database) == 0


def test_unverifiable_speech_retries_without_blocking_and_fences_refresh(monkeypatch):
    host = os.environ.get('FIRESTORE_EMULATOR_HOST', '')
    if not host.startswith(('127.0.0.1:', 'localhost:')):
        pytest.skip('local Firestore emulator required')
    database = firestore.Client(project='demo-dream-coalesce', credentials=AnonymousCredentials())
    monkeypatch.setattr(_client, '_firestore_client', database)
    uid = 'synthetic-' + str(uuid4())
    monkeypatch.setenv('DREAM_AGENT_MODE', 'shadow')
    monkeypatch.setenv('DREAM_AGENT_UID_ALLOWLIST', uid)
    monkeypatch.setattr(dream_reads, 'context_candidates', lambda *a, **k: [])
    database.collection('users').document(uid).set({})
    source = database.collection('users').document(uid).collection('conversations')
    source.document('bad').set(
        {
            'transcript_segments': 'invented-undecodable-speech',
            'transcript_segments_compressed': True,
            'data_protection_level': 'enhanced',
        }
    )
    source.document('healthy').set({'transcript_segments': [{'text': 'Garden boat'}]})
    dream_store.mark_dirty(uid, [('conversations', 'bad'), ('conversations', 'healthy')], firestore_client=database)
    caps = Caps(passes=10)
    for attempt in range(5):
        lease = dream_store.acquire(uid, caps, firestore_client=database)
        report, unavailable = {}, []
        records, consumed = dream_reads.read_changes(uid, lease, caps, diagnostics=report, unavailable=unavailable)
        assert report['dirty_counts']['failed'] == report['dirty_counts']['transient'] == 1
        assert report['input_content_counts']['transcript_decode_failed'] == 1
        assert records.targets == ({'conversations/healthy'} if attempt == 0 else set())
        assert len(unavailable) == 1 and unavailable[0]['transient'] is True
        if attempt == 1:
            # A refreshed version cannot inherit this pass's observed failure.
            dream_store.mark_dirty(uid, [('conversations', 'bad')], firestore_client=database)
        dream_store.finish(
            uid,
            lease,
            report,
            success=bool(consumed),
            refund=True,
            consumed=consumed,
            unavailable=unavailable,
            firestore_client=database,
        )
        assert report['dirty_counts']['transient_expired'] == int(attempt == 4)
        queued = dream_store.dirty_refs(uid, firestore_client=database)
        if attempt < 4:
            assert len(queued) == 1 and queued[0].to_dict()['id'] == 'bad'
            assert queued[0].to_dict()['failed_passes'] == [1, 0, 1, 2][attempt]
        else:
            assert not queued
    # A later product write restores a fresh, readable dirty version.
    source.document('bad').set({'transcript_segments': [{'text': 'Garden boat restored'}]})
    dream_store.mark_dirty(uid, [('conversations', 'bad')], firestore_client=database)
    lease = dream_store.acquire(uid, caps, firestore_client=database)
    records, consumed = dream_reads.read_changes(uid, lease, caps)
    assert records.targets == {'conversations/bad'} and len(consumed) == 1
    dream_store.finish(uid, lease, {}, success=True, refund=True, consumed=consumed, firestore_client=database)


def test_oldest_inspection_progresses_under_35_new_refs_per_pass(monkeypatch):
    host = os.environ.get('FIRESTORE_EMULATOR_HOST', '')
    if not host.startswith(('127.0.0.1:', 'localhost:')):
        pytest.skip('local Firestore emulator required')
    database = firestore.Client(project='demo-dream-coalesce', credentials=AnonymousCredentials())
    monkeypatch.setattr(_client, '_firestore_client', database)
    uid = 'synthetic-' + str(uuid4())
    monkeypatch.setenv('DREAM_AGENT_MODE', 'shadow')
    monkeypatch.setenv('DREAM_AGENT_UID_ALLOWLIST', uid)
    monkeypatch.setattr(dream_reads, 'context_candidates', lambda *a, **k: [])
    database.collection('users').document(uid).set({})
    initial = {f'initial-{i}' for i in range(35)}
    dream_store.mark_dirty(uid, [('conversations', key) for key in sorted(initial)], firestore_client=database)
    inspected = set()

    def read(uid, ref, **kwargs):
        inspected.add(ref.split('/')[1])
        return {'transcript_segments': [{'text': 'Garden boat'}]}

    monkeypatch.setattr(dream_reads, 'read_record', read)
    caps = Caps(passes=10)
    for hour in range(5):
        arrivals = [('conversations', f'hour-{hour}-{i}') for i in range(35)]
        dream_store.mark_dirty(uid, arrivals, firestore_client=database)
        lease = dream_store.acquire(uid, caps, firestore_client=database)
        report = {}
        records, consumed = dream_reads.read_changes(uid, lease, caps, diagnostics=report)
        assert report['dirty_counts']['fetched'] == 32
        assert 1 <= len(consumed) <= 8 and len(records.targets) == len(consumed)
        dream_store.finish(uid, lease, report, success=True, refund=True, consumed=consumed, firestore_client=database)
        assert dream_store.dirty_count(uid, firestore_client=database) < 500
    assert initial <= inspected
    assert not dream_store.state_ref(database, uid).get().to_dict().get('dirty_dropped', 0)


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
    else:
        put('discarded', -8, discarded=True)
        put('deleted', -9, deleted=True)
        put('locked', 1, is_locked=True)
        put('discarded-right', 2, discarded=True)
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


@pytest.mark.parametrize('level', ['standard', 'enhanced'])
def test_context_reservation_settles_only_admitted_dirty_versions(monkeypatch, level):
    from database import _client, conversations
    from utils import dream_context, dream_reads

    host = os.environ.get('FIRESTORE_EMULATOR_HOST', '')
    if not host.startswith(('127.0.0.1:', 'localhost:')):
        pytest.skip('local Firestore emulator required')
    database = firestore.Client(project='demo-dream-coalesce', credentials=AnonymousCredentials())
    monkeypatch.setattr(_client, '_firestore_client', database)
    uid = 'synthetic-' + str(uuid4())
    monkeypatch.setenv('DREAM_AGENT_MODE', 'shadow')
    monkeypatch.setenv('DREAM_AGENT_UID_ALLOWLIST', uid)
    now = datetime.now(timezone.utc)
    source = database.collection('users').document(uid).collection('conversations')
    for key in [str(i) for i in range(8)] + ['neighbour']:
        row = conversations.encode_conversation_for_write(
            uid,
            {
                'id': key,
                'created_at': now,
                'discarded': False,
                'transcript_segments': [
                    {
                        'id': 'synthetic-segment',
                        'text': 'Bún bò ở phố, garden boat. ' * 200,
                        'speaker': 'SPEAKER_00',
                        'start': 0,
                        'end': 50,
                        'is_user': True,
                    }
                ],
                'structured': {
                    'title': '',
                    'overview': '',
                    'sections': [
                        {'heading': 'Garden boat', 'body_markdown': 'Bún bò, garden boat. ' * 50},
                    ],
                },
            },
            level,
        )
        source.document(key).set({**row, 'data_protection_level': level})
    dream_store.mark_dirty(uid, [('conversations', str(i)) for i in range(8)], firestore_client=database)
    lease = dream_store.acquire(uid, Caps(), firestore_client=database)
    monkeypatch.setattr(
        dream_reads,
        'context_candidates',
        lambda *a, **k: [
            ('conversations/neighbour', lambda: dream_reads.read_record(uid, 'conversations/neighbour'), 'temporal'),
        ],
    )
    report = {}
    records, consumed = dream_reads.read_changes(uid, lease, Caps(), diagnostics=report)
    assert 1 <= len(records.targets) <= 4 and len(records) > len(records.targets)
    assert {f"{item['collection']}/{item['id']}" for item in consumed} == records.targets
    assert dream_context.fits_pass(records, Caps())
    assert report['context_budget_counts']['reservation_kept'] == 1
    assert report['dirty_counts']['budget_deferred'] == 8 - len(consumed)
    # Concurrent refresh survives along with every target deferred for context.
    refreshed = consumed[0]['id']
    dream_store.mark_dirty(uid, [('conversations', refreshed)], firestore_client=database)
    dream_store.finish(uid, lease, report, success=True, consumed=consumed, firestore_client=database)
    remaining = {s.to_dict()['id'] for s in dream_store.dirty_refs(uid, firestore_client=database)}
    assert remaining == (set(str(i) for i in range(8)) - {item['id'] for item in consumed}) | {refreshed}
    assert dream_store.dirty_count(uid, firestore_client=database) == 8 - len(consumed) + 1


def test_older_seed_context_and_deferral_settle_with_full_inspection_window(monkeypatch):
    host = os.environ.get('FIRESTORE_EMULATOR_HOST', '')
    if not host.startswith(('127.0.0.1:', 'localhost:')):
        pytest.skip('local Firestore emulator required')
    database = firestore.Client(project='demo-dream-coalesce', credentials=AnonymousCredentials())
    monkeypatch.setattr(_client, '_firestore_client', database)
    uid = 'synthetic-' + str(uuid4())
    monkeypatch.setenv('DREAM_AGENT_MODE', 'shadow')
    monkeypatch.setenv('DREAM_AGENT_UID_ALLOWLIST', uid)
    monkeypatch.setenv('DREAM_AGENT_BACKFILL_SHARE', '1')
    monkeypatch.setenv('DREAM_AGENT_RANDOM_SEED_SHARE', '0')
    now = datetime.now(timezone.utc)
    old = now - timedelta(days=60)
    database.collection('users').document(uid).set({})
    source = database.collection('users').document(uid).collection('conversations')
    speech = 'Garden boat planning. ' * 200
    for key in ('older', 'neighbour'):
        row = conversations.encode_conversation_for_write(
            uid,
            {
                'created_at': old,
                'structured': {'title': '', 'overview': '', 'sections': []},
                'transcript_segments': [{'text': speech}],
            },
            'enhanced',
        )
        source.document(key).set({**row, 'data_protection_level': 'enhanced'})
    rng = Mock()
    rng.random.return_value = 0.5
    rng.choice.return_value = 'conversations'
    rng.choices.return_value = ['conversations/older']
    monkeypatch.setattr(dream_cleanup.random, 'SystemRandom', lambda: rng)
    dream_store.mark_dirty(uid, [('conversations', f'missing-{i}') for i in range(32)], firestore_client=database)

    def candidates(owner, records, vocabulary, *, read_record, diagnostics, **kwargs):
        assert records.targets == {'conversations/older'}
        yield 'conversations/neighbour', partial(read_record, owner, 'conversations/neighbour'), 'semantic'

    monkeypatch.setattr(dream_reads, 'context_candidates', candidates)
    lease = dream_store.acquire(uid, Caps(), now=now + timedelta(seconds=1), firestore_client=database)
    report, unavailable = {}, []
    records, consumed = dream_reads.read_changes(uid, lease, Caps(), diagnostics=report, unavailable=unavailable)
    assert len(unavailable) == 32 and not consumed
    assert records.targets == {'conversations/older'}
    assert records.target_sources == {'conversations/older': 'seeded'}
    assert set(records) - records.targets == {'conversations/neighbour'}
    assert report['context_budget_counts']['reservation_kept'] == 1
    assert dream_context.fits_pass(records, Caps())
    dream_store.finish(
        uid,
        lease,
        report,
        success=True,
        unavailable=unavailable,
        reviewed=records.targets,
        deferred=records.targets,
        seeded=records.targets,
        cleanup_cursor=records.cleanup_cursor,
        now=now,
        firestore_client=database,
    )
    assert report['dirty_counts']['permanent_acknowledged'] == 32
    assert dream_store.dirty_count(uid, firestore_client=database) == 0
    review = dream_history.review_states(uid, records.targets, firestore_client=database)['conversations/older']
    assert review == {'deferred_until': now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)}
    state = dream_store.own_state(uid, firestore_client=database)
    assert state['cleanup_cursor']['conversations'] == 'older'
    # The actual persisted review batch prevents another same-day hydration.
    monkeypatch.setattr(dream_history, 'history_page', lambda *a, **k: ['older'])
    hydration = Mock(side_effect=AssertionError('daily-capped seed hydrated'))
    selected = dream_cleanup.add_seed(
        uid,
        dream_context.EvidenceRecords(),
        {'started_at': now, 'cleanup_selected': True},
        Caps(),
        [],
        read_record=hydration,
        rng=rng,
    )
    assert not selected
    hydration.assert_not_called()


@pytest.mark.parametrize('context', ['full', 'bounded'])
@pytest.mark.parametrize('legacy', [False, True])
def test_stale_reclamation_contended_admission_and_late_finish(monkeypatch, context, legacy):
    host = os.environ.get('FIRESTORE_EMULATOR_HOST', '')
    if not host.startswith(('127.0.0.1:', 'localhost:')):
        pytest.skip('local Firestore emulator required')
    database = firestore.Client(project='demo-dream-coalesce', credentials=AnonymousCredentials())
    uid = 'synthetic-abandoned-' + str(uuid4())
    monkeypatch.setenv('DREAM_AGENT_MODE', 'shadow')
    monkeypatch.setenv('DREAM_AGENT_UID_ALLOWLIST', uid)
    monkeypatch.setenv('DREAM_AGENT_BACKFILL_SHARE', '0')
    old_time = datetime(2026, 10, 14, 23, 0, tzinfo=timezone.utc)
    now = old_time + timedelta(days=1)
    caps = Caps(context_mode=context, passes=24, daily_usd=250)
    database.collection('users').document(uid).set({})
    dream_store.mark_dirty(uid, [('conversations', 'synthetic')], firestore_client=database)
    old = dream_store.acquire(uid, caps, now=old_time, firestore_client=database)
    state = dream_store.state_ref(database, uid)
    old_spend = dream_store.spend_ref(database, uid, old['day'])
    if legacy:
        old.pop('spend_scope')
        old.pop('context_mode')
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
    assert outcomes == [{'age_s': int((now - old_time).total_seconds()), 'context_mode': 'full' if legacy else context}]
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
