"""Role-configured ASGI entrypoint for the local Sync Cloud Tasks gauntlet.

The admission process keeps the real public Sync route and production task
protobuf construction.  The worker process keeps the protected worker route,
lease/ledger transitions, and provider-independent leaves.  They share only
isolated Redis, Firestore, and filesystem-backed staged blobs.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from google.oauth2 import id_token
from fastapi import Header, HTTPException, Request, Response

# Install the no-egress guard before backend imports can instantiate a provider.
from .isolation import LOOPBACK_HOSTS as _LOOPBACK_HOSTS, install_no_egress_guard

install_no_egress_guard()

from .events import write_event  # noqa: E402
from .storage import configure_storage_dir, patch_google_storage  # noqa: E402

_ROLES = frozenset({'admission', 'batch-serving'})


def _role() -> str:
    value = os.getenv('OMI_SYNC_STACK_ROLE', '')
    if value not in _ROLES:
        raise RuntimeError('OMI_SYNC_STACK_ROLE must be admission or batch-serving')
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
                'serving',
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
