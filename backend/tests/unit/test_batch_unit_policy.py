"""E1 guards for the 2026-10-18 policy-window incident (plan E)."""

import ast
from dataclasses import FrozenInstanceError, replace
import hashlib
import json
from pathlib import Path

import pytest
import yaml

from config.policy import (
    BatchUnitPolicy,
    ProjectionPolicy,
    SchedulerPolicy,
    FirstSummaryPolicy,
    cohort_bucket,
    resolve_batch_policy,
    resolve_stage_policy,
    kill_switch,
)
from config.policy.batch import COHORT_SALTS, LEGACY_CORRELATED_COHORTS, SNAPSHOT_ENV_KEYS
from config.policy.kill_switches import KILL_SWITCHES

from database.batch_pipeline_intake import admit
from database.batch_pipeline_policy import load_job_policy, load_stage_policy
from testing.pipeline_sim.store import CustomerData, SimStore
from utils.batch_pipeline.contracts import ProjectionBinding, WorkItem, Priority
from utils.batch_pipeline.scheduler import Scheduler

ROOT = Path(__file__).resolve().parents[3]


def test_defaults_roundtrip_and_content_identity():
    policy = resolve_batch_policy('owner', flags={})
    assert policy == BatchUnitPolicy()
    assert BatchUnitPolicy.from_dict(json.loads(json.dumps(policy.to_dict()))) == policy
    assert BatchUnitPolicy.from_dict({'future_field': 1}) == policy
    assert BatchUnitPolicy.from_dict({'max_attempts': 'malformed'}) == policy
    assert replace(policy, batch_percent=6).policy_id != policy.policy_id
    with pytest.raises(FrozenInstanceError):
        policy.batch_enabled = True


@pytest.mark.parametrize('percent', ['0', '1', '50', '100', 'nan', 'inf', '-1', '101', 'bad'])
def test_batch_membership_matches_original_hash(percent):
    for index in range(100):
        uid = f'owner-{index}'
        bucket = int.from_bytes(hashlib.sha256(uid.encode()).digest()[:4], 'big') / 2**32 * 100
        assert cohort_bucket(uid, '') == bucket
        expected = percent in {'0', '1', '50', '100'} and bucket < float(percent)
        assert (
            resolve_batch_policy(
                uid, flags={'BATCH_PIPELINE_ENABLED': 'true', 'BATCH_PIPELINE_PERCENT': percent}
            ).batch_enabled
            == expected
        )


def test_allowlist_and_nested_retirement():
    flags = {'BATCH_PIPELINE_ENABLED': 'true', 'BATCH_PIPELINE_PERCENT': '20', 'BATCH_LIVE_STT_RETIRE_PERCENT': '99'}
    for index in range(100):
        policy = resolve_batch_policy(f'owner-{index}', flags=flags)
        assert policy.retire_percent == 20
        assert not policy.live_stt_retired or policy.batch_enabled
    assert not resolve_batch_policy('owner', flags={**flags, 'BATCH_PIPELINE_ENABLED': 'false'}).live_stt_retired
    assert resolve_batch_policy(
        'owner', flags={**flags, 'BATCH_PIPELINE_PERCENT': '0', 'BATCH_PIPELINE_UID_ALLOWLIST': 'owner'}
    ).batch_enabled
    with pytest.raises(ValueError, match='nested'):
        BatchUnitPolicy(batch_percent=10, retire_percent=20)


def test_cohort_registry_and_live_switch_contract():
    assert COHORT_SALTS['batch-live-stt-retire'] == COHORT_SALTS['batch-pipeline'] == ''
    seen = {}
    for cohort, salt in COHORT_SALTS.items():
        if cohort in LEGACY_CORRELATED_COHORTS or cohort == 'batch-live-stt-retire':
            continue
        assert salt not in seen, f'{cohort} must have its own salt'
        seen[salt] = cohort
    # The 240 KB registry takes ~0.7s to parse with the pure-Python loader; the C loader
    # yields the identical structure and keeps this call-phase cost well under the guard.
    loader = getattr(yaml, 'CSafeLoader', yaml.SafeLoader)
    rows = yaml.load((ROOT / 'config/feature-flags.yaml').read_text(), Loader=loader)['flags']
    by_key = {row['key']: row for row in rows}
    for key in KILL_SWITCHES:
        assert by_key[key]['lifecycle'] == 'ops_kill'
        assert kill_switch(key, flags={})
        assert not kill_switch(key, flags={key: 'false'})
    assert 'nested' in by_key['BATCH_LIVE_STT_RETIRE_PERCENT']['notes'].lower()
    with pytest.raises(ValueError):
        kill_switch('BATCH_PIPELINE_ENABLED')
    assert kill_switch(
        'BATCH_PIPELINE_LEADER_LEASE_ENABLED', flags={'BATCH_PIPELINE_LEADER_LEASE_ENABLED': 'unexpected'}
    )


@pytest.fixture(scope='module')
def scoped_env_violations():
    from config.policy.guard import violations, registry_violations

    return violations(ROOT) + registry_violations(ROOT)


def test_scoped_env_reads_only_in_policy(scoped_env_violations):
    assert not scoped_env_violations, '\n'.join(scoped_env_violations)


def test_guard_catches_aliased_and_subscript_reads():
    from config.policy.guard import env_reads

    source = "import os as operating; from os import getenv as read; key = 'BATCH_PIPELINE_ENABLED'; operating.environ.get(key); read(key); operating.environ[key]"
    assert list(env_reads(source)) == ['BATCH_PIPELINE_ENABLED'] * 3


def test_admission_policy_survives_env_change(monkeypatch):

    policy = resolve_batch_policy(
        'owner',
        flags={'BATCH_PIPELINE_ENABLED': 'true', 'BATCH_PIPELINE_PERCENT': '100', 'BATCH_PIPELINE_MAX_ATTEMPTS': '1'},
    )
    customer = CustomerData()
    customer.add_user('owner')
    store = SimStore(customer)
    binding = ProjectionBinding('owner', 'job', 'content', ('seg',))
    monkeypatch.setenv('BATCH_PIPELINE_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_MAX_ATTEMPTS', '20')
    item = WorkItem('seg', 'owner', 1, 'sim://audio', 1, Priority.FRESH, privacy_generation=0)
    assert admit(store, [item], binding, 1, namespace=store.namespace, policy=policy)['outcome'] == 'batch'
    queue = Scheduler(store)
    lease = queue.pull(2)[0]
    assert queue.fail('seg', lease.token, 3)
    assert store.get('jobs', 'seg')['state'] == 'retry'
    assert store.get('jobs', 'seg')['policy_parts']['scheduler']['max_attempts'] == 20
    assert store.get('jobs', 'seg')['policy'] == policy.to_dict()


def test_legacy_fallback_persists_across_stages(monkeypatch):

    customer = CustomerData()
    customer.add_user('owner')
    store = SimStore(customer)
    binding = {'owner_id': 'owner', 'segment_ids': ['a', 'b']}
    for sid in ('a', 'b'):
        store.rows[('jobs', sid)] = {'segment_id': sid, 'owner_id': 'owner', 'projection_binding': binding}
    monkeypatch.setenv('BATCH_PIPELINE_MAX_ATTEMPTS', '2')
    job, first = load_stage_policy(store, 'a', 'scheduler')
    monkeypatch.setenv('BATCH_PIPELINE_MAX_ATTEMPTS', '19')
    _, second = load_stage_policy(store, 'b', 'scheduler')
    assert first == second and second.max_attempts == 2
    assert 'policy' not in job and 'policy' not in store.get('jobs', 'b')
    assert all('policy' not in row['projection_binding'] for row in store.jobs())


def test_summary_obligation_uses_creation_policy_after_ramp(monkeypatch):
    from config.summary_guarantee import first_summary_pending

    policy = resolve_stage_policy(
        'owner',
        'first_summary',
        flags={'FIRST_SUMMARY_DEADLINE_ENABLED': 'true', 'FIRST_SUMMARY_DEADLINE_PERCENT': '0'},
    )
    row = {'uid': 'owner', 'first_summary_policy': policy.to_dict(), 'first_pending_at': 1}
    monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_ENABLED', 'true')
    monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_PERCENT', '100')
    assert not first_summary_pending(row)
    row['first_summary_policy'] = replace(policy, first_summary_enabled=True).to_dict()
    monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_PERCENT', '0')
    assert first_summary_pending(row)


@pytest.fixture(scope='module')
def policy_window_result():
    from testing.pipeline_sim.sim import simulate
    from testing.pipeline_sim.trace import GOLDEN_CONFIGS

    return simulate(GOLDEN_CONFIGS['policy_window']())


def test_policy_window_is_graded_under_the_creation_policy(policy_window_result):
    from testing.pipeline_sim.scorer import score

    result = policy_window_result
    assert any(
        record.summary_completed_at - record.summary_pending_at > 120
        for record in result.records
        if record.summary_completed_at
    )
    result.config.flags['FIRST_SUMMARY_DEADLINE_PERCENT'] = '100'
    sample = score(result)
    assert sample['first_summary_checked_conversations'] == 0
    assert sample['first_summary_deadline_breaches'] == 0
    # Counterfactual: today's contract would misgrade the same observations.
    for record in result.records:
        if record.first_summary_policy:
            record.first_summary_policy = replace(record.first_summary_policy, first_summary_enabled=True)
    assert score(result)['first_summary_deadline_breaches'] > 0


@pytest.fixture
def legacy_sibling_groups():
    from dataclasses import asdict

    customer = CustomerData()
    store = SimStore(customer)
    tails = []
    for unit in range(5):
        owner = f'owner-{unit}'
        customer.add_user(owner)
        ids = tuple(f'unit-{unit}-segment-{i}' for i in range(128))
        binding = asdict(ProjectionBinding(owner, f'job-{unit}', f'content-{unit}', ids))
        for sid in ids:
            store.rows[('jobs', sid)] = {'segment_id': sid, 'owner_id': owner, 'projection_binding': binding}
        tails.append(ids[-1])
    return store, tails


def test_fallback_does_not_rewrite_all_siblings_per_queue(legacy_sibling_groups):
    from database.batch_pipeline_policy import policy_in_transaction

    store, tails = legacy_sibling_groups

    def visit(tx):
        for sid in tails:
            policy_in_transaction(tx, tx.get('jobs', sid))
        return len(tx.writes)

    assert store.run(visit) == 10  # anchor + visited row per unit, below the 450-write ceiling


def test_existing_cohort_membership_stays_correlated():
    for i in range(100):
        uid = f'owner-{i}'
        policy = resolve_batch_policy(
            uid,
            flags={
                'BATCH_PIPELINE_ENABLED': 'true',
                'BATCH_PIPELINE_PERCENT': '25',
                'FIRST_SUMMARY_DEADLINE_ENABLED': 'true',
                'FIRST_SUMMARY_DEADLINE_PERCENT': '25',
                'TRANSCRIPTION_FINAL_PASS_DIARIZER': 'pyannote_shadow',
                'TRANSCRIPTION_FINAL_PASS_PERCENT': '25',
            },
        )
        assert (
            policy.batch_enabled
            == resolve_stage_policy(
                uid,
                'first_summary',
                flags={'FIRST_SUMMARY_DEADLINE_ENABLED': 'true', 'FIRST_SUMMARY_DEADLINE_PERCENT': '25'},
            ).first_summary_enabled
            == policy.final_pass_enabled
        )


@pytest.fixture
def sync_jobs_with_redis(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    import fakeredis
    from database import sync_jobs

    redis = fakeredis.FakeRedis()
    redis.eval('return 1', 0)
    monkeypatch.setattr(sync_jobs, 'r', redis)
    return sync_jobs, redis


def test_redis_legacy_policy_is_persisted_once_without_resetting_ttl(sync_jobs_with_redis, monkeypatch):
    jobs, redis = sync_jobs_with_redis
    key = jobs._key(jobs.JOB_KEY_PREFIX + 'legacy')
    redis.set(key, json.dumps({'uid': 'owner', 'job_id': 'legacy', 'processed_segments': 3}), ex=100)
    monkeypatch.setenv('BATCH_PIPELINE_PERCENT', '2')
    first = jobs.load_sync_job_policy('legacy')
    monkeypatch.setenv('BATCH_PIPELINE_PERCENT', '19')
    second = jobs.load_sync_job_policy('legacy')
    assert first['policy'] == second['policy']
    assert second['policy']['batch_percent'] == 2
    assert second['processed_segments'] == 3 and second['policy_source'] == 'fallback'
    assert 95 <= redis.ttl(key) <= 100


def test_redis_owner_pins_the_existing_admission_policy(sync_jobs_with_redis, monkeypatch):
    jobs, redis = sync_jobs_with_redis
    key = jobs._key(jobs.JOB_KEY_PREFIX + 'legacy')
    original = json.dumps({'uid': 'owner', 'job_id': 'legacy', 'processed_segments': 3})
    redis.set(key, original, ex=100)
    admitted = BatchUnitPolicy(batch_enabled=True, batch_percent=3)
    monkeypatch.setenv('BATCH_PIPELINE_PERCENT', '99')
    assert jobs.get_sync_job('legacy') == json.loads(original)
    assert redis.get(key) == original.encode()
    pinned = jobs.load_sync_job_policy('legacy', policy=admitted)
    assert pinned['policy'] == admitted.to_dict()
    assert jobs.get_sync_job('legacy') == pinned


def test_redis_policy_cas_preserves_concurrent_progress(sync_jobs_with_redis, monkeypatch):
    jobs, redis = sync_jobs_with_redis
    key = jobs._key(jobs.JOB_KEY_PREFIX + 'legacy')
    redis.set(key, json.dumps({'uid': 'owner', 'job_id': 'legacy', 'processed_segments': 1}), ex=100)
    original_eval = redis.eval
    raced = False

    def race(script, *args):
        nonlocal raced
        if not raced:
            raced = True
            current = json.loads(redis.get(key))
            current['processed_segments'] = 4
            redis.set(key, json.dumps(current), keepttl=True)
        return original_eval(script, *args)

    monkeypatch.setattr(redis, 'eval', race)
    assert jobs.load_sync_job_policy('legacy')['processed_segments'] == 4
    assert json.loads(redis.get(key))['policy_source'] == 'fallback'


def test_redis_policy_cas_adopts_an_existing_winner(sync_jobs_with_redis, monkeypatch):
    jobs, redis = sync_jobs_with_redis
    key = jobs._key(jobs.JOB_KEY_PREFIX + 'legacy')
    redis.set(key, json.dumps({'uid': 'owner', 'job_id': 'legacy'}), ex=100)
    winner = BatchUnitPolicy(batch_percent=3).to_dict()
    original_eval = redis.eval

    def race(script, *args):
        current = json.loads(redis.get(key))
        current.update(policy=winner, policy_source='fallback')
        redis.set(key, json.dumps(current), keepttl=True)
        return original_eval(script, *args)

    monkeypatch.setattr(redis, 'eval', race)
    assert jobs.load_sync_job_policy('legacy')['policy'] == winner


def test_guard_rejects_a_stage_reresolving_through_a_legacy_getter():
    from config.policy.guard import stage_policy_reads

    source = "from config.batch_pipeline import head_priority_enabled as selected\ndef pull():\n    return selected()\n"
    assert len(stage_policy_reads(source, 'utils/batch_pipeline/scheduler.py')) == 1
    source = "from config.policy import resolve_batch_policy\ndef enqueue_in_transaction():\n    return resolve_batch_policy('owner')\n"
    assert not stage_policy_reads(source, 'utils/batch_pipeline/scheduler.py')
    assert len(stage_policy_reads(source, 'utils/batch_pipeline/projection.py')) == 1


def test_partial_recorded_snapshot_uses_original_defaults_not_current_env(monkeypatch):
    customer = CustomerData()
    customer.add_user('owner')
    store = SimStore(customer)
    store.rows[('jobs', 'old')] = {'owner_id': 'owner', 'segment_id': 'old', 'policy': {}}
    monkeypatch.setenv('BATCH_PIPELINE_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_PERCENT', '100')
    monkeypatch.setenv('BATCH_PIPELINE_MAX_ATTEMPTS', '1')
    _, policy = load_job_policy(store, 'old')
    assert policy == BatchUnitPolicy()


def test_legacy_policy_repair_does_not_block_other_privacy_eligible_owners():
    customer = CustomerData()
    store = SimStore(customer)
    queue = Scheduler(store)
    for owner in ('blocked', 'healthy'):
        customer.add_user(owner)
        queue.enqueue(WorkItem(owner, owner, 1, 'sim://audio', 1, Priority.FRESH), 1)
        store.rows[('jobs', owner)].pop('policy')
    customer.block_privacy('blocked')
    leases = queue.pull(2)
    assert [lease.item.owner_id for lease in leases] == ['healthy']
    assert 'policy' not in store.get('jobs', 'blocked')


def test_legacy_fallback_can_anchor_on_an_unfenced_sibling():
    from dataclasses import asdict

    customer = CustomerData()
    customer.add_user('owner')
    customer.add_conversation('owner', 'old-target')
    customer.add_conversation('owner', 'live-target')
    customer.delete_conversation('owner', 'old-target')
    store = SimStore(customer)
    binding = asdict(ProjectionBinding('owner', 'job', 'content', ('old', 'live')))
    for sid, target in [('old', 'old-target'), ('live', 'live-target')]:
        store.rows[('jobs', sid)] = {
            'segment_id': sid,
            'owner_id': 'owner',
            'conversation_id': target,
            'projection_binding': binding,
        }
    _, policy = load_job_policy(store, 'live')
    assert store.get('jobs', 'live')['policy'] == policy.to_dict()
    assert not store.get('jobs', 'old').get('policy')


@pytest.fixture(params=[True, False])
def explicit_sim_policy(request, monkeypatch):
    import os
    from testing.pipeline_sim.sim import Simulation
    from testing.pipeline_sim.trace import GOLDEN_CONFIGS

    monkeypatch.setenv('BATCH_PIPELINE_ENABLED', 'false')
    config = GOLDEN_CONFIGS['healthy']()
    policy = BatchUnitPolicy(batch_enabled=request.param)
    config.policy = policy
    sim = Simulation(config)
    observed = []
    sim.store.observers.append(lambda *args: observed.append(os.environ['BATCH_PIPELINE_ENABLED']))
    return sim.run(), policy, observed


def test_sim_accepts_an_explicit_policy_without_installing_scoped_env(explicit_sim_policy):
    result, policy, observed = explicit_sim_policy
    assert result.records and all(record.policy is policy for record in result.records)
    assert all(value == 'false' for value in observed)
    admitted = [record for record in result.records if record.status == 'admitted']
    assert bool(admitted) is policy.batch_enabled
    assert all(job['policy'] == policy.to_dict() for job in result.store.jobs())
    if not policy.batch_enabled:
        assert result.stt.stats.requests == 0


def test_getter_guard_covers_new_directories_and_import_aliases():
    from config.policy.guard import stage_policy_reads

    assert stage_policy_reads(
        "from config.batch_pipeline import recovery_enabled_for as allowed\nallowed('owner')",
        'database/a_new_recovery_owner.py',
    )
    assert stage_policy_reads(
        "from config import batch_pipeline as flags\nflags.terminal_empty_disposition_enabled()",
        'utils/a_new_artifact_writer.py',
    )
    assert stage_policy_reads(
        "from config.policy.stages import resolve_stage_policy as resolve\nresolve('owner', 'recovery')",
        'utils/a_new_unit_handler.py',
    )
    assert not stage_policy_reads(
        "from utils.sync import legacy_fresh\nlegacy_fresh.enabled_for('owner')",
        'routers/sync.py',
    )


@pytest.mark.parametrize('key', sorted(SNAPSHOT_ENV_KEYS | KILL_SWITCHES.keys()))
def test_guard_fails_owned_and_live_switch_reads_outside_policy(tmp_path, key):
    from config.policy.guard import scan

    path = tmp_path / 'backend/utils/new_stage.py'
    path.parent.mkdir(parents=True)
    path.write_text(f'import os\nos.getenv({key!r})\n')
    errors, warnings = scan(tmp_path)
    assert errors == [f'utils/new_stage.py: {key} must be resolved in config/policy/']
    assert warnings == []


@pytest.mark.parametrize(
    'key',
    [
        'BATCH_PIPELINE_PUBLISH_CONCURRENCY',
        'BATCH_PIPELINE_FLIGHT_BATCH_SECONDS',
        'BATCH_PIPELINE_FLIGHT_BATCHING_ENABLED',
        'BATCH_PIPELINE_DIARIZE_SPEECH_ONLY_ENABLED',
        'BATCH_PIPELINE_MODEL_BATCH_SIZE',
        'BATCH_PIPELINE_NEW_UNLISTED_WORKER_KEY',
    ],
)
def test_guard_warns_without_failing_unowned_batch_reads(tmp_path, key, monkeypatch, capsys):
    from config.policy import guard

    path = tmp_path / 'backend/utils/new_worker.py'
    path.parent.mkdir(parents=True)
    path.write_text(f'import os\nos.getenv({key!r})\n')
    errors, warnings = guard.scan(tmp_path)
    assert errors == []
    assert warnings == [f'utils/new_worker.py: {key} is outside E1 policy ownership (E1b candidate)']
    monkeypatch.setattr(guard, 'scan', lambda root: (errors, warnings))
    monkeypatch.setattr(guard, 'registry_violations', lambda root: [])
    assert guard.main() == 0
    assert f'WARNING: utils/new_worker.py: {key}' in capsys.readouterr().err


def test_guard_ownership_matches_batch_resolver_inputs():
    # Adding a resolver-owned batch key must extend the ownership declaration;
    # otherwise it could incorrectly become an advisory worker-key warning.
    keys = set()
    directory = ROOT / 'backend/config/policy'
    for filename in ('batch.py', 'stages.py'):
        tree = ast.parse((directory / filename).read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if node.value.startswith('BATCH_PIPELINE_') or node.value == 'BATCH_LIVE_STT_RETIRE_PERCENT':
                    keys.add(node.value)
    assert keys == SNAPSHOT_ENV_KEYS
