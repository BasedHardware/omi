"""Synthetic operator contracts; no customer fixtures or external services."""

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import fakeredis
import pytest

from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils import cloud_tasks
from utils.sync.incident_redrive import (
    Evidence,
    PAYLOAD_FIELDS,
    SERVICES,
    classify,
    evidence_digest,
    operation_key,
    select_population,
    serving_commits_valid,
)

SCRIPT = Path(__file__).resolve().parents[2] / 'scripts' / 'openloop_redrive.py'
spec = importlib.util.spec_from_file_location('openloop_redrive_operator', SCRIPT)
operator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(operator)


@pytest.fixture
def candidate():
    row = {
        'job_id': 'job',
        'job_ref': 'opaque',
        'population': 'persistence_suspected_open_loop',
        'status': 'partial_failure',
        'redrive_key': {'job_id': 'job', 'uid': 'owner', 'content_id': None},
    }
    payload = dict.fromkeys(PAYLOAD_FIELDS)
    payload.update(
        schema_version=1,
        job_id='job',
        uid='owner',
        content_id='content',
        lane='fresh',
        ledger_fence_mode='active',
        raw_blob_paths=['syncing/owner/job/original_pcm16_audio.bin'],
    )
    ledger = {
        'job_id': 'job',
        'status': 'retryable',
        'lane': 'fresh',
        'processed_segment_ids': ['landed'],
        'partial_result': {'new_memories': ['row-a'], 'updated_memories': []},
        'usage_recorded_at': 'once',
    }
    job = {
        'job_id': 'job',
        'uid': 'owner',
        'content_id': 'content',
        'lane': 'fresh',
        'ledger_fence_mode': 'active',
        'result': {'failed_segments': 1, 'total_segments': 2, 'errors': ['sync_persistence_failed']},
        'status': 'partial_failure',
        'policy': {'version': 'admitted'},
        'dispatch_mode': 'cloud_tasks',
    }
    return row, Evidence(
        payloads={'sync_redrive_required': payload},
        ledger=ledger,
        job=job,
        content_id='content',
        runtime_checked=True,
        sources_present=True,
    )


@pytest.mark.parametrize(
    'change,reason',
    [
        ({'payloads': {}}, 'payload_missing'),
        ({'ledger': None}, 'ledger_missing'),
        ({'runtime_checked': False}, 'runtime_probe_required'),
        ({'sources_present': False}, 'source_missing'),
        ({'active_owner': True}, 'active_owner'),
        ({'job': None}, 'job_missing'),
        ({'read_failed': True}, 'metadata_read_failed'),
    ],
)
def test_classification(candidate, change, reason):
    row, evidence = candidate
    assert classify(row, evidence) == 'ready'
    for key, value in change.items():
        setattr(evidence, key, value)
    assert classify(row, evidence) == reason


def test_sources_are_original_and_conflicts_never_reconstructed(candidate):
    row, evidence = candidate
    assert classify(row, evidence) == 'ready'
    assert evidence.field_sources['content_id'] == 'sync_redrive_required'
    assert evidence.field_sources['partial_result'] == 'sync_content_ledger'
    evidence.payloads['cloud_tasks.queue'] = {**next(iter(evidence.payloads.values())), 'source': 'other'}
    assert classify(row, evidence) == 'payload_conflict'


@pytest.mark.parametrize('field', ['processed_segment_ids', 'partial_result'])
def test_partial_requires_both_durable_checkpoints(candidate, field):
    row, evidence = candidate
    evidence.ledger.pop(field)
    assert classify(row, evidence) == 'checkpoint_missing'


def test_finalize_does_not_retranscribe_already_persisted_intake(candidate):
    row, evidence = candidate
    row['population'] = 'finalize_legacy'
    assert classify(row, evidence) == 'finalize_receipt_replay_required'


def test_existing_completion_or_operator_dispatch_is_noop(candidate):
    row, evidence = candidate
    evidence.ledger['status'] = 'completed'
    assert classify(row, evidence) == 'ledger_completed'
    evidence.ledger['status'] = 'retryable'
    evidence.ledger['openloop_redrive'] = {'key': operation_key(row, 'content'), 'state': 'dispatched'}
    assert classify(row, evidence) == 'already_dispatched'
    evidence.ledger['openloop_redrive']['state'] = 'unknown'
    assert classify(row, evidence) == 'operation_conflict'


def test_population_limit_is_explicit_and_deterministic():
    rows = [
        {'job_id': str(i), 'population': p}
        for i, p in enumerate(['finalize_legacy', 'persistence_suspected_open_loop', 'finalize_legacy'])
    ]
    assert select_population(rows, 'finalize_legacy', 1) == rows[:1]
    assert select_population(rows, 'finalize_legacy', 5) == [rows[0], rows[2]]
    for population, limit in [('unknown', 1), ('finalize_legacy', 0), ('finalize_legacy', -1)]:
        with pytest.raises(ValueError):
            select_population(rows, population, limit)


def test_serving_guard_checks_every_traffic_revision_on_every_service():
    fixed, old = 'a' * 40, 'b' * 40
    contains = lambda sha: sha == fixed
    commits = {service: [fixed] for service in SERVICES}
    assert serving_commits_valid(commits, contains)
    commits['backend-sync'] = [fixed, old]
    assert not serving_commits_valid(commits, contains)
    commits['backend-sync'] = []
    assert not serving_commits_valid(commits, contains)
    commits.pop('backend-integration')
    assert not serving_commits_valid(commits, contains)


def test_named_dispatch_retries_same_key_through_production_route(candidate, monkeypatch):
    row, evidence = candidate
    payload = next(iter(evidence.payloads.values()))
    enqueue = Mock()
    monkeypatch.setattr(cloud_tasks, '_enqueue_sync_job_routed', enqueue)
    key = operation_key(row, 'content')
    cloud_tasks.enqueue_sync_job_redrive(payload, key)
    cloud_tasks.enqueue_sync_job_redrive(payload, key)
    assert enqueue.call_args_list[0] == enqueue.call_args_list[1]
    assert enqueue.call_args.args == (payload, 'job-or-' + key, None)
    with pytest.raises(ValueError):
        cloud_tasks.enqueue_sync_job_redrive({**payload, 'sequencer_epoch': 1}, key)


@pytest.fixture
def writer(candidate, monkeypatch):
    row, evidence = candidate
    db = StrictFirestore()
    ref = db.collection('users').document('owner').collection('sync_content_ledger').document('content')
    ref.create(evidence.ledger)
    redis = fakeredis.FakeRedis()
    redis.set('sync_job:job', json.dumps(evidence.job))
    inventory = SimpleNamespace(redis=redis, firestore=db, ledger_ref=lambda uid, content: ref)
    # The strict fixture runs the real transaction bodies and enforces reads
    # before writes. fakeredis executes the actual production Lua CAS scripts.
    prepare = operator.prepare_operation.to_wrap
    mark = operator.mark_dispatched.to_wrap
    monkeypatch.setattr(operator, 'prepare_operation', prepare)
    monkeypatch.setattr(operator, 'mark_dispatched', mark)
    return row, evidence, inventory, ref


def test_apply_preserves_partial_checkpoints_usage_and_second_run_is_noop(writer):
    row, evidence, inventory, ref = writer
    before = deepcopy(evidence.ledger)
    enqueue = Mock()
    approved = evidence_digest(evidence)
    assert operator.apply_one(row, evidence, approved, inventory, enqueue) == 'dispatched'
    enqueue.assert_called_once()
    assert enqueue.call_args.args[0]['job_id'] == 'job'
    current = ref.get().to_dict()
    for key in ('processed_segment_ids', 'partial_result', 'usage_recorded_at'):
        assert current[key] == before[key]
    evidence.ledger = current
    evidence.job = json.loads(inventory.redis.get('sync_job:job'))
    assert operator.apply_one(row, evidence, approved, inventory, enqueue) == 'already_dispatched'
    enqueue.assert_called_once()
    assert not inventory.redis.exists('sync_job_lock:job')


def test_ambiguous_enqueue_resumes_exact_operation_with_original_plan(writer):
    row, evidence, inventory, ref = writer
    approved = evidence_digest(evidence)
    enqueue = Mock(side_effect=TimeoutError('private exception must never be printed'))
    assert operator.apply_one(row, evidence, approved, inventory, enqueue) == 'dispatch_uncertain'
    first_payload, first_key = enqueue.call_args.args
    evidence.ledger = ref.get().to_dict()
    evidence.job = json.loads(inventory.redis.get('sync_job:job'))
    enqueue.side_effect = None
    assert operator.apply_one(row, evidence, approved, inventory, enqueue) == 'dispatched'
    assert enqueue.call_args.args == (first_payload, first_key)


def test_changed_checkpoint_refuses_without_enqueue(writer):
    row, evidence, inventory, ref = writer
    approved = evidence_digest(evidence)
    inventory.firestore.rows[ref.path]['processed_segment_ids'] = ['landed', 'concurrent']
    enqueue = Mock()
    assert operator.apply_one(row, evidence, approved, inventory, enqueue) == 'plan_changed'
    enqueue.assert_not_called()
    assert json.loads(inventory.redis.get('sync_job:job'))['status'] == 'partial_failure'


def test_readonly_inventory_only_reads_exact_projected_metadata(candidate):
    row, evidence = candidate
    inventory = operator.ReadInventory.__new__(operator.ReadInventory)
    inventory.documents = {
        'sync_redrive_required/job': {'uid': 'owner', 'payload': next(iter(evidence.payloads.values()))}
    }
    inventory.owners, inventory.queues, inventory.redis = {}, [], None
    inventory.denied_queues, inventory.task_cache = set(), {}
    ref = Mock()
    ref.get.return_value.to_dict.return_value = evidence.ledger
    inventory.ledger_ref = Mock(return_value=ref)
    result = inventory.inspect(row)
    assert classify(row, result) == 'runtime_probe_required'
    assert ref.get.call_args.kwargs['field_paths'] == list(operator.LEDGER_FIELDS)
    assert all('transcript' not in p for p in operator.LEDGER_FIELDS + tuple(operator.PAYLOAD_MASK))
    ref.set.assert_not_called()
    ref.update.assert_not_called()


def test_dry_run_never_obtains_mutation_authority(candidate, monkeypatch, tmp_path, capsys):
    row, evidence = candidate
    reader = Mock()
    reader.run_metadata.return_value = {service: ['a' * 40] for service in SERVICES}
    reader.inspect.return_value = evidence
    monkeypatch.setattr(operator, 'contains_fix', lambda sha: True)
    monkeypatch.setattr(operator, 'ReadInventory', Mock(return_value=reader))
    mutate = Mock(side_effect=AssertionError('dry run obtained writer'))
    monkeypatch.setattr(operator, 'apply_one', mutate)
    monkeypatch.setattr(operator, 'configure_dispatch', mutate)
    args = SimpleNamespace(apply=False, population=None, limit=None, runtime_redis=False)
    output = tmp_path / 'results.json'
    assert operator.run(args, [row], output, {'runs': []}) == 0
    assert json.loads(capsys.readouterr().out) == {'counts': {'ready': 1}}
    assert output.stat().st_mode & 0o777 == 0o600
    mutate.assert_not_called()


def test_stale_serving_commit_refuses_before_mutation(candidate, monkeypatch, tmp_path):
    row, evidence = candidate
    reader = Mock()
    reader.run_metadata.return_value = {service: ['b' * 40] for service in SERVICES}
    monkeypatch.setattr(operator, 'ReadInventory', Mock(return_value=reader))
    monkeypatch.setattr(operator, 'contains_fix', lambda sha: False)
    args = SimpleNamespace(apply=True, population=row['population'], limit=1, runtime_redis=True)
    history = {'runs': [{'mode': 'dry_run', 'results': [operator.result_record(row, evidence, 'ready')]}]}
    assert operator.run(args, [row], tmp_path / 'results.json', history) == 2
    assert history['runs'][-1]['counts'] == {'serving_commit_unverified': 1}
    reader.preload.assert_not_called()


def test_private_outputs_reject_symlink_and_broad_permissions(tmp_path):
    target = tmp_path / 'target'
    target.write_text('unchanged')
    alias = tmp_path / 'alias'
    alias.symlink_to(target)
    for path in (alias, target):
        with pytest.raises(operator.Blocked):
            operator.atomic_private_write(path, {'private': 'synthetic'})
    assert target.read_text() == 'unchanged'


def test_uncertain_dispatch_never_outlives_task_name_tombstone(writer):
    row, evidence, inventory, ref = writer
    approved = evidence_digest(evidence)
    enqueue = Mock(side_effect=TimeoutError())
    assert operator.apply_one(row, evidence, approved, inventory, enqueue) == 'dispatch_uncertain'
    marker = inventory.firestore.rows[ref.path]['openloop_redrive']
    marker['enqueue_until'] = 0
    evidence.ledger = ref.get().to_dict()
    evidence.job = json.loads(inventory.redis.get('sync_job:job'))
    assert operator.apply_one(row, evidence, approved, inventory, enqueue) == 'dispatch_uncertain'
    enqueue.assert_called_once()


def test_lost_dispatch_ack_after_worker_failed_cannot_restart_provider(writer):
    row, evidence, inventory, ref = writer
    approved = evidence_digest(evidence)
    enqueue = Mock(side_effect=TimeoutError())
    assert operator.apply_one(row, evidence, approved, inventory, enqueue) == 'dispatch_uncertain'
    evidence.ledger = ref.get().to_dict()
    evidence.job = json.loads(inventory.redis.get('sync_job:job'))
    evidence.job['status'] = 'failed'
    assert operator.apply_one(row, evidence, approved, inventory, enqueue) == 'already_dispatched'
    enqueue.assert_called_once()


def test_concurrently_added_usage_marker_refuses_before_enqueue(writer):
    row, evidence, inventory, ref = writer
    approved = evidence_digest(evidence)
    inventory.firestore.rows[ref.path]['metered_at'] = 'concurrent'
    enqueue = Mock()
    assert operator.apply_one(row, evidence, approved, inventory, enqueue) == 'plan_changed'
    enqueue.assert_not_called()


def test_released_claim_reuses_original_identity_without_clearing_checkpoint(writer):
    row, evidence, inventory, ref = writer
    inventory.firestore.rows[ref.path].pop('job_id')
    evidence.ledger.pop('job_id')
    approved = evidence_digest(evidence)
    assert operator.apply_one(row, evidence, approved, inventory, Mock()) == 'dispatched'
    current = ref.get().to_dict()
    assert current['job_id'] == row['job_id']
    assert current['processed_segment_ids'] == ['landed']
    assert current['usage_recorded_at'] == 'once'


def test_task_access_denial_is_cached_and_other_sources_remain_readable(candidate):
    inventory = operator.ReadInventory.__new__(operator.ReadInventory)
    inventory.denied_queues, inventory.task_cache = set(), {}
    inventory.tasks = Mock()
    inventory.tasks.get_task.side_effect = operator.PermissionDenied('synthetic')
    assert inventory.task_payload('queue', 'first') is None
    assert inventory.task_payload('queue', 'second') is None
    inventory.tasks.get_task.assert_called_once()
    row, evidence = candidate
    evidence.payloads = {}
    evidence.task_read_denied = True
    assert classify(row, evidence) == 'task_payload_read_denied'


def test_guard_reads_actual_traffic_revisions_instead_of_newest_template():
    reader = operator.ReadInventory.__new__(operator.ReadInventory)
    reader.services, reader.revisions = {}, {}
    reader.tasks = Mock()
    fixed, old = 'a' * 40, 'b' * 40
    service = {
        'spec': {'template': {'metadata': {'name': 'fixed'}}},
        'status': {'traffic': [{'revisionName': 'old', 'percent': 80}, {'revisionName': 'fixed', 'percent': 20}]},
    }

    def response(url, **kwargs):
        if '/services/' in url:
            data = service
        else:
            sha = old if url.endswith('/old') else fixed
            data = {'spec': {'containers': [{'env': [{'name': 'OMI_BACKEND_RELEASE_SHA', 'value': sha}]}]}}
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: data)

    reader.http = SimpleNamespace(get=response)
    commits = reader.run_metadata()
    assert all(set(values) == {fixed, old} for values in commits.values())
    assert not serving_commits_valid(commits, lambda sha: sha == fixed)


def test_stale_ledger_run_binding_blocks_even_without_redis_lock(candidate):
    row, evidence = candidate
    evidence.ledger['ledger_run_epoch'] = 1
    evidence.ledger['ledger_run_token'] = 'prior-owner'
    assert classify(row, evidence) == 'active_owner'


def test_main_requires_population_and_limit_before_constructing_apply_client(monkeypatch, tmp_path, capsys):
    path = tmp_path / 'input.json'
    path.write_text('{}')
    path.chmod(0o600)
    monkeypatch.setenv('GCP_AGENT_TIER', 'prod-operator')
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    client = Mock(side_effect=AssertionError('unauthorized apply client'))
    monkeypatch.setattr(operator, 'ReadInventory', client)
    assert operator.main(['--input', str(path), '--apply', '--runtime-redis']) == 2
    assert json.loads(capsys.readouterr().out) == {'counts': {'invalid_input': 1}}
    client.assert_not_called()


def test_missing_payload_outputs_explicit_per_field_unavailability(candidate):
    row, evidence = candidate
    evidence.payloads = {}
    record = operator.result_record(row, evidence, classify(row, evidence))
    assert record['status'] == 'blocked'
    for field in ('content_id', 'partial_result', 'processed_segment_ids', 'filenames', 'source', 'lane', 'language'):
        assert record['field_sources'][field] == 'unavailable'


def test_apply_refusal_records_job_and_exits_nonzero_before_next_canary(candidate, monkeypatch, tmp_path):
    row, evidence = candidate
    reader = Mock()
    reader.run_metadata.return_value = {service: ['a' * 40] for service in SERVICES}
    reader.inspect.return_value = evidence
    monkeypatch.setattr(operator, 'ReadInventory', Mock(return_value=reader))
    monkeypatch.setattr(operator, 'contains_fix', lambda sha: True)
    monkeypatch.setattr(operator, 'configure_dispatch', Mock())
    monkeypatch.setattr(operator, 'apply_one', Mock(return_value='plan_changed'))
    args = SimpleNamespace(apply=True, population=row['population'], limit=1, runtime_redis=True)
    history = {'runs': [{'mode': 'dry_run', 'results': [operator.result_record(row, evidence, 'ready')]}]}
    assert operator.run(args, [row], tmp_path / 'results.json', history) == 2
    assert history['runs'][-1]['results'][0]['reason'] == 'plan_changed'


@pytest.mark.parametrize(
    'result,processed,reason',
    [
        (None, ['landed'], 'failure_manifest_incomplete'),
        (
            {'failed_segments': 11, 'total_segments': 12, 'errors': ['sync_persistence_failed'] * 10},
            ['landed'],
            'failure_manifest_incomplete',
        ),
        (
            {'failed_segments': 1, 'total_segments': 2, 'errors': ['sync_finalize_failed']},
            ['landed'],
            'finalize_receipt_replay_required',
        ),
        (
            {'failed_segments': 1, 'total_segments': 2, 'errors': ['sync_firestore_contention_exhausted']},
            ['landed'],
            'failure_manifest_incomplete',
        ),
        ({'failed_segments': 1, 'total_segments': 2, 'errors': ['sync_persistence_failed']}, [], 'checkpoint_missing'),
        (
            {'failed_segments': 3, 'total_segments': 2, 'errors': ['sync_persistence_failed']},
            ['landed'],
            'failure_manifest_incomplete',
        ),
    ],
)
def test_complete_failure_phases_and_all_successful_checkpoints_are_required(candidate, result, processed, reason):
    row, evidence = candidate
    evidence.job['result'] = result
    evidence.ledger['processed_segment_ids'] = processed
    assert classify(row, evidence) == reason
