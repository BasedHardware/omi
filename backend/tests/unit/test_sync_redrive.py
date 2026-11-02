"""Durable custody and under-lock legacy convergence, without external IO."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from database import sync_jobs, sync_redrive
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore


@pytest.fixture(autouse=True)
def production_stage(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')


def test_legacy_success_uses_cas_token_without_rebinding_ledger(monkeypatch):
    client = StrictFirestore()
    result = {'failed_segments': 0, 'total_segments': 1, 'errors': [], 'outcome': 'success'}
    ref = sync_redrive.sync_content_reference(client, 'owner', 'content')
    ref.create({'status': 'completed', 'result': result})
    finalize = Mock(return_value=SimpleNamespace(applied=True, job={'status': 'completed'}))
    monkeypatch.setattr(sync_jobs, 'fenced_finalize_sync_job_from_durable_ledger', finalize)
    assert sync_redrive.converge_legacy_completion(
        job_id='job', uid='owner', content_id='content', run_lock_token='legacy-token', firestore_client=client
    ) == {'status': 'completed'}
    finalize.assert_called_once_with('job', 'legacy-token', result)
    assert ref.get().to_dict() == {'status': 'completed', 'result': result}


@pytest.mark.parametrize(
    'status,result',
    [
        ('retryable', {}),
        ('completed', {'total_segments': 0, 'failed_segments': 0, 'errors': []}),
        ('held', {'held_audio': True}),
    ],
)
def test_invalid_or_held_completion_does_not_finalize(monkeypatch, status, result):
    client = StrictFirestore()
    sync_redrive.sync_content_reference(client, 'owner', 'content').create({'status': status, 'result': result})
    finalize = Mock(side_effect=AssertionError('must not finalize'))
    monkeypatch.setattr(sync_jobs, 'fenced_finalize_sync_job_from_durable_ledger', finalize)
    assert (
        sync_redrive.converge_legacy_completion(
            job_id='job', uid='owner', content_id='content', run_lock_token='legacy-token', firestore_client=client
        )
        is None
    )


def test_legacy_lock_loss_fails_closed(monkeypatch):
    client = StrictFirestore()
    sync_redrive.sync_content_reference(client, 'owner', 'content').create(
        {
            'status': 'completed',
            'result': {'failed_segments': 0, 'total_segments': 0, 'errors': [], 'outcome': 'expected_silence'},
        }
    )
    monkeypatch.setattr(
        sync_jobs, 'fenced_finalize_sync_job_from_durable_ledger', Mock(return_value=SimpleNamespace(applied=False))
    )
    with pytest.raises(RuntimeError, match='lost its run lock'):
        sync_redrive.converge_legacy_completion(
            job_id='job', uid='owner', content_id='content', run_lock_token='stale', firestore_client=client
        )


def test_rollout_defaults_dark(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    monkeypatch.delenv('SYNC_DURABLE_REDRIVE_GUARD', raising=False)
    monkeypatch.delenv('SYNC_LEGACY_COMPLETION_CONVERGENCE', raising=False)
    assert not sync_redrive.enabled()
    assert not sync_redrive.legacy_convergence_enabled()
