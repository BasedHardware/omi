"""SCA-1894: a new durable stamp must declare its independently deployed readers."""

from copy import deepcopy

import pytest
import yaml

from scripts.state_readers_registry import (
    REGISTRY,
    coverage_errors,
    runtime_roster,
    source_paths,
    validate,
    written_fields,
)


def registry():
    return yaml.safe_load(REGISTRY.read_text())


def test_state_readers_registry():
    data = registry()
    errors = validate(data, runtime_roster()) + coverage_errors(data, source_paths())
    assert not errors, '\n'.join(errors)
    ready = data['states']['{namespace}_jobs.ready_at']
    assert 'helm/batch-pipeline-worker' in ready['readers']
    assert ready['kill_switch'] == {
        'flag': 'BATCH_PIPELINE_WORKER_ENABLED',
        'service': 'helm/batch-pipeline-worker',
    }


@pytest.mark.parametrize(
    'source',
    [
        "ref.set({'x_probe_at': now})",
        "ref.update({'x_probe_at': now})",
        "transaction.update(ref, {'x_probe_at': now})",
        "patch = {'x_probe_at': now}\ntransaction.update(ref, patch)",
        "tx.put('jobs', key, {'x_probe_at': now})",
        "job = {}\njob.update(x_probe_at=now)\ntx.put('jobs', key, job)",
        "job = {}\njob['x_probe_at'] = now\ntx.put('jobs', key, job)",
        "patch = {'x_probe_at': now}\ntx.put('jobs', key, {**patch})",
        "def defer(job):\n    job.update(x_probe_at=now)",
    ],
)
def test_new_literal_write_names_missing_field(tmp_path, source):
    probe = tmp_path / 'probe.py'
    probe.write_text(source)
    errors = coverage_errors({'states': {}}, [probe])
    assert any('x_probe_at' in error for error in errors)


def test_transient_dict_and_rpc_options_are_not_durable_state():
    fields = written_fields("entry = {}\nentry.update(diagnostic=True)\nref.set({'ready_at': now}, merge=True)")
    assert set().union(*fields.values()) == {'ready_at'}


def test_payload_names_are_scoped_to_their_function():
    fields = written_fields('''
def diagnostics():
    job = {'diagnostic': True}
def persist(tx):
    job = {'ready_at': now}
    tx.put('jobs', key, job)
''')
    assert fields == {'jobs': {'ready_at'}}


@pytest.mark.parametrize(
    'change, expected',
    [
        ({'readers': {}}, 'no readers'),
        ({'readers': {'gke/nonexistent-worker': 'v1'}}, 'gke/nonexistent-worker'),
        ({'readers': {'helm/batch-pipeline-worker': ''}}, 'minimum version'),
        ({'kill_switch': {'flag': 'STOP', 'service': 'gke/pusher'}}, 'gke/pusher'),
        ({'kill_switch': {'service': 'helm/batch-pipeline-worker'}}, 'needs a flag'),
    ],
)
def test_invalid_reader_or_containment_is_rejected(change, expected):
    data = deepcopy(registry())
    # Break the alias before changing this one state's contract.
    key = '{namespace}_jobs.ready_at'
    data['states'][key] = {**data['states'][key], **change}
    assert any(expected in error for error in validate(data, runtime_roster()))


def test_runtime_roster_includes_independent_gpu_deployment():
    roster = runtime_roster()
    assert {'helm/batch-pipeline-worker', 'gke/backend-listen', 'cloud_run/backend-integration'} <= roster
