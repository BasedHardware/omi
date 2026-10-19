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
    binding = asdict(ProjectionBinding('owner', 'job', 'content', ('head', 'tail'), policy=admission))
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
        assert job['projection_binding']['policy'] == admission.to_dict()
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


def test_old_admission_and_new_stage_repair_share_the_unit_fence(unit, monkeypatch):
    store, _ = unit
    for sid in ('head', 'tail'):
        row = store.rows[('jobs', sid)]
        row.pop('policy')
        row['projection_binding'] = {**row['projection_binding'], 'policy': None}
    monkeypatch.setenv('BATCH_PIPELINE_MAX_ATTEMPTS', '2')
    _, first = policies.load_stage_policy(store, 'tail', 'scheduler')
    monkeypatch.setenv('BATCH_PIPELINE_MAX_ATTEMPTS', '19')
    _, second = policies.load_stage_policy(store, 'head', 'scheduler')
    assert first == second and first.max_attempts == 2
    assert store.get('jobs', 'head')['policy_source'] == 'fallback'
    assert store.get('jobs', 'tail')['policy_source'] == 'fallback'


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
