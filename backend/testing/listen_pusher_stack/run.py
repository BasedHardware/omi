"""Run isolated high-fidelity tests for the listen -> pusher chain.

Run through ``run.sh`` so Firebase supplies a fresh Firestore emulator.  This
supervisor owns only the Redis, listener/backend, finalization-worker, pusher,
and Parakeet child processes that it starts; it never probes or stops user
services.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlencode

import httpx
import redis
import websockets
from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

from testing.listen_pusher_stack.cloud_tasks import FINALIZATION_HANDLER_PATH, LOCAL_TASK_TOKEN_ENV, TASK_EVENTS_FILE

ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / 'backend'
PYTHON = BACKEND / '.venv' / 'bin' / 'python'
ADMIN_KEY = 'omi-listen-pusher-stack-admin-'
PROJECT = 'demo-omi-listen-stack'
LOCAL_TASK_TOKEN = 'listen-pusher-stack-loopback-task'
REST_FINALIZATION_RACE_ENV = (
    'OMI_STACK_FINALIZATION_RACE_UID',
    'OMI_STACK_FINALIZATION_RACE_CONVERSATION_ID',
    'OMI_STACK_FINALIZATION_RACE_PARTIES',
)


class StackFailure(AssertionError):
    """An actionable scenario assertion failure."""


@dataclass
class Child:
    name: str
    process: subprocess.Popen[bytes]
    log_path: Path


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(('127.0.0.1', 0))
        return int(probe.getsockname()[1])


def _wait_for_port(
    port: int,
    *,
    label: str,
    timeout: float = 20.0,
    child: 'Child | None' = None,
) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if child and child.process.poll() is not None:
            raise StackFailure(
                f'{label} exited with status {child.process.returncode} before listening; inspect {child.log_path}'
            )
        try:
            with socket.create_connection(('127.0.0.1', port), timeout=0.25):
                return
        except OSError:
            time.sleep(0.1)
    raise StackFailure(f'{label} did not listen on 127.0.0.1:{port} within {timeout:.0f}s')


def _wait_until(predicate: Callable[[], bool], *, label: str, timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.1)
    raise StackFailure(f'timed out waiting for {label}')


def _read_events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding='utf-8').splitlines():
        with suppress(json.JSONDecodeError):
            value = json.loads(line)
            if isinstance(value, dict):
                rows.append(value)
    return rows


def _append_event(path: Path, event: dict[str, Any]) -> None:
    with path.open('a', encoding='utf-8') as output:
        output.write(json.dumps(event, sort_keys=True) + '\n')


class Stack:
    def __init__(
        self,
        state_dir: Path,
        *,
        finalization_mode: str = 'inline',
        finalizer_failures: dict[str, int] | None = None,
        hold_inline_finalization: bool = False,
        rest_finalization_race_uid: str | None = None,
        rest_finalization_race_parties: int = 0,
    ):
        if finalization_mode not in {'inline', 'cloud_tasks'}:
            raise ValueError(f'unsupported finalization mode: {finalization_mode}')
        if hold_inline_finalization and finalization_mode != 'inline':
            raise ValueError('inline finalization hold requires inline dispatch')
        if rest_finalization_race_parties and not rest_finalization_race_uid:
            raise ValueError('REST finalization race requires a target user')
        if rest_finalization_race_parties < 0:
            raise ValueError('REST finalization race party count cannot be negative')
        if rest_finalization_race_uid and rest_finalization_race_parties < 2:
            raise ValueError('REST finalization race requires at least two parties')
        self.state_dir = state_dir
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.finalization_mode = finalization_mode
        self.finalizer_failures = finalizer_failures or {}
        self.hold_inline_finalization = hold_inline_finalization
        self.inline_finalization_release_file = self.state_dir / 'release-inline-finalization'
        self.rest_finalization_race_uid = rest_finalization_race_uid
        self.rest_finalization_race_parties = rest_finalization_race_parties
        self.rest_finalization_race_conversation_id = (
            str(uuid.uuid4()) if rest_finalization_race_uid is not None else None
        )
        self.redis_port = _free_port()
        self.backend_port = _free_port()
        self.finalization_worker_port = _free_port()
        self.pusher_port = _free_port()
        self.parakeet_port = _free_port()
        self.children: dict[str, Child] = {}
        self.env = self._environment()
        self.firestore = firestore.Client(project=PROJECT)

    def _environment(self) -> dict[str, str]:
        firestore_host = os.getenv('FIRESTORE_EMULATOR_HOST')
        if not firestore_host:
            raise StackFailure('FIRESTORE_EMULATOR_HOST is required; run backend/testing/listen_pusher_stack/run.sh')
        if not firestore_host.startswith(('127.0.0.1:', 'localhost:')):
            raise StackFailure('listen-pusher stack only accepts a loopback Firestore emulator')
        isolated_home = self.state_dir / 'home'
        isolated_config = self.state_dir / 'config'
        isolated_home.mkdir(exist_ok=True)
        isolated_config.mkdir(exist_ok=True)
        # Never inherit developer credentials, provider keys, proxy settings, or
        # cloud CLI configuration. The test process owns only local child
        # services and has a private, empty HOME/XDG config root.
        env = {key: os.environ[key] for key in ('PATH', 'LANG', 'LC_ALL', 'TZ', 'TMPDIR') if os.getenv(key)}
        env.update(
            {
                'HOME': str(isolated_home),
                'XDG_CONFIG_HOME': str(isolated_config),
                'CLOUDSDK_CONFIG': str(isolated_config / 'gcloud'),
                'NO_PROXY': '127.0.0.1,localhost',
                'no_proxy': '127.0.0.1,localhost',
                'FIRESTORE_EMULATOR_HOST': firestore_host,
                'OMI_HARNESS_INSTANCE': 'listen-pusher-stack',
                'OMI_ENV_STAGE': 'offline',
                'PROVIDER_MODE': 'offline',
                'FIREBASE_PROJECT_ID': PROJECT,
                'GOOGLE_CLOUD_PROJECT': PROJECT,
                'GCLOUD_PROJECT': PROJECT,
                'FIRESTORE_DATABASE_ID': '(default)',
                'ENCRYPTION_SECRET': 'omi_listen_pusher_stack_test_secret_32_bytes',
                'ADMIN_KEY': ADMIN_KEY,
                'REDIS_DB_HOST': '127.0.0.1',
                'REDIS_DB_PORT': str(self.redis_port),
                'HOSTED_PUSHER_API_URL': f'http://127.0.0.1:{self.pusher_port}',
                'HOSTED_PARAKEET_API_URL': f'http://127.0.0.1:{self.parakeet_port}',
                'STT_SERVICE_MODELS': 'parakeet',
                'TRIAL_PAYWALL_ENABLED': 'false',
                'LISTEN_FINALIZATION_DISPATCH_MODE': self.finalization_mode,
                'OMI_STACK_STATE_DIR': str(self.state_dir),
                'PYTHONPATH': str(BACKEND),
                # Child logs are evidence when a process fails to bind; avoid
                # losing a short Python traceback in the file buffer.
                'PYTHONUNBUFFERED': '1',
            }
        )
        if self.finalization_mode == 'cloud_tasks':
            handler_url = self.finalization_handler_url
            env.update(
                {
                    'SYNC_TASKS_PROJECT': PROJECT,
                    'SYNC_TASKS_LOCATION': 'us-central1',
                    'LISTEN_FINALIZATION_TASKS_QUEUE': 'conversation-finalization',
                    'LISTEN_FINALIZATION_TASKS_HANDLER_URL': handler_url,
                    'LISTEN_FINALIZATION_TASKS_INVOKER_SA': 'listen-finalizer@demo-omi-listen-stack.iam.gserviceaccount.com',
                    'LISTEN_FINALIZATION_TASKS_MAX_ATTEMPTS': '2',
                    LOCAL_TASK_TOKEN_ENV: LOCAL_TASK_TOKEN,
                    'OMI_STACK_FINALIZATION_FAILURES': json.dumps(self.finalizer_failures, sort_keys=True),
                }
            )
        if self.hold_inline_finalization:
            env['OMI_STACK_INLINE_FINALIZATION_RELEASE_FILE'] = str(self.inline_finalization_release_file)
        if self.rest_finalization_race_uid is not None and self.rest_finalization_race_conversation_id is not None:
            env.update(
                {
                    'OMI_STACK_FINALIZATION_RACE_UID': self.rest_finalization_race_uid,
                    'OMI_STACK_FINALIZATION_RACE_CONVERSATION_ID': self.rest_finalization_race_conversation_id,
                    'OMI_STACK_FINALIZATION_RACE_PARTIES': str(self.rest_finalization_race_parties),
                }
            )
        return env

    @property
    def finalization_handler_url(self) -> str:
        return f'http://127.0.0.1:{self.finalization_worker_port}{FINALIZATION_HANDLER_PATH}'

    def _start(
        self,
        name: str,
        command: list[str],
        *,
        extra_env: dict[str, str] | None = None,
        unset_env: tuple[str, ...] = (),
    ) -> Child:
        if name in self.children:
            raise StackFailure(f'{name} is already running')
        log_path = self.state_dir / f'{name}.log'
        process_env = self.env.copy()
        for key in unset_env:
            process_env.pop(key, None)
        if extra_env:
            process_env.update(extra_env)
        output = log_path.open('ab')
        process = subprocess.Popen(
            command,
            cwd=BACKEND,
            env=process_env,
            stdin=subprocess.DEVNULL,
            stdout=output,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        child = Child(name, process, log_path)
        self.children[name] = child
        return child

    def start(self, *, pusher_drop_opcode: int | None = None) -> None:
        redis_binary = shutil.which('redis-server')
        if not redis_binary:
            raise StackFailure('redis-server is required; install Redis and retry')
        redis_child = self._start(
            'redis',
            [
                redis_binary,
                '--port',
                str(self.redis_port),
                '--save',
                '',
                '--appendonly',
                'no',
                '--protected-mode',
                'yes',
            ],
        )
        _wait_for_port(self.redis_port, label='isolated Redis', child=redis_child)
        redis.Redis(host='127.0.0.1', port=self.redis_port).ping()
        parakeet_child = self._start(
            'parakeet',
            [
                str(PYTHON),
                '-m',
                'uvicorn',
                'testing.listen_pusher_stack.parakeet_stub:app',
                '--host',
                '127.0.0.1',
                '--port',
                str(self.parakeet_port),
            ],
        )
        _wait_for_port(self.parakeet_port, label='Parakeet stub', child=parakeet_child)
        pusher_env = (
            {'OMI_STACK_DROP_PUBLISHING_ON_OPCODE': str(pusher_drop_opcode)} if pusher_drop_opcode is not None else None
        )
        pusher_child = self._start(
            'pusher',
            [
                str(PYTHON),
                '-m',
                'uvicorn',
                'testing.listen_pusher_stack.pusher_app:app',
                '--host',
                '127.0.0.1',
                '--port',
                str(self.pusher_port),
            ],
            extra_env=pusher_env,
        )
        _wait_for_port(self.pusher_port, label='pusher', child=pusher_child)
        self._start_backend()
        if self.finalization_mode == 'cloud_tasks':
            worker_child = self._start(
                'finalization-worker',
                [
                    str(PYTHON),
                    '-m',
                    'uvicorn',
                    'testing.listen_pusher_stack.finalization_worker_app:app',
                    '--host',
                    '127.0.0.1',
                    '--port',
                    str(self.finalization_worker_port),
                ],
            )
            _wait_for_port(
                self.finalization_worker_port,
                label='finalization worker',
                timeout=45.0,
                child=worker_child,
            )

    def _start_backend(self, *, enable_rest_finalization_race: bool = True) -> None:
        backend_app = (
            'testing.listen_pusher_stack.listener_app:app' if self.finalization_mode == 'cloud_tasks' else 'main:app'
        )
        backend_child = self._start(
            'backend',
            [str(PYTHON), '-m', 'uvicorn', backend_app, '--host', '127.0.0.1', '--port', str(self.backend_port)],
            unset_env=() if enable_rest_finalization_race else REST_FINALIZATION_RACE_ENV,
        )
        _wait_for_port(self.backend_port, label='listen backend', timeout=45.0, child=backend_child)

    def restart_pusher(self, *, drop_opcode: int | None = None) -> None:
        self.stop('pusher')
        pusher_env = {'OMI_STACK_DROP_PUBLISHING_ON_OPCODE': str(drop_opcode)} if drop_opcode is not None else None
        pusher_child = self._start(
            'pusher',
            [
                str(PYTHON),
                '-m',
                'uvicorn',
                'testing.listen_pusher_stack.pusher_app:app',
                '--host',
                '127.0.0.1',
                '--port',
                str(self.pusher_port),
            ],
            extra_env=pusher_env,
        )
        _wait_for_port(self.pusher_port, label='restarted pusher', child=pusher_child)

    def restart_backend(self) -> None:
        """Prove the durable task survives loss of its originating listener."""
        self.stop('backend')
        # The controlled stale-read race belongs only to the first listener;
        # normal post-restart status reads must use the unmodified entrypoint.
        self._start_backend(enable_rest_finalization_race=False)

    def stop(self, name: str) -> None:
        child = self.children.pop(name, None)
        if not child or child.process.poll() is not None:
            return
        with suppress(ProcessLookupError):
            os.killpg(child.process.pid, signal.SIGTERM)
        try:
            child.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            with suppress(ProcessLookupError):
                os.killpg(child.process.pid, signal.SIGKILL)
            child.process.wait(timeout=5)

    def close(self) -> None:
        for name in reversed(list(self.children)):
            self.stop(name)

    @property
    def pusher_events(self) -> list[dict[str, Any]]:
        return _read_events(self.state_dir / 'pusher.jsonl')

    @property
    def finalizer_events(self) -> list[dict[str, Any]]:
        return _read_events(self.state_dir / 'finalizer.jsonl')

    @property
    def finalization_task_events(self) -> list[dict[str, Any]]:
        return _read_events(self.state_dir / TASK_EVENTS_FILE)

    @property
    def finalization_tasks(self) -> list[dict[str, Any]]:
        return [event for event in self.finalization_task_events if event.get('event') == 'task_enqueued']

    def wait_for_finalization_task(self, *, count: int = 1, timeout: float = 20.0) -> dict[str, Any]:
        tasks: list[dict[str, Any]] = []

        def enqueued() -> bool:
            nonlocal tasks
            tasks = self.finalization_tasks
            return len(tasks) >= count

        _wait_until(enqueued, label='loopback Cloud Tasks enqueue', timeout=timeout)
        return tasks[count - 1]

    async def deliver_finalization_task(
        self, task: dict[str, Any], *, retry_count: int, authenticated: bool = True
    ) -> tuple[int, dict[str, Any]]:
        if self.finalization_mode != 'cloud_tasks':
            raise StackFailure('only the Cloud Tasks stack can deliver finalization tasks')
        if task.get('url') != self.finalization_handler_url:
            raise StackFailure('loopback task handler URL did not match the real backend route')
        payload = task.get('payload')
        if not isinstance(payload, dict) or set(payload) != {'job_id', 'dispatch_generation'}:
            raise StackFailure('loopback task payload was not opaque durable routing data')
        headers = {'X-CloudTasks-TaskRetryCount': str(retry_count)}
        if authenticated:
            headers['Authorization'] = f'Bearer {LOCAL_TASK_TOKEN}'
        async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
            response = await client.post(
                self.finalization_handler_url,
                json=payload,
                headers=headers,
            )
        try:
            body = response.json()
        except json.JSONDecodeError as error:
            raise StackFailure(f'finalization worker returned non-JSON status={response.status_code}') from error
        if not isinstance(body, dict):
            raise StackFailure(f'finalization worker returned non-object JSON status={response.status_code}')
        _append_event(
            self.state_dir / 'cloud_tasks_deliveries.jsonl',
            {
                'event': 'task_delivered',
                'task_name': task.get('task_name'),
                'retry_count': retry_count,
                'status_code': response.status_code,
                'status': body.get('status'),
            },
        )
        return response.status_code, body

    async def finalization_status(self, uid: str, conversation_id: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
            response = await client.get(
                f'http://127.0.0.1:{self.backend_port}/v1/conversations/{conversation_id}/finalization',
                headers={'Authorization': f'Bearer {ADMIN_KEY}{uid}'},
            )
        if response.status_code != 200:
            raise StackFailure(f'finalization status endpoint returned {response.status_code}: {response.text[:120]}')
        body = response.json()
        if not isinstance(body, dict):
            raise StackFailure('finalization status endpoint returned non-object JSON')
        return body

    def seed_user(self, uid: str) -> None:
        # Private cloud is enabled solely to exercise 103 + 101.  The pusher
        # process receives the real frames, but storage leaves are not invoked
        # by this harness because it intentionally has no cloud credentials.
        self.firestore.collection('users').document(uid).set(
            {
                'id': uid,
                'language': 'en',
                'private_cloud_sync_enabled': True,
                'data_protection_level': 'standard',
                # This gauntlet exercises the English-only Parakeet stub. Make
                # the user's single-language choice explicit so selection
                # requests English rather than multi-language auto-detection.
                'transcription_preferences': {'uses_custom_stt': False, 'single_language_mode': True},
            }
        )

    def conversation(self, uid: str, conversation_id: str) -> dict[str, Any] | None:
        snapshot = (
            self.firestore.collection('users').document(uid).collection('conversations').document(conversation_id).get()
        )
        return snapshot.to_dict() if snapshot.exists else None

    def jobs_for(self, uid: str, conversation_id: str) -> list[dict[str, Any]]:
        query = self.firestore.collection('conversation_finalization_jobs').where(filter=FieldFilter('uid', '==', uid))
        jobs: list[dict[str, Any]] = []
        for document in query.stream():
            job = document.to_dict() or {}
            if job.get('conversation_id') != conversation_id:
                continue
            job['id'] = document.id
            jobs.append(job)
        return jobs

    def age_conversation(self, uid: str, conversation_id: str) -> None:
        self.firestore.collection('users').document(uid).collection('conversations').document(conversation_id).update(
            {'finished_at': datetime.now(timezone.utc) - timedelta(seconds=121)}
        )

    def release_inline_finalization(self) -> None:
        if not self.hold_inline_finalization:
            raise StackFailure('inline finalization hold was not configured')
        self.inline_finalization_release_file.touch()

    def seed_bare_processing_conversation(
        self,
        uid: str,
        conversation_id: str,
        *,
        admitted_at: datetime,
        finalization_job_id: str | None = None,
        legacy: bool = False,
        deferred: bool = False,
    ) -> None:
        """Seed the crash-window state: a bare `processing` row with no durable job.

        Mirrors what the synchronous legacy route leaves behind when the process
        hard-crashes between admission and completion. ``admitted_at`` controls the
        admission age the reconciler thresholds on. ``legacy`` omits the
        server-owned ``processing_admitted_at`` stamp (a pre-fence stranded row the
        reconciler must migrate, never complete on first sight). ``deferred`` marks
        a desktop lazy row that intentionally lives on ``processing`` and must be
        excluded from the sweep.
        """
        document = {
            'id': conversation_id,
            'created_at': admitted_at,
            'started_at': admitted_at,
            'finished_at': admitted_at,
            'status': 'processing',
            'source': 'omi',
            'language': 'en',
            'has_content': True,
            'transcript_segments': [],
            'structured': {
                'title': 'Stale orphan recording',
                'overview': '',
                'emoji': '🧠',
                'category': 'other',
                'action_items': [],
                'events': [],
            },
        }
        if not legacy:
            document['processing_admitted_at'] = admitted_at
        if finalization_job_id:
            document['finalization_job_id'] = finalization_job_id
        if deferred:
            document['deferred'] = True
        self.firestore.collection('users').document(uid).collection('conversations').document(conversation_id).set(
            document
        )

    async def conversation_via_api(self, uid: str, conversation_id: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
            response = await client.get(
                f'http://127.0.0.1:{self.backend_port}/v1/conversations/{conversation_id}',
                headers={'Authorization': f'Bearer {ADMIN_KEY}{uid}'},
            )
        if response.status_code != 200:
            raise StackFailure(
                f'GET /v1/conversations/{conversation_id} returned {response.status_code}: {response.text[:160]}'
            )
        body = response.json()
        if not isinstance(body, dict):
            raise StackFailure(f'GET /v1/conversations/{conversation_id} returned non-object JSON')
        return body


def _one_job(stack: Stack, uid: str, conversation_id: str) -> dict[str, Any]:
    jobs = stack.jobs_for(uid, conversation_id)
    if len(jobs) != 1:
        raise StackFailure(f'expected one finalization job, observed {len(jobs)}')
    return jobs[0]


async def _receive_until(websocket: Any, predicate: Callable[[Any], bool], *, label: str, timeout: float = 15.0) -> Any:
    deadline = time.monotonic() + timeout
    seen: list[Any] = []
    while time.monotonic() < deadline:
        remaining = deadline - time.monotonic()
        try:
            message = await asyncio.wait_for(websocket.recv(), timeout=max(0.05, remaining))
        except asyncio.TimeoutError:
            continue
        if not isinstance(message, str):
            continue
        with suppress(json.JSONDecodeError):
            payload = json.loads(message)
            seen.append(payload)
            if predicate(payload):
                return payload
    raise StackFailure(f'timed out waiting for {label}; observed {len(seen)} JSON messages')


async def _connect(stack: Stack, uid: str, session_id: str | None) -> tuple[Any, dict[str, Any]]:
    parameters: dict[str, Any] = {
        'language': 'en',
        'sample_rate': 8000,
        'codec': 'pcm8',
        'source': 'desktop',
        'stt_service': 'parakeet',
    }
    if session_id:
        parameters['client_conversation_id'] = session_id
    params = urlencode(parameters)
    websocket = await websockets.connect(
        f'ws://127.0.0.1:{stack.backend_port}/v4/listen?{params}',
        extra_headers={'Authorization': f'Bearer {ADMIN_KEY}{uid}'},
        max_size=10 * 1024 * 1024,
    )
    session = await _receive_until(
        websocket,
        lambda payload: isinstance(payload, dict) and payload.get('type') == 'conversation_session',
        label='conversation session',
    )
    await _receive_until(
        websocket,
        lambda payload: isinstance(payload, dict)
        and payload.get('type') == 'service_status'
        and payload.get('status') == 'ready',
        label='ready',
    )
    return websocket, session


async def _record_audio(websocket: Any) -> None:
    # pcm8 converts to real pcm16 in the production receiver.  This exceeds
    # its STT buffer threshold and makes the real Parakeet socket emit a segment.
    await websocket.send(bytes([128]) * 16_000)
    await _receive_until(
        websocket,
        lambda payload: isinstance(payload, list) and bool(payload) and payload[0].get('id') == 'stack-segment-1',
        label='streamed transcript',
    )


async def _request_rest_finalization(
    stack: Stack, conversation_id: str, uid: str, *, requests: int = 4
) -> list[httpx.Response]:
    """Issue one or more public REST admissions through the durable outbox."""
    if requests < 1:
        raise ValueError('REST finalization requires at least one request')
    limits = httpx.Limits(max_connections=requests, max_keepalive_connections=requests)
    async with httpx.AsyncClient(timeout=15.0, trust_env=False, limits=limits) as client:
        return list(
            await asyncio.gather(
                *(
                    client.post(
                        f'http://127.0.0.1:{stack.backend_port}/v1/conversations/{conversation_id}/finalize',
                        headers={'Authorization': f'Bearer {ADMIN_KEY}{uid}'},
                    )
                    for _ in range(requests)
                )
            )
        )


def _wait_for_job(
    stack: Stack, uid: str, conversation_id: str, status: str, *, timeout: float = 25.0
) -> dict[str, Any]:
    result: list[dict[str, Any]] = []

    def found() -> bool:
        nonlocal result
        result = stack.jobs_for(uid, conversation_id)
        return len(result) == 1 and result[0].get('status') == status

    _wait_until(found, label=f'finalization job {status}', timeout=timeout)
    return result[0]


def _assert_local_provider_admission(stack: Stack, conversation_id: str) -> None:
    """Assert local seams were reached once, without claiming external delivery."""

    def provider_leaves_flushed() -> bool:
        events = stack.pusher_events
        return any(
            event.get('event') == 'integration_fanout_skipped' and event.get('conversation_id') == conversation_id
            for event in events
        ) and any(
            event.get('event') == 'audio_storage_skipped' and event.get('conversation_id') == conversation_id
            for event in events
        )

    # Pusher flushes its private-cloud queue during the real session teardown.
    # Wait for that observable completion rather than racing the process cleanup.
    _wait_until(provider_leaves_flushed, label='local provider admission')
    events = stack.pusher_events
    fanouts = [
        event
        for event in events
        if event.get('event') == 'integration_fanout_skipped' and event.get('conversation_id') == conversation_id
    ]
    if len(fanouts) != 1:
        raise StackFailure(f'expected one durable finalization fanout admission, observed {len(fanouts)}')
    audio_flushes = [
        event
        for event in events
        if event.get('event') == 'audio_storage_skipped' and event.get('conversation_id') == conversation_id
    ]
    if len(audio_flushes) != 1 or not audio_flushes[0].get('bytes'):
        raise StackFailure('pusher did not admit the private-cloud audio queue exactly once')


async def _normal_and_terminal_reconnect(stack: Stack) -> None:
    uid = 'stack-normal'
    session_id = str(uuid.uuid4())
    stack.seed_user(uid)
    websocket, first_session = await _connect(stack, uid, session_id)
    if first_session.get('conversation_id') != session_id or first_session.get('status') != 'in_progress':
        raise StackFailure('new desktop recording did not bind its requested native session UUID')
    await _record_audio(websocket)
    # Inline compatibility mode owns finalization in the live pusher WebSocket,
    # so trigger the normal stale-recording lifecycle while that connection is
    # still active. Immediate-close durability is exercised separately through
    # the Cloud Tasks scenarios below, where the worker is detached from this
    # client connection.
    stack.age_conversation(uid, session_id)
    await _receive_until(
        websocket,
        lambda payload: isinstance(payload, dict)
        and payload.get('type') == 'memory_created'
        and payload.get('conversation_id') == session_id
        and payload.get('lifecycle_phase') == 'completed',
        label='inline finalization completion',
        timeout=25.0,
    )
    await websocket.close(code=1000)
    job = _wait_for_job(stack, uid, session_id, 'completed')
    conversation = stack.conversation(uid, session_id)
    if not conversation or conversation.get('status') != 'completed' or not conversation.get('has_content'):
        raise StackFailure('normal recording was not persisted and completed through the lifecycle owner')
    events = stack.pusher_events
    opcodes = {event.get('opcode') for event in events if event.get('direction') == 'in'}
    required = {101, 102, 103, 104}
    if not required.issubset(opcodes):
        raise StackFailure(f'normal path missed pusher frames: expected {sorted(required)}, observed {sorted(opcodes)}')
    if not any(
        event.get('direction') == 'out' and event.get('opcode') == 201 and event.get('success') for event in events
    ):
        raise StackFailure('normal path did not receive a successful pusher result frame')
    if job.get('fanout_status') != 'completed':
        raise StackFailure('normal finalization job completed without durable fanout completion')
    _assert_local_provider_admission(stack, session_id)

    # A terminal reconnect with the same native recording UUID must replay the
    # old binding and create a fresh active one, never a second job for the old.
    websocket, replay_session = await _connect(stack, uid, session_id)
    if replay_session.get('conversation_id') != session_id or replay_session.get('status') != 'completed':
        raise StackFailure('terminal native reconnect did not replay the completed recording binding')
    await websocket.close(code=1000)
    jobs = stack.jobs_for(uid, session_id)
    if len(jobs) != 1 or jobs[0].get('id') != job.get('id'):
        raise StackFailure('terminal reconnect changed the original durable finalization job')


async def _inline_finalization_survives_source_close(stack: Stack) -> None:
    """#9995: closing listen after 104 cannot cancel pusher's durable owner."""
    if not stack.hold_inline_finalization:
        raise StackFailure('inline source-close recovery requires a held finalizer')

    uid = 'stack-inline-source-close'
    conversation_id = str(uuid.uuid4())
    stack.seed_user(uid)
    websocket, _ = await _connect(stack, uid, conversation_id)
    await _record_audio(websocket)
    stack.age_conversation(uid, conversation_id)

    def pusher_received_finalization() -> bool:
        return any(
            event.get('event') == 'frame'
            and event.get('direction') == 'in'
            and event.get('opcode') == 104
            and event.get('conversation_id') == conversation_id
            for event in stack.pusher_events
        )

    _wait_until(pusher_received_finalization, label='inline finalization handoff')
    _wait_until(
        lambda: any(
            event.get('event') == 'inline_finalization_hold_entered' and event.get('conversation_id') == conversation_id
            for event in stack.pusher_events
        ),
        label='claimed inline finalization hold',
    )
    # The durable claim transitions the job to 'leased' (the only non-terminal
    # processing state); 'processing' is a conversation status, not a job status.
    claimed = _wait_for_job(stack, uid, conversation_id, 'leased')
    if claimed.get('attempt_count') != 1:
        raise StackFailure('source-close finalization was not claimed exactly once before disconnect')

    await websocket.close(code=1000)
    _wait_until(
        lambda: any(event.get('event') == 'pusher_cleanup_completed' for event in stack.pusher_events),
        label='source pusher cleanup',
    )
    stack.release_inline_finalization()

    completed = _wait_for_job(stack, uid, conversation_id, 'completed')
    conversation = stack.conversation(uid, conversation_id)
    if completed.get('attempt_count') != 1 or completed.get('fanout_status') != 'completed':
        raise StackFailure('source-close finalization did not complete the original durable job')
    if not conversation or conversation.get('status') != 'completed':
        raise StackFailure('source-close finalization did not complete its conversation without a later session')
    _assert_local_provider_admission(stack, conversation_id)


async def _empty_recording(stack: Stack) -> None:
    uid = 'stack-empty'
    session_id = str(uuid.uuid4())
    stack.seed_user(uid)
    websocket, _ = await _connect(stack, uid, session_id)
    await websocket.close(code=1000)
    stack.age_conversation(uid, session_id)
    # Single-channel clean disconnects intentionally defer processing. A later
    # session sees this stale recording as timed out, routes it through the
    # production lifecycle owner, and tombstones it after the pending delay.
    websocket, _ = await _connect(stack, uid, None)

    def deleted() -> bool:
        return stack.conversation(uid, session_id) is None

    _wait_until(deleted, label='stale empty desktop recording deletion', timeout=20.0)
    await websocket.close(code=1000)
    if stack.jobs_for(uid, session_id):
        raise StackFailure('empty desktop recording created a finalization job')


async def _pusher_restart_replay(stack: Stack) -> None:
    uid = 'stack-restart'
    session_id = str(uuid.uuid4())
    stack.seed_user(uid)
    # Restart into a deterministic test mode that drops the first 104 before
    # job claim.  The backend session stays live and must replay its pending
    # exact job/generation after the real pusher process is restarted.
    stack.restart_pusher(drop_opcode=104)
    websocket, _ = await _connect(stack, uid, session_id)
    await _record_audio(websocket)
    stack.age_conversation(uid, session_id)

    def dropped() -> bool:
        return any(event.get('event') == 'intentional_drop_before_dispatch' for event in stack.pusher_events)

    _wait_until(dropped, label='pusher drop after finalization handoff', timeout=20.0)
    first_request = next(
        event
        for event in stack.pusher_events
        if event.get('direction') == 'in' and event.get('opcode') == 104 and event.get('conversation_id') == session_id
    )
    stack.restart_pusher()
    job = _wait_for_job(stack, uid, session_id, 'completed', timeout=30.0)
    finalization_requests = [
        event
        for event in stack.pusher_events
        if event.get('direction') == 'in' and event.get('opcode') == 104 and event.get('conversation_id') == session_id
    ]
    if len(finalization_requests) < 2:
        raise StackFailure('pusher restart did not replay the pending finalization request')
    replay = finalization_requests[-1]
    if (
        replay.get('finalization_job_id') != first_request.get('finalization_job_id')
        or replay.get('dispatch_generation') != first_request.get('dispatch_generation')
        or replay.get('finalization_job_id') != job.get('id', replay.get('finalization_job_id'))
    ):
        raise StackFailure('pusher replay changed its durable finalization identity')
    if job.get('attempt_count') != 1:
        raise StackFailure(
            f'pusher restart processed the durable job more than once: attempts={job.get("attempt_count")}'
        )
    _assert_local_provider_admission(stack, session_id)
    await websocket.close(code=1000)


async def _cloud_task_for_clean_desktop_close(stack: Stack, uid: str, conversation_id: str) -> dict[str, Any]:
    stack.seed_user(uid)
    websocket, session = await _connect(stack, uid, conversation_id)
    if session.get('conversation_id') != conversation_id:
        raise StackFailure('cloud-task recording did not preserve its native session identity')
    await _record_audio(websocket)
    await websocket.close(code=1000)
    return stack.wait_for_finalization_task()


def _assert_opaque_task(task: dict[str, Any], job: dict[str, Any], stack: Stack) -> None:
    payload = task.get('payload')
    if payload != {'job_id': job.get('id'), 'dispatch_generation': job.get('dispatch_generation')}:
        raise StackFailure('Cloud Tasks handoff did not preserve the opaque durable job identity')
    if task.get('url') != stack.finalization_handler_url:
        raise StackFailure('Cloud Tasks handoff did not target the loopback worker route')


def _provider_events(stack: Stack, conversation_id: str, stage: str, outcome: str) -> list[dict[str, Any]]:
    return [
        event
        for event in stack.finalizer_events
        if event.get('event') == 'provider_leaf'
        and event.get('conversation_id') == conversation_id
        and event.get('stage') == stage
        and event.get('outcome') == outcome
    ]


async def _rest_finalization_survives_listener_restart(stack: Stack) -> None:
    """#10000's task seam also covers REST admission after the listener is lost."""
    if stack.finalization_mode != 'cloud_tasks':
        raise StackFailure('REST finalization recovery requires the Cloud Tasks stack')

    uid = 'stack-cloud-rest-restart'
    conversation_id = stack.rest_finalization_race_conversation_id
    if conversation_id is None:
        raise StackFailure('REST finalization race was not configured before listener startup')
    stack.seed_user(uid)
    websocket, session = await _connect(stack, uid, conversation_id)
    if session.get('conversation_id') != conversation_id:
        raise StackFailure('REST finalization recording did not preserve its native session identity')
    await _record_audio(websocket)

    def content_persisted() -> bool:
        conversation = stack.conversation(uid, conversation_id)
        return bool(conversation and conversation.get('has_content'))

    _wait_until(content_persisted, label='persisted content before REST finalization')
    responses = await _request_rest_finalization(
        stack, conversation_id, uid, requests=stack.rest_finalization_race_parties
    )
    for response in responses:
        if response.status_code != 200:
            raise StackFailure(f'REST finalization returned HTTP {response.status_code}: {response.text[:120]}')
        body = response.json()
        conversation = body.get('conversation') if isinstance(body, dict) else None
        if not isinstance(conversation, dict) or conversation.get('status') != 'processing':
            raise StackFailure('REST finalization did not return the admitted processing snapshot')

    task = stack.wait_for_finalization_task()
    job = _wait_for_job(stack, uid, conversation_id, 'queued')
    _assert_opaque_task(task, job, stack)
    duplicate_task_events = [
        event for event in stack.finalization_task_events if event.get('event') == 'task_already_exists'
    ]
    expected_duplicates = stack.rest_finalization_race_parties - 1
    if len(duplicate_task_events) != expected_duplicates:
        raise StackFailure(
            f'concurrent REST finalization expected {expected_duplicates} named-task AlreadyExists events, '
            f'observed {len(duplicate_task_events)}'
        )
    if any(
        event.get('task_name') != task.get('task_name') or event.get('payload') != task.get('payload')
        for event in duplicate_task_events
    ):
        raise StackFailure('duplicate REST admission changed the durable Cloud Tasks identity')
    if len(stack.finalization_tasks) != 1 or len(stack.jobs_for(uid, conversation_id)) != 1:
        raise StackFailure('duplicate REST finalization created more than one durable handoff')
    if job.get('attempt_count') != 0:
        raise StackFailure('duplicate REST finalization claimed work before worker delivery')

    queued_status = await stack.finalization_status(uid, conversation_id)
    if (
        queued_status.get('job_id') != job.get('id')
        or queued_status.get('status') != 'queued'
        or queued_status.get('terminal')
        or not queued_status.get('retryable')
        or queued_status.get('attempt_count') != 0
    ):
        raise StackFailure(f'queued REST finalization projection was incorrect: {queued_status}')

    denied_status, _ = await stack.deliver_finalization_task(task, retry_count=0, authenticated=False)
    if denied_status != 403:
        raise StackFailure(f'worker accepted an unauthenticated Cloud Tasks delivery: HTTP {denied_status}')
    if _wait_for_job(stack, uid, conversation_id, 'queued').get('attempt_count') != 0:
        raise StackFailure('unauthenticated delivery changed the queued durable job')

    # The task and Firestore job must survive a listener-process loss. The
    # detached worker process is the sole delivery owner after this point.
    stack.restart_backend()
    restarted_tasks = stack.finalization_tasks
    if len(restarted_tasks) != 1 or restarted_tasks[0] != task:
        raise StackFailure('listener restart did not retain the exact opaque Cloud Tasks handoff')
    restarted_task = restarted_tasks[0]
    delivered = await stack.deliver_finalization_task(restarted_task, retry_count=0)
    if delivered != (200, {'status': 'done'}):
        raise StackFailure(f'restarted-listener task delivery did not complete: {delivered}')

    completed = _wait_for_job(stack, uid, conversation_id, 'completed')
    if completed.get('attempt_count') != 1 or completed.get('fanout_status') != 'completed':
        raise StackFailure('detached worker did not complete the exact REST-finalization job once')
    completed_status = await stack.finalization_status(uid, conversation_id)
    if (
        completed_status.get('job_id') != job.get('id')
        or completed_status.get('status') != 'completed'
        or not completed_status.get('terminal')
        or completed_status.get('retryable')
        or completed_status.get('attempt_count') != 1
    ):
        raise StackFailure(f'completed REST finalization projection was incorrect: {completed_status}')

    process_events = _provider_events(stack, conversation_id, 'process', 'completed')
    if len(process_events) != 1:
        raise StackFailure('REST finalizer did not process the durable job exactly once')
    completed_conversation = stack.conversation(uid, conversation_id)
    if not completed_conversation or completed_conversation.get('status') != 'completed':
        raise StackFailure('restarted-listener delivery did not complete the user-visible conversation')
    if (
        not process_events[0].get('persisted')
        or not process_events[0].get('force_process')
        or not process_events[0].get('defer_derived_effects')
    ):
        raise StackFailure('REST finalization lost its persisted processing and extraction policy')
    if len(_provider_events(stack, conversation_id, 'integration', 'completed')) != 1:
        raise StackFailure('REST finalization did not complete durable integration fanout exactly once')

    provider_event_count = len(stack.finalizer_events)
    duplicate = await stack.deliver_finalization_task(restarted_task, retry_count=1)
    if duplicate != (200, {'status': 'acked', 'job_status': 'completed'}):
        raise StackFailure(f'duplicate REST task delivery was not safely acknowledged: {duplicate}')
    if (
        len(stack.finalization_tasks) != 1
        or _wait_for_job(stack, uid, conversation_id, 'completed').get('attempt_count') != 1
        or len(stack.finalizer_events) != provider_event_count
    ):
        raise StackFailure('duplicate REST task delivery repeated durable work')

    with suppress(Exception):
        await websocket.close(code=1000)


async def _shutdown_window_retries_through_cloud_tasks(stack: Stack) -> None:
    """#9960's early shutdown wake must redispatch the timed-out recording."""
    uid = 'stack-cloud-shutdown-retry'
    conversation_id = str(uuid.uuid4())
    stack.seed_user(uid)

    websocket, _ = await _connect(stack, uid, conversation_id)
    await _record_audio(websocket)
    stack.age_conversation(uid, conversation_id)
    # A non-clean disconnect leaves this recording pending.  The following
    # session wakes process_pending before its seven-second delay expires.
    await websocket.close(code=1001)
    if stack.finalization_tasks:
        raise StackFailure('abnormal close unexpectedly bypassed the pending-finalization recovery path')

    recovery_session, _ = await _connect(stack, uid, None)
    await recovery_session.close(code=1000)
    # The production shutdown event shortens the seven-second pending delay.
    # Keep this below seven seconds so the scenario fails if that work becomes
    # an unconditional sleep again.
    task = stack.wait_for_finalization_task(timeout=5.0)
    job = _one_job(stack, uid, conversation_id)
    _assert_opaque_task(task, job, stack)
    if job.get('status') != 'queued' or job.get('attempt_count') != 0:
        raise StackFailure('shutdown recovery did not leave one queued durable finalization job')

    status_code, body = await stack.deliver_finalization_task(task, retry_count=0)
    if (status_code, body) != (500, {'status': 'retry'}):
        raise StackFailure(f'first Cloud Tasks delivery did not request a retry: {(status_code, body)}')
    retry_job = _one_job(stack, uid, conversation_id)
    retry_conversation = stack.conversation(uid, conversation_id)
    if retry_job.get('status') != 'queued' or retry_job.get('attempt_count') != 1:
        raise StackFailure('retryable worker failure did not return the same job to the durable queue')
    if not retry_conversation or retry_conversation.get('status') != 'processing':
        raise StackFailure('retryable worker failure changed the conversation before a successful finalization')
    retry_status = await stack.finalization_status(uid, conversation_id)
    if retry_status.get('status') != 'queued' or not retry_status.get('retryable'):
        raise StackFailure('client finalization status did not expose the retryable durable state')

    status_code, body = await stack.deliver_finalization_task(task, retry_count=1)
    if (status_code, body) != (200, {'status': 'done'}):
        raise StackFailure(f'retry Cloud Tasks delivery did not complete: {(status_code, body)}')
    completed_job = _one_job(stack, uid, conversation_id)
    completed_conversation = stack.conversation(uid, conversation_id)
    if completed_job.get('status') != 'completed' or completed_job.get('attempt_count') != 2:
        raise StackFailure('successful retry did not complete the exact durable job')
    if completed_job.get('fanout_status') != 'completed':
        raise StackFailure('successful retry did not complete durable fanout')
    if not completed_conversation or completed_conversation.get('status') != 'completed':
        raise StackFailure('successful retry did not complete the recovered conversation')
    completed_status = await stack.finalization_status(uid, conversation_id)
    if completed_status.get('status') != 'completed' or not completed_status.get('terminal'):
        raise StackFailure('client finalization status did not expose the completed terminal state')
    if len(stack.finalization_tasks) != 1:
        raise StackFailure('worker retry created a second Cloud Tasks handoff')
    if len(_provider_events(stack, conversation_id, 'process', 'controlled_failure')) != 1:
        raise StackFailure('controlled processing failure was not observed exactly once')
    if len(_provider_events(stack, conversation_id, 'process', 'completed')) != 1:
        raise StackFailure('recovered processing did not execute exactly once')


async def _terminal_cloud_tasks_failure_dead_letters(stack: Stack) -> None:
    uid = 'stack-cloud-dead-letter'
    conversation_id = str(uuid.uuid4())
    task = await _cloud_task_for_clean_desktop_close(stack, uid, conversation_id)
    job = _one_job(stack, uid, conversation_id)
    _assert_opaque_task(task, job, stack)

    first = await stack.deliver_finalization_task(task, retry_count=0)
    if first != (500, {'status': 'retry'}):
        raise StackFailure(f'first terminal-path delivery did not request a retry: {first}')
    final = await stack.deliver_finalization_task(task, retry_count=1)
    if final != (200, {'status': 'dead_letter'}):
        raise StackFailure(f'final delivery did not dead-letter the exhausted job: {final}')

    dead_letter = _one_job(stack, uid, conversation_id)
    conversation = stack.conversation(uid, conversation_id)
    if (
        dead_letter.get('status') != 'dead_letter'
        or dead_letter.get('attempt_count') != 2
        or dead_letter.get('task_retry_count') != 2
    ):
        raise StackFailure('exhausted worker delivery did not record its terminal durable state')
    if not conversation or {
        'status': conversation.get('status'),
        'discarded': conversation.get('discarded'),
        'finalization_status': conversation.get('finalization_status'),
    } != {'status': 'failed', 'discarded': True, 'finalization_status': 'dead_letter'}:
        raise StackFailure('dead-lettering did not atomically close the processing conversation')
    projection = await stack.finalization_status(uid, conversation_id)
    if projection.get('status') != 'dead_letter' or not projection.get('terminal') or projection.get('retryable'):
        raise StackFailure('client finalization status did not expose the dead-letter terminal state')

    redelivery = await stack.deliver_finalization_task(task, retry_count=2)
    if redelivery != (200, {'status': 'dropped', 'reason': 'dead_letter'}):
        raise StackFailure(f'dead-letter redelivery was not safely fenced: {redelivery}')
    if len(_provider_events(stack, conversation_id, 'process', 'controlled_failure')) != 2:
        raise StackFailure('dead-letter path did not consume exactly the configured attempt budget')
    if len(stack.finalization_tasks) != 1:
        raise StackFailure('dead-letter path created a new finalization generation')


async def _integration_retry_preserves_processed_conversation(stack: Stack) -> None:
    uid = 'stack-cloud-integration-retry'
    conversation_id = str(uuid.uuid4())
    task = await _cloud_task_for_clean_desktop_close(stack, uid, conversation_id)
    first = await stack.deliver_finalization_task(task, retry_count=0)
    if first != (500, {'status': 'retry'}):
        raise StackFailure(f'integration failure delivery did not request a retry: {first}')
    after_failure = _one_job(stack, uid, conversation_id)
    conversation = stack.conversation(uid, conversation_id)
    if after_failure.get('status') != 'queued' or not conversation or conversation.get('status') != 'completed':
        raise StackFailure('integration failure did not retain completed processing work for fanout retry')
    fanout_key = after_failure.get('fanout_key')
    if not isinstance(fanout_key, str) or not fanout_key:
        raise StackFailure('integration failure did not retain a durable fanout idempotency key')

    final = await stack.deliver_finalization_task(task, retry_count=1)
    if final != (200, {'status': 'done'}):
        raise StackFailure(f'integration retry did not complete finalization: {final}')
    completed = _one_job(stack, uid, conversation_id)
    if completed.get('status') != 'completed' or completed.get('fanout_status') != 'completed':
        raise StackFailure('integration retry did not complete the durable fanout boundary')
    if completed.get('fanout_key') != fanout_key:
        raise StackFailure('integration retry changed the durable fanout idempotency key')
    if len(_provider_events(stack, conversation_id, 'process', 'completed')) != 1:
        raise StackFailure('fanout retry re-ran completed conversation processing')
    if len(_provider_events(stack, conversation_id, 'integration', 'controlled_failure')) != 1:
        raise StackFailure('controlled integration failure was not observed exactly once')
    if len(_provider_events(stack, conversation_id, 'integration', 'completed')) != 1:
        raise StackFailure('integration retry did not deliver the durable fanout exactly once')
    integration_attempts = [
        event
        for event in stack.finalizer_events
        if event.get('event') == 'provider_leaf'
        and event.get('conversation_id') == conversation_id
        and event.get('stage') == 'integration'
    ]
    fanout_key_hashes = {event.get('fanout_key_sha256') for event in integration_attempts}
    expected_fanout_key_hash = sha256(fanout_key.encode('utf-8')).hexdigest()
    if len(integration_attempts) != 2 or fanout_key_hashes != {expected_fanout_key_hash}:
        raise StackFailure('integration retry did not preserve one idempotency key across both delivery attempts')


async def _stale_processing_orphan_reconciled(stack: Stack) -> None:
    """#10461: a bare-`processing` row orphaned by a sync-route crash reaches one terminal.

    Covers the revised authority/saturation contract: eligibility is bounded by
    the server-owned admission fence (never caller-controlled created_at), legacy
    rows migrate before they complete, deferred rows are excluded, a backlog of
    excluded rows cannot starve a later eligible orphan, and every outcome is
    reached through the lifecycle CAS alone — no durable job, worker, or fanout.
    """
    if stack.finalization_mode != 'cloud_tasks':
        raise StackFailure('stale-processing orphan recovery requires the Cloud Tasks stack')

    uid = 'stack-stale-orphan'
    saturation_uid = 'stack-stale-saturation'
    stack.seed_user(uid)
    stack.seed_user(saturation_uid)

    now = datetime.now(timezone.utc)
    aged_id = 'stale-orphan-aged'
    fresh_id = 'stale-orphan-fresh'
    durable_id = 'stale-orphan-durable-job'
    legacy_id = 'stale-orphan-legacy'
    deferred_id = 'stale-orphan-deferred'

    # Aged admission: admitted long enough ago that only a genuine crash could
    # still be on `processing` with no durable job.
    stack.seed_bare_processing_conversation(uid, aged_id, admitted_at=now - timedelta(seconds=1000))
    # Fresh admission under the conservative threshold: must be left alone.
    stack.seed_bare_processing_conversation(uid, fresh_id, admitted_at=now - timedelta(seconds=10))
    # A durable job still owns this row: the orphan sweep must never double-finalize it.
    stack.seed_bare_processing_conversation(
        uid, durable_id, admitted_at=now - timedelta(seconds=1000), finalization_job_id='stale-orphan-durable-job-id'
    )
    # A legacy row predating the admission fence: must be migrated (stamped), never
    # completed on first sight even though its caller-controlled created_at is ancient.
    stack.seed_bare_processing_conversation(uid, legacy_id, admitted_at=now - timedelta(days=30), legacy=True)
    # A desktop lazy row that intentionally lives on `processing`: must be excluded.
    stack.seed_bare_processing_conversation(uid, deferred_id, admitted_at=now - timedelta(seconds=1000), deferred=True)
    # Saturation: 120 excluded (deferred) rows ahead of one aged eligible orphan. The
    # sweep must page past the excluded first page and still reach the orphan.
    for i in range(120):
        stack.seed_bare_processing_conversation(
            saturation_uid, f'saturation-deferred-{i:03d}', admitted_at=now - timedelta(seconds=1000), deferred=True
        )
    saturation_orphan_id = 'saturation-orphan'
    stack.seed_bare_processing_conversation(
        saturation_uid, saturation_orphan_id, admitted_at=now - timedelta(seconds=1000)
    )

    # The startup drain re-runs on restart and is the deterministic reconciler trigger.
    stack.restart_backend()

    def completed(target_uid: str, target_id: str) -> Callable[[], bool]:
        def check() -> bool:
            conversation = stack.conversation(target_uid, target_id)
            return bool(conversation and conversation.get('status') == 'completed')

        return check

    _wait_until(completed(uid, aged_id), label='aged orphan reconciled to completed', timeout=30.0)
    _wait_until(
        completed(saturation_uid, saturation_orphan_id),
        label='saturation orphan reached past the excluded backlog',
        timeout=30.0,
    )

    aged = stack.conversation(uid, aged_id)
    if not aged or aged.get('status') != 'completed':
        raise StackFailure('stale processing reconciler did not close the aged orphan')
    # Exactly one terminal, reached through the lifecycle CAS alone — no durable
    # job is created and no worker/enrichment runs (re-enrichment is a follow-up).
    if stack.jobs_for(uid, aged_id):
        raise StackFailure('stale processing reconciler created a durable job for the orphan')
    if _provider_events(stack, aged_id, 'process', 'completed'):
        raise StackFailure('stale processing reconciler invoked the durable finalization worker')
    if _provider_events(stack, aged_id, 'integration', 'completed'):
        raise StackFailure('stale processing reconciler duplicated an integration fanout')

    # The conservative threshold is respected: a too-recent admission is left on `processing`.
    fresh = stack.conversation(uid, fresh_id)
    if not fresh or fresh.get('status') != 'processing':
        raise StackFailure('stale processing reconciler swept an admission under the conservative threshold')

    # A durable job still owns its row: the orphan sweep never double-finalizes it.
    durable = stack.conversation(uid, durable_id)
    if not durable or durable.get('status') != 'processing':
        raise StackFailure('stale processing reconciler touched a durable-job-owned conversation')

    # Deferred rows are excluded in every case — single and across the saturation backlog.
    deferred = stack.conversation(uid, deferred_id)
    if not deferred or deferred.get('status') != 'processing':
        raise StackFailure('stale processing reconciler swept a deferred desktop row')
    leftover_deferred = stack.conversation(saturation_uid, 'saturation-deferred-000')
    if not leftover_deferred or leftover_deferred.get('status') != 'processing':
        raise StackFailure('stale processing reconciler swept a backlog deferred row')

    # The legacy row is migrated, not completed on first sight: it now carries the
    # server-owned admission fence but is still on `processing`.
    legacy = stack.conversation(uid, legacy_id)
    if not legacy or legacy.get('status') != 'processing':
        raise StackFailure('stale processing reconciler terminalized a legacy row on first sight')
    if not legacy.get('processing_admitted_at'):
        raise StackFailure('stale processing reconciler did not stamp the admission fence on the legacy row')

    # The terminal conversation is retrievable through the public read path.
    retrieved = await stack.conversation_via_api(uid, aged_id)
    if retrieved.get('status') != 'completed' or retrieved.get('id') != aged_id:
        raise StackFailure('GET /v1/conversations/{id} did not return the reconciled terminal conversation')

    # The legacy row, once its stamped admission has aged, is recovered on a later
    # sweep — proving the two-phase legacy path without waiting the real threshold.
    stack.firestore.collection('users').document(uid).collection('conversations').document(legacy_id).update(
        {'processing_admitted_at': datetime.now(timezone.utc) - timedelta(seconds=1000)}
    )
    stack.restart_backend()
    _wait_until(completed(uid, legacy_id), label='legacy row recovered after its fence aged', timeout=30.0)
    if _provider_events(stack, legacy_id, 'process', 'completed') or _provider_events(
        stack, legacy_id, 'integration', 'completed'
    ):
        raise StackFailure('legacy row recovery produced a worker or integration fanout')

    # Re-running the sweep is a no-op: completed orphans stay on their single terminal.
    stack.restart_backend()
    _wait_until(completed(uid, aged_id), label='aged orphan still completed after re-sweep', timeout=30.0)
    if stack.conversation(uid, aged_id).get('status') != 'completed' or stack.jobs_for(uid, aged_id):
        raise StackFailure('stale processing reconciler was not idempotent across sweeps')


async def _stale_processing_orphan_reconciled_inline(stack: Stack) -> None:
    """The orphan reconciler also runs without Cloud Tasks (inline deployments).

    Proves the periodic/startup sweep is not gated on durable dispatch: an aged
    orphan reaches one terminal, a fresh admission is left alone, a legacy row is
    migrated, and a deferred row is excluded.
    """
    uid = 'stack-inline-stale-orphan'
    stack.seed_user(uid)
    now = datetime.now(timezone.utc)
    aged_id = 'inline-aged'
    fresh_id = 'inline-fresh'
    legacy_id = 'inline-legacy'
    deferred_id = 'inline-deferred'
    stack.seed_bare_processing_conversation(uid, aged_id, admitted_at=now - timedelta(seconds=1000))
    stack.seed_bare_processing_conversation(uid, fresh_id, admitted_at=now - timedelta(seconds=10))
    stack.seed_bare_processing_conversation(uid, legacy_id, admitted_at=now - timedelta(days=30), legacy=True)
    stack.seed_bare_processing_conversation(uid, deferred_id, admitted_at=now - timedelta(seconds=1000), deferred=True)

    stack.restart_backend()

    def aged_completed() -> bool:
        conversation = stack.conversation(uid, aged_id)
        return bool(conversation and conversation.get('status') == 'completed')

    _wait_until(aged_completed, label='inline aged orphan reconciled to completed', timeout=30.0)

    if stack.conversation(uid, fresh_id).get('status') != 'processing':
        raise StackFailure('inline reconciler swept a fresh admission')
    legacy = stack.conversation(uid, legacy_id)
    if legacy.get('status') != 'processing' or not legacy.get('processing_admitted_at'):
        raise StackFailure('inline reconciler did not migrate the legacy row without completing it')
    if stack.conversation(uid, deferred_id).get('status') != 'processing':
        raise StackFailure('inline reconciler swept a deferred row')


async def run_inline_scenarios(stack: Stack) -> None:
    await _normal_and_terminal_reconnect(stack)
    await _empty_recording(stack)
    await _pusher_restart_replay(stack)


def _run_stack_scenario(
    state_dir: Path,
    *,
    finalization_mode: str,
    finalizer_failures: dict[str, int] | None,
    hold_inline_finalization: bool = False,
    rest_finalization_race_uid: str | None = None,
    rest_finalization_race_parties: int = 0,
    scenario: Callable[[Stack], Any],
) -> None:
    stack = Stack(
        state_dir,
        finalization_mode=finalization_mode,
        finalizer_failures=finalizer_failures,
        hold_inline_finalization=hold_inline_finalization,
        rest_finalization_race_uid=rest_finalization_race_uid,
        rest_finalization_race_parties=rest_finalization_race_parties,
    )
    try:
        stack.start()
        asyncio.run(scenario(stack))
    finally:
        stack.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-dir', type=Path, help='directory for sanitized process logs and JSONL evidence')
    parser.add_argument('--keep', action='store_true', help='preserve generated evidence after a successful run')
    args = parser.parse_args()
    if not PYTHON.exists():
        raise SystemExit(f'missing backend virtual environment: {PYTHON}; run backend/scripts/sync-python-deps.sh')
    state_dir = args.state_dir or Path(tempfile.mkdtemp(prefix='omi-listen-pusher-stack-'))
    state_dir.mkdir(parents=True, exist_ok=True)
    try:
        _run_stack_scenario(
            state_dir / 'inline',
            finalization_mode='inline',
            finalizer_failures=None,
            scenario=run_inline_scenarios,
        )
        _run_stack_scenario(
            state_dir / 'inline-source-close',
            finalization_mode='inline',
            finalizer_failures=None,
            hold_inline_finalization=True,
            scenario=_inline_finalization_survives_source_close,
        )
        _run_stack_scenario(
            state_dir / 'inline-stale-orphan',
            finalization_mode='inline',
            finalizer_failures=None,
            scenario=_stale_processing_orphan_reconciled_inline,
        )
        _run_stack_scenario(
            state_dir / 'cloud-rest-restart',
            finalization_mode='cloud_tasks',
            finalizer_failures=None,
            rest_finalization_race_uid='stack-cloud-rest-restart',
            rest_finalization_race_parties=4,
            scenario=_rest_finalization_survives_listener_restart,
        )
        _run_stack_scenario(
            state_dir / 'cloud-shutdown-retry',
            finalization_mode='cloud_tasks',
            finalizer_failures={'process': 1},
            scenario=_shutdown_window_retries_through_cloud_tasks,
        )
        _run_stack_scenario(
            state_dir / 'cloud-dead-letter',
            finalization_mode='cloud_tasks',
            finalizer_failures={'process': 2},
            scenario=_terminal_cloud_tasks_failure_dead_letters,
        )
        _run_stack_scenario(
            state_dir / 'cloud-integration-retry',
            finalization_mode='cloud_tasks',
            finalizer_failures={'integration': 1},
            scenario=_integration_retry_preserves_processed_conversation,
        )
        _run_stack_scenario(
            state_dir / 'cloud-stale-orphan',
            finalization_mode='cloud_tasks',
            finalizer_failures=None,
            scenario=_stale_processing_orphan_reconciled,
        )
        print(f'listen-pusher stack gauntlet passed; evidence: {state_dir}')
        return 0
    except Exception as error:
        print(f'listen-pusher stack gauntlet failed; evidence retained: {state_dir}', file=sys.stderr)
        raise
    finally:
        if not args.keep and not sys.exc_info()[0]:
            shutil.rmtree(state_dir)


if __name__ == '__main__':
    raise SystemExit(main())
