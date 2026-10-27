"""Batch-lane scenarios for the process-isolated Sync stack gauntlet.

One stack runs four separate processes against the loopback Firestore emulator
and a private Redis: the admission ASGI process (real ``/v2/sync-local-files``
→ ``accept_upload``), the serving ASGI process (real ``main`` lifespan with
``BATCH_PIPELINE_SERVING_ENABLED`` so ``Serving`` projects, sweeps quarantine
recovery, and recovers leases), and the batch worker process (real
``batch_pipeline_runtime.run_process`` → ``Pump(Scheduler(FirestoreStore))``
over ``PipelineWorker`` with fake model leaves).  Every assertion reads back
durable emulator/Redis state or real HTTP status codes; evidence stays
metadata-only.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import signal
import struct
import subprocess
import threading
import time
import uuid
import wave
from contextlib import suppress
from pathlib import Path
from typing import Any, Callable

import httpx
import redis

from .local_oidc import local_oidc_token
from .run import (
    BACKEND,
    DEVICE_HASH,
    PYTHON,
    SENSITIVE_UID,
    Stack,
    StackFailure,
    _assert_evidence_is_sanitized,
    _auth_headers,
    _fresh_pcm_filename,
    _free_port,
    _record_job_event,
    _seed_capture_conversation,
    _wait_for_port,
    _wait_for_port_free,
    _wait_until,
)

NAMESPACE = 'batch_pipeline_dev'
SERVING_ORIGIN = 'https://batch-serving.local'
WORKER_AUDIENCE = 'https://batch-serving.local/batch-worker'
WORKER_SA = 'batch-worker@demo-omi-sync-cloud-tasks-stack.iam.gserviceaccount.com'
LOCAL_INVOKER_SA = 'sync-stack-invoker@demo-omi-sync-cloud-tasks-stack.iam.gserviceaccount.com'
BATCH_BUCKET = 'batch-pipeline-local'
FIXTURE = BACKEND / 'scripts' / 'fixtures' / 'parakeet_route_synthetic.wav'
LEASE_SECONDS = 8
HEARTBEAT_SECONDS = 2
SIGTERM_GRACE_SECONDS = 3.0
FRAME_SAMPLES = 1600
STATUS_POLL_SECONDS = 1.0


def _owner_hash(uid: str) -> str:
    return hashlib.sha256(uid.encode()).hexdigest()[:16]


def _speech_pcm(variant: int, seconds: float = 4.0) -> bytes:
    """Synthetic speech fixture, trimmed to whole frames; one LSB marks the owner."""
    with wave.open(str(FIXTURE), 'rb') as handle:
        if (handle.getnchannels(), handle.getsampwidth(), handle.getframerate()) != (1, 2, 16000):
            raise StackFailure('synthetic speech fixture must be 16 kHz mono PCM16')
        pcm = bytearray(handle.readframes(handle.getnframes()))
    samples = int(seconds * 16000) // FRAME_SAMPLES * FRAME_SAMPLES
    pcm = pcm[: samples * 2]
    if len(pcm) != samples * 2:
        raise StackFailure('synthetic speech fixture is shorter than requested')
    first = struct.unpack_from('<h', pcm, 0)[0]
    struct.pack_into('<h', pcm, 0, (first & ~0xFF) | (variant & 0xFF))
    return bytes(pcm)


def _framed(pcm: bytes) -> bytes:
    frame_bytes = FRAME_SAMPLES * 2
    return b''.join(
        struct.pack('<I', frame_bytes) + pcm[offset : offset + frame_bytes]
        for offset in range(0, len(pcm), frame_bytes)
    )


class BatchStack(Stack):
    """Admission + serving + batch worker processes over one emulator and Redis."""

    def __init__(self, state_dir: Path):
        self.serving_port = _free_port()
        self.control_dir = state_dir / 'batch-control'
        super().__init__(state_dir)
        self.control_dir.mkdir(parents=True, exist_ok=True)
        from config.policy import resolve_batch_policy

        policy = resolve_batch_policy(
            'synthetic-stack-owner',
            flags={
                'BATCH_PIPELINE_ENABLED': 'true',
                'BATCH_PIPELINE_PERCENT': '100',
            },
        )
        # No owner identity is serialized; this 100% policy covers every
        # synthetic owner through the admission seam.
        (self.control_dir / 'policy.json').write_text(json.dumps(policy.to_dict()))
        self.owner_variants = 0
        self.worker_generation = 0
        self.serving_generation = 0
        self.worker_name = ''
        self.serving_name = ''

    def _environment(self) -> dict[str, str]:
        env = super()._environment()
        env.update(
            {
                # Batch namespaces are stage-qualified (prod|dev); this
                # emulator project is private to one gauntlet invocation.
                'OMI_ENV_STAGE': 'dev',
                'BATCH_PIPELINE_NAMESPACE': NAMESPACE,
                'BUCKET_BATCH_PIPELINE': BATCH_BUCKET,
                'BATCH_PIPELINE_RECOVERY_TASK_AUDIENCE': SERVING_ORIGIN,
                'BATCH_PIPELINE_WORKER_AUDIENCE': WORKER_AUDIENCE,
                'BATCH_PIPELINE_WORKER_SERVICE_ACCOUNT': WORKER_SA,
                'BATCH_PIPELINE_API_URL': SERVING_ORIGIN,
            }
        )
        return env

    def _role_env(self, role: str) -> dict[str, str]:
        if role == 'admission':
            return {'OMI_BATCH_STACK_POLICY_FILE': str(self.control_dir / 'policy.json')}
        if role == 'batch-serving':
            return {
                'BATCH_PIPELINE_SERVING_ENABLED': 'true',
                # Only the owning serving role stamps these onto each job.
                'BATCH_PIPELINE_RECOVERY_MODE': 'on',
                'BATCH_PIPELINE_RECOVERY_ALL_ADMITTED': 'true',
                # Projection enrichment obligations bind to an HTTPS sync
                # handler; the strict recorder captures, never delivers, them.
                'SYNC_TASKS_HANDLER_URL': SERVING_ORIGIN + '/v2/sync-jobs/run',
                'SYNC_TASKS_OIDC_AUDIENCE': SERVING_ORIGIN + '/v2/sync-jobs/run',
            }
        return {
            'BATCH_PIPELINE_WORKER_ENABLED': 'true',
            'BATCH_PIPELINE_EMPTY_ASR_RECOVERY_ENABLED': 'true',
            'BATCH_PIPELINE_MODEL_BATCH_SIZE': os.getenv('OMI_BATCH_STACK_CAPACITY', '4'),
            'OMI_BATCH_STACK_SERVING_ORIGIN': self.serving_url,
            'OMI_BATCH_STACK_LEASE_SECONDS': str(LEASE_SECONDS),
            'OMI_BATCH_STACK_HEARTBEAT_SECONDS': str(HEARTBEAT_SECONDS),
        }

    @property
    def serving_url(self) -> str:
        return f'http://127.0.0.1:{self.serving_port}'

    def _start_with(self, name: str, command: list[str], role: str, extra: dict[str, str]) -> None:
        saved = self.env
        self.env = {**saved, **self._role_env(role), **extra}
        try:
            self._start(name, command, role=role if role != 'batch-worker' else None)
        finally:
            self.env = saved

    def start_serving(self) -> None:
        self.serving_generation += 1
        self.serving_name = f'batch-serving-{self.serving_generation}'
        command = [
            str(PYTHON),
            '-m',
            'uvicorn',
            'testing.sync_cloud_tasks_stack.admission_app:app',
            '--host',
            '127.0.0.1',
            '--port',
            str(self.serving_port),
        ]
        self._start_with(self.serving_name, command, 'batch-serving', {})

    def start_worker(self, extra: dict[str, str] | None = None) -> None:
        self.worker_name = self._spawn_worker(extra)

    def start_peer_worker(self, extra: dict[str, str] | None = None) -> str:
        """A second concurrent replica; ``worker_name`` keeps naming the primary."""
        return self._spawn_worker(extra)

    def _spawn_worker(self, extra: dict[str, str] | None = None) -> str:
        self.worker_generation += 1
        name = f'batch-worker-{self.worker_generation}'
        command = [str(PYTHON), '-m', 'testing.sync_cloud_tasks_stack.batch_worker']
        self._start_with(name, command, 'batch-worker', {**(extra or {}), 'OMI_BATCH_STACK_WORKER_NAME': name})
        return name

    def stop_worker(self, name: str) -> None:
        self.signal(name, signal.SIGTERM)
        if self.wait_exit(name, timeout=30.0) is None:
            self.signal(name, signal.SIGKILL)
            self.wait_exit(name, timeout=10.0)
        self.forget(name)

    def wait_serving(self) -> None:
        _wait_for_port(self.serving_port, label='batch serving', timeout=120.0)
        self._assert_health(self.serving_url, role='batch-serving')

    def wait_worker(self, name: str | None = None) -> None:
        name = name or self.worker_name

        def ready() -> bool:
            child = self.children.get(name)
            if child is None or child.process.poll() is not None:
                raise StackFailure(f'{name} exited before readiness')
            return any(
                event.get('event') == 'batch_worker_ready' and event.get('worker_name') == name
                for event in self.evidence_events('worker')
            )

        _wait_until(ready, label=f'{name} readiness', timeout=120.0)

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
        # Independent imports start concurrently; readiness is checked per role.
        self.start_serving()
        self._start_with(
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
            'admission',
            {},
        )
        self.start_worker()
        self.wait_serving()
        _wait_for_port(self.admission_port, label='batch admission', timeout=120.0)
        self._assert_health(self.admission_url, role='admission')
        self.wait_worker()

    def signal(self, name: str, sig: signal.Signals) -> None:
        child = self.children.get(name)
        if child is None:
            raise StackFailure(f'{name} is not running')
        with suppress(ProcessLookupError):
            os.killpg(child.process.pid, sig)

    def wait_exit(self, name: str, timeout: float) -> int | None:
        child = self.children[name]
        try:
            return child.process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            return None

    def forget(self, name: str) -> None:
        self.children.pop(name, None)

    def close(self) -> None:
        # Stop application processes before their Redis so shutdown hooks
        # (pub/sub, executors) do not log spurious connection failures.
        for name in sorted(self.children, key=lambda child: child == 'redis'):
            self.stop(name)
        for port, label in (
            (self.redis_port, 'isolated Redis'),
            (self.serving_port, 'batch serving'),
            (self.admission_port, 'batch admission'),
        ):
            _wait_for_port_free(port, label=label)
        self.http.close()

    # ---- control files read by the provider leaves -------------------------
    def _write_control(self, name: str, update: dict[str, Any]) -> None:
        path = self.control_dir / name
        current = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
        current.update(update)
        staged = path.with_suffix('.tmp')
        staged.write_text(json.dumps(current), encoding='utf-8')
        staged.replace(path)

    def set_words(self, uid: str, mode: str, latency_ms: float = 0) -> None:
        self._write_control('words.json', {_owner_hash(uid): {'mode': mode, 'latency_ms': latency_ms}})

    def set_paid(self, pcm_digest: str, mode: str = 'words', latency_ms: float = 0) -> None:
        self._write_control('paid.json', {pcm_digest: {'mode': mode, 'latency_ms': latency_ms}})

    # ---- durable reads ------------------------------------------------------
    def doc(self, table: str, key: str) -> dict[str, Any]:
        snapshot = self.firestore.collection(f'{NAMESPACE}_{table}').document(key).get()
        return (snapshot.to_dict() or {}) if snapshot.exists else {}

    def ledger(self, uid: str, content_id: str) -> dict[str, Any]:
        snapshot = (
            self.firestore.collection('users')
            .document(uid)
            .collection('sync_content_ledger_dev')
            .document(content_id)
            .get()
        )
        return (snapshot.to_dict() or {}) if snapshot.exists else {}

    def words_calls(self, segment_id: str) -> int:
        return sum(
            1
            for event in self.evidence_events('providers')
            if event.get('event') == 'words_started' and segment_id in (event.get('segment_ids') or [])
        )

    def paid_calls(self, digest: str) -> int:
        return sum(
            1
            for event in self.evidence_events('providers')
            if event.get('event') == 'paid_stt_started' and event.get('pcm_hash') == digest
        )

    def fair_use_meter_ms(self, uid: str) -> int:
        client = redis.Redis(host='127.0.0.1', port=self.redis_port)
        return sum(
            int(value) for key in client.keys(f'fair_use:v2:bucket:*:{uid}') for value in client.hgetall(key).values()
        )

    # ---- serving RPCs (production routes, local OIDC) ------------------------
    def reconcile(self) -> int:
        try:
            response = self.http.post(
                self.serving_url + '/v2/batch-pipeline/reconcile',
                json={'stage': 'dev'},
                headers={'Authorization': f'Bearer {local_oidc_token(WORKER_AUDIENCE, WORKER_SA)}'},
                timeout=60.0,
            )
        except httpx.HTTPError:
            return 0
        return response.status_code

    def recovery_tasks(self) -> list[dict[str, Any]]:
        response = self.http.get(
            self.serving_url + '/__sync-stack/tasks',
            params={'kind': 'batch_recovery'},
            headers=self.control_headers,
            timeout=5.0,
        )
        if response.status_code != 200:
            raise StackFailure(f'serving task control returned HTTP {response.status_code}')
        return response.json()

    def deliver_recovery(self, task: dict[str, Any], *, retry_count: int, timeout: float = 60.0) -> httpx.Response:
        # Cloud Tasks routes the HTTPS serving-origin URL to this revision.
        path = '/v2/batch-pipeline/recover-quarantine'
        if task.get('url') != SERVING_ORIGIN + path:
            raise StackFailure('recovery task URL is not the serving-origin route')
        with httpx.Client(timeout=timeout, trust_env=False) as client:
            response = client.post(
                self.serving_url + path,
                json=task['body'],
                headers={
                    'Authorization': f'Bearer {local_oidc_token(SERVING_ORIGIN, LOCAL_INVOKER_SA)}',
                    'X-CloudTasks-TaskRetryCount': str(retry_count),
                    'X-CloudTasks-TaskName': str(task.get('task_id') or ''),
                },
            )
        _record_job_event(
            {
                'event': 'recovery_delivery',
                'task_id': task.get('task_id'),
                'retry_count': retry_count,
                'http_status': response.status_code,
                'outcome': (response.json() or {}).get('status') if response.status_code == 200 else None,
            }
        )
        return response


class Upload:
    def __init__(self, uid: str, job_id: str, conversation_id: str, pcm_digest: str, duration: float):
        self.uid, self.job_id, self.conversation_id = uid, job_id, conversation_id
        self.pcm_digest, self.duration = pcm_digest, duration
        self.segment_ids: list[str] = []
        self.content_id = ''


def _upload(
    stack: BatchStack, scenario: str, *, words: str = 'words', latency_ms: float = 0, uid: str | None = None
) -> Upload:
    uid = uid or stack.scenario_uid(scenario)
    stack.seed_user(uid)
    # The corpus is synthetic English. Qualify that declaration through the
    # real intake/worker metadata path without a vendor language probe.
    stack.firestore.collection('users').document(uid).update({'transcription_preferences.single_language_mode': True})
    stack.set_words(uid, words, latency_ms)
    stack.owner_variants += 1
    pcm = _speech_pcm(stack.owner_variants)
    digest = hashlib.sha256(pcm).hexdigest()[:16]
    audio = _framed(pcm)
    filename = _fresh_pcm_filename()
    conversation_id = f'batch-stack-capture-{uuid.uuid4().hex}'
    _seed_capture_conversation(stack, uid, conversation_id)
    headers = {**_auth_headers(uid), 'X-App-Platform': 'ios', 'X-Device-Id-Hash': DEVICE_HASH}
    manifest = stack.http.post(
        stack.admission_url + '/v2/sync-capture-manifest',
        json={
            'conversation_id': conversation_id,
            'files': [{'name': filename, 'sha256': hashlib.sha256(audio).hexdigest()}],
        },
        headers=headers,
        timeout=10.0,
    )
    if manifest.status_code != 200:
        raise StackFailure(f'batch capture manifest returned HTTP {manifest.status_code}')
    response = stack.http.post(
        stack.admission_url + f'/v2/sync-local-files?conversation_id={conversation_id}',
        files=[('files', (filename, audio, 'application/octet-stream'))],
        headers={**headers, 'X-Omi-Sync-Capture-Manifest': manifest.json()['manifest']},
        timeout=30.0,
    )
    if response.status_code != 202:
        raise StackFailure(f'batch admission returned HTTP {response.status_code}: {response.text[:200]}')
    admitted = response.json()
    job_id = admitted.get('job_id')
    if not isinstance(job_id, str) or not job_id.startswith('bp_') or admitted.get('lane') != 'fresh':
        raise StackFailure(f'upload was not admitted to the batch lane: {sorted(admitted)}')
    upload = Upload(uid, job_id, conversation_id, digest, len(pcm) / 32000)
    intake = stack.doc('intakes', job_id)
    if intake.get('owner_id') != uid or not intake.get('segment_ids'):
        raise StackFailure('batch intake row was not durably written by admission')
    upload.segment_ids = list(intake['segment_ids'])
    upload.content_id = intake['content_id']
    for segment in upload.segment_ids:
        job = stack.doc('jobs', segment)
        expected_policy = json.loads((stack.control_dir / 'policy.json').read_text())
        if job.get('policy') != expected_policy:
            raise StackFailure('batch job did not retain the admission policy')
        if not job.get('requires_compute_admission') or not str(job.get('audio_uri', '')).startswith('gs://'):
            raise StackFailure('batch job row lacks compute admission or a staged encrypted artifact')
    _record_job_event(
        {
            'event': 'batch_upload_admitted',
            'scenario': scenario,
            'job_id': job_id,
            'status': admitted.get('status'),
            'segments': len(upload.segment_ids),
            'pcm_hash': digest,
            'owner_hash': _owner_hash(uid),
        }
    )
    return upload


def _status(stack: BatchStack, upload: Upload) -> tuple[int, dict[str, Any]]:
    response = stack.http.get(
        stack.admission_url + f'/v2/sync-local-files/{upload.job_id}', headers=_auth_headers(upload.uid), timeout=10.0
    )
    body = response.json() if response.headers.get('content-type', '').startswith('application/json') else {}
    return response.status_code, body if isinstance(body, dict) else {}


def _wait_job(stack: BatchStack, upload: Upload, predicate: Callable[[dict[str, Any]], bool], label: str, **kw) -> None:
    segment = upload.segment_ids[0]
    _wait_until(lambda: predicate(stack.doc('jobs', segment)), label=label, **kw)


def _drive_to_status(stack: BatchStack, upload: Upload, wanted: str, *, timeout: float = 60.0) -> dict[str, Any]:
    """Poll the real status route; nudge the serving reconcile like its scheduler."""
    observed: list[str] = []
    result: dict[str, Any] = {}

    def done() -> bool:
        nonlocal result
        code, result = _status(stack, upload)
        status = result.get('status') if code == 200 else f'http_{code}'
        if not observed or observed[-1] != status:
            observed.append(str(status))
        if status == wanted:
            return True
        stack.reconcile()
        # Stay under the production per-owner status-poll admission window.
        time.sleep(STATUS_POLL_SECONDS)
        return False

    _wait_until(done, label=f'{upload.job_id} status {wanted} (observed {observed})', timeout=timeout)
    _record_job_event({'event': 'batch_status_path', 'job_id': upload.job_id, 'statuses': observed})
    return result


def _conversation(stack: BatchStack, uid: str, conversation_id: str) -> dict[str, Any]:
    response = stack.http.get(
        stack.admission_url + f'/v1/conversations/{conversation_id}', headers=_auth_headers(uid), timeout=10.0
    )
    if response.status_code != 200:
        raise StackFailure(f'conversation read returned HTTP {response.status_code}')
    return response.json()


def _assert_projected(stack: BatchStack, upload: Upload, status: dict[str, Any], *, provider: str) -> list[dict]:
    result = status.get('result') or {}
    ids = [*(result.get('new_memories') or []), *(result.get('updated_memories') or [])]
    if len(ids) != 1:
        raise StackFailure(f'batch result did not name exactly one projected conversation: {len(ids)}')
    conversation = _conversation(stack, upload.uid, ids[0])
    if ids[0] != upload.conversation_id:
        raise StackFailure(
            f'projection named conversation {ids[0]!r} instead of updating the capture {upload.conversation_id!r}'
        )
    segments = conversation.get('transcript_segments') or []
    words = ' '.join(segment.get('text', '') for segment in segments).lower().split()
    if not segments or words.count('batch') != 1 or words.count('words') != 1:
        raise StackFailure('projected conversation does not hold exactly one copy of the provider transcript')
    providers = {segment.get('stt_provider') for segment in segments}
    if providers != {provider}:
        raise StackFailure(f'projected segments carry provider {sorted(map(str, providers))}, expected {provider}')
    ledger = stack.ledger(upload.uid, upload.content_id)
    if ledger.get('status') != 'completed' or ledger.get('dispatch_protocol') != 'batch_v1':
        raise StackFailure('batch content ledger was not durably completed')
    for segment in upload.segment_ids:
        job = stack.doc('jobs', segment)
        if job.get('state') != 'committed':
            raise StackFailure(f'batch job ended in state {job.get("state")!r}, expected committed')
        from config.policy.stages import STAGE_TYPES

        expected_roles = {'scheduler': 'scheduler', 'projection': 'batch-serving'}
        if provider == 'legacy_sync':
            expected_roles['recovery'] = 'batch-serving'
        for stage, role in expected_roles.items():
            raw = (job.get('policy_parts') or {}).get(stage)
            if (
                not raw
                or raw.get('source_role') != role
                or STAGE_TYPES[stage].from_dict(raw).policy_id != raw.get('policy_id')
            ):
                raise StackFailure('job did not retain a valid owning-role policy stamp')
    obligation_id = hashlib.sha256(f'{upload.uid}\0{ids[0]}'.encode()).hexdigest()
    obligation = stack.firestore.collection('sync_reprocess_outbox').document(obligation_id).get().to_dict() or {}
    summary_part = obligation.get('first_summary_policy') or {}
    if summary_part.get('source_role') != 'batch-serving' or not summary_part.get('policy_id'):
        raise StackFailure('first-summary obligation did not retain its creation policy')
    _record_job_event(
        {
            'event': 'batch_projection_verified',
            'job_id': upload.job_id,
            'conversation_is_capture': True,
            'segments': len(segments),
            'provider': provider,
            'ledger_status': 'completed',
        }
    )
    return segments


# ---- scenarios -----------------------------------------------------------------


def _happy_path(stack: BatchStack) -> None:
    upload = _upload(stack, 'batch-happy')
    status = _drive_to_status(stack, upload, 'completed')
    _assert_projected(stack, upload, status, provider='parakeet')
    segment = upload.segment_ids[0]
    if stack.words_calls(segment) != 1 or stack.paid_calls(upload.pcm_digest) != 0:
        raise StackFailure('happy path did not run the words provider exactly once without paid STT')
    meter = stack.fair_use_meter_ms(upload.uid)
    if meter <= 0:
        raise StackFailure('batch projection did not meter fair-use speech')
    # A duplicate projection sweep must neither duplicate segments nor re-meter.
    for _ in range(2):
        stack.reconcile()
    status = _drive_to_status(stack, upload, 'completed')
    _assert_projected(stack, upload, status, provider='parakeet')
    if stack.fair_use_meter_ms(upload.uid) != meter:
        raise StackFailure('repeated reconcile re-metered completed batch content')
    _record_job_event({'event': 'batch_happy_verified', 'job_id': upload.job_id, 'fair_use_ms': meter})


def _assert_recovery_pending(stack: BatchStack, upload: Upload, phase: str) -> dict[str, Any]:
    """A quarantined unit whose recovery is held/prepared/running polls as live work.

    The client must keep polling (processing, nonzero hint) rather than surface a
    failure that recovery may still repair. Only terminal quarantine reports failed.
    """
    code, status = _status(stack, upload)
    hint = status.get('poll_after_ms')
    if (
        code != 200
        or status.get('status') != 'processing'
        or not isinstance(hint, int)
        or hint <= 0
        or status.get('failed_segments') != 0
        or status.get('processed_segments') != 0
        or status.get('successful_segments') != 0
        or status.get('result') is not None
        or status.get('error') is not None
    ):
        raise StackFailure(
            f'quarantined job {phase} polled HTTP {code} status={status.get("status")!r} '
            f'poll_after_ms={hint!r} failed_segments={status.get("failed_segments")!r}, '
            'expected processing with a nonzero poll hint while recovery is pending'
        )
    return status


def _assert_recovery_failed(stack: BatchStack, upload: Upload) -> dict[str, Any]:
    """A terminally held unit answers completed/batch_unit_held so the phone stops re-uploading.

    Its encrypted audio stays server-side for the operator path; no conversation
    ID is named. BATCH_PIPELINE_HELD_TERMINAL_STATUS_ENABLED=false restores failed.
    """
    code, status = _status(stack, upload)
    result = status.get('result') or {}
    if (
        code != 200
        or status.get('status') != 'completed'
        or status.get('reason_code') != 'batch_unit_held'
        or status.get('poll_after_ms') != 0
        or status.get('failed_segments') != len(upload.segment_ids)
        or result.get('new_memories')
        or result.get('updated_memories')
    ):
        raise StackFailure(
            f'terminal recovery failure polled HTTP {code} status={status.get("status")!r} '
            f'reason_code={status.get("reason_code")!r} poll_after_ms={status.get("poll_after_ms")!r} '
            f'failed_segments={status.get("failed_segments")!r}, expected completed/batch_unit_held without IDs'
        )
    return status


def _quarantine(stack: BatchStack, upload: Upload) -> dict[str, Any]:
    _wait_job(
        stack,
        upload,
        lambda job: job.get('state') == 'quarantined' and job.get('recovery_state') == 'held',
        label='empty-ASR quarantine',
        timeout=60.0,
    )
    status = _assert_recovery_pending(stack, upload, 'awaiting recovery dispatch')
    _record_job_event(
        {
            'event': 'batch_quarantine_observed',
            'job_id': upload.job_id,
            'client_status': status.get('status'),
            'poll_after_ms': status.get('poll_after_ms'),
        }
    )
    return status


def _await_recovery_task(stack: BatchStack, upload: Upload) -> dict[str, Any]:
    segment = upload.segment_ids[0]
    found: dict[str, Any] = {}

    def captured() -> bool:
        nonlocal found
        for task in stack.recovery_tasks():
            if task['body'].get('segment_id') == segment:
                found = task
                return True
        stack.reconcile()
        return False

    _wait_until(captured, label='quarantine recovery task capture', timeout=60.0)
    job = stack.doc('jobs', segment)
    if job.get('recovery_state') != 'prepared':
        raise StackFailure(f'recovery dispatch left state {job.get("recovery_state")!r}, expected prepared')
    return found


def _empty_asr_recovery(stack: BatchStack) -> None:
    upload = _upload(stack, 'batch-empty-asr', words='empty')
    _quarantine(stack, upload)
    task = _await_recovery_task(stack, upload)
    _assert_recovery_pending(stack, upload, 'with prepared recovery')
    first = stack.deliver_recovery(task, retry_count=0)
    if first.status_code != 200 or first.json().get('status') != 'recovered':
        raise StackFailure(f'recovery delivery returned HTTP {first.status_code} {first.text[:120]}')
    duplicate = stack.deliver_recovery(task, retry_count=1)
    if duplicate.status_code != 200 or duplicate.json().get('status') not in {'held', 'reconciled'}:
        raise StackFailure(f'duplicate recovery delivery returned HTTP {duplicate.status_code} {duplicate.text[:120]}')
    if stack.paid_calls(upload.pcm_digest) != 1:
        raise StackFailure('paid fallback was not invoked exactly once across duplicate deliveries')
    status = _drive_to_status(stack, upload, 'completed')
    _assert_projected(stack, upload, status, provider='legacy_sync')
    job = stack.doc('jobs', upload.segment_ids[0])
    if job.get('recovery_state') != 'recovered':
        raise StackFailure('recovered job did not keep its durable recovered intent')
    late = stack.deliver_recovery(task, retry_count=2)
    if late.status_code != 200 or stack.paid_calls(upload.pcm_digest) != 1:
        raise StackFailure('late duplicate recovery after projection issued another paid call')


def _empty_asr_recovery_failure(stack: BatchStack) -> None:
    upload = _upload(stack, 'batch-empty-asr-failure', words='empty')
    stack.set_paid(upload.pcm_digest, mode='fail')
    _quarantine(stack, upload)
    task = _await_recovery_task(stack, upload)
    _assert_recovery_pending(stack, upload, 'with prepared recovery')
    first = stack.deliver_recovery(task, retry_count=0)
    if first.status_code != 200 or first.json().get('status') != 'failed_held':
        raise StackFailure(f'failed recovery delivery returned HTTP {first.status_code} {first.text[:120]}')
    job = stack.doc('jobs', upload.segment_ids[0])
    if job.get('state') != 'quarantined' or job.get('recovery_state') != 'failed_held':
        raise StackFailure(f'failed paid recovery left recovery state {job.get("recovery_state")!r}')
    stack.reconcile()
    status = _assert_recovery_failed(stack, upload)
    duplicate = stack.deliver_recovery(task, retry_count=1)
    if duplicate.status_code != 200 or stack.paid_calls(upload.pcm_digest) != 1:
        raise StackFailure('duplicate delivery after terminal recovery failure issued another paid call')
    _assert_recovery_failed(stack, upload)
    _record_job_event(
        {
            'event': 'batch_recovery_failure_terminal',
            'job_id': upload.job_id,
            'client_status': status.get('status'),
            'poll_after_ms': status.get('poll_after_ms'),
        }
    )


def _worker_sigterm_drains(stack: BatchStack) -> None:
    upload = _upload(stack, 'batch-worker-sigterm', latency_ms=3000)
    segment = upload.segment_ids[0]
    old = stack.worker_name
    _wait_until(lambda: stack.words_calls(segment) == 1, label='words call before SIGTERM', timeout=60.0)
    signalled = time.monotonic()
    stack.signal(old, signal.SIGTERM)
    code = stack.wait_exit(old, timeout=30.0)
    if code is None:
        raise StackFailure('SIGTERM did not let the batch worker drain and exit')
    stack.forget(old)
    drain_ms = int((time.monotonic() - signalled) * 1000)
    job = stack.doc('jobs', segment)
    if job.get('state') not in {'committed', 'result_ready'} or stack.words_calls(segment) != 1:
        raise StackFailure(f'draining worker left state {job.get("state")!r} instead of publishing its result')
    stack.start_worker()
    stack.wait_worker()
    status = _drive_to_status(stack, upload, 'completed')
    _assert_projected(stack, upload, status, provider='parakeet')
    if stack.words_calls(segment) != 1:
        raise StackFailure('replacement worker re-ran a result published during SIGTERM drain')
    _record_job_event({'event': 'batch_worker_sigterm_drain', 'exit_code': code, 'drain_ms': drain_ms})


def _worker_killed_after_grace(stack: BatchStack) -> None:
    upload = _upload(stack, 'batch-worker-killed', latency_ms=60000)
    segment = upload.segment_ids[0]
    old = stack.worker_name
    _wait_until(lambda: stack.words_calls(segment) == 1, label='words call before kill', timeout=60.0)
    leased = stack.doc('jobs', segment)
    stack.signal(old, signal.SIGTERM)
    code = stack.wait_exit(old, timeout=SIGTERM_GRACE_SECONDS)
    if code is not None:
        raise StackFailure('a 60s model call should outlast the SIGTERM grace period')
    # Like the kubelet after terminationGracePeriodSeconds.
    stack.signal(old, signal.SIGKILL)
    stack.wait_exit(old, timeout=10.0)
    stack.forget(old)
    orphaned = stack.doc('jobs', segment)
    if orphaned.get('state') != 'leased' or orphaned.get('token') != leased.get('token'):
        raise StackFailure('killed worker did not leave its lease durable for expiry recovery')
    stack.set_words(upload.uid, 'words', 0)
    killed_at = time.monotonic()
    stack.start_worker()
    stack.wait_worker()
    status = _drive_to_status(stack, upload, 'completed', timeout=90.0)
    _assert_projected(stack, upload, status, provider='parakeet')
    job = stack.doc('jobs', segment)
    if stack.words_calls(segment) != 2:
        raise StackFailure(f'expected one lost and one replacement words call, saw {stack.words_calls(segment)}')
    _record_job_event(
        {
            'event': 'batch_worker_kill_recovered',
            'recovery_ms': int((time.monotonic() - killed_at) * 1000),
            'attempt': job.get('attempt'),
            'compressed_lease_seconds': LEASE_SECONDS,
        }
    )


def _serving_replacement_mid_paid_call(stack: BatchStack) -> None:
    upload = _upload(stack, 'batch-serving-sigterm', words='empty')
    stack.set_paid(upload.pcm_digest, latency_ms=3000)
    _quarantine(stack, upload)
    task = _await_recovery_task(stack, upload)
    responses: list[httpx.Response | Exception] = []

    def deliver() -> None:
        try:
            responses.append(stack.deliver_recovery(task, retry_count=0))
        except Exception as error:  # noqa: BLE001 - recorded for the assertion below
            responses.append(error)

    thread = threading.Thread(target=deliver, daemon=True)
    thread.start()
    _wait_until(lambda: stack.paid_calls(upload.pcm_digest) == 1, label='paid call in flight', timeout=30.0)
    old = stack.serving_name
    stack.signal(old, signal.SIGTERM)
    code = stack.wait_exit(old, timeout=45.0)
    if code is None:
        raise StackFailure('batch serving revision did not exit after SIGTERM within 45 s')
    thread.join(timeout=10.0)
    stack.forget(old)
    first = responses[0] if responses else None
    in_flight_status = (
        first.json().get('status') if isinstance(first, httpx.Response) and first.status_code == 200 else None
    )
    _record_job_event(
        {
            'event': 'batch_serving_sigterm',
            'exit_code': code,
            'in_flight_http': first.status_code if isinstance(first, httpx.Response) else type(first).__name__,
            'in_flight_status': in_flight_status,
        }
    )
    if in_flight_status != 'recovered':
        raise StackFailure('SIGTERM did not let the in-flight paid recovery settle its durable result')
    _wait_for_port_free(stack.serving_port, label='terminated batch serving')
    stack.start_serving()
    stack.wait_serving()
    duplicate = stack.deliver_recovery(task, retry_count=1)
    if duplicate.status_code != 200 or stack.paid_calls(upload.pcm_digest) != 1:
        raise StackFailure('redelivery to the replacement serving revision issued another paid call')
    status = _drive_to_status(stack, upload, 'completed')
    _assert_projected(stack, upload, status, provider='legacy_sync')


def _serving_killed_mid_paid_call(stack: BatchStack) -> None:
    upload = _upload(stack, 'batch-serving-killed', words='empty')
    stack.set_paid(upload.pcm_digest, latency_ms=60000)
    _quarantine(stack, upload)
    task = _await_recovery_task(stack, upload)

    def deliver() -> None:
        # The connection dies with the killed revision; only durable state counts.
        with suppress(Exception):
            stack.deliver_recovery(task, retry_count=0)

    thread = threading.Thread(target=deliver, daemon=True)
    thread.start()
    _wait_until(lambda: stack.paid_calls(upload.pcm_digest) == 1, label='paid call in flight', timeout=30.0)
    old = stack.serving_name
    stack.signal(old, signal.SIGKILL)
    stack.wait_exit(old, timeout=10.0)
    stack.forget(old)
    thread.join(timeout=10.0)
    _wait_for_port_free(stack.serving_port, label='killed batch serving')
    stack.set_paid(upload.pcm_digest, latency_ms=0)
    stack.start_serving()
    stack.wait_serving()
    redelivered = stack.deliver_recovery(task, retry_count=1)
    stack.reconcile()
    job = stack.doc('jobs', upload.segment_ids[0])
    if redelivered.status_code != 200 or redelivered.json().get('status') != 'held':
        raise StackFailure(
            f'killed-revision redelivery returned HTTP {redelivered.status_code} {redelivered.text[:120]}, '
            'expected the held acknowledgement Cloud Tasks relies on'
        )
    if stack.paid_calls(upload.pcm_digest) != 1:
        raise StackFailure('replacement serving re-issued a paid call whose outcome was unknown')
    if job.get('recovery_state') != 'running' or job.get('state') != 'quarantined':
        raise StackFailure(f'unknown paid outcome left recovery state {job.get("recovery_state")!r}')
    status = _assert_recovery_pending(stack, upload, 'with running recovery')
    _record_job_event(
        {
            'event': 'batch_serving_kill_paid_call',
            'redelivery_http': redelivered.status_code,
            'redelivery_status': redelivered.json().get('status') if redelivered.status_code == 200 else None,
            'recovery_state': job.get('recovery_state'),
            'client_status': status.get('status'),
            'poll_after_ms': status.get('poll_after_ms'),
        }
    )


def _privacy_fenced(stack: BatchStack) -> None:
    from database.batch_pipeline_privacy import advance_privacy_generation

    # In-flight GPU work: the account-deletion fence lands while words run.
    compute = _upload(stack, 'batch-privacy-compute', latency_ms=3000)
    segment = compute.segment_ids[0]
    _wait_until(lambda: stack.words_calls(segment) == 1, label='words call before fence', timeout=60.0)
    advance_privacy_generation(stack.firestore, compute.uid, blocked=True)
    _wait_until(
        lambda: any(
            event.get('event') == 'words_completed' and segment in (event.get('segment_ids') or [])
            for event in stack.evidence_events('providers')
        ),
        label='fenced words call completion',
        timeout=30.0,
    )
    time.sleep(2.0)
    for _ in range(3):
        stack.reconcile()
    job = stack.doc('jobs', segment)
    if stack.doc('results', segment) or job.get('result') or job.get('state') in {'result_ready', 'committed'}:
        raise StackFailure('privacy-fenced worker result was published')
    # Read through the real (decrypting) conversation route, not raw ciphertext.
    if _conversation(stack, compute.uid, compute.conversation_id).get('transcript_segments'):
        raise StackFailure('privacy-fenced work was projected into the conversation')
    code, status = _status(stack, compute)
    _record_job_event(
        {
            'event': 'batch_privacy_compute_fenced',
            'job_state': job.get('state'),
            'status_http': code,
            'client_status': status.get('status'),
            'paid_calls': stack.paid_calls(compute.pcm_digest),
        }
    )
    if stack.paid_calls(compute.pcm_digest):
        raise StackFailure('privacy-fenced compute work reached paid STT')

    # Paid recovery: the fence lands after dispatch prepared the intent.
    recovery = _upload(stack, 'batch-privacy-recovery', words='empty')
    _quarantine(stack, recovery)
    task = _await_recovery_task(stack, recovery)
    advance_privacy_generation(stack.firestore, recovery.uid, blocked=True)
    delivered = stack.deliver_recovery(task, retry_count=0)
    if delivered.status_code != 200 or delivered.json().get('status') != 'cancelled':
        raise StackFailure(f'fenced recovery returned HTTP {delivered.status_code} {delivered.text[:120]}')
    for _ in range(2):
        stack.reconcile()
    if stack.paid_calls(recovery.pcm_digest) != 0:
        raise StackFailure('privacy-fenced recovery issued a paid call')
    rjob = stack.doc('jobs', recovery.segment_ids[0])
    if stack.doc('results', recovery.segment_ids[0]) or rjob.get('result'):
        raise StackFailure('privacy-fenced recovery published a result')
    if _conversation(stack, recovery.uid, recovery.conversation_id).get('transcript_segments'):
        raise StackFailure('privacy-fenced recovery was projected into the conversation')
    _record_job_event(
        {
            'event': 'batch_privacy_recovery_fenced',
            'job_state': rjob.get('state'),
            'recovery_state': rjob.get('recovery_state'),
        }
    )


def _burst_drain(stack: BatchStack) -> None:
    """Three captures from one owner: commit order and cross-process drain time."""
    uid = stack.scenario_uid('batch-burst')
    started = time.monotonic()
    uploads = [_upload(stack, 'batch-burst', uid=uid) for _ in range(3)]
    admitted_ms = int((time.monotonic() - started) * 1000)
    for upload in uploads:
        _drive_to_status(stack, upload, 'completed')
    order = [
        event.get('segment_id')
        for event in stack.evidence_events('providers')
        if event.get('event') == 'worker_item_started'
        and event.get('segment_id') in {upload.segment_ids[0] for upload in uploads}
    ]
    expected_order = [upload.segment_ids[0] for upload in uploads]
    if order != expected_order:
        raise StackFailure(
            'one-owner burst was not drained in admission order '
            f'(got {[(segment or "?")[:8] for segment in order]}, '
            f'expected {[(segment or "?")[:8] for segment in expected_order]})'
        )
    _record_job_event(
        {
            'event': 'batch_burst_drained',
            'uploads': len(uploads),
            'admission_ms': admitted_ms,
            'drain_ms': int((time.monotonic() - started) * 1000),
            'worker_starts': len(order),
            'drain_order_verified': True,
        }
    )


def _unit_states(stack: BatchStack, uploads: list[Upload]) -> list[dict[str, Any]]:
    """Sanitized durable states for diagnosing a stuck drain (no owner IDs)."""
    rows = []
    for upload in uploads:
        for segment in upload.segment_ids:
            job, result = stack.doc('jobs', segment), stack.doc('results', segment)
            rows.append(
                {
                    'job': upload.job_id[:11],
                    'segment': segment[:8],
                    'owner_hash': _owner_hash(upload.uid),
                    'state': job.get('state'),
                    'attempt': job.get('attempt'),
                    'merge_pending': job.get('merge_pending'),
                    'log_sequence': result.get('log_sequence'),
                    'previous': (result.get('previous_segment_id') or '')[:8],
                    'projection_state': result.get('projection_state'),
                    'failure': job.get('failure'),
                    'fence': _fence_reason(
                        stack, upload.uid, job.get('conversation_id'), job.get('privacy_generation')
                    ),
                }
            )
    return rows


def _fence_reason(stack: BatchStack, uid: str, conversation_id: str | None, generation: int | None) -> str:
    from google.cloud import firestore

    from database.batch_pipeline_privacy import BatchPrivacyBlocked, assert_batch_write_allowed

    @firestore.transactional
    def check(transaction):
        return assert_batch_write_allowed(
            stack.firestore,
            transaction,
            uid,
            conversation_ids=(conversation_id,) if conversation_id else (),
            expected_generation=generation,
        )

    try:
        return f'open:{check(stack.firestore.transaction())}'
    except BatchPrivacyBlocked as error:
        return f'blocked:{error.reason.value}'


# Prod keeps a 120s lease renewed every 20s. The emulator holds a
# collection-wide lock for every transactional query, so two replicas plus
# serving can stall one heartbeat for seconds; the 8s/2s compression used by
# the kill scenario would then expire healthy leases (result_lease_lost). Keep
# prod's 6:1 lease/heartbeat ratio at a scale the emulator can honour.
# One unit per flight: with the default pipeline depth a replica holds up to
# depth x capacity claimed units (one chain plus a waiting lane), which at the
# stack capacity of 4 covers this whole six-unit scenario. Bounding each claim
# keeps both replicas draining so cross-replica once-only and order are tested.
TWO_WORKER_TIMING = {
    'OMI_BATCH_STACK_LEASE_SECONDS': '60',
    'OMI_BATCH_STACK_HEARTBEAT_SECONDS': '10',
    'BATCH_PIPELINE_MODEL_BATCH_SIZE': '1',
}


def _two_workers(stack: BatchStack) -> None:
    """Two worker replicas drain one queue: once-only, capture order, one paid call."""
    stack.stop_worker(stack.worker_name)
    stack.start_worker(TWO_WORKER_TIMING)
    peer = stack.start_peer_worker(TWO_WORKER_TIMING)
    stack.wait_worker()
    stack.wait_worker(peer)
    try:
        uid = stack.scenario_uid('batch-two-workers-burst')
        started = time.monotonic()
        burst = [_upload(stack, 'batch-two-workers-burst', uid=uid, latency_ms=2500) for _ in range(3)]
        solos = [_upload(stack, f'batch-two-workers-solo-{n}', latency_ms=2500) for n in range(2)]
        empty = _upload(stack, 'batch-two-workers-empty', words='empty')
        for upload in [*burst, *solos]:
            try:
                _drive_to_status(stack, upload, 'completed', timeout=120.0)
            except StackFailure:
                _record_job_event({'event': 'batch_two_workers_stuck', 'units': _unit_states(stack, [*burst, *solos])})
                raise
        drain_ms = int((time.monotonic() - started) * 1000)
        segments = [segment for upload in [*burst, *solos] for segment in upload.segment_ids]
        events = stack.evidence_events('providers')
        starts = [e for e in events if e.get('event') == 'worker_item_started' and e.get('segment_id') in segments]
        results = [e for e in events if e.get('event') == 'worker_item_result' and e.get('segment_id') in segments]
        workers = {e.get('worker_name') for e in starts}
        if workers != {stack.worker_name, peer}:
            raise StackFailure(f'expected both replicas to drain work, saw {sorted(map(str, workers))}')
        # Compute is at-least-once by design: a lease that expires (or whose
        # renewal is ambiguous at publication) is recovered and leased again,
        # and the stale holder's result is fenced by its token. The emulator's
        # collection-wide transaction lock stalls heartbeats on slow runners,
        # so a re-lease is legitimate here. The cross-replica invariants are:
        # every compute ran under its own lease grant (computes <= grants),
        # and each segment committed exactly once to the result log. Grants
        # come from the replicas' own lease evidence, not the job's attempt
        # field: attempt is a retry budget that a pre-compute refund lowers.
        recomputed: set[str] = set()
        attempt_gaps = 0
        for segment in segments:
            job = stack.doc('jobs', segment)
            attempt = int(job.get('attempt') or 0)
            grants = sum(e.get('event') == 'lease_granted' and e.get('segment_id') == segment for e in events)
            refunds = sum(
                e.get('event') == 'lease_refunded' and e.get('segment_id') == segment and e.get('refunded')
                for e in events
            )
            computes = sum(
                e.get('event') == 'words_started' and segment in (e.get('segment_ids') or []) for e in events
            )
            computed = sum(e['segment_id'] == segment for e in results)
            counts = (
                f'segment={segment[:8]} grants={grants} refunds={refunds} attempt={attempt} '
                f'computes={computes} results={computed} state={job.get("state")} failure={job.get("failure")}'
            )
            if computes < 1 or computed < 1:
                raise StackFailure(f'a two-replica segment has no compute evidence ({counts})')
            if computes > grants or computed > grants:
                _record_job_event(
                    {'event': 'batch_two_workers_overcompute', 'units': _unit_states(stack, [*burst, *solos])}
                )
                raise StackFailure(f'a segment was computed more often than it was leased across replicas ({counts})')
            if attempt != grants - refunds:
                # Visible, not fatal: the retry budget drifted from the grants
                # observed. Compute and publication are still bounded above.
                attempt_gaps += 1
                print(f'two-replica attempt drift: {counts}', flush=True)
            if computes > 1:
                recomputed.add(segment)
            if job.get('state') != 'committed':
                raise StackFailure('a two-replica segment did not reach the committed result log')
            if stack.doc('results', segment).get('segment_id') != segment:
                raise StackFailure('a two-replica segment has no committed result log entry')
        chain = sorted(
            (stack.doc('results', upload.segment_ids[0]) for upload in burst), key=lambda entry: entry['log_sequence']
        )
        if len({entry['log_sequence'] for entry in chain}) != len(chain):
            raise StackFailure('two-replica burst committed a segment more than once to the result log')
        committed = [entry['segment_id'] for entry in chain]
        if [entry['previous_segment_id'] for entry in chain[1:]] != committed[:-1]:
            raise StackFailure('two-replica burst result log has a broken predecessor chain')
        # Capture order is (capture_at, segment_id); second-resolution capture
        # names can tie, so upload order alone is not the commit contract.
        expected = sorted((entry['capture_at'], entry['segment_id']) for entry in chain)
        expected = [segment for _, segment in expected]
        late = [entry['segment_id'] for entry in chain if entry.get('late_capture')]
        if not late:
            if committed != expected:
                raise StackFailure('two-replica burst was committed out of capture order')
        else:
            # A re-leased head can outlast the bounded merge head wait (#22820);
            # its successors then commit in capture order and the head appends
            # as late_capture. Only a recomputed unit may be released late.
            if not set(late) <= recomputed:
                raise StackFailure('two-replica burst marked an in-order capture late')
            if [s for s in committed if s not in late] != [s for s in expected if s not in late]:
                raise StackFailure('two-replica burst was committed out of capture order')

        # Reconciles while the other captures drained may already have
        # prepared this unit's recovery intent; accept either held state.
        _wait_job(
            stack,
            empty,
            lambda job: job.get('state') == 'quarantined' and job.get('recovery_state') in {'held', 'prepared'},
            label='two-replica empty-ASR quarantine',
            timeout=60.0,
        )
        task = _await_recovery_task(stack, empty)
        for retry in range(2):
            delivered = stack.deliver_recovery(task, retry_count=retry)
            if delivered.status_code != 200:
                raise StackFailure(f'two-replica recovery delivery returned HTTP {delivered.status_code}')
        _drive_to_status(stack, empty, 'completed')
        if stack.paid_calls(empty.pcm_digest) != 1:
            raise StackFailure('two replicas produced other than exactly one paid recovery call')
        _record_job_event(
            {
                'event': 'batch_two_workers_verified',
                'segments': len(segments),
                'replicas': len(workers),
                'recomputed_after_lease_loss': len(recomputed),
                'attempt_drift': attempt_gaps,
                'per_replica': {
                    'primary': sum(e.get('worker_name') == stack.worker_name for e in starts),
                    'peer': sum(e.get('worker_name') == peer for e in starts),
                },
                'drain_ms': drain_ms,
                'paid_calls': 1,
            }
        )
    finally:
        stack.stop_worker(peer)
        # Later scenarios expect one primary with the default compressed lease.
        stack.stop_worker(stack.worker_name)
        stack.start_worker()
        stack.wait_worker()


SCENARIOS: tuple[tuple[str, Callable[[BatchStack], None]], ...] = (
    ('batch-happy', _happy_path),
    ('batch-empty-asr-recovery', _empty_asr_recovery),
    ('batch-empty-asr-recovery-failure', _empty_asr_recovery_failure),
    ('batch-worker-sigterm-drain', _worker_sigterm_drains),
    ('batch-worker-kill-lease-recovery', _worker_killed_after_grace),
    ('batch-serving-sigterm-paid-call', _serving_replacement_mid_paid_call),
    ('batch-serving-kill-paid-call', _serving_killed_mid_paid_call),
    ('batch-privacy-fence', _privacy_fenced),
    ('batch-burst', _burst_drain),
    ('batch-two-workers', _two_workers),
)


def run_batch_scenarios(state_dir: Path) -> None:
    stack = BatchStack(state_dir)
    timings: dict[str, int] = {}
    try:
        started = time.monotonic()
        stack.start()
        timings['startup'] = int((time.monotonic() - started) * 1000)
        for name, scenario in SCENARIOS:
            began = time.monotonic()
            print(f'batch scenario {name}: running', flush=True)
            scenario(stack)
            timings[name] = int((time.monotonic() - began) * 1000)
            print(f'batch scenario {name}: passed in {timings[name] / 1000:.1f}s', flush=True)
        _record_job_event({'event': 'batch_scenarios_passed', 'timings_ms': timings})
        _assert_evidence_is_sanitized(stack)
        for path in stack.evidence_dir.glob('*.jsonl'):
            if SENSITIVE_UID in path.read_text(encoding='utf-8'):
                raise StackFailure(f'owner id leaked into batch evidence: {path.name}')
    finally:
        stack.close()
        stack.cleanup_workspace_files()
