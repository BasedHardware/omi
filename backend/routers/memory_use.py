"""Authenticated owner feedback for canonical memory usefulness."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator

from database._client import get_data_plane_firestore_client
from database.memory_apply_store import CanonicalMemoryIntakePausedError, MemoryFirestoreApplyError
from models.feedback import MemoryUseFeedback
from models.product_memory import MemoryItem
from utils.memory.belief_model import belief_model_enabled
from utils.memory.memory_use import (
    MAX_FEEDBACK_ID_LENGTH,
    MemoryUseAction,
    MemoryUseConflict,
    build_memory_use_patch,
)
from utils.other import endpoints as auth

router = APIRouter()


class MemoryUseRequest(BaseModel):
    """Retry-stable owner action for one canonical memory."""

    model_config = ConfigDict(extra="forbid")

    action: MemoryUseAction
    feedback_id: str = Field(min_length=1, max_length=MAX_FEEDBACK_ID_LENGTH)
    expected_item_revision: Optional[int] = Field(default=None, ge=1)

    @field_validator("feedback_id")
    @classmethod
    def validate_feedback_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("feedback_id must not be blank")
        return normalized


class MemoryUseResponse(BaseModel):
    status: str
    memory_id: str
    action: MemoryUseAction
    feedback_id: str
    item_revision: int
    suppressed: bool
    curation_weight: int


def _memory_use_state(item: MemoryItem) -> dict[str, Any]:
    value = item.arguments.get("memory_use")
    return value if isinstance(value, dict) else {}


def _apply_canonical_user_mutation(*args: Any, **kwargs: Any) -> tuple[MemoryItem, MemoryItem]:
    """Load the canonical adapter only when an authenticated write is used.

    The adapter and knowledge-ledger modules have a historical import cycle;
    keeping this route's request schema importable avoids making API contract
    validation depend on that heavy write-path import order.
    """

    from utils.memory.canonical_memory_adapter import apply_canonical_user_mutation

    return apply_canonical_user_mutation(*args, **kwargs)


@router.post(
    "/v3/memories/{memory_id}/use",
    tags=["memories"],
    response_model=MemoryUseResponse,
    response_model_exclude_none=True,
)
def use_memory(
    memory_id: str,
    request: MemoryUseRequest,
    response: Response,
    uid: str = Depends(auth.with_rate_limit(auth.get_current_user_uid, "memories:modify")),
) -> MemoryUseResponse:
    """Record an owner use decision without changing truth or currency.

    The route is additive and only available when the belief-model beta flag
    is enabled.  The canonical mutation adapter supplies authenticated owner,
    account-generation, source, deletion, and operation-journal fences.
    """

    if not belief_model_enabled():
        raise HTTPException(status_code=404, detail="memory use feedback is unavailable")
    if not memory_id.strip():
        raise HTTPException(status_code=404, detail="Memory not found")

    db_client = get_data_plane_firestore_client()
    expected_revision = request.expected_item_revision
    feedback = MemoryUseFeedback(
        uid=uid,
        feedback_id=request.feedback_id,
        target_memory_id=memory_id,
        action=request.action.value,
        created_at=datetime.now(timezone.utc),
    )

    def build_patch(item: MemoryItem, now: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        try:
            patch = build_memory_use_patch(
                item,
                action=request.action,
                feedback_id=request.feedback_id,
                expected_item_revision=expected_revision,
            )
        except MemoryUseConflict as exc:
            if "different action" in str(exc):
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            raise
        if expected_revision is not None and item.item_revision != expected_revision:
            raise HTTPException(status_code=409, detail="memory revision has changed")
        return (
            {
                "arguments": patch.arguments,
            },
            {
                "arguments": patch.arguments,
                "curation_weight": patch.curation_weight,
                "expected_item_revision": item.item_revision,
            },
        )

    try:
        previous, updated = _apply_canonical_user_mutation(
            uid,
            memory_id,
            mutation_kind=f"memory_use:{request.feedback_id}",
            build_patch=build_patch,
            memory_use_feedback=feedback,
            db_client=db_client,
        )
    except HTTPException:
        raise
    except MemoryUseConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        message = str(exc)
        if "not found" in message:
            raise HTTPException(status_code=404, detail="Memory not found") from exc
        if "revision" in message or "expected_" in message:
            raise HTTPException(status_code=409, detail="memory revision has changed") from exc
        raise HTTPException(status_code=409, detail=message) from exc
    except CanonicalMemoryIntakePausedError as exc:
        raise HTTPException(status_code=503, detail="memory feedback intake is temporarily paused") from exc
    except MemoryFirestoreApplyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    response.headers["Cache-Control"] = "no-store"
    use = _memory_use_state(updated)
    return MemoryUseResponse(
        status="ok" if updated.item_revision != previous.item_revision else "idempotent",
        memory_id=updated.memory_id,
        # The request identifiers are the durable receipt identity.  The
        # current item may contain a later owner action when an old retry is
        # replayed, so do not echo mutable ``memory_use.last_action`` here.
        action=request.action,
        feedback_id=request.feedback_id,
        item_revision=updated.item_revision,
        suppressed=bool(use.get("suppressed", False)),
        curation_weight=updated.curation_weight,
    )


__all__ = ["MemoryUseRequest", "MemoryUseResponse", "router", "use_memory"]
