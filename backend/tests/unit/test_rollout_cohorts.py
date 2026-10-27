"""Membership authority, read amplification, revocation and private operator output."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
import importlib.util
from pathlib import Path
import threading
from unittest.mock import MagicMock

import pytest

from utils import rollout_cohorts as cohorts


@pytest.fixture(scope='module', autouse=True)
def loaded_adapters():
    # Import/SDK initialization belongs to setup, outside fast-unit call budgets.
    import database._client
    import utils.executors


def cache(monkeypatch, reader, capacity=4096):
    cohorts.configure_rollout_runtime()
    value = cohorts._TTLReads(lambda uid: {cohorts.rollout_environment(): reader(uid)}, capacity)
    monkeypatch.setattr(cohorts, '_cache', value)
    return value


def test_all_flags_share_one_read_and_refresh_at_sixty_seconds(monkeypatch):
    clock = [0]
    monkeypatch.setattr(cohorts.time, 'monotonic', lambda: clock[0])
    reads = []
    cache(monkeypatch, lambda uid: reads.append(uid) or {'batch-pipeline': True, 'first-summary': True})
    for _ in range(1000):
        assert cohorts.in_rollout_cohort('synthetic-owner', 'batch-pipeline')
        assert cohorts.in_rollout_cohort('synthetic-owner', 'first-summary')
        assert not cohorts.in_rollout_cohort('synthetic-owner', 'dream-agent')
    assert reads == ['synthetic-owner']
    clock[0] = 59.999
    assert cohorts.in_rollout_cohort('synthetic-owner', 'batch-pipeline')
    assert len(reads) == 1
    clock[0] = 60
    assert cohorts.in_rollout_cohort('synthetic-owner', 'batch-pipeline')
    assert len(reads) == 2


def test_missing_documents_negative_members_and_errors_are_cached(monkeypatch, caplog):
    clock = [0]
    monkeypatch.setattr(cohorts.time, 'monotonic', lambda: clock[0])
    reads = []

    def read(uid):
        reads.append(uid)
        if len(reads) == 1:
            return {}
        raise RuntimeError('private document path synthetic-owner')

    cache(monkeypatch, read)
    for _ in range(100):
        assert not cohorts.in_rollout_cohort('synthetic-owner', 'batch-pipeline')
    assert len(reads) == 1
    monkeypatch.setenv('BATCH_PIPELINE_UID_ALLOWLIST', 'synthetic-owner')
    assert cohorts.in_rollout_cohort('synthetic-owner', 'batch-pipeline')  # explicit migration fallback
    clock[0] = 60
    for _ in range(100):
        assert not cohorts.in_rollout_cohort('synthetic-owner', 'batch-pipeline')
    assert len(reads) == 2
    assert 'synthetic-owner' not in caplog.text
    assert 'outcome=denied' in caplog.text


def test_firestore_false_revokes_retained_env_and_other_flags_are_independent(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_UID_ALLOWLIST', 'synthetic-owner')
    cache(monkeypatch, lambda _: {'batch-pipeline': False, 'first-summary': True})
    assert not cohorts.in_rollout_cohort('synthetic-owner', 'batch-pipeline')
    assert cohorts.in_rollout_cohort('synthetic-owner', 'first-summary')
    assert not cohorts.in_rollout_cohort('synthetic-owner', 'first-summary-prefix')


def test_cache_capacity_evicts_completed_entries(monkeypatch):
    reads = []
    value = cache(monkeypatch, lambda uid: reads.append(uid) or {}, capacity=2)
    for uid in ['one', 'two', 'three', 'one']:
        assert not cohorts.in_rollout_cohort(uid, 'batch-pipeline')
        assert len(value.entries) <= 2
    assert reads == ['one', 'two', 'three', 'one']


def test_concurrent_cold_reads_are_single_flight(monkeypatch):
    started, release = threading.Event(), threading.Event()
    reads = []

    def read(uid):
        reads.append(uid)
        started.set()
        assert release.wait(1)
        return {'batch-pipeline': True}

    cache(monkeypatch, read)
    with ThreadPoolExecutor(max_workers=12) as pool:
        futures = [pool.submit(cohorts.in_rollout_cohort, 'owner', 'batch-pipeline') for _ in range(12)]
        assert started.wait(1)
        release.set()
        assert all(f.result(1) for f in futures)
    assert reads == ['owner']


@pytest.mark.asyncio
async def test_async_miss_denies_and_listen_warmup_reads_off_loop_once(monkeypatch):
    loop_thread = threading.get_ident()
    read_threads = []

    def read(_uid):
        read_threads.append(threading.get_ident())
        return {'batch-pipeline': True}

    cache(monkeypatch, read)
    await asyncio.gather(*(cohorts.warm_rollout_cohorts('owner') for _ in range(20)))
    assert cohorts.in_rollout_cohort('owner', 'batch-pipeline')
    assert len(read_threads) == 1 and read_threads[0] != loop_thread


@pytest.mark.asyncio
async def test_expired_positive_never_serves_stale_grant(monkeypatch):
    now = [0]
    monkeypatch.setattr(cohorts.time, 'monotonic', lambda: now[0])
    value = cache(monkeypatch, lambda _: {'batch-pipeline': True})
    # Preload explicitly, as listen does before admission.
    await cohorts.warm_rollout_cohorts('owner')
    assert cohorts.in_rollout_cohort('owner', 'batch-pipeline')
    now[0] = 60
    queued = []
    monkeypatch.setattr(
        'utils.executors.get_rollout_executor',
        lambda: type('Queue', (), {'submit': lambda self, *a: queued.append(a)})(),
    )
    assert not cohorts.in_rollout_cohort('owner', 'batch-pipeline')
    assert len(queued) == 1
    assert not cohorts.in_rollout_cohort('owner', 'batch-pipeline')
    assert len(queued) == 1 and len(value.entries) == 1


def test_bad_uid_and_unknown_cohort_do_not_read(monkeypatch):
    reader = MagicMock()
    cache(monkeypatch, reader)
    for uid, name in [('', 'batch-pipeline'), ('bad/uid', 'batch-pipeline'), ('owner', 'typo')]:
        assert not cohorts.in_rollout_cohort(uid, name)
    reader.assert_not_called()


def test_real_adapter_bounds_rpc_and_validates_document(monkeypatch):
    client = MagicMock()
    monkeypatch.setattr('database.rollout_cohorts.get_data_plane_firestore_client', lambda: client)
    doc = client.collection.return_value.document.return_value.get.return_value
    doc.exists = False
    assert cohorts.read_memberships('owner') == {}
    injected = MagicMock(name='injected')
    injected.collection.return_value.document.return_value.get.return_value.exists = False
    assert cohorts.read_memberships('owner', firestore_client=injected) == {}
    injected.collection.assert_called_with('rollout_cohorts')
    doc.exists = True
    doc.to_dict.return_value = {'cohorts': {'prod': {'batch-pipeline': True}}}
    assert cohorts.read_memberships('owner') == {'prod': {'batch-pipeline': True}}
    client.collection.assert_called_with('rollout_cohorts')
    client.collection.return_value.document.return_value.get.assert_called_with(timeout=1.0, retry=None)
    for malformed in [None, {}, {'cohorts': []}, {'cohorts': {'batch-pipeline': 'true'}}]:
        doc.to_dict.return_value = malformed
        with pytest.raises(ValueError):
            cohorts.read_memberships('owner')


def test_absent_keys_preserve_each_legacy_contract(monkeypatch):
    from config import summary_guarantee, sync_lineage

    cache(monkeypatch, lambda _: {})
    monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_ENABLED', 'true')
    monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_PERCENT', '0')
    monkeypatch.delenv('FIRST_SUMMARY_UID_ALLOWLIST', raising=False)
    monkeypatch.delenv('SYNC_LINEAGE_RESOLVE_UID_ALLOWLIST', raising=False)
    assert not summary_guarantee.enabled('owner')
    assert sync_lineage.sync_lineage_resolve_uid_allowed('owner')
    # Main #22113 makes first-summary empty deny; lineage retains its legacy empty contract.
    monkeypatch.setenv('FIRST_SUMMARY_UID_ALLOWLIST', '')
    monkeypatch.setenv('SYNC_LINEAGE_RESOLVE_UID_ALLOWLIST', '')
    assert not summary_guarantee.enabled('owner')
    assert sync_lineage.sync_lineage_resolve_uid_allowed('owner')


def test_disabled_batch_flag_does_not_fetch_cohorts(monkeypatch):
    from config.batch_pipeline import enabled_for

    reader = MagicMock()
    cache(monkeypatch, reader)
    monkeypatch.setenv('BATCH_PIPELINE_ENABLED', 'false')
    assert not enabled_for('owner')
    reader.assert_not_called()


def operator():
    path = Path(__file__).resolve().parents[2] / 'scripts/rollout_cohort.py'
    spec = importlib.util.spec_from_file_location('cohort_operator', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('environment', ['dev', 'prod'])
@pytest.mark.parametrize('apply', [False, True])
@pytest.mark.parametrize('operation', ['--add', '--remove'])
def test_operator_dry_run_or_single_merge_write_without_uid(
    monkeypatch, tmp_path, capsys, apply, operation, environment
):
    uid_file = tmp_path / 'private.uid'
    uid_file.write_text('synthetic-private-owner\n')
    monkeypatch.setenv('GCP_AGENT_TIER', 'prod-operator')
    monkeypatch.setenv('GOOGLE_APPLICATION_CREDENTIALS', '/private/operator.json')
    factory = MagicMock()
    args = [
        '--uid-file',
        str(uid_file),
        '--cohort',
        'batch-pipeline',
        '--project',
        'based-hardware',
        '--environment',
        environment,
        operation,
    ]
    args.append('--apply' if apply else '--dry-run')
    assert operator().main(args, client_factory=factory) == 0
    assert 'synthetic-private-owner' not in capsys.readouterr().out
    if apply:
        factory.assert_called_once_with(project='based-hardware')
        factory.return_value.collection.return_value.document.return_value.set.assert_called_once_with(
            {'cohorts': {environment: {'batch-pipeline': operation == '--add'}}}, merge=True, timeout=3.0, retry=None
        )
    else:
        factory.assert_not_called()


def test_operator_suppresses_sdk_document_paths_and_requires_operator_tier(monkeypatch, tmp_path, capsys):
    uid_file = tmp_path / 'private.uid'
    uid_file.write_text('synthetic-private-owner')
    args = [
        '--uid-file',
        str(uid_file),
        '--cohort',
        'batch-pipeline',
        '--project',
        'based-hardware',
        '--environment',
        'prod',
        '--add',
        '--apply',
    ]
    factory = MagicMock(side_effect=RuntimeError('documents/rollout_cohorts/synthetic-private-owner'))
    monkeypatch.delenv('GCP_AGENT_TIER', raising=False)
    assert operator().main(args, client_factory=factory) == 2
    factory.assert_not_called()
    monkeypatch.setenv('GCP_AGENT_TIER', 'prod-operator')
    monkeypatch.setenv('GOOGLE_APPLICATION_CREDENTIALS', '/private/operator.json')
    assert operator().main(args, client_factory=factory) == 1
    assert 'synthetic-private-owner' not in capsys.readouterr().err


@pytest.mark.parametrize('members', [{'first-summary': False, 'sync-lineage-resolve': False}, None])
def test_firestore_denial_beats_even_legacy_enable_all(monkeypatch, members):
    from config import summary_guarantee, sync_lineage

    def read(_):
        if members is None:
            raise RuntimeError('unavailable')
        return members

    cache(monkeypatch, read)
    monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_ENABLED', 'true')
    monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_PERCENT', '0')
    monkeypatch.setenv('FIRST_SUMMARY_UID_ALLOWLIST', '')
    monkeypatch.setenv('SYNC_LINEAGE_RESOLVE_UID_ALLOWLIST', '')
    assert not summary_guarantee.enabled('owner')
    assert not sync_lineage.sync_lineage_resolve_uid_allowed('owner')


def test_operator_merge_mask_preserves_other_cohort_fields():
    from google.cloud.firestore_v1._helpers import pbs_for_set_with_merge

    writes = pbs_for_set_with_merge(
        'projects/synthetic/databases/(default)/documents/rollout_cohorts/owner',
        {'cohorts': {'prod': {'batch-pipeline': False}}},
        merge=True,
    )
    assert list(writes[0].update_mask.field_paths) == ['cohorts.prod.`batch-pipeline`']


@pytest.mark.asyncio
async def test_cache_and_executor_saturation_deny_without_unbounded_work(monkeypatch):
    queued = []
    monkeypatch.setattr(
        'utils.executors.get_rollout_executor',
        lambda: type('Queue', (), {'submit': lambda self, *a: queued.append(a)})(),
    )
    value = cache(monkeypatch, lambda _: {'batch-pipeline': True}, capacity=2)
    for uid in ['one', 'two', 'three', 'three']:
        assert not cohorts.in_rollout_cohort(uid, 'batch-pipeline')
    assert len(queued) == 2 and len(value.entries) == 2

    def reject(*_):
        raise RuntimeError('saturated')

    monkeypatch.setattr('utils.executors.get_rollout_executor', lambda: type('Reject', (), {'submit': reject})())
    cache(monkeypatch, lambda _: {'batch-pipeline': True})
    assert not cohorts.in_rollout_cohort('owner', 'batch-pipeline')
    assert not cohorts.in_rollout_cohort('owner', 'batch-pipeline')


def test_shared_customer_project_never_unions_dev_and_prod_members(monkeypatch):
    cohorts.configure_rollout_runtime()
    reads = []
    value = cohorts._TTLReads(
        lambda uid: reads.append(uid)
        or {
            'dev': {'batch-pipeline': True, 'first-summary': False},
            'prod': {'batch-pipeline': False, 'first-summary': True},
        }
    )
    monkeypatch.setattr(cohorts, '_cache', value)
    for _ in range(100):
        monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
        assert cohorts.in_rollout_cohort('owner', 'batch-pipeline')
        assert not cohorts.in_rollout_cohort('owner', 'first-summary')
        monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
        assert not cohorts.in_rollout_cohort('owner', 'batch-pipeline')
        assert cohorts.in_rollout_cohort('owner', 'first-summary')
    assert reads == ['owner']
    monkeypatch.setenv('OMI_ENV_STAGE', 'typo')
    assert not cohorts.in_rollout_cohort('owner', 'first-summary')


def test_background_discovery_is_environment_scoped(monkeypatch):
    cohorts.configure_rollout_runtime()
    keys = []
    monkeypatch.setattr(cohorts, '_member_cache', cohorts._TTLReads(lambda key: keys.append(key) or ('owner',)))
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    assert cohorts.rollout_cohort_members('dream-agent') == ('owner',)
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    assert cohorts.rollout_cohort_members('dream-agent') == ('owner',)
    assert keys == ['dev:dream-agent', 'prod:dream-agent']


@pytest.mark.asyncio
async def test_unconfigured_scheduler_denies_without_database_importing_utils(monkeypatch):
    monkeypatch.setattr(cohorts, '_background_submitter', None)
    cache(monkeypatch, MagicMock(side_effect=AssertionError('must not read on loop')))
    await cohorts.warm_rollout_cohorts('owner')
    assert not cohorts.in_rollout_cohort('owner', 'batch-pipeline')
    import ast

    tree = ast.parse((Path(__file__).parents[2] / 'database/rollout_cohorts.py').read_text())
    assert not any(
        isinstance(node, ast.ImportFrom) and (node.module or '').startswith('utils') for node in ast.walk(tree)
    )


def test_config_cohorts_has_only_stdlib_and_lazy_shared_bucket_dependency():
    import ast

    tree = ast.parse((Path(__file__).parents[2] / 'config/rollout_cohorts.py').read_text())
    assert {node.module for node in tree.body if isinstance(node, ast.ImportFrom)} <= {'__future__', 'typing'}
    shared = [
        node for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module == 'config.policy.batch'
    ]
    bucket = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'cohort_bucket')
    assert len(shared) == 1 and shared[0] in bucket.body
    assert [alias.name for alias in shared[0].names] == ['cohort_bucket']
    assert {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)} <= {
        '__future__',
        'typing',
        'config.policy.batch',
    }
    assert {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names} == {
        'os',
    }


def test_serving_composition_roots_bind_private_cohort_runtime():
    for relative in (
        'main.py',
        'pusher/main.py',
        'scripts/dream-agent.py',
        'scripts/dream-replay.py',
        'scripts/batch_pipeline_held_disposition.py',
        'scripts/batch_pipeline_speech_redrive.py',
        'scripts/batch_pipeline_terminal_empty.py',
    ):
        text = (Path(__file__).parents[2] / relative).read_text()
        assert 'from utils.rollout_cohorts import configure_rollout_runtime' in text
        assert 'configure_rollout_runtime()' in text
