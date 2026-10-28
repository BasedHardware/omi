"""Occasion step 1: paid admission over synthetic content and durable worker wakes."""

from unittest.mock import Mock

import pytest

from database.outbox_firestore import ENRICHMENT_OUTBOX
from utils.conversations.summary_delivery import PROCESS_CONTEXT
from utils.enrichment import callback, custody
from utils.enrichment.consumer import EnrichmentConsumer
from utils.workers.consumer import run_push
from tests.unit.test_conversation_smart_merge import World
from utils.conversations import smart_merge

from utils.sync import processing_hold as hold
from utils.enrichment import outbox
from tests.unit.test_sync_reprocess_coalesce import state


def row(words=100, seconds=60):
    return {
        'id': 'c',
        'finished_at': 60,
        'sync_content_revision': 1,
        'transcript_segments': [{'text': 'word ' * words, 'start': 0, 'end': seconds}],
        hold.FIELD: {'pending_since': 100, 'last_content_at': 100, 'held': True},
    }


def test_parent_waits_for_last_content_and_merge_then_runs_once(state):
    rows, tasks = state
    obligation = {'first_pending_at': 100}
    conversation = row()
    conversation[hold.FIELD]['last_content_at'] = 300
    conversation['smart_merge'] = {'last_merged_at': 450}
    assert hold.admission(conversation, obligation, now=900) == ('quiet_wait', 1050)
    assert hold.admission(conversation, obligation, now=1050) == ('ready', None)
    for at in (100, 300, 450):
        outbox.mark('u', 'c', 'en', now=at, sync_hold=True)
    key = outbox.key('u', 'c')
    process = Mock()
    assert outbox.run(key, tasks[-1]['task_token'], process, now=700) == 'deferred'
    process.assert_not_called()
    assert outbox.run(key, tasks[-1]['task_token'], process, now=1050) == 'processed'
    assert outbox.run(key, tasks[-1]['task_token'], process, now=1051) == 'stale'
    process.assert_called_once()


def test_material_late_audio_refinalizes_once_and_cannot_reset_budget():
    conversation = row()
    conversation[hold.FIELD] = hold.completion_patch(conversation, hold.content_snapshot(conversation))
    conversation[hold.FIELD] = hold.activity_patch(conversation, 1000)
    conversation['transcript_segments'][0].update(text='word ' * 200, end=120)
    assert hold.admission(conversation, {'first_pending_at': 1000}, now=1600) == ('ready', None)
    conversation[hold.FIELD] = hold.completion_patch(conversation, hold.content_snapshot(conversation))
    conversation[hold.FIELD] = hold.activity_patch(conversation, 2000)
    conversation['transcript_segments'][0].update(text='word ' * 400, end=240)
    assert hold.admission(conversation, {'first_pending_at': 2000}, now=2600) == ('late_cap', None)
    assert conversation[hold.FIELD]['late_runs'] == 1


def test_immaterial_and_replayed_content_buy_no_full_run():
    conversation = row()
    conversation[hold.FIELD] = hold.completion_patch(conversation, hold.content_snapshot(conversation))
    assert hold.admission(conversation, {'first_pending_at': 100}, now=700) == ('unchanged', None)
    conversation['transcript_segments'][0]['text'] += 'tiny change'
    assert hold.admission(conversation, {'first_pending_at': 100}, now=700) == ('immaterial', None)


def test_max_hold_overrides_continuous_content_and_lagging_watermark(state):
    rows, tasks = state
    conversation = row()
    conversation[hold.FIELD].update(last_content_at=3600, upload_watermark_at=50)
    assert hold.admission(conversation, {'first_pending_at': 100}, now=3699) == ('quiet_wait', 3700)
    assert hold.admission(conversation, {'first_pending_at': 100}, now=3700) == ('max_hold', None)
    for at in (100, 1000, 2000, 3000, 3600):
        outbox.mark('u', 'c', 'en', now=at, sync_hold=True)
    assert rows[outbox.key('u', 'c')]['due_at'] == 3700


def test_optional_watermark_must_pass_quiet_gap():
    conversation = row()
    conversation[hold.FIELD]['upload_watermark_at'] = 659
    assert hold.admission(conversation, {'first_pending_at': 100}, now=700) == ('watermark_wait', 1300)
    conversation[hold.FIELD]['upload_watermark_at'] = 660
    assert hold.admission(conversation, {'first_pending_at': 100}, now=700) == ('ready', None)


def test_kill_switch_drains_already_held_obligation_without_waiting(state, monkeypatch):
    rows, tasks = state
    outbox.mark('u', 'c', 'en', now=100, sync_hold=True)
    monkeypatch.setenv('SYNC_PROCESSING_HOLD_ENABLED', 'false')
    process = Mock()
    assert outbox.run(outbox.key('u', 'c'), tasks[-1]['task_token'], process, now=101) == 'processed'
    process.assert_called_once()


@pytest.mark.parametrize('value', ['false', 'off', '0', 'no'])
def test_kill_switch(value, monkeypatch):
    monkeypatch.setenv('SYNC_PROCESSING_HOLD_ENABLED', value)
    assert not hold.enabled()


def test_default_on(monkeypatch):
    monkeypatch.delenv('SYNC_PROCESSING_HOLD_ENABLED', raising=False)
    assert hold.enabled()


def test_merged_held_piece_transfers_to_parent_without_full_run(state, monkeypatch):
    rows, tasks = state
    outbox.mark('u', 'piece', 'en', now=100, sync_hold=True)
    key = outbox.key('u', 'piece')
    monkeypatch.setattr(custody, 'discard_blocked', lambda _: False)
    monkeypatch.setattr(
        callback.conversations_db, 'get_conversation', lambda *_: {'deleted': True, 'sync_merged_into': 'parent'}
    )
    monkeypatch.setattr(callback.conversations_db, 'resolve_sync_conversation_redirect', lambda *_: 'parent')
    full = Mock(side_effect=AssertionError('merged piece must not get full processing'))
    monkeypatch.setattr(callback, 'process_conversation', full)
    transferred = []

    def transfer(document, token, owner, canonical, *, now):
        transferred.append(canonical)
        rows.pop(document)
        return None

    monkeypatch.setattr(custody, 'transfer_redirect', transfer)
    result = run_push(EnrichmentConsumer(ENRICHMENT_OUTBOX), ENRICHMENT_OUTBOX, key, tasks[-1]['task_token'], now=700)
    assert result.reason == 'redirected'
    assert transferred == ['parent'] and key not in rows
    full.assert_not_called()


def test_real_consumer_keeps_hold_metadata_and_deferred_wake(state, monkeypatch):
    rows, tasks = state
    monkeypatch.setattr(custody, 'discard_blocked', lambda _: False)
    outbox.mark('u', 'c', 'en', now=100, sync_hold=True)
    key = outbox.key('u', 'c')

    def callback(*_):
        context = PROCESS_CONTEXT.get()
        assert context['sync_hold'] and context['first_pending_at'] == 100
        context.update(defer_reason='quiet_wait', defer_until=950)

    result = run_push(
        EnrichmentConsumer(ENRICHMENT_OUTBOX, process=callback),
        ENRICHMENT_OUTBOX,
        key,
        tasks[-1]['task_token'],
        now=700,
    )
    assert result.outcome == 'deferred'
    assert rows[key]['due_at'] == 950 and rows[key]['lease_until'] == 0


def test_smart_merge_refresh_is_handed_off_without_full_processing(monkeypatch):
    world = World(monkeypatch)
    world.add(
        'parent',
        0,
        5,
        **{hold.FIELD: {'pending_since': 100, 'last_content_at': 100}},
        smart_merge={'role': 'survivor', 'revision': 2, 'refreshed_revision': 1}
    )
    mark = Mock()
    monkeypatch.setattr(smart_merge.enrichment_outbox, 'mark', mark)
    smart_merge.refresh_survivor('user-1', 'parent', owner='synthetic')
    mark.assert_called_once_with('user-1', 'parent', 'en', sync_hold=True)
    assert world.raw('parent')['smart_merge']['delegated_revision'] == 2
    assert not world.processed


def test_completion_receipt_is_revision_fenced_and_preserves_late_budget(monkeypatch):
    from database import conversations as conversations_db

    world = World(monkeypatch)
    world.add('parent', 0, 5, sync_content_revision=2, **{hold.FIELD: {'pending_since': 100, 'last_content_at': 100}})
    snapshot = hold.content_snapshot(world.get('user-1', 'parent'))
    assert not conversations_db.complete_sync_processing_hold(
        'user-1', 'parent', 1, snapshot, firestore_client=world.store
    )
    assert 'full_snapshot' not in world.raw('parent')[hold.FIELD]
    assert conversations_db.complete_sync_processing_hold('user-1', 'parent', 2, snapshot, firestore_client=world.store)
    state = world.raw('parent')[hold.FIELD]
    assert state['full_snapshot'] == snapshot and state['late_runs'] == 0 and state['pending_since'] is None
    # A skipped immaterial epoch clears only the wait; it cannot reset a paid budget.
    state.update(pending_since=200, late_runs=1)
    assert conversations_db.complete_sync_processing_hold('user-1', 'parent', 2, None, firestore_client=world.store)
    assert world.raw('parent')[hold.FIELD]['late_runs'] == 1
