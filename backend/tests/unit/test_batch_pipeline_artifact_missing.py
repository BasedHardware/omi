"""Missing audio cannot acknowledge custody, including after sibling publication."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from database.batch_pipeline_projection import ProjectionStore
from database.batch_pipeline_projection_protocol import ProjectionBlocked
from tests.unit.test_batch_pipeline_quarantine_recovery import (
    setup,
    row,
    ledger_row,
    PARTIAL_ACCOUNTING,
)
from utils.batch_pipeline.intake import durable_status


def missing_setup(setup):
    client, store, binding, *_ = setup
    row(client).update(recovery_state='failed_held', audio_uri='gs://synthetic/audio#7')
    client.rows[('batch_pipeline_prod_intakes', binding.job_id)] = {
        'owner_id': binding.owner_id,
        'content_id': binding.content_id,
        'segment_ids': list(binding.segment_ids),
        'lane': 'backfill',
        'total_files': 1,
    }
    return client, store, binding


def evidence(job):
    return {
        'status': 404,
        'generation': 7,
        'uri_sha256': hashlib.sha256(job['audio_uri'].encode()).hexdigest(),
        'verified_at': 100,
    }


def test_operator_discovery_counts_permission_unknown_without_inventing_absence(monkeypatch):
    from importlib import import_module
    from google.api_core.exceptions import Forbidden

    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / 'scripts'))
    operator = import_module('batch_pipeline_artifact_missing')

    def denied(*args):
        raise Forbidden('synthetic metadata denial')

    monkeypatch.setattr(operator, 'inspect', denied)
    assert operator.inspect_candidate(None, None, 'synthetic') == (None, None, 'unknown')
    monkeypatch.setattr(operator, 'inspect', lambda *args: ({'state': 'quarantined'}, {'status': 404}))
    assert operator.inspect_candidate(None, None, 'synthetic')[2] == 'missing'
    monkeypatch.setattr(operator, 'inspect', lambda *args: ({'state': 'quarantined'}, None))
    assert operator.inspect_candidate(None, None, 'synthetic')[2] == 'not_missing'


@pytest.mark.parametrize('change', ['none', 'owner', 'content', 'job', 'legacy'])
def test_repair_age_exception_requires_exact_existing_owner_without_writes(setup, monkeypatch, change):
    from utils.batch_pipeline import intake

    client, store, binding = missing_setup(setup)
    monkeypatch.setattr(intake, 'FirestoreStore', lambda *args: store)
    monkeypatch.setattr(intake, 'shadow_from_env', lambda value: value)
    uid, content, job = binding.owner_id, binding.content_id, binding.job_id
    if change == 'owner':
        uid = 'foreign'
    if change == 'content':
        content = 'changed'
    if change == 'job':
        job = 'bp_other'
    if change == 'legacy':
        ledger_row(client, binding)['dispatch_protocol'] = 'legacy'
    writes = sum(len(tx.updates) for tx in client.transactions)
    assert intake.repair_upload_owner_matches(uid, content, job) is (change == 'none')
    assert sum(len(tx.updates) for tx in client.transactions) == writes


def mark(setup):
    from database.batch_pipeline_artifact_missing import ArtifactMissingStore

    client, store, binding = missing_setup(setup)
    before = deepcopy(row(client))
    assert ArtifactMissingStore(store).apply('bad', before, evidence(before), 'a' * 64, 101)
    return client, store, binding, before


def test_disposition_never_completes_or_releases_audio_and_replays(setup):
    from database.batch_pipeline_artifact_missing import ArtifactMissingStore

    client, store, binding, before = mark(setup)
    job = row(client)
    assert job['state'] == 'quarantined' and job['recovery_state'] == 'failed_held'
    assert {k: v for k, v in job.items() if k != 'artifact_disposition'} == before
    assert not job.get('result') and not job.get('expires_at') and not job.get('client_status')
    assert ledger_row(client, binding)['status'] == 'processing'
    writes = sum(len(tx.updates) for tx in client.transactions)
    assert ArtifactMissingStore(store).apply('bad', before, evidence(before), 'a' * 64, 102)
    assert writes == sum(len(tx.updates) for tx in client.transactions)


@pytest.mark.parametrize(
    'change', ['uri', 'generation', 'status', 'old', 'future', 'snapshot', 'lease', 'result', 'intent', 'owner']
)
def test_disposition_fails_closed_on_changed_or_unproven_work(setup, change):
    from database.batch_pipeline_artifact_missing import ArtifactMissingStore

    client, store, binding = missing_setup(setup)
    snapshot = deepcopy(row(client))
    proof = evidence(snapshot)
    if change == 'uri':
        proof['uri_sha256'] = 'b' * 64
    elif change == 'generation':
        proof['generation'] = 8
    elif change == 'status':
        proof['status'] = 403
    elif change == 'old':
        proof['verified_at'] = 1
    elif change == 'future':
        proof['verified_at'] = 102
    elif change == 'snapshot':
        row(client)['attempt'] = 99
    elif change == 'lease':
        row(client)['lease_until'] = 200
        snapshot = deepcopy(row(client))
    elif change == 'result':
        client.rows[('batch_pipeline_prod_results', 'bad')] = {'projection': {'state': 'ready'}}
    elif change == 'intent':
        row(client)['terminal_disposition'] = {'state': 'prepared'}
        snapshot = deepcopy(row(client))
    else:
        ledger_row(client, binding)['job_id'] = 'bp_other'
    before = deepcopy(client.rows)
    with pytest.raises(ProjectionBlocked):
        ArtifactMissingStore(store).apply('bad', snapshot, proof, 'a' * 64, 101)
    assert client.rows == before


@pytest.mark.parametrize('partial', [False, True])
def test_missing_status_precedes_partial_ack_and_retains_held_unit(setup, partial):
    client, store, binding, before = mark(setup)
    if partial:
        result, _ = ProjectionStore(store).complete_partial(binding, 102, PARTIAL_ACCOUNTING)
        assert result['held_segments'] == 1
    status = durable_status(store, binding.owner_id, binding.job_id)
    assert status['status'] == 'failed'
    assert status['reason_code'] == 'batch_artifact_missing' and status['poll_after_ms'] == 0
    assert status['failed_segments'] == 1
    assert row(client)['state'] == 'quarantined' and row(client)['recovery_state'] == 'failed_held'
    setup[3].fetch_audio.assert_not_called()
    setup[4].assert_not_called()


def test_partial_releases_projected_siblings_without_completing_missing_job(setup):
    client, store, binding, before = mark(setup)
    projection = ProjectionStore(store)
    result, steps = projection.complete_partial(binding, 102, PARTIAL_ACCOUNTING)
    assert result['reason_code'] == 'batch_artifact_missing'
    assert ledger_row(client, binding)['status'] == 'partial'
    assert row(client)['artifact_disposition']['state'] == 'missing'
    assert row(client, 'results', 'good')['projection']['state'] == 'ready'
    assert not row(client).get('client_status')
    assert not row(client, 'jobs', 'good').get('client_status')
    assert steps == ([0.0, 3], [102])
    assert projection.complete_partial(binding, 103, PARTIAL_ACCOUNTING) == (result, steps)
    golden = json.loads((Path(__file__).parents[1] / 'fixtures/batch_artifact_missing_status.json').read_text())
    assert durable_status(store, binding.owner_id, binding.job_id) == golden


def test_existing_partial_path_cannot_ack_an_operator_proven_missing_artifact(setup):
    client, store, binding = missing_setup(setup)
    row(client)['artifact_disposition'] = {
        'state': 'missing',
        'evidence': evidence(row(client)),
        'plan_digest': 'a' * 64,
        'privacy_generation': 0,
        'verified_at': 100,
    }
    ProjectionStore(store).complete_partial(binding, 101, PARTIAL_ACCOUNTING)
    status = durable_status(store, binding.owner_id, binding.job_id)
    assert status['status'] == 'failed', 'completed would acknowledge and age out the only recoverable phone copy'
    assert status['reason_code'] == 'batch_artifact_missing'


def test_missing_marker_precedes_even_a_stale_completed_ledger(setup):
    client, store, binding, _ = mark(setup)
    ledger_row(client, binding).update(
        status='completed',
        result={
            'new_memories': [],
            'updated_memories': [],
            'failed_segments': 0,
            'total_segments': 2,
            'errors': [],
            'outcome': 'expected_silence',
        },
    )
    status = durable_status(store, binding.owner_id, binding.job_id)
    assert status['status'] == 'failed' and status['reason_code'] == 'batch_artifact_missing'
