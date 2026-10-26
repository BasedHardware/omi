"""Role-configured ASGI entrypoint for the local Sync Cloud Tasks gauntlet.

The admission process keeps the real public Sync route and production task
protobuf construction.  The worker process keeps the protected worker route,
lease/ledger transitions, and provider-independent leaves.  They share only
isolated Redis, Firestore, and filesystem-backed staged blobs.
"""

from __future__ import annotations

import os
import time
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from google.oauth2 import id_token
from fastapi import Header, HTTPException, Request, Response

# Install the no-egress guard before backend imports can instantiate a provider.
from .isolation import LOOPBACK_HOSTS as _LOOPBACK_HOSTS, install_no_egress_guard

install_no_egress_guard()

from .events import write_event  # noqa: E402
from .storage import configure_storage_dir, patch_google_storage, read_signed_url  # noqa: E402

_ROLES = frozenset({'admission', 'worker', 'batch-serving'})


def _role() -> str:
    value = os.getenv('OMI_SYNC_STACK_ROLE', '')
    if value not in _ROLES:
        raise RuntimeError('OMI_SYNC_STACK_ROLE must be admission, worker, or batch-serving')
    return value


ROLE = _role()


# ``cloud_tasks`` imports the production task helper, so load it only after
# the no-egress guard is active.
from .cloud_tasks import CloudTasksRecorder  # noqa: E402
from .local_oidc import local_oidc_token  # noqa: E402


def _local_oidc_bindings() -> set[tuple[str, str]]:
    """(audience, identity) pairs this process's task/worker routes accept."""
    pairs = {
        (os.getenv('SYNC_TASKS_OIDC_AUDIENCE', ''), os.getenv('SYNC_TASKS_INVOKER_SA', '')),
    }
    if ROLE == 'batch-serving':
        pairs.add(
            (os.getenv('BATCH_PIPELINE_WORKER_AUDIENCE', ''), os.getenv('BATCH_PIPELINE_WORKER_SERVICE_ACCOUNT', ''))
        )
        pairs.add((os.getenv('BATCH_PIPELINE_RECOVERY_TASK_AUDIENCE', ''), os.getenv('SYNC_TASKS_INVOKER_SA', '')))
    return {(audience, identity) for audience, identity in pairs if audience and identity}


def _verify_local_oidc(token: str, _request: Any, *, audience: str | None = None, **_kwargs: Any) -> dict[str, Any]:
    """Accept one exact local token per configured audience/identity binding.

    The token binds both the audience and the service-account identity, and the
    production dependency still compares the returned identity with the route's
    configured invoker, so a token minted for one route's audience or identity
    is rejected by every other route.
    """
    for expected_audience, expected_identity in _local_oidc_bindings():
        if audience == expected_audience and token == local_oidc_token(expected_audience, expected_identity):
            write_event(
                'worker' if ROLE == 'worker' else 'serving',
                {'event': 'local_oidc_verified', 'audience': audience, 'identity_verified': True},
            )
            return {'email': expected_identity, 'email_verified': True}
    raise ValueError('local Cloud Tasks OIDC verifier rejected the token')


_storage_root = os.getenv('OMI_SYNC_STACK_STORAGE_DIR', '').strip()
if not _storage_root:
    raise RuntimeError('OMI_SYNC_STACK_STORAGE_DIR is required')
configure_storage_dir(_storage_root)
patch_google_storage()

task_recorder: CloudTasksRecorder | None = None
if ROLE in {'admission', 'batch-serving'}:
    import utils.cloud_tasks as production_cloud_tasks  # noqa: E402

    task_recorder = CloudTasksRecorder()
    production_cloud_tasks._tasks_client = task_recorder
if ROLE == 'admission':
    from database import conversations as conversations_db  # noqa: E402
    from database._client import get_firestore_client  # noqa: E402
else:
    # ``verify_cloud_tasks_oidc`` still validates header shape, audience,
    # service-account identity, and retry count. The local seam replaces the
    # Google verifier with one exact token; signature, issuer, and expiry
    # validation remain a production-provider concern.
    id_token.verify_oauth2_token = _verify_local_oidc

if ROLE == 'batch-serving':
    # Replace only the paid legacy STT leaf that quarantine recovery invokes.
    from .batch_providers import install_paid_stt_fake  # noqa: E402

    install_paid_stt_fake()


from main import app  # noqa: E402

if ROLE == 'admission' and os.getenv('OMI_BATCH_STACK_POLICY_FILE'):
    import json
    from config.policy import BatchUnitPolicy
    from routers import sync as _policy_sync_router

    _recorded_policy = BatchUnitPolicy.from_dict(
        json.loads(Path(os.environ['OMI_BATCH_STACK_POLICY_FILE']).read_text())
    )
    _policy_sync_router.resolve_batch_policy = lambda uid: _recorded_policy


def _require_control(
    request: Request,
    control_token: str | None = Header(None, alias='X-Omi-Sync-Stack-Control'),
) -> None:
    client_host = request.client.host if request.client else None
    if client_host not in _LOOPBACK_HOSTS or control_token != os.getenv('OMI_SYNC_STACK_CONTROL_TOKEN'):
        raise HTTPException(status_code=403, detail='Sync stack control is loopback-only')


@app.get('/__sync-stack/health', include_in_schema=False)
def sync_stack_health() -> dict[str, str]:
    return {'status': 'ok', 'role': ROLE}


if task_recorder is not None:
    recorder = task_recorder

    @app.get('/__sync-stack/tasks', include_in_schema=False)
    def sync_stack_tasks(
        request: Request,
        kind: str | None = None,
        control_token: str | None = Header(None, alias='X-Omi-Sync-Stack-Control'),
    ) -> list[dict[str, Any]]:
        _require_control(request, control_token)
        # Loopback-only control data, never serialized into the evidence files.
        return [
            {'task_id': captured.task_id, 'kind': captured.kind, 'url': captured.url, 'body': captured.body}
            for captured in recorder.tasks(kind)
        ]

    @app.get('/__sync-stack/tasks/{task_id}', include_in_schema=False)
    def sync_stack_task(
        task_id: str,
        request: Request,
        control_token: str | None = Header(None, alias='X-Omi-Sync-Stack-Control'),
    ) -> dict[str, Any]:
        _require_control(request, control_token)
        captured = recorder.task(task_id)
        if captured is None:
            raise HTTPException(status_code=404, detail='captured task not found')
        # Loopback-only control data, never serialized into the evidence files.
        return {'task_id': captured.task_id, 'url': captured.url, 'body': captured.body}


if ROLE == 'admission':

    @app.post('/__sync-stack/capture-provenance/{conversation_id}', include_in_schema=False, status_code=204)
    def sync_stack_capture_provenance(
        conversation_id: str,
        payload: dict[str, Any],
        request: Request,
        control_token: str | None = Header(None, alias='X-Omi-Sync-Stack-Control'),
    ) -> Response:
        """Create server-capture provenance through the isolated production encoder."""
        _require_control(request, control_token)
        uid = payload.get('uid')
        device_id = payload.get('device_id')
        platform = payload.get('platform')
        if not all(isinstance(value, str) and value for value in (uid, device_id, platform)):
            raise HTTPException(status_code=422, detail='capture provenance requires uid and device context')
        now = datetime.now(timezone.utc)
        capture = {
            'id': conversation_id,
            'created_at': now,
            'started_at': now,
            'finished_at': now,
            'source': 'omi',
            'language': 'en',
            'structured': {
                'title': 'Local capture provenance',
                'overview': '',
                'emoji': '🧪',
                'category': 'other',
                'action_items': [],
                'events': [],
            },
            'transcript_segments': [],
            'private_cloud_sync_enabled': False,
            'status': 'completed',
            'discarded': False,
            'is_locked': False,
            'data_protection_level': 'enhanced',
            'client_device_id': device_id,
            'client_platform': platform,
        }
        encoded_capture = conversations_db.encode_conversation_for_write(uid, capture, level='enhanced')
        if isinstance(encoded_capture.get('transcript_segments'), list):
            raise RuntimeError('Sync stack capture provenance was not encrypted by the production encoder')
        get_firestore_client().collection('users').document(uid).collection('conversations').document(
            conversation_id
        ).set(encoded_capture)
        return Response(status_code=204)

elif ROLE == 'worker':
    from models.conversation import Conversation  # noqa: E402
    from models.conversation_enums import ConversationStatus  # noqa: E402
    from models.structured import Structured  # noqa: E402
    import utils.sync.pipeline as sync_pipeline  # noqa: E402
    from utils.conversations import lifecycle as lifecycle_service  # noqa: E402
    from routers import sync as sync_router  # noqa: E402

    def _nonnegative_int(name: str) -> int:
        raw = os.getenv(name, '0')
        try:
            value = int(raw)
        except ValueError as error:
            raise RuntimeError(f'{name} must be an integer') from error
        if value < 0:
            raise RuntimeError(f'{name} must be non-negative')
        return value

    _worker_failures_remaining = _nonnegative_int('OMI_SYNC_STACK_WORKER_FAILURES')
    _pre_ledger_failures_remaining = _nonnegative_int('OMI_SYNC_STACK_PRE_LEDGER_FAILURES')
    _post_ledger_failures_remaining = _nonnegative_int('OMI_SYNC_STACK_POST_LEDGER_FAILURES')
    _cleanup_failures_remaining = _nonnegative_int('OMI_SYNC_STACK_CLEANUP_FAILURES')
    _process_persistence_fenced = os.getenv('OMI_SYNC_STACK_PROCESS_PERSISTENCE_FENCED', 'false').lower() == 'true'
    _gate_dir_raw = os.getenv('OMI_SYNC_STACK_PROCESS_GATE_DIR', '').strip()
    _gate_dir = Path(_gate_dir_raw) if _gate_dir_raw else None

    def _job_id_from_path(path: str) -> str:
        # Production paths are syncing/<uid>/<job-id>/<file>; never record path.
        return Path(path).parent.name

    def _local_vad(path: str, *, return_segments: bool = False, **_kwargs: Any) -> Any:
        """External VAD leaf: prove the production decoder made readable WAV."""
        with wave.open(path, 'rb') as wav_file:
            duration = wav_file.getnframes() / float(wav_file.getframerate())
        segments = [{'start': 0.0, 'end': min(duration, 1.0)}] if duration >= 1.0 else []
        write_event(
            'providers', {'event': 'vad_result', 'job_id': _job_id_from_path(path), 'segment_count': len(segments)}
        )
        return segments if return_segments else bool(segments)

    def _local_prerecorded(audio_url: str, *, return_language: bool = False, **_kwargs: Any) -> Any:
        """Deterministic STT leaf; it emits no transcript into evidence."""
        job_id = audio_url.rsplit('/', 1)[-1]
        write_event('providers', {'event': 'stt_completed', 'job_id': job_id, 'word_count': 1})
        words = [
            {
                'timestamp': [0.0, 1.0],
                'speaker': 'SPEAKER_00',
                'text': os.getenv('OMI_SYNC_STACK_TRANSCRIPT_TOKEN', 'sync-stack-transcript'),
            }
        ]
        return (words, 'en') if return_language else words

    def _wait_for_process_gate(conversation_id: str) -> None:
        if _gate_dir is None:
            return
        _gate_dir.mkdir(parents=True, exist_ok=True)
        entered = _gate_dir / 'entered'
        release = _gate_dir / 'release'
        entered.write_text('entered', encoding='utf-8')
        write_event('providers', {'event': 'processor_gate_entered', 'conversation_id': conversation_id})
        deadline = time.monotonic() + 15.0
        while not release.exists():
            if time.monotonic() >= deadline:
                raise RuntimeError('controlled Sync processor gate timed out')
            time.sleep(0.01)

    def _local_process_conversation(
        uid: str,
        language: str | None = None,
        conversation: Any = None,
        *,
        language_code: str | None = None,
        persistence_observer: Any = None,
        **_kwargs: Any,
    ) -> Conversation:
        """Deterministic process leaf with real lifecycle-backed persistence."""
        if conversation is None:
            raise ValueError('Sync stack deterministic processor requires a conversation')
        conversation_id = getattr(conversation, 'id', None)
        if not isinstance(conversation_id, str) or not conversation_id:
            raise ValueError('Sync stack processor requires a durable conversation id')
        _wait_for_process_gate(conversation_id)
        effective_language = language_code or language or 'en'
        started_at = getattr(conversation, 'started_at', None) or datetime.now(timezone.utc)
        finished_at = getattr(conversation, 'finished_at', None) or started_at
        completed = Conversation(
            id=conversation_id,
            created_at=getattr(conversation, 'created_at', None) or started_at,
            started_at=started_at,
            finished_at=finished_at,
            source=getattr(conversation, 'source', None),
            language=effective_language,
            structured=Structured(
                title='Sync stack deterministic conversation',
                overview='Deterministic local processor result.',
                emoji='🧪',
                category='other',
            ),
            transcript_segments=list(getattr(conversation, 'transcript_segments', [])),
            private_cloud_sync_enabled=bool(getattr(conversation, 'private_cloud_sync_enabled', False)),
            status=ConversationStatus.completed,
            is_locked=bool(getattr(conversation, 'is_locked', False)),
            client_device_id=getattr(conversation, 'client_device_id', None),
            client_platform=getattr(conversation, 'client_platform', None),
            # Preserve the ingest-owned revision the processor read, exactly as a
            # real processor payload must: persist_processing_result_with_lifecycle
            # fences writes whose revision no longer matches the stored transcript.
            sync_content_revision=getattr(conversation, 'sync_content_revision', None),
        )
        persisted = (
            False
            if _process_persistence_fenced
            else lifecycle_service.persist_processed_conversation(uid, completed.model_dump())
        )
        if persistence_observer is not None:
            persistence_observer(persisted)
        if not persisted:
            write_event('providers', {'event': 'conversation_persistence_fenced', 'conversation_id': completed.id})
            return completed
        write_event('providers', {'event': 'conversation_persisted', 'conversation_id': completed.id})
        return completed

    _original_delete_staged_blobs_async = sync_router._delete_staged_blobs_async
    _original_run_full_pipeline = sync_router._run_full_pipeline_background_async
    _original_mark_sync_content_completed = sync_pipeline.mark_sync_content_completed

    async def _run_full_pipeline_with_controlled_worker_failure(*args: Any, **kwargs: Any) -> Any:
        global _worker_failures_remaining
        if _worker_failures_remaining:
            _worker_failures_remaining -= 1
            write_event('worker', {'event': 'intentional_worker_failure'})
            raise RuntimeError('controlled Sync worker execution failure')
        return await _original_run_full_pipeline(*args, **kwargs)

    async def _delete_staged_blobs_with_controlled_failure(blob_paths: list[str], **custody) -> None:
        global _cleanup_failures_remaining
        if _cleanup_failures_remaining:
            _cleanup_failures_remaining -= 1
            write_event('jobs', {'event': 'intentional_cleanup_failure', 'blob_count': len(blob_paths)})
            raise RuntimeError('controlled Sync staged-cleanup failure')
        await _original_delete_staged_blobs_async(blob_paths, **custody)

    def _mark_sync_content_completed_with_controlled_failure(*args: Any, **kwargs: Any) -> Any:
        global _pre_ledger_failures_remaining, _post_ledger_failures_remaining
        if _pre_ledger_failures_remaining:
            _pre_ledger_failures_remaining -= 1
            write_event('worker', {'event': 'intentional_pre_ledger_failure'})
            raise RuntimeError('controlled Sync failure before durable ledger completion')
        completed = _original_mark_sync_content_completed(*args, **kwargs)
        if completed and _post_ledger_failures_remaining:
            _post_ledger_failures_remaining -= 1
            write_event('worker', {'event': 'intentional_post_ledger_failure'})
            raise RuntimeError('controlled Sync failure after durable ledger completion')
        return completed

    # Replace only external/provider leaves.  The decoder, staging/download,
    # task route, fair-use policy/metering, Redis locks, ledger, and lifecycle
    # owner remain production code.
    sync_pipeline.vad_is_empty = _local_vad
    sync_pipeline.get_prerecorded_service = lambda _language='en': ('parakeet', 'en', 'parakeet')
    sync_pipeline.prerecorded = _local_prerecorded
    sync_pipeline._download_audio_bytes = read_signed_url
    sync_pipeline.process_conversation = _local_process_conversation
    sync_pipeline.mark_sync_content_completed = _mark_sync_content_completed_with_controlled_failure
    sync_router._run_full_pipeline_background_async = _run_full_pipeline_with_controlled_worker_failure
    sync_router._delete_staged_blobs_async = _delete_staged_blobs_with_controlled_failure
