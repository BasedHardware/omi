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
    sm.RECORD_BARRIER_DEAD_LETTER_SWITCH,
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
    return backlog_metrics.TERMINAL_TRANSITIONS.labels(name)._value.get()


def test_switches_are_registered_safety_kill_switches_default_on(monkeypatch):
    from config.policy.kill_switches import KILL_SWITCHES

    for name in SWITCHES:
        assert KILL_SWITCHES[name] is True
    assert sm.retry_cap_enforced() and sm.sync_attempt_carry_enabled()
    assert sm.held_redrive_budget_enabled() and sm.record_barrier_dead_letter_enabled()
    for name in SWITCHES:
        monkeypatch.setenv(name, 'false')
    assert not sm.retry_cap_enforced() and not sm.sync_attempt_carry_enabled()
    assert not sm.held_redrive_budget_enabled() and not sm.record_barrier_dead_letter_enabled()


# 1. Retry cap enforced by default ------------------------------------------------


@pytest.mark.parametrize('switch,expected', [(None, 'quarantined'), ('false', 'retry')])
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


@pytest.mark.parametrize('switch,serving', [(None, True), ('false', False)])
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


# 2. Sync lease expiry carries dispatch_attempt ------------------------------------


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


@pytest.mark.parametrize('switch,expected', [(None, [1, 2, 3]), ('false', [0, 0, 0])])
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
    account, epoch = running_owner(db, monkeypatch, attempts='2')
    replacement, now = crash_once(account, epoch, NOW)
    assert replacement['dispatch_attempt'] == 1
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


def test_budget_deferral_chain_keeps_its_own_count_and_terminal(db, monkeypatch):
    account, epoch = running_owner(db, monkeypatch, attempts='2')
    for _ in range(3):
        assert registry.begin_job(account, 'crashy', epoch, now=NOW)
        assert registry.note_budget_deferral(account, 'crashy', epoch, 1, now=NOW)
        expired = NOW + timedelta(seconds=registry.LEASE_SECONDS + 1)
        replacement = registry.redrive_job(account, 'crashy', epoch, now=expired)
        # budget_chain_exhausted owns this chain; its dispatch count keeps the legacy reset.
        assert replacement['dispatch_attempt'] == 0
        epoch = replacement['epoch']


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


def test_running_cap_kill_switch_restores_unbounded_redrive(db, monkeypatch):
    monkeypatch.setenv(sm.SYNC_ATTEMPT_CARRY_SWITCH, 'false')
    account, epoch = running_owner(db, monkeypatch, attempts='2')
    now = NOW
    for _ in range(4):
        replacement, now = crash_once(account, epoch, now)
        assert replacement is not None
        epoch = replacement['epoch']


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


@pytest.mark.parametrize('switch', [None, 'false'])
def test_requeue_grants_a_fresh_attempt_budget(setup, monkeypatch, switch):
    if switch is not None:
        monkeypatch.setenv(sm.HELD_REDRIVE_BUDGET_SWITCH, switch)
    client, store, _, _, _, _ = setup
    control_for(client)
    held_dead(bad(client), attempt=5)
    assert RecoveryStore(store).requeue_quarantined('bad', 30, dead_before=86400) is True
    job = bad(client)
    assert job['state'] == 'ready' and job['audio_uri'] == 'gs://synthetic/audio'
    if switch is None:
        # A re-drive gets a real attempt: the first failure no longer re-quarantines.
        assert job['attempt'] == 0
        assert job['held_redrives'] == 1 and job['held_redrive_last_attempt'] == 5
    else:
        assert job['attempt'] == 5 and 'held_redrives' not in job


def test_requeued_unit_survives_one_lease_expiry_with_a_fresh_budget(monkeypatch):
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
    assert lease.attempt == 1
    queue.recover(5121)
    # Before: attempt stayed at the cap and this first expiry re-quarantined.
    assert store.rows['jobs', 'poison']['state'] == 'retry'


def test_automatic_redrive_stops_after_max_and_operator_can_still_requeue(setup, monkeypatch):
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


def test_malformed_redrive_counter_counts_as_spent(setup):
    client, store, _, _, _, _ = setup
    control_for(client)
    held_dead(bad(client))
    bad(client)['held_redrives'] = 'two'
    assert RecoveryStore(store).requeue_quarantined('bad', 30, dead_before=86400) == 'exhausted'


def test_held_budget_switch_off_keeps_legacy_unbounded_nightly_redrive(setup, monkeypatch):
    monkeypatch.setenv(sm.HELD_REDRIVE_BUDGET_SWITCH, 'false')
    client, store, _, _, _, _ = setup
    control_for(client)
    held_dead(bad(client))
    bad(client)['held_redrives'] = sm.MAX_HELD_REDRIVES + 5
    assert RecoveryStore(store).requeue_quarantined('bad', 30, dead_before=86400) is True


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


@pytest.mark.parametrize('switch', [None, 'false'])
def test_projection_rearm_counts_and_stops_after_max(projection, monkeypatch, switch):
    from database.batch_pipeline_projection_release import MAX_RELEASE_ATTEMPTS, ProjectionReleaseStore

    if switch is not None:
        monkeypatch.setenv(sm.HELD_REDRIVE_BUDGET_SWITCH, switch)
    rows, store_for = projection
    result = ('batch_pipeline_prod_results', 'held')
    client, store = store_for(
        rows(discarded=True, held_deadline_at=1, projection_release_attempts=MAX_RELEASE_ATTEMPTS)
    )
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
        if switch is None and rearm > sm.MAX_PROJECTION_REARMS:
            assert release.rearm_exhausted
            assert entry['projection_release_attempts'] == MAX_RELEASE_ATTEMPTS
            assert entry['held_rearm_exhausted_at'] == 2.0 + rearm
            assert entry['held_expired_rearms'] == sm.MAX_PROJECTION_REARMS
        else:
            assert entry['projection_release_attempts'] == 0
            if switch is None:
                assert entry['held_expired_rearms'] == rearm
            else:
                assert 'held_expired_rearms' not in entry
        # The receipt and its payload are retained in every case.
        assert entry['projection_state'] == 'quarantine_held'


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


def test_unfinished_conversation_redrives_weekly_then_dead_letters(drain):
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
    assert delay == sm.RECORD_BARRIER_PARK_SECONDS
    assert job['state'] == 'record_pending'  # Custody and erasure keep owning the row.
    assert job['barrier_dead_letter']['reason'] == sm.RECORD_BARRIER_DEAD_LETTER_REASON
    assert job['barrier_dead_letter']['redrives'] == sm.MAX_RECORD_BARRIER_REDRIVES
    assert job['audio_uri'] == 'gs://synthetic/record'
    assert transitions('record_barrier_redrive') == redrives + sm.MAX_RECORD_BARRIER_REDRIVES
    assert transitions('record_barrier_dead_letter') == dead + 1
    # Parked: never due again, so the drain stops reading it.
    clock[0] += 365 * DAY
    assert store.due('record_pending', clock[0], 100) == []
    # Operator exit: one fresh budget, history retained.
    assert live.requeue_barrier_dead_letter(store, 's', clock[0])
    job = store.rows['jobs', 's']
    assert job['available_at'] == clock[0] and job['barrier_redrives'] == 0
    assert 'barrier_dead_letter' not in job and len(job['barrier_dead_letter_history']) == 1
    assert not live.requeue_barrier_dead_letter(store, 's', clock[0])


@pytest.mark.parametrize(
    'age,status,present,delay',
    [
        # Young rows keep the #24863 ladder.
        (13 * DAY, 'in_progress', True, 3600),
        # A missing conversation belongs to the seven-day record_pending_repair cancel.
        (30 * DAY, None, False, 3600),
        # A completed conversation with open upload tokens belongs to seal repair.
        (30 * DAY, 'completed', True, 3600),
    ],
)
def test_other_barrier_cohorts_keep_their_existing_owner(drain, age, status, present, delay):
    live, _, seed, run, _ = drain
    seed(age)
    job, got = run(barrier(live, status, present))
    assert got == delay and 'barrier_redrives' not in job and 'barrier_dead_letter' not in job


def test_plain_barrier_error_from_the_transactional_recheck_is_not_parked(drain):
    live, _, seed, run, _ = drain
    seed(30 * DAY)
    job, delay = run(ValueError(live.BARRIER_NOT_CLOSED))
    assert delay == 3600 and 'barrier_redrives' not in job


def test_record_dead_letter_kill_switch_keeps_the_hourly_ladder(drain, monkeypatch):
    live, _, seed, run, _ = drain
    monkeypatch.setenv(sm.RECORD_BARRIER_DEAD_LETTER_SWITCH, 'false')
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
