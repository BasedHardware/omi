"""The finalizer's episode hook runs after fanout completion and can never fail finalization."""

import asyncio

import pytest

from config import episodes as config
from utils.conversations import finalizer
from utils.conversations.processing_trigger import ProcessingTrigger


@pytest.fixture(autouse=True)
def _enabled(monkeypatch):
    monkeypatch.delenv(config.EPISODES_ENABLED_ENV, raising=False)
    monkeypatch.delenv(config.EPISODES_PERCENT_ENV, raising=False)
    # A user whose app shows episodes (test_episodes_client_gate covers the marker).
    monkeypatch.setattr(finalizer, 'episode_client_seen', lambda uid: True)


def _run_blocking_recorder(calls, rows=None):
    async def fake(_executor, function, *args, **kwargs):
        calls.append((function, args, kwargs))
        if function is finalizer.conversations_db.get_conversation:
            return (rows or {}).get(args[1])
        return function(*args, **kwargs)

    return fake


def test_hook_passes_the_processed_row_and_trigger(monkeypatch):
    calls = []
    seen = []
    monkeypatch.setattr(finalizer, 'run_blocking', _run_blocking_recorder(calls))
    monkeypatch.setattr(finalizer, 'record_episode_finalized', lambda *a, **k: seen.append((a, k)) or 'reconciled')
    asyncio.run(finalizer._episode_after_finalization('u', 'c1', {'id': 'c1'}, ProcessingTrigger.CAPTURE_END))
    assert seen == [(('u', 'c1', {'id': 'c1'}), {'trigger': 'capture_end', 'absorbed_from': None})]


def test_hook_swallows_errors_and_skips_missing_rows(monkeypatch):
    calls = []
    monkeypatch.setattr(finalizer, 'run_blocking', _run_blocking_recorder(calls))

    def boom(*args, **kwargs):
        raise RuntimeError('episode store down')

    monkeypatch.setattr(finalizer, 'record_episode_finalized', boom)
    asyncio.run(finalizer._episode_after_finalization('u', 'c1', {'id': 'c1'}, ProcessingTrigger.CAPTURE_END))
    asyncio.run(finalizer._episode_after_finalization('u', 'c1', None, ProcessingTrigger.CAPTURE_END))
    assert len(calls) == 1


def test_hook_is_time_bounded(monkeypatch):
    budgets = []

    async def expired(awaitable, timeout):
        # The budget expires deterministically: record it, drop the work, raise as wait_for would.
        budgets.append(timeout)
        awaitable.close()
        raise asyncio.TimeoutError

    async def never_awaited(*args, **kwargs):
        raise AssertionError('the stubbed budget expires before the work runs')

    monkeypatch.setattr(finalizer, 'run_blocking', never_awaited)
    monkeypatch.setattr(finalizer.asyncio, 'wait_for', expired)
    asyncio.run(finalizer._episode_after_finalization('u', 'c1', {'id': 'c1'}, ProcessingTrigger.CAPTURE_END))
    assert budgets == [finalizer.EPISODE_FINALIZE_TIMEOUT_SECONDS]


@pytest.mark.parametrize('gate', ['hit', 'miss', 'error'])
def test_sync_schedule_gate_precedes_episode_executor_and_compose(monkeypatch, gate):
    calls, seen = [], []

    def check(*args, **kwargs):
        if gate == 'error':
            raise TimeoutError('synthetic memo timeout')
        return gate == 'hit'

    monkeypatch.setattr(finalizer, 'skip_unchanged_schedule', check)
    monkeypatch.setattr(finalizer, 'run_blocking', _run_blocking_recorder(calls))
    monkeypatch.setattr(finalizer, 'record_episode_finalized', lambda *a, **k: seen.append((a, k)))
    asyncio.run(finalizer._episode_after_finalization('u', 'c1', {'id': 'c1'}, ProcessingTrigger.SYNC_UPDATE))
    assert len(seen) == (0 if gate == 'hit' else 1)
    assert calls[0][0] is check


@pytest.mark.parametrize('switch', ['EPISODE_ATTACH_NOOP_SCHEDULE_ENABLED', 'EPISODE_ATTACH_OPTIMIZATIONS_ENABLED'])
def test_sync_finalizer_kill_switch_runs_hook_even_with_completed_proof(monkeypatch, switch):
    monkeypatch.setenv(switch, 'off')
    calls, seen = [], []
    monkeypatch.setattr(finalizer, 'skip_unchanged_schedule', lambda *a, **kw: True)
    monkeypatch.setattr(finalizer, 'run_blocking', _run_blocking_recorder(calls))
    monkeypatch.setattr(finalizer, 'record_episode_finalized', lambda *a, **kw: seen.append(a))
    asyncio.run(finalizer._episode_after_finalization('u', 'c1', {'id': 'c1'}, ProcessingTrigger.SYNC_UPDATE))
    assert len(seen) == 1


def test_absorb_hook_follows_the_donor_to_its_survivor(monkeypatch):
    calls = []
    seen = []
    donor = {'id': 'n', 'smart_merge': {'role': 'donor', 'survivor_id': 'p'}}
    monkeypatch.setattr(finalizer, 'run_blocking', _run_blocking_recorder(calls, {'n': donor}))
    monkeypatch.setattr(finalizer, 'record_episode_finalized', lambda *a, **k: seen.append((a, k)))
    asyncio.run(finalizer._episode_after_absorb('u', 'n', ProcessingTrigger.CAPTURE_END))
    assert seen == [(('u', 'p', donor), {'trigger': 'capture_end', 'absorbed_from': 'n'})]


def test_absorb_hook_reads_nothing_when_disabled(monkeypatch):
    calls = []
    monkeypatch.setenv(config.EPISODES_ENABLED_ENV, 'off')
    monkeypatch.setattr(finalizer, 'run_blocking', _run_blocking_recorder(calls))
    asyncio.run(finalizer._episode_after_absorb('u', 'n', ProcessingTrigger.CAPTURE_END))
    assert calls == []


@pytest.mark.parametrize('enabled', [False, True])
def test_live_member_notes_wait_for_close_or_recording_detail(monkeypatch, enabled):
    from unittest.mock import Mock
    from utils.episodes import member_notes
    from utils.conversations import demand_processing
    from utils.sync.processing_hold import ProcessingDeferred
    from utils.enrichment import outbox
    from types import SimpleNamespace

    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    monkeypatch.setenv('HOME_LIVE_MEMBER_NOTES_DEFERRED_ENABLED', str(enabled).lower())
    owner = {'id': 'e', 'status': 'live', 'conversation_ids': ['c1']}
    read = Mock(return_value=owner)
    monkeypatch.setattr(member_notes.episodes, 'get_episode_owner_snapshot', read)
    redis = Mock()
    redis.get.return_value = None
    monkeypatch.setattr(demand_processing, 'client', lambda: redis)
    mark = Mock()
    monkeypatch.setattr(outbox, 'mark', mark)
    row = {'id': 'c1'}
    assert member_notes.waits('u', row) is enabled
    assert not member_notes.waits('u', row, ProcessingTrigger.FIRST_OPEN)
    if enabled:
        with pytest.raises(ProcessingDeferred, match='live_episode_notes'):
            member_notes.before_notes('u', SimpleNamespace(id='c1'), ProcessingTrigger.SYNC_UPDATE)
        mark.assert_called_once_with('u', 'c1', 'en', sync_hold=True)
        redis.get.return_value = 'detail-open'
        assert not member_notes.waits('u', row)
        redis.get.return_value = None
        owner['status'] = 'closed'
        assert not member_notes.waits('u', row)
    else:
        read.assert_not_called()


@pytest.mark.parametrize('has_existing_notes', [False, True])
def test_recording_detail_escalates_only_that_recording(monkeypatch, has_existing_notes):
    from unittest.mock import Mock
    from utils.episodes import member_notes
    from utils.conversations import demand_processing
    from database.outbox_firestore import ENRICHMENT_OUTBOX

    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    monkeypatch.setenv('HOME_LIVE_MEMBER_NOTES_DEFERRED_ENABLED', 'true')
    monkeypatch.setattr(
        member_notes.episodes,
        'get_episode_owner_snapshot',
        lambda *args: {'id': 'e', 'status': 'live', 'conversation_ids': ['c1', 'c2']},
    )
    redis = Mock()
    redis.get.return_value = None
    monkeypatch.setattr(demand_processing, 'client', lambda: redis)
    enqueue = Mock()
    monkeypatch.setattr(ENRICHMENT_OUTBOX, 'enqueue', enqueue)
    member_notes.open_recording(
        'u',
        {
            'id': 'c1',
            'status': 'completed',
            'transcript_segments': [{'text': 'text'}],
            'structured': {'overview': 'Earlier notes'} if has_existing_notes else {},
        },
    )
    assert redis.set.call_args.args[0].endswith(':u:c1')
    assert enqueue.call_args.args[2]['conversation_id'] == 'c1'
    assert enqueue.call_args.kwargs['coalesce'] == 'min'


@pytest.mark.asyncio
async def test_live_member_finalization_closes_boundary_before_budget_free_wait(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import Mock
    from utils.episodes import member_notes

    monkeypatch.setenv('HOME_LIVE_MEMBER_NOTES_DEFERRED_ENABLED', 'true')

    async def loaded(*args):
        return None, {'id': 'c1'}, SimpleNamespace()

    monkeypatch.setattr(finalizer, '_load_admitted_conversation', loaded)
    monkeypatch.setattr(member_notes, 'waits', lambda *args: True)
    yielded = Mock(return_value=True)
    monkeypatch.setattr(finalizer.finalization_jobs_db, 'mark_finalization_retryable', yielded)
    calls = []
    close = Mock(return_value='kept_open')
    monkeypatch.setattr(finalizer, 'close_episode_now', close)
    monkeypatch.setattr(finalizer, 'run_blocking', _run_blocking_recorder(calls))
    result = await finalizer.finalize_persisted_conversation(
        'u', 'c1', finalization_job_id='job', dispatch_generation=2, lease_epoch=3
    )
    assert result is finalizer.ConversationFinalizationDisposition.deferred
    assert yielded.call_args.args == ('job', 2, 3, 'live_episode_notes')
    assert yielded.call_args.kwargs == {'count_attempt': False}

    assert [call[0] for call in calls] == [close, member_notes.waits, yielded]


@pytest.mark.parametrize('failure', ['get', 'set', 'enqueue'])
def test_live_detail_dependency_failure_preserves_read_and_retry(monkeypatch, failure):
    from unittest.mock import Mock
    from utils.episodes import member_notes

    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    monkeypatch.setenv('HOME_LIVE_MEMBER_NOTES_DEFERRED_ENABLED', 'true')
    monkeypatch.setattr(
        member_notes.episodes, 'get_episode_owner_snapshot', lambda *a: {'status': 'live', 'conversation_ids': ['c1']}
    )
    redis = Mock()
    redis.get.return_value = None
    enqueue = Mock()
    monkeypatch.setattr(member_notes.demand_processing, 'client', lambda: redis)
    monkeypatch.setattr(member_notes.ENRICHMENT_OUTBOX, 'enqueue', enqueue)
    {'get': redis.get, 'set': redis.set, 'enqueue': enqueue}[failure].side_effect = TimeoutError('unavailable')
    row = {'id': 'c1', 'status': 'completed', 'transcript_segments': [{'text': 'text'}]}
    member_notes.open_recording('u', row)  # Optional escalation never fails detail.
    if failure == 'get':
        assert not member_notes.waits('u', row)
        enqueue.assert_not_called()
    elif failure == 'enqueue':
        redis.set.assert_not_called()  # Next read can retry without a stale lease.
    else:
        enqueue.assert_called_once()


@pytest.mark.asyncio
async def test_boundary_close_releases_live_member_without_another_client_read(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import Mock
    from utils.episodes import member_notes
    from models.conversation import ConversationStatus

    monkeypatch.setenv('HOME_LIVE_MEMBER_NOTES_DEFERRED_ENABLED', 'true')
    owner = {'status': 'live', 'conversation_ids': ['c1']}
    monkeypatch.setattr(member_notes.episodes, 'get_episode_owner_snapshot', lambda *a: owner)

    async def loaded(*args):
        return None, {'id': 'c1'}, SimpleNamespace(status=ConversationStatus.processing)

    monkeypatch.setattr(finalizer, '_load_admitted_conversation', loaded)
    close = Mock(side_effect=lambda *a: owner.update(status='closed'))
    monkeypatch.setattr(finalizer, 'close_episode_now', close)
    monkeypatch.setattr(finalizer, 'run_blocking', _run_blocking_recorder([]))

    async def paid_seam(*a, **k):
        raise RuntimeError('reached-after-boundary-close')

    monkeypatch.setattr(finalizer, 'await_meeting_evidence', paid_seam)
    retry = Mock()
    monkeypatch.setattr(finalizer.finalization_jobs_db, 'mark_finalization_retryable', retry)
    with pytest.raises(RuntimeError, match='reached-after-boundary-close'):
        await finalizer.finalize_persisted_conversation(
            'u', 'c1', finalization_job_id='job', dispatch_generation=2, lease_epoch=3
        )
    close.assert_called_once()
    retry.assert_not_called()
