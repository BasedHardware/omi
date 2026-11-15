"""The operator census must retain the worker evidence the serving repair uses."""

from copy import deepcopy
import importlib.util
from pathlib import Path

import pytest

from tests.unit.test_batch_pipeline_quarantine_recovery import setup, legacy_dependencies, row  # noqa: F401
from tests.unit.test_batch_pipeline_speech_redrive import enabled
from tests.unit.test_batch_language_recovery import worker_receipt
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from database.batch_pipeline_projection_protocol import ProjectionBlocked


def operator(monkeypatch):
    scripts = Path(__file__).parents[2] / 'scripts'
    monkeypatch.syspath_prepend(str(scripts))
    spec = importlib.util.spec_from_file_location(
        'speech_census_operator', scripts / 'batch_pipeline_speech_redrive.py'
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('proof', ['bound', 'missing', 'foreign', 'subframe', 'zero', 'cpu_positive'])
def test_operator_census_never_calls_worker_positive_cpu_zero_silent(setup, monkeypatch, legacy_dependencies, proof):
    client, store, binding, artifacts, legacy, alternate, _ = enabled(setup, monkeypatch, legacy_dependencies)
    module = operator(monkeypatch)
    job = row(client)
    job['worker_failure'] = {'stage': 'assemble_words', 'reason': 'no_owned_words'}
    receipt = worker_receipt(client, 0 if proof == 'zero' else 0.016 if proof == 'subframe' else 1.5)
    if proof in {'missing', 'cpu_positive'}:
        job.pop('worker_vad_receipt')
    elif proof == 'foreign':
        receipt['input_uri_sha256'] = '0' * 64
    _, vad, *_ = legacy_dependencies
    monkeypatch.setattr(
        vad, 'offline_pcm_speech_segments', lambda _: [{'start': 1, 'end': 2}] if proof == 'cpu_positive' else []
    )
    transaction = client.transaction
    monkeypatch.setattr(client, 'transaction', lambda **kwargs: transaction())
    key = module.held.fingerprint(job)
    before = deepcopy(client.rows)
    if proof in {'missing', 'foreign', 'subframe'}:
        with pytest.raises(module.held.Refused, match='positive_held_speech_requires_worker_proof'):
            module.inspect_unit(store, artifacts, 'bad', binding.owner_id, key)
    else:
        assert module.inspect_unit(store, artifacts, 'bad', binding.owner_id, key) == (
            'silent' if proof == 'zero' else 'speech'
        )
    assert client.rows == before
    legacy.assert_not_called()
    alternate.assert_not_called()
    if proof == 'bound':
        artifacts.fetch_audio.assert_not_called()
    else:
        artifacts.fetch_audio.assert_called_once()


@pytest.mark.parametrize('fence', ['completed_upload', 'privacy'])
def test_operator_census_checks_ownership_and_privacy_before_worker_proof(
    setup, monkeypatch, legacy_dependencies, fence
):
    client, store, binding, artifacts, legacy, alternate, _ = enabled(setup, monkeypatch, legacy_dependencies)
    module = operator(monkeypatch)
    worker_receipt(client, 1.5)
    if fence == 'completed_upload':
        client.rows[('users', binding.owner_id, 'sync_content_ledger', binding.content_id)]['status'] = 'completed'
    else:
        client.rows[('users', binding.owner_id)]['migration_status'] = 'pending'
    transaction = client.transaction
    monkeypatch.setattr(client, 'transaction', lambda **kwargs: transaction())
    before = deepcopy(client.rows)
    with pytest.raises((module.held.Refused, ProjectionBlocked, BatchPrivacyBlocked)):
        module.inspect_unit(store, artifacts, 'bad', binding.owner_id, module.held.fingerprint(row(client)))
    assert client.rows == before
    artifacts.fetch_audio.assert_not_called()
    legacy.assert_not_called()
    alternate.assert_not_called()


@pytest.mark.parametrize('speech', [0, 1.5])
def test_completed_silence_census_cannot_override_later_positive_custody(
    setup, monkeypatch, legacy_dependencies, speech
):
    client, store, binding, artifacts, legacy, alternate, _ = enabled(setup, monkeypatch, legacy_dependencies)
    module = operator(monkeypatch)
    worker_receipt(client, speech)
    job = row(client)
    job.pop('worker_vad_receipt')
    job['silence_disposition'] = {'state': 'completed'}
    transaction = client.transaction
    monkeypatch.setattr(client, 'transaction', lambda **kwargs: transaction())
    before = deepcopy(client.rows)
    if speech:
        with pytest.raises(module.held.Refused, match='positive_held_speech_requires_worker_proof'):
            module.inspect_unit(store, artifacts, 'bad', binding.owner_id, module.held.fingerprint(job))
    else:
        assert module.inspect_unit(store, artifacts, 'bad', binding.owner_id, module.held.fingerprint(job)) == 'silent'
    assert client.rows == before
    artifacts.fetch_audio.assert_not_called()
    legacy.assert_not_called()
    alternate.assert_not_called()
