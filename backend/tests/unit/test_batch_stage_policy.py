"""E1 owner split: serving values win once, independently of admission values."""

from dataclasses import asdict, replace

import pytest

from config.policy import BatchUnitPolicy, ProjectionPolicy, RecoveryPolicy, SchedulerPolicy, resolve_batch_policy
from config.policy.stages import STAGE_TYPES
from database import batch_pipeline_policy as policies
from testing.pipeline_sim.store import CustomerData, SimStore
from utils.batch_pipeline.contracts import ProjectionBinding


@pytest.fixture
def unit():
    customer = CustomerData()
    customer.add_user('owner')
    store = SimStore(customer)
    admission = resolve_batch_policy('owner', flags={'BATCH_PIPELINE_ENABLED': 'true', 'BATCH_PIPELINE_PERCENT': '100'})
    binding = asdict(ProjectionBinding('owner', 'job', 'content', ('head', 'tail')))
    for sid in ('head', 'tail'):
        store.rows[('jobs', sid)] = {
            'segment_id': sid,
            'owner_id': 'owner',
            'policy': admission.to_dict(),
            'projection_binding': binding,
        }
    return store, admission


def test_stage_owner_stamps_serving_values_once_without_changing_admission(unit, monkeypatch):
    store, admission = unit
    assert all(not job.get('policy_parts') for job in store.jobs())
    monkeypatch.setenv('K_SERVICE', 'owning-serving-role')
    monkeypatch.setenv('BATCH_PIPELINE_AUTHORITATIVE_LABELS_ENABLED', 'true')
    _, first = policies.load_stage_policy(store, 'tail', 'projection')
    assert first.authoritative_labels and first.source_role == 'owning-serving-role'
    monkeypatch.setenv('K_SERVICE', 'later-role')
    monkeypatch.setenv('BATCH_PIPELINE_AUTHORITATIVE_LABELS_ENABLED', 'false')
    original = policies.resolve_stage_policy

    def no_projection_reresolution(uid, stage):
        assert stage != 'projection', 'recorded part re-resolved env'
        return original(uid, stage)

    monkeypatch.setattr(policies, 'resolve_stage_policy', no_projection_reresolution)
    _, head = policies.load_stage_policy(store, 'head', 'projection')
    _, tail = policies.load_stage_policy(store, 'tail', 'projection')
    assert head == tail == first
    monkeypatch.setenv('BATCH_PIPELINE_RECOVERY_MODE', 'on')
    monkeypatch.setenv('BATCH_PIPELINE_RECOVERY_ALL_ADMITTED', 'true')
    _, recovery = policies.load_stage_policy(store, 'tail', 'recovery')
    assert recovery.recovery_enabled and recovery.source_role == 'later-role'
    monkeypatch.setenv('BATCH_PIPELINE_RECOVERY_MODE', 'off')
    assert policies.load_stage_policy(store, 'head', 'recovery')[1] == recovery
    for sid in ('head', 'tail'):
        job = store.get('jobs', sid)
        assert job['policy'] == admission.to_dict()
        assert 'policy' not in job['projection_binding']
        assert job['policy_parts']['projection'] == first.to_dict()
        assert job['policy_parts']['recovery'] == recovery.to_dict()


@pytest.mark.parametrize('stage', sorted(STAGE_TYPES))
def test_partial_stage_stamp_uses_defaults_without_env(unit, monkeypatch, stage):
    store, _ = unit
    store.rows[('jobs', 'head')]['policy_parts'] = {stage: {}}
    monkeypatch.setattr(policies, 'resolve_stage_policy', lambda *a, **k: pytest.fail('partial stamp re-resolved'))
    _, part = policies.load_stage_policy(store, 'tail', stage)
    assert part == STAGE_TYPES[stage]()
    assert STAGE_TYPES[stage].from_dict({**part.to_dict(), 'future_knob': True}) == part
    assert replace(part, source_role='other-owner').policy_id != part.policy_id


def test_old_stage_repair_leaves_admission_unset(unit, monkeypatch):
    store, _ = unit
    for sid in ('head', 'tail'):
        row = store.rows[('jobs', sid)]
        row.pop('policy')
    monkeypatch.setenv('BATCH_PIPELINE_MAX_ATTEMPTS', '2')
    _, first = policies.load_stage_policy(store, 'tail', 'scheduler')
    monkeypatch.setenv('BATCH_PIPELINE_MAX_ATTEMPTS', '19')
    _, second = policies.load_stage_policy(store, 'head', 'scheduler')
    assert first == second and first.max_attempts == 2
    assert all('policy' not in store.get('jobs', sid) for sid in ('head', 'tail'))


@pytest.fixture(scope='module')
def replay_result():
    from testing.pipeline_sim.sim import simulate
    from testing.pipeline_sim.trace import GOLDEN_CONFIGS

    config = GOLDEN_CONFIGS['healthy']()
    scheduler = SchedulerPolicy(source_role='recorded-scheduler', max_attempts=2)
    recovery = RecoveryPolicy(source_role='recorded-recovery', recovery_enabled=True, recovery_mode='on')
    config.policy_parts = {'scheduler': scheduler.to_dict(), 'recovery': recovery.to_dict()}
    config.flags.update(BATCH_PIPELINE_MAX_ATTEMPTS='19', BATCH_PIPELINE_RECOVERY_MODE='off')
    result = simulate(config)
    return result, scheduler


def test_sim_replay_consumes_recorded_owner_parts_even_when_flags_disagree(replay_result):
    result, scheduler = replay_result
    assert result.store.jobs()
    assert all(job['policy_parts']['scheduler'] == scheduler.to_dict() for job in result.store.jobs())


def test_first_summary_owner_stamps_creation_and_keeps_stamp_on_coalescing(monkeypatch):
    from utils.sync import reprocess
    from config.summary_guarantee import first_summary_pending

    saved = None

    def mutate(_key, operation):
        nonlocal saved
        saved, result = operation(saved)
        return result

    monkeypatch.setattr(reprocess, 'owns_runtime', lambda: True)
    monkeypatch.setattr(reprocess, '_enqueue', lambda row: None)
    monkeypatch.setenv('K_SERVICE', 'summary-owner')
    monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_ENABLED', 'true')
    monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_PERCENT', '0')
    reprocess.mark('owner', 'conversation', 'en', now=1, mutate=mutate, snapshot_summary=True)
    first = saved['first_summary_policy']
    assert first['source_role'] == 'summary-owner' and not first['first_summary_enabled']
    monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_PERCENT', '100')
    reprocess.mark('owner', 'conversation', 'en', now=2, mutate=mutate, snapshot_summary=True)
    assert saved['first_summary_policy'] == first and not first_summary_pending(saved)
    saved['dormant'] = True  # A new obligation may use the owner's new policy.
    reprocess.mark('owner', 'conversation', 'en', now=3, mutate=mutate, snapshot_summary=True)
    assert first_summary_pending(saved) and saved['first_summary_policy']['policy_id'] != first['policy_id']


@pytest.mark.parametrize('competing_writer', [False, True])
def test_retried_stage_claim_keeps_candidate_and_adopts_a_committed_winner(unit, monkeypatch, competing_writer):
    from testing.pipeline_sim.store import SimTransaction

    store, _ = unit
    run = store.run
    resolve = policies.resolve_stage_policy
    calls = []
    winner = ProjectionPolicy(source_role='competing-owner', authoritative_labels=False)
    scheduler = SchedulerPolicy(max_attempts=4)
    monkeypatch.setenv('BATCH_PIPELINE_AUTHORITATIVE_LABELS_ENABLED', 'true')

    def counted(uid, stage):
        calls.append(stage)
        return resolve(uid, stage)

    def retry(body):
        body(SimTransaction(store))  # Discard the aborted attempt's buffered writes.
        monkeypatch.setenv('BATCH_PIPELINE_AUTHORITATIVE_LABELS_ENABLED', 'false')
        if competing_writer:
            store.rows[('jobs', 'head')]['policy_parts'] = {
                'projection': winner.to_dict(),
                'scheduler': scheduler.to_dict(),
            }
        return run(body)

    monkeypatch.setattr(policies, 'resolve_stage_policy', counted)
    monkeypatch.setattr(store, 'run', retry)
    _, part = policies.load_stage_policy(store, 'tail', 'projection')
    assert calls == ['projection']
    assert part == winner if competing_writer else part.authoritative_labels
    assert store.get('jobs', 'head')['policy_parts']['projection'] == part.to_dict()
    assert store.get('jobs', 'tail')['policy_parts']['projection'] == part.to_dict()
    if competing_writer:
        assert store.get('jobs', 'head')['policy_parts']['scheduler'] == scheduler.to_dict()


def test_first_summary_fallback_preserves_an_existing_admitted_deadline():
    from config.policy import resolve_stage_policy

    part = resolve_stage_policy(
        'owner',
        'first_summary',
        flags={
            'FIRST_SUMMARY_DEADLINE_ENABLED': 'true',
            'FIRST_SUMMARY_DEADLINE_PERCENT': '0',
            'FIRST_SUMMARY_PRESERVE_ADMITTED_ENABLED': 'true',
        },
        obligation={'summary_deadline_at': 120},
    )
    assert part.first_summary_enabled


def test_first_scheduler_failure_stamps_only_its_owner_part(monkeypatch):
    from config.policy import telemetry
    from utils.batch_pipeline.contracts import WorkItem, Priority
    from utils.batch_pipeline.scheduler import Scheduler

    customer = CustomerData()
    customer.add_user('owner')
    store = SimStore(customer)
    queue = Scheduler(store)
    queue.enqueue(WorkItem('old', 'owner', 1, 'sim://audio', 1, Priority.FRESH), 1)
    lease = queue.pull(2)[0]
    row = store.rows[('jobs', 'old')]
    row.pop('policy')
    row.pop('policy_parts')
    row.pop('policy_source', None)
    monkeypatch.setenv('BATCH_PIPELINE_MAX_ATTEMPTS', '2')
    events = []
    monkeypatch.setattr(telemetry, 'record_policy_source', lambda source, *_: events.append(source))
    assert queue.fail('old', lease.token, 3, quarantine=True)
    row = store.get('jobs', 'old')
    assert row['policy_parts']['scheduler']['max_attempts'] == 2
    assert 'policy' not in row and 'policy_source' not in row
    assert row['policy_part_sources']['scheduler'] == 'fallback'
    assert events == ['fallback']


def test_disabled_recovery_does_not_read_the_cohort(monkeypatch):
    import config.policy.stages as stages

    def unexpected(*args, **kwargs):
        raise AssertionError('disabled recovery must not load membership')

    monkeypatch.setattr(stages, 'member', unexpected)
    assert not stages.resolve_stage_policy('owner', 'recovery', flags={}).recovery_enabled


@pytest.fixture(scope='module')
def role_policy_trace():
    from testing.pipeline_sim.trace import GOLDEN_CONFIGS, trace

    config = GOLDEN_CONFIGS['role_policy']()
    correct = trace(config)
    config.stage_roles.update(projection='sync', recovery='sync')
    wrong = trace(config)
    return correct, wrong


def test_two_serving_environments_leave_visible_owner_stamps(role_policy_trace):
    correct, wrong = role_policy_trace
    jobs = [segment['final_job'] for segment in correct['segments'].values() if segment['final_job']]
    assert jobs and any(job.get('policy_parts', {}).get('recovery') for job in jobs)
    for job in jobs:
        assert job['policy']['source_role'] == 'sync'
        for stage, field in [('projection', 'authoritative_labels'), ('recovery', 'recovery_enabled')]:
            part = job.get('policy_parts', {}).get(stage)
            if part:
                assert part['source_role'] == 'integration'
                assert part[field] is True
                assert len(part['policy_id']) == 64
    assert correct != wrong, 'swapping stage ownership must break the policy golden'


def test_pre_e1_constructor_accepts_every_binding_written_by_e1(replay_result):
    from tests.unit.fixtures.pre_e1_projection_binding import PreE1ProjectionBinding

    result, *_ = replay_result
    bindings = [job['projection_binding'] for job in result.store.jobs()]
    assert bindings
    for binding in bindings:
        assert 'policy' not in binding
        assert PreE1ProjectionBinding(**binding).job_id == binding['job_id']


@pytest.mark.parametrize('stage', ['scheduler', 'projection', 'recovery'])
def test_stage_role_never_writes_an_admission_fallback(unit, monkeypatch, stage):
    store, _ = unit
    for job in store.rows.values():
        job.pop('policy', None)
    monkeypatch.setattr(policies, 'resolve_batch_policy', lambda *a, **k: pytest.fail('stage resolved admission'))
    monkeypatch.setenv('K_SERVICE', 'gpu-worker')
    monkeypatch.setenv('BATCH_PIPELINE_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_PERCENT', '0')
    _, part = policies.load_stage_policy(store, 'tail', stage)
    assert part.source_role == 'gpu-worker'
    assert all('policy' not in row for row in store.jobs())
    assert all(row['policy_part_sources'][stage] == 'fallback' for row in store.jobs())
    assert all('policy' not in row['projection_binding'] for row in store.jobs())
