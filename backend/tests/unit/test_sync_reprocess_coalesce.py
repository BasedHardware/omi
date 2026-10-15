"""Quiet-window state transitions; persistence/contention is proved on the emulator."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from config import sync_reprocess as flags
from utils.sync import reprocess

_ENQUEUE = reprocess._enqueue


@pytest.fixture
def state(monkeypatch):
    rows, tasks = {}, []

    def mutate(key, operation):
        new, result = operation(deepcopy(rows.get(key)))
        if new is None:
            rows.pop(key, None)
        else:
            rows[key] = deepcopy(new)
        return result

    monkeypatch.setattr(reprocess, 'owns_runtime', lambda: True)
    monkeypatch.setattr(reprocess, '_mutate', mutate)
    monkeypatch.setattr(reprocess, '_enqueue', lambda row: tasks.append(deepcopy(row)))
    monkeypatch.setenv('SYNC_REPROCESS_SETTLE_SECONDS', '600')
    return rows, tasks


def test_n_appends_one_pass_after_last_append_settles(state):
    rows, tasks = state
    for now in range(0, 500, 100):
        reprocess.mark('u', 'c', 'en', now=now)
    assert len(tasks) == 1
    process = Mock()
    key = reprocess.key('u', 'c')
    assert reprocess.run(key, tasks[0]['task_token'], process, now=600) == 'deferred'
    process.assert_not_called()
    assert len(tasks) == 2  # Replace the delivered wake; no per-append tasks.
    assert reprocess.run(key, tasks[1]['task_token'], process, now=1000) == 'processed'
    process.assert_called_once_with('u', 'c', 'en')
    assert not rows
    assert reprocess.run(key, tasks[0]['task_token'], process, now=1001) == 'stale'
    process.assert_called_once()


def test_delayed_older_mark_cannot_shorten_the_quiet_window(state):
    rows, tasks = state
    reprocess.mark('u', 'c', 'en', now=100)
    reprocess.mark('u', 'c', 'en', now=50)
    assert rows[reprocess.key('u', 'c')]['due_at'] == 700
    process = Mock()
    reprocess.run(reprocess.key('u', 'c'), tasks[-1]['task_token'], process, now=650)
    process.assert_not_called()


def test_append_after_window_gets_second_pass_and_fresh_task_name(state):
    rows, tasks = state
    process = Mock()
    key = reprocess.key('u', 'c')
    reprocess.mark('u', 'c', 'en', now=0)
    reprocess.run(key, tasks[-1]['task_token'], process, now=600)
    first_token = tasks[-1]['task_token']
    reprocess.mark('u', 'c', 'fr', now=601)
    assert tasks[-1]['task_token'] != first_token
    reprocess.run(key, tasks[-1]['task_token'], process, now=1201)
    assert process.call_count == 2 and not rows
    assert process.call_args.args == ('u', 'c', 'fr')


def test_append_while_processing_stays_owed(state):
    rows, tasks = state
    reprocess.mark('u', 'c', 'en', now=0)
    key = reprocess.key('u', 'c')
    reprocess.run(key, tasks[-1]['task_token'], lambda *a: reprocess.mark(*a, now=601), now=600)
    assert key in rows and len(tasks) == 2
    process = Mock()
    reprocess.run(key, tasks[-1]['task_token'], process, now=1201)
    process.assert_called_once()
    assert not rows


def test_lease_prevents_duplicate_processing_and_crash_is_recoverable(state):
    rows, tasks = state
    reprocess.mark('u', 'c', 'en', now=0)
    key, token = reprocess.key('u', 'c'), tasks[-1]['task_token']
    process = Mock(side_effect=RuntimeError('crash'))
    with pytest.raises(RuntimeError):
        reprocess.run(key, token, process, now=600)
    assert key in rows
    assert reprocess.run(key, token, process, now=601) == 'busy'
    recovered = Mock()
    assert reprocess.run(key, token, recovered, now=600 + reprocess.LEASE_SECONDS) == 'processed'
    recovered.assert_called_once()
    assert not rows


def test_sweep_recovers_dirty_without_task(state, monkeypatch):
    rows, tasks = state
    enqueue = reprocess._enqueue
    monkeypatch.setattr(reprocess, '_enqueue', Mock(side_effect=RuntimeError('lost enqueue')))
    with pytest.raises(RuntimeError):
        reprocess.mark('u', 'c', 'en', now=0)
    assert len(rows) == 1 and not tasks
    query = Mock()
    query.where.return_value = query
    query.order_by.return_value = query
    query.limit.return_value = query
    query.stream.return_value = [SimpleNamespace(id=reprocess.key('u', 'c'))]
    monkeypatch.setattr(reprocess, 'get_firestore_client', lambda: SimpleNamespace(collection=lambda _: query))
    monkeypatch.setattr(reprocess, '_enqueue', enqueue)
    assert reprocess.sweep(now=600) == {'repaired': 1, 'error': 0}
    process = Mock()
    reprocess.run(reprocess.key('u', 'c'), tasks[-1]['task_token'], process, now=600)
    process.assert_called_once()
    assert not rows


def test_sweep_rotates_exhausted_task_name(state, monkeypatch):
    rows, tasks = state
    reprocess.mark('u', 'c', 'en', now=0)
    key = reprocess.key('u', 'c')
    old = tasks[-1]['task_token']
    query = Mock()
    query.where.return_value = query
    query.order_by.return_value = query
    query.limit.return_value = query
    query.stream.return_value = [SimpleNamespace(id=key)]
    monkeypatch.setattr(reprocess, 'get_firestore_client', lambda: SimpleNamespace(collection=lambda _: query))
    reprocess.sweep(now=600 + reprocess.REPAIR_SECONDS)
    assert tasks[-1]['task_token'] != old
    assert reprocess.run(key, old, Mock(), now=2400) == 'stale'


def test_flags_default_off(monkeypatch):
    monkeypatch.delenv('SYNC_REPROCESS_COALESCE_ENABLED', raising=False)
    monkeypatch.delenv('CONVERSATION_LLM_INPUT_DEDUPE_ENABLED', raising=False)
    assert not flags.coalesce_enabled() and not flags.dedupe_enabled()


@pytest.fixture(scope='module')
def pipeline():
    from pathlib import Path
    from testing.import_isolation import load_module_fresh, stub_modules
    from tests.unit.test_sync_geolocation_enrichment import _build_pipeline_fakes

    with stub_modules(_build_pipeline_fakes()):
        yield load_module_fresh('utils.sync.pipeline', Path(__file__).resolve().parents[2] / 'utils/sync/pipeline.py')


def test_pipeline_flags_off_eager_and_process_now_bypasses_coalescing(monkeypatch, pipeline):
    process, mark = Mock(), Mock()
    monkeypatch.setattr(pipeline, '_reprocess_conversation_after_update', process)
    monkeypatch.setattr(reprocess, 'mark', mark)
    monkeypatch.setenv('SYNC_REPROCESS_COALESCE_ENABLED', 'false')
    pipeline._reprocess_merged_conversations('u', {'_merged': {'c': 'en'}})
    process.assert_called_once_with('u', 'c', 'en')
    mark.assert_not_called()
    monkeypatch.setenv('SYNC_REPROCESS_COALESCE_ENABLED', 'true')
    pipeline._reprocess_merged_conversations('u', {'_merged': {'c': 'en'}})
    mark.assert_called_once_with('u', 'c', 'en')
    process.assert_called_once()
    pipeline._reprocess_merged_conversations('u', {'_merged': {'c': 'en'}}, user_selected=True)
    assert process.call_count == 2 and mark.call_count == 1


def test_dev_sweep_does_not_read_the_shared_production_store(monkeypatch):
    monkeypatch.setattr(reprocess, 'owns_runtime', lambda: False)
    read = Mock(side_effect=AssertionError('dev must not touch prod outbox'))
    monkeypatch.setattr(reprocess, 'get_firestore_client', read)
    assert reprocess.sweep() == {'repaired': 0, 'error': 0}
    read.assert_not_called()


def test_partial_result_replay_recovers_intent_without_transient_merged_map(pipeline, monkeypatch):
    monkeypatch.setenv('SYNC_REPROCESS_COALESCE_ENABLED', 'true')
    mark = Mock()
    monkeypatch.setattr(reprocess, 'mark', mark)
    response = {'updated_memories': {'c', 'fenced'}, pipeline._RESPONSE_FENCED_CONVERSATION_IDS: {'fenced'}}
    pipeline._reprocess_merged_conversations('u', response)
    mark.assert_called_once_with('u', 'c', pipeline._LINEAGE_RETRY_LANGUAGE)


def test_backfill_recovery_retains_its_queue_worker_and_identity(state, monkeypatch):
    rows, tasks = state
    from utils import cloud_tasks

    enqueue = Mock()
    monkeypatch.setattr(cloud_tasks, 'enqueue_named_task', enqueue)
    monkeypatch.setenv('SYNC_TASKS_QUEUE', 'sync-backfill')
    monkeypatch.setenv('SYNC_TASKS_HANDLER_URL', 'https://backfill.invalid/v2/sync-jobs/run')
    monkeypatch.setenv('SYNC_TASKS_OIDC_AUDIENCE', 'backfill-audience')
    monkeypatch.setenv('SYNC_TASKS_INVOKER_SA', 'backfill-invoker@example.invalid')
    reprocess.mark('u', 'c', 'en', now=0)
    row = rows[reprocess.key('u', 'c')]
    monkeypatch.setenv('SYNC_TASKS_QUEUE', 'sync-jobs')
    monkeypatch.setenv('SYNC_TASKS_HANDLER_URL', 'https://fresh.invalid/v2/sync-jobs/run')
    monkeypatch.setenv('SYNC_TASKS_OIDC_AUDIENCE', 'fresh-audience')
    monkeypatch.setenv('SYNC_TASKS_INVOKER_SA', 'fresh-invoker@example.invalid')
    _ENQUEUE(row)
    assert enqueue.call_args.args[0:2] == ('sync-backfill', 'https://backfill.invalid/v2/sync-jobs/run')
    assert enqueue.call_args.kwargs['audience'] == 'backfill-audience'
    assert enqueue.call_args.kwargs['invoker_sa'] == 'backfill-invoker@example.invalid'
    assert enqueue.call_args.kwargs['schedule_at'] == 600


@pytest.fixture(scope='module')
def runtime_manifest():
    from pathlib import Path
    import yaml

    path = Path(__file__).resolve().parents[2] / 'deploy/runtime_env.yaml'
    return yaml.load(path.read_text(), Loader=getattr(yaml, 'CSafeLoader', yaml.SafeLoader))


def test_train1_runtime_flags_are_on_only_for_prod_sync_hosts(runtime_manifest):
    selected = {'backend-sync', 'backend-sync-backfill'}
    switches = ('SYNC_REPROCESS_COALESCE_ENABLED', 'CONVERSATION_LLM_INPUT_DEDUPE_ENABLED')
    for stage, environment in runtime_manifest['environments'].items():
        for name, service in environment['cloud_run']['services'].items():
            env = service.get('env', {})
            for switch in switches:
                enabled = str(env.get(switch, {}).get('value', 'false')).lower() == 'true'
                assert enabled == (stage == 'prod' and name in selected), (stage, name, switch)
            if name in selected:
                assert env['SYNC_REPROCESS_SETTLE_SECONDS']['value'] == '600'
        for name, service in environment['gke'].items():
            for switch in switches:
                assert str(service.get('env', {}).get(switch, {}).get('value', 'false')).lower() != 'true'


@pytest.fixture(scope='module')
def sync_router():
    import importlib
    from testing.import_isolation import stub_modules

    with stub_modules({}):
        yield importlib.import_module('routers.sync')


@pytest.mark.parametrize(
    'sequencer_errors,repair_errors,repair_raises,status',
    [
        (0, 2, False, 200),
        (0, 0, True, 200),
        (1, 0, False, 500),
    ],
)
def test_sweep_reports_repair_errors_without_failing_successful_retirement(
    sync_router, monkeypatch, sequencer_errors, repair_errors, repair_raises, status
):
    import asyncio
    import json

    async def run(_executor, fn):
        return fn()

    monkeypatch.setattr(sync_router, 'run_blocking', run)
    monkeypatch.setattr(sync_router.uid_sequencer, 'sweep', Mock(return_value={'error': sequencer_errors}))
    monkeypatch.setattr(reprocess, 'owns_runtime', lambda: True)
    repair = Mock(return_value={'repaired': 3, 'error': repair_errors})
    if repair_raises:
        repair.side_effect = RuntimeError('query failed')
    monkeypatch.setattr(reprocess, 'sweep', repair)
    response = asyncio.run(sync_router.sweep_sync_backfill_sequencer(0))
    assert response.status_code == status
    assert json.loads(response.body)['outcomes'] == {
        'error': sequencer_errors,
        'reprocess_repaired': 0 if repair_raises else 3,
        'reprocess_repair_errors': 1 if repair_raises else repair_errors,
    }
