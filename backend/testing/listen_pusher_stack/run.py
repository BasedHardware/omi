"""Run isolated high-fidelity tests for the listen -> pusher chain.

Run through ``run.sh`` so Firebase supplies a fresh Firestore emulator.  This
supervisor owns only the Redis, backend, pusher, and Parakeet child processes
that it starts; it never probes or stops user services.
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
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlencode

import redis
import websockets
from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / 'backend'
PYTHON = BACKEND / '.venv' / 'bin' / 'python'
ADMIN_KEY = 'omi-listen-pusher-stack-admin-'
PROJECT = 'demo-omi-listen-stack'


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


def _wait_for_port(port: int, *, label: str, timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
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


class Stack:
    def __init__(self, state_dir: Path):
        self.state_dir = state_dir
        self.redis_port = _free_port()
        self.backend_port = _free_port()
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
                'LISTEN_FINALIZATION_DISPATCH_MODE': 'inline',
                'OMI_STACK_STATE_DIR': str(self.state_dir),
                'PYTHONPATH': str(BACKEND),
            }
        )
        return env

    def _start(self, name: str, command: list[str], *, extra_env: dict[str, str] | None = None) -> Child:
        if name in self.children:
            raise StackFailure(f'{name} is already running')
        log_path = self.state_dir / f'{name}.log'
        process_env = self.env.copy()
        if extra_env:
            process_env.update(extra_env)
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
        child = Child(name, process, log_path)
        self.children[name] = child
        return child

    def start(self, *, pusher_drop_opcode: int | None = None) -> None:
        redis_binary = shutil.which('redis-server')
        if not redis_binary:
            raise StackFailure('redis-server is required; install Redis and retry')
        self._start(
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
        _wait_for_port(self.redis_port, label='isolated Redis')
        redis.Redis(host='127.0.0.1', port=self.redis_port).ping()
        self._start(
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
        _wait_for_port(self.parakeet_port, label='Parakeet stub')
        pusher_env = (
            {'OMI_STACK_DROP_PUBLISHING_ON_OPCODE': str(pusher_drop_opcode)} if pusher_drop_opcode is not None else None
        )
        self._start(
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
        _wait_for_port(self.pusher_port, label='pusher')
        self._start(
            'backend',
            [str(PYTHON), '-m', 'uvicorn', 'main:app', '--host', '127.0.0.1', '--port', str(self.backend_port)],
        )
        _wait_for_port(self.backend_port, label='listen backend', timeout=45.0)

    def restart_pusher(self, *, drop_opcode: int | None = None) -> None:
        self.stop('pusher')
        pusher_env = {'OMI_STACK_DROP_PUBLISHING_ON_OPCODE': str(drop_opcode)} if drop_opcode is not None else None
        self._start(
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
        _wait_for_port(self.pusher_port, label='restarted pusher')

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
        for name in list(self.children):
            self.stop(name)

    @property
    def pusher_events(self) -> list[dict[str, Any]]:
        return _read_events(self.state_dir / 'pusher.jsonl')

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
                'transcription_preferences': {'uses_custom_stt': False},
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


async def run_scenarios(stack: Stack) -> None:
    await _normal_and_terminal_reconnect(stack)
    await _empty_recording(stack)
    await _pusher_restart_replay(stack)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-dir', type=Path, help='directory for sanitized process logs and JSONL evidence')
    parser.add_argument('--keep', action='store_true', help='preserve generated evidence after a successful run')
    args = parser.parse_args()
    if not PYTHON.exists():
        raise SystemExit(f'missing backend virtual environment: {PYTHON}; run backend/scripts/sync-python-deps.sh')
    state_dir = args.state_dir or Path(tempfile.mkdtemp(prefix='omi-listen-pusher-stack-'))
    state_dir.mkdir(parents=True, exist_ok=True)
    stack = Stack(state_dir)
    try:
        stack.start()
        asyncio.run(run_scenarios(stack))
        print(f'listen-pusher stack gauntlet passed; evidence: {state_dir}')
        return 0
    except Exception as error:
        print(f'listen-pusher stack gauntlet failed; evidence retained: {state_dir}', file=sys.stderr)
        raise
    finally:
        stack.close()
        if not args.keep and not sys.exc_info()[0]:
            shutil.rmtree(state_dir)


if __name__ == '__main__':
    raise SystemExit(main())
