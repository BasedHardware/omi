"""Shared FastAPI dependency for canonical task-system routes."""

from fastapi import Depends, HTTPException, status

from utils.other import endpoints as auth
from utils.memory.memory_system import MemorySystem, resolve_memory_system


def require_canonical_task_user(uid: str = Depends(auth.get_current_user_uid)) -> str:
    """Authorize task-system access exclusively through canonical membership.

    Task workflow controls supply generation fences after this check; they must
    not select the product surface. Keeping the entitlement at router entry
    also prevents non-enrolled users from reaching canonical stores.
    """

    if resolve_memory_system(uid) != MemorySystem.CANONICAL:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Not found')
    return uid


__all__ = ['require_canonical_task_user']
