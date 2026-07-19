"""Run the process-isolated Sync Cloud Tasks stack gauntlet.

Invoke through ``run.sh`` so Firebase owns a fresh Firestore emulator.  The
supervisor starts private Redis plus independent admission and worker ASGI
processes; it never probes, reuses, or stops developer services.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import shutil
import signal
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Callable

import google.auth
import httpx
import redis
from google.auth import credentials as google_auth_credentials
from google.cloud import firestore

ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / 'backend'
PYTHON = BACKEND / '.venv' / 'bin' / 'python'
PROJECT = 'demo-omi-sync-cloud-tasks-stack'
ADMIN_KEY = 'omi-sync-cloud-tasks-stack-admin-'
LOCAL_OIDC_AUDIENCE = 'https://sync-stack.local/v2/sync-jobs/run'
LOCAL_INVOKER_SA = 'sync-stack-invoker@demo-omi-sync-cloud-tasks-stack.iam.gserviceaccount.com'
LOCAL_OIDC_TOKEN = f'local-sync-oidc:{LOCAL_INVOKER_SA}'
SYNC_QUEUE = 'sync-jobs'
SENSITIVE_UID = 'sync-stack-sensitive-uid'
TRANSCRIPT_TOKEN = 'Sync stack transcript verified.'
DEVICE_HASH = '01234567'
DEVICE_ID = f'ios_{DEVICE_HASH}'
ENCRYPTION_SECRET = 'omi_sync_cloud_tasks_stack_test_secret_32_bytes'


class StackFailure(AssertionError):
    """An actionable assertion failure from a local stack scenario."""


@dataclass
class Child:
    name: str
    process: subprocess.Popen[bytes]
    log_path: Path


def _anonymous_google_credentials(
    *_args: Any, **_kwargs: Any
) -> tuple[google_auth_credentials.AnonymousCredentials, str]:
    return google_auth_credentials.AnonymousCredentials(), PROJECT


# The parent itself uses only the loopback Firestore emulator; never discover ADC.
google.auth.default = _anonymous_google_credentials


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(('127.0.0.1', 0))
        return int(probe.getsockname()[1])


def _wait_for_port(port: int, *, label: str, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(('127.0.0.1', port), timeout=0.25):
                return
        except OSError:
            time.sleep(0.1)
    raise StackFailure(f'{label} did not listen on 127.0.0.1:{port} within {timeout:.0f}s')


def _wait_until(predicate: Callable[[], bool], *, label: str, timeout: float = 25.0) -> None:
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


class Stack:
    def __init__(
        self,
        state_dir: Path,
        *,
        task_ack_failures: int = 0,
        worker_failures: int = 0,
        pre_ledger_failures: int = 0,
        post_ledger_failures: int = 0,
        cleanup_failures: int = 0,
        hold_processor: bool = False,
    ):
        self.state_dir = state_dir
        self.logs_dir = state_dir / 'logs'
        self.evidence_dir = state_dir / 'evidence'
        self.storage_dir = state_dir / 'local-storage'
        self.gate_dir = state_dir / 'processor-gate' if hold_processor else None
        self.redis_port = _free_port()
        self.admission_port = _free_port()
        self.worker_port = _free_port()
        self.task_ack_failures = task_ack_failures
        self.worker_failures = worker_failures
        self.pre_ledger_failures = pre_ledger_failures
        self.post_ledger_failures = post_ledger_failures
        self.cleanup_failures = cleanup_failures
        self.children: dict[str, Child] = {}
        self.http = httpx.Client(timeout=15.0, trust_env=False)
        self.control_token = secrets.token_urlsafe(32)
        self.uid_namespace = f'{SENSITIVE_UID}-{secrets.token_hex(8)}'
        self.created_uids: set[str] = set()

        # Runner-side evidence follows the same sanitizer as the ASGI roles.
        os.environ['OMI_SYNC_STACK_STATE_DIR'] = str(state_dir)
        os.environ['OMI_SYNC_STACK_SENSITIVE_UID'] = SENSITIVE_UID
        os.environ['OMI_SYNC_STACK_TRANSCRIPT_TOKEN'] = TRANSCRIPT_TOKEN
        os.environ['ENCRYPTION_SECRET'] = ENCRYPTION_SECRET
        os.environ.pop('GOOGLE_APPLICATION_CREDENTIALS', None)
        os.environ.pop('SERVICE_ACCOUNT_JSON', None)
        self.env = self._environment()
        self.firestore = firestore.Client(project=PROJECT)

    def _environment(self) -> dict[str, str]:
        firestore_host = os.getenv('FIRESTORE_EMULATOR_HOST', '').strip()
        host = firestore_host.rsplit(':', 1)[0] if ':' in firestore_host else firestore_host
        if host not in {'127.0.0.1', 'localhost'}:
            raise StackFailure('FIRESTORE_EMULATOR_HOST must be loopback; run via run.sh')
        for directory in (self.logs_dir, self.evidence_dir, self.storage_dir):
            directory.mkdir(parents=True, exist_ok=True)
        if self.gate_dir is not None:
            self.gate_dir.mkdir(parents=True, exist_ok=True)

        # Inherit no provider keys, proxy configuration, ADC paths, or cloud CLI state.
        env = {key: os.environ[key] for key in ('PATH', 'LANG', 'LC_ALL', 'TZ', 'TMPDIR') if os.getenv(key)}
        isolated_home = self.state_dir / 'home'
        isolated_config = self.state_dir / 'config'
        env.update(
            {
                'HOME': str(isolated_home),
                'XDG_CONFIG_HOME': str(isolated_config),
                'CLOUDSDK_CONFIG': str(isolated_config / 'gcloud'),
                'NO_PROXY': '127.0.0.1,localhost',
                'no_proxy': '127.0.0.1,localhost',
                'FIRESTORE_EMULATOR_HOST': firestore_host,
                'FIREBASE_AUTH_EMULATOR_HOST': '127.0.0.1:9099',
                'OMI_HARNESS_INSTANCE': 'sync-cloud-tasks-stack',
                'OMI_ENV_STAGE': 'offline',
                'PROVIDER_MODE': 'offline',
                'LOCAL_DEVELOPMENT': 'true',
                'FIREBASE_PROJECT_ID': PROJECT,
                'GOOGLE_CLOUD_PROJECT': PROJECT,
                'GCLOUD_PROJECT': PROJECT,
                'FIRESTORE_DATABASE_ID': '(default)',
                'ENCRYPTION_SECRET': ENCRYPTION_SECRET,
                'ADMIN_KEY': ADMIN_KEY,
                'REDIS_DB_HOST': '127.0.0.1',
                'REDIS_DB_PORT': str(self.redis_port),
                'REDIS_DB_PASSWORD': '',
                'SYNC_DISPATCH_MODE': 'cloud_tasks',
                'SYNC_LEDGER_FENCE_MODE': 'active',
                'SYNC_TASKS_PROJECT': PROJECT,
                'SYNC_TASKS_LOCATION': 'local',
                'SYNC_TASKS_QUEUE': SYNC_QUEUE,
                'SYNC_TASKS_HANDLER_URL': self.worker_url + '/v2/sync-jobs/run',
                'SYNC_TASKS_OIDC_AUDIENCE': LOCAL_OIDC_AUDIENCE,
                'SYNC_TASKS_INVOKER_SA': LOCAL_INVOKER_SA,
                'SYNC_TASKS_MAX_ATTEMPTS': '2',
                'HTTP_SYNC_JOBS_RUN_TIMEOUT': '30',
                'FAIR_USE_ENABLED': 'true',
                'MAX_DAILY_AUDIO_HOURS': '30',
                'TRIAL_PAYWALL_ENABLED': 'false',
                'STT_PRERECORDED_MODEL': 'parakeet',
                'STT_SERVICE_MODELS': 'parakeet',
                'HOSTED_PARAKEET_API_URL': 'http://127.0.0.1:1',
                'BUCKET_TEMPORAL_SYNC_LOCAL': 'sync-temporal',
                'BUCKET_SPEECH_PROFILES': 'speech-profiles',
                'BUCKET_POSTPROCESSING': 'postprocessing',
                'BUCKET_PRIVATE_CLOUD_SYNC': 'omi-private-cloud-sync',
                'BUCKET_MEMORIES_RECORDINGS': 'memories-recordings',
                'BUCKET_APP_THUMBNAILS': 'app-thumbnails',
                'BUCKET_CHAT_FILES': 'chat-files',
                'BUCKET_DESKTOP_UPDATES': 'desktop-updates',
                'STRIPE_SECRET_KEY': '',
                'OMI_SYNC_STACK_STATE_DIR': str(self.state_dir),
                'OMI_SYNC_STACK_STORAGE_DIR': str(self.storage_dir),
                'OMI_SYNC_STACK_CONTROL_TOKEN': self.control_token,
                'OMI_SYNC_STACK_SENSITIVE_UID': SENSITIVE_UID,
                'OMI_SYNC_STACK_TRANSCRIPT_TOKEN': TRANSCRIPT_TOKEN,
                'OMI_SYNC_STACK_LOST_TASK_ACKS': str(self.task_ack_failures),
                'OMI_SYNC_STACK_WORKER_FAILURES': str(self.worker_failures),
                'OMI_SYNC_STACK_PRE_LEDGER_FAILURES': str(self.pre_ledger_failures),
                'OMI_SYNC_STACK_POST_LEDGER_FAILURES': str(self.post_ledger_failures),
                'OMI_SYNC_STACK_CLEANUP_FAILURES': str(self.cleanup_failures),
                'OMI_SYNC_STACK_PROCESS_GATE_DIR': str(self.gate_dir) if self.gate_dir is not None else '',
                'PYTHONPATH': str(BACKEND),
            }
        )
        return env

    @property
    def admission_url(self) -> str:
        return f'http://127.0.0.1:{self.admission_port}'

    @property
    def worker_url(self) -> str:
        return f'http://127.0.0.1:{self.worker_port}'

    @property
    def control_headers(self) -> dict[str, str]:
        return {'X-Omi-Sync-Stack-Control': self.control_token}

    def _start(self, name: str, command: list[str], *, role: str | None = None) -> Child:
        if name in self.children:
            raise StackFailure(f'{name} is already running')
        log_path = self.logs_dir / f'{name}.log'
        process_env = self.env.copy()
        if role:
            process_env['OMI_SYNC_STACK_ROLE'] = role
        output = log_path.open('wb')
        process = subprocess.Popen(
            command,
            cwd=BACKEND,
            env=process_env,
            stdin=subprocess.DEVNULL,
            stdout=output,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        child = Child(name=name, process=process, log_path=log_path)
        self.children[name] = child
        return child

    def _assert_health(self, base_url: str, *, role: str) -> None:
        def healthy() -> bool:
            try:
                response = self.http.get(base_url + '/__sync-stack/health', timeout=1.0)
                body = response.json()
                return response.status_code == 200 and body == {'status': 'ok', 'role': role}
            except (httpx.HTTPError, ValueError):
                return False

        _wait_until(healthy, label=f'Sync {role} health endpoint', timeout=20.0)

    def start(self) -> None:
        redis_binary = shutil.which('redis-server')
        if not redis_binary:
            raise StackFailure('redis-server is required; install Redis and retry')
        self._start(
            'redis',
            [
                redis_binary,
                '--bind',
                '127.0.0.1',
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
        _wait_for_port(self.redis_port, label='isolated Redis')
        redis.Redis(host='127.0.0.1', port=self.redis_port).ping()
        self._start(
            'worker',
            [
                str(PYTHON),
                '-m',
                'uvicorn',
                'testing.sync_cloud_tasks_stack.worker_app:app',
                '--host',
                '127.0.0.1',
                '--port',
                str(self.worker_port),
            ],
            role='worker',
        )
        _wait_for_port(self.worker_port, label='Sync worker', timeout=120.0)
        self._assert_health(self.worker_url, role='worker')
        self._start(
            'admission',
            [
                str(PYTHON),
                '-m',
                'uvicorn',
                'testing.sync_cloud_tasks_stack.admission_app:app',
                '--host',
                '127.0.0.1',
                '--port',
                str(self.admission_port),
            ],
            role='admission',
        )
        _wait_for_port(self.admission_port, label='Sync admission', timeout=45.0)
        self._assert_health(self.admission_url, role='admission')

    def stop(self, name: str) -> None:
        child = self.children.pop(name, None)
        if child is None or child.process.poll() is not None:
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
        for name in list(self.children):
            self.stop(name)
        self.http.close()

    def cleanup_workspace_files(self) -> None:
        sync_root = (BACKEND / 'syncing').resolve()
        for uid in self.created_uids:
            target = (sync_root / uid).resolve()
            if target.parent != sync_root or not uid.startswith(SENSITIVE_UID):
                raise StackFailure(f'refusing unexpected Sync cleanup target: {target}')
            if target.exists():
                shutil.rmtree(target)

    def seed_user(self, uid: str) -> None:
        self.created_uids.add(uid)
        self.firestore.collection('users').document(uid).set(
            {
                'id': uid,
                'language': 'en',
                'private_cloud_sync_enabled': False,
                'data_protection_level': 'enhanced',
                'transcription_preferences': {'uses_custom_stt': False},
                'subscription': {'plan': 'basic', 'status': 'active'},
            }
        )
        self.firestore.collection('users').document(uid).collection('fair_use_state').document('current').set(
            {'stage': 'none'}
        )

    def scenario_uid(self, scenario: str) -> str:
        """Give each stack instance a private Sync workspace namespace."""
        return f'{self.uid_namespace}-{scenario}'

    def evidence_events(self, stream: str) -> list[dict[str, Any]]:
        return _read_events(self.evidence_dir / f'{stream}.jsonl')

    def task_control(self, task_id: str) -> dict[str, Any]:
        response = self.http.get(
            self.admission_url + f'/__sync-stack/tasks/{task_id}', headers=self.control_headers, timeout=5.0
        )
        if response.status_code != 200:
            raise StackFailure(f'captured task {task_id} unavailable: HTTP {response.status_code}')
        payload = response.json()
        if not isinstance(payload, dict):
            raise StackFailure('captured task control endpoint returned a non-object')
        return payload

    def staged_blob_path(self, blob_path: str) -> Path:
        relative = PurePosixPath(blob_path)
        if relative.is_absolute() or '..' in relative.parts:
            raise StackFailure('task yielded an unsafe staged blob path')
        return self.storage_dir / 'sync-temporal' / Path(*relative.parts)

    def fair_use_meter_ms(self, uid: str) -> int:
        values = redis.Redis(host='127.0.0.1', port=self.redis_port).hgetall(f'fair_use:v2:bucket:sync_fresh:{uid}')
        return sum(int(value) for value in values.values())


def _pcm16_upload_bytes() -> bytes:
    """One second of framed PCM16 accepted by the production v2 decoder."""
    frame = struct.pack('<h', 1200) * 1600
    return b''.join(struct.pack('<I', len(frame)) + frame for _ in range(10))


def _fresh_pcm_filename() -> str:
    return f'audio_omi_pcm16_16000_1_fs160_{int(time.time()) - 60}.bin'


def _record_job_event(event: dict[str, Any]) -> None:
    from testing.sync_cloud_tasks_stack.events import write_event

    write_event('jobs', event)


def _auth_headers(uid: str) -> dict[str, str]:
    return {'Authorization': f'Bearer {ADMIN_KEY}{uid}'}


def _seed_capture_conversation(stack: Stack, uid: str, conversation_id: str) -> None:
    """Seed real encoded provenance inside the isolated admission process."""
    response = stack.http.post(
        stack.admission_url + f'/__sync-stack/capture-provenance/{conversation_id}',
        json={'uid': uid, 'device_id': DEVICE_ID, 'platform': 'ios'},
        headers=stack.control_headers,
        timeout=10.0,
    )
    if response.status_code != 204:
        raise StackFailure(f'isolated capture provenance seed returned HTTP {response.status_code}')


def _submit_and_capture_task(stack: Stack, uid: str) -> tuple[str, dict[str, Any]]:
    stack.seed_user(uid)
    filename = _fresh_pcm_filename()
    audio = _pcm16_upload_bytes()
    capture_conversation_id = f'sync-stack-capture-{uuid.uuid4().hex}'
    _seed_capture_conversation(stack, uid, capture_conversation_id)
    common_headers = {
        **_auth_headers(uid),
        'X-App-Platform': 'ios',
        'X-Device-Id-Hash': DEVICE_HASH,
    }
    manifest_response = stack.http.post(
        stack.admission_url + '/v2/sync-capture-manifest',
        json={
            'conversation_id': capture_conversation_id,
            'files': [{'name': filename, 'sha256': hashlib.sha256(audio).hexdigest()}],
        },
        headers=common_headers,
        timeout=10.0,
    )
    if manifest_response.status_code != 200:
        raise StackFailure(f'fresh capture manifest returned HTTP {manifest_response.status_code}')
    manifest_body = manifest_response.json()
    manifest = manifest_body.get('manifest') if isinstance(manifest_body, dict) else None
    if not isinstance(manifest, str) or not manifest:
        raise StackFailure('fresh capture manifest response omitted its signed manifest')
    response = stack.http.post(
        stack.admission_url + f'/v2/sync-local-files?conversation_id={capture_conversation_id}',
        files=[('files', (filename, audio, 'application/octet-stream'))],
        headers={**common_headers, 'X-Omi-Sync-Capture-Manifest': manifest},
        timeout=20.0,
    )
    if response.status_code != 202:
        raise StackFailure(f'Sync admission returned HTTP {response.status_code}: {response.text[:160]}')
    admitted = response.json()
    job_id = admitted.get('job_id') if isinstance(admitted, dict) else None
    if not isinstance(job_id, str) or admitted.get('status') != 'queued' or admitted.get('lane') != 'fresh':
        raise StackFailure('Sync admission did not return one queued fresh job')

    captured: dict[str, Any] = {}

    def task_captured() -> bool:
        nonlocal captured
        try:
            captured = stack.task_control(job_id)
        except (httpx.HTTPError, StackFailure):
            return False
        return isinstance(captured.get('body'), dict)

    _wait_until(task_captured, label=f'Cloud Tasks capture for job {job_id}', timeout=10.0)
    _assert_task_contract(stack, job_id, uid, capture_conversation_id, captured)
    _assert_unauthenticated_delivery_is_rejected(stack, uid, job_id, captured)
    return job_id, captured


def _assert_task_contract(stack: Stack, job_id: str, uid: str, conversation_id: str, captured: dict[str, Any]) -> None:
    body = captured.get('body')
    if not isinstance(body, dict):
        raise StackFailure('captured task body is missing')
    raw_paths = body.get('raw_blob_paths')
    if (
        body.get('job_id') != job_id
        or body.get('uid') != uid
        or body.get('conversation_id') != conversation_id
        or body.get('client_device_id') != DEVICE_ID
        or body.get('client_platform') != 'ios'
        or body.get('lane') != 'fresh'
        or body.get('capture_time_trust') != 'device_bound'
        or body.get('ledger_fence_mode') != 'active'
        or body.get('should_lock') is not False
        or not isinstance(raw_paths, list)
        or len(raw_paths) != 1
        or not isinstance(raw_paths[0], str)
        or not stack.staged_blob_path(raw_paths[0]).is_file()
    ):
        raise StackFailure('captured task did not preserve the fresh durable Sync worker contract')
    recording_age_seconds = body.get('recording_age_seconds')
    if (
        not isinstance(recording_age_seconds, int)
        or isinstance(recording_age_seconds, bool)
        or not 0 <= recording_age_seconds <= 300
    ):
        raise StackFailure('fresh task did not preserve a recent device-bound recording age')
    events = [
        event
        for event in stack.evidence_events('tasks')
        if event.get('event') == 'task_captured' and event.get('task_id') == job_id
    ]
    if len(events) != 1:
        raise StackFailure(f'expected one captured task event for {job_id}, saw {len(events)}')


def _post_task(task: dict[str, Any], *, retry_count: int, include_auth: bool = True) -> httpx.Response:
    body = task.get('body')
    url = task.get('url')
    if not isinstance(body, dict) or not isinstance(url, str):
        raise StackFailure('task control response is malformed')
    headers = {'X-CloudTasks-TaskRetryCount': str(retry_count)}
    if include_auth:
        headers['Authorization'] = f'Bearer {LOCAL_OIDC_TOKEN}'
    with httpx.Client(timeout=35.0, trust_env=False) as client:
        return client.post(url, json=body, headers=headers)


def _deliver_task(task: dict[str, Any], *, retry_count: int) -> httpx.Response:
    response = _post_task(task, retry_count=retry_count)
    _record_job_event(
        {
            'event': 'worker_delivery',
            'task_id': task.get('task_id'),
            'retry_count': retry_count,
            'http_status': response.status_code,
        }
    )
    return response


def _job_status(stack: Stack, uid: str, job_id: str) -> dict[str, Any]:
    response = stack.http.get(
        stack.admission_url + f'/v2/sync-local-files/{job_id}', headers=_auth_headers(uid), timeout=5.0
    )
    if response.status_code != 200:
        raise StackFailure(f'Sync status poll returned HTTP {response.status_code}')
    body = response.json()
    if not isinstance(body, dict):
        raise StackFailure('Sync status poll returned a non-object')
    return body


def _assert_unauthenticated_delivery_is_rejected(stack: Stack, uid: str, job_id: str, task: dict[str, Any]) -> None:
    denied = _post_task(task, retry_count=0, include_auth=False)
    if denied.status_code != 403:
        raise StackFailure(f'unauthenticated worker delivery returned HTTP {denied.status_code}, expected 403')
    if _job_status(stack, uid, job_id).get('status') != 'queued':
        raise StackFailure('rejected worker delivery changed the queued Sync job state')


def _poll_terminal_job(stack: Stack, uid: str, job_id: str, *, timeout: float = 20.0) -> dict[str, Any]:
    result: dict[str, Any] = {}

    def terminal() -> bool:
        nonlocal result
        result = _job_status(stack, uid, job_id)
        return result.get('status') in {'completed', 'partial_failure', 'failed'}

    _wait_until(terminal, label=f'terminal Sync job {job_id}', timeout=timeout)
    return result


def _assert_durable_success(stack: Stack, uid: str, job_id: str) -> str:
    status = _poll_terminal_job(stack, uid, job_id)
    result = status.get('result')
    if status.get('status') != 'completed' or not isinstance(result, dict):
        raise StackFailure(f'Sync worker did not publish a durable completed result for {job_id}')
    conversations = [*(result.get('new_memories') or []), *(result.get('updated_memories') or [])]
    if len(conversations) != 1 or not isinstance(conversations[0], str):
        raise StackFailure('deterministic worker did not produce exactly one durable conversation id')
    conversation_id = conversations[0]
    response = stack.http.get(
        stack.admission_url + f'/v1/conversations/{conversation_id}', headers=_auth_headers(uid), timeout=10.0
    )
    if response.status_code != 200:
        raise StackFailure(f'durable conversation read returned HTTP {response.status_code}')
    conversation = response.json()
    segments = conversation.get('transcript_segments') if isinstance(conversation, dict) else None
    if (
        not isinstance(conversation, dict)
        or conversation.get('status') != 'completed'
        or not isinstance(segments, list)
        or len(segments) != 1
        or segments[0].get('text') != TRANSCRIPT_TOKEN
    ):
        raise StackFailure('durable conversation did not contain the deterministic worker result')
    task = stack.task_control(job_id)
    body = task.get('body')
    if not isinstance(body, dict) or body.get('conversation_id') != conversation_id:
        raise StackFailure('worker did not merge/reprocess the conversation selected during fresh admission')
    content_id = body.get('content_id')
    if not isinstance(content_id, str):
        raise StackFailure('task content id is missing')
    ledger = (
        stack.firestore.collection('users').document(uid).collection('sync_content_ledger').document(content_id).get()
    )
    ledger_data = ledger.to_dict() if ledger.exists else None
    if not isinstance(ledger_data, dict) or ledger_data.get('status') != 'completed':
        raise StackFailure('Firestore Sync content ledger was not durably completed')
    _record_job_event(
        {
            'event': 'durable_job_verified',
            'job_id': job_id,
            'status': 'completed',
            'conversation_id': conversation_id,
            'ledger_status': 'completed',
        }
    )
    return conversation_id


def _stt_invocation_count(stack: Stack, job_id: str) -> int:
    return sum(
        1
        for event in stack.evidence_events('providers')
        if event.get('event') == 'stt_completed' and event.get('job_id') == job_id
    )


def _assert_metered_once(stack: Stack, uid: str) -> None:
    if stack.fair_use_meter_ms(uid) != 1000:
        raise StackFailure('fresh Sync task did not meter exactly one second once')


def _assert_not_metered(stack: Stack, uid: str) -> None:
    if stack.fair_use_meter_ms(uid) != 0:
        raise StackFailure('worker failure before pipeline execution unexpectedly recorded speech usage')


def _happy_path_and_terminal_duplicate(stack: Stack) -> None:
    uid = stack.scenario_uid('duplicate')
    job_id, task = _submit_and_capture_task(stack, uid)
    first = _deliver_task(task, retry_count=0)
    if first.status_code != 200 or first.json().get('status') != 'done':
        raise StackFailure('first worker delivery did not complete through the separate worker route')
    _assert_durable_success(stack, uid, job_id)
    _assert_metered_once(stack, uid)
    if _stt_invocation_count(stack, job_id) != 1:
        raise StackFailure('first completed worker delivery did not invoke STT exactly once')
    duplicate = _deliver_task(task, retry_count=1)
    if duplicate.status_code != 200 or duplicate.json().get('status') != 'acked':
        raise StackFailure('terminal duplicate was not ACKed by the separate worker route')
    _assert_metered_once(stack, uid)
    if _stt_invocation_count(stack, job_id) != 1:
        raise StackFailure('terminal duplicate re-ran the provider pipeline')


def _cleanup_retry_preserves_terminal_work(stack: Stack) -> None:
    uid = stack.scenario_uid('cleanup-retry')
    job_id, task = _submit_and_capture_task(stack, uid)
    raw_path = task['body']['raw_blob_paths'][0]
    staged_path = stack.staged_blob_path(raw_path)
    first = _deliver_task(task, retry_count=0)
    if first.status_code != 500:
        raise StackFailure('controlled terminal cleanup failure did not request Cloud Tasks retry')
    _assert_durable_success(stack, uid, job_id)
    _assert_metered_once(stack, uid)
    if not staged_path.is_file() or _stt_invocation_count(stack, job_id) != 1:
        raise StackFailure('terminal cleanup retry did not preserve staged material and one STT invocation')
    retry = _deliver_task(task, retry_count=1)
    if retry.status_code != 200 or retry.json().get('status') != 'acked':
        raise StackFailure('terminal cleanup retry was not ACKed')
    if staged_path.exists() or _stt_invocation_count(stack, job_id) != 1:
        raise StackFailure('terminal cleanup retry did not clean exact material without reprocessing')
    _assert_metered_once(stack, uid)


def _content_ledger_data(stack: Stack, uid: str, task: dict[str, Any]) -> dict[str, Any]:
    body = task.get('body')
    content_id = body.get('content_id') if isinstance(body, dict) else None
    if not isinstance(content_id, str):
        raise StackFailure('Sync task omitted durable content identity')
    ledger = (
        stack.firestore.collection('users').document(uid).collection('sync_content_ledger').document(content_id).get()
    )
    ledger_data = ledger.to_dict() if ledger.exists else None
    if not isinstance(ledger_data, dict):
        raise StackFailure('Sync content ledger was not durably readable')
    return ledger_data


def _pre_ledger_failure_retries_once(stack: Stack) -> None:
    uid = stack.scenario_uid('transient-retry')
    job_id, task = _submit_and_capture_task(stack, uid)
    first = _deliver_task(task, retry_count=0)
    if first.status_code != 500 or first.json().get('status') != 'retry':
        raise StackFailure('controlled pre-ledger failure did not request a durable retry')
    if _job_status(stack, uid, job_id).get('status') != 'queued':
        raise StackFailure('pre-ledger worker failure did not return the job to queued')
    if not stack.staged_blob_path(task['body']['raw_blob_paths'][0]).is_file():
        raise StackFailure('pre-ledger worker failure deleted staged input')
    ledger_data = _content_ledger_data(stack, uid, task)
    if ledger_data.get('status') != 'processing' or len(ledger_data.get('processed_segment_ids') or []) != 1:
        raise StackFailure('pre-ledger retry did not preserve the durable processed-segment checkpoint')
    _assert_metered_once(stack, uid)
    if _stt_invocation_count(stack, job_id) != 1:
        raise StackFailure('pre-ledger failure did not execute the initial provider pipeline exactly once')
    retry = _deliver_task(task, retry_count=1)
    if retry.status_code != 200 or retry.json().get('status') != 'done':
        raise StackFailure('pre-ledger retry did not complete the durable job')
    _assert_durable_success(stack, uid, job_id)
    _assert_metered_once(stack, uid)
    if _stt_invocation_count(stack, job_id) != 1:
        raise StackFailure('pre-ledger retry re-ran a completed Sync segment')


def _post_ledger_failure_converges_once(stack: Stack) -> None:
    uid = stack.scenario_uid('post-ledger-retry')
    job_id, task = _submit_and_capture_task(stack, uid)
    first = _deliver_task(task, retry_count=0)
    if first.status_code != 500 or first.json().get('status') != 'retry':
        raise StackFailure('controlled post-ledger failure did not request a durable retry')
    if _job_status(stack, uid, job_id).get('status') != 'queued':
        raise StackFailure('post-ledger worker failure did not return the job to queued')
    if not stack.staged_blob_path(task['body']['raw_blob_paths'][0]).is_file():
        raise StackFailure('post-ledger worker failure deleted staged input')
    if _content_ledger_data(stack, uid, task).get('status') != 'completed':
        raise StackFailure('controlled retry did not fail after durable content-ledger completion')
    _assert_metered_once(stack, uid)
    if _stt_invocation_count(stack, job_id) != 1:
        raise StackFailure('post-ledger failure did not execute the initial provider pipeline exactly once')
    retry = _deliver_task(task, retry_count=1)
    if retry.status_code != 200 or retry.json().get('status') != 'done' or retry.json().get('reconciled') is not True:
        raise StackFailure('post-ledger retry did not converge through the durable content ledger')
    _assert_durable_success(stack, uid, job_id)
    _assert_metered_once(stack, uid)
    if _stt_invocation_count(stack, job_id) != 1:
        raise StackFailure('post-ledger retry re-ran a completed Sync segment')


def _final_attempt_post_ledger_failure_converges(stack: Stack) -> None:
    """A final task delivery must not overwrite its own completed ledger."""
    uid = stack.scenario_uid('final-attempt-ledger')
    job_id, task = _submit_and_capture_task(stack, uid)
    first = _deliver_task(task, retry_count=0)
    if first.status_code != 500 or first.json().get('status') != 'retry':
        raise StackFailure('pre-pipeline first delivery did not request a durable retry')
    if _job_status(stack, uid, job_id).get('status') != 'queued':
        raise StackFailure('pre-pipeline first delivery did not return the job to queued')
    _assert_not_metered(stack, uid)
    if _stt_invocation_count(stack, job_id) != 0:
        raise StackFailure('pre-pipeline first delivery unexpectedly invoked STT')

    final = _deliver_task(task, retry_count=1)
    if final.status_code != 200 or final.json().get('status') != 'done' or final.json().get('reconciled') is not True:
        raise StackFailure('final delivery did not converge its completed durable content ledger')
    _assert_durable_success(stack, uid, job_id)
    _assert_metered_once(stack, uid)
    if _stt_invocation_count(stack, job_id) != 1:
        raise StackFailure('final durable-ledger convergence re-ran the provider pipeline')
    if stack.staged_blob_path(task['body']['raw_blob_paths'][0]).exists():
        raise StackFailure('final durable-ledger convergence did not clean staged input')


def _retry_budget_terminalizes_truthfully(stack: Stack) -> None:
    uid = stack.scenario_uid('terminal-failure')
    job_id, task = _submit_and_capture_task(stack, uid)
    first = _deliver_task(task, retry_count=0)
    if first.status_code != 500 or first.json().get('status') != 'retry':
        raise StackFailure('first controlled worker failure did not request retry')
    final = _deliver_task(task, retry_count=1)
    if final.status_code != 200 or final.json().get('status') != 'failed_final':
        raise StackFailure('retry-budget exhaustion did not terminalize through the worker route')
    status = _poll_terminal_job(stack, uid, job_id)
    if status.get('status') != 'failed':
        raise StackFailure('retry-budget exhaustion did not publish truthful failed job state')
    if stack.staged_blob_path(task['body']['raw_blob_paths'][0]).exists():
        raise StackFailure('terminal failure did not release staged material')
    _assert_not_metered(stack, uid)
    duplicate = _deliver_task(task, retry_count=2)
    if duplicate.status_code != 200 or duplicate.json().get('status') != 'acked':
        raise StackFailure('terminal failed job was not safely ACKed on duplicate delivery')
    _assert_not_metered(stack, uid)


def _concurrent_delivery_is_lease_fenced(stack: Stack) -> None:
    if stack.gate_dir is None:
        raise StackFailure('concurrent scenario requires a processor gate')
    uid = stack.scenario_uid('concurrent')
    job_id, task = _submit_and_capture_task(stack, uid)
    first_result: list[httpx.Response] = []

    def first_delivery() -> None:
        first_result.append(_deliver_task(task, retry_count=0))

    thread = threading.Thread(target=first_delivery, daemon=True)
    thread.start()
    _wait_until(lambda: (stack.gate_dir / 'entered').exists(), label='first worker processor gate')
    second = _deliver_task(task, retry_count=1)
    if second.status_code != 409 or second.json().get('status') != 'locked':
        raise StackFailure('concurrent worker delivery did not observe the real run lock')
    (stack.gate_dir / 'release').write_text('release', encoding='utf-8')
    thread.join(timeout=35.0)
    if thread.is_alive() or len(first_result) != 1:
        raise StackFailure('first gated worker delivery did not finish')
    first = first_result[0]
    if first.status_code != 200 or first.json().get('status') != 'done':
        raise StackFailure('lease-owning worker delivery did not finish successfully')
    _assert_durable_success(stack, uid, job_id)
    _assert_metered_once(stack, uid)
    if _stt_invocation_count(stack, job_id) != 1:
        raise StackFailure('concurrent delivery ran the provider pipeline more than once')


def _ambiguous_enqueue_and_expired_blob(stack: Stack) -> None:
    uid = stack.scenario_uid('lost-ack')
    job_id, task = _submit_and_capture_task(stack, uid)
    task_events = stack.evidence_events('tasks')
    if sum(event.get('event') == 'task_captured' and event.get('task_id') == job_id for event in task_events) != 1:
        raise StackFailure('lost create acknowledgement created more than one named task')
    if not any(event.get('event') == 'task_ack_lost' and event.get('task_id') == job_id for event in task_events):
        raise StackFailure('ambiguous enqueue scenario did not exercise the lost acknowledgement')
    if not any(
        event.get('event') == 'named_task_deduplicated' and event.get('task_id') == job_id for event in task_events
    ):
        raise StackFailure('ambiguous enqueue did not converge through named-task AlreadyExists')
    if _job_status(stack, uid, job_id).get('status') != 'queued':
        raise StackFailure('ambiguous named enqueue fell back or terminalized before delivery')
    delivered = _deliver_task(task, retry_count=0)
    if delivered.status_code != 200 or delivered.json().get('status') != 'done':
        raise StackFailure('ambiguous named enqueue task did not later complete normally')
    _assert_durable_success(stack, uid, job_id)

    expired_uid = stack.scenario_uid('expired-blob')
    expired_job, expired_task = _submit_and_capture_task(stack, expired_uid)
    staged = stack.staged_blob_path(expired_task['body']['raw_blob_paths'][0])
    staged.unlink()
    expired = _deliver_task(expired_task, retry_count=0)
    if expired.status_code != 200 or expired.json() != {'status': 'dropped', 'reason': 'staged_audio_expired'}:
        raise StackFailure('missing staged blob did not take the durable expired-input path')
    if _poll_terminal_job(stack, expired_uid, expired_job).get('status') != 'failed':
        raise StackFailure('expired staged blob did not publish a failed Sync job')
    if _stt_invocation_count(stack, expired_job) != 0:
        raise StackFailure('expired staged blob unexpectedly invoked STT')


def _assert_evidence_is_sanitized(stack: Stack) -> None:
    # A deliberate pre-pipeline failure has no provider event; all scenarios
    # must still produce task, worker, durable-job, and storage evidence.
    expected_streams = {'tasks', 'jobs', 'worker', 'storage'}
    present = {path.stem for path in stack.evidence_dir.glob('*.jsonl')}
    if not expected_streams.issubset(present):
        raise StackFailure(f'missing sanitized evidence streams: {sorted(expected_streams - present)}')
    for path in stack.evidence_dir.glob('*.jsonl'):
        content = path.read_text(encoding='utf-8')
        if SENSITIVE_UID in content or TRANSCRIPT_TOKEN in content:
            raise StackFailure(f'sensitive uid or transcript leaked into evidence: {path.name}')
        for line in content.splitlines():
            try:
                value = json.loads(line)
            except json.JSONDecodeError as error:
                raise StackFailure(f'non-JSON evidence line in {path.name}') from error
            if not isinstance(value, dict):
                raise StackFailure(f'non-object evidence event in {path.name}')


def _run_scenario(
    state_dir: Path,
    *,
    task_ack_failures: int = 0,
    worker_failures: int = 0,
    pre_ledger_failures: int = 0,
    post_ledger_failures: int = 0,
    cleanup_failures: int = 0,
    hold_processor: bool = False,
    scenario: Callable[[Stack], None],
) -> None:
    stack = Stack(
        state_dir,
        task_ack_failures=task_ack_failures,
        worker_failures=worker_failures,
        pre_ledger_failures=pre_ledger_failures,
        post_ledger_failures=post_ledger_failures,
        cleanup_failures=cleanup_failures,
        hold_processor=hold_processor,
    )
    try:
        stack.start()
        scenario(stack)
        _assert_evidence_is_sanitized(stack)
    finally:
        stack.close()
        stack.cleanup_workspace_files()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-dir', type=Path, help='directory for sanitized evidence and private process logs')
    parser.add_argument('--keep', action='store_true', help='preserve state after a successful run')
    args = parser.parse_args()
    if not PYTHON.exists():
        raise SystemExit(f'missing backend virtual environment: {PYTHON}; run backend/scripts/sync-python-deps.sh')
    created_state_dir = args.state_dir is None
    state_dir = (args.state_dir or Path(tempfile.mkdtemp(prefix='omi-sync-cloud-tasks-stack-'))).resolve()
    state_dir.mkdir(parents=True, exist_ok=True)
    succeeded = False
    try:
        _run_scenario(state_dir / 'happy-duplicate', scenario=_happy_path_and_terminal_duplicate)
        _run_scenario(state_dir / 'cleanup-retry', cleanup_failures=1, scenario=_cleanup_retry_preserves_terminal_work)
        _run_scenario(state_dir / 'pre-ledger-retry', pre_ledger_failures=1, scenario=_pre_ledger_failure_retries_once)
        _run_scenario(
            state_dir / 'post-ledger-retry', post_ledger_failures=1, scenario=_post_ledger_failure_converges_once
        )
        _run_scenario(
            state_dir / 'final-attempt-ledger',
            worker_failures=1,
            post_ledger_failures=1,
            scenario=_final_attempt_post_ledger_failure_converges,
        )
        _run_scenario(state_dir / 'terminal-failure', worker_failures=2, scenario=_retry_budget_terminalizes_truthfully)
        _run_scenario(state_dir / 'concurrent', hold_processor=True, scenario=_concurrent_delivery_is_lease_fenced)
        _run_scenario(state_dir / 'lost-ack-expired', task_ack_failures=1, scenario=_ambiguous_enqueue_and_expired_blob)
        succeeded = True
        print(f'Sync Cloud Tasks stack gauntlet passed; sanitized evidence: {state_dir}')
        return 0
    except Exception:
        print(f'Sync Cloud Tasks stack gauntlet failed; state retained: {state_dir}', file=sys.stderr)
        raise
    finally:
        if succeeded and created_state_dir and not args.keep:
            shutil.rmtree(state_dir)


if __name__ == '__main__':
    raise SystemExit(main())
