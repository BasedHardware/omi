"""Backlog state machine (core): each class runs with its switch on and off.

Classes from the 2026-11-07 backlog root-cause review:

1. the retry cap enforces for every uid only with CAPTURE_RETRY_CAP_ENFORCED on;
2. a running sync lease expiry carries dispatch_attempt instead of resetting it;
3. a held/dead-letter requeue grants a fresh attempt budget;
6. (counter) held re-drives are counted and a spent budget is reported.
"""

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


def decisions(check, outcome):
    from utils.capture.retry_cap import DECISIONS

    return DECISIONS.labels(check, outcome)._value.get()


@pytest.mark.parametrize('class1', [None, 'false', 'true'])
def test_unenforced_running_cap_is_observed_and_alertable(db, monkeypatch, class1):
    """Custody review (luna-core-2): class 1 unset and CAPTURE_COVERAGE_MODE off.

    A running lease that expires at the cap is redriven, never terminalized,
    and every such expiry records sync_running_cap_observed (alert
    omi-backlog-sync-running-cap-unenforced) plus a would_quarantine decision.
    Class 1 on is the control: the same expiry finalizes and is not "observed".
    """
    if class1 is not None:
        monkeypatch.setenv(sm.RETRY_CAP_SWITCH, class1)
    account, expired = at_cap_running_owner(db, monkeypatch)
    failure = finalizer_mocks(monkeypatch)
    dispatch = Mock()
    monkeypatch.setattr(uid_sequencer, '_dispatch', dispatch)
    observed = transitions('sync_running_cap_observed')
    would = decisions('sequencer_running', 'would_quarantine')
    outcome = uid_sequencer.reconcile_uid(account, registry.get_owner(account), now=expired)
    if class1 == 'true':
        assert outcome == 'dispatch_retry_cap_reached'
        failure.assert_called_once()
        assert transitions('sync_running_cap_observed') == observed
        return
    assert outcome == 'lease_expired'
    dispatch.assert_called_once()
    failure.assert_not_called()
    owner = registry.get_owner(account)
    assert owner['active_job_id'] == 'crashy' and owner['running_expiries'] == 2
    assert transitions('sync_running_cap_observed') == observed + 1
    assert decisions('sequencer_running', 'would_quarantine') == would + 1
    # Over the cap: the next expiry is observed again, still never terminalized.
    replacement_epoch = owner['active_epoch']
    assert registry.begin_job(account, 'crashy', replacement_epoch, now=expired)
    again = expired + timedelta(seconds=registry.LEASE_SECONDS + 1)
    assert uid_sequencer.reconcile_uid(account, registry.get_owner(account), now=again) == 'lease_expired'
    failure.assert_not_called()
    assert transitions('sync_running_cap_observed') == observed + 2


@pytest.mark.parametrize('case', ['below_cap', 'carry_off'])
def test_running_cap_observation_needs_a_carried_count_at_the_cap(db, monkeypatch, case):
    # carry_off: a cap of 1 is reached on the first expiry, but with class 2 off
    # there is no carried count to observe (main's reset).
    if case == 'carry_off':
        monkeypatch.setenv(sm.SYNC_ATTEMPT_CARRY_SWITCH, 'false')
    account, epoch = running_owner(db, monkeypatch, attempts='1' if case == 'carry_off' else '5')
    assert registry.begin_job(account, 'crashy', epoch, now=NOW)
    expired = NOW + timedelta(seconds=registry.LEASE_SECONDS + 1)
    finalizer_mocks(monkeypatch)
    monkeypatch.setattr(uid_sequencer, '_dispatch', Mock())
    observed = transitions('sync_running_cap_observed')
    assert uid_sequencer.reconcile_uid(account, registry.get_owner(account), now=expired) == 'lease_expired'
    assert transitions('sync_running_cap_observed') == observed


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


def operator_redrive_app(store, monkeypatch):
    from types import SimpleNamespace

    from fastapi import FastAPI
    from routers import batch_pipeline as router

    monkeypatch.setattr(
        router, 'serving_for_stage', lambda stage: SimpleNamespace(store=store, queue=lambda: Scheduler(store))
    )
    app = FastAPI()
    app.include_router(router.router)
    app.dependency_overrides[router.verify_worker] = lambda: None
    return app


@pytest.mark.parametrize('counter', ['true', 'false'])
@pytest.mark.parametrize('budget', ['true', 'false'])
@pytest.mark.parametrize('prior', [0, sm.MAX_HELD_REDRIVES])
def test_operator_redrive_dead_route_keeps_the_switched_accounting(setup, monkeypatch, counter, budget, prior):
    """Custody review (luna-core-1, luna-core-2): /redrive-dead on a held_expired row.

    The operator route must count the re-drive (class 6), reset attempt
    (class 3) and report a spent budget after commit, like the nightly and
    poll re-drives. Each switch off keeps main's behavior for its field.
    """
    from fastapi.testclient import TestClient

    monkeypatch.setenv(sm.HELD_REDRIVE_COUNTER_SWITCH, counter)
    monkeypatch.setenv(sm.HELD_REDRIVE_BUDGET_SWITCH, budget)
    monkeypatch.setenv('BATCH_HELD_DEAD_LETTER_ENABLED', 'false')
    client, store, _, _, _, _ = setup
    control_for(client)
    held_dead(bad(client), attempt=5)
    if prior:
        bad(client)['held_redrives'] = prior
    before = transitions('held_redrive_budget_spent')
    app = operator_redrive_app(store, monkeypatch)
    with TestClient(app) as api:
        assert api.post('/v2/batch-pipeline/redrive-dead', json={'stage': 'prod', 'segment_id': 'bad'}).json() == {
            'accepted': True
        }
        job = deepcopy(bad(client))
        # Idempotent: a second call finds no dead row and changes nothing.
        assert api.post('/v2/batch-pipeline/redrive-dead', json={'stage': 'prod', 'segment_id': 'bad'}).json() == {
            'accepted': False
        }
    app.dependency_overrides.clear()
    assert bad(client) == job
    assert job['state'] == 'ready' and job['audio_uri'] == 'gs://synthetic/audio'
    if counter == 'true':
        assert job['held_redrives'] == prior + 1
    else:
        assert job.get('held_redrives', 0) == prior
    if budget == 'true':
        assert job['attempt'] == 0 and job['held_redrive_last_attempt'] == 5
    else:
        assert job['attempt'] == 5 and 'held_redrive_last_attempt' not in job
    spent = counter == 'true' and prior >= sm.MAX_HELD_REDRIVES
    assert transitions('held_redrive_budget_spent') == before + (1 if spent else 0)


def test_operator_redrive_of_a_plain_dead_row_is_not_held_accounting(monkeypatch):
    monkeypatch.setenv(sm.HELD_REDRIVE_COUNTER_SWITCH, 'true')
    monkeypatch.setenv(sm.HELD_REDRIVE_BUDGET_SWITCH, 'true')
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('plain', owner=uuid4().hex), 0)
    store.rows['jobs', 'plain'].update(state='dead', merge_pending=True, attempt=4)
    assert queue.redrive_dead('plain', 10)
    job = store.rows['jobs', 'plain']
    assert job['state'] == 'ready' and job['attempt'] == 4
    assert 'held_redrives' not in job and 'held_redrive_last_attempt' not in job


def backlog_alert(uid):
    import json
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / 'charts/monitoring/alerts/backlog-state-machine.json'
    return next(rule for rule in json.loads(path.read_text(encoding='utf-8')) if rule['uid'] == uid)


def alert_backtest():
    import importlib.util
    from pathlib import Path

    script = Path(__file__).resolve().parents[2] / 'scripts/alert_backtest.py'
    spec = importlib.util.spec_from_file_location('alert_backtest', script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def nightly_counter_samples(monkeypatch, nights, prior):
    """Run the real nightly pass over one held recording; return (time, counter) after each pass.

    The recording is re-driven on each listed night and starts with ``prior``
    held re-drives. A spent budget is observed by the pass's scan.
    """
    from utils.batch_pipeline import held_dead_letter as sweep

    store = Mock()
    store.run.side_effect = lambda fn: fn(Mock(get=Mock(return_value={})))
    runner = sweep.HeldDeadLetter(store)
    job = {'held_expired_at': 1, 'held_redrives': prior}
    monkeypatch.setattr(sweep, 'held_candidates', lambda *a, **k: [])
    monkeypatch.setattr(sweep, 'dead_held_candidates', lambda *a, **k: [('one-recording', dict(job))])

    def requeue(*_, **__):
        job['held_redrives'] += 1  # the counter's own increment on a committed requeue
        return True

    monkeypatch.setattr(runner.recovery, 'requeue_quarantined', requeue)
    base = transitions('held_redrive_budget_spent')
    samples = []
    for night in nights:
        now = night * 86400 + 60
        runner.tick(now)
        samples.append((now, transitions('held_redrive_budget_spent') - base))
    return samples


def alert_episodes(rule, samples, end_day):
    """Evaluate the rule hourly: A is PromQL increase(counter[window]) from the sampled counter."""
    import re

    b = alert_backtest()
    expr = rule['data'][0]['model']['expr']
    window = int(re.search(r'\[(\d+)d\]', expr).group(1)) * 86400

    def counter_at(t):
        return max([value for at, value in samples if at <= t], default=0)

    step = 3600
    frames = [
        (t, b.evaluate(rule, {'A': {(): [counter_at(t) - counter_at(t - window)]}}))
        for t in range(0, end_day * 86400, step)
    ]
    return b.episodes(rule, frames, 0, end_day * 86400 - step, step)


@pytest.mark.parametrize(
    'prior,nights,fires',
    [
        # A recording that already spent its budget, re-driven on consecutive nightly passes.
        (sm.MAX_HELD_REDRIVES, [1, 2], True),
        # The real loop: re-driven once per cycle (7-day held window, then the next night).
        (sm.MAX_HELD_REDRIVES, [1, 9, 17], True),
        # Below the budget: re-drives are not a spent-budget signal.
        (0, [1, 2, 3], False),
    ],
)
def test_one_looping_held_recording_fires_the_unit_alert(monkeypatch, prior, nights, fires):
    """Custody review: one spent-budget unit must alert; the 64/h volume rule never sees it."""
    monkeypatch.setenv(sm.HELD_REDRIVE_COUNTER_SWITCH, 'true')
    samples = nightly_counter_samples(monkeypatch, nights, prior)
    looping = alert_episodes(backlog_alert('omi-backlog-held-redrive-unit-looping'), samples, 20)
    assert (looping['episodes'] > 0) is fires
    if fires:
        # Stays firing while the unit keeps looping (no gap between cycles).
        assert looping['episodes'] == 1
    # The volume rule stays quiet for a single recording (why the unit rule exists).
    assert alert_episodes(backlog_alert('omi-backlog-held-redrive-budget-spent'), samples, 20)['episodes'] == 0


@pytest.mark.parametrize('counter', ['true', 'false'])
@pytest.mark.parametrize('prior', [0, sm.MAX_HELD_REDRIVES])
def test_operator_requeue_quarantined_route_reports_a_spent_budget(setup, monkeypatch, counter, prior):
    """Custody review: /requeue-quarantined counts and signals like /redrive-dead, after commit."""
    from fastapi.testclient import TestClient

    monkeypatch.setenv(sm.HELD_REDRIVE_COUNTER_SWITCH, counter)
    monkeypatch.setenv('BATCH_HELD_DEAD_LETTER_ENABLED', 'false')
    client, store, _, _, _, _ = setup
    control_for(client)
    held_dead(bad(client), attempt=5)
    if prior:
        bad(client)['held_redrives'] = prior
    before = transitions('held_redrive_budget_spent')
    app = operator_redrive_app(store, monkeypatch)
    path = '/v2/batch-pipeline/requeue-quarantined'
    with TestClient(app) as api:
        assert api.post(path, json={'stage': 'prod', 'segment_id': 'bad'}).json() == {'accepted': True}
        assert api.post(path, json={'stage': 'prod', 'segment_id': 'bad'}).json() == {'accepted': False}
    app.dependency_overrides.clear()
    job = bad(client)
    assert job['state'] == 'ready'
    assert job.get('held_redrives', 0) == prior + (1 if counter == 'true' else 0)
    spent = counter == 'true' and prior >= sm.MAX_HELD_REDRIVES
    assert transitions('held_redrive_budget_spent') == before + (1 if spent else 0)


def test_nightly_requeue_is_not_double_counted(setup, monkeypatch):
    """The nightly pass observes in its scan; its requeue call must not signal again."""
    monkeypatch.setenv(sm.HELD_REDRIVE_COUNTER_SWITCH, 'true')
    client, store, _, _, _, _ = setup
    control_for(client)
    held_dead(bad(client), attempt=5)
    bad(client)['held_redrives'] = sm.MAX_HELD_REDRIVES
    before = transitions('held_redrive_budget_spent')
    assert RecoveryStore(store).requeue_quarantined('bad', 30, dead_before=86400) is True
    assert transitions('held_redrive_budget_spent') == before
