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
from utils.llm.shaped_agent import Turn
from models.dream_edit import Edit

pytestmark = pytest.mark.integration


def emulator_client():
    assert os.environ.get('FIRESTORE_EMULATOR_HOST', '').startswith(('127.0.0.1:', 'localhost:'))
    return firestore.Client(project='demo-dream-' + uuid4().hex[:16], credentials=AnonymousCredentials())


def test_hidden_capture_union_and_query_immutability(monkeypatch):
    from database.conversation_visibility_counts import count_hidden
    from google.cloud.firestore_v1 import FieldFilter

    assert os.environ.get('FIRESTORE_EMULATOR_HOST', '').startswith(('127.0.0.1:', 'localhost:'))
    database = emulator_client()
    collection = database.collection('users').document('synthetic-count-' + str(uuid4())).collection('conversations')
    base = {'discarded': False, 'status': 'completed', 'source': 'omi'}
    for key, extras in [
        ('legacy', {}),
        ('duplicate', {'dream_duplicate_of': 'legacy'}),
        ('both', {'deleted': True, 'dream_duplicate_of': 'legacy'}),
        ('deleted', {'deleted': True}),
        ('empty', {'dream_duplicate_of': ''}),
    ]:
        collection.document(key).set({**base, **extras})
    deleted = collection.where(filter=FieldFilter('deleted', '==', True))
    duplicate = collection.where(filter=FieldFilter('dream_duplicate_of', '>', ''))
    assert {doc.id for doc in deleted.stream()} == {'both', 'deleted'}
    assert {doc.id for doc in duplicate.stream()} == {'both', 'duplicate'}
    assert len(list(collection.stream())) == 5
    assert count_hidden(collection, include_discarded=False, sources=['omi']) == 3
    assert count_hidden(collection, include_discarded=True, sources=['omi']) == 2
    assert count_hidden(collection, include_discarded=False, sources=['other']) == 0


def test_atomic_harness_memory_merge_and_undo_on_real_sdk(monkeypatch):
    from database import review_changes
    from models.agent_edit import HarnessEdit
    from models.memory_apply import MemoryControlState, WriterMode
    from models.product_memory import MemoryItem
    from utils.agent_capabilities import tools

    assert os.environ.get('FIRESTORE_EMULATOR_HOST', '').startswith(('127.0.0.1:', 'localhost:'))
    database = emulator_client()
    uid = 'synthetic-memory-merge-' + str(uuid4())
    monkeypatch.setenv('REVIEW_SURFACE_MODE', 'on')
    monkeypatch.setenv('MEMORY_ENABLED', 'on')
    monkeypatch.setattr(review_store, 'get_firestore_client', lambda: database)
    monkeypatch.setattr(_client, '_firestore_client', database)
    owner = database.collection('users').document(uid)
    owner.set({})
    owner.collection('memory_state').document('apply_control').set(
        MemoryControlState(
            uid=uid, writer_mode=WriterMode.ledger, head_commit_id='genesis', account_generation=0, source_generation=0
        ).model_dump(mode='json')
    )
    now = datetime.now(timezone.utc)
    records = {}
    for key in ('one', 'two'):
        row = MemoryItem(
            memory_id=key,
            uid=uid,
            version=1,
            ledger_commit_id='synthetic-prior',
            ledger_sequence=1,
            tier='long_term',
            status='active',
            processing_state='processed',
            content='Lives in the invented Toytown.',
            source_state='active',
            sensitivity_labels=[],
            visibility='private',
            user_asserted=True,
            captured_at=now,
            updated_at=now,
            valid_from=now,
            ledger_schema_version='knowledge_ledger.v1',
            kind='fact',
            subject_scope='primary_user',
            slot='location',
            write_reason='agent_reusable_conclusion',
            intent_backed=True,
        ).model_dump(mode='python')
        owner.collection('memory_items').document(key).set(row)
        records['memory_items/' + key] = row
    capture = {'id': 'evidence', 'status': 'completed', 'created_at': now}
    owner.collection('conversations').document('evidence').set(capture)
    records['conversations/evidence'] = capture
    operation = HarnessEdit(
        kind='merge_memories',
        target='memory_items/one',
        other='memory_items/two',
        after='Lives in the invented Toytown.',
        reason='Synthetic duplicate fact',
        evidence=['memory_items/two', 'conversations/evidence'],
    )
    fences = tools.proposal_fences(uid, {'records': records})
    assert tools.apply_edit(uid, operation, records, expected_records=fences) == 'applied'
    after = [owner.collection('memory_items').document(key).get().to_dict() for key in ('one', 'two')]
    assert after[0]['superseded_by'] == after[1]['superseded_by']
    assert after[0]['ledger_commit_id'] == after[1]['ledger_commit_id']
    journal = next(review_store.decode_doc(uid, doc.to_dict()) for doc in owner.collection('review_changes').stream())
    review_changes.set_undone(uid, journal['change']['change_id'], True)
    for key in ('one', 'two'):
        restored = owner.collection('memory_items').document(key).get().to_dict()
        original = records['memory_items/' + key]
        assert {
            field: value for field, value in restored.items() if field not in {'ledger_commit_id', 'ledger_sequence'}
        } == {field: value for field, value in original.items() if field not in {'ledger_commit_id', 'ledger_sequence'}}


def test_budget_settlement_user_isolation_and_duplicate_finish(monkeypatch):
    host = os.environ.get('FIRESTORE_EMULATOR_HOST', '')
    if not host.startswith(('127.0.0.1:', 'localhost:')):
        pytest.skip('local Firestore emulator required')
    database = emulator_client()
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
    assert first_spend.get().to_dict()['reserved_usd'] == pytest.approx(0)
    assert second_spend.get().to_dict()['reserved_usd'] == pytest.approx(0)
    assert dream_store.own_state(uids[0], firestore_client=database)['lease'] is None
    dream_store.finish(uids[1], second, {'tokens': 10, 'usage_unknown': True}, success=False, firestore_client=database)
    assert second_spend.get().to_dict()['reserved_usd'] == pytest.approx(0)


def test_fragment_spelling_round_trip_and_undo_preserve_other_segments(monkeypatch):
    from database import review_store, review_changes
    from utils.agent_capabilities import tools as dream_tools

    host = os.environ.get('FIRESTORE_EMULATOR_HOST', '')
    if not host.startswith(('127.0.0.1:', 'localhost:')):
        pytest.skip('local Firestore emulator required')
    database = emulator_client()
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
    from utils.agent_capabilities.transcripts import originals

    assert originals(current['transcript_segments'])[1] == row['transcript_segments'][1]
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
    from utils.agent_capabilities.transcripts import originals

    assert originals(restored['transcript_segments']) == row['transcript_segments']
    assert restored['structured'] == row['structured']
    assert (
        dream_tools.apply_edit(uid, edit.model_copy(update={'target': 'conversations/synthetic#12.5'}), records)
        == 'suppressed'
    )


@pytest.fixture(autouse=True)
def review_journal_available(monkeypatch):
    monkeypatch.setenv('REVIEW_SURFACE_MODE', 'on')


def test_dirty_queue_transforms_queries_and_transaction_deletes(monkeypatch):
    host = os.environ.get('FIRESTORE_EMULATOR_HOST', '')
    if not host.startswith(('127.0.0.1:', 'localhost:')):
        pytest.skip('local Firestore emulator required')
    database = emulator_client()
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
    assert dream_store.spend_ref(database, uid, lease['day']).get().to_dict()['reserved_usd'] == pytest.approx(0)

    lease = dream_store.acquire(uid, Caps(), firestore_client=database)
    dream_store.finish(uid, lease, {'tokens': 0}, success=False, release=False, refund=True, firestore_client=database)
    data = state.get().to_dict()
    assert data['passes'] == 1 and data['lease']['run_id'] == lease['run_id']
    assert dream_store.spend_ref(database, uid, lease['day']).get().to_dict()['reserved_usd'] == pytest.approx(0)
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
    database = emulator_client()
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
    database = emulator_client()
    uid = 'synthetic-' + str(uuid4())
    monkeypatch.setenv('DREAM_AGENT_ENABLED', 'true')
    monkeypatch.setenv('DREAM_AGENT_ELIGIBILITY', 'all')
    monkeypatch.setenv('DREAM_AGENT_UID_ALLOWLIST', uid)
    database.collection('users').document(uid).set({})
    caps = Caps(passes=10, daily_usd=250)
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
    database = emulator_client()
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
    database = emulator_client()
    uid = 'synthetic-abandoned-' + str(uuid4())
    monkeypatch.setenv('DREAM_AGENT_ENABLED', 'true')
    monkeypatch.setenv('DREAM_AGENT_ELIGIBILITY', 'all')
    monkeypatch.setenv('DREAM_AGENT_UID_ALLOWLIST', uid)
    old_time = datetime(2026, 10, 14, 23, 0, tzinfo=timezone.utc)
    now = old_time + timedelta(days=1)
    caps = Caps(tokens=24000, passes=24, daily_usd=250)
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
    assert old_spend.get().to_dict()['reserved_usd'] == pytest.approx(0)
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
    assert old_spend.get().to_dict()['reserved_usd'] == pytest.approx(0)
    new_spend = dream_store.spend_ref(database, uid, new['day'])
    assert new_spend.get().to_dict()['reserved_usd'] == pytest.approx(0)
    assert [s.to_dict() for s in dream_store.dirty_refs(uid, firestore_client=database)] == pending
    report = review_store.decode_doc(uid, dream_store.own_run(uid, old['run_id'], firestore_client=database))
    assert report['source']['usage_unknown'] is True and report['source']['reason'] == 'abandoned'
    assert report['source']['budget_charge_usd'] == pytest.approx(0)
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
    assert new_spend.get().to_dict()['reserved_usd'] == pytest.approx(0)
    assert [s.to_dict() for s in dream_store.dirty_refs(uid, firestore_client=database)] == pending


def test_manual_overlay_projection_boundaries_dependencies_and_atomic_invalidation(monkeypatch):
    from database import review_changes
    from utils.agent_capabilities import tools
    from utils.agent_capabilities.transcripts import originals

    host = os.environ.get('FIRESTORE_EMULATOR_HOST', '')
    if not host.startswith(('127.0.0.1:', 'localhost:')):
        pytest.skip('local Firestore emulator required')
    database = emulator_client()
    monkeypatch.setattr(_client, '_firestore_client', database)
    uid = 'synthetic-manual-overlay-' + str(uuid4())
    document = database.collection('users').document(uid).collection('conversations').document('synthetic')
    row = {
        'id': 'synthetic',
        'visibility': 'shared',
        'status': 'completed',
        'data_protection_level': 'enhanced',
        'client_processing': {'synthetic_stale_projection': True},
        'structured': {
            'title': 'Invented workshop',
            'sections': [{'heading': 'Plan', 'body_markdown': '- A synthetic plan', 'source_segment_ids': ['s1']}],
        },
        'transcript_segments': [
            {'id': 's1', 'start': 0, 'end': 5, 'text': 'Qorby plans an invented workshop.'},
            {'id': 's2', 'start': 6, 'end': 8, 'text': 'This other segment stays unchanged.'},
        ],
    }
    original = conversations.encode_conversation_for_write(uid, row, 'enhanced')
    document.set(original)
    edit = Edit(
        kind='spelling',
        target='conversations/synthetic#s1',
        before='Qorby',
        after='Qorbi',
        reason='Synthetic explicit spelling',
        evidence=['conversations/synthetic#s1'],
    )
    assert tools.apply_edit(uid, edit, {'conversations/synthetic': row}) == 'applied'
    first_id = str(uuid5(NAMESPACE_URL, uid + ':' + tools.edit_key(edit, {'conversations/synthetic': row})))
    # The existing manual API works independently of autonomous Review enablement.
    monkeypatch.setenv('REVIEW_SURFACE_MODE', 'off')
    assert (
        conversations.update_conversation_segment_text(
            uid, 'synthetic', 's1', 'Owner corrected synthetic workshop wording.'
        )
        == 'ok'
    )
    raw = document.get().to_dict()
    assert raw['transcript_segments'] == original['transcript_segments']
    assert 'client_processing' not in raw
    assert raw['structured']['sections'][0]['source_segment_ids'] == []
    entries = review_store.decode_doc(
        uid,
        database.collection('users')
        .document(uid)
        .collection('transcript_corrections')
        .document('synthetic')
        .get()
        .to_dict(),
    )['source']
    manual_id = entries[-1]['change_id']
    assert entries[-1]['source'] == 'user' and entries[-1]['depends_on'] == [first_id]
    projected = conversations.prepare_conversation_for_read(raw, uid)
    assert projected['transcript_segments'][0]['text'] == 'Owner corrected synthetic workshop wording.'
    assert projected['transcript_segments'][0]['original_text'] == row['transcript_segments'][0]['text']
    assert originals(projected['transcript_segments'])[1] == row['transcript_segments'][1]
    mcp = conversations.get_mcp_conversations_by_id(
        uid, ['synthetic'], include_transcript=True, firestore_client=database
    )
    public = conversations.get_public_shared_conversation_bounded(uid, 'synthetic', firestore_client=database)
    assert (
        mcp[0]['transcript_segments'][0]['text']
        == public['transcript_segments'][0]['text']
        == projected['transcript_segments'][0]['text']
    )
    with pytest.raises(review_store.ReviewConflict, match='dependent newer correction'):
        review_changes.set_undone(uid, first_id, True)
    undone = review_changes.set_undone(uid, manual_id, True)
    assert review_changes.set_undone(uid, manual_id, True) == undone
    raw = document.get().to_dict()
    assert raw['transcript_segments'] == original['transcript_segments']
    assert 'client_processing' not in raw
    assert raw['structured']['sections'] == original['structured']['sections']
    assert 'has_user_transcript_corrections' not in raw
    assert conversations.prepare_conversation_for_read(raw, uid)['transcript_segments'][0]['text'].startswith('Qorbi')
    review_changes.set_undone(uid, first_id, True)
    with pytest.raises(review_store.ReviewConflict, match='depends on an undone correction'):
        review_changes.set_undone(uid, manual_id, False)
    review_changes.set_undone(uid, first_id, False)
    review_changes.set_undone(uid, manual_id, False)
    assert (
        conversations.prepare_conversation_for_read(document.get().to_dict(), uid)['transcript_segments'][0]['text']
        == 'Owner corrected synthetic workshop wording.'
    )

    from utils.conversations.transcript_hash import transcript_sha256

    assert not conversations.bind_client_processing(
        uid,
        'synthetic',
        {'client_processing': {'transcript_sha256': transcript_sha256(row['transcript_segments'])}},
        firestore_client=database,
    )
    current = conversations.prepare_conversation_for_read(document.get().to_dict(), uid)
    digest = transcript_sha256(current['transcript_segments'])
    assert conversations.bind_client_processing(
        uid, 'synthetic', {'client_processing': {'transcript_sha256': digest}}, firestore_client=database
    )
    review_changes.set_undone(uid, manual_id, True)
    assert 'client_processing' not in document.get().to_dict()
    review_changes.set_undone(uid, first_id, True)
    assert document.get().to_dict()['client_processing'] == original['client_processing']
    assert document.get().to_dict()['transcript_segments'] == original['transcript_segments']


def test_due_queue_discovers_owners_once_orders_staleness_and_reschedules_caps(monkeypatch):
    from database import dream_scheduler
    from config import dream_control

    database = emulator_client()
    monkeypatch.setattr(dream_control, 'allowed', lambda: True)
    monkeypatch.setenv('DREAM_AGENT_ENABLED', 'true')
    monkeypatch.setenv('DREAM_AGENT_ELIGIBILITY', 'all')
    monkeypatch.setenv('REVIEW_SURFACE_MODE', 'on')
    now = datetime.now(timezone.utc)
    for key, ago in [('synthetic-old', 3), ('synthetic-new', 1), ('synthetic-fresh', 0)]:
        database.collection('users').document(key).set({})
        database.collection('dream_users').document(key).set({'last_attempt_at': now - timedelta(days=ago)})
    selected = dream_scheduler.candidates(limit=5000, now=now, firestore_client=database)
    assert selected == ['synthetic-old', 'synthetic-new']
    # Independent discovery cursor advances even with no session admitted.
    assert database.collection('dream_scheduler').document('discovery').get().to_dict()['after'] is None
    database.collection('dream_users').document('synthetic-old').set(
        {'day': now.date().isoformat(), 'passes': 2}, merge=True
    )
    assert dream_store.acquire('synthetic-old', Caps(), now=now, firestore_client=database) is None
    assert 'synthetic-old' not in dream_scheduler.candidates(limit=5000, now=now, firestore_client=database)
    # A dirty write atomically requeues a future hunt; discovery never overwrites it.
    dream_store.mark_dirty('synthetic-fresh', [('conversations', 'invented')], firestore_client=database)
    assert dream_scheduler.candidates(limit=5000, now=now, firestore_client=database)[0] == 'synthetic-fresh'


def test_real_flag_doc_can_stop_all_dream_hosts_without_env_rollout(monkeypatch):
    from config import dream_control

    database = emulator_client()
    monkeypatch.setattr(_client, 'get_firestore_client', lambda: database)
    ref = database.collection('dream_control').document('global')
    ref.set({'enabled': False})
    assert dream_control.load_flag() is False
    ref.set({'enabled': True})
    assert dream_control.load_flag() is True


def test_real_merge_relocates_offsets_and_undo_receipts_without_rewriting_capture(monkeypatch):
    from copy import deepcopy
    from database import review_changes, review_transcript_changes
    from database.review_overlay_merge import transfer

    database = emulator_client()
    monkeypatch.setattr(_client, '_firestore_client', database)
    monkeypatch.setenv('REVIEW_SURFACE_MODE', 'on')
    uid = 'synthetic-overlay-merge-' + str(uuid4())
    owner = database.collection('users').document(uid)
    owner.set({})
    source = {
        'id': 'one',
        'status': 'completed',
        'data_protection_level': 'enhanced',
        'transcript_segments': [{'id': 'speech', 'start': 0, 'end': 4, 'text': 'Invented workshop plan.'}],
    }
    prefix = {
        'id': 'prefix',
        'status': 'completed',
        'data_protection_level': 'enhanced',
        'transcript_segments': [{'id': 'intro', 'start': 0, 'end': 2, 'text': 'Synthetic introduction.'}],
    }
    for row in [source, prefix]:
        owner.collection('conversations').document(row['id']).set(
            conversations.encode_conversation_for_write(uid, row, 'enhanced')
        )
    assert (
        review_transcript_changes.edit_user_segment(uid, 'one', 'speech', 'Owner requested synthetic wording.') == 'ok'
    )
    journal = next(owner.collection('review_changes').stream())
    change_id = review_store.require_doc(uid, journal.to_dict())['change']['change_id']
    merged = {
        **source,
        'id': 'merged',
        'transcript_segments': [
            *prefix['transcript_segments'],
            {**source['transcript_segments'][0], 'start': 100, 'end': 104},
        ],
    }
    merged_doc = owner.collection('conversations').document('merged')
    merged_raw = conversations.encode_conversation_for_write(uid, merged, 'enhanced')
    merged_doc.set(merged_raw)
    assert transfer(uid, ['prefix', 'one'], 'merged', firestore_client=database)
    moved = review_store.require_doc(uid, journal.reference.get().to_dict())['transcript_overlay']
    assert moved['conversation_id'] == 'merged' and moved['corrections'][0]['segment_index'] == 1
    assert moved['corrections'][0]['start'] == 100
    assert review_transcript_changes.edit_user_segment(uid, 'one', 'speech', 'A stale source write.') == 'conflict'
    assert (
        conversations.get_conversation(uid, 'merged')['transcript_segments'][1]['text']
        == 'Owner requested synthetic wording.'
    )
    review_changes.set_undone(uid, change_id, True)
    assert conversations.get_conversation(uid, 'merged')['transcript_segments'][1]['text'] == 'Invented workshop plan.'
    assert merged_doc.get().to_dict()['transcript_segments'] == merged_raw['transcript_segments']
    review_changes.set_undone(uid, change_id, False)
    assert (
        conversations.get_conversation(uid, 'merged')['transcript_segments'][1]['text']
        == 'Owner requested synthetic wording.'
    )


def test_merge_seals_sources_even_when_no_overlay_existed_at_admission(monkeypatch):
    from database import review_transcript_changes
    from database.review_overlay_merge import transfer

    database = emulator_client()
    monkeypatch.setattr(_client, '_firestore_client', database)
    uid = 'synthetic-plain-merge-' + str(uuid4())
    owner = database.collection('users').document(uid)
    owner.set({})
    row = {
        'id': 'source',
        'status': 'completed',
        'data_protection_level': 'enhanced',
        'transcript_segments': [{'id': 'speech', 'start': 0, 'end': 4, 'text': 'An invented capture.'}],
    }
    for key in ['source', 'destination']:
        owner.collection('conversations').document(key).set(
            conversations.encode_conversation_for_write(uid, {**row, 'id': key}, 'enhanced')
        )
    assert transfer(uid, ['source'], 'destination', firestore_client=database)
    assert review_transcript_changes.edit_user_segment(uid, 'source', 'speech', 'Stale source wording.') == 'conflict'
    assert (
        review_transcript_changes.edit_user_segment(uid, 'destination', 'speech', 'Requested destination wording.')
        == 'ok'
    )
