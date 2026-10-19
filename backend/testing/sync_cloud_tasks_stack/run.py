"""Run the process-isolated Sync Cloud Tasks stack gauntlet.

Invoke through ``run.sh`` so Firebase owns a fresh Firestore emulator.  The
supervisor starts private Redis plus independent admission, serving and batch
worker processes (``batch.py``); it never probes, reuses, or stops developer
services.  The legacy Sync Cloud Tasks worker family was deleted with legacy
transcription (legacy-retire C11).
"""

from __future__ import annotations

import argparse
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
import time
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Callable

import google.auth
import httpx
import redis
from google.auth import credentials as google_auth_credentials
from google.cloud import firestore

from .local_oidc import local_oidc_token

ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / 'backend'
PYTHON = BACKEND / '.venv' / 'bin' / 'python'
PROJECT = 'demo-omi-sync-cloud-tasks-stack'
ADMIN_KEY = 'omi-sync-cloud-tasks-stack-admin-'
LOCAL_OIDC_AUDIENCE = 'https://sync-stack.local/v2/sync-jobs/run'
LOCAL_INVOKER_SA = 'sync-stack-invoker@demo-omi-sync-cloud-tasks-stack.iam.gserviceaccount.com'
LOCAL_OIDC_TOKEN = local_oidc_token(LOCAL_OIDC_AUDIENCE, LOCAL_INVOKER_SA)
SYNC_QUEUE = 'sync-jobs'
SENSITIVE_UID = 'sync-stack-sensitive-uid'
TRANSCRIPT_TOKEN = 'Sync stack transcript verified.'
DEVICE_HASH = '01234567'
DEVICE_ID = f'ios_{DEVICE_HASH}'
ENCRYPTION_SECRET = 'omi_sync_cloud_tasks_stack_test_secret_32_bytes'  # pragma: allowlist secret


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


def _wait_for_port_free(port: int, *, label: str, timeout: float = 10.0) -> None:
    # Scenarios run back-to-back and each allocates fresh ports, but a child of
    # the previous stack that is still tearing down can keep its listener alive
    # past close(). A later stack's TCP probe then connects to that corpse and
    # reports readiness for a service that never came up (observed in CI as
    # "timed out waiting for Sync admission health endpoint" after the port
    # wait had already succeeded). Failing to free a port here is a warning,
    # not a failure: the next stack binds different ports, this only shrinks
    # the cross-scenario collision window.
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(('127.0.0.1', port), timeout=0.25):
                time.sleep(0.1)
        except OSError:
            return
    print(f'WARNING: {label} still accepting connections on 127.0.0.1:{port} after {timeout:.0f}s', flush=True)


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


def postgres_requested() -> bool:
    return os.getenv('OMI_STACK_POSTGRES', '').strip().lower() in {'1', 'true', 'yes', 'on'}


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
        process_persistence_fenced: bool = False,
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
        self.process_persistence_fenced = process_persistence_fenced
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
                'SYNC_JOB_HANDLER_BUDGET_SECONDS': '20',
                'FAIR_USE_ENABLED': 'true',
                'MAX_DAILY_AUDIO_HOURS': '30',
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
                'OMI_SYNC_STACK_PROCESS_PERSISTENCE_FENCED': ('true' if self.process_persistence_fenced else 'false'),
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

        # Health is the authoritative readiness signal (a TCP accept only
        # proves *something* listens — uvicorn accepts before the app finishes
        # importing, and on a contended runner the backend import chain alone
        # can exceed 20s). Give the strong check the generous budget.
        _wait_until(healthy, label=f'Sync {role} health endpoint', timeout=60.0)

    def _start_postgres(self) -> None:
        """Opt-in (``OMI_STACK_POSTGRES=1``): a private-socket Postgres 16 with the job-store schema, for roles
        that select the Postgres job store. Its DSN reaches children as ``JOBSTORE_POSTGRES_DSN``. Nothing in
        the default stack reads it, so the stack is unchanged unless asked."""
        from testing.store_fixtures import BackendUnavailable, postgres_dsn

        try:
            self.env['JOBSTORE_POSTGRES_DSN'] = postgres_dsn()
        except BackendUnavailable as exc:
            raise StackFailure(f'OMI_STACK_POSTGRES=1 but Postgres is unavailable: {exc}') from exc

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
        if postgres_requested():
            self._start_postgres()
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
        if postgres_requested():
            from testing.store_fixtures import stop_local_postgres

            stop_local_postgres()
        for port, label in (
            (self.redis_port, 'isolated Redis'),
            (self.worker_port, 'Sync worker'),
            (self.admission_port, 'Sync admission'),
        ):
            _wait_for_port_free(port, label=label)
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-dir', type=Path, help='directory for sanitized evidence and private process logs')
    parser.add_argument('--keep', action='store_true', help='preserve state after a successful run')
    parser.add_argument(
        '--only',
        choices=('all', 'batch'),
        default='all',
        help='the legacy Sync Cloud Tasks scenarios were deleted with legacy transcription (legacy-retire C11); both values run the batch-lane scenarios',
    )
    args = parser.parse_args()
    if not PYTHON.exists():
        raise SystemExit(f'missing backend virtual environment: {PYTHON}; run backend/scripts/sync-python-deps.sh')
    created_state_dir = args.state_dir is None
    state_dir = (args.state_dir or Path(tempfile.mkdtemp(prefix='omi-sync-cloud-tasks-stack-'))).resolve()
    state_dir.mkdir(parents=True, exist_ok=True)
    succeeded = False
    try:
        if args.only in {'all', 'batch'}:
            from .batch import run_batch_scenarios

            run_batch_scenarios(state_dir / 'batch')
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
