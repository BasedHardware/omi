"""Cloud Tasks existence probes cannot confuse permission failure with exhaustion."""

from datetime import datetime, timezone
from unittest.mock import Mock
from google.api_core.exceptions import AlreadyExists, FailedPrecondition, NotFound, PermissionDenied
import pytest

from utils import cloud_tasks
from utils.enrichment import scan as enrichment_scan


@pytest.mark.parametrize('duplicate', [False, True])
def test_verified_wake_requires_an_undispatched_future_task(monkeypatch, duplicate):
    client = Mock()
    path = 'projects/p/locations/l/queues/q/tasks/wake'
    client.task_path.return_value = path
    monkeypatch.setattr(cloud_tasks, '_get_tasks_client', lambda: client)
    monkeypatch.setattr(cloud_tasks.time, 'time', lambda: 100)
    monkeypatch.setenv('SYNC_TASKS_PROJECT', 'p')
    monkeypatch.setenv('SYNC_TASKS_LOCATION', 'l')
    monkeypatch.setenv('SYNC_TASKS_INVOKER_SA', 'invoker@example.test')
    future = cloud_tasks.tasks_v2.Task(name=path, schedule_time=datetime.fromtimestamp(120, timezone.utc))
    client.create_task.return_value = future
    client.get_task.return_value = future
    if duplicate:
        client.create_task.side_effect = AlreadyExists('synthetic')

    def enqueue():
        cloud_tasks.enqueue_named_task(
            'q', 'https://example.test/reconcile', 'wake', {}, schedule_at=120, require_future=True
        )

    enqueue()
    assert client.create_task.call_args.kwargs['timeout'] == 3
    if not duplicate:
        client.get_task.assert_not_called()
        return
    request = client.get_task.call_args.kwargs['request']
    assert request.name == path and request.response_view == cloud_tasks.tasks_v2.Task.View.BASIC
    assert client.get_task.call_args.kwargs['timeout'] == 3
    future.dispatch_count = 1
    with pytest.raises(RuntimeError, match='no undispatched future wake'):
        enqueue()
    future.dispatch_count = 0
    future.schedule_time = datetime.fromtimestamp(99, timezone.utc)
    with pytest.raises(RuntimeError, match='no undispatched future wake'):
        enqueue()
    client.get_task.side_effect = NotFound('retained name')
    with pytest.raises(NotFound):
        enqueue()
    client.get_task.side_effect = PermissionDenied('synthetic')
    with pytest.raises(PermissionDenied):
        enqueue()


def test_cloud_task_probe_uses_basic_and_distinguishes_not_found(monkeypatch):
    client = Mock()
    client.task_path.return_value = 'projects/demo-custody/locations/us-central1/queues/queue/tasks/wake'
    monkeypatch.setattr(cloud_tasks, '_get_tasks_client', lambda: client)
    monkeypatch.setenv('SYNC_TASKS_PROJECT', 'demo-custody')
    monkeypatch.setenv('SYNC_TASKS_LOCATION', 'us-central1')
    assert cloud_tasks.named_task_exists('queue', 'wake')
    request = client.get_task.call_args.kwargs['request']
    assert request.response_view == cloud_tasks.tasks_v2.Task.View.BASIC
    assert client.get_task.call_args.kwargs['timeout'] == 3
    assert client.get_task.call_args.kwargs['retry'] is None
    client.get_task.side_effect = NotFound('synthetic exhausted task')
    assert not cloud_tasks.named_task_exists('queue', 'wake')
    client.get_task.side_effect = PermissionDenied('synthetic')
    with pytest.raises(PermissionDenied):
        cloud_tasks.named_task_exists('queue', 'wake')


def test_scan_checkpoint_cas_conflict_cannot_overwrite_another_pass():
    previous, last = Mock(), Mock()
    previous.exists = True
    previous.update_time = None
    previous.reference.update.side_effect = FailedPrecondition('synthetic competing cursor')
    last.to_dict.return_value = {'due_at': 120}
    last.id = 'a' * 64
    enrichment_scan.finish(previous, last, False)
    assert previous.reference.update.call_args.kwargs['option'] is not None
