"""Experiment ``fast_end_feedback``: a v3 conversation is shown as done once its summary is stored.

Off (the default) the row stays ``writing`` until the whole processing pass ends, which the ordinary
v3 suites assert. On, the builder flips only the visible state when process_conversation reports its
canonical write, before folder assignment, memory extraction and the other derived effects; the
processing obligation still settles at the end of the pass.
"""

import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock, call

import pytest
from fastapi import HTTPException

from config import reliability_experiments
from database import conversations_v3 as store, conversations_v3_leases as leases
from database import conversations_v3_processing as writers
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.conversations import lifecycle, process_conversation as process
from utils.conversations.v3 import manual_cuts, service, summary_wake

EXPERIMENT = 'fast_end_feedback'
AT = datetime(2026, 11, 16, 12, tzinfo=timezone.utc)
CID = ('users', 'synthetic', 'conversations', 'c')


def row(**extra):
    return {
        'id': 'w',
        'v3_derived': True,
        'kind': 'conversation',
        'created_at': AT,
        'started_at': AT,
        'finished_at': AT,
        'structured': {},
        'transcript_segments': [{'text': 'word ' * 400, 'start': 0, 'end': 10, 'is_user': False}],
        **extra,
    }


def stored(**extra):
    """A row as it stands right after the summary write of a processing pass."""
    return {
        'id': 'c',
        'status': 'completed',
        'tile_state': 'writing',
        'v3_process_pending': True,
        'summary_output_present': True,
        **extra,
    }


@pytest.fixture
def strict(monkeypatch):
    client = StrictFirestore()
    monkeypatch.setattr(leases, 'get_firestore_client', lambda: client)

    def transactional(body):
        def run(tx, *args, **kwargs):
            with client.lock:
                return body(tx, *args, **kwargs)

        return run

    monkeypatch.setattr(store.firestore, 'transactional', transactional)
    return client


@pytest.fixture
def passes(monkeypatch):
    """Run service._process with the notes call stubbed; record the order of what the pass does."""
    order = []
    monkeypatch.setattr(writers, 'begin_processing', lambda *a, **kw: True)
    monkeypatch.setattr(writers, 'settle_processing', lambda *a, **kw: order.append('settled'))
    monkeypatch.setattr(lifecycle, 'complete', lambda *a: pytest.fail('skipped notes'))

    def notes(uid, language, conversation, **kw):
        order.append('summary stored')
        kw['persistence_observer'](True)
        order.append('derived effects')
        return SimpleNamespace(status='completed')

    monkeypatch.setattr(process, 'process_conversation', notes)
    monkeypatch.setattr(summary_wake, 'publish', lambda *a: None)
    return order


def test_registered():
    assert EXPERIMENT in reliability_experiments.EXPERIMENTS


def test_off_pass_never_shows_early(monkeypatch, passes):
    monkeypatch.delenv(reliability_experiments.ENV, raising=False)
    monkeypatch.setattr(writers, 'show_summary_stored', lambda *a, **kw: pytest.fail('baseline wrote early'))
    service._process('u', row(), 'token')
    assert passes == ['summary stored', 'derived effects', 'settled']


def test_on_pass_shows_done_between_the_summary_and_the_derived_effects(monkeypatch, passes):
    monkeypatch.setenv(reliability_experiments.ENV, EXPERIMENT)
    monkeypatch.setattr(writers, 'show_summary_stored', lambda uid, cid, token: passes.append(f'shown {cid}') or True)
    service._process('u', row(), 'token')
    assert passes == ['summary stored', 'shown w', 'derived effects', 'settled']


def test_on_a_fenced_summary_write_is_not_shown(monkeypatch, passes):
    monkeypatch.setenv(reliability_experiments.ENV, EXPERIMENT)
    monkeypatch.setattr(writers, 'show_summary_stored', lambda *a, **kw: pytest.fail('shown without a stored summary'))

    def fenced(uid, language, conversation, **kw):
        kw['persistence_observer'](False)
        return SimpleNamespace(status='completed')

    monkeypatch.setattr(process, 'process_conversation', fenced)
    with pytest.raises(RuntimeError, match='v3_processing_not_completed'):
        service._process('u', row(), 'token')


def test_on_a_failed_early_write_does_not_fail_the_pass(monkeypatch, passes):
    monkeypatch.setenv(reliability_experiments.ENV, EXPERIMENT)

    def broken(*a, **kw):
        raise RuntimeError('store down')

    monkeypatch.setattr(writers, 'show_summary_stored', broken)
    service._process('u', row(), 'token')
    assert passes == ['summary stored', 'derived effects', 'settled']


def test_show_summary_stored_moves_only_the_visible_state(strict):
    strict.rows[CID] = stored()
    token = leases.acquire('synthetic', 'summary-c', firestore_client=strict)
    before = deepcopy(strict.rows[CID])
    assert writers.show_summary_stored('synthetic', 'c', token, firestore_client=strict) is True
    assert strict.rows[CID] == {**before, 'tile_state': 'done'}
    assert strict.rows[CID]['v3_process_pending'] is True, 'the obligation still settles at the end of the pass'
    # The end-of-pass settle then closes it as before.
    writers.settle_processing('synthetic', 'c', token, None, AT, notes=True, firestore_client=strict)
    assert strict.rows[CID]['v3_process_pending'] is False
    assert strict.rows[CID]['tile_state'] == 'done'


@pytest.mark.parametrize(
    'change',
    [
        {'status': 'processing'},
        {'tile_state': 'live'},
        {'tile_state': 'failed'},
        {'v3_process_pending': False},
        {'summary_output_present': False},
        {'deleted': True},
    ],
)
def test_show_summary_stored_leaves_other_rows_alone(strict, change):
    strict.rows[CID] = stored(**change)
    token = leases.acquire('synthetic', 'summary-c', firestore_client=strict)
    before = deepcopy(strict.rows[CID])
    assert writers.show_summary_stored('synthetic', 'c', token, firestore_client=strict) is False
    assert strict.rows[CID] == before


def test_show_summary_stored_needs_this_pass_lease(strict):
    strict.rows[CID] = stored()
    leases.acquire('synthetic', 'summary-c', firestore_client=strict)
    assert writers.show_summary_stored('synthetic', 'c', 'another-token', firestore_client=strict) is False
    assert strict.rows[CID]['tile_state'] == 'writing'


def test_end_schedules_two_early_retry_wakes_only_with_both_experiments(monkeypatch):
    record, enqueue = Mock(return_value='cut-1'), Mock()
    monkeypatch.setattr(manual_cuts.cuts_db, 'record', record)
    monkeypatch.setattr(manual_cuts.triggers, 'enqueue', enqueue)
    monkeypatch.setattr(manual_cuts, 'conversations_v3_enabled', lambda uid: True)

    # End's own experiment alone: the single immediate wake, as before.
    monkeypatch.setenv(reliability_experiments.ENV, 'end_open_conversation')
    assert manual_cuts.request_end('u', now=AT) is True
    assert enqueue.call_args_list == [call('u', manual_end_id='cut-1')]

    # This experiment alone records nothing: End's cut belongs to end_open_conversation.
    enqueue.reset_mock()
    monkeypatch.setenv(reliability_experiments.ENV, EXPERIMENT)
    assert manual_cuts.request_end('u', now=AT) is False
    enqueue.assert_not_called()

    # Both: the immediate wake plus one 15 s and one 35 s after End, each under its own task name.
    monkeypatch.setenv(reliability_experiments.ENV, f'end_open_conversation,{EXPERIMENT}')
    assert manual_cuts.request_end('u', now=AT) is True
    assert enqueue.call_args_list == [
        call('u', manual_end_id='cut-1'),
        call('u', at=AT + timedelta(seconds=15), manual_end_id='cut-1:retry1'),
        call('u', at=AT + timedelta(seconds=35), manual_end_id='cut-1:retry2'),
    ]


# --- One waiting request for the summary: the wake and GET /v1/conversations/{id}/summary/wait ---


def test_pass_wakes_a_waiter_when_the_summary_shows_and_again_when_the_pass_ends(monkeypatch, passes):
    monkeypatch.setenv(reliability_experiments.ENV, EXPERIMENT)
    monkeypatch.setattr(writers, 'show_summary_stored', lambda uid, cid, token: passes.append('shown') or True)
    monkeypatch.setattr(summary_wake, 'publish', lambda uid, cid: passes.append(f'wake {uid} {cid}'))
    service._process('u', row(), 'token')
    assert passes == ['summary stored', 'shown', 'wake u w', 'derived effects', 'settled', 'wake u w']


def test_a_summary_that_could_not_be_shown_early_wakes_only_at_the_end(monkeypatch, passes):
    monkeypatch.setenv(reliability_experiments.ENV, EXPERIMENT)
    monkeypatch.setattr(writers, 'show_summary_stored', lambda *a: False)
    monkeypatch.setattr(summary_wake, 'publish', lambda uid, cid: passes.append('wake'))
    service._process('u', row(), 'token')
    assert passes == ['summary stored', 'derived effects', 'settled', 'wake']


def test_publish_is_silent_while_off_and_never_raises(monkeypatch):
    from database import redis_db

    published = Mock()
    monkeypatch.setenv('OMI_ENV_STAGE', 'local')
    monkeypatch.setattr(redis_db, 'r', SimpleNamespace(publish=published))
    monkeypatch.delenv(reliability_experiments.ENV, raising=False)
    summary_wake.publish('u', 'c')
    published.assert_not_called()

    monkeypatch.setenv(reliability_experiments.ENV, EXPERIMENT)
    summary_wake.publish('u', 'c')
    published.assert_called_once_with(summary_wake.channel('u'), 'c')

    published.side_effect = ConnectionError('redis down')
    summary_wake.publish('u', 'c')  # the row is already written; a lost wake costs one re-read interval


@pytest.mark.parametrize(
    'stored, expected',
    [
        ({'v3_derived': True, 'tile_state': 'done'}, True),
        ({'v3_derived': True, 'tile_state': 'failed'}, True),
        ({'v3_derived': True, 'tile_state': 'writing', 'status': 'completed'}, False),
        ({'v3_derived': True, 'tile_state': 'live', 'status': 'in_progress'}, False),
        ({'v3_derived': True, 'tile_state': 'transcribing'}, False),
        ({'status': 'completed'}, True),
        ({'status': 'processing'}, False),
    ],
)
def test_settled_follows_what_the_app_shows(stored, expected):
    assert summary_wake.settled(stored) is expected


class _Subscription:
    """A pub/sub stand-in: records the order of subscribe and reads, hands out queued messages."""

    def __init__(self, log):
        self.log, self.messages, self.listening = log, asyncio.Queue(), asyncio.Event()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        self.log.append('closed')

    async def subscribe(self, channel):
        self.log.append(f'subscribe {channel}')
        self.messages.put_nowait({'type': 'subscribe'})

    async def get_message(self, ignore_subscribe_messages=False, timeout=None):
        if ignore_subscribe_messages:
            self.listening.set()
        try:
            return await asyncio.wait_for(self.messages.get(), timeout)
        except asyncio.TimeoutError:
            return None


@pytest.fixture
def waiter(monkeypatch):
    from database import redis_db

    monkeypatch.setenv('OMI_ENV_STAGE', 'local')
    log = []
    subscription = _Subscription(log)

    async def get_redis():
        return SimpleNamespace(pubsub=lambda: subscription)

    monkeypatch.setattr(redis_db, 'get_async_redis_client', get_redis)
    state = {'row': stored(v3_derived=True)}

    async def read():
        log.append('read')
        return dict(state['row'])

    async def connected():
        return False

    return SimpleNamespace(log=log, sub=subscription, state=state, read=read, connected=connected)


@pytest.mark.asyncio
async def test_wait_answers_at_once_for_a_settled_row(waiter):
    waiter.state['row'] = stored(v3_derived=True, tile_state='done')
    found, state = await summary_wake.wait('u', 'c', waiter.read, waiter.connected)
    assert state == 'ready' and found['tile_state'] == 'done'
    # Subscribed before the first read, so a wake between the two cannot be lost.
    assert waiter.log == [f"subscribe {summary_wake.channel('u')}", 'read', 'closed']


@pytest.mark.asyncio
async def test_wait_returns_on_the_wake_for_its_conversation_only(waiter):
    task = asyncio.create_task(summary_wake.wait('u', 'c', waiter.read, waiter.connected, recheck=60))
    await asyncio.wait_for(waiter.sub.listening.wait(), 2)
    waiter.sub.messages.put_nowait({'type': 'message', 'data': 'another-conversation'})
    await asyncio.sleep(0.05)
    assert not task.done() and waiter.log.count('read') == 1

    waiter.state['row'] = stored(v3_derived=True, tile_state='done')
    waiter.sub.messages.put_nowait({'type': 'message', 'data': 'c'})
    found, state = await asyncio.wait_for(task, 2)
    assert state == 'ready' and found['tile_state'] == 'done'
    assert waiter.log.count('read') == 2


@pytest.mark.asyncio
async def test_wait_rereads_the_row_without_a_wake(waiter):
    task = asyncio.create_task(summary_wake.wait('u', 'c', waiter.read, waiter.connected, recheck=0))
    await asyncio.wait_for(waiter.sub.listening.wait(), 2)
    waiter.state['row'] = stored(v3_derived=True, tile_state='failed')
    found, state = await asyncio.wait_for(task, 3)
    assert state == 'ready' and found['tile_state'] == 'failed'


@pytest.mark.asyncio
async def test_wait_runs_out_and_returns_the_row_as_it_stands(waiter):
    found, state = await summary_wake.wait('u', 'c', waiter.read, waiter.connected, seconds=0.05)
    # The summary wait ran out on a row that is committed but not summarised yet.
    assert state == 'outline' and found['tile_state'] == 'writing'


@pytest.mark.asyncio
async def test_wait_stops_when_the_client_went_away(waiter):
    async def gone():
        return True

    found, state = await summary_wake.wait('u', 'c', waiter.read, gone, seconds=30)
    assert state == 'outline' and waiter.log.count('read') == 1


@pytest.mark.asyncio
async def test_wait_works_on_rereads_when_redis_is_unavailable(monkeypatch, waiter):
    from database import redis_db

    async def no_redis():
        raise ConnectionError('redis down')

    monkeypatch.setattr(redis_db, 'get_async_redis_client', no_redis)
    waiter.state['row'] = stored(v3_derived=True, tile_state='done')
    found, state = await summary_wake.wait('u', 'c', waiter.read, waiter.connected)
    assert state == 'ready'


@pytest.mark.asyncio
async def test_wait_lets_a_missing_conversation_refuse_as_the_detail_read_does(waiter):
    async def missing():
        raise HTTPException(status_code=404, detail='Conversation not found')

    with pytest.raises(HTTPException) as refused:
        await summary_wake.wait('u', 'c', missing, waiter.connected)
    assert refused.value.status_code == 404
    assert waiter.log[-1] == 'closed'


@pytest.mark.asyncio
async def test_wait_path_is_a_plain_404_for_an_account_the_experiment_is_off_for(monkeypatch):
    from fastapi import Response
    from routers import conversations

    monkeypatch.delenv(reliability_experiments.ENV, raising=False)
    monkeypatch.setattr(reliability_experiments, '_resolver', lambda name, uid: name == EXPERIMENT and uid == 'in')
    monkeypatch.setattr(
        conversations.v3_summary_wake, 'wait', lambda *a, **kw: pytest.fail('no wait for an account that is off')
    )
    with pytest.raises(HTTPException) as refused:
        await conversations.wait_for_conversation_summary('c', SimpleNamespace(), Response(), 'summary', 'out')
    assert refused.value.status_code == 404 and refused.value.detail == 'Not Found'
    assert summary_wake.enabled('in') is True and summary_wake.enabled('out') is False
    path = '/v1/conversations/{conversation_id}/summary/wait'
    route = next(r for r in conversations.router.routes if getattr(r, 'path', '') == path)
    assert route.include_in_schema is False


@pytest.mark.asyncio
@pytest.mark.parametrize('until, state', [('summary', 'ready'), ('outline', 'outline'), ('summary', 'timeout')])
async def test_wait_route_answers_with_the_detail_read_and_says_where_the_row_stands(monkeypatch, until, state):
    from fastapi import Response
    from routers import conversations

    monkeypatch.setenv(reliability_experiments.ENV, EXPERIMENT)
    asked = []

    async def wait(uid, conversation_id, read, disconnected, *, until):
        asked.append((uid, conversation_id, until))
        return {}, state

    def detail(conversation_id, source, include_discarded, uid, *rest):
        return {'id': conversation_id, 'uid': uid, 'read': 'detail'}

    async def run(_executor, fn, *args):
        return fn(*args)

    monkeypatch.setattr(conversations.v3_summary_wake, 'wait', wait)
    monkeypatch.setattr(conversations, 'get_conversation_by_id', detail)
    monkeypatch.setattr(conversations, 'run_blocking', run)
    response = Response()
    body = await conversations.wait_for_conversation_summary('c', SimpleNamespace(), response, until, 'owner')
    assert asked == [('owner', 'c', until)]
    assert body == {'id': 'c', 'uid': 'owner', 'read': 'detail'}
    assert response.headers['X-Omi-Summary-Wait'] == state


# --- The first of the two updates: the ended conversation committed with its outline ---


@pytest.mark.parametrize(
    'stored, outlined, state',
    [
        ({'v3_derived': True, 'tile_state': 'live'}, False, 'timeout'),
        ({'v3_derived': True, 'tile_state': 'transcribing'}, True, 'outline'),
        ({'v3_derived': True, 'tile_state': 'writing'}, True, 'outline'),
        ({'v3_derived': True, 'tile_state': 'done'}, True, 'ready'),
        ({'v3_derived': True, 'tile_state': 'failed'}, True, 'ready'),
        ({'status': 'processing'}, False, 'timeout'),
        ({'status': 'completed'}, True, 'ready'),
    ],
)
def test_advanced_and_state_follow_the_builder_commit(stored, outlined, state):
    assert summary_wake.advanced(stored) is outlined
    assert summary_wake.state(stored) == state


def test_commit_wakes_only_the_conversations_that_just_left_live(monkeypatch):
    woken = []
    monkeypatch.setattr(summary_wake, 'publish', lambda uid, cid: woken.append((uid, cid)))
    existing = {
        'ended': {'tile_state': 'live'},
        'waiting-for-audio': {'tile_state': 'live'},
        'audio-landed': {'tile_state': 'transcribing'},
        'still-writing': {'tile_state': 'writing'},
        'old': {'tile_state': 'done'},
    }
    rows = [
        {'id': 'ended', 'tile_state': 'writing'},
        {'id': 'waiting-for-audio', 'tile_state': 'transcribing'},
        {'id': 'audio-landed', 'tile_state': 'writing'},
        {'id': 'still-writing', 'tile_state': 'writing'},
        {'id': 'old', 'tile_state': 'done'},
        {'id': 'open', 'tile_state': 'live'},
        {'id': 'new-and-ended', 'tile_state': 'writing'},
    ]
    monkeypatch.delenv(reliability_experiments.ENV, raising=False)
    summary_wake.publish_committed('u', rows, existing)
    assert woken == [], 'baseline publishes nothing'

    monkeypatch.setenv(reliability_experiments.ENV, EXPERIMENT)
    summary_wake.publish_committed('u', rows, existing)
    assert woken == [('u', 'ended'), ('u', 'waiting-for-audio'), ('u', 'audio-landed'), ('u', 'new-and-ended')]


@pytest.mark.asyncio
async def test_outline_wait_returns_when_the_row_leaves_live_and_the_summary_wait_keeps_waiting(waiter):
    waiter.state['row'] = stored(v3_derived=True, tile_state='live', status='in_progress')
    early = asyncio.create_task(summary_wake.wait('u', 'c', waiter.read, waiter.connected, until='outline', recheck=60))
    await asyncio.wait_for(waiter.sub.listening.wait(), 2)
    assert not early.done()

    waiter.state['row'] = stored(v3_derived=True, tile_state='writing')
    waiter.sub.messages.put_nowait({'type': 'message', 'data': 'c'})
    found, state = await asyncio.wait_for(early, 2)
    assert state == 'outline' and found['tile_state'] == 'writing'

    # The same row does not satisfy a wait for the summary.
    found, state = await summary_wake.wait('u', 'c', waiter.read, waiter.connected, until='summary', seconds=0.05)
    assert state == 'outline'


@pytest.mark.asyncio
async def test_outline_wait_that_runs_out_on_a_live_row_says_timeout(waiter):
    waiter.state['row'] = stored(v3_derived=True, tile_state='live', status='in_progress')
    found, state = await summary_wake.wait('u', 'c', waiter.read, waiter.connected, until='outline', seconds=0.05)
    assert state == 'timeout' and found['tile_state'] == 'live'


def test_builder_publishes_the_commit_wake_from_the_live_pass_only():
    import inspect

    source = inspect.getsource(service.reconcile)
    call = 'summary_wake.publish_committed(uid, rows, existing)'
    assert source.count(call) == 1
    # Inside the branch that excludes backfill (derive) and on-open passes, after the commit.
    assert source.index('moved = await run_blocking(') < source.index(call)
    assert 'if not derive and not on_open:' in source[: source.index(call)].splitlines()[-4]
