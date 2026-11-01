"""The retry logger receives static shadow labels, never owner/job identities."""

from types import SimpleNamespace

import pytest

from database import batch_pipeline_store as storage
from database import batch_pipeline_shadow as shadow
from database.batch_pipeline_transaction_labels import shadow_operation
from tests.unit.test_batch_pipeline_shadow import repository  # noqa: F401
from utils.batch_pipeline.contracts import WorkItem, RecoveryWork


@pytest.fixture
def operation_log(monkeypatch):
    seen = []
    original = storage.run_with_transaction_contention_retry

    def observed(*args, **kwargs):
        seen.append(kwargs['operation_name'])
        return original(*args, **kwargs)

    monkeypatch.setattr(storage, 'contention_retry_enabled', lambda: True)
    monkeypatch.setattr(storage, 'run_with_transaction_contention_retry', observed)
    return seen


def test_shadow_lifecycle_labels_the_actual_retry_consumer(repository, operation_log, monkeypatch):
    worker = 'synthetic-private-worker'
    repository.offer(worker)
    reservation = repository.reserve('synthetic-owner', 'synthetic-content', 'fresh')
    assert reservation is not None
    item = WorkItem(reservation[0], 'synthetic-owner', 1, 'encrypted:synthetic', 2, 0, shadow=True)
    assert repository.ready(reservation, item, 'en')
    assert repository.take(worker) == item
    assert repository.projection_input(item.segment_id) is not None
    assert repository.handoff(item.segment_id, RecoveryWork(item.segment_id))
    assert repository.start_recovery(item.segment_id) is not None
    assert repository.paid(item.segment_id, 'modulate')
    repository.recovery_transport_failed(item.segment_id)
    repository.finish(item.segment_id, 'error')
    monkeypatch.setattr(shadow, 'stale_jobs', lambda *args: [SimpleNamespace(id=item.segment_id)])
    repository.reap()
    assert operation_log == [
        'batch_shadow_offer',
        'batch_shadow_reserve',
        'batch_shadow_ready',
        'batch_shadow_take',
        'batch_shadow_projection_input',
        'batch_shadow_handoff',
        'batch_shadow_start_recovery',
        'batch_shadow_paid',
        'batch_shadow_recovery_transport_failed',
        'batch_shadow_finish',
        'batch_shadow_reap',
    ]
    repository.store.run(lambda transaction: None)
    assert operation_log[-1] == 'batch_pipeline_store'
    assert all('synthetic' not in label for label in operation_log)


def test_shadow_scope_restores_the_serving_pull_label(repository, operation_log):
    with storage.pull_operation('pull', 'scheduler_00'):
        repository.offer('synthetic-worker')
        repository.store.run(lambda transaction: None)
    repository.store.run(lambda transaction: None)
    assert operation_log == ['batch_shadow_offer', 'batch_pull shard=scheduler_00', 'batch_pipeline_store']


def test_retry_failure_restores_the_next_transaction_label(repository, monkeypatch):
    seen = []
    original = storage.run_with_transaction_contention_retry

    def failing(*args, **kwargs):
        seen.append(kwargs['operation_name'])
        raise RuntimeError('synthetic retry failure')

    monkeypatch.setattr(storage, 'contention_retry_enabled', lambda: True)
    monkeypatch.setattr(storage, 'run_with_transaction_contention_retry', failing)
    with pytest.raises(RuntimeError, match='synthetic retry failure'):
        repository.offer('synthetic-worker')

    def succeeding(*args, **kwargs):
        seen.append(kwargs['operation_name'])
        return original(*args, **kwargs)

    monkeypatch.setattr(storage, 'run_with_transaction_contention_retry', succeeding)
    repository.store.run(lambda transaction: None)
    assert seen == ['batch_shadow_offer', 'batch_pipeline_store']


@pytest.mark.parametrize('untrusted', ['synthetic-owner', 'take owner=synthetic', 'take\nprivate', 'unknown'])
def test_identity_or_arbitrary_operation_cannot_become_a_log_label(untrusted):
    with pytest.raises(ValueError, match='static shadow store operation required'):
        with shadow_operation(untrusted):
            pytest.fail('untrusted label entered scope')
