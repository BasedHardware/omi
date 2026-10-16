"""Quiet-window state transitions; persistence/contention is proved on the emulator."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from config import sync_reprocess as flags
from utils.sync import reprocess

_ENQUEUE = reprocess._enqueue
_MUTATE = reprocess._mutate


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
    monkeypatch.setenv('SYNC_TASKS_QUEUE', 'sync-jobs')
    monkeypatch.setenv('SYNC_TASKS_HANDLER_URL', 'https://fresh.invalid/v2/sync-jobs/run')
    monkeypatch.delenv('SYNC_TASKS_OIDC_AUDIENCE', raising=False)
    monkeypatch.setenv('SYNC_TASKS_INVOKER_SA', 'invoker@example.invalid')
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


@pytest.mark.parametrize(
    'stage,namespace,emulator,expected',
    [
        ('prod', 'batch_pipeline_prod', None, True),
        ('dev', 'batch_pipeline_dev', None, False),
        ('dev', 'batch_pipeline_prod', None, False),
        ('dev', 'arbitrary_namespace', None, False),
        ('dev', None, None, False),
        ('local', 'batch_pipeline_dev', None, False),
        ('dev', 'batch_pipeline_dev', '127.0.0.1:8080', True),
    ],
)
def test_owns_runtime_only_allows_production_or_emulator(monkeypatch, stage, namespace, emulator, expected):
    monkeypatch.setenv('OMI_ENV_STAGE', stage)
    if namespace is None:
        monkeypatch.delenv('BATCH_PIPELINE_NAMESPACE', raising=False)
    else:
        monkeypatch.setenv('BATCH_PIPELINE_NAMESPACE', namespace)
    if emulator is None:
        monkeypatch.delenv('FIRESTORE_EMULATOR_HOST', raising=False)
    else:
        monkeypatch.setenv('FIRESTORE_EMULATOR_HOST', emulator)

    assert reprocess.owns_runtime() is expected


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
    monkeypatch.setenv('SYNC_TASKS_OIDC_AUDIENCE', 'https://backfill.invalid/v2/sync-jobs/run')
    monkeypatch.setenv('SYNC_TASKS_INVOKER_SA', 'backfill-invoker@example.invalid')
    reprocess.mark('u', 'c', 'en', now=0)
    row = rows[reprocess.key('u', 'c')]
    monkeypatch.setenv('SYNC_TASKS_QUEUE', 'sync-jobs')
    monkeypatch.setenv('SYNC_TASKS_HANDLER_URL', 'https://fresh.invalid/v2/sync-jobs/run')
    monkeypatch.setenv('SYNC_TASKS_OIDC_AUDIENCE', 'https://fresh.invalid/v2/sync-jobs/run')
    monkeypatch.setenv('SYNC_TASKS_INVOKER_SA', 'fresh-invoker@example.invalid')
    _ENQUEUE(row)
    assert enqueue.call_args.args[0:2] == ('sync-backfill', 'https://backfill.invalid/v2/sync-jobs/run')
    assert enqueue.call_args.kwargs['audience'] == 'https://backfill.invalid/v2/sync-jobs/run'
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


@pytest.fixture
def sweep_query(state, monkeypatch):
    rows, _ = state
    query = Mock()
    query.where.return_value = query
    query.order_by.return_value = query
    query.limit.return_value = query
    query.stream.side_effect = lambda: [SimpleNamespace(id=key) for key in list(rows)]
    monkeypatch.setattr(reprocess, 'get_firestore_client', lambda: SimpleNamespace(collection=lambda _: query))
    return query


@pytest.mark.parametrize('poison', [None, {}, {'queue': ''}, 'invalid'])
def test_sweep_rebinds_poison_in_cas_and_fences_old_delivery(state, sweep_query, poison):
    rows, tasks = state
    reprocess.mark('u', 'c', 'en', now=0)
    key = reprocess.key('u', 'c')
    original = deepcopy(rows[key])
    rows[key]['dispatch'] = poison
    assert reprocess.sweep(now=600) == {'repaired': 1, 'error': 0}
    repaired = rows[key]
    assert repaired['dispatch'] == reprocess._dispatch_binding()
    assert repaired['task_token'] != original['task_token']
    assert repaired['version'] == original['version'] and repaired['due_at'] == original['due_at']
    assert tasks[-1] == repaired  # The binding/token are durable before enqueue.
    process = Mock()
    assert reprocess.run(key, original['task_token'], process, now=600) == 'stale'
    process.assert_not_called()
    assert reprocess.run(key, repaired['task_token'], process, now=600) == 'processed'
    assert not rows


@pytest.mark.parametrize('field', ['queue', 'handler', 'audience', 'invoker_sa'])
def test_sweep_repairs_each_missing_binding_field(state, sweep_query, field):
    rows, _ = state
    reprocess.mark('u', 'c', 'en', now=0)
    rows[reprocess.key('u', 'c')]['dispatch'][field] = ''
    assert reprocess.sweep(now=600) == {'repaired': 1, 'error': 0}
    assert rows[reprocess.key('u', 'c')]['dispatch'] == reprocess._dispatch_binding()


def test_unbound_host_leaves_claimable_obligation_without_error_storm(state, sweep_query, monkeypatch, caplog):
    rows, tasks = state
    monkeypatch.delenv('SYNC_TASKS_QUEUE')
    reprocess.mark('u', 'c', 'en', now=0)
    key = reprocess.key('u', 'c')
    assert rows[key]['dispatch'] is None and not tasks
    # Includes a legacy poison row: neither row is rewritten or enqueued here.
    reprocess.mark('u', 'poison', 'en', now=0)
    rows[reprocess.key('u', 'poison')]['dispatch'] = {'queue': ''}
    original = deepcopy(rows)
    before = reprocess.UNBOUND.labels(action='repair')._value.get()
    for _ in range(3):
        assert reprocess.sweep(now=600) == {'repaired': 0, 'error': 0}
    assert rows == original and not tasks
    assert reprocess.UNBOUND.labels(action='repair')._value.get() == before + 6
    assert not caplog.records
    monkeypatch.setenv('SYNC_TASKS_QUEUE', 'sync-jobs')
    assert reprocess.sweep(now=600) == {'repaired': 2, 'error': 0}
    assert len(tasks) == 2


def test_rebinding_waits_for_lease_and_cannot_finish_another_owner(state, sweep_query):
    rows, tasks = state
    reprocess.mark('u', 'c', 'en', now=0)
    key = reprocess.key('u', 'c')
    rows[key].update(dispatch=None, lease_until=700, owner='other')
    original = deepcopy(rows[key])
    assert reprocess.sweep(now=600) == {'repaired': 0, 'error': 0}
    assert rows[key] == original and len(tasks) == 1
    assert reprocess.sweep(now=700) == {'repaired': 1, 'error': 0}

    def supersede(*_):
        rows[key]['owner'] = 'new-owner'

    assert reprocess.run(key, tasks[-1]['task_token'], supersede, now=700) == 'processed'
    assert rows[key]['owner'] == 'new-owner'


def test_sweep_keeps_valid_backfill_binding_on_fresh_host(state, sweep_query):
    rows, tasks = state
    reprocess.mark('u', 'c', 'en', now=0)
    binding = {
        'queue': 'sync-backfill',
        'handler': 'https://backfill.invalid/v2/sync-jobs/run',
        'audience': 'https://backfill.invalid/v2/sync-jobs/run',
        'invoker_sa': 'backfill@example.invalid',
    }
    rows[reprocess.key('u', 'c')]['dispatch'] = binding
    assert reprocess.sweep(now=600) == {'repaired': 1, 'error': 0}
    assert tasks[-1]['dispatch'] == binding


@pytest.mark.parametrize(
    'handler,audience',
    [
        ('https://fresh.invalid/v2/audio-merge-jobs/run', 'https://fresh.invalid/v2/audio-merge-jobs/run'),
        ('https://fresh.invalid/v2/sync-jobs/run', 'https://sibling.invalid/v2/sync-jobs/run'),
        ('https://fresh.invalid/v2/sync-jobs/run?extra=1', 'https://fresh.invalid/v2/sync-jobs/run?extra=1'),
    ],
)
def test_mark_never_persists_invalid_worker_or_sibling_audience(state, monkeypatch, handler, audience):
    rows, tasks = state
    monkeypatch.setenv('SYNC_TASKS_HANDLER_URL', handler)
    monkeypatch.setenv('SYNC_TASKS_OIDC_AUDIENCE', audience)
    reprocess.mark('u', 'c', 'en', now=0)
    assert rows[reprocess.key('u', 'c')]['dispatch'] is None and not tasks


def test_integration_manifest_has_fresh_worker_queue_and_receiving_audience(runtime_manifest):
    env = runtime_manifest['environments']['prod']['cloud_run']['services']['backend-integration']['env']
    assert env['SYNC_TASKS_QUEUE']['value'] == 'sync-jobs'
    assert env['SYNC_TASKS_OIDC_AUDIENCE']['env_var'] == env['SYNC_TASKS_HANDLER_URL']['env_var']
    assert env['SYNC_TASKS_INVOKER_SA']['env_var'] == 'SYNC_TASKS_INVOKER_SA'


def test_rebind_cas_conflict_rereads_a_new_lease(state, sweep_query, monkeypatch):
    from google.api_core.exceptions import FailedPrecondition

    rows, tasks = state
    reprocess.mark('u', 'c', 'en', now=0)
    poisoned = deepcopy(rows[reprocess.key('u', 'c')])
    poisoned['dispatch'] = None
    leased = {**poisoned, 'lease_until': 900, 'owner': 'winning-worker'}
    ref = Mock()
    ref.get.side_effect = [
        SimpleNamespace(exists=True, update_time=None, to_dict=lambda: deepcopy(poisoned)),
        SimpleNamespace(exists=True, update_time=None, to_dict=lambda: deepcopy(leased)),
    ]
    ref.update.side_effect = FailedPrecondition('CAS conflict')
    client = Mock()
    client.collection.return_value = sweep_query
    sweep_query.document.return_value = ref
    monkeypatch.setattr(reprocess, 'get_firestore_client', lambda: client)
    monkeypatch.setattr(reprocess, '_mutate', _MUTATE)
    monkeypatch.setattr(reprocess.time, 'sleep', lambda _: None)
    assert reprocess.sweep(now=600) == {'repaired': 0, 'error': 0}
    assert ref.get.call_count == 2 and ref.update.call_count == 1
    assert ref.update.call_args.kwargs['option'] is not None
    assert len(tasks) == 1  # The failed CAS never dispatches its tentative token.


def test_repeat_work_window_has_a_hard_ceiling_without_a_second_queue(state, monkeypatch):
    rows, tasks = state
    monkeypatch.setenv('REPEAT_WORK_REVISION_ENABLED', 'true')
    for now in range(0, 3600, 100):
        reprocess.mark('u', 'c', 'en', now=now)
    key = reprocess.key('u', 'c')
    assert rows[key]['due_at'] == 3600 and len(tasks) == 1
    process = Mock()
    assert reprocess.run(key, tasks[0]['task_token'], process, now=3600) == 'processed'
    process.assert_called_once()
    assert not rows


def test_repeat_work_deadline_survives_overlapping_revision_and_next_mark(state, monkeypatch):
    rows, tasks = state
    monkeypatch.setenv('REPEAT_WORK_REVISION_ENABLED', 'true')
    for now in range(0, 3600, 100):
        reprocess.mark('u', 'c', 'en', now=now)
    key = reprocess.key('u', 'c')
    assert rows[key]['first_pending_at'] == 0 and rows[key]['due_at'] == 3600
    assert (
        reprocess.run(key, tasks[0]['task_token'], lambda *_: reprocess.mark('u', 'c', 'en', now=3700), now=3600)
        == 'processed'
    )
    assert rows[key]['task_due_at'] == 3600
    reprocess.mark('u', 'c', 'en', now=3900)
    assert rows[key]['first_pending_at'] == 0
    assert rows[key]['due_at'] == rows[key]['task_due_at'] == 3600
    process = Mock()
    assert reprocess.run(key, tasks[-1]['task_token'], process, now=3900) == 'processed'
    process.assert_called_once_with('u', 'c', 'en')
    assert not rows
