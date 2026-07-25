"""Strict loopback Cloud Tasks seam for the listen finalization gauntlet.

The production enqueue code still constructs the real ``tasks_v2.Task``.  This
client accepts only the finalization task shape, persists sanitized metadata,
and never has credentials or a route beyond the local ASGI process.
"""

from __future__ import annotations

import fcntl
import json
import os
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import urlparse

from fastapi import HTTPException, Request
from google.api_core.exceptions import AlreadyExists
from google.cloud import tasks_v2

from utils import cloud_tasks
from utils.cloud_tasks import DISPATCH_DEADLINE_SECONDS

FINALIZATION_HANDLER_PATH = '/v1/conversation-finalization-jobs/run'
TASK_EVENTS_FILE = 'cloud_tasks.jsonl'
LOCAL_TASK_TOKEN_ENV = 'OMI_STACK_LOCAL_TASK_TOKEN'


def _state_dir() -> Path:
    value = os.getenv('OMI_STACK_STATE_DIR')
    if not value:
        raise RuntimeError('OMI_STACK_STATE_DIR is required for the loopback Cloud Tasks client')
    return Path(value)


def _append_event(event: dict[str, Any]) -> None:
    path = _state_dir() / TASK_EVENTS_FILE
    with path.open('a', encoding='utf-8') as output:
        output.write(json.dumps(event, sort_keys=True) + '\n')


def _read_task_names() -> set[str]:
    path = _state_dir() / TASK_EVENTS_FILE
    if not path.exists():
        return set()
    names: set[str] = set()
    for line in path.read_text(encoding='utf-8').splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if (
            isinstance(event, dict)
            and event.get('event') == 'task_enqueued'
            and isinstance(event.get('task_name'), str)
        ):
            names.add(event['task_name'])
    return names


@contextmanager
def _task_event_lock() -> Iterator[None]:
    """Serialize named-task creation across listener processes."""
    path = _state_dir() / 'cloud_tasks.lock'
    with path.open('a+', encoding='utf-8') as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


class StrictLoopbackTasksClient:
    """The narrow ``CloudTasksClient`` surface the finalization enqueue uses."""

    def queue_path(self, project: str, location: str, queue: str) -> str:
        return f'projects/{project}/locations/{location}/queues/{queue}'

    def task_path(self, project: str, location: str, queue: str, task_id: str) -> str:
        return f'{self.queue_path(project, location, queue)}/tasks/{task_id}'

    def create_task(self, *, parent: str, task: Any) -> Any:
        project = os.getenv('SYNC_TASKS_PROJECT', '')
        location = os.getenv('SYNC_TASKS_LOCATION', '')
        queue = os.getenv('LISTEN_FINALIZATION_TASKS_QUEUE', '')
        handler_url = os.getenv('LISTEN_FINALIZATION_TASKS_HANDLER_URL', '')
        invoker_sa = os.getenv('LISTEN_FINALIZATION_TASKS_INVOKER_SA', '')
        expected_parent = self.queue_path(project, location, queue)
        if parent != expected_parent:
            raise RuntimeError(f'finalization task used unexpected parent {parent!r}')
        if not all((project, location, queue, handler_url, invoker_sa)):
            raise RuntimeError('loopback finalization task configuration is incomplete')

        request = task.http_request
        parsed_url = urlparse(str(request.url))
        if (
            str(request.url) != handler_url
            or parsed_url.scheme != 'http'
            or parsed_url.hostname != '127.0.0.1'
            or parsed_url.port is None
            or parsed_url.path != FINALIZATION_HANDLER_PATH
            or parsed_url.query
            or parsed_url.username
            or parsed_url.password
        ):
            raise RuntimeError('loopback task attempted a non-local or unexpected finalization route')
        if int(request.http_method) != int(tasks_v2.HttpMethod.POST):
            raise RuntimeError('finalization task must use POST')
        if dict(request.headers) != {'Content-Type': 'application/json'}:
            raise RuntimeError('finalization task must have only the JSON content-type header')
        if request.oidc_token.service_account_email != invoker_sa or request.oidc_token.audience != handler_url:
            raise RuntimeError('finalization task has an unexpected OIDC binding')
        if task.dispatch_deadline != timedelta(seconds=DISPATCH_DEADLINE_SECONDS):
            raise RuntimeError('finalization task has an unexpected dispatch deadline')

        try:
            payload = json.loads(bytes(request.body).decode('utf-8'))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise RuntimeError('finalization task body is not valid JSON') from error
        if (
            not isinstance(payload, dict)
            or set(payload) != {'job_id', 'dispatch_generation'}
            or not isinstance(payload.get('job_id'), str)
            or not payload['job_id']
            or not isinstance(payload.get('dispatch_generation'), int)
            or isinstance(payload['dispatch_generation'], bool)
            or payload['dispatch_generation'] < 1
        ):
            raise RuntimeError('finalization task body is not the opaque durable schema')

        task_name = str(task.name)
        expected_name = self.task_path(
            project, location, queue, f"listen-finalization-{payload['job_id']}-{payload['dispatch_generation']}"
        )
        if task_name != expected_name:
            raise RuntimeError('finalization task name does not match its opaque durable identity')
        with _task_event_lock():
            if task_name in _read_task_names():
                _append_event(
                    {
                        'event': 'task_already_exists',
                        'task_name': task_name,
                        'payload': payload,
                    }
                )
                raise AlreadyExists(f'loopback task already exists: {task_name}')
            _append_event(
                {
                    'event': 'task_enqueued',
                    'task_name': task_name,
                    'url': handler_url,
                    'payload': payload,
                }
            )
        return task


def install_loopback_tasks_client() -> None:
    """Patch only client construction; task building remains production code."""
    cloud_tasks._get_tasks_client = StrictLoopbackTasksClient  # type: ignore[method-assign]


def install_loopback_task_auth() -> None:
    """Keep the production dependency but replace only JWT crypto for local delivery."""

    def verify(request: Request, *, audience: str, invoker_sa: str, log_failure: bool = True) -> int:
        del log_failure
        expected_audience = os.getenv('LISTEN_FINALIZATION_TASKS_HANDLER_URL', '')
        expected_invoker = os.getenv('LISTEN_FINALIZATION_TASKS_INVOKER_SA', '')
        expected_token = os.getenv(LOCAL_TASK_TOKEN_ENV, '')
        if audience != expected_audience or invoker_sa != expected_invoker or not expected_token:
            raise HTTPException(status_code=403, detail='Loopback task dispatch not configured')
        if request.headers.get('authorization') != f'Bearer {expected_token}':
            raise HTTPException(status_code=403, detail='Invalid loopback task identity')
        try:
            retry_count = int(request.headers.get('x-cloudtasks-taskretrycount', '0'))
        except ValueError:
            return 0
        return max(retry_count, 0)

    cloud_tasks._verify_cloud_tasks_oidc = verify  # type: ignore[assignment]
