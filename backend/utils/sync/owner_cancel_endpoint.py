"""``DELETE /v2/sync-local-files/{job_id}``: the owner deletes an uploaded recording that has not
been transcribed, and its server copy is erased. Mounted by ``routers.sync``; the fence and
erasure live in ``utils.batch_pipeline.owner_cancel``.
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from config import sync_owner_cancel
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from database.batch_pipeline_shadow_hook import shadow_from_env
from database.batch_pipeline_store import FirestoreStore
from database.legal_holds import destructive_operation_gate
from models.sync_job_status import SyncJobCancelResponse
from utils.batch_pipeline import owner_cancel
from utils.batch_pipeline.intake import privacy_blocked_response
from utils.other import endpoints as auth
from utils.sync.poll_limit import SYNC_POLL_WINDOW_SECONDS, admit_sync_job_poll
from utils.sync.stage import current_stage

router = APIRouter()


# Erasure and the legacy cap-hold store load on first use: routers.sync imports this module, and
# its import-isolated test harnesses stub the storage and Firestore packages they pull in.
def FirestoreEraser(namespace: str):  # noqa: N802 - stands in for the class at its call site
    from utils.batch_pipeline.owner_cancel_erase import FirestoreEraser as eraser

    return eraser(namespace)


def FirestoreLegacyStore():  # noqa: N802
    from utils.sync.owner_cancel_legacy import FirestoreLegacyStore as store

    return store()


# A same-account deletion holding the gate is short; the phone retries a busy answer from its tombstone.
OWNER_CANCEL_GATE_WAIT_SECONDS = 5.0
_GATE_ERRORS = frozenset(
    {'DestructiveGateTakeover', 'DestructiveOperationInProgress', 'LegalHoldActive', 'LegalHoldAuthorityUnavailable'}
)


def _refusal(status_code: int, code: str, message: str, retry_after: int | None = None) -> JSONResponse:
    """``detail`` carries the bounded machine code the app's typed client reads."""
    headers = {'Retry-After': str(retry_after)} if retry_after else None
    return JSONResponse(
        status_code=status_code, headers=headers, content={'code': code, 'detail': code, 'message': message}
    )


def _disabled() -> JSONResponse:
    return _refusal(503, 'sync_job_cancel_disabled', 'Deleting server copies is paused; retry later', 3600)


@router.delete('/v2/sync-local-files/{job_id}', response_model=SyncJobCancelResponse, response_model_exclude_none=True)
def cancel_sync_upload(job_id: str, uid: str = Depends(auth.get_current_user_uid)):
    """Owner deletes an uploaded recording that has not been transcribed; its server copy is erased.

    Batch (``bp_``) uploads and legacy uploads held in cap holds are both covered. Idempotent. Wrong-owner, unknown and legacy handles share the ``not_found``
    answer. Work that a worker is computing, merging or projecting answers 409
    ``sync_job_processing`` (retry later); a committed transcript is never
    deleted here and answers ``already_processed`` with its conversations.
    Runs under the account destructive-operation gate, so a legal hold refuses it.
    """
    if not admit_sync_job_poll(uid):
        raise HTTPException(
            status_code=429,
            detail='Sync job polling too frequent; retry later',
            headers={'Retry-After': str(SYNC_POLL_WINDOW_SECONDS)},
        )
    if not sync_owner_cancel.enabled():
        return _disabled()
    namespace = f'batch_pipeline_{current_stage()}'
    try:
        with destructive_operation_gate(
            uid, kind='audio_conversation_deletion', wait_seconds=OWNER_CANCEL_GATE_WAIT_SECONDS
        ):
            result = owner_cancel.cancel_owner_upload(
                uid,
                job_id,
                store=shadow_from_env(FirestoreStore(namespace)),
                eraser=FirestoreEraser(namespace),
                legacy=FirestoreLegacyStore(),
            )
    except owner_cancel.CancelDisabled:
        return _disabled()
    except BatchPrivacyBlocked:
        return privacy_blocked_response()
    except RuntimeError as error:
        if type(error).__name__ not in _GATE_ERRORS:
            raise
        from utils.other.account_gate_http import account_gate_busy_http_exception

        raise account_gate_busy_http_exception() from error
    if result.outcome is owner_cancel.Outcome.IN_PROGRESS:
        return _refusal(409, 'sync_job_processing', 'The recording is being processed; retry later', 300)
    if result.outcome is owner_cancel.Outcome.NOT_CANCELLABLE:
        message = 'This upload will be processed; delete its conversation afterwards'
        return _refusal(409, 'sync_job_not_cancellable', message)
    return {
        'job_id': job_id,
        'outcome': result.outcome.value,
        'erasure': result.erasure,
        'conversation_ids': list(result.conversation_ids),
    }
