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
    from utils.enrichment import scan as enrichment_scan

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
    monkeypatch.setattr(reprocess, '_wake_exists', lambda *_: False)
    monkeypatch.setattr(enrichment_scan, 'begin', lambda *_: (None, None))
    monkeypatch.setattr(enrichment_scan, 'finish', lambda *_: None)

    def empty_failure(_client, _collection, document_id, owner, token):
        row = rows[document_id]
        assert row['owner'] == owner and row['task_token'] == token
        row['summary_empty_failures'] = min(3, row.get('summary_empty_failures', 0) + 1)
        if row['summary_empty_failures'] == 3:
            row.update(dormant=True, due_at=None, lease_until=0, summary_blocked_reason='empty_output_exhausted')
            return True
        return False

    # Actual multi-document failure persistence is exercised by the emulator.
    monkeypatch.setattr(reprocess, 'record_empty_failure', empty_failure)
    monkeypatch.setattr(reprocess, 'get_firestore_client', lambda: None)
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


def test_expired_backfill_retirement_is_disabled_for_prod_sync_hosts(runtime_manifest):
    services = runtime_manifest['environments']['prod']['cloud_run']['services']
    for name in ('backend-sync', 'backend-sync-backfill'):
        assert services[name]['env']['SYNC_BACKFILL_RETIRE_EXPIRED_AT_CLAIM']['value'] == 'false'


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


def test_lazy_mark_blind_write_preserves_live_lease(monkeypatch):
    client, ref = Mock(), Mock()
    client.collection.return_value.document.return_value = ref
    monkeypatch.setattr(reprocess, 'owns_runtime', lambda: True)
    monkeypatch.setattr(reprocess, 'get_firestore_client', lambda: client)
    monkeypatch.setattr(
        reprocess,
        '_effects_binding',
        lambda: {
            'queue': 'existing',
            'handler': 'https://worker.invalid/v2/sync-jobs/run',
            'audience': 'https://worker.invalid/v2/sync-jobs/run',
            'invoker_sa': 'worker@example.invalid',
        },
    )
    monkeypatch.setattr(reprocess.time, 'time', lambda: 1000)
    wake = Mock()
    monkeypatch.setattr(reprocess, '_enqueue', wake)
    reprocess.mark_effects('owner', 'conversation', 'en')
    ref.get.assert_not_called()
    ref.set.assert_called_once()
    body = ref.set.call_args.args[0]
    assert body['effects_only'] is True and 'lease_until' not in body and 'owner' not in body
    assert body['due_at'] == 4540 and body['task_due_at'] == 4540
    assert ref.set.call_args.kwargs == {'merge': True}
    assert wake.call_args.args[0]['document_id'] == reprocess.key('owner', 'conversation\0effects')


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
    assert env['SYNC_TASKS_QUEUE']['value'] == 'sync-jobs-fresh'
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


def test_lazy_unbound_host_keeps_debt_without_failing_visible_completion(monkeypatch):
    client, ref = Mock(), Mock()
    client.collection.return_value.document.return_value = ref
    monkeypatch.setattr(reprocess, 'owns_runtime', lambda: True)
    monkeypatch.setattr(reprocess, 'get_firestore_client', lambda: client)
    monkeypatch.setattr(reprocess, '_effects_binding', lambda: {})
    wake = Mock()
    monkeypatch.setattr(reprocess, '_enqueue', wake)
    reprocess.mark_effects('owner', 'conversation', 'en')
    ref.set.assert_called_once()
    ref.get.assert_not_called()
    wake.assert_not_called()


def test_repaired_delivery_token_always_gets_a_new_cloud_task_name(state, monkeypatch):
    from utils import cloud_tasks

    monkeypatch.setenv('DEMAND_PROCESSING_ENABLED', 'false')
    rows, tasks = state
    reprocess.mark('u', 'c', 'en', now=0)
    row = dict(tasks[0], wake_token='obsolete-name')
    enqueue = Mock()
    monkeypatch.setattr(cloud_tasks, 'enqueue_named_task', enqueue)
    _ENQUEUE(row)
    first = enqueue.call_args.args[2]
    row['task_token'] = 'new-fenced-delivery'
    _ENQUEUE(row)
    assert enqueue.call_args.args[2] != first
    assert enqueue.call_args.args[3]['task_token'] == 'new-fenced-delivery'


@pytest.mark.parametrize('revision_enabled', [False, True])
@pytest.mark.parametrize('redis_available', [False, True])
@pytest.mark.parametrize('opened', [False, True])
def test_demand_master_preserves_production_settle_and_one_pass(
    state, monkeypatch, redis_available, opened, revision_enabled
):
    import fakeredis
    from utils import cloud_tasks
    from utils.conversations import demand_processing as demand

    rows, _ = state
    monkeypatch.setenv('REPEAT_WORK_REVISION_ENABLED', 'true' if revision_enabled else 'false')
    clock = [1000000]
    monkeypatch.setattr(reprocess.time, 'time', lambda: clock[0])
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    monkeypatch.setenv('DEMAND_PROCESSING_ENABLED', 'true')
    monkeypatch.setenv('DEMAND_PROCESSING_PERCENT', '100')
    monkeypatch.setenv('DEMAND_PROCESSING_LAZY_ENABLED', 'false')
    monkeypatch.setenv('DEMAND_PROCESSING_TOOL_ENABLED', 'false')
    monkeypatch.setenv('DEMAND_PROCESSING_SURFACE_REPORTING_ENABLED', 'true')
    redis = fakeredis.FakeRedis()
    monkeypatch.setattr(demand, 'client', (lambda: redis) if redis_available else Mock(side_effect=ConnectionError()))
    enqueue = Mock()
    monkeypatch.setattr(cloud_tasks, 'enqueue_named_task', enqueue)
    monkeypatch.setattr(reprocess, '_enqueue', _ENQUEUE)
    if opened:
        demand.observe_surface('u', 'phone', {'surface_open': True, 'transcript_visible': False})
    for offset in range(0, 500, 100):
        clock[0] = 1000000 + offset
        reprocess.mark('u', 'c', 'en')
    key = reprocess.key('u', 'c')
    assert enqueue.call_count == 1
    assert enqueue.call_args.kwargs['schedule_at'] == 1000600
    assert rows[key]['due_at'] == 1001000
    process = Mock()
    clock[0] = 1000600
    assert reprocess.run(key, rows[key]['task_token'], process) == 'deferred'
    process.assert_not_called()
    assert enqueue.call_count == 2
    assert enqueue.call_args.kwargs['schedule_at'] == 1001000
    clock[0] = 1001000
    assert reprocess.run(key, rows[key]['task_token'], process) == 'processed'
    process.assert_called_once_with('u', 'c', 'en')
    assert not rows


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


@pytest.mark.parametrize(
    'demand_enabled,revision_enabled,expected_due',
    [(False, False, 4600), (False, True, 3600), (True, False, 3540), (True, True, 3540)],
)
def test_demand_and_revision_reuse_keep_their_existing_ceilings(
    state, monkeypatch, demand_enabled, revision_enabled, expected_due
):
    rows, tasks = state
    monkeypatch.setenv('DEMAND_PROCESSING_ENABLED', 'true' if demand_enabled else 'false')
    monkeypatch.setenv('DEMAND_PROCESSING_PERCENT', '100')
    monkeypatch.setenv('REPEAT_WORK_REVISION_ENABLED', 'true' if revision_enabled else 'false')
    reprocess.mark('u', 'c', 'en', now=0)
    key = reprocess.key('u', 'c')
    assert rows[key]['due_at'] == 600
    for now in range(100, 4001, 100):
        reprocess.mark('u', 'c', 'en', now=now)
    assert rows[key]['due_at'] == expected_due
    assert rows[key]['effects_only'] is False
    assert len(tasks) == 1


def test_first_summary_continuous_appends_cannot_extend_dispatch(state, monkeypatch):
    monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_ENABLED', 'true')
    monkeypatch.setenv('FIRST_SUMMARY_UID_ALLOWLIST', 'u')
    rows, tasks = state
    for now in range(0, 120, 5):
        reprocess.mark('u', 'c', 'en', now=now)
    row = rows[reprocess.key('u', 'c')]
    assert row['first_pending_at'] == 0 and row['due_at'] == 120
    output = SimpleNamespace(discarded=False, structured={'overview': 'A real summary'})
    assert reprocess.run(reprocess.key('u', 'c'), tasks[0]['task_token'], lambda *_: output, now=120) == 'processed'
    assert rows[reprocess.key('u', 'c')]['summary_seen']
    reprocess.mark('u', 'c', 'en', now=121)
    assert rows[reprocess.key('u', 'c')]['due_at'] == 721
    assert rows[reprocess.key('u', 'c')]['first_pending_at'] == 121


def test_enabling_deadline_wakes_preexisting_later_task(state, monkeypatch):
    rows, tasks = state
    reprocess.mark('u', 'c', 'en', now=0)
    original = tasks[0]['task_token']
    monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_ENABLED', 'true')
    monkeypatch.setenv('FIRST_SUMMARY_UID_ALLOWLIST', 'u')
    reprocess.mark('u', 'c', 'en', now=100)
    assert len(tasks) == 2 and tasks[-1]['due_at'] == 120
    assert reprocess.run(reprocess.key('u', 'c'), original, Mock(), now=600) == 'stale'


def test_first_pending_survives_death_lease_and_empty_output(state, monkeypatch):
    from utils.conversations.summary_delivery import SummaryOutputUnavailable

    monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_ENABLED', 'true')
    monkeypatch.setenv('FIRST_SUMMARY_UID_ALLOWLIST', 'u')
    rows, tasks = state
    reprocess.mark('u', 'c', 'en', now=0)
    key, token = reprocess.key('u', 'c'), tasks[-1]['task_token']
    with pytest.raises(SummaryOutputUnavailable):
        reprocess.run(key, token, lambda *_: SimpleNamespace(discarded=False, structured={}), now=120)
    assert reprocess.run(key, token, Mock(), now=121) == 'busy'
    reprocess.mark('u', 'c', 'en', now=150)
    assert rows[key]['due_at'] == 120 and rows[key]['first_pending_at'] == 0
    output = SimpleNamespace(discarded=False, structured={'overview': 'Recovered'})
    assert reprocess.run(key, token, lambda *_: output, now=120 + reprocess.LEASE_SECONDS) == 'processed'
    assert reprocess.run(key, token, Mock(), now=2000) == 'stale'


def test_first_summary_bypasses_demand_tier_wait_without_extra_reads(state, monkeypatch):
    from utils import cloud_tasks
    from utils.conversations import demand_processing as demand

    monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_ENABLED', 'true')
    monkeypatch.setenv('FIRST_SUMMARY_UID_ALLOWLIST', 'u')
    rows, tasks = state
    reprocess.mark('u', 'c', 'en', now=0)
    schedule = Mock(side_effect=AssertionError('first summary cannot wait behind demand tiers'))
    monkeypatch.setattr(demand, 'schedule', schedule)
    enqueue = Mock()
    monkeypatch.setattr(cloud_tasks, 'enqueue_named_task', enqueue)
    _ENQUEUE(tasks[0])
    schedule.assert_not_called()
    assert enqueue.call_args.kwargs['schedule_at'] == 120


def test_short_first_summary_lease_and_rolled_back_later_revision(state, monkeypatch):
    monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_ENABLED', 'true')
    monkeypatch.setenv('FIRST_SUMMARY_UID_ALLOWLIST', 'u')
    rows, tasks = state
    key = reprocess.key('u', 'c')
    reprocess.mark('u', 'c', 'en', now=0)

    def death(*_):
        assert rows[key]['lease_until'] == 240
        raise RuntimeError('worker terminated')

    with pytest.raises(RuntimeError):
        reprocess.run(key, tasks[0]['task_token'], death, now=120)
    assert reprocess.run(key, tasks[0]['task_token'], Mock(), now=239) == 'busy'
    result = SimpleNamespace(discarded=False, structured={'overview': 'Real summary'})
    reprocess.run(key, tasks[0]['task_token'], lambda *_: result, now=240)
    monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_ENABLED', 'false')
    reprocess.mark('u', 'c', 'en', now=241)
    assert tasks[-1]['due_at'] == 841
    assert reprocess.run(key, tasks[-1]['task_token'], Mock(), now=841) == 'processed'
    assert not rows


def test_first_summary_retry_preserves_queued_token(state, monkeypatch):
    monkeypatch.setattr(reprocess, '_wake_exists', lambda *_: True)
    monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_ENABLED', 'true')
    monkeypatch.setenv('FIRST_SUMMARY_UID_ALLOWLIST', 'u')
    rows, tasks = state
    key = reprocess.key('u', 'c')
    reprocess.mark('u', 'c', 'en', now=0)
    earliest = tasks[0]['task_token']
    query = Mock()
    query.where.return_value = query
    query.order_by.return_value = query
    query.limit.return_value = query
    query.stream.return_value = [SimpleNamespace(id=key)]
    monkeypatch.setattr(reprocess, 'get_firestore_client', lambda: SimpleNamespace(collection=lambda _: query))
    for now in (240, 360, 480):
        reprocess.sweep(now=now)
        assert rows[key]['task_token'] == earliest
    assert rows[key].get('wake_generation', 0) == 0
    assert len(tasks) == 1
    output = SimpleNamespace(discarded=False, structured={'overview': 'Real summary'})
    assert reprocess.run(key, earliest, lambda *_: output, now=480) == 'processed'


def test_live_request_heartbeats_same_owner_token_without_a_replacement_wake(state, monkeypatch):
    import threading

    monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_ENABLED', 'true')
    monkeypatch.setenv('FIRST_SUMMARY_UID_ALLOWLIST', 'u')
    monkeypatch.setattr(reprocess, 'FIRST_SUMMARY_HEARTBEAT_SECONDS', 0.01)
    clock = [120]
    monkeypatch.setattr(reprocess, 'time', SimpleNamespace(time=lambda: clock[0]))
    rows, tasks = state
    reprocess.mark('u', 'c', 'en', now=0)
    key, token = reprocess.key('u', 'c'), tasks[0]['task_token']
    renewed = threading.Event()
    mutate = reprocess._mutate

    def observe(document_id, operation):
        result = mutate(document_id, operation)
        if rows.get(key, {}).get('lease_until', 0) > 300:
            renewed.set()
        return result

    monkeypatch.setattr(reprocess, '_mutate', observe)
    query = Mock()
    query.where.return_value = query
    query.order_by.return_value = query
    query.limit.return_value = query
    query.stream.return_value = [SimpleNamespace(id=key)]
    monkeypatch.setattr(reprocess, 'get_firestore_client', lambda: SimpleNamespace(collection=lambda _: query))

    def slow_process(*_):
        owner = rows[key]['owner']
        assert rows[key]['lease_until'] == 240
        clock[0] = 300  # The original 120s lease expires during model work.
        assert renewed.wait(1)
        assert rows[key]['owner'] == owner and rows[key]['task_token'] == token
        assert reprocess.sweep(now=300) == {'repaired': 0, 'error': 0}
        assert len(tasks) == 1
        duplicate = Mock()
        assert reprocess.run(key, token, duplicate, now=300) == 'busy'
        duplicate.assert_not_called()
        return SimpleNamespace(discarded=False, structured={'overview': 'Real summary'})

    assert reprocess.run(key, token, slow_process, now=120) == 'processed'
    assert rows[key]['dormant'] and rows[key]['summary_seen']
    assert not any(t.name == 'first-summary-heartbeat' and t.is_alive() for t in threading.enumerate())


def test_empty_kept_output_has_a_terminal_budget_and_cannot_be_remarked(state, monkeypatch):
    from utils.conversations.summary_delivery import SummaryOutputUnavailable

    monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_ENABLED', 'true')
    monkeypatch.setenv('FIRST_SUMMARY_UID_ALLOWLIST', 'u')
    rows, tasks = state
    reprocess.mark('u', 'c', 'en', now=0)
    key, token = reprocess.key('u', 'c'), tasks[0]['task_token']
    empty = lambda *_: SimpleNamespace(discarded=False, structured={})
    for now in (120, 240):
        with pytest.raises(SummaryOutputUnavailable):
            reprocess.run(key, token, empty, now=now)
    assert reprocess.run(key, token, empty, now=360) == 'blocked'
    assert rows[key]['summary_empty_failures'] == 3 and rows[key]['due_at'] is None
    reprocess.mark('u', 'c', 'en', now=1000)
    assert len(tasks) == 1 and rows[key]['due_at'] is None
    process = Mock()
    assert reprocess.run(key, token, process, now=1000) == 'stale'
    process.assert_not_called()


def test_revision_changed_before_repair_claim_keeps_same_version_debt(state, monkeypatch):
    from utils.conversations.summary_delivery import SummaryRepairSuperseded

    monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_ENABLED', 'true')
    monkeypatch.setenv('FIRST_SUMMARY_UID_ALLOWLIST', 'u')
    rows, tasks = state
    reprocess.mark('u', 'c', 'en', now=0)
    key = reprocess.key('u', 'c')
    version = rows[key]['version']

    def append_before_claim(*_):
        raise SummaryRepairSuperseded('new revision without outbox mark', retry_revision=4)

    assert reprocess.run(key, tasks[0]['task_token'], append_before_claim, now=120) == 'superseded'
    assert rows[key]['version'] == version
    assert rows[key]['summary_repair'] and rows[key]['summary_expected_revision'] == 4
    assert rows[key]['lease_until'] == 0 and rows[key]['due_at'] == 120
    output = SimpleNamespace(discarded=False, structured={'overview': 'New revision summary'})
    assert reprocess.run(key, tasks[-1]['task_token'], lambda *_: output, now=120) == 'processed'


@pytest.mark.parametrize('manual', [False, True])
def test_repair_preclaim_retries_only_an_eligible_new_revision(pipeline, monkeypatch, manual):
    from utils.conversations import summary_delivery as delivery

    row = {'status': 'completed', 'summary_title_provenance': 'server_minimum', 'sync_content_revision': 4}
    if manual:
        row['user_title'] = 'Synthetic manual title'
    monkeypatch.setattr(pipeline.conversations_db, 'get_conversation', lambda *_: row)
    process = Mock()
    monkeypatch.setattr(pipeline, 'process_conversation', process)
    token = delivery.REPAIR_CONTEXT.set({'summary_expected_revision': 3})
    try:
        with pytest.raises(delivery.SummaryRepairSuperseded) as error:
            pipeline._reprocess_conversation_after_update('u', 'c', 'en')
        assert error.value.retry_revision == (None if manual else 4)
        process.assert_not_called()
    finally:
        delivery.REPAIR_CONTEXT.reset(token)


def test_superseded_repair_retires_only_its_own_generation(state, monkeypatch):
    from utils.conversations.summary_delivery import SummaryRepairSuperseded

    monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_ENABLED', 'true')
    monkeypatch.setenv('FIRST_SUMMARY_UID_ALLOWLIST', 'u')
    rows, tasks = state
    key = reprocess.key('u', 'c')
    reprocess.mark('u', 'c', 'en', now=0)

    def supersede(*_):
        raise SummaryRepairSuperseded('manual edit')

    assert reprocess.run(key, tasks[-1]['task_token'], supersede, now=120) == 'superseded'
    assert not rows
    reprocess.mark('u', 'c', 'en', now=200)

    def append_then_supersede(*args):
        reprocess.mark(*args, now=321)
        raise SummaryRepairSuperseded('new revision')

    assert reprocess.run(key, tasks[-1]['task_token'], append_then_supersede, now=320) == 'superseded'
    assert rows[key]['lease_until'] == 0 and not rows[key]['summary_repair']


@pytest.mark.parametrize('enabled', [False, True])
def test_only_scheduled_owner_runs_bounded_summary_scan(sync_router, monkeypatch, enabled):
    import asyncio
    import json

    async def run(_executor, fn):
        return fn()

    monkeypatch.setattr(sync_router, 'run_blocking', run)
    monkeypatch.setattr(sync_router.uid_sequencer, 'sweep', Mock(return_value={'error': 0}))
    monkeypatch.setattr(reprocess, 'owns_runtime', lambda: True)
    monkeypatch.setattr(reprocess, 'sweep', Mock(return_value={'repaired': 0, 'error': 0}))
    monkeypatch.setattr(sync_router, 'summary_repair_enabled', lambda: enabled)
    scan = Mock(return_value={'scanned': 100, 'admitted': 10, 'errors': 0})
    monkeypatch.setattr(sync_router.summary_debt_repair, 'tick', scan)
    response = asyncio.run(sync_router.sweep_sync_backfill_sequencer(0))
    outcomes = json.loads(response.body)['outcomes']
    if enabled:
        scan.assert_called_once_with()
        assert outcomes['summary_debt_scanned'] == 100 and outcomes['summary_debt_admitted'] == 10
    else:
        scan.assert_not_called()
        assert 'summary_debt_scanned' not in outcomes


def test_discard_is_terminal_but_does_not_count_as_a_first_summary(state, monkeypatch):
    monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_ENABLED', 'true')
    monkeypatch.setenv('FIRST_SUMMARY_UID_ALLOWLIST', 'u')
    rows, tasks = state
    key = reprocess.key('u', 'c')
    reprocess.mark('u', 'c', 'en', now=0)
    result = SimpleNamespace(discarded=True, structured={'overview': ''})
    assert reprocess.run(key, tasks[-1]['task_token'], lambda *_: result, now=120) == 'processed'
    assert not rows
    reprocess.mark('u', 'c', 'en', now=10000)
    assert rows[key]['due_at'] == 10120 and not rows[key].get('summary_seen')


def test_first_summary_fulfilled_during_append_starts_a_later_revision_window(state, monkeypatch):
    monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_ENABLED', 'true')
    monkeypatch.setenv('FIRST_SUMMARY_UID_ALLOWLIST', 'u')
    monkeypatch.setenv('REPEAT_WORK_REVISION_ENABLED', 'true')
    rows, tasks = state
    key = reprocess.key('u', 'c')
    reprocess.mark('u', 'c', 'en', now=0)

    def persist_then_append(*args):
        reprocess.mark(*args, now=10001)
        return SimpleNamespace(discarded=False, structured={'overview': 'Real summary'})

    reprocess.run(key, tasks[-1]['task_token'], persist_then_append, now=10000)
    reprocess.mark('u', 'c', 'en', now=10002)
    assert rows[key]['first_pending_at'] == 10000
    assert rows[key]['due_at'] == 10602


@pytest.mark.parametrize('preserve', [False, True])
def test_percent_rollback_cannot_forget_admitted_first_summary_when_drain_is_enabled(state, monkeypatch, preserve):
    from config import summary_guarantee

    rows, tasks = state
    monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_ENABLED', 'true')
    monkeypatch.setenv('FIRST_SUMMARY_UID_ALLOWLIST', '')
    monkeypatch.setenv('FIRST_SUMMARY_UID_ALLOWLIST', 'u')
    monkeypatch.setenv('FIRST_SUMMARY_PRESERVE_ADMITTED_ENABLED', str(preserve).lower())
    reprocess.mark('u', 'c', 'en', now=0)
    key, token = reprocess.key('u', 'c'), tasks[-1]['task_token']
    monkeypatch.delenv('FIRST_SUMMARY_UID_ALLOWLIST', raising=False)
    assert not summary_guarantee.enabled('u')
    monkeypatch.setenv('FIRST_SUMMARY_UID_ALLOWLIST', 'other-owner')
    assert not summary_guarantee.enabled('u')

    def no_output(*_):
        assert summary_guarantee.enabled('u') == preserve
        assert not summary_guarantee.enabled('unrelated-owner')
        reprocess.mark('u', 'nested-conversation', 'en', now=120)
        nested = rows[reprocess.key('u', 'nested-conversation')]
        assert nested['due_at'] == 720 and 'summary_deadline_at' not in nested
        return None

    if preserve:
        with pytest.raises(reprocess.FirstSummaryCallbackPending):
            reprocess.run(key, token, no_output, now=120)
        assert 'summary_empty_failures' not in rows[key]
        assert rows[key]['first_pending_at'] == 0
        assert rows[key]['due_at'] == rows[key]['task_due_at'] == 120
        assert rows[key]['lease_until'] == 240  # Short admitted-deadline lease, not 1800s.
        reprocess.mark('u', 'c', 'en', now=180)
        assert rows[key]['due_at'] == 120
        assert rows[key]['task_token'] == token
        output = SimpleNamespace(discarded=False, structured={'overview': 'Synthetic recovered summary'})
        assert reprocess.run(key, token, lambda *_: output, now=240) == 'processed'
        assert rows[key]['summary_seen'] and rows[key]['dormant']
    else:
        assert reprocess.run(key, token, no_output, now=120) == 'processed'
        assert key not in rows  # Reproduce the legacy loss of scheduling debt.
    assert not summary_guarantee.enabled('u')
    assert summary_guarantee.ADMITTED_OWNER.get() is None
    reprocess.mark('u', 'new-conversation', 'en', now=300)
    new = rows[reprocess.key('u', 'new-conversation')]
    assert new['due_at'] == 900 and 'summary_deadline_at' not in new


@pytest.mark.parametrize('deadline', [None, True, '120', float('nan'), float('inf')])
def test_invalid_deadline_never_grants_summary_drain_eligibility(monkeypatch, deadline):
    from config import summary_guarantee

    monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_ENABLED', 'true')
    monkeypatch.setenv('FIRST_SUMMARY_UID_ALLOWLIST', '')
    monkeypatch.setenv('FIRST_SUMMARY_UID_ALLOWLIST', 'other-owner')
    monkeypatch.setenv('FIRST_SUMMARY_PRESERVE_ADMITTED_ENABLED', 'true')
    row = {'uid': 'u', 'summary_deadline_at': deadline}
    assert not summary_guarantee.first_summary_pending(row)


def test_preserved_deadline_bypasses_demand_wait_and_repairs_without_rotating_queued_token(state, monkeypatch):
    from utils import cloud_tasks
    from utils.conversations import demand_processing as demand

    rows, tasks = state
    monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_ENABLED', 'true')
    monkeypatch.setenv('FIRST_SUMMARY_UID_ALLOWLIST', '')
    monkeypatch.setenv('FIRST_SUMMARY_UID_ALLOWLIST', 'u')
    monkeypatch.setenv('FIRST_SUMMARY_PRESERVE_ADMITTED_ENABLED', 'true')
    reprocess.mark('u', 'c', 'en', now=0)
    key, token = reprocess.key('u', 'c'), tasks[-1]['task_token']
    monkeypatch.setenv('FIRST_SUMMARY_UID_ALLOWLIST', 'other-owner')
    schedule, enqueue = Mock(), Mock()
    monkeypatch.setattr(demand, 'schedule', schedule)
    monkeypatch.setattr(cloud_tasks, 'enqueue_named_task', enqueue)
    _ENQUEUE(rows[key])
    schedule.assert_not_called()
    assert enqueue.call_args.kwargs['schedule_at'] == 120
    query = Mock()
    query.where.return_value = query
    query.order_by.return_value = query
    query.limit.return_value = query
    query.stream.return_value = [SimpleNamespace(id=key)]
    monkeypatch.setattr(reprocess, 'get_firestore_client', lambda: SimpleNamespace(collection=lambda _: query))
    assert reprocess.sweep(now=240) == {'repaired': 1, 'error': 0}
    assert rows[key]['task_token'] != token and rows[key].get('wake_generation', 0) == 0
    for exclusions in ({'effects_only': True}, {'summary_seen': True}):
        rows[key].update(exclusions)
        from config import summary_guarantee

        assert not summary_guarantee.preserves_admitted(rows[key])
        rows[key].update({field: False for field in exclusions})


def test_preserved_callback_rule_discard_receipt_settles_without_empty_failure(state, monkeypatch):
    rows, tasks = state
    monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_ENABLED', 'true')
    monkeypatch.setenv('FIRST_SUMMARY_UID_ALLOWLIST', '')
    monkeypatch.setenv('FIRST_SUMMARY_UID_ALLOWLIST', 'u')
    monkeypatch.setenv('FIRST_SUMMARY_PRESERVE_ADMITTED_ENABLED', 'true')
    reprocess.mark('u', 'c', 'en', now=0)
    key, token = reprocess.key('u', 'c'), tasks[-1]['task_token']
    monkeypatch.setenv('FIRST_SUMMARY_UID_ALLOWLIST', 'other-owner')

    def rule_discard(*_):
        context = reprocess.summary_delivery.PROCESS_CONTEXT.get()
        assert context is not None
        context['discarded'] = True
        return None

    assert reprocess.run(key, token, rule_discard, now=120) == 'processed'
    assert key not in rows


@pytest.mark.parametrize('persisted', [False, True])
def test_pipeline_only_receipts_a_rule_discard_after_persistence(pipeline, monkeypatch, persisted):
    monkeypatch.setattr(
        pipeline.conversations_db,
        'get_conversation',
        lambda *_: {'status': 'completed', 'sync_relevance': 'review', 'transcript_segments': []},
    )
    monkeypatch.setattr(pipeline, 'fragment_rule', lambda *_: ('discard', 'synthetic-rule'))
    monkeypatch.setattr(pipeline, 'is_user_curated', lambda *_: False)
    monkeypatch.setattr(pipeline, 'repair_fenced', lambda *_: False)
    monkeypatch.setattr(
        pipeline.lifecycle_service,
        'rule_discard_outcome',
        lambda *a, **k: 'discarded' if persisted else 'refused',
    )
    relevance = Mock()
    monkeypatch.setattr(pipeline, 'record_conversation_relevance', relevance)
    context = {}
    token = pipeline.PROCESS_CONTEXT.set(context)
    try:
        assert pipeline._reprocess_conversation_after_update('u', 'c', 'en') is None
    finally:
        pipeline.PROCESS_CONTEXT.reset(token)
    assert context.get('discarded', False) == persisted
    assert relevance.call_count == int(persisted)


@pytest.mark.parametrize('with_context', [False, True])
def test_pipeline_receipts_an_intake_discarded_fragment_without_a_second_write(pipeline, monkeypatch, with_context):
    # The read predicate shows every uncurated review row as discarded, so the
    # callback cannot tell a stored discard apart from an unpersisted one; only
    # the write's own outcome can.
    monkeypatch.setattr(
        pipeline.conversations_db,
        'get_conversation',
        lambda *_: {
            'status': 'completed',
            'sync_relevance': 'review',
            'discarded': True,
            'sync_content_revision': 3,
            'transcript_segments': [],
        },
    )
    monkeypatch.setattr(pipeline, 'fragment_rule', lambda *_: ('discard', 'synthetic-rule'))
    monkeypatch.setattr(pipeline, 'is_user_curated', lambda *_: False)
    monkeypatch.setattr(pipeline, 'repair_fenced', lambda *_: False)
    outcome, relevance = Mock(return_value='already_discarded'), Mock()
    monkeypatch.setattr(pipeline.lifecycle_service, 'rule_discard_outcome', outcome)
    monkeypatch.setattr(pipeline, 'record_conversation_relevance', relevance)
    context = {} if with_context else None
    token = pipeline.PROCESS_CONTEXT.set(context)
    try:
        assert pipeline._reprocess_conversation_after_update('u', 'c', 'en') is None
    finally:
        pipeline.PROCESS_CONTEXT.reset(token)
    # The stored discard owes no summary and is not a new rule decision; the
    # receipt is what stops reprocess.run from raising FirstSummaryCallbackPending.
    assert (context or {}).get('discarded', False) == with_context
    assert outcome.call_args.kwargs['expected_sync_content_revision'] == 3
    relevance.assert_not_called()


def test_intake_discarded_fragment_settles_admitted_obligation_instead_of_callback_pending(
    state, pipeline, monkeypatch
):
    rows, tasks = state
    monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_ENABLED', 'true')
    monkeypatch.setenv('FIRST_SUMMARY_UID_ALLOWLIST', '')
    monkeypatch.setenv('FIRST_SUMMARY_UID_ALLOWLIST', 'u')
    monkeypatch.setenv('FIRST_SUMMARY_PRESERVE_ADMITTED_ENABLED', 'true')
    reprocess.mark('u', 'c', 'en', now=0)
    key, token = reprocess.key('u', 'c'), tasks[-1]['task_token']
    monkeypatch.setattr(
        pipeline.conversations_db,
        'get_conversation',
        lambda *_: {'status': 'completed', 'sync_relevance': 'review', 'discarded': True, 'transcript_segments': []},
    )
    monkeypatch.setattr(pipeline, 'fragment_rule', lambda *_: ('discard', 'synthetic-rule'))
    monkeypatch.setattr(pipeline, 'is_user_curated', lambda *_: False)
    monkeypatch.setattr(pipeline, 'repair_fenced', lambda *_: False)
    monkeypatch.setattr(pipeline.lifecycle_service, 'rule_discard_outcome', Mock(return_value='already_discarded'))
    monkeypatch.setattr(pipeline, 'record_conversation_relevance', Mock())

    def callback(uid, conversation_id, language):
        # The freshly loaded pipeline module carries its own PROCESS_CONTEXT
        # object; bridge run()'s context into it the way the request path shares one.
        token = pipeline.PROCESS_CONTEXT.set(reprocess.summary_delivery.PROCESS_CONTEXT.get())
        try:
            return pipeline._reprocess_conversation_after_update(uid, conversation_id, language)
        finally:
            pipeline.PROCESS_CONTEXT.reset(token)

    assert reprocess.run(key, token, callback, now=120) == 'processed'
    assert key not in rows


@pytest.mark.parametrize('preserve', [False, True])
@pytest.mark.parametrize('has_output', [False, True])
def test_later_summary_keeps_legacy_callback_validation_and_completion(state, monkeypatch, preserve, has_output):
    monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_ENABLED', 'true')
    monkeypatch.setenv('FIRST_SUMMARY_UID_ALLOWLIST', '')
    monkeypatch.setenv('FIRST_SUMMARY_UID_ALLOWLIST', 'u')
    monkeypatch.setenv('FIRST_SUMMARY_PRESERVE_ADMITTED_ENABLED', str(preserve).lower())
    rows, tasks = state
    reprocess.mark('u', 'c', 'en', now=0)
    key, token = reprocess.key('u', 'c'), tasks[-1]['task_token']
    rows[key]['summary_seen'] = True

    def callback(*_):
        assert reprocess.summary_delivery.PROCESS_CONTEXT.get() is None
        return SimpleNamespace(discarded=False, structured={'overview': 'Synthetic output'} if has_output else {})

    if has_output:
        assert reprocess.run(key, token, callback, now=120) == 'processed'
        assert rows[key]['dormant'] and rows[key]['summary_seen']
    else:
        with pytest.raises(reprocess.summary_delivery.SummaryOutputUnavailable):
            reprocess.run(key, token, callback, now=120)
        assert not rows[key].get('dormant')
        assert rows[key]['lease_until'] == 1920
