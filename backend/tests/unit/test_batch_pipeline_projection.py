"""Projection binding validation and provider-free retry/publication guards."""

from dataclasses import replace
from unittest.mock import Mock

from google.api_core.exceptions import Aborted, InvalidArgument
import pytest

from utils.batch_pipeline.contracts import ProjectionBinding
from database.batch_pipeline_projection import ProjectionStore


@pytest.fixture
def binding():
    return ProjectionBinding('synthetic-owner', 'job', 'content', ('segment',))


@pytest.mark.parametrize(
    'field,value',
    [
        ('segment_ids', ()),
        ('segment_ids', ('same', 'same')),
        ('segment_ids', tuple(str(n) for n in range(129))),
        ('owner_id', ''),
        ('content_id', 'path/id'),
        ('data_protection_level', 'e2ee'),
        ('run_token', 'without-epoch'),
        ('privacy_generation', -1),
    ],
)
def test_invalid_projection_binding_refused(binding, field, value):
    with pytest.raises(ValueError):
        replace(binding, **{field: value})


def test_read_contention_retry_uses_fresh_transactions_when_enabled(monkeypatch):
    monkeypatch.setenv('SYNC_ASSIGNMENT_CONTENTION_RETRY_ENABLED', 'true')
    from database import firestore_transaction_retry

    actual = firestore_transaction_retry.run_with_transaction_contention_retry

    def fast(*args, **kwargs):
        return actual(*args, **kwargs, sleep=lambda _: None)

    monkeypatch.setattr(firestore_transaction_retry, 'run_with_transaction_contention_retry', fast)
    client = Mock()
    client.transaction.side_effect = [object(), object()]
    operation = Mock(side_effect=[Aborted('synthetic'), 'persisted'])
    store = ProjectionStore(Mock(client=client))
    assert store.run(operation) == 'persisted'
    assert operation.call_args_list[0] != operation.call_args_list[1]


def test_read_contention_default_off_and_non_contention_never_replayed(monkeypatch):
    monkeypatch.delenv('SYNC_ASSIGNMENT_CONTENTION_RETRY_ENABLED', raising=False)
    client = Mock()
    operation = Mock(side_effect=Aborted('synthetic'))
    store = ProjectionStore(Mock(client=client))
    with pytest.raises(Aborted):
        store.run(operation)
    assert operation.call_count == 1
    monkeypatch.setenv('SYNC_ASSIGNMENT_CONTENTION_RETRY_ENABLED', 'true')
    operation = Mock(side_effect=InvalidArgument('not contention'))
    with pytest.raises(InvalidArgument):
        store.run(operation)
    assert operation.call_count == 1
