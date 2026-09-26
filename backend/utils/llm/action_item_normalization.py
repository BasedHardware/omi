"""Deterministic normalization shared by action-item extraction routes."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, List

from models.structured import ActionItem  # type: ignore[reportAttributeAccessIssue]  # SDK/fallback export is runtime-complete.

logger = logging.getLogger(__name__)


def normalize_action_item_due_dates(
    action_items: List[ActionItem],
    *,
    user_tz: Any,
    now: datetime,
    log_past_due_clears: bool,
) -> List[ActionItem]:
    for action_item in action_items:
        if action_item.due_at is None:
            continue
        if action_item.due_at.tzinfo is None:
            action_item.due_at = action_item.due_at.replace(tzinfo=user_tz).astimezone(timezone.utc)
        else:
            action_item.due_at = action_item.due_at.astimezone(timezone.utc)
        if action_item.due_at < now - timedelta(days=1):
            if log_past_due_clears:
                logger.warning(
                    f'Clearing past due_at {action_item.due_at.isoformat()} for action item: {action_item.description}'
                )
            action_item.due_at = None
    return action_items
