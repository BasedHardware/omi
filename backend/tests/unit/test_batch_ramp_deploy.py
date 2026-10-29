"""A backend deploy replaces process config, never runtime ramp intent."""

import asyncio
from copy import deepcopy
from pathlib import Path
import threading

import pytest
import yaml

from config import rollout_cohorts as policy
from config.policy.batch import cohort_bucket, resolve_batch_policy
from database import rollout_cohorts as store
from scripts import render_backend_runtime_env as renderer
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils import rollout_cohorts as cohorts
from utils.rollout import runtime_percent as rp

ROOT = Path(__file__).resolve().parents[2]
SERVICES = ('backend', 'backend-sync', 'backend-sync-backfill', 'backend-integration')


@pytest.fixture
def runtime(monkeypatch):
    db = StrictFirestore()
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    monkeypatch.delenv('OMI_DEPLOYMENT', raising=False)
    monkeypatch.setattr(policy, '_percent_resolver', None)
    monkeypatch.setattr(policy, '_membership_resolver', cohorts._in_rollout_cohort)
    monkeypatch.setattr(cohorts.runtime_cohort, 'tokens', lambda: '')
    monkeypatch.setattr(rp, '_background_submitter', rp._submit_read)
    rp.configure_runtime_percent()

    def restart():
        def read():
            raw = db.rows.get(('rollout_cohorts', '_ramp'))
            return store.normalize_ramp_document(raw) if raw is not None else None

        monkeypatch.setattr(rp, '_cache', rp._RampCache(read))
        monkeypatch.setattr(
            cohorts,
            '_cache',
            cohorts._TTLReads(lambda uid: {'prod': {'batch-pipeline': uid == 'synthetic-allowlisted'}}),
        )

    restart()
    return db, restart


@pytest.mark.parametrize('service', SERVICES)
@pytest.mark.parametrize('percent', [0.0, 5.0, 25.0, 100.0])
def test_deploy_and_cold_process_preserve_effective_ramp(monkeypatch, runtime, service, percent):
    db, restart = runtime
    rp.write_ramp(
        'prod',
        {'percents': {'batch-pipeline': percent}},
        expected_revision=0,
        actor='lead',
        reason='seed',
        firestore_client=db,
    )
    before_store = deepcopy(db.rows)
    # This is the same manifest/rendering boundary the backend deploy action uses.
    manifest = yaml.load((ROOT / 'deploy/runtime_env.yaml').read_text(), Loader=yaml.CSafeLoader)
    config = manifest['environments']['prod']['cloud_run']['services'][service]
    for binding in config['env'].values():
        if 'env_var' in binding and 'default' not in binding and not binding.get('provisional'):
            monkeypatch.setenv(binding['env_var'], 'synthetic-render-input')
    env = {entry['name']: entry.get('value', '') for entry in renderer._render_env_entries(config['env'])}
    assert 'BATCH_PIPELINE_PERCENT' not in env
    assert 'BATCH_PIPELINE_PERCENT' not in renderer._remove_env_extra(service, config).split(',')
    assert 'BATCH_PIPELINE_PERCENT' not in renderer._action_removed_env_names(service)
    assert 'BATCH_PIPELINE_PERCENT' not in config.get('forbidden_env', [])

    for name, value in env.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv('BATCH_PIPELINE_PERCENT', '75')  # stale revision fallback cannot override remote zero
    monkeypatch.setenv('K_SERVICE', service)
    owners = ['synthetic-' + str(i) for i in range(200)] + ['synthetic-allowlisted']
    before = {uid: resolve_batch_policy(uid) for uid in owners}

    for name, value in env.items():
        monkeypatch.setenv(name, value)
    # Omitted env survives Cloud Run merge; a fresh install has no fallback at all.
    monkeypatch.delenv('BATCH_PIPELINE_PERCENT')
    restart()
    after = {uid: resolve_batch_policy(uid) for uid in owners}
    assert before == after
    assert all(value.batch_percent == percent for value in after.values())
    assert after['synthetic-allowlisted'].batch_allowlisted
    for uid in owners[:-1]:
        assert after[uid].batch_enabled == (cohort_bucket(uid, '') < percent)
    assert db.rows == before_store  # no config/history or cohort writes from deploy/serving


@pytest.mark.asyncio
async def test_async_admission_warms_remote_percent_and_membership_off_loop(monkeypatch, runtime):
    db, restart = runtime
    rp.write_ramp(
        'prod',
        {'percents': {'batch-pipeline': 5.0}},
        expected_revision=0,
        actor='lead',
        reason='seed',
        firestore_client=db,
    )
    restart()
    loop_thread = threading.get_ident()
    reads = []
    read = rp._cache.reader

    def tracked_read():
        reads.append(threading.get_ident())
        return read()

    rp._cache.reader = tracked_read
    monkeypatch.setenv('BATCH_PIPELINE_ENABLED', 'true')
    monkeypatch.delenv('BATCH_PIPELINE_PERCENT', raising=False)
    await asyncio.gather(*(cohorts._warm_rollout_cohorts('synthetic-allowlisted') for _ in range(20)))
    snapshot = resolve_batch_policy('synthetic-allowlisted')
    assert snapshot.batch_percent == 5.0 and snapshot.batch_allowlisted
    assert len(reads) == 1 and reads[0] != loop_thread


def test_unseeded_or_unreadable_cold_config_retains_env_fallback(monkeypatch, runtime):
    monkeypatch.setenv('BATCH_PIPELINE_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_PERCENT', '25')
    assert resolve_batch_policy('synthetic-owner').batch_percent == 25.0

    def unavailable():
        raise TimeoutError('synthetic config outage')

    monkeypatch.setattr(rp, '_cache', rp._RampCache(unavailable))
    assert resolve_batch_policy('synthetic-owner').batch_percent == 25.0
