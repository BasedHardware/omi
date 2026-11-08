"""Backlog state machine (core): each class runs with its switch on and off.

Classes from the 2026-11-07 backlog root-cause review:

1. the retry cap enforces for every uid only with CAPTURE_RETRY_CAP_ENFORCED on;
2. a running sync lease expiry carries dispatch_attempt instead of resetting it;
3. a held/dead-letter requeue grants a fresh attempt budget;
6. (counter) held re-drives are counted and a spent budget is reported.
"""

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
from utils.batch_pipeline.scheduler import Scheduler
from utils.sync import uid_sequencer

SWITCHES = (
    sm.RETRY_CAP_SWITCH,
    sm.SYNC_ATTEMPT_CARRY_SWITCH,
    sm.HELD_REDRIVE_COUNTER_SWITCH,
    sm.HELD_REDRIVE_BUDGET_SWITCH,
)


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
    from utils import backlog_metrics

    return backlog_metrics.TERMINAL_TRANSITIONS.labels(name)._value.get()


# Defaults by the lead2 rule (64b2fa): ON only where a class just cuts wasted
# work or retries; OFF where it changes custody, settle or expiry semantics.
EXPECTED_DEFAULTS = {
    sm.RETRY_CAP_SWITCH: False,
    sm.SYNC_ATTEMPT_CARRY_SWITCH: True,
    sm.HELD_REDRIVE_COUNTER_SWITCH: True,
    sm.HELD_REDRIVE_BUDGET_SWITCH: False,
}
READERS = {
    sm.RETRY_CAP_SWITCH: sm.retry_cap_enforced,
    sm.SYNC_ATTEMPT_CARRY_SWITCH: sm.sync_attempt_carry_enabled,
    sm.HELD_REDRIVE_COUNTER_SWITCH: sm.held_redrive_counter_enabled,
    sm.HELD_REDRIVE_BUDGET_SWITCH: sm.held_redrive_budget_enabled,
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


@pytest.mark.parametrize('class1', ['false', None])
def test_crash_carry_does_not_spend_the_legacy_dispatch_budget_while_class_1_is_off(db, monkeypatch, class1):
    """Review wave 5 (finding 1): crash -> redrive -> dispatch timeout in a serve cohort, max 2.

    Main reset dispatch_attempt on a running expiry, so the next dispatch
    deadline started a fresh legacy budget. The carried task identity must not
    spend that budget: the delayed replacement is redriven, not failed.
    """
    if class1 is not None:
        monkeypatch.setenv(sm.RETRY_CAP_SWITCH, class1)
    monkeypatch.setenv('CAPTURE_COVERAGE_MODE', 'serve')
    account, epoch = running_owner(db, monkeypatch, attempts='2')
    replacement, expired = crash_once(account, epoch, NOW)
    owner = registry.get_owner(account)
    assert owner['active_state'] == 'dispatching' and owner['dispatch_attempt'] == 1  # carried identity
    failure = finalizer_mocks(monkeypatch)
    dispatch = Mock()
    monkeypatch.setattr(uid_sequencer, '_dispatch', dispatch)
    deadline = expired + timedelta(seconds=registry.DISPATCH_RETRY_SECONDS + 1)
    outcome = uid_sequencer.reconcile_uid(account, registry.get_owner(account), now=deadline)
    assert outcome != 'dispatch_retry_cap_reached'
    failure.assert_not_called()
    dispatch.assert_called_once()
    owner = registry.get_owner(account)
    assert owner['active_job_id'] == 'crashy' and owner['dispatch_attempt'] == 2


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


# 6. Held re-drive counter (BATCH_HELD_REDRIVE_COUNTER_ENABLED, default ON) ----------


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


def test_repeated_poll_redrives_report_a_spent_budget(monkeypatch):
    """Review wave 4 (finding 2): poll re-drives emit the same spent-budget signal as the nightly scan."""
    from tests.unit.test_batch_pipeline_intake import proposal, submit
    from utils.batch_pipeline.intake import durable_status

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


# 3. Held requeue budget reset (BATCH_HELD_REDRIVE_BUDGET_ENABLED, default OFF) ------


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


@pytest.mark.parametrize('counter', ['true', 'false'])
@pytest.mark.parametrize('budget', ['true', 'false'])
def test_client_poll_redrive_keeps_the_nightly_accounting(monkeypatch, counter, budget):
    """Review wave 3 (finding 2): a poll re-drive is counted and reset like the nightly one."""
    from tests.unit.test_batch_pipeline_intake import proposal, submit
    from utils.batch_pipeline.intake import durable_status

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
