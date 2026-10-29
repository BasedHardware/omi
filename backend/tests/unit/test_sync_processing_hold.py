"""Occasion step 1: paid admission over synthetic content and durable worker wakes."""

from unittest.mock import Mock

import pytest

from database.outbox_firestore import ENRICHMENT_OUTBOX
from utils.conversations.summary_delivery import PROCESS_CONTEXT
from utils.enrichment import callback, custody, smart_refresh
from utils.enrichment.consumer import EnrichmentConsumer
from utils.workers.consumer import run_push
from tests.unit.test_conversation_smart_merge import World
from utils.conversations import smart_merge, sync_hold_completion
from utils.conversations.processing_trigger import ProcessingTrigger

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


def test_policy_reload_preserves_outcome_counts():
    import importlib
    from prometheus_client import REGISTRY

    hold.record('ready')
    before = REGISTRY.get_sample_value('omi_sync_processing_hold_total', {'outcome': 'ready'})
    importlib.reload(hold)
    hold.record('ready')
    assert REGISTRY.get_sample_value('omi_sync_processing_hold_total', {'outcome': 'ready'}) == before + 1


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
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
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


def test_first_summary_repair_cannot_bypass_a_stored_hold(monkeypatch):
    current = row()
    monkeypatch.setattr(callback.conversations_db, 'get_conversation', lambda *_: current)
    monkeypatch.setattr(callback, 'repair_fenced', lambda _: False)
    monkeypatch.setattr(callback.time, 'time', lambda: 200)
    full = Mock(side_effect=AssertionError('repair cannot process during quiet window'))
    monkeypatch.setattr(callback, 'process_conversation', full)
    context = {'owner': 'repair', 'lease_until': 1000, 'first_pending_at': 100}
    token = PROCESS_CONTEXT.set(context)
    try:
        assert callback.enrich_conversation('u', 'c', 'en') is None
    finally:
        PROCESS_CONTEXT.reset(token)
    assert context['defer_until'] == 700 and context['sync_hold']
    full.assert_not_called()


@pytest.mark.parametrize('has_summary', [True, False])
def test_late_wal_after_smart_refresh_still_processes_new_content(monkeypatch, has_summary):
    world = World(monkeypatch)
    world.add(
        'parent',
        0,
        5,
        sync_content_revision=3,
        **{hold.FIELD: {'pending_since': 100, 'last_content_at': 100}},
        smart_merge={'role': 'survivor', 'revision': 2, 'refreshed_revision': 2, 'processed_sync_revision': 2}
    )
    current = world.get('user-1', 'parent')
    monkeypatch.setattr(callback.conversations_db, 'get_conversation', lambda *_: current)
    complete = Mock(return_value=True)
    monkeypatch.setattr(callback.conversations_db, 'complete_sync_processing_hold', complete)
    monkeypatch.setattr(callback, 'repair_fenced', lambda _: False)
    monkeypatch.setattr(callback, 'claim_from_snapshot', lambda *_: True)
    monkeypatch.setattr(callback, 'get_firestore_client', lambda: world.store)
    monkeypatch.setattr(callback, 'schedule_after_finalization', lambda *_: None)
    monkeypatch.setattr(callback.time, 'time', lambda: 700)
    if not has_summary:
        current['structured'] = {'title': 'Synthetic minimum'}
    full = Mock(return_value=callback.deserialize_conversation(current))
    smart = Mock(side_effect=AssertionError('a completed merge receipt cannot consume new WAL content'))
    monkeypatch.setattr(callback, 'process_conversation', full)
    monkeypatch.setattr(callback, 'settle_survivor', smart)
    token = PROCESS_CONTEXT.set({'owner': 'worker', 'lease_until': 1000, 'first_pending_at': 100, 'sync_hold': True})
    try:
        callback.enrich_conversation('user-1', 'parent', 'en')
    finally:
        PROCESS_CONTEXT.reset(token)
    full.assert_called_once()
    smart.assert_not_called()
    assert complete.call_count == int(has_summary)


@pytest.mark.parametrize(
    'stage,emulator,expected',
    [('prod', '', True), ('dev', '', False), ('local', '127.0.0.1:8080', True), ('', '', False)],
)
def test_hold_scheduling_respects_the_existing_outbox_runtime_boundary(monkeypatch, stage, emulator, expected):
    monkeypatch.setenv('OMI_ENV_STAGE', stage)
    monkeypatch.setenv('FIRESTORE_EMULATOR_HOST', emulator)
    assert hold.scheduling_enabled() is expected


@pytest.mark.parametrize('switch_on', [True, False])
@pytest.mark.parametrize('trigger', ['client_finalize', 'backlog_choice', 'first_open', 'user_reprocess'])
def test_explicit_end_satisfies_hold_immediately_without_spending_late_budget(monkeypatch, trigger, switch_on):
    world = World(monkeypatch)
    world.add('parent', 0, 5, sync_content_revision=2, **{hold.FIELD: {'pending_since': 100, 'last_content_at': 100}})
    current = world.get('user-1', 'parent')
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    monkeypatch.setenv('SYNC_PROCESSING_HOLD_ENABLED', str(switch_on).lower())
    sync_hold_completion.complete_explicit(
        'user-1', callback.deserialize_conversation(current), ProcessingTrigger(trigger)
    )
    state = world.raw('parent')[hold.FIELD]
    assert state['pending_since'] is None and state['late_runs'] == 0
    assert hold.admission(world.get('user-1', 'parent'), {'first_pending_at': 100}, now=700) == ('unchanged', None)


def test_settled_survivor_uses_existing_refresh_lease_and_checkpoint_once(monkeypatch):
    world = World(monkeypatch)
    world.add(
        'parent',
        0,
        5,
        sync_content_revision=2,
        smart_merge={'role': 'survivor', 'revision': 2, 'refreshed_revision': 1},
    )
    smart_refresh.settle_survivor('user-1', 'parent', owner='worker')
    smart_refresh.settle_survivor('user-1', 'parent', owner='retry')
    assert len(world.processed) == 1
    assert world.raw('parent')['smart_merge']['refreshed_revision'] == 2


def test_relevance_discard_never_spends_the_first_full_summary_budget(monkeypatch):
    world = World(monkeypatch)
    world.add('parent', 0, 5, sync_content_revision=2, **{hold.FIELD: {'pending_since': 100, 'last_content_at': 100}})
    current = world.get('user-1', 'parent')
    monkeypatch.setattr(callback.conversations_db, 'get_conversation', lambda *_: current)
    monkeypatch.setattr(callback, 'repair_fenced', lambda _: False)
    monkeypatch.setattr(callback, 'claim_from_snapshot', lambda *_: True)
    monkeypatch.setattr(callback, 'get_firestore_client', lambda: world.store)
    monkeypatch.setattr(callback, 'schedule_after_finalization', lambda *_: None)
    monkeypatch.setattr(callback.time, 'time', lambda: 700)
    discarded = callback.deserialize_conversation({**current, 'discarded': True, 'structured': {'title': 'Minimum'}})
    monkeypatch.setattr(callback, 'process_conversation', Mock(return_value=discarded))
    token = PROCESS_CONTEXT.set({'owner': 'worker', 'lease_until': 1000, 'first_pending_at': 100, 'sync_hold': True})
    try:
        callback.enrich_conversation('user-1', 'parent', 'en')
    finally:
        PROCESS_CONTEXT.reset(token)
    state = world.raw('parent')[hold.FIELD]
    assert 'full_snapshot' not in state and state['pending_since'] is None
    # A later small fragment can promote the row and still receive its first notes.
    promoted = {**current, hold.FIELD: hold.activity_patch({hold.FIELD: state}, 1000)}
    assert hold.admission(promoted, {'first_pending_at': 1000}, now=1600) == ('ready', None)


@pytest.mark.parametrize('snapshot_present', [True, False])
@pytest.mark.parametrize('marker', [{'wipe_status': 'pending'}, {'wipe_status': 'completed'}, {}])
def test_completion_receipt_rechecks_deletion_after_worker_claim(monkeypatch, snapshot_present, marker):
    from copy import deepcopy
    from database import conversations as conversations_db

    world = World(monkeypatch)
    world.add('parent', 0, 5, sync_content_revision=2, **{hold.FIELD: {'pending_since': 100, 'held': True}})
    snapshot = hold.content_snapshot(world.get('user-1', 'parent')) if snapshot_present else None
    before = deepcopy(world.raw('parent'))
    # The worker already read/claimed the revision before deletion began.
    world.store.rows[('account_deletions', 'user-1')] = marker
    assert not conversations_db.complete_sync_processing_hold(
        'user-1', 'parent', 2, snapshot, firestore_client=world.store
    )
    assert world.raw('parent') == before
    assert not world.store.transactions[-1].updates


@pytest.mark.parametrize('runner', ['consumer', 'legacy'])
def test_budget_deferral_retains_late_revision_until_funding_returns(state, monkeypatch, runner):
    from utils.conversations import process_conversation as processor

    rows, tasks = state
    monkeypatch.setattr(custody, 'discard_blocked', lambda _: False)
    monkeypatch.setattr(processor.funded_processing, 'enabled', lambda *_: True)
    allowed = False
    monkeypatch.setattr(processor.funded_processing, 'processing_allowed', lambda *_: allowed)
    world = World(monkeypatch)
    world.add('c', 0, 5, sync_content_revision=2)
    current = world.get('user-1', 'c')
    current['transcript_segments'][0].update(text='synthetic ' * 100, end=100)
    previous = hold.content_snapshot(current)
    previous.update(digest='previous', words=0, speech_seconds=0, revision=1)
    current[hold.FIELD] = dict(pending_since=100, last_content_at=100, held=True, full_snapshot=previous)
    monkeypatch.setattr(callback.conversations_db, 'get_conversation', lambda *_: current)
    monkeypatch.setattr(callback, 'claim_from_snapshot', lambda *_: True)
    monkeypatch.setattr(callback, 'repair_fenced', lambda _: False)
    monkeypatch.setattr(callback, 'get_firestore_client', lambda: world.store)
    monkeypatch.setattr(callback, 'schedule_after_finalization', lambda *_: None)
    monkeypatch.setattr(callback.time, 'time', lambda: 700)
    monkeypatch.setattr(processor.time, 'time', lambda: 700)
    complete = Mock(return_value=True)
    monkeypatch.setattr(callback.conversations_db, 'complete_sync_processing_hold', complete)
    monkeypatch.setattr(callback, 'process_conversation', processor.process_conversation)
    outbox.mark('user-1', 'c', 'en', now=100, sync_hold=True)
    key = outbox.key('user-1', 'c')

    def deliver(now):
        if runner == 'consumer':
            return run_push(
                EnrichmentConsumer(ENRICHMENT_OUTBOX), ENRICHMENT_OUTBOX, key, tasks[-1]['task_token'], now=now
            ).outcome
        return outbox.run(key, tasks[-1]['task_token'], callback.enrich_conversation, now=now)

    assert deliver(700) == 'deferred'
    assert key in rows and rows[key]['due_at'] == 1300 and rows[key]['lease_until'] == 0
    assert current[hold.FIELD]['held'] and current[hold.FIELD].get('late_runs', 0) == 0
    complete.assert_not_called()
    # Funding returns without a new WAL append: the retained wake processes it.
    allowed = True
    full = Mock(return_value=callback.deserialize_conversation(current))
    monkeypatch.setattr(callback, 'process_conversation', full)
    assert deliver(1300) in {'done', 'processed'}
    full.assert_called_once()
    complete.assert_called_once()
    assert key not in rows or rows[key].get('dormant')


@pytest.mark.parametrize('runner', ['consumer', 'legacy'])
def test_lazy_effects_near_deadline_wait_for_late_hold_receipt(state, monkeypatch, runner):
    from utils.conversations import lazy_enrichment, process_conversation as processor

    rows, tasks = state
    monkeypatch.setattr(custody, 'discard_blocked', lambda _: False)
    world = World(monkeypatch)
    world.add('c', 0, 5, sync_content_revision=2)
    current = world.get('user-1', 'c')
    # Prior effects are due at 3540; late content arrived ten seconds before it.
    current[hold.FIELD] = dict(pending_since=3530, last_content_at=3530, held=True)
    monkeypatch.setattr(lazy_enrichment.conversations_db, 'get_conversation', lambda *_: current)
    apply = Mock()
    checkpoint = Mock()
    monkeypatch.setattr(processor, 'apply_settled_enrichment', apply)
    monkeypatch.setattr(lazy_enrichment.conversations_db, 'record_demand_enrichment_checkpoint', checkpoint)
    monkeypatch.setenv('DEMAND_PROCESSING_ENABLED', 'true')
    monkeypatch.setenv('DEMAND_PROCESSING_PERCENT', '100')
    from utils.conversations import demand_processing

    monkeypatch.setattr(demand_processing, 'admit', lambda *_a, **_k: True)
    clock = [3540]
    monkeypatch.setattr(lazy_enrichment.time, 'time', lambda: clock[0])
    outbox.mark('user-1', 'c', 'en', now=2940, effects_only=True)
    key = outbox.key('user-1', 'c' + chr(0) + 'effects')

    def deliver():
        if runner == 'consumer':
            return run_push(
                EnrichmentConsumer(ENRICHMENT_OUTBOX), ENRICHMENT_OUTBOX, key, tasks[-1]['task_token'], now=clock[0]
            ).outcome
        return outbox.run(key, tasks[-1]['task_token'], Mock(), now=clock[0])

    assert deliver() == 'deferred'
    apply.assert_not_called()
    checkpoint.assert_not_called()
    assert rows[key]['lease_until'] == 0 and rows[key]['due_at'] == 3660
    # User demand cannot bypass this new prerequisite on an early delivery.
    clock[0] = 3541
    assert deliver() == 'deferred'
    apply.assert_not_called()
    assert rows[key]['due_at'] == 3660
    # Passing the quiet deadline alone is insufficient: a cap/worker can delay notes.
    clock[0] = 4200
    assert deliver() == 'deferred'
    apply.assert_not_called()
    current['structured']['overview'] = 'Settled late revision'
    current[hold.FIELD] = hold.completion_patch(current, hold.content_snapshot(current))
    clock[0] = 4320
    assert deliver() in {'done', 'processed'}
    apply.assert_called_once()
    assert apply.call_args.args[1].structured.overview == 'Settled late revision'
    checkpoint.assert_called_once()


def test_rollback_sweep_releases_future_holds_and_fences_old_delivery(state, monkeypatch):
    from types import SimpleNamespace

    rows, tasks = state
    for cid in ('held', 'leased', 'ordinary'):
        outbox.mark('u', cid, 'en', now=100, sync_hold=cid != 'ordinary')
    key = outbox.key('u', 'held')
    old_token = rows[key]['task_token']
    rows[key]['wake_check_after'] = 700
    leased = rows[outbox.key('u', 'leased')]
    leased.update(owner='active', lease_until=500)
    monkeypatch.setenv('SYNC_PROCESSING_HOLD_ENABLED', 'false')
    query = Mock()
    query.where.return_value = query
    query.order_by.return_value = query
    query.limit.return_value = query
    query.stream.return_value = [SimpleNamespace(id=key) for key in rows]
    monkeypatch.setattr(outbox, 'get_firestore_client', lambda: SimpleNamespace(collection=lambda _: query))
    assert outbox.sweep(now=101) == {'repaired': 1, 'error': 0}
    assert rows[key]['due_at'] == 101 and rows[key]['task_token'] != old_token
    assert leased['lease_until'] == 500
    assert rows[outbox.key('u', 'ordinary')]['due_at'] == 700
    process = Mock()
    assert outbox.run(key, old_token, process, now=101) == 'stale'
    assert outbox.run(key, rows[key]['task_token'], process, now=101) == 'processed'
    process.assert_called_once()


@pytest.mark.parametrize('status', ['cancelled', 'billing_failed'])
def test_completion_receipt_respects_restored_account_access(monkeypatch, status):
    from database import conversations as conversations_db

    world = World(monkeypatch)
    world.add('parent', 0, 5, sync_content_revision=2, **{hold.FIELD: {'pending_since': 100, 'held': True}})
    world.store.rows[('account_deletions', 'user-1')] = {'wipe_status': status}
    assert conversations_db.complete_sync_processing_hold('user-1', 'parent', 2, None, firestore_client=world.store)
    assert not world.raw('parent')[hold.FIELD]['held']


def test_rollback_processing_settles_hold_before_lazy_effects(monkeypatch):
    from utils.conversations import lazy_enrichment, process_conversation as processor

    world = World(monkeypatch)
    world.add('parent', 0, 5, sync_content_revision=2, **{hold.FIELD: {'pending_since': 100, 'held': True}})
    monkeypatch.setenv('SYNC_PROCESSING_HOLD_ENABLED', 'false')
    monkeypatch.setattr(callback, 'repair_fenced', lambda _: False)
    monkeypatch.setattr(callback, 'claim_from_snapshot', lambda *_: True)
    monkeypatch.setattr(callback, 'get_firestore_client', lambda: world.store)
    monkeypatch.setattr(callback, 'schedule_after_finalization', lambda *_: None)
    full = Mock(return_value=callback.deserialize_conversation(world.get('user-1', 'parent')))
    monkeypatch.setattr(callback, 'process_conversation', full)
    token = PROCESS_CONTEXT.set({'owner': 'worker', 'lease_until': 1000, 'first_pending_at': 100, 'sync_hold': True})
    try:
        callback.enrich_conversation('user-1', 'parent', 'en')
    finally:
        PROCESS_CONTEXT.reset(token)
    full.assert_called_once()
    assert not world.raw('parent')[hold.FIELD]['held']
    apply = Mock()
    monkeypatch.setattr(processor, 'apply_settled_enrichment', apply)
    monkeypatch.setattr(lazy_enrichment.conversations_db, 'record_demand_enrichment_checkpoint', Mock())
    lazy_enrichment.enrich_settled('user-1', 'parent', 'en')
    apply.assert_called_once()


def test_deferred_effects_wake_respects_settlement_deadline_on_demand(state, monkeypatch):
    from utils.conversations import demand_processing
    from tests.unit.test_sync_reprocess_coalesce import _ENQUEUE

    rows, tasks = state
    outbox.mark('u', 'c', 'en', now=100, effects_only=True)
    current = dict(tasks[-1], deferred_reason='not_due', due_at=950, task_due_at=950)
    schedule = Mock(return_value=True)
    monkeypatch.setattr(demand_processing, 'schedule', schedule)
    _ENQUEUE(current)
    assert not schedule.call_args.kwargs['effects_only']
    assert schedule.call_args.kwargs['not_before'] == 950
    assert not outbox.effects_may_run_early(current)
    assert outbox.effects_may_run_early(dict(current, deferred_reason=None))


def test_explicit_rollback_only_settles_existing_hold_metadata(monkeypatch):
    world = World(monkeypatch)
    world.add('parent', 0, 5, sync_content_revision=2)
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    monkeypatch.setenv('SYNC_PROCESSING_HOLD_ENABLED', 'false')
    complete = Mock()
    monkeypatch.setattr(callback.conversations_db, 'complete_sync_processing_hold', complete)
    sync_hold_completion.complete_explicit(
        'user-1', callback.deserialize_conversation(world.get('user-1', 'parent')), ProcessingTrigger.BACKLOG_CHOICE
    )
    complete.assert_not_called()
    assert hold.FIELD not in world.raw('parent')
