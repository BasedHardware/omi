"""Occasion step 2: execute the relevance -> merge -> notes boundary and real absorbs."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from config import merge_before_processing as switch
from database import conversations as conversations_db
from database import smart_merge as merge_db
from utils.conversations import merge_before_processing as boundary
from utils.conversations import process_conversation as process_module
from utils.conversations import smart_merge, finalizer, sync_hold_completion
from utils.conversations.factory import deserialize_conversation
from utils.conversations.processing_trigger import ProcessingTrigger
from utils.conversations.relevance import RelevanceDecision
from utils.conversations.summary_delivery import PROCESS_CONTEXT
from utils.sync import processing_hold as hold
from utils.enrichment import outbox, callback
from utils.enrichment.admission import ConversationAbsorbed
from tests.unit.test_conversation_smart_merge import World, UID, _path
from tests.unit.test_sync_reprocess_coalesce import state


@pytest.fixture
def world(monkeypatch):
    monkeypatch.delenv('CONVERSATION_MERGE_BEFORE_PROCESSING', raising=False)
    monkeypatch.setenv('CONVERSATION_SMART_MERGE_MODE', 'merge')
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    w = World(monkeypatch)
    w.add('p', 0, 10)
    w.add('n', 15, 10, status='processing', structured={})
    w.marks = []
    monkeypatch.setattr(smart_merge.enrichment_outbox, 'mark', lambda *a, **kw: w.marks.append((a, kw)))
    return w


def invoke(world, trigger=ProcessingTrigger.CAPTURE_END, **kwargs):
    boundary.before_notes(UID, deserialize_conversation(world.get(UID, 'n')), trigger, **kwargs)


@pytest.mark.parametrize('words', [0, 1, 24])
def test_ineligible_short_capture_never_loads_merge_worker(world, monkeypatch, words):
    conversation = deserialize_conversation(world.get(UID, 'n'))
    conversation.transcript_segments[0].text = ' '.join(['speech'] * words)
    conversation.transcript_segments = conversation.transcript_segments[:1]
    monkeypatch.setattr(boundary.importlib, 'import_module', Mock(side_effect=AssertionError('no merge read')))
    boundary.before_notes(UID, conversation, ProcessingTrigger.CAPTURE_END)


@pytest.mark.parametrize(
    'trigger', [ProcessingTrigger.CAPTURE_END, ProcessingTrigger.SYNC_UPDATE, ProcessingTrigger.SERVER_RECOVERY]
)
def test_each_raw_path_merges_before_full_notes_and_delegates_one_parent_refresh(world, trigger):
    with pytest.raises(ConversationAbsorbed) as raised:
        invoke(world, trigger)
    assert raised.value.canonical_id == 'p'
    assert world.raw('n')['relevance_decision']['verdict'] == 'absorbed'
    assert world.raw('n')['relevance_decision']['neighbor_id'] == 'p'
    assert world.processed == [] and world.vectors == []
    assert world.raw('n')['smart_merge_decision']['processing_stage'] == 'before_notes'
    assert world.raw('p')['smart_merge']['delegated_revision'] == 1
    assert len(world.marks) == 1 and world.marks[0][1] == {'sync_hold': True, 'merge_hold': True}
    baseline = world.get(UID, 'p')[hold.FIELD]
    assert baseline['merge_first'] and baseline['held'] and baseline['full_snapshot']['words'] > 0


@pytest.mark.parametrize('discard', [False, True])
def test_real_structuring_gate_runs_relevance_before_merge_and_no_notes_for_donor(world, monkeypatch, discard):
    pc = process_module
    order = []
    monkeypatch.setattr(pc, 'content_minimum', lambda *a, **kw: None)
    monkeypatch.setattr(pc, 'quiet_minimum', lambda *a, **kw: None)
    monkeypatch.setattr(pc.notification_db, 'get_user_time_zone', lambda _: 'UTC')
    monkeypatch.setattr(pc.users_db, 'get_user_language_preference', lambda _: 'en')
    monkeypatch.setattr(pc, 'conversation_transcripts_for_llm', lambda *a: ('speech', 'speech', {}))
    monkeypatch.setattr(pc, '_proposes_task_candidates', lambda *_: False)
    monkeypatch.setattr(pc, 'jev_tier_applies', lambda _: False)

    def relevance(**kwargs):
        order.append('relevance')
        return RelevanceDecision('discard' if discard else 'keep', 'rule', 'synthetic', kwargs['trigger'])

    monkeypatch.setattr(pc, 'decide_relevance', relevance)
    real_ask = world.ask

    def ask(*a, **kw):
        order.append('merge')
        return real_ask(*a, **kw)

    monkeypatch.setattr(smart_merge, 'ask_jev', ask)
    notes = Mock(side_effect=AssertionError('donor must not buy notes or tasks'))
    monkeypatch.setattr(pc, 'get_conversation_notes', notes)
    conversation = deserialize_conversation(world.get(UID, 'n'))
    if discard:
        _, discarded = pc._get_structured(UID, 'en', conversation)
        assert discarded and order == ['relevance']
        assert not world.raw('n').get('deleted')
    else:
        with pytest.raises(ConversationAbsorbed):
            pc._get_structured(UID, 'en', conversation)
        assert order == ['relevance', 'merge']
    notes.assert_not_called()


@pytest.mark.parametrize(
    'trigger',
    [
        ProcessingTrigger.CLIENT_FINALIZE,
        ProcessingTrigger.USER_REPROCESS,
        ProcessingTrigger.FIRST_OPEN,
        ProcessingTrigger.BACKLOG_CHOICE,
        ProcessingTrigger.MERGE,
    ],
)
def test_explicit_ends_and_user_requests_do_not_wait_or_merge(world, trigger):
    invoke(world, trigger)
    assert not world.jev_calls and not world.marks and not world.raw('n').get('deleted')


@pytest.mark.parametrize('value', ['false', 'off', '0', 'no'])
def test_kill_switch_restores_the_post_notes_path(world, monkeypatch, value):
    monkeypatch.setenv('CONVERSATION_MERGE_BEFORE_PROCESSING', value)
    assert not switch.enabled()
    invoke(world)
    assert not world.jev_calls and not world.marks


def test_default_on(world):
    assert switch.enabled()


@pytest.mark.parametrize(
    'field,value',
    [
        ('structured', {'title': 'Already processed', 'overview': 'full notes'}),
        ('processing_deferred', True),
        ('relevance_decision', {'trigger': 'client_finalize'}),
        ('source', 'desktop'),
        ('record_lane_owner', 'batch_live_v1'),
    ],
)
def test_processed_paid_hold_user_end_and_other_owners_are_never_new_donors(world, field, value):
    world.raw('n')[field] = value
    invoke(world)
    assert not world.raw('n').get('deleted') and not world.jev_calls


@pytest.mark.parametrize('mutation', ['expired', 'epoch', 'generation', 'binding', 'completed', 'delete'])
def test_absorb_transaction_fences_stale_jobs_and_deletion(world, mutation):
    now = datetime.now(timezone.utc)
    job = {
        'uid': UID,
        'conversation_id': 'n',
        'status': 'leased',
        'dispatch_generation': 1,
        'lease_epoch': 2,
        'finalization_revision': 3,
        'lease_expires_at': now + timedelta(minutes=5),
    }
    world.store.rows[('conversation_finalization_jobs', 'job')] = job
    world.raw('n').update(finalization_job_id='job', finalization_revision=3)

    def race():
        if mutation == 'expired':
            job['lease_expires_at'] = now - timedelta(seconds=1)
        elif mutation == 'epoch':
            job['lease_epoch'] = 4
        elif mutation == 'generation':
            job['dispatch_generation'] = 5
        elif mutation == 'completed':
            job['fanout_status'] = 'completed'
        elif mutation == 'binding':
            world.raw('n')['finalization_revision'] = 4
        else:
            world.raw('n')['deleted'] = True

    world.on_ask = race
    invoke(world, finalization_fence=('job', 1, 2))
    assert not world.raw('p').get('smart_merge') and not world.marks


def test_current_live_job_can_absorb_without_fanout_or_paid_notes(world):
    world.raw('n').update(finalization_job_id='job', finalization_revision=3)
    world.store.rows[('conversation_finalization_jobs', 'job')] = {
        'uid': UID,
        'conversation_id': 'n',
        'status': 'leased',
        'dispatch_generation': 1,
        'lease_epoch': 2,
        'finalization_revision': 3,
        'lease_expires_at': datetime.now(timezone.utc) + timedelta(minutes=5),
    }
    with pytest.raises(ConversationAbsorbed):
        invoke(world, finalization_fence=('job', 1, 2))
    assert world.processed == [] and world.raw('n')['deleted']


def test_repeated_parent_absorbs_share_a_window_and_unprocessed_donors_still_refresh(world):
    with pytest.raises(ConversationAbsorbed):
        invoke(world)
    world.add('third', 30, 10, status='processing', structured={})
    with pytest.raises(ConversationAbsorbed):
        boundary.before_notes(UID, deserialize_conversation(world.get(UID, 'third')), ProcessingTrigger.CAPTURE_END)
    parent = world.get(UID, 'p')
    pending = parent[hold.FIELD]['pending_since']
    assert len(world.marks) == 2 and world.processed == []
    assert parent['smart_merge']['revision'] == 2
    assert hold.admission(parent, {'first_pending_at': pending}, now=pending + 1)[0] == 'quiet_wait'
    assert hold.admission(parent, {'first_pending_at': pending}, now=pending + hold.MAX_HOLD_SECONDS)[0] == 'max_hold'
    smart_merge.refresh_survivor(UID, 'p', owner='settled', settled=True)
    snapshot = hold.content_snapshot(parent)
    assert smart_merge.conversations_db.complete_sync_processing_hold(
        UID, 'p', parent.get('sync_content_revision'), snapshot
    )
    assert len(world.processed) == 1
    world.add('fourth', 45, 10, status='processing', structured={})
    with pytest.raises(ConversationAbsorbed):
        boundary.before_notes(UID, deserialize_conversation(world.get(UID, 'fourth')), ProcessingTrigger.CAPTURE_END)
    latest = world.get(UID, 'p')
    assert hold.admission(latest, {'first_pending_at': 0}, now=1e12)[0] == 'max_hold'
    smart_merge.refresh_survivor(UID, 'p', owner='capped', settled=True)
    assert len(world.processed) == 2
    assert world.raw('p')['smart_merge']['refreshed_revision'] == 3


def test_merge_hold_kill_switch_is_independent_and_drains_existing_wake(state, monkeypatch):
    rows, tasks = state
    monkeypatch.setenv('SYNC_PROCESSING_HOLD_ENABLED', 'false')
    monkeypatch.delenv('CONVERSATION_MERGE_BEFORE_PROCESSING', raising=False)
    outbox.mark('u', 'p', 'en', now=100, sync_hold=True, merge_hold=True)
    key = outbox.key('u', 'p')
    process = Mock()
    assert outbox.run(key, tasks[-1]['task_token'], process, now=101) == 'deferred'
    process.assert_not_called()
    monkeypatch.setenv('CONVERSATION_MERGE_BEFORE_PROCESSING', 'false')
    assert outbox.run(key, tasks[-1]['task_token'], process, now=102) == 'processed'
    process.assert_called_once()


def test_sync_callback_transfers_a_deep_redirect_without_processing(world, monkeypatch):
    world.add('middle', 12, 1, deleted=True, sync_merged_into='p')
    world.raw('n').update(deleted=True, sync_merged_into='middle')
    context = {'owner': 'worker', 'sync_hold': True, 'first_pending_at': 1}
    token = PROCESS_CONTEXT.set(context)
    process = Mock(side_effect=AssertionError('redirect donor cannot process'))
    monkeypatch.setattr(callback, 'process_conversation', process)
    try:
        callback.enrich_conversation(UID, 'n', 'en')
    finally:
        PROCESS_CONTEXT.reset(token)
    assert context['redirect_to'] == 'p'
    process.assert_not_called()


@pytest.mark.asyncio
async def test_real_finalizer_closes_absorbed_donor_without_any_fanout(world, monkeypatch):
    from tests.unit.test_conversation_smart_merge import _Jobs, JOB

    monkeypatch.setenv('BATCH_PIPELINE_LIVE_ADMISSION_ENABLED', 'false')
    monkeypatch.setenv('CALLS_RECAP_MODE', 'off')
    monkeypatch.setenv('EPISODES_ENABLED', 'off')
    world.raw('n').update(finalization_job_id=JOB, finalization_revision=1)
    jobs = _Jobs(world, monkeypatch)

    async def direct(_executor, function, *args, **kwargs):
        return function(*args, **kwargs)

    async def no_evidence(*args, **kwargs):
        return 'not_applicable'

    async def no_warm(*args, **kwargs):
        return None

    monkeypatch.setattr(finalizer, 'run_blocking', direct)
    monkeypatch.setattr(finalizer, 'await_meeting_evidence', no_evidence)
    monkeypatch.setattr(finalizer, 'warm_rollout_cohorts', no_warm)

    def structure(uid, language, conversation, **kwargs):
        boundary.before_notes(uid, conversation, kwargs['trigger'], finalization_fence=kwargs['finalization_fence'])
        raise AssertionError('an absorbed donor reached notes')

    monkeypatch.setattr(finalizer, 'process_conversation', structure)
    memory = Mock(side_effect=AssertionError('donor memory fanout'))
    monkeypatch.setattr(finalizer, 'extract_memories', memory)
    await jobs.attempt()
    assert jobs.job['status'] == 'completed' and jobs.job['fanout_status'] == 'fenced'
    assert world.processed == [] and len(world.marks) == 1
    memory.assert_not_called()


def test_raw_survivor_first_processing_preserves_relevance_assessment(world, monkeypatch):
    world.add('p', 0, 10, structured={})
    with pytest.raises(ConversationAbsorbed):
        invoke(world)
    seen = []
    real = world.process

    def process(*args, **kwargs):
        seen.append(kwargs['trigger'])
        return real(*args, **kwargs)

    monkeypatch.setattr(smart_merge, 'process_conversation', process)
    smart_merge.refresh_survivor(UID, 'p', owner='first', settled=True)
    assert seen == [ProcessingTrigger.SYNC_UPDATE]


def test_immaterial_content_settles_ledger_without_notes_or_vector(world):
    with pytest.raises(ConversationAbsorbed):
        invoke(world)
    row = world.get(UID, 'p')
    snapshot = hold.content_snapshot(row)
    row[hold.FIELD].pop('unprocessed_donor', None)  # Model a donor whose full processing already ran.
    row[hold.FIELD]['full_snapshot'] = snapshot
    world.raw('p')[hold.FIELD] = row[hold.FIELD]
    assert hold.admission(row, {'first_pending_at': 0}, now=1e12)[0] == 'unchanged'
    smart_merge.refresh_survivor(UID, 'p', owner='unchanged', settled=True, skip_processing=True)
    assert world.processed == [] and world.vectors == []
    assert world.raw('p')['smart_merge']['refreshed_revision'] == 1


def test_unprocessed_40_word_20_second_donor_refreshes_the_survivor(world):
    donor = world.get(UID, 'n')
    segments = donor['transcript_segments']
    segments[0].update(text=' '.join(['donor'] * 20), start=0, end=10)
    segments[1].update(text=' '.join(['donor'] * 20), start=10, end=20)
    world.store.rows[_path('n')] = conversations_db.encode_conversation_for_write(UID, donor, 'enhanced')

    with pytest.raises(ConversationAbsorbed):
        invoke(world)

    parent = world.get(UID, 'p')
    hold_state = parent[hold.FIELD]
    previous = hold_state['full_snapshot']
    current = hold.content_snapshot(parent)
    assert current['words'] - previous['words'] == 40
    assert current['speech_seconds'] - previous['speech_seconds'] == 20
    assert hold_state['unprocessed_donor']
    assert (
        hold.admission(
            parent,
            {'first_pending_at': hold_state['pending_since']},
            now=hold_state['pending_since'] + hold.QUIET_SECONDS,
        )[0]
        == 'ready'
    )

    smart_merge.refresh_survivor(UID, 'p', owner='small-donor', settled=True)
    assert len(world.processed) == 1


def test_max_hold_budget_denial_settles_merge_refresh_without_rearming(world, monkeypatch):
    world.raw('p').update(
        sync_content_revision=2,
        **{hold.FIELD: {'pending_since': 100, 'last_content_at': 100, 'held': True}},
        smart_merge={'role': 'survivor', 'revision': 1, 'refreshed_revision': 0},
    )
    monkeypatch.setattr(callback, 'repair_fenced', lambda _: False)
    monkeypatch.setattr(callback, 'claim_from_snapshot', lambda *_: True)
    monkeypatch.setattr(callback, 'get_firestore_client', lambda: world.store)
    monkeypatch.setattr(callback, 'schedule_after_finalization', lambda *_: None)
    monkeypatch.setattr(callback.time, 'time', lambda: 3700)

    def denied(_uid, _language, conversation, *, persistence_observer, **_kwargs):
        sync_hold_completion.defer_held_budget_denial()
        persistence_observer(False)
        return conversation

    monkeypatch.setattr(smart_merge, 'process_conversation', denied)
    context = {
        'owner': 'budget-denied',
        'lease_until': 4000,
        'first_pending_at': 100,
        'sync_hold': True,
        'merge_hold': True,
    }
    token = PROCESS_CONTEXT.set(context)
    try:
        assert callback.enrich_conversation(UID, 'p', 'en') is None
    finally:
        PROCESS_CONTEXT.reset(token)

    state = world.raw('p')[hold.FIELD]
    assert state['pending_since'] is None and not state['held']
    assert context['hold_budget_denied_at_max'] and context['hold_skipped']
    assert 'defer_reason' not in context
    assert world.raw('p')['smart_merge']['refreshed_revision'] == 1


@pytest.mark.parametrize('processed', [('p',), ('n',), ('p', 'n')])
def test_late_sync_bridge_keeps_every_already_processed_identity(world, processed):
    from tests.unit.test_conversation_smart_merge_flatten import _assign, _sync_chunk, _seed_index

    for cid, start in [('p', 0), ('n', 15)]:
        world.add(cid, start, 10, sync_content_revision=1, structured={})
        if cid in processed:
            world.raw(cid).update(summary_output_present=True)
    _seed_index(world, 'p', 'n')
    result, created, _ = _assign(world, _sync_chunk('bridge', 9, minutes=8))
    assert not created and result['id'] == ('p' if 'p' in processed else 'n')
    for cid in processed:
        assert not world.raw(cid).get('deleted') and not world.raw(cid).get('sync_merged_into')
    assert any(s['id'] == 'bridge-seg' for s in world.get(UID, result['id'])['transcript_segments'])


def test_sync_retry_keeps_its_processed_anchor_and_explicit_live_target_keeps_both(world):
    from tests.unit.test_conversation_smart_merge_flatten import _assign, _sync_chunk, _seed_index

    world.add('p', 0, 10, sync_content_revision=1, summary_output_present=True)
    world.add('n', 15, 10, sync_content_revision=1, summary_output_present=True)
    _seed_index(world, 'p', 'n')
    result, _, _ = _assign(world, _sync_chunk('n', 9, minutes=8))
    assert result['id'] == 'n'
    assert not world.raw('p').get('deleted')
    result, _, _ = _assign(world, _sync_chunk('bridge', 9, minutes=8), target_id='p')
    assert result['id'] == 'p' and not world.raw('n').get('deleted')


def test_kill_switch_restores_legacy_sync_bridge_absorption(world, monkeypatch):
    from tests.unit.test_conversation_smart_merge_flatten import _assign, _sync_chunk, _seed_index

    monkeypatch.setenv('CONVERSATION_MERGE_BEFORE_PROCESSING', 'false')
    world.add('p', 0, 10, sync_content_revision=1, summary_output_present=True)
    world.add('n', 15, 10, sync_content_revision=1, summary_output_present=True)
    _seed_index(world, 'p', 'n')
    result, _, _ = _assign(world, _sync_chunk('bridge', 9, minutes=8))
    assert result['id'] == 'p' and world.raw('n')['sync_merged_into'] == 'p'


def test_concurrent_transcript_append_without_sync_revision_change_fences_absorb(world):
    def append():
        row = world.get(UID, 'n')
        row['transcript_segments'][0]['text'] += ' new content after relevance'
        world.store.rows[_path('n')] = smart_merge.conversations_db.encode_conversation_for_write(UID, row, 'enhanced')

    world.on_ask = append
    invoke(world)
    assert not world.raw('n').get('deleted') and not world.marks
    assert world.raw('n')['smart_merge_decision']['reason'] == 'flatten_content_changed'


def test_stale_relevance_snapshot_cannot_absorb_newer_speech(world):
    conversation = deserialize_conversation(world.get(UID, 'n'))
    conversation.transcript_segments[0].text += ' stale relevance input'
    boundary.before_notes(UID, conversation, ProcessingTrigger.CAPTURE_END)
    assert not world.raw('n').get('deleted') and not world.jev_calls


@pytest.mark.parametrize(
    'extra',
    [
        {'notes_llm_input_hash': 'receipt', 'summary_output_present': False},
        {'structured': {'title': 'Generated title only'}, 'summary_output_present': False},
        {'structured': {'action_items': [{'description': 'saved task'}]}, 'summary_output_present': False},
    ],
)
def test_note_call_or_derived_task_receipt_protects_a_donor_even_without_rich_notes(world, extra):
    world.raw('n').update(extra)
    invoke(world)
    assert not world.raw('n').get('deleted') and not world.jev_calls


@pytest.mark.parametrize(
    'sync_enabled,merge_enabled,expected', [('true', 'false', True), ('false', 'true', True), ('false', 'false', False)]
)
def test_mixed_pending_hold_obeys_either_enabled_producer(state, monkeypatch, sync_enabled, merge_enabled, expected):
    rows, tasks = state
    outbox.mark('u', 'p', 'en', now=100, sync_hold=True, merge_hold=True)
    outbox.mark('u', 'p', 'en', now=110, sync_hold=True)
    pending = rows[outbox.key('u', 'p')]
    monkeypatch.setenv('SYNC_PROCESSING_HOLD_ENABLED', sync_enabled)
    monkeypatch.setenv('CONVERSATION_MERGE_BEFORE_PROCESSING', merge_enabled)
    assert hold.enabled_for(pending) is expected


def test_new_sync_epoch_does_not_inherit_retired_live_hold_switch(state, monkeypatch):
    rows, tasks = state
    outbox.mark('u', 'p', 'en', now=100, sync_hold=True, merge_hold=True)
    key = outbox.key('u', 'p')
    rows[key]['dormant'] = True
    outbox.mark('u', 'p', 'en', now=1000, sync_hold=True)
    monkeypatch.setenv('CONVERSATION_MERGE_BEFORE_PROCESSING', 'false')
    monkeypatch.setenv('SYNC_PROCESSING_HOLD_ENABLED', 'true')
    assert not rows[key].get('merge_hold') and rows[key]['sync_hold_requested']
    assert hold.enabled_for(rows[key])


def test_new_live_epoch_does_not_inherit_retired_sync_hold_switch(state, monkeypatch):
    rows, tasks = state
    outbox.mark('u', 'p', 'en', now=100, sync_hold=True)
    key = outbox.key('u', 'p')
    rows[key]['dormant'] = True
    outbox.mark('u', 'p', 'en', now=1000, sync_hold=True, merge_hold=True)
    monkeypatch.setenv('CONVERSATION_MERGE_BEFORE_PROCESSING', 'false')
    monkeypatch.setenv('SYNC_PROCESSING_HOLD_ENABLED', 'true')
    assert not rows[key].get('sync_hold_requested') and rows[key]['merge_hold']
    assert not hold.enabled_for(rows[key])


def test_existing_sync_obligation_keeps_its_window_when_live_merge_joins(state, monkeypatch):
    rows, tasks = state
    outbox.mark('u', 'p', 'en', now=100, sync_hold=True)
    key = outbox.key('u', 'p')
    rows[key].pop('sync_hold_requested')  # A stored step-1 obligation predates this field.
    outbox.mark('u', 'p', 'en', now=110, sync_hold=True, merge_hold=True)
    monkeypatch.setenv('CONVERSATION_MERGE_BEFORE_PROCESSING', 'false')
    monkeypatch.setenv('SYNC_PROCESSING_HOLD_ENABLED', 'true')
    assert rows[key]['sync_hold_requested'] and hold.enabled_for(rows[key])


def test_proven_server_minimum_title_still_merges_before_first_notes(world):
    world.raw('n').update(
        structured={'title': 'Raw speech', 'title_provenance': 'server_minimum'}, summary_output_present=False
    )
    with pytest.raises(ConversationAbsorbed):
        invoke(world)
    assert world.processed == [] and len(world.marks) == 1


@pytest.mark.parametrize(
    'merge_enabled,uid,expected', [('true', 'owner', 'server_minimum'), ('false', 'owner', None), ('true', None, None)]
)
def test_minimum_provenance_is_available_outside_first_summary_cohort(monkeypatch, merge_enabled, uid, expected):
    from utils.conversations import deterministic_minimum as minimum

    monkeypatch.setattr(minimum, 'enabled', lambda _: False)
    monkeypatch.setenv('CONVERSATION_MERGE_BEFORE_PROCESSING', merge_enabled)
    conversation = SimpleNamespace(transcript_segments=[SimpleNamespace(text='Raw synthetic speech.')])
    result = minimum.build_deterministic_minimum_structured(conversation, uid=uid)
    assert result.title_provenance == expected
    assert result.overview == '' and result.action_items == []
