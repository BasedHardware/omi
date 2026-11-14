"""SCA-1894: a new durable stamp must declare its independently deployed readers.

The registry, runtime roster and batch-pipeline source scan are read-only, so each
one is parsed once per pytest process and shared through module-scoped fixtures. The
backend fast-unit duration guard budgets per-test CPU, and re-parsing the deploy
manifests or the whole `utils/batch_pipeline/` tree inside every test spent that
budget on the same unchanged bytes.
"""

from copy import deepcopy

import pytest
import yaml

from scripts.state_readers_registry import (
    BACKEND,
    REGISTRY,
    coverage_errors,
    runtime_roster,
    source_paths,
    validate,
    written_fields,
)


@pytest.fixture(scope='module')
def registry_data():
    return yaml.safe_load(REGISTRY.read_text())


@pytest.fixture(scope='module')
def roster():
    return runtime_roster()


@pytest.fixture(scope='module')
def registry_errors(registry_data, roster):
    """One full registry + source-coverage pass, shared by every assertion below."""
    return validate(registry_data, roster) + coverage_errors(registry_data, source_paths())


def test_state_readers_registry(registry_data, registry_errors):
    assert not registry_errors, '\n'.join(registry_errors)
    ready = registry_data['states']['{namespace}_jobs.ready_at']
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
def test_invalid_reader_or_containment_is_rejected(registry_data, roster, change, expected):
    data = deepcopy(registry_data)
    # Break the alias before changing this one state's contract.
    key = '{namespace}_jobs.ready_at'
    data['states'][key] = {**data['states'][key], **change}
    assert any(expected in error for error in validate(data, roster))


def test_runtime_roster_includes_independent_gpu_deployment(roster):
    assert {'helm/batch-pipeline-worker', 'gke/backend-listen', 'cloud_run/backend-integration'} <= roster


def test_independent_repair_cronjob_owns_the_maintenance_cursor(registry_data):
    """The repair CronJob is the only RepairCursor consumer, and it is not Cloud Run.

    ``record_seal_repair_cursor.RepairCursor`` is reached only through
    ``record_seal_cluster_repair.run()``, which only
    ``scripts/record_seal_repair_job.py`` launches. That entrypoint ships in the
    independently released ``helm/batch-pipeline-worker`` chart, so the registry
    must name the Helm deployment as reader and writer and give it the CronJob's
    own ``RECORD_SEAL_REPAIR_ENABLED`` binding. Naming the Cloud Run service
    instead would claim containment that disabling Cloud Run does not provide.
    """
    for state in ('batch_pipeline_prod_maintenance.cursor', 'batch_pipeline_prod_maintenance.version'):
        entry = registry_data['states'][state]
        assert entry['writers'] == ['helm/batch-pipeline-worker'], state
        assert entry['readers'].get('helm/batch-pipeline-worker'), state
        assert entry['kill_switch'] == {
            'flag': 'RECORD_SEAL_REPAIR_ENABLED',
            'service': 'helm/batch-pipeline-worker',
        }, state


def test_repair_cronjob_template_still_binds_the_registered_kill_switch():
    """Keep the registry assertion above anchored to the chart it describes."""
    template = (BACKEND / 'charts/batch-pipeline-worker/templates/record-seal-repair.yaml').read_text()
    assert 'scripts/record_seal_repair_job.py' in template
    assert 'RECORD_SEAL_REPAIR_ENABLED' in template
