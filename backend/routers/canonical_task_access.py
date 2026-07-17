"""Shared FastAPI dependency for canonical task-system routes."""

from fastapi import Depends, HTTPException, status

from config.canonical_memory_cohort import is_canonical_memory_user
from utils.other import endpoints as auth


def require_canonical_task_user(uid: str = Depends(auth.get_current_user_uid)) -> str:
    """Authorize task-system access exclusively through canonical membership.

    Task workflow controls supply generation fences after this check; they must
    not select the product surface. Keeping the entitlement at router entry
    also prevents non-enrolled users from reaching canonical stores.
    """

    if not is_canonical_memory_user(uid):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Not found')
    return uid


__all__ = ['require_canonical_task_user']
