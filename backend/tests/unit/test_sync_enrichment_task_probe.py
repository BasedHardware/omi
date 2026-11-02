"""Cloud Tasks existence probes cannot confuse permission failure with exhaustion."""

from unittest.mock import Mock
from google.api_core.exceptions import FailedPrecondition, NotFound, PermissionDenied
import pytest

from utils import cloud_tasks
from utils.enrichment import scan as enrichment_scan


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
