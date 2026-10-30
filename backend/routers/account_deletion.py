"""Owner-facing account deletion and restore endpoints."""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from services.users.account_deletion import account_deletion_status, restore_account_deletion, start_account_deletion
from utils.log_sanitizer import sanitize
from utils.other import endpoints as auth

logger = logging.getLogger(__name__)
router = APIRouter()


class DeleteAccountRequest(BaseModel):
    reason: Optional[str] = None
    reason_details: Optional[str] = None
    erase_now: bool = False


class AccountDeletionLossSummary(BaseModel):
    held_recordings: int = 0
    held_audio_seconds: int = 0
    backlog_conversations: int = 0
    backlog_seconds: int = 0


class AccountDeletionStatusResponse(BaseModel):
    status: Optional[str] = None
    pending_deletion: bool = False
    wipe_at: Optional[datetime] = None
    grace_period_days: int = 0
    loss_summary: AccountDeletionLossSummary


class AccountDeletionActionResponse(BaseModel):
    status: str
    message: str
    pending_deletion: bool = False
    wipe_at: Optional[datetime] = None


class AccountDeletionRestoreResponse(BaseModel):
    status: str
    restored: bool
    billing_cancelled: bool = False


@router.delete('/v1/users/delete-account', tags=['v1'], response_model=AccountDeletionActionResponse)
def delete_account(
    request: DeleteAccountRequest = DeleteAccountRequest(),
    grace: bool = False,
    uid: str = Depends(auth.get_current_user_uid_for_deletion_status),
):
    # This recovery-auth route is open for status and restore operations, and
    # accepts erase-now only while the marker is still in its restorable grace
    # state. Once an immediate wipe has been queued or claimed, ordinary
    # deletion auth fencing applies again.
    auth.enforce_account_deletion_http_access(uid, allow_grace_erase_now=request.erase_now)
    try:
        return start_account_deletion(
            uid,
            reason=request.reason,
            reason_details=request.reason_details,
            grace=grace,
            erase_now=request.erase_now,
        )
    except Exception as error:
        logger.info('delete_account %s', sanitize(str(error)))
        raise HTTPException(status_code=500, detail='Could not delete account. Please try again.')


@router.get('/v1/users/deletion-status', tags=['v1'], response_model=AccountDeletionStatusResponse)
def get_account_deletion_status_endpoint(
    uid: str = Depends(auth.get_current_user_uid_for_deletion_status),
):
    """Status plus metadata counts used by the account-deletion warning screen."""
    try:
        return account_deletion_status(uid)
    except Exception as error:
        logger.info('account deletion status read failed: %s', sanitize(str(error)))
        raise HTTPException(status_code=503, detail='Could not read account deletion status. Please retry.')


@router.post('/v1/users/restore-account', tags=['v1'], response_model=AccountDeletionRestoreResponse)
def restore_account_deletion_endpoint(
    uid: str = Depends(auth.get_current_user_uid_for_deletion_status),
):
    """Cancel a pending grace wipe while the deadline remains in the future."""
    try:
        result = restore_account_deletion(uid)
    except Exception as error:
        logger.info('account deletion restore failed: %s', sanitize(str(error)))
        raise HTTPException(status_code=503, detail='Could not restore account. Please retry.')
    if result.get('restored') is not True:
        raise HTTPException(
            status_code=409, detail={'code': 'account_deletion_not_restorable', 'status': result['status']}
        )
    return result
