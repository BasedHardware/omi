"""Backlog state machine (core): each class runs with its switch on and off.

Classes from the 2026-11-07 backlog root-cause review:

1. the batch lease-expiry retry cap enforces for every uid only with
   CAPTURE_RETRY_CAP_ENFORCED on (the sync path is main's, unchanged);
3. a held/dead-letter requeue grants a fresh attempt budget;
6. (counter) held re-drives are counted and a spent budget is reported.
"""

from copy import deepcopy
from unittest.mock import Mock
from uuid import uuid4

import pytest

from config import backlog_state_machine as sm
from database.batch_pipeline_quarantine_recovery import RecoveryStore
from tests.unit.test_batch_pipeline_quarantine_recovery import setup  # noqa: F401
from tests.unit.test_batch_pipeline_scheduler import MemoryStore, item
from utils.batch_pipeline.scheduler import Scheduler

SWITCHES = (
    sm.RETRY_CAP_SWITCH,
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
    sm.HELD_REDRIVE_COUNTER_SWITCH: True,
    sm.HELD_REDRIVE_BUDGET_SWITCH: False,
}
READERS = {
    sm.RETRY_CAP_SWITCH: sm.retry_cap_enforced,
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
    decision = retry_cap(uuid4().hex, 5, 5, enforce=True)
    assert decision.reached and decision.serving is serving
    monkeypatch.setenv('CAPTURE_COVERAGE_MODE', 'off')
    decision = retry_cap(uuid4().hex, 5, 5, enforce=True)
    # Coverage mode off no longer disables the cap; only the cap's own switch does.
    assert (decision is not None) is serving


@pytest.mark.parametrize('switch', ['true', None, 'false'])
@pytest.mark.parametrize('coverage', ['off', 'shadow'])
def test_class_1_never_changes_the_sync_dispatch_cap(monkeypatch, switch, coverage):
    """Class 2 and the sync budget-deferral chain are not in core: main's sync cap is unchanged.

    The sync dispatch cap keeps the CAPTURE_COVERAGE_MODE cohort decision with
    class 1 on or off: never served outside the cohort, never on with coverage off.
    """
    from utils.sync import retry_hygiene

    if switch is not None:
        monkeypatch.setenv(sm.RETRY_CAP_SWITCH, switch)
    monkeypatch.setenv('CAPTURE_COVERAGE_MODE', coverage)
    monkeypatch.setenv('SYNC_TASKS_MAX_ATTEMPTS', '2')
    decision = retry_hygiene.dispatch_cap(uuid4().hex, {'dispatch_attempt': 5})
    if coverage == 'off':
        assert decision is None
    else:
        assert decision.reached and not decision.serving


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
def test_nightly_pass_reports_a_spent_budget_only_with_the_counter_on(setup, monkeypatch, switch):
    from utils.batch_pipeline import held_dead_letter as sweep

    if switch is not None:
        monkeypatch.setenv(sm.HELD_REDRIVE_COUNTER_SWITCH, switch)
    client, store, _, _, _, _ = setup
    control_for(client)
    held_dead(bad(client), expired_at=1)
    bad(client)['held_redrives'] = sm.MAX_HELD_REDRIVES
    runner = sweep.HeldDeadLetter(store)
    spent = deepcopy(bad(client))
    monkeypatch.setattr(sweep, 'held_candidates', lambda *a, **k: [])
    monkeypatch.setattr(sweep, 'dead_held_candidates', lambda *a, **k: [('bad', spent)])
    before = transitions('held_redrive_budget_spent')
    assert runner.tick(86400)['requeued'] == 1
    assert transitions('held_redrive_budget_spent') == before + (0 if switch == 'false' else 1)
    # Replaying the stale page cannot requeue the now-ready row or emit again.
    assert runner.tick(172800)['requeued'] == 0
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
    # Class 3 resets only where the retry cap enforces for the owner (class 1 on).
    monkeypatch.setenv(sm.RETRY_CAP_SWITCH, 'true')
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
    # Class 3 resets only where the retry cap enforces for the owner (class 1 on).
    monkeypatch.setenv(sm.RETRY_CAP_SWITCH, 'true')
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
    # Class 3 takes effect only with the counter on (bounded and alerted).
    assert job['attempt'] == (0 if budget == 'true' and counter == 'true' else 5)


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
    # Class 3 resets only where the retry cap enforces for the owner (class 1 on).
    monkeypatch.setenv(sm.RETRY_CAP_SWITCH, 'true')
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
    # Class 3 takes effect only with the counter on and an unspent budget.
    if budget == 'true' and counter == 'true' and prior < sm.MAX_HELD_REDRIVES:
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


def nightly_counter_samples(setup, monkeypatch, nights, prior):
    """Run the real nightly pass over one held recording; return (time, counter) after each pass.

    The recording is re-driven on each listed night and starts with ``prior``
    held re-drives. A spent budget is reported after the recovery transaction.
    """
    from utils.batch_pipeline import held_dead_letter as sweep

    client, store, _, _, _, _ = setup
    control_for(client)
    rows = deepcopy(client.rows)
    runner = sweep.HeldDeadLetter(store)
    monkeypatch.setattr(sweep, 'held_candidates', lambda *a, **k: [])
    monkeypatch.setattr(sweep, 'dead_held_candidates', lambda *a, **k: [('bad', deepcopy(bad(client)))])
    base = transitions('held_redrive_budget_spent')
    samples = []
    for night in nights:
        now = night * 86400 + 60
        # Model the next held cycle with no leftover runnable queue entries.
        client.rows.clear()
        client.rows.update(deepcopy(rows))
        held_dead(bad(client), expired_at=(night - 1) * 86400)
        bad(client)['held_redrives'] = prior
        assert runner.tick(now)['requeued'] == 1
        prior = bad(client)['held_redrives']
        samples.append((now, transitions('held_redrive_budget_spent') - base))
    return samples


def alert_episodes(rule, samples, end_day):
    """Evaluate the rule hourly: A is PromQL increase(counter[window]) from the sampled counter."""
    import re

    b = alert_backtest()
    expr = rule['data'][0]['model']['expr']
    amount, unit = re.search(r'\[(\d+)([hd])\]', expr).groups()
    window = int(amount) * (86400 if unit == 'd' else 3600)

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
def test_one_looping_held_recording_fires_the_unit_alert(setup, monkeypatch, prior, nights, fires):
    """Custody review: one spent-budget unit must alert; the 64/h volume rule never sees it."""
    monkeypatch.setenv(sm.HELD_REDRIVE_COUNTER_SWITCH, 'true')
    samples = nightly_counter_samples(setup, monkeypatch, nights, prior)
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


# Custody review on 53a692de1d1d -------------------------------------------------


def held_cycles(client, store, cycles, max_attempts=3):
    """Nightly loop: re-drive a held_expired unit, fail every attempt, expire, repeat.

    Returns how many re-drives granted a fresh attempt budget.
    """
    fresh = 0
    for night in range(1, cycles + 1):
        # Every attempt the previous re-drive granted failed; the unit expired again.
        held_dead(bad(client), attempt=max_attempts, expired_at=night * 86400 - 10)
        assert RecoveryStore(store).requeue_quarantined('bad', night * 86400 + 60, dead_before=night * 86400) is True
        fresh += bad(client)['attempt'] == 0
    return fresh


@pytest.mark.parametrize(
    'budget,counter,expected_fresh',
    [
        ('true', 'false', 0),  # no count, no alert: the reset must not take effect
        ('true', 'true', sm.MAX_HELD_REDRIVES),  # stop is excluded from core: bounded by the counter
        (None, None, 0),  # defaults: budget off, counter on
    ],
)
def test_held_budget_reset_is_bounded_and_alerted(setup, monkeypatch, budget, counter, expected_fresh):
    """B (luna-core-1, luna-core-2): class 3 never sustains an unbounded fresh-budget loop.

    The reset takes effect only with the class 6 counter on and only while the
    unit's re-drive budget is unspent; after that the unit keeps main's
    retained held loop and the spent-budget signal (unit-looping alert).
    """
    # Class 3 resets only where the retry cap enforces for the owner (class 1 on).
    monkeypatch.setenv(sm.RETRY_CAP_SWITCH, 'true')
    from utils.batch_pipeline.scheduler import held_redrive_budget_spent

    if budget is not None:
        monkeypatch.setenv(sm.HELD_REDRIVE_BUDGET_SWITCH, budget)
    if counter is not None:
        monkeypatch.setenv(sm.HELD_REDRIVE_COUNTER_SWITCH, counter)
    client, store, _, _, _, _ = setup
    control_for(client)
    fresh = held_cycles(client, store, cycles=10)
    assert fresh == expected_fresh
    job = bad(client)
    assert job['audio_uri'] == 'gs://synthetic/audio'  # retained
    if counter != 'false':
        assert job['held_redrives'] == 10
        assert held_redrive_budget_spent(job)  # committed re-drives report it: alerted


@pytest.mark.parametrize('name', sorted(EXPECTED_DEFAULTS))
@pytest.mark.parametrize('raw', ['TRUE', 'True', ' true', 'true ', '1', 'yes', 'on', ''])
def test_backlog_switches_enable_only_on_exact_true(monkeypatch, name, raw):
    """C (luna-core-2): only the exact value true enables; anything else set is off."""
    monkeypatch.setenv(name, raw)
    assert READERS[name]() is False
    monkeypatch.setenv(name, 'true')
    assert READERS[name]() is True
    monkeypatch.delenv(name)
    assert READERS[name]() is EXPECTED_DEFAULTS[name]


# Custody review on da4132e093f2 -------------------------------------------------


@pytest.mark.parametrize(
    'class1,coverage,reset',
    [
        (None, None, False),  # class 1 off (default), owner outside any served cohort: main's behavior
        ('false', 'shadow', False),  # explicit off, shadow cohort: still not enforced for this owner
        ('true', None, True),  # control: class 1 enforces for every owner
        (None, 'serve', True),  # control: the owner is in the served CAPTURE_COVERAGE_MODE cohort
    ],
)
def test_class_3_reset_only_where_the_retry_cap_enforces_for_the_owner(monkeypatch, class1, coverage, reset):
    """luna-core-5-1: class 3 and the counter on; repeated lease expiries after a re-drive.

    Where the cap does not enforce for the owner, lease expiries only defer, so
    a fresh budget would keep the unit runnable without bound and no alert
    would see it. The reset is then a no-op (main's behavior); the counter
    still counts. Where the cap enforces, the reset grants one real attempt.
    """
    monkeypatch.setenv(sm.HELD_REDRIVE_BUDGET_SWITCH, 'true')
    monkeypatch.setenv(sm.HELD_REDRIVE_COUNTER_SWITCH, 'true')
    if class1 is not None:
        monkeypatch.setenv(sm.RETRY_CAP_SWITCH, class1)
    if coverage is not None:
        monkeypatch.setenv('CAPTURE_COVERAGE_MODE', coverage)
    monkeypatch.setenv('BATCH_PIPELINE_MAX_ATTEMPTS', '2')
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('looping', owner=uuid4().hex), 0)
    queue.pull(0)
    job = store.rows['jobs', 'looping']
    # A held unit at its cap (as a worker failure leaves it), then re-driven.
    job.update(
        state='quarantined',
        quarantine_reason='worker_failed',
        recovery_state='held',
        attempt=2,
        token='',
        lease_until=0,
        merge_pending=False,
    )
    assert store.run(lambda tx: Scheduler.requeue_quarantined_in_transaction(tx, tx.get('jobs', 'looping'), 5000))
    job = store.rows['jobs', 'looping']
    assert job['held_redrives'] == 1  # the class 6 counter is unchanged either way
    if reset:
        assert job['attempt'] == 0 and job['held_redrive_last_attempt'] == 2
    else:
        assert job['attempt'] == 2 and 'held_redrive_last_attempt' not in job
    # Repeated lease expiries: with the cap enforced the unit is held again at
    # the cap; without it, main's behavior (defer, stay runnable) continues
    # from the cap, never from a fresh budget.
    attempts = []
    for n in range(3):
        now = 6000 + n * 1000
        queue.recover(now)
        leases = queue.pull(now)
        if not leases:
            break
        attempts.append(leases[0].attempt)
        queue.recover(now + 121)
    if reset:
        assert attempts[0] == 1
    else:
        assert attempts and attempts[0] == 3  # continues from the cap: no fresh budget


def test_class_3_on_to_off_keeps_existing_grants_and_stops_new_resets(monkeypatch):
    """Coordinator ruling 13:07Z (option 2): rollback semantics of class 3.

    Switching class 3 OFF stops new budget resets. Existing grants persist
    until their unit runs or finishes. Each grant is capped at MAX_ATTEMPTS.
    """
    monkeypatch.setenv(sm.HELD_REDRIVE_BUDGET_SWITCH, 'true')
    monkeypatch.setenv(sm.HELD_REDRIVE_COUNTER_SWITCH, 'true')
    monkeypatch.setenv(sm.RETRY_CAP_SWITCH, 'true')
    monkeypatch.setenv('BATCH_PIPELINE_MAX_ATTEMPTS', '2')
    store = MemoryStore()
    queue = Scheduler(store)
    queue.enqueue(item('granted', owner=uuid4().hex), 0)
    queue.pull(0)
    held = dict(
        state='quarantined',
        quarantine_reason='worker_failed',
        recovery_state='held',
        attempt=2,
        token='',
        lease_until=0,
        merge_pending=False,
    )
    store.rows['jobs', 'granted'].update(held)

    def redrive(now):
        assert store.run(lambda tx: Scheduler.requeue_quarantined_in_transaction(tx, tx.get('jobs', 'granted'), now))
        return store.rows['jobs', 'granted']

    # Class 3 ON: the re-drive grants a fresh budget.
    job = redrive(5000)
    assert job['attempt'] == 0 and job['held_redrive_last_attempt'] == 2 and job['held_redrives'] == 1

    # Class 3 switched OFF: the existing grant is not clawed back.
    monkeypatch.setenv(sm.HELD_REDRIVE_BUDGET_SWITCH, 'false')
    assert store.rows['jobs', 'granted']['attempt'] == 0

    # The grant runs, capped at MAX_ATTEMPTS: lease expiries until the cap holds it.
    attempts = []
    for n in range(4):
        now = 6000 + n * 1000
        queue.recover(now)
        leases = queue.pull(now)
        if not leases:
            break
        attempts.append(leases[0].attempt)
        queue.recover(now + 121)
    assert attempts == [1, 2]
    job = store.rows['jobs', 'granted']
    assert job['state'] == 'quarantined' and job['attempt'] == 2

    # A later re-drive while OFF gets no new reset: attempt stays at the cap.
    job.update(held)
    job = redrive(20000)
    assert job['attempt'] == 2 and job['held_redrives'] == 2
    assert job['held_redrive_last_attempt'] == 2  # the old grant's record, not a new one


def test_single_unit_looping_alert_routes_unmuted_and_is_on_the_reviewed_import_list():
    """Coordinator ruling 15:48Z: the single-unit loop must notify someone.

    One looping unit stays below the volume alert's threshold, so this rule is
    the only notice. It must reach the unmuted Telegram page route (not the
    agent tier muted by omi-tier-silent), and its UID must be on the live
    alert gate that the monitoring workflow imports and reads back.
    """
    import json
    from pathlib import Path

    monitoring = Path(__file__).resolve().parents[2] / 'charts/monitoring'
    uid = 'omi-backlog-held-redrive-unit-looping'
    rule = backlog_alert(uid)
    combined = {r['uid']: r for r in json.loads((monitoring / 'alert-rules.json').read_text(encoding='utf-8'))}
    assert combined[uid] == rule
    settings = rule['notification_settings']
    assert settings['receiver'] == 'Omi - Services Alerting (Telegram)'
    assert 'omi-tier-silent' not in (settings.get('mute_time_intervals') or [])
    assert rule['labels']['tier'] == 'page' and rule['labels']['audience'] == 'human'
    assert not rule['isPaused']
    gate = json.loads((monitoring / 'live-alert-gate.json').read_text(encoding='utf-8'))['uids']
    assert uid in gate
