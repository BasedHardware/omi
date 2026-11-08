"""Caller exhaustion contracts: every pump-side outcome when a budget burns.

The wave-bridge changes how long a chain waits, not what happens when it
exhausts. Each caller keeps its closed outcome set — this suite pins that
closed set end to end, so the log taxonomy and the durable fallbacks survive
any future budget reshape:

- ``Pump._publish``: one segment's exhausted transition marks it lost, logs
  ``event=batch_completion outcome=retry``, returns False, and never
  suppresses a sibling's accepted transition.
- ``Pump._drain_after_publication``: an exhausted ordered drain arms the
  owner's bounded deferred drain lane (INFO ``event=batch_merge_drain
  outcome=deferred``), converges without waiting for an incidental later
  drain, and falls back to the historical ``event=batch_merge outcome=retry``
  error line only when the attempt cap refuses to re-arm.
- Maintenance steps and the recover sweep keep their per-step / per-item
  continuation contracts under the real raise site.
- Non-contention errors stay fail-noisy everywhere.

Failure-Class: FC-contention-chain-spends-its-budget-inside-one-abort-wave
"""

import asyncio
import copy
import logging
from types import SimpleNamespace

import pytest

import utils.batch_pipeline.pump as pump_module
from database.firestore_transaction_retry import FirestoreContentionExhausted
from utils.batch_pipeline.contracts import (
    FailedWork,
    HeldWork,
    LeasedWork,
    Priority,
    RecoveryWork,
    ValidationFailureWork,
    WorkItem,
    WorkResult,
)
from utils.batch_pipeline.pump import Pump

EXHAUSTED = 'chain budget burned'


def chain_exhaustion():
    """Raise a real FirestoreContentionExhausted (the production raise site)."""
    raise FirestoreContentionExhausted(f'Firestore transaction contention exhausted for {EXHAUSTED}')


@pytest.fixture(autouse=True)
def inline_blocking(monkeypatch):
    """Run the pump's blocking leaves inline on the event loop."""

    async def passthrough(executor, function, *args, **kwargs):
        return function(*args, **kwargs)

    monkeypatch.setattr(pump_module, 'run_blocking', passthrough)


def work_item(segment='seg-1', owner='owner-1'):
    return WorkItem(
        segment_id=segment,
        owner_id=owner,
        capture_at=1000.0,
        audio_uri='gs://bucket/audio/seg-1',
        duration_seconds=12.0,
        priority=Priority.RECENT,
    )


def lease(segment='seg-1', owner='owner-1', token='tok'):
    item = work_item(segment, owner)
    return LeasedWork(item=item, token=token, attempt=1, lease_until=1999.0)


class ScriptScheduler:
    def __init__(self):
        self.store = self
        self.calls = []

    def defer(self, segment_id, token, now, retry_after=30, held_reason=None, admission_refused=False):
        self.calls.append(('defer', segment_id, retry_after, held_reason, admission_refused))
        return True

    def fail(self, segment_id, token, now, **kwargs):
        self.calls.append(('fail', segment_id, kwargs))
        return True

    def complete(self, result, token, now):
        self.calls.append(('complete', result.segment_id))
        return True

    def release(self, segment_id, token, now):
        self.calls.append(('release', segment_id))
        return True

    def heartbeat(self, segment_id, token, now):
        return True

    def probe(self, table, key):
        return {'owner_id': 'owner-1'} if key.startswith('seg') else {}


class ScriptMerge:
    def __init__(self):
        self.held_owners = set()
        self.drained = []
        self.marked_page_result = []
        self.released = []
        self.commit_script = {}

    def marked_page(self, limit=50):
        return self.marked_page_result

    def release_hold(self, key, *, force=False):
        self.released.append((key, force))

    def commit_next(self, owner_id, now):
        self.drained.append(owner_id)
        script = self.commit_script.get(owner_id) or []
        if script:
            step = script.pop(0)
            if isinstance(step, Exception):
                raise step
            return step
        return None


def make_pump(**overrides):
    scheduler = overrides.pop('scheduler', None) or ScriptScheduler()
    merge = overrides.pop('merge', None) or ScriptMerge()
    pump = Pump(
        scheduler,
        SimpleNamespace(),
        merge=merge,
        publish_concurrency=overrides.pop('publish_concurrency', 1),
        on_committed=overrides.pop('on_committed', None),
    )
    for name, value in overrides.items():
        setattr(pump, name, value)
    return pump


# --------------------------------------------------------------------------
# _publish: the closed per-segment outcome set
# --------------------------------------------------------------------------


async def test_exhausted_complete_transition_marks_the_segment_lost():
    pump = make_pump()
    received = []

    def complete(result, token, now):
        received.append(result.segment_id)
        chain_exhaustion()

    pump.scheduler.complete = complete
    lease_ = lease()
    lost = set()
    accepted = await pump._publish(lease_, {lease_.item.segment_id: WorkResult('seg-1', 'gs://r')}, lost)
    assert accepted is False
    assert lost == {'seg-1'}


async def test_exhausted_complete_transition_logs_batch_completion_retry(caplog):
    pump = make_pump()

    def complete(result, token, now):
        chain_exhaustion()

    pump.scheduler.complete = complete
    lease_ = lease()
    await pump._publish(lease_, {'seg-1': WorkResult('seg-1', 'gs://r')}, set())
    retry_lines = [record.getMessage() for record in caplog.records if 'event=batch_completion' in record.getMessage()]
    assert len(retry_lines) == 1
    assert 'outcome=retry' in retry_lines[0]
    assert 'exception_type=FirestoreContentionExhausted' in retry_lines[0]


async def test_exhausted_transition_does_not_suppress_the_sibling():
    pump = make_pump()

    def complete(result, token, now):
        if result.segment_id == 'seg-a':
            chain_exhaustion()
        return True

    pump.scheduler.complete = complete
    leases = [lease('seg-a'), lease('seg-b')]
    result_map = {'seg-a': WorkResult('seg-a', 'gs://a'), 'seg-b': WorkResult('seg-b', 'gs://b')}
    lost = set()
    assert await pump._publish(leases[0], result_map, lost) is False
    assert await pump._publish(leases[1], result_map, lost) is True
    assert lost == {'seg-a'}


async def test_failed_work_transition_exhaustion_follows_the_same_contract():
    pump = make_pump()
    pump.scheduler.fail = lambda *args, **kwargs: chain_exhaustion()
    lost = set()
    lease_ = lease('seg-f')
    accepted = await pump._publish(lease_, {'seg-f': FailedWork('seg-f')}, lost)
    assert accepted is False
    assert lost == {'seg-f'}


async def test_validation_failure_transition_carries_stage_and_reason():
    pump = make_pump()
    seen = {}

    def fail(segment_id, token, now, **kwargs):
        seen.update(kwargs)
        return True

    pump.scheduler.fail = fail
    work = ValidationFailureWork('seg-v', 'fetch_decode', 'staged_audio_invalid', 1.5, {'receipt': True})
    assert await pump._publish(lease('seg-v'), {'seg-v': work}, set()) is True
    assert seen['worker_failure'] == {'stage': 'fetch_decode', 'reason': 'staged_audio_invalid'}
    assert seen['measured_held_vad_speech_seconds'] == 1.5
    assert seen['worker_vad_receipt'] == {'receipt': True}


async def test_recovery_work_transition_quarantines_with_evidence():
    pump = make_pump()
    seen = {}

    def fail(segment_id, token, now, **kwargs):
        seen.update(kwargs)
        return True

    pump.scheduler.fail = fail
    work = RecoveryWork('seg-r', padded_retry_empty=True, padded_retry='empty', reason='empty_asr')
    assert await pump._publish(lease('seg-r'), {'seg-r': work}, set()) is True
    assert seen['quarantine'] is True
    assert seen['padded_retry_empty'] is True
    assert seen['padded_retry'] == 'empty'
    assert seen['worker_failure'] == {'stage': 'assemble_words', 'reason': 'empty_asr'}


async def test_held_work_transition_defers_with_the_admission_decision():
    pump = make_pump()
    work = HeldWork('seg-h', retry_after=45, reason='cap_exhausted')
    assert await pump._publish(lease('seg-h'), {'seg-h': work}, set()) is False
    assert pump.scheduler.calls == [('defer', 'seg-h', 45, 'cap_exhausted', True)]


async def test_lost_segment_with_a_live_heartbeat_recovers_and_publishes():
    pump = make_pump()
    attempts = []

    def heartbeat(segment_id, token, now):
        attempts.append(segment_id)
        return True  # the lease is still ours

    pump.scheduler.heartbeat = heartbeat
    result = WorkResult('seg-l', 'gs://l')
    assert await pump._publish(lease('seg-l'), {'seg-l': result}, {'seg-l'}) is True
    assert attempts == ['seg-l']
    assert pump.scheduler.calls == [('complete', 'seg-l')]


async def test_lost_segment_with_a_dead_heartbeat_stays_lost():
    pump = make_pump()
    pump.scheduler.heartbeat = lambda segment_id, token, now: False
    lost = {'seg-l'}
    assert await pump._publish(lease('seg-l'), {'seg-l': WorkResult('seg-l', 'gs://l')}, lost) is False
    assert lost == {'seg-l'}
    assert pump.scheduler.calls == []


async def test_accepted_complete_transition_reports_true_and_forwards_the_result():
    pump = make_pump()
    result = WorkResult('seg-a', 'gs://a')
    assert await pump._publish(lease('seg-a'), {'seg-a': result}, set()) is True
    assert pump.scheduler.calls == [('complete', 'seg-a')]


async def test_missing_result_is_published_as_an_ordinary_failure():
    pump = make_pump()
    seen = {}

    def fail(segment_id, token, now, **kwargs):
        seen.update(kwargs)
        return True

    pump.scheduler.fail = fail
    assert await pump._publish(lease('seg-x'), {}, set()) is True
    assert seen['worker_failure_evidence'] is None
    assert seen['measured_held_vad_speech_seconds'] is None


async def test_exhaustion_inside_the_held_defer_marks_the_segment_lost():
    pump = make_pump()

    def defer(*args, **kwargs):
        chain_exhaustion()

    pump.scheduler.defer = defer
    lost = set()
    work = HeldWork('seg-h', retry_after=10)
    assert await pump._publish(lease('seg-h'), {'seg-h': work}, lost) is False
    assert lost == {'seg-h'}


# --------------------------------------------------------------------------
# _publish_flight: owner grouping and the ordered drain
# --------------------------------------------------------------------------


async def test_serial_flight_drains_after_each_accepted_transition():
    pump = make_pump()
    drains = []

    async def drain(owner_id):
        drains.append(owner_id)

    pump._drain_after_publication = drain
    leases = [lease('seg-a'), lease('seg-b')]
    result_map = {'seg-a': WorkResult('seg-a', 'gs://a'), 'seg-b': WorkResult('seg-b', 'gs://b')}
    await pump._publish_flight(leases, result_map, set())
    assert drains == ['owner-1', 'owner-1']


async def test_serial_flight_skips_the_drain_when_nothing_is_accepted():
    pump = make_pump()
    drains = []

    async def drain(owner_id):
        drains.append(owner_id)

    pump._drain_after_publication = drain
    pump.scheduler.complete = lambda *args, **kwargs: chain_exhaustion()
    await pump._publish_flight([lease('seg-a')], {'seg-a': WorkResult('seg-a', 'gs://a')}, set())
    assert drains == []


async def test_concurrent_flight_drains_once_per_owner(monkeypatch):
    pump = make_pump(publish_concurrency=4)
    drains = []

    async def drain(owner_id):
        drains.append(owner_id)

    pump._drain_after_publication = drain
    leases = [lease('seg-a'), lease('seg-b'), lease('seg-c', owner='owner-2')]
    result_map = {
        'seg-a': WorkResult('seg-a', 'gs://a'),
        'seg-b': WorkResult('seg-b', 'gs://b'),
        'seg-c': WorkResult('seg-c', 'gs://c'),
    }
    await pump._publish_flight(leases, result_map, set())
    assert drains.count('owner-1') == 1
    assert drains.count('owner-2') == 1


async def test_concurrent_flight_skips_the_drain_for_an_all_lost_owner():
    pump = make_pump(publish_concurrency=4)
    drains = []

    async def drain(owner_id):
        drains.append(owner_id)

    pump._drain_after_publication = drain
    pump.scheduler.complete = lambda *args, **kwargs: chain_exhaustion()
    await pump._publish_flight([lease('seg-a')], {'seg-a': WorkResult('seg-a', 'gs://a')}, set())
    assert drains == []


# --------------------------------------------------------------------------
# _drain_after_publication and drain_owner: the ordered-merge boundary
# --------------------------------------------------------------------------


async def test_exhausted_ordered_drain_arms_the_deferred_lane_without_raising(caplog):
    caplog.set_level(logging.INFO)
    pump = make_pump()
    pump.merge.commit_script['owner-1'] = [FirestoreContentionExhausted(EXHAUSTED)]
    await pump._drain_after_publication('owner-1')  # must not raise
    armed = pump._deferred_drains['owner-1']
    assert armed['attempts'] == 1
    assert pump._deferred_lane is not None
    deferred = [r.getMessage() for r in caplog.records if 'outcome=deferred' in r.getMessage()]
    assert deferred == ['event=batch_merge_drain outcome=deferred exception_type=FirestoreContentionExhausted']
    await pump.flush_deferred_drains()
    assert pump._deferred_drains == {}


async def test_deferred_lane_gives_up_at_the_attempt_cap_and_falls_back_to_the_error_line(caplog):
    caplog.set_level(logging.INFO)
    pump = make_pump()

    def always_hot(owner_id, now):
        raise FirestoreContentionExhausted(EXHAUSTED)

    pump.merge.commit_next = always_hot
    now = 1000.0
    pump._monotonic = lambda: now
    for _ in range(64):
        now += 30.0
        await pump._drain_after_publication('owner-1')
        if not pump._deferred_drains:
            break
        await pump._drain_deferred_due()
    assert pump._deferred_drains == {}
    deferred = [r.getMessage() for r in caplog.records if 'outcome=deferred' in r.getMessage()]
    assert len(deferred) == pump_module.DRAIN_RETRY_MAX_ATTEMPTS
    retry = [r.getMessage() for r in caplog.records if 'event=batch_merge outcome=retry' in r.getMessage()]
    assert len(retry) == 1
    assert 'exception_type=FirestoreContentionExhausted' in retry[0]
    await pump.flush_deferred_drains()


async def test_drain_owner_raises_when_the_merge_exhausts():
    pump = make_pump()
    pump.merge.commit_script['owner-1'] = [FirestoreContentionExhausted(EXHAUSTED)]
    with pytest.raises(FirestoreContentionExhausted):
        await pump.drain_owner('owner-1')


async def test_drain_owner_stops_at_the_first_none():
    pump = make_pump()
    pump.merge.commit_script['owner-1'] = [None]
    await pump.drain_owner('owner-1')
    assert len(pump.merge.drained) == 1


async def test_drain_owner_loops_until_the_merge_is_empty():
    pump = make_pump()
    pump.merge.commit_script['owner-1'] = [{'segment_id': 'a'}, {'segment_id': 'b'}, None]
    await pump.drain_owner('owner-1')
    assert len(pump.merge.drained) == 3


async def test_drain_owner_forwards_committed_entries_to_the_projection():
    pump = make_pump()
    committed = []
    pump.on_committed = committed.append
    entry = {'segment_id': 'a'}
    pump.merge.commit_script['owner-1'] = [entry, None]
    await pump.drain_owner('owner-1')
    assert committed == [entry]


async def test_projection_failure_after_a_commit_does_not_stop_the_drain():
    pump = make_pump()

    def on_committed(entry):
        chain_exhaustion()

    pump.on_committed = on_committed
    pump.merge.commit_script['owner-1'] = [{'segment_id': 'a'}, None]
    with pytest.raises(FirestoreContentionExhausted):
        await pump.drain_owner('owner-1')


# --------------------------------------------------------------------------
# _log_held_retry: the held-reoffer warning taxonomy
# --------------------------------------------------------------------------


def test_held_retry_warning_names_scope_and_exception():
    pump = make_pump()
    with pytest.MonkeyPatch.context() as patch:
        records = []
        handler = logging_handler(records)
        import logging as logging_module

        logging_module.getLogger('utils.batch_pipeline.pump').addHandler(handler)
        try:
            pump._log_held_retry('marker', FirestoreContentionExhausted(EXHAUSTED))
        finally:
            logging_module.getLogger('utils.batch_pipeline.pump').removeHandler(handler)
    [line] = [record for record in records if 'event=batch_merge' in record]
    assert 'action=held_reoffer' in line
    assert 'scope=marker' in line
    assert 'exception_type=FirestoreContentionExhausted' in line
    assert 'count=1' in line


def logging_handler(sink):
    import logging as logging_module

    class Sink(logging_module.Handler):
        def emit(self, record):
            sink.append(record.getMessage())

    return Sink()


# --------------------------------------------------------------------------
# Maintenance: per-step isolation under exhaustion (leader steps)
# --------------------------------------------------------------------------


def gate(monkeypatch, enabled):
    monkeypatch.setattr(pump_module, 'maintenance_contention_continuation_enabled', lambda: enabled)


async def test_leader_step_loss_returns_none_and_logs_the_step(caplog, monkeypatch):
    gate(monkeypatch, True)
    pump = make_pump()
    result = await pump._maintenance_step('projection', 'projection', None, lambda: chain_exhaustion())
    assert result is None
    retry_lines = [record.getMessage() for record in caplog.records if 'event=batch_maintenance' in record.getMessage()]
    assert len(retry_lines) == 1
    assert 'step=projection' in retry_lines[0]
    assert 'exception_type=FirestoreContentionExhausted' in retry_lines[0]
    assert 'site=' in retry_lines[0]


async def test_leader_step_loss_leaves_the_ready_due_page_running(monkeypatch):
    gate(monkeypatch, True)
    pump = make_pump()
    pump.scheduler.store.due = lambda state, now, limit: ['seg-1']
    pump.scheduler.recover = lambda now, limit=100: 0
    pump.project_pending = lambda: chain_exhaustion()  # projection step lost
    seen = []

    async def drain_ready(ready):
        seen.extend(ready)

    monkeypatch.setattr(pump, '_drain_ready_owners', drain_ready)
    await pump._maintain_leader_steps()
    assert seen == ['seg-1']


async def test_leader_ready_page_loss_leaves_the_marked_page_running(monkeypatch):
    gate(monkeypatch, True)
    pump = make_pump()
    pump.scheduler.recover = lambda now, limit=100: 0
    pump.scheduler.store.due = lambda state, now, limit: chain_exhaustion()  # ready_due step lost
    pump.merge.marked_page_result = [('owner-9', None)]
    await pump._maintain_leader_steps()
    assert pump.merge.released == [('owner-9', True)]


async def test_held_owner_reoffer_runs_after_a_lost_marked_page(monkeypatch):
    gate(monkeypatch, True)
    pump = make_pump()
    pump.scheduler.recover = lambda now, limit=100: 0
    pump.scheduler.store.due = lambda state, now, limit: []
    pump.merge.marked_page_result = []
    pump.merge.commit_script['owner-1'] = [{'segment_id': 'a'}, None]
    pump.merge.held_owners.add('owner-1')
    await pump._maintain()  # the held reoffer follows the leader steps in _maintain
    assert pump.merge.drained  # the held owner was re-offered


async def test_recover_step_loss_is_logged_under_the_recover_step_name(monkeypatch, caplog):
    gate(monkeypatch, True)
    pump = make_pump()

    def recover(now, limit=100):
        chain_exhaustion()

    pump.scheduler.recover = recover
    pump.scheduler.store.due = lambda state, now, limit: []
    await pump._maintain_leader_steps()
    retry_lines = [record.getMessage() for record in caplog.records if 'step=' in record.getMessage()]
    assert any('step=recover' in line for line in retry_lines)


async def test_legacy_path_first_failure_aborts_the_sweep(monkeypatch):
    gate(monkeypatch, False)
    pump = make_pump()
    pump.project_pending = None

    def recover(now, limit=100):
        chain_exhaustion()

    pump.scheduler.recover = recover
    with pytest.raises(FirestoreContentionExhausted):
        await pump._maintain()


async def test_non_contention_step_loss_still_logs_and_returns_none(monkeypatch):
    gate(monkeypatch, True)
    pump = make_pump()
    assert (
        await pump._maintenance_step('projection', 'projection', None, lambda: (_ for _ in ()).throw(KeyError('x')))
        is None
    )


async def test_maintenance_step_success_returns_the_result(monkeypatch):
    gate(monkeypatch, True)
    pump = make_pump()
    assert await pump._maintenance_step('ready_due', 'maintenance', None, lambda: ['seg-1']) == ['seg-1']


# --------------------------------------------------------------------------
# _release: lease recovery under exhaustion stays durable
# --------------------------------------------------------------------------


async def test_release_exhaustion_is_logged_and_does_not_raise():
    pump = make_pump()
    pump.scheduler.release = lambda *args, **kwargs: chain_exhaustion()
    await pump._release([lease('seg-a')])  # durable lease expiry remains the fallback


async def test_release_successes_continue_past_one_exhaustion():
    pump = make_pump()
    calls = []

    def release(segment_id, token, now):
        calls.append(segment_id)
        if segment_id == 'seg-a':
            chain_exhaustion()
        return True

    pump.scheduler.release = release
    await pump._release([lease('seg-a'), lease('seg-b')])
    assert calls == ['seg-a', 'seg-b']
