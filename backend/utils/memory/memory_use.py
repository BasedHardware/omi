"""Owner feedback for how a canonical memory should be used.

This module is deliberately pure.  The canonical memory adapter owns the
transaction, operation journal, and source/deletion fences; this module only
validates the small action contract and builds the additive argument patch.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Mapping, Optional

from models.product_memory import MemoryItem

MAX_FEEDBACK_ID_LENGTH = 128


class MemoryUseAction(str, Enum):
    suppress = "suppress"
    allow = "allow"
    useful = "useful"


class MemoryUseConflict(ValueError):
    """The durable feedback id was reused for a different owner action."""


@dataclass(frozen=True)
class MemoryUsePatch:
    """Canonical mutation inputs for one owner feedback action."""

    action: MemoryUseAction
    feedback_id: str
    expected_item_revision: Optional[int]
    arguments: dict[str, Any]
    curation_weight: int


def feedback_value(action: MemoryUseAction | str) -> int:
    """Map an owner use action to the unified feedback ledger value."""

    resolved = normalize_action(action)
    return {MemoryUseAction.suppress: -1, MemoryUseAction.allow: 0, MemoryUseAction.useful: 1}[resolved]


def feedback_reason(action: MemoryUseAction | str) -> Optional[str]:
    """Return the normalized feedback reason for the negative action only."""

    return "not_useful" if normalize_action(action) == MemoryUseAction.suppress else None


def normalize_feedback_id(value: Any) -> str:
    """Validate and normalize the content-free retry receipt identifier."""

    if not isinstance(value, str):
        raise ValueError("feedback_id must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError("feedback_id must not be blank")
    if len(normalized) > MAX_FEEDBACK_ID_LENGTH:
        raise ValueError(f"feedback_id must be at most {MAX_FEEDBACK_ID_LENGTH} characters")
    return normalized


def normalize_action(value: MemoryUseAction | str) -> MemoryUseAction:
    try:
        return value if isinstance(value, MemoryUseAction) else MemoryUseAction(value.strip().lower())
    except (AttributeError, ValueError) as exc:
        raise ValueError("action must be suppress, allow, or useful") from exc


def _existing_memory_use(item: MemoryItem) -> Mapping[str, Any]:
    value = item.arguments.get("memory_use")
    return value if isinstance(value, Mapping) else {}


def _copy_arguments(item: MemoryItem) -> dict[str, Any]:
    # The canonical patch model validates JSON-shaped arguments.  Copy the
    # outer bag so this helper never mutates the authoritative read snapshot.
    return {key: value for key, value in item.arguments.items()}


def build_memory_use_patch(
    item: MemoryItem,
    *,
    action: MemoryUseAction | str,
    feedback_id: str,
    expected_item_revision: Optional[int] = None,
    now: Optional[datetime] = None,
) -> MemoryUsePatch:
    """Build an additive owner-use state patch.

    ``suppress`` is the only action that suppresses default use.  ``allow`` is
    the explicit re-enable action; ``useful`` deliberately preserves an
    existing suppression so a positive signal cannot accidentally undo a
    prior owner veto.  The timestamp is accepted for callers that want a
    response/audit value, but is not stored in the patch identity: the item
    revision and operation journal are the durable retry authority.
    """

    resolved_action = normalize_action(action)
    normalized_feedback_id = normalize_feedback_id(feedback_id)
    if expected_item_revision is not None and expected_item_revision < 1:
        raise ValueError("expected_item_revision must be positive")

    existing_use = _existing_memory_use(item)
    existing_feedback_id = existing_use.get("feedback_id")
    existing_action = existing_use.get("last_action")
    if existing_feedback_id == normalized_feedback_id and existing_action != resolved_action.value:
        raise MemoryUseConflict("feedback_id was already used for a different action")

    suppressed = resolved_action == MemoryUseAction.suppress
    if resolved_action == MemoryUseAction.useful:
        suppressed = bool(existing_use.get("suppressed", False))

    state = "suppressed" if suppressed else ("useful" if resolved_action == MemoryUseAction.useful else "allowed")
    next_use: dict[str, Any] = {
        "state": state,
        "suppressed": suppressed,
        "last_action": resolved_action.value,
        "feedback_id": normalized_feedback_id,
    }
    # ``now`` is intentionally not stored in the argument bag.  Item
    # ``updated_at`` and the unified feedback event carry server time; keeping
    # a timestamp here would make a retry's patch identity unstable.
    _ = now

    arguments = _copy_arguments(item)
    arguments["memory_use"] = next_use
    curation_weight = item.curation_weight
    if resolved_action == MemoryUseAction.useful:
        curation_weight = max(curation_weight, 1)

    return MemoryUsePatch(
        action=resolved_action,
        feedback_id=normalized_feedback_id,
        expected_item_revision=expected_item_revision,
        arguments=arguments,
        curation_weight=curation_weight,
    )


__all__ = [
    "MAX_FEEDBACK_ID_LENGTH",
    "MemoryUseAction",
    "MemoryUseConflict",
    "MemoryUsePatch",
    "build_memory_use_patch",
    "feedback_reason",
    "feedback_value",
    "normalize_action",
    "normalize_feedback_id",
]
