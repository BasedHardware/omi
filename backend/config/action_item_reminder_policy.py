"""Canonical task lifecycle admission for existing reminder transports."""

from typing import Any, Optional

from models.action_item import TaskStatus


def action_item_reminder_lifecycle_allows_delivery(
    *, completed: bool, status: Optional[str] = None, deleted: bool = False
) -> bool:
    """Missing status keeps legacy behavior; explicit non-active state never arms.

    Canonical cancelled/superseded tasks have completed=False, so completion is
    not a substitute for lifecycle. Unknown explicit states fail closed too.
    """
    return not completed and not deleted and (status is None or status == TaskStatus.active)


def should_schedule_action_item_reminder(
    *, completed: bool, due_at: Any, status: Optional[str] = None, deleted: bool = False
) -> bool:
    return bool(due_at) and action_item_reminder_lifecycle_allows_delivery(
        completed=completed, status=status, deleted=deleted
    )
