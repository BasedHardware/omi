"""Backlog state machine: every non-terminal state has an owner, a deadline and a counter.

One test per bug class from the 2026-11-07 backlog root-cause review
(data/run-2026-11-07-backlog-hypotheses in the workspace meta-repo):

1. the retry cap enforces by default, not only for the CAPTURE_COVERAGE_MODE cohort;
2. a running sync lease expiry carries dispatch_attempt instead of resetting it;
3. a held/dead-letter requeue grants a fresh attempt budget;
4. an aged record_pending row whose conversation exists but never finished
   is re-driven weekly with a counter, then parked as a retained dead letter;
5. (C7) assignment_held has an automatic exit for restorable targets only;
6. held and projection re-drive keep a counter and stop after N.

Every test also proves the kill switch restores the old transition.
"""

import asyncio
from copy import deepcopy
from datetime import timedelta
from unittest.mock import Mock
from uuid import uuid4

import pytest

from config import backlog_state_machine as sm
from database import sync_backfill_sequencer as registry, sync_jobs
from database.batch_pipeline_quarantine_recovery import RecoveryStore
from tests.unit.test_batch_pipeline_quarantine_recovery import setup  # noqa: F401
from tests.unit.test_batch_pipeline_scheduler import MemoryStore, item
from tests.unit.test_sync_backfill_uid_sequencer import db, NOW, _register  # noqa: F401
from utils import backlog_metrics
from utils.batch_pipeline.scheduler import Scheduler
from utils.sync import uid_sequencer

SWITCHES = (
    sm.RETRY_CAP_SWITCH,
    sm.SYNC_ATTEMPT_CARRY_SWITCH,
    sm.HELD_REDRIVE_BUDGET_SWITCH,
    sm.HELD_REDRIVE_COUNTER_SWITCH,
    sm.HELD_REDRIVE_STOP_SWITCH,
    sm.RECORD_BARRIER_DEAD_LETTER_SWITCH,
    sm.ASSIGNMENT_HOLD_ESCALATION_SWITCH,
)
# The class 6 terminal stop's own switch (split from class 3's budget reset).
STOP_SWITCH = sm.HELD_REDRIVE_STOP_SWITCH


@pytest.fixture(autouse=True)
def defaults(monkeypatch):
    # The production defaults: no capture-coverage mode or cohort, every switch unset.
    for name in (
        'CAPTURE_COVERAGE_MODE',
        'CAPTURE_COVERAGE_MODE_SERVE_PERCENT',
        'CAPTURE_COVERAGE_MODE_SERVE_UID_SHA256S',
        *SWITCHES,
    ):
        monkeypatch.delenv(name, raising=False)


def transitions(name):
    return backlog_metrics.TERMINAL_TRANSITIONS.labels(name)._value.get()


# Defaults by the lead2 rule (64b2fa): ON only where a class just cuts wasted
# work or retries; OFF where it changes custody, settle or expiry semantics.
EXPECTED_DEFAULTS = {
    sm.RETRY_CAP_SWITCH: False,
    sm.SYNC_ATTEMPT_CARRY_SWITCH: True,
    sm.HELD_REDRIVE_BUDGET_SWITCH: False,
    sm.HELD_REDRIVE_COUNTER_SWITCH: True,
    sm.HELD_REDRIVE_STOP_SWITCH: False,
    sm.RECORD_BARRIER_DEAD_LETTER_SWITCH: False,
    sm.ASSIGNMENT_HOLD_ESCALATION_SWITCH: False,
}
READERS = {
    sm.RETRY_CAP_SWITCH: sm.retry_cap_enforced,
    sm.SYNC_ATTEMPT_CARRY_SWITCH: sm.sync_attempt_carry_enabled,
    sm.HELD_REDRIVE_BUDGET_SWITCH: sm.held_redrive_budget_enabled,
    sm.HELD_REDRIVE_COUNTER_SWITCH: sm.held_redrive_counter_enabled,
    sm.HELD_REDRIVE_STOP_SWITCH: sm.held_redrive_stop_enabled,
    sm.RECORD_BARRIER_DEAD_LETTER_SWITCH: sm.record_barrier_dead_letter_enabled,
    sm.ASSIGNMENT_HOLD_ESCALATION_SWITCH: sm.assignment_hold_escalation_enabled,
}


@pytest.mark.parametrize('name', sorted(EXPECTED_DEFAULTS))
def test_switch_default_and_both_explicit_states(monkeypatch, name):
    from config.policy.kill_switches import KILL_SWITCHES

    assert set(SWITCHES) == set(EXPECTED_DEFAULTS) == set(READERS)
    assert KILL_SWITCHES[name] is EXPECTED_DEFAULTS[name]
    assert READERS[name]() is EXPECTED_DEFAULTS[name]
    # The capture-coverage serve mode never changes a backlog switch default.
    monkeypatch.setenv('CAPTURE_COVERAGE_MODE', 'serve')
    assert READERS[name]() is EXPECTED_DEFAULTS[name]
    monkeypatch.setenv(name, 'true')
    assert READERS[name]() is True
    monkeypatch.setenv(name, 'false')
    assert READERS[name]() is False


# 1. Retry cap enforcement (CAPTURE_RETRY_CAP_ENFORCED, default OFF) ---------------


@pytest.mark.parametrize('switch,expected', [('true', 'quarantined'), (None, 'retry'), ('false', 'retry')])
def test_retry_cap_enforced_by_default_on_lease_expiry(monkeypatch, switch, expected):
    if switch is not None:
        monkeypatch.setenv(sm.RETRY_CAP_SWITCH, switch)
    monkeypatch.setenv('BATCH_PIPELINE_MAX_ATTEMPTS', '2')
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('poison', owner=uuid4().hex), 0)
    for attempt in (1, 2):
        now = attempt * 1000
        queue.recover(now)
        lease = queue.pull(now)[0]
        assert lease.attempt == attempt
        assert queue.recover(now + 121) == 1
    job = store.rows['jobs', 'poison']
    assert job['state'] == expected
    if expected == 'quarantined':
        # Quarantine is a retained hold, never a deletion.
        assert job['recovery_state'] == 'held' and job['audio_uri']
    else:
        # The rollback restores the shadow-only behavior: the poison unit stays runnable.
        assert job['merge_pending']


@pytest.mark.parametrize('switch,serving', [('true', True), (None, False), ('false', False)])
def test_retry_cap_serves_without_capture_coverage_cohort(monkeypatch, switch, serving):
    from utils.capture.retry_cap import retry_cap

    if switch is not None:
        monkeypatch.setenv(sm.RETRY_CAP_SWITCH, switch)
    decision = retry_cap(uuid4().hex, 5, 5)
    assert decision.reached and decision.serving is serving
    monkeypatch.setenv('CAPTURE_COVERAGE_MODE', 'off')
    decision = retry_cap(uuid4().hex, 5, 5)
    # Coverage mode off no longer disables the cap; only the cap's own switch does.
    assert (decision is not None) is serving


# 2. Sync lease expiry carries dispatch_attempt (SYNC_DISPATCH_ATTEMPT_CARRY_ENABLED, default ON)


def running_owner(db, monkeypatch, attempts='5'):
    account = uuid4().hex
    monkeypatch.setenv('SYNC_TASKS_MAX_ATTEMPTS', attempts)
    monkeypatch.setattr(uid_sequencer, 'sync_job_run_lock_present', lambda _: False)
    monkeypatch.setattr(uid_sequencer, 'get_sync_job', lambda _: {'status': 'processing'})
    _register(account, 'crashy', 0, db=db)
    claim = registry.claim_next(account, now=NOW)
    return account, claim['epoch']


def crash_once(account, epoch, now):
    """The worker begins, then dies: the running lease expires without a run lock."""
    assert registry.begin_job(account, 'crashy', epoch, now=now)
    expired = now + timedelta(seconds=registry.LEASE_SECONDS + 1)
    return registry.redrive_job(account, 'crashy', epoch, now=expired), expired


@pytest.mark.parametrize('switch,expected', [('true', [1, 2, 3]), (None, [1, 2, 3]), ('false', [0, 0, 0])])
def test_running_lease_expiry_keeps_the_attempt_budget(db, monkeypatch, switch, expected):
    if switch is not None:
        monkeypatch.setenv(sm.SYNC_ATTEMPT_CARRY_SWITCH, switch)
    account, epoch = running_owner(db, monkeypatch)
    seen, now = [], NOW
    for _ in expected:
        replacement, now = crash_once(account, epoch, now)
        # Epoch still fences the expired worker; only the count changed.
        assert replacement['epoch'] == epoch + 1
        epoch = replacement['epoch']
        seen.append(registry.get_owner(account)['dispatch_attempt'])
    assert seen == expected


def test_running_lease_expiry_at_the_cap_terminalizes_instead_of_redriving(db, monkeypatch):
    monkeypatch.setenv(sm.RETRY_CAP_SWITCH, 'true')  # finalization needs class 1 on
    account, epoch = running_owner(db, monkeypatch, attempts='2')
    replacement, now = crash_once(account, epoch, NOW)
    assert replacement['dispatch_attempt'] == 1
    assert registry.get_owner(account)['running_expiries'] == 1
    epoch = replacement['epoch']
    assert registry.begin_job(account, 'crashy', epoch, now=now)
    expired = now + timedelta(seconds=registry.LEASE_SECONDS + 1)
    dispatch = Mock(side_effect=AssertionError('a capped job must not be redriven'))
    monkeypatch.setattr(uid_sequencer, '_dispatch', dispatch)
    monkeypatch.setattr(uid_sequencer, 'try_acquire_job_run_lock', lambda _: 'lock')
    monkeypatch.setattr(uid_sequencer, 'release_job_run_lock', Mock())
    failure = Mock(
        return_value=sync_jobs.FencedSyncJobMutation(
            outcome=sync_jobs.FencedSyncJobMutationOutcome.APPLIED, job={'status': 'failed'}
        )
    )
    monkeypatch.setattr(uid_sequencer, 'fenced_mark_job_failed', failure)
    monkeypatch.setattr(uid_sequencer, '_cleanup_capped_chain_job_side_effects', Mock(return_value=True))
    monkeypatch.setattr(uid_sequencer, 'kick', Mock())
    before = transitions('sync_running_cap_reached')
    outcome = uid_sequencer.reconcile_uid(account, registry.get_owner(account), now=expired)
    assert outcome == 'dispatch_retry_cap_reached'
    assert failure.call_args.kwargs['reason_code'] == 'sync_dispatch_exhausted'
    assert not registry.get_owner(account).get('active_job_id')
    assert transitions('sync_running_cap_reached') == before + 1


def test_delayed_queue_dispatch_retries_are_not_terminalized_by_default(db, monkeypatch):
    """A passed dispatch retry deadline is not failure: a backlogged queue delivers late.

    Only a running lease expiry (the job began and died) is capped by default;
    the dispatching-state cap keeps its CAPTURE_COVERAGE_MODE cohort gate.
    """
    from utils.sync import retry_hygiene

    account, epoch = running_owner(db, monkeypatch, attempts='2')
    owner = registry.get_owner(account)
    for minute in range(6, 61, 6):
        current = NOW + timedelta(minutes=minute)
        replacement = registry.redrive_job(account, 'crashy', epoch, now=current)
        assert replacement is not None and replacement['epoch'] == epoch
        owner = registry.get_owner(account)
    assert owner['dispatch_attempt'] == 10 and owner['running_expiries'] == 0
    decision = retry_hygiene.dispatch_cap(account, owner)
    assert decision.reached and not decision.serving


def finalizer_mocks(monkeypatch):
    monkeypatch.setattr(uid_sequencer, 'try_acquire_job_run_lock', lambda _: 'lock')
    monkeypatch.setattr(uid_sequencer, 'try_acquire_sync_job_run_lock', lambda _: 'lock')
    monkeypatch.setattr(uid_sequencer, 'release_job_run_lock', Mock())
    failure = Mock(
        return_value=sync_jobs.FencedSyncJobMutation(
            outcome=sync_jobs.FencedSyncJobMutationOutcome.APPLIED, job={'status': 'failed'}
        )
    )
    monkeypatch.setattr(uid_sequencer, 'fenced_mark_job_failed', failure)
    monkeypatch.setattr(uid_sequencer, '_cleanup_capped_chain_job_side_effects', Mock(return_value=True))
    monkeypatch.setattr(uid_sequencer, 'kick', Mock())
    monkeypatch.setattr(uid_sequencer, '_dispatch', Mock())
    return failure


def test_budget_deferred_owner_that_keeps_crashing_reaches_a_terminal_outcome(db, monkeypatch):
    """Review wave 1 (finding 2): one budget deferral must not disable crash accounting.

    The chain deferred once, then every replacement crashed (lease expired, no
    run lock, no live deferred_until marker). The UID lane must terminate.
    """
    monkeypatch.setenv(sm.RETRY_CAP_SWITCH, 'true')  # finalization needs class 1 on
    account, epoch = running_owner(db, monkeypatch, attempts='5')
    failure = finalizer_mocks(monkeypatch)
    now, outcomes = NOW, []
    for _ in range(8):
        owner = registry.get_owner(account)
        if not owner.get('active_job_id'):
            break
        epoch = owner['active_epoch']
        assert registry.begin_job(account, 'crashy', epoch, now=now)
        assert registry.note_budget_deferral(account, 'crashy', epoch, 1, now=now)
        now += timedelta(seconds=registry.LEASE_SECONDS + 1)
        outcomes.append(uid_sequencer.reconcile_uid(account, registry.get_owner(account), now=now))
    assert outcomes[-1] == 'dispatch_retry_cap_reached', outcomes
    assert failure.call_args.kwargs['reason_code'] == 'sync_dispatch_exhausted'
    assert not registry.get_owner(account).get('active_job_id')


def test_expiry_during_a_live_budget_deferral_is_not_counted_as_a_crash(db, monkeypatch):
    import time as _time

    account, epoch = running_owner(db, monkeypatch, attempts='5')
    finalizer_mocks(monkeypatch)
    monkeypatch.setattr(
        uid_sequencer, 'get_sync_job', lambda _: {'status': 'processing', 'deferred_until': _time.time() + 3600}
    )
    now = NOW
    for _ in range(4):
        epoch = registry.get_owner(account)['active_epoch']
        assert registry.begin_job(account, 'crashy', epoch, now=now)
        assert registry.note_budget_deferral(account, 'crashy', epoch, 1, now=now)
        now += timedelta(seconds=registry.LEASE_SECONDS + 1)
        assert uid_sequencer.reconcile_uid(account, registry.get_owner(account), now=now) == 'lease_expired'
    assert registry.get_owner(account)['running_expiries'] == 0


def test_running_owner_at_cap_with_terminal_job_is_not_stranded(db, monkeypatch):
    """The cap lives in the reconciler only; redrive_job never refuses a running owner."""
    account, epoch = running_owner(db, monkeypatch, attempts='2')
    replacement, now = crash_once(account, epoch, NOW)
    epoch = replacement['epoch']
    assert registry.begin_job(account, 'crashy', epoch, now=now)
    monkeypatch.setattr(uid_sequencer, 'get_sync_job', lambda _: {'status': 'completed'})
    dispatch = Mock()
    monkeypatch.setattr(uid_sequencer, '_dispatch', dispatch)
    expired = now + timedelta(seconds=registry.LEASE_SECONDS + 1)
    assert uid_sequencer.reconcile_uid(account, registry.get_owner(account), now=expired) == 'terminal_cleanup'
    dispatch.assert_called_once()


def at_cap_running_owner(db, monkeypatch):
    """Two crashes with the carry switch ON: running_expiries is 1 of a cap of 2."""
    account, epoch = running_owner(db, monkeypatch, attempts='2')
    replacement, now = crash_once(account, epoch, NOW)
    owner = registry.get_owner(account)
    assert owner['running_expiries'] == 1 and owner['dispatch_attempt'] == 1
    epoch = replacement['epoch']
    assert registry.begin_job(account, 'crashy', epoch, now=now)
    return account, now + timedelta(seconds=registry.LEASE_SECONDS + 1)


@pytest.mark.parametrize('switch', ['false', 'true', None])
def test_running_cap_kill_switch_through_the_sweep(db, monkeypatch, switch):
    """Review wave 2: drive reconcile_uid, not redrive_job.

    The next crash puts a running owner at its cap. With the switch OFF the
    sweep must redrive it (replacement dispatched, counters reset, nothing
    finalized). The switch-ON control finalizes the same owner.
    """
    monkeypatch.setenv(sm.RETRY_CAP_SWITCH, 'true')  # finalization needs class 1 on
    account, expired = at_cap_running_owner(db, monkeypatch)
    failure = finalizer_mocks(monkeypatch)
    dispatch = Mock()
    monkeypatch.setattr(uid_sequencer, '_dispatch', dispatch)
    if switch is not None:
        monkeypatch.setenv(sm.SYNC_ATTEMPT_CARRY_SWITCH, switch)
    outcome = uid_sequencer.reconcile_uid(account, registry.get_owner(account), now=expired)
    owner = registry.get_owner(account)
    if switch == 'false':
        assert outcome == 'lease_expired'
        dispatch.assert_called_once()
        assert owner['active_job_id'] == 'crashy'
        assert owner['dispatch_attempt'] == 0 and owner['running_expiries'] == 0
        failure.assert_not_called()
    else:
        assert outcome == 'dispatch_retry_cap_reached'
        dispatch.assert_not_called()
        assert not owner.get('active_job_id')
        assert failure.call_args.kwargs['reason_code'] == 'sync_dispatch_exhausted'


@pytest.mark.parametrize('class1', ['false', None])
@pytest.mark.parametrize('coverage', [None, 'serve_mode', 'serve_cohort'])
def test_running_cap_only_observes_while_class_1_is_off(db, monkeypatch, class1, coverage):
    """CAPTURE_RETRY_CAP_ENFORCED off (explicit or default): the carried count never finalizes.

    Review wave 4 (finding 1): this holds for capture-coverage serving users
    too (CAPTURE_COVERAGE_MODE=serve, or a uid in the serve cohort). Main never
    capped running owners, so only class 1 may turn the running cap on.
    """
    from config.refactor_modes import uid_digest

    if class1 is not None:
        monkeypatch.setenv(sm.RETRY_CAP_SWITCH, class1)
    account, expired = at_cap_running_owner(db, monkeypatch)
    if coverage == 'serve_mode':
        monkeypatch.setenv('CAPTURE_COVERAGE_MODE', 'serve')
    elif coverage == 'serve_cohort':
        monkeypatch.setenv('CAPTURE_COVERAGE_MODE', 'shadow')
        monkeypatch.setenv('CAPTURE_COVERAGE_MODE_SERVE_UID_SHA256S', uid_digest(account))
    failure = finalizer_mocks(monkeypatch)
    dispatch = Mock()
    monkeypatch.setattr(uid_sequencer, '_dispatch', dispatch)
    assert uid_sequencer.reconcile_uid(account, registry.get_owner(account), now=expired) == 'lease_expired'
    dispatch.assert_called_once()
    failure.assert_not_called()
    assert registry.get_owner(account)['running_expiries'] == 2


# 3 and 6. Held requeue resets the budget; automatic re-drive stops after N --------


def held_dead(job, *, attempt=5, expired_at=20):
    job.update(
        state='dead',
        dead_letter_reason='held_expired',
        held_expired_at=expired_at,
        merge_pending=True,
        attempt=attempt,
        token='',
        lease_until=0,
    )


def bad(client):
    return client.rows['batch_pipeline_prod_jobs', 'bad']


def control_for(client):
    from config.batch_pipeline import scheduler_control_key

    client.rows['batch_pipeline_prod_control', scheduler_control_key(bad(client)['owner_key'])] = {'p0_active': True}


@pytest.mark.parametrize('switch', ['true', None, 'false'])
def test_requeue_grants_a_fresh_attempt_budget(setup, monkeypatch, switch):
    if switch is not None:
        monkeypatch.setenv(sm.HELD_REDRIVE_BUDGET_SWITCH, switch)
    client, store, _, _, _, _ = setup
    control_for(client)
    held_dead(bad(client), attempt=5)
    assert RecoveryStore(store).requeue_quarantined('bad', 30, dead_before=86400) is True
    job = bad(client)
    assert job['state'] == 'ready' and job['audio_uri'] == 'gs://synthetic/audio'
    if switch == 'true':
        # A re-drive gets a real attempt: the first failure no longer re-quarantines.
        assert job['attempt'] == 0
        assert job['held_redrives'] == 1 and job['held_redrive_last_attempt'] == 5
    else:
        # Budget reset off (default): attempt stays; the class 6 counter still counts.
        assert job['attempt'] == 5 and job['held_redrives'] == 1
        assert 'held_redrive_last_attempt' not in job


@pytest.mark.parametrize('budget,after', [('true', 'retry'), (None, 'quarantined'), ('false', 'quarantined')])
def test_requeued_unit_survives_one_lease_expiry_with_a_fresh_budget(monkeypatch, budget, after):
    monkeypatch.setenv(sm.RETRY_CAP_SWITCH, 'true')  # reaching quarantine needs class 1 on
    if budget is not None:
        monkeypatch.setenv(sm.HELD_REDRIVE_BUDGET_SWITCH, budget)
    monkeypatch.setenv('BATCH_PIPELINE_MAX_ATTEMPTS', '2')
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('poison', owner=uuid4().hex), 0)
    for attempt in (1, 2):
        queue.recover(attempt * 1000)
        queue.pull(attempt * 1000)
        queue.recover(attempt * 1000 + 121)
    job = store.rows['jobs', 'poison']
    assert job['state'] == 'quarantined' and job['attempt'] == 2
    assert store.run(lambda tx: Scheduler.requeue_quarantined_in_transaction(tx, tx.get('jobs', 'poison'), 5000))
    lease = queue.pull(5000)[0]
    assert lease.attempt == (1 if budget == 'true' else 3)
    queue.recover(5121)
    # Budget off: attempt stayed at the cap and this first expiry re-quarantines.
    assert store.rows['jobs', 'poison']['state'] == after


def test_automatic_redrive_stops_after_max_and_operator_can_still_requeue(setup, monkeypatch):
    monkeypatch.setenv(STOP_SWITCH, 'true')  # class 6 terminal stop (default off)
    monkeypatch.setenv(sm.HELD_REDRIVE_BUDGET_SWITCH, 'true')  # class 3 reset, asserted below
    client, store, _, _, _, _ = setup
    control_for(client)
    recovery = RecoveryStore(store)
    original_audio = bad(client)['audio_uri']
    now = 30
    for redrive in range(1, sm.MAX_HELD_REDRIVES + 1):
        # The unit failed again and its held window expired: back to dead/held_expired.
        held_dead(bad(client), attempt=5, expired_at=now)
        bad(client).pop('result', None)
        assert recovery.requeue_quarantined('bad', now + 1, dead_before=now + 86400) is True
        assert bad(client)['held_redrives'] == redrive and bad(client)['attempt'] == 0
        now += 86400 * 8
    held_dead(bad(client), attempt=5, expired_at=now)
    before = transitions('held_exhausted')
    assert recovery.requeue_quarantined('bad', now + 1, dead_before=now + 86400) == 'exhausted'
    job = bad(client)
    assert job['state'] == 'dead' and job['dead_letter_reason'] == sm.HELD_EXHAUSTED_REASON
    assert job['held_exhausted_at'] == now + 1 and job['audio_uri'] == original_audio
    assert job['held_redrives'] == sm.MAX_HELD_REDRIVES
    # The nightly pass never selects it again (it filters on held_expired) and refuses it directly.
    snapshot = deepcopy(client.rows)
    assert recovery.requeue_quarantined('bad', now + 2, dead_before=now + 86400) is False
    assert client.rows == snapshot
    # The terminal stop is for automation only: an operator requeue still works.
    assert recovery.requeue_quarantined('bad', now + 3) is True
    assert bad(client)['state'] == 'ready' and bad(client)['attempt'] == 0


def test_malformed_redrive_counter_counts_as_spent(setup, monkeypatch):
    monkeypatch.setenv(STOP_SWITCH, 'true')  # class 6 terminal stop (default off)
    client, store, _, _, _, _ = setup
    control_for(client)
    held_dead(bad(client))
    bad(client)['held_redrives'] = 'two'
    assert RecoveryStore(store).requeue_quarantined('bad', 30, dead_before=86400) == 'exhausted'


@pytest.mark.parametrize('stop', ['false', None])
def test_terminal_stop_off_keeps_legacy_unbounded_nightly_redrive(setup, monkeypatch, stop):
    if stop is not None:
        monkeypatch.setenv(STOP_SWITCH, stop)
    client, store, _, _, _, _ = setup
    control_for(client)
    held_dead(bad(client))
    bad(client)['held_redrives'] = sm.MAX_HELD_REDRIVES + 5
    assert RecoveryStore(store).requeue_quarantined('bad', 30, dead_before=86400) is True


@pytest.mark.parametrize('stop', ['true', 'false', None])
@pytest.mark.parametrize('reason', ['held_expired', sm.HELD_EXHAUSTED_REASON])
def test_client_poll_never_redrives_a_retained_held_dead_letter(monkeypatch, reason, stop):
    """Review wave 1 (finding 1): the real status-poll path, not RecoveryStore.

    durable_status() redrove every dead merge-pending unit on each phone poll,
    which bypassed held_redrives and the attempt reset. Only an operator or the
    counted nightly pass may move a retained held dead letter.
    """
    from tests.unit.test_batch_pipeline_intake import proposal, submit
    from utils.batch_pipeline.intake import durable_status

    if stop is not None:
        monkeypatch.setenv(STOP_SWITCH, stop)
    monkeypatch.setenv('BATCH_PIPELINE_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_UID_ALLOWLIST', 'synthetic-owner')
    monkeypatch.setenv('BATCH_PIPELINE_PERCENT', '0')
    store = MemoryStore()
    submit(store, *proposal())
    queue = Scheduler(store)
    queue.pull(100)
    store.rows['jobs', 'segment'].update(
        state='dead',
        token='',
        lease_until=0,
        merge_pending=True,
        dead_letter_reason=reason,
        held_redrives=sm.MAX_HELD_REDRIVES,
        attempt=5,
    )
    durable_status(store, 'synthetic-owner', 'bp_first')
    job = store.rows['jobs', 'segment']
    if stop != 'true':
        # Terminal stop off (default): the legacy poll redrive is unchanged.
        assert job['state'] == 'ready'
        return
    assert job['state'] == 'dead' and job['attempt'] == 5
    assert queue.pull(9999999999) == []
    # Explicit operator recovery still works.
    assert queue.redrive_dead('segment', 10**10)
    assert store.rows['jobs', 'segment']['state'] == 'ready'


@pytest.mark.parametrize('counter', ['true', 'false'])
@pytest.mark.parametrize('budget', ['true', 'false'])
def test_client_poll_redrive_with_stop_off_keeps_the_nightly_accounting(monkeypatch, counter, budget):
    """Review wave 3 (finding 2): a poll re-drive is counted and reset like the nightly one."""
    from tests.unit.test_batch_pipeline_intake import proposal, submit
    from utils.batch_pipeline.intake import durable_status

    monkeypatch.setenv(STOP_SWITCH, 'false')
    monkeypatch.setenv(sm.HELD_REDRIVE_COUNTER_SWITCH, counter)
    monkeypatch.setenv(sm.HELD_REDRIVE_BUDGET_SWITCH, budget)
    monkeypatch.setenv('BATCH_PIPELINE_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_UID_ALLOWLIST', 'synthetic-owner')
    monkeypatch.setenv('BATCH_PIPELINE_PERCENT', '0')
    store = MemoryStore()
    submit(store, *proposal())
    Scheduler(store).pull(100)
    store.rows['jobs', 'segment'].update(
        state='dead',
        token='',
        lease_until=0,
        merge_pending=True,
        dead_letter_reason='held_expired',
        held_redrives=1,
        attempt=5,
    )
    durable_status(store, 'synthetic-owner', 'bp_first')
    job = store.rows['jobs', 'segment']
    assert job['state'] == 'ready'
    assert job['held_redrives'] == (2 if counter == 'true' else 1)
    assert job['attempt'] == (0 if budget == 'true' else 5)


def test_repeated_poll_redrives_report_a_spent_budget_with_the_stop_off(monkeypatch):
    """Review wave 4 (finding 2): poll re-drives emit the same spent-budget signal as the nightly scan."""
    from tests.unit.test_batch_pipeline_intake import proposal, submit
    from utils.batch_pipeline.intake import durable_status

    monkeypatch.setenv(STOP_SWITCH, 'false')
    monkeypatch.setenv(sm.HELD_REDRIVE_COUNTER_SWITCH, 'true')
    monkeypatch.setenv('BATCH_PIPELINE_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_UID_ALLOWLIST', 'synthetic-owner')
    monkeypatch.setenv('BATCH_PIPELINE_PERCENT', '0')
    store = MemoryStore()
    submit(store, *proposal())
    Scheduler(store).pull(100)
    seen = []
    for _ in range(sm.MAX_HELD_REDRIVES + 2):
        # The unit failed again and its held window expired: a retained dead letter again.
        store.rows['jobs', 'segment'].update(
            state='dead', token='', lease_until=0, merge_pending=True, dead_letter_reason='held_expired'
        )
        before = transitions('held_redrive_budget_spent')
        durable_status(store, 'synthetic-owner', 'bp_first')
        assert store.rows['jobs', 'segment']['state'] == 'ready'
        seen.append(transitions('held_redrive_budget_spent') - before)
    # Below the budget (0..MAX-1 prior re-drives): no signal. At or over it: one per committed poll.
    assert seen == [0] * sm.MAX_HELD_REDRIVES + [1, 1]
    assert store.rows['jobs', 'segment']['held_redrives'] == sm.MAX_HELD_REDRIVES + 2


def test_client_poll_still_redrives_a_plain_historical_dead_row(monkeypatch):
    from tests.unit.test_batch_pipeline_intake import proposal, submit
    from utils.batch_pipeline.intake import durable_status

    monkeypatch.setenv('BATCH_PIPELINE_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_UID_ALLOWLIST', 'synthetic-owner')
    monkeypatch.setenv('BATCH_PIPELINE_PERCENT', '0')
    store = MemoryStore()
    submit(store, *proposal())
    Scheduler(store).pull(100)
    store.rows['jobs', 'segment'].update(state='dead', token='', lease_until=0)
    durable_status(store, 'synthetic-owner', 'bp_first')
    assert store.rows['jobs', 'segment']['state'] == 'ready'


def test_switch_off_nightly_pass_requeues_an_exhausted_unit(setup, monkeypatch):
    """Review wave 2 (finding 1): on -> exhaust -> off -> nightly requeue.

    The fake candidate query honors the real filter (state=dead and the
    requested dead_letter_reason), so the pass must ask for held_exhausted.
    """
    from utils.batch_pipeline import held_dead_letter as sweep

    monkeypatch.setenv(STOP_SWITCH, 'true')
    client, store, _, _, _, _ = setup
    control_for(client)
    held_dead(bad(client), expired_at=20)
    bad(client)['held_redrives'] = sm.MAX_HELD_REDRIVES
    assert RecoveryStore(store).requeue_quarantined('bad', 30, dead_before=86400) == 'exhausted'
    assert bad(client)['dead_letter_reason'] == sm.HELD_EXHAUSTED_REASON
    monkeypatch.setenv(STOP_SWITCH, 'false')

    def candidates(_client, _namespace, limit=32, *, after_id=None, reason='held_expired'):
        return [
            (key[1], dict(row))
            for key, row in sorted(client.rows.items())
            if key[0] == 'batch_pipeline_prod_jobs'
            and row.get('state') == 'dead'
            and row.get('dead_letter_reason') == reason
        ][:limit]

    monkeypatch.setattr(sweep, 'held_candidates', lambda *a, **k: [])
    monkeypatch.setattr(sweep, 'dead_held_candidates', candidates)
    sweep.HeldDeadLetter(store).tick(2 * 86400)
    job = bad(client)
    assert job['state'] == 'ready' and job['merge_pending'] is True
    assert job['audio_uri'] == 'gs://synthetic/audio'


def test_switch_on_nightly_pass_never_requeues_an_exhausted_unit(setup, monkeypatch):
    monkeypatch.setenv(STOP_SWITCH, 'true')  # class 6 terminal stop (default off)
    client, store, _, _, _, _ = setup
    control_for(client)
    held_dead(bad(client), expired_at=20)
    bad(client)['dead_letter_reason'] = sm.HELD_EXHAUSTED_REASON
    bad(client)['held_redrives'] = sm.MAX_HELD_REDRIVES
    assert RecoveryStore(store).requeue_quarantined('bad', 30, dead_before=86400) is False
    assert bad(client)['state'] == 'dead'


@pytest.mark.parametrize('switch', ['true', None, 'false'])
def test_redrive_counter_counts_requeues_only_with_its_switch(setup, monkeypatch, switch):
    """Class 6 counter (BATCH_HELD_REDRIVE_COUNTER_ENABLED, default ON)."""
    if switch is not None:
        monkeypatch.setenv(sm.HELD_REDRIVE_COUNTER_SWITCH, switch)
    client, store, _, _, _, _ = setup
    control_for(client)
    held_dead(bad(client), attempt=5)
    assert RecoveryStore(store).requeue_quarantined('bad', 30, dead_before=86400) is True
    if switch == 'false':
        assert 'held_redrives' not in bad(client)
    else:
        assert bad(client)['held_redrives'] == 1


@pytest.mark.parametrize('switch', ['true', None, 'false'])
def test_nightly_pass_reports_a_spent_budget_only_with_the_counter_on(monkeypatch, switch):
    from utils.batch_pipeline import held_dead_letter as sweep

    if switch is not None:
        monkeypatch.setenv(sm.HELD_REDRIVE_COUNTER_SWITCH, switch)
    store = Mock()
    store.run.side_effect = lambda fn: fn(Mock(get=Mock(return_value={})))
    runner = sweep.HeldDeadLetter(store)
    spent = {'held_expired_at': 1, 'held_redrives': sm.MAX_HELD_REDRIVES}
    monkeypatch.setattr(sweep, 'held_candidates', lambda *a, **k: [])
    monkeypatch.setattr(sweep, 'dead_held_candidates', lambda *a, **k: [('a', spent)])
    monkeypatch.setattr(runner.recovery, 'requeue_quarantined', lambda *a, **k: False)
    before = transitions('held_redrive_budget_spent')
    runner.tick(86400)
    assert transitions('held_redrive_budget_spent') == before + (0 if switch == 'false' else 1)


def test_nightly_tick_counts_exhausted_separately(monkeypatch):
    from utils.batch_pipeline import held_dead_letter as sweep

    store = Mock()
    store.run.side_effect = lambda fn: fn(Mock(get=Mock(return_value={})))
    runner = sweep.HeldDeadLetter(store)
    monkeypatch.setattr(sweep, 'held_candidates', lambda *a, **k: [])
    monkeypatch.setattr(sweep, 'dead_held_candidates', lambda *a, **k: [('a', {'held_expired_at': 1})])
    monkeypatch.setattr(runner.recovery, 'requeue_quarantined', lambda *a, **k: 'exhausted')
    before = transitions('held_exhausted')
    assert runner.tick(86400) == {'expired': 0, 'requeued': 0, 'exhausted': 1}
    assert transitions('held_exhausted') == before + 1


# 6. Projection expiry re-arm has a terminal stop ----------------------------------


@pytest.fixture
def projection(monkeypatch):
    from tests.unit.test_batch_pipeline_projection_release import rows, store_for

    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    monkeypatch.setenv('BATCH_HELD_DEAD_LETTER_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_HOLD_RECOVERY_ENABLED', 'true')
    return rows, store_for


@pytest.mark.parametrize('stop', ['true', 'false'])
@pytest.mark.parametrize('counter', ['true', 'false'])
def test_projection_rearm_counts_and_stops_after_max(projection, monkeypatch, stop, counter):
    """Class 6: the counter counts re-arms; only the terminal stop keeps the budget spent."""
    from database.batch_pipeline_projection_release import MAX_RELEASE_ATTEMPTS, ProjectionReleaseStore

    monkeypatch.setenv(STOP_SWITCH, stop)
    monkeypatch.setenv(sm.HELD_REDRIVE_COUNTER_SWITCH, counter)
    rows, store_for = projection
    result = ('batch_pipeline_prod_results', 'held')
    client, store = store_for(
        rows(discarded=True, held_deadline_at=1, projection_release_attempts=MAX_RELEASE_ATTEMPTS)
    )
    counted = counter == 'true'
    for rearm in range(1, sm.MAX_PROJECTION_REARMS + 2):
        entry = client.rows[result]
        # A released-then-re-held unit: a fresh, passed deadline and a spent release budget.
        entry.update(held_deadline_at=1, projection_release_attempts=MAX_RELEASE_ATTEMPTS)
        entry.pop('held_expired_reason', None)
        entry.pop('held_expired_at', None)
        release = ProjectionReleaseStore(store)
        assert release.release('held', 2.0 + rearm) is False
        assert release.expired
        entry = client.rows[result]
        if stop == 'true' and counted and rearm > sm.MAX_PROJECTION_REARMS:
            assert release.rearm_exhausted
            assert entry['projection_release_attempts'] == MAX_RELEASE_ATTEMPTS
            assert entry['held_rearm_exhausted_at'] == 2.0 + rearm
            assert entry['held_expired_rearms'] == sm.MAX_PROJECTION_REARMS
        else:
            assert not release.rearm_exhausted
            assert entry['projection_release_attempts'] == 0
            if counted:
                assert entry['held_expired_rearms'] == rearm
            else:
                assert 'held_expired_rearms' not in entry
        # The receipt and its payload are retained in every case.
        assert entry['projection_state'] == 'quarantine_held'


@pytest.mark.parametrize('rearms,emitted', [(sm.MAX_PROJECTION_REARMS - 1, 0), (sm.MAX_PROJECTION_REARMS, 1)])
def test_projection_spent_rearm_budget_is_observed_with_the_stop_off(projection, monkeypatch, rearms, emitted):
    """Review wave 3 (finding 3): ruled defaults (counter on, stop off) still report a spent budget."""
    import json
    from pathlib import Path

    from database.batch_pipeline_projection_release import MAX_RELEASE_ATTEMPTS, ProjectionReleaseStore

    monkeypatch.setenv(STOP_SWITCH, 'false')
    monkeypatch.setenv(sm.HELD_REDRIVE_COUNTER_SWITCH, 'true')
    rows, store_for = projection
    client, store = store_for(
        rows(
            discarded=True,
            held_deadline_at=1,
            projection_release_attempts=MAX_RELEASE_ATTEMPTS,
            held_expired_rearms=rearms,
        )
    )
    before = transitions('projection_rearm_budget_spent')
    release = ProjectionReleaseStore(store)
    assert release.release('held', 2.0) is False and release.expired and not release.rearm_exhausted
    assert transitions('projection_rearm_budget_spent') == before + emitted
    rules = json.loads((Path(__file__).resolve().parents[2] / 'charts/monitoring/alert-rules.json').read_text())
    exprs = [d['model'].get('expr', '') for r in rules for d in r['data']]
    assert any('projection_rearm_budget_spent' in e for e in exprs)


def test_rearm_exhausted_receipt_releases_after_stop_switch_off_and_target_restored(projection, monkeypatch):
    """Review wave 1 (finding 3): on -> exhausted -> off -> restored must release."""
    from database.batch_pipeline_projection_release import MAX_RELEASE_ATTEMPTS, ProjectionReleaseStore

    monkeypatch.setenv(STOP_SWITCH, 'true')
    rows, store_for = projection
    result = ('batch_pipeline_prod_results', 'held')
    conversation = ('users', 'synthetic-owner', 'conversations', 'rec-target')
    client, store = store_for(
        rows(
            discarded=True,
            held_deadline_at=1,
            projection_release_attempts=MAX_RELEASE_ATTEMPTS,
            held_expired_rearms=sm.MAX_PROJECTION_REARMS,
        )
    )
    release = ProjectionReleaseStore(store)
    assert release.release('held', 2.0) is False and release.rearm_exhausted
    monkeypatch.setenv(STOP_SWITCH, 'false')
    client.rows[conversation]['discarded'] = False
    assert ProjectionReleaseStore(store).release('held', 3.0) is True
    entry = client.rows[result]
    assert entry['projection_state'] == 'pending'
    assert entry.get('held_rearm_exhausted_at') is None


def test_rearm_exhausted_receipt_stays_spent_while_stop_switch_on(projection, monkeypatch):
    monkeypatch.setenv(STOP_SWITCH, 'true')  # class 6 terminal stop (default off)
    from database.batch_pipeline_projection_release import MAX_RELEASE_ATTEMPTS, ProjectionReleaseStore

    rows, store_for = projection
    conversation = ('users', 'synthetic-owner', 'conversations', 'rec-target')
    client, store = store_for(
        rows(
            discarded=True,
            held_deadline_at=1,
            projection_release_attempts=MAX_RELEASE_ATTEMPTS,
            held_expired_rearms=sm.MAX_PROJECTION_REARMS,
        )
    )
    assert ProjectionReleaseStore(store).release('held', 2.0) is False
    client.rows[conversation]['discarded'] = False
    assert ProjectionReleaseStore(store).release('held', 3.0) is False


# 4. record_pending with a present but unfinished conversation -----------------------

DAY = 86400.0
CLOCK = 100 * DAY


@pytest.fixture
def drain(monkeypatch):
    from utils.batch_pipeline import live

    monkeypatch.setenv('RECORD_DRAIN_CONCURRENCY', '1')
    clock = [CLOCK]
    monkeypatch.setattr(live.time, 'time', lambda: clock[0])
    store = MemoryStore()

    def seed(enqueued_ago):
        store.rows['jobs', 's'] = {
            'owner_id': 'synthetic-owner',
            'segment_id': 's',
            'state': 'record_pending',
            'available_at': 0,
            'enqueued_at': clock[0] - enqueued_ago,
            'audio_uri': 'gs://synthetic/record',
        }

    def run(error):
        async def admission(store, pending):
            raise error

        monkeypatch.setattr(live, 'admit_recording', admission)
        asyncio.run(live.drain_recordings(store))
        job = store.rows['jobs', 's']
        return job, job['available_at'] - clock[0]

    return live, store, seed, run, clock


def barrier(live, status, present=True):
    return live.RecordBarrierOpen(live.BARRIER_NOT_CLOSED, conversation_present=present, conversation_status=status)


def test_unfinished_conversation_redrives_weekly_then_dead_letters(drain, monkeypatch):
    monkeypatch.setenv(sm.RECORD_BARRIER_DEAD_LETTER_SWITCH, 'true')  # class 4 (default off)
    live, store, seed, run, clock = drain
    seed(15 * DAY)
    redrives = transitions('record_barrier_redrive')
    dead = transitions('record_barrier_dead_letter')
    for spent in range(1, sm.MAX_RECORD_BARRIER_REDRIVES + 1):
        job, delay = run(barrier(live, 'in_progress'))
        assert delay == sm.RECORD_BARRIER_REDRIVE_SECONDS
        assert job['barrier_redrives'] == spent and job['state'] == 'record_pending'
        clock[0] += delay
    job, delay = run(barrier(live, 'processing'))
    assert delay == sm.RECORD_BARRIER_PARK_RECHECK_SECONDS
    assert job['state'] == 'record_pending'  # Custody and erasure keep owning the row.
    assert job['barrier_dead_letter']['reason'] == sm.RECORD_BARRIER_DEAD_LETTER_REASON
    assert job['barrier_dead_letter']['redrives'] == sm.MAX_RECORD_BARRIER_REDRIVES
    assert job['audio_uri'] == 'gs://synthetic/record'
    assert transitions('record_barrier_redrive') == redrives + sm.MAX_RECORD_BARRIER_REDRIVES
    assert transitions('record_barrier_dead_letter') == dead + 1
    # Parked: not due inside the daily recheck window; a recheck never admits
    # it (test_parked_row_is_rechecked_without_admission_while_the_switch_is_on).
    assert store.due('record_pending', clock[0] + sm.RECORD_BARRIER_PARK_RECHECK_SECONDS - 1, 100) == []
    # Operator exit: one fresh budget, history retained.
    assert live.requeue_barrier_dead_letter(store, 's', clock[0])
    job = store.rows['jobs', 's']
    assert job['available_at'] == clock[0] and job['barrier_redrives'] == 0
    assert 'barrier_dead_letter' not in job and len(job['barrier_dead_letter_history']) == 1
    assert not live.requeue_barrier_dead_letter(store, 's', clock[0])


def park(live, run, clock):
    for _ in range(sm.MAX_RECORD_BARRIER_REDRIVES + 1):
        job, delay = run(barrier(live, 'in_progress'))
        clock[0] += delay
    assert job['barrier_dead_letter']
    return job


def test_parked_row_returns_to_the_ladder_after_the_switch_is_turned_off(drain, monkeypatch):
    """Review wave 1 (finding 4): park with the switch on, then roll back."""
    monkeypatch.setenv(sm.RECORD_BARRIER_DEAD_LETTER_SWITCH, 'true')  # class 4 (default off)
    live, store, seed, run, clock = drain
    seed(15 * DAY)
    park(live, run, clock)
    monkeypatch.setenv(sm.RECORD_BARRIER_DEAD_LETTER_SWITCH, 'false')
    clock[0] += sm.RECORD_BARRIER_PARK_RECHECK_SECONDS
    assert store.due('record_pending', clock[0], 100) == ['s']
    admission = Mock(side_effect=AssertionError('rollback reschedules before admitting'))
    monkeypatch.setattr(live, 'admit_recording', admission)
    asyncio.run(live.drain_recordings(store))
    job = store.rows['jobs', 's']
    assert 'barrier_dead_letter' not in job and job['barrier_dead_letter_history']
    assert job['available_at'] - clock[0] == 3600  # back on the #24863 ladder
    assert job['audio_uri'] == 'gs://synthetic/record'


def test_parked_row_is_rechecked_without_admission_while_the_switch_is_on(drain, monkeypatch):
    monkeypatch.setenv(sm.RECORD_BARRIER_DEAD_LETTER_SWITCH, 'true')  # class 4 (default off)
    live, store, seed, run, clock = drain
    seed(15 * DAY)
    parked = park(live, run, clock)
    clock[0] += sm.RECORD_BARRIER_PARK_RECHECK_SECONDS
    assert store.due('record_pending', clock[0], 100) == ['s']
    admission = Mock(side_effect=AssertionError('a parked row is not re-admitted'))
    monkeypatch.setattr(live, 'admit_recording', admission)
    asyncio.run(live.drain_recordings(store))
    job = store.rows['jobs', 's']
    assert job['barrier_dead_letter'] == parked['barrier_dead_letter']
    assert job['available_at'] - clock[0] == sm.RECORD_BARRIER_PARK_RECHECK_SECONDS


@pytest.mark.parametrize(
    'age,status,present,delay',
    [
        # A missing conversation belongs to the seven-day record_pending_repair cancel.
        (30 * DAY, None, False, 3600),
        # A completed conversation with open upload tokens belongs to seal repair.
        (30 * DAY, 'completed', True, 3600),
    ],
)
def test_other_barrier_cohorts_keep_their_existing_owner(drain, monkeypatch, age, status, present, delay):
    monkeypatch.setenv(sm.RECORD_BARRIER_DEAD_LETTER_SWITCH, 'true')  # class 4 on: still not its cohort
    live, _, seed, run, _ = drain
    seed(age)
    job, got = run(barrier(live, status, present))
    assert got == delay and 'barrier_redrives' not in job and 'barrier_dead_letter' not in job


@pytest.mark.parametrize(
    'age,redrive',
    [(sm.RECORD_BARRIER_DEAD_LETTER_AGE_SECONDS - 1, False), (sm.RECORD_BARRIER_DEAD_LETTER_AGE_SECONDS, True)],
)
def test_class_4_spends_no_redrive_before_the_14_day_boundary(drain, monkeypatch, age, redrive):
    """Review wave 3 (finding 4): class 4 on, a present unfinished row, either side of 14 days."""
    monkeypatch.setenv(sm.RECORD_BARRIER_DEAD_LETTER_SWITCH, 'true')
    live, _, seed, run, _ = drain
    seed(age)
    job, delay = run(barrier(live, 'in_progress'))
    if redrive:
        assert job['barrier_redrives'] == 1 and delay == sm.RECORD_BARRIER_REDRIVE_SECONDS
    else:
        assert 'barrier_redrives' not in job and delay == 3600
    assert 'barrier_dead_letter' not in job


def test_class_4_refuses_to_spend_budget_after_losing_the_drain_lease(drain, monkeypatch):
    """Review wave 3 (finding 1): a slow admission outlives its lease; another replica claims the row."""
    monkeypatch.setenv(sm.RECORD_BARRIER_DEAD_LETTER_SWITCH, 'true')
    live, store, seed, _, clock = drain
    seed(30 * DAY)
    store.rows['jobs', 's']['barrier_redrives'] = 2
    competing_lease = clock[0] + 5000

    async def slow_admission(store_, pending):
        # While this worker was admitting, its lease ended and another replica claimed the row.
        store.rows['jobs', 's']['available_at'] = competing_lease
        raise barrier(live, 'in_progress')

    monkeypatch.setattr(live, 'admit_recording', slow_admission)
    asyncio.run(live.drain_recordings(store))
    job = store.rows['jobs', 's']
    assert job['barrier_redrives'] == 2  # the stale worker spent nothing
    assert 'barrier_redrive_at' not in job and 'barrier_dead_letter' not in job
    assert job['available_at'] >= competing_lease  # the competing lease is kept


def test_plain_barrier_error_from_the_transactional_recheck_is_not_parked(drain):
    live, _, seed, run, _ = drain
    seed(30 * DAY)
    job, delay = run(ValueError(live.BARRIER_NOT_CLOSED))
    assert delay == 3600 and 'barrier_redrives' not in job


@pytest.mark.parametrize('switch', ['false', None])
def test_record_dead_letter_kill_switch_keeps_the_hourly_ladder(drain, monkeypatch, switch):
    live, _, seed, run, _ = drain
    if switch is not None:
        monkeypatch.setenv(sm.RECORD_BARRIER_DEAD_LETTER_SWITCH, switch)
    seed(30 * DAY)
    job, delay = run(barrier(live, 'in_progress'))
    assert delay == 3600 and 'barrier_redrives' not in job


def test_admission_precheck_reports_the_conversation_it_read(monkeypatch):
    from utils.batch_pipeline import live
    import config.batch_pipeline as batch_config

    monkeypatch.setattr(batch_config, 'require_record_protocol_ready', lambda: None)
    document = Mock()
    document.get.return_value.to_dict.return_value = {'status': 'in_progress', 'record_lane_owner': 'batch_live_v1'}
    client = Mock()
    client.collection.return_value.document.return_value.collection.return_value.document.return_value = document
    store = Mock(client=client)
    pending = {'owner_id': 'u', 'conversation_id': 'c', 'record_snapshot': {}, 'record_content_id': 'x'}
    with pytest.raises(live.RecordBarrierOpen) as raised:
        asyncio.run(live.admit_recording(store, pending, now=1.0))
    assert str(raised.value) == live.BARRIER_NOT_CLOSED
    assert isinstance(raised.value, ValueError)
    assert raised.value.conversation_present and raised.value.conversation_status == 'in_progress'


# 5. C7: assignment_held has an automatic exit, but only for a restorable target ------


@pytest.mark.parametrize('restorable', [True, False])
def test_assignment_held_releases_automatically_only_when_target_restorable(projection, monkeypatch, restorable):
    """Settles the C7 dispute: Sol is right that an automatic path exists.

    The serving release scan has an assignment leg (state=committed,
    recovery_state=held) that resets a restorable unit to pending with no
    operator intent. An unrestorable assignment hold waits: it gets no
    deadline, because projection_state 'persisted' never expires. That is
    the part of the 8.4k stock that stays operator-only.
    """
    import database.batch_pipeline_projection_release as release

    monkeypatch.setenv('BATCH_HELD_DEAD_LETTER_ENABLED', 'true')
    rows, store_for = projection
    client, store = store_for(rows(projection_state='persisted', discarded=not restorable))
    job = client.rows[('batch_pipeline_prod_jobs', 'held')]
    job['state'] = 'committed'
    assert not any(job.get(key) for key in ('speech_redrive', 'terminal_disposition', 'silence_disposition'))
    monkeypatch.setattr(release, 'held_page_ids', lambda *a: [])
    monkeypatch.setattr(release, 'assignment_held_page_ids', lambda *a: ['held'])
    for now in (500.0, 500.0 + 30 * DAY):
        counts, _ = release.release_scan_pass(store, limit=2, after_id=None, now=now)
        if restorable:
            break
        assert counts['released'] == 0 and counts['waiting'] == 1 and counts['expired'] == 0
    result = client.rows[('batch_pipeline_prod_results', 'held')]
    if restorable:
        assert counts['released'] == 1
        assert result['projection_state'] == 'pending'
        assert client.rows[('batch_pipeline_prod_jobs', 'held')]['recovery_state'] is None
    else:
        assert result['projection_state'] == 'persisted'
        assert 'held_deadline_at' not in result


def test_unrestorable_assignment_hold_escalates_after_its_deadline_and_keeps_its_obligation(projection, monkeypatch):
    """Review wave 1 (finding 5): every non-terminal state has an owner and a deadline."""
    monkeypatch.setenv(sm.ASSIGNMENT_HOLD_ESCALATION_SWITCH, 'true')  # class 5 (default off)
    import database.batch_pipeline_projection_release as release

    monkeypatch.setenv('BATCH_HELD_DEAD_LETTER_ENABLED', 'true')
    rows, store_for = projection
    client, store = store_for(rows(projection_state='persisted', discarded=True, payload={'words': ['kept']}))
    job_key, result_key = ('batch_pipeline_prod_jobs', 'held'), ('batch_pipeline_prod_results', 'held')
    client.rows[job_key]['state'] = 'committed'
    monkeypatch.setattr(release, 'held_page_ids', lambda *a: [])
    monkeypatch.setattr(release, 'assignment_held_page_ids', lambda *a: ['held'])
    release.release_scan_pass(store, limit=2, after_id=None, now=500.0)
    entry = client.rows[result_key]
    assert entry['assignment_hold_deadline_at'] == 500.0 + sm.ASSIGNMENT_HOLD_DEADLINE_SECONDS
    assert 'assignment_hold_escalated_at' not in entry
    before = transitions('assignment_hold_escalated')
    later = 501.0 + sm.ASSIGNMENT_HOLD_DEADLINE_SECONDS
    release.release_scan_pass(store, limit=2, after_id=None, now=later)
    entry, job = client.rows[result_key], client.rows[job_key]
    assert entry['assignment_hold_escalated_at'] == later
    assert entry['assignment_hold_escalation_reason'] == 'target_unrestorable'
    # A parking transition: obligation, receipt, payload and audio all retained.
    assert entry['projection_state'] == 'persisted' and entry['payload'] == {'words': ['kept']}
    assert entry['projection']['state'] == 'quarantined'
    assert job['recovery_state'] == 'held' and job['audio_uri'] == 'gs://synthetic/audio'
    assert transitions('assignment_hold_escalated') == before + 1
    # Idempotent: a later pass does not re-escalate or re-count.
    release.release_scan_pass(store, limit=2, after_id=None, now=later + 10)
    assert client.rows[result_key]['assignment_hold_escalated_at'] == later
    assert transitions('assignment_hold_escalated') == before + 1
    # A restored target still releases an escalated hold automatically.
    target = ('users', 'synthetic-owner', 'conversations', 'rec-target')
    client.rows[target]['discarded'] = False
    counts, _ = release.release_scan_pass(store, limit=2, after_id=None, now=later + 20)
    assert counts['released'] == 1
    # Review wave 2 (finding 3): release clears the active escalation, so a new
    # hold on the same unit gets a fresh deadline instead of the old marker.
    released = client.rows[result_key]
    assert released.get('assignment_hold_escalated_at') is None
    assert released.get('assignment_hold_deadline_at') is None
    assert released['assignment_hold_escalation_history'][-1]['escalated_at'] == later
    rehold = later + 100
    released.update(
        projection_state='persisted',
        projection={'state': 'quarantined', 'disposition': 'ambiguous_generation', 'quarantine_version': 1},
    )
    client.rows[job_key]['recovery_state'] = 'held'
    client.rows[target]['discarded'] = True
    release.release_scan_pass(store, limit=2, after_id=None, now=rehold)
    entry = client.rows[result_key]
    assert entry['assignment_hold_deadline_at'] == rehold + sm.ASSIGNMENT_HOLD_DEADLINE_SECONDS
    assert entry.get('assignment_hold_escalated_at') is None


@pytest.mark.parametrize('switch', ['false', None])
def test_assignment_hold_escalation_kill_switch_writes_nothing(projection, monkeypatch, switch):
    import database.batch_pipeline_projection_release as release

    if switch is not None:
        monkeypatch.setenv(sm.ASSIGNMENT_HOLD_ESCALATION_SWITCH, switch)
    rows, store_for = projection
    client, store = store_for(rows(projection_state='persisted', discarded=True))
    client.rows[('batch_pipeline_prod_jobs', 'held')]['state'] = 'committed'
    monkeypatch.setattr(release, 'held_page_ids', lambda *a: [])
    monkeypatch.setattr(release, 'assignment_held_page_ids', lambda *a: ['held'])
    release.release_scan_pass(store, limit=2, after_id=None, now=500.0)
    assert 'assignment_hold_deadline_at' not in client.rows[('batch_pipeline_prod_results', 'held')]
