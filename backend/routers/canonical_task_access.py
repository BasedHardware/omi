"""Shared FastAPI dependency for the universal task-system routes."""

from fastapi import Depends

from utils.other import endpoints as auth


def require_canonical_task_user(uid: str = Depends(auth.get_current_user_uid)) -> str:
    """Authorize task-system access by authenticated ownership only.

    Generation, idempotency, ownership, device, and malformed-control fences
    remain at each store boundary. Memory enrollment is not an entitlement.
    The function keeps its released name as a compatibility import for routes
    and clients while no longer selecting a memory rollout group.
    """

    return uid


__all__ = ['require_canonical_task_user']
