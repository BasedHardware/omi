"""Strict loopback Cloud Tasks control-plane seam for the Sync gauntlet."""

from __future__ import annotations

import copy
import json
import os
import re
import threading
from dataclasses import dataclass
from datetime import timedelta
from typing import Any
from urllib.parse import urlparse

from google.api_core.exceptions import AlreadyExists
from google.cloud import tasks_v2

from utils.cloud_tasks import DISPATCH_DEADLINE_SECONDS, sync_job_payload_keys_valid

from .events import write_event

RECOVERY_ROUTE = '/v2/batch-pipeline/recover-quarantine'
# Legacy time-bucketed wake suffix, or the leased wake sequence (`w<seq>`).
_RECOVERY_TASK_ID = re.compile(r'bpr-(prod|dev)-[0-9a-f]{64}-[0-9a-f]{32}-([0-9]{1,12}|w[0-9]{1,9})')
_REPROCESS_TASK_ID = re.compile(r'sr-[0-9a-f]{64}-[0-9a-f]{32}(-repair-[0-9]{1,12})?')
_REPROCESS_KEY = re.compile(r'[0-9a-f]{64}')
_REPROCESS_TOKEN = re.compile(r'[0-9a-f]{32}')


@dataclass(frozen=True)
class CapturedTask:
    task_id: str
    body: dict[str, Any]
    url: str
    kind: str = 'sync_job'


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
        if urlparse(str(task.http_request.url)).path == RECOVERY_ROUTE:
            return self._capture_recovery_task(parent, task, body)
        if body.get('kind') == 'sync_reprocess':
            return self._capture_reprocess_task(parent, task, body)
        task_id = body.get('job_id')
        if (
            not sync_job_payload_keys_valid(body, allow_sequenced=False)
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

    def tasks(self, kind: str | None = None) -> list[CapturedTask]:
        with self._lock:
            return [copy.deepcopy(item) for item in self._tasks.values() if kind is None or item.kind == kind]

    @staticmethod
    def _common_contract(task: tasks_v2.Task, *, audience: str, invoker_sa: str) -> None:
        request = task.http_request
        if int(request.http_method) != int(tasks_v2.HttpMethod.POST):
            raise RuntimeError('task must use POST')
        if dict(request.headers) != {'Content-Type': 'application/json'}:
            raise RuntimeError('task must have only the JSON content-type header')
        if request.oidc_token.service_account_email != invoker_sa or request.oidc_token.audience != audience:
            raise RuntimeError('task has an unexpected OIDC binding')
        if task.dispatch_deadline != timedelta(seconds=DISPATCH_DEADLINE_SECONDS):
            raise RuntimeError('task has an unexpected dispatch deadline')

    def _record(self, task_id: str, body: dict[str, Any], url: str, kind: str, event: dict[str, Any]) -> None:
        with self._lock:
            if task_id in self._tasks:
                write_event('tasks', {'event': 'named_task_deduplicated', 'task_id': task_id, 'kind': kind})
                raise AlreadyExists(f'task {task_id} already exists')
            self._tasks[task_id] = CapturedTask(task_id=task_id, body=body, url=url, kind=kind)
        write_event('tasks', {'event': 'task_captured', 'task_id': task_id, 'kind': kind, **event})

    def _capture_recovery_task(self, parent: str, task: tasks_v2.Task, body: dict[str, Any]) -> tasks_v2.Task:
        """Batch quarantine recovery: serving-origin audience, opaque segment body."""
        project = os.getenv('SYNC_TASKS_PROJECT', '')
        location = os.getenv('SYNC_TASKS_LOCATION', '')
        queue = os.getenv('SYNC_TASKS_QUEUE', '')
        audience = os.getenv('BATCH_PIPELINE_RECOVERY_TASK_AUDIENCE', '').strip()
        invoker_sa = os.getenv('SYNC_TASKS_INVOKER_SA', '').strip()
        if not all((project, location, queue, audience, invoker_sa)):
            raise RuntimeError('batch recovery task configuration is incomplete')
        if parent != self.queue_path(project, location, queue):
            raise RuntimeError('batch recovery task used an unexpected queue parent')
        url = str(task.http_request.url)
        parsed = urlparse(url)
        if (
            url != audience.rstrip('/') + RECOVERY_ROUTE
            or parsed.scheme != 'https'
            or parsed.query
            or parsed.username
            or parsed.password
        ):
            raise RuntimeError('batch recovery task targeted an unexpected serving route')
        segment_id = body.get('segment_id')
        if set(body) != {'stage', 'segment_id'} or body.get('stage') not in {'prod', 'dev'}:
            raise RuntimeError('batch recovery task body must carry only stage and segment id')
        if not isinstance(segment_id, str) or not re.fullmatch(r'[0-9a-f]{64}', segment_id):
            raise RuntimeError('batch recovery task segment id is not opaque')
        task_id = str(task.name).rsplit('/', 1)[-1]
        if str(task.name) != self.task_path(project, location, queue, task_id) or not _RECOVERY_TASK_ID.fullmatch(
            task_id
        ):
            raise RuntimeError('batch recovery task name does not bind its durable intent')
        self._common_contract(task, audience=audience, invoker_sa=invoker_sa)
        self._record(
            task_id,
            body,
            url,
            'batch_recovery',
            {'segment_id': segment_id, 'url_path': parsed.path, 'payload_keys': sorted(body)},
        )
        return task

    def _capture_reprocess_task(self, parent: str, task: tasks_v2.Task, body: dict[str, Any]) -> tasks_v2.Task:
        """Projection enrichment obligation; recorded, never delivered here.

        Mirrors the production handler's binding: ``run_enrichment`` only
        accepts a 64-hex ``key`` and a 32-hex ``task_token`` (400 otherwise),
        and the producer names the task after those exact values.
        """
        if set(body) != {'kind', 'key', 'task_token'}:
            raise RuntimeError('sync reprocess task body has unexpected keys')
        key, task_token = body['key'], body['task_token']
        if not isinstance(key, str) or not _REPROCESS_KEY.fullmatch(key):
            raise RuntimeError('sync reprocess task key is not the 64-hex enrichment document id')
        if not isinstance(task_token, str) or not _REPROCESS_TOKEN.fullmatch(task_token):
            raise RuntimeError('sync reprocess task token is not the 32-hex obligation token')
        project = os.getenv('SYNC_TASKS_PROJECT', '')
        location = os.getenv('SYNC_TASKS_LOCATION', '')
        if not parent.startswith(f'projects/{project}/locations/{location}/queues/'):
            raise RuntimeError('sync reprocess task used an unexpected queue parent')
        url = str(task.http_request.url)
        parsed = urlparse(url)
        if parsed.scheme != 'https' or not parsed.path.endswith('/v2/sync-jobs/run'):
            raise RuntimeError('sync reprocess task targeted an unexpected handler')
        task_id = str(task.name).rsplit('/', 1)[-1]
        match = _REPROCESS_TASK_ID.fullmatch(task_id)
        # ``-repair-{wake_generation}`` is the producer's only sanctioned suffix.
        suffix = match.group(1) or '' if match else ''
        if match is None or task_id != f'sr-{key}-{task_token}{suffix}':
            raise RuntimeError('sync reprocess task name does not bind its key and obligation token')
        self._common_contract(
            task,
            audience=task.http_request.oidc_token.audience,
            invoker_sa=os.getenv('SYNC_TASKS_INVOKER_SA', '').strip(),
        )
        if task.http_request.oidc_token.audience != url:
            raise RuntimeError('sync reprocess task audience must be its handler')
        self._record(task_id, body, url, 'sync_reprocess', {'url_path': parsed.path, 'payload_keys': sorted(body)})
        return task
