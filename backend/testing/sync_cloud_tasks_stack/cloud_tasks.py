"""Strict loopback Cloud Tasks control-plane seam for the Sync gauntlet."""

from __future__ import annotations

import copy
import json
import os
import threading
from dataclasses import dataclass
from datetime import timedelta
from typing import Any
from urllib.parse import urlparse

from google.api_core.exceptions import AlreadyExists
from google.cloud import tasks_v2

from utils.cloud_tasks import DISPATCH_DEADLINE_SECONDS

from .events import write_event


@dataclass(frozen=True)
class CapturedTask:
    task_id: str
    body: dict[str, Any]
    url: str


class CloudTasksRecorder:
    """The narrow client surface Sync uses while retaining real task creation.

    The production code still builds the ``tasks_v2.Task`` protobuf.  This
    recorder admits only the configured local worker task and retains its
    payload in memory for the supervisor to deliver over real loopback HTTP.
    """

    def __init__(self):
        raw_lost_acks = os.getenv('OMI_SYNC_STACK_LOST_TASK_ACKS', '0')
        try:
            self._lost_acks_remaining = int(raw_lost_acks)
        except ValueError as error:
            raise RuntimeError('OMI_SYNC_STACK_LOST_TASK_ACKS must be an integer') from error
        if self._lost_acks_remaining < 0:
            raise RuntimeError('OMI_SYNC_STACK_LOST_TASK_ACKS must be non-negative')
        self._tasks: dict[str, CapturedTask] = {}
        self._lock = threading.Lock()

    @staticmethod
    def queue_path(project: str, location: str, queue: str) -> str:
        return f'projects/{project}/locations/{location}/queues/{queue}'

    @staticmethod
    def task_path(project: str, location: str, queue: str, task: str) -> str:
        return f'projects/{project}/locations/{location}/queues/{queue}/tasks/{task}'

    @staticmethod
    def _configuration() -> tuple[str, str, str, str, str, str]:
        project = os.getenv('SYNC_TASKS_PROJECT', '')
        location = os.getenv('SYNC_TASKS_LOCATION', '')
        queue = os.getenv('SYNC_TASKS_QUEUE', '')
        handler_url = os.getenv('SYNC_TASKS_HANDLER_URL', '')
        audience = os.getenv('SYNC_TASKS_OIDC_AUDIENCE', '') or handler_url
        invoker_sa = os.getenv('SYNC_TASKS_INVOKER_SA', '')
        if not all((project, location, queue, handler_url, audience, invoker_sa)):
            raise RuntimeError('Sync loopback Cloud Tasks configuration is incomplete')
        return project, location, queue, handler_url, audience, invoker_sa

    def create_task(self, *, parent: str, task: tasks_v2.Task, **_kwargs: Any) -> tasks_v2.Task:
        if not isinstance(task, tasks_v2.Task):
            raise TypeError(f'expected tasks_v2.Task, got {type(task).__name__}')
        project, location, queue, handler_url, audience, invoker_sa = self._configuration()
        if parent != self.queue_path(project, location, queue):
            raise RuntimeError('Sync task used an unexpected queue parent')
        try:
            body = json.loads(bytes(task.http_request.body).decode('utf-8'))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise RuntimeError('Sync task body is not valid JSON') from error
        if not isinstance(body, dict):
            raise RuntimeError('Sync task body must be a JSON object')
        expected_keys = {
            'schema_version',
            'job_id',
            'uid',
            'raw_blob_paths',
            'source',
            'should_lock',
            'conversation_id',
            'client_device_id',
            'client_platform',
            'enqueued_at',
            'lane',
            'capture_time_trust',
            'recording_age_seconds',
            'content_id',
            'ledger_fence_mode',
        }
        task_id = body.get('job_id')
        if (
            set(body) != expected_keys
            or not isinstance(task_id, str)
            or not task_id
            or not isinstance(body.get('raw_blob_paths'), list)
            or len(body['raw_blob_paths']) != 1
            or not all(isinstance(path, str) and path for path in body['raw_blob_paths'])
        ):
            raise RuntimeError('Sync task body is not the durable v2 worker schema')
        expected_name = self.task_path(project, location, queue, task_id)
        if str(task.name) != expected_name:
            raise RuntimeError('Sync task name does not match the durable job identity')
        request = task.http_request
        parsed_url = urlparse(str(request.url))
        if (
            str(request.url) != handler_url
            or parsed_url.scheme != 'http'
            or parsed_url.hostname != '127.0.0.1'
            or parsed_url.port is None
            or parsed_url.path != '/v2/sync-jobs/run'
            or parsed_url.query
            or parsed_url.username
            or parsed_url.password
        ):
            raise RuntimeError('Sync task attempted a non-loopback or unexpected worker route')
        if int(request.http_method) != int(tasks_v2.HttpMethod.POST):
            raise RuntimeError('Sync task must use POST')
        if dict(request.headers) != {'Content-Type': 'application/json'}:
            raise RuntimeError('Sync task must have only the JSON content-type header')
        if request.oidc_token.service_account_email != invoker_sa or request.oidc_token.audience != audience:
            raise RuntimeError('Sync task has an unexpected OIDC binding')
        if task.dispatch_deadline != timedelta(seconds=DISPATCH_DEADLINE_SECONDS):
            raise RuntimeError('Sync task has an unexpected dispatch deadline')

        with self._lock:
            if task_id in self._tasks:
                write_event('tasks', {'event': 'named_task_deduplicated', 'task_id': task_id})
                raise AlreadyExists(f'task {task_id} already exists')
            self._tasks[task_id] = CapturedTask(task_id=task_id, body=body, url=str(request.url))
            should_lose_ack = self._lost_acks_remaining > 0
            if should_lose_ack:
                self._lost_acks_remaining -= 1

        write_event(
            'tasks',
            {
                'event': 'task_captured',
                'task_id': task_id,
                'queue': queue,
                'http_method': 'POST',
                'url_loopback': True,
                'url_path': parsed_url.path,
                'oidc_audience': audience,
                'oidc_service_account': invoker_sa,
                'payload_schema_version': body['schema_version'],
                'payload_keys': sorted(body),
                'raw_blob_count': len(body['raw_blob_paths']),
                'dispatch_deadline_seconds': DISPATCH_DEADLINE_SECONDS,
            },
        )
        if should_lose_ack:
            write_event('tasks', {'event': 'task_ack_lost', 'task_id': task_id})
            raise RuntimeError('intentional local Cloud Tasks acknowledgement loss')
        return task

    def task(self, task_id: str) -> CapturedTask | None:
        with self._lock:
            captured = self._tasks.get(task_id)
            return copy.deepcopy(captured) if captured is not None else None
