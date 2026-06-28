"""Shared write orchestration for the MCP goals surface.

Both the REST endpoints (``routers/mcp.py``) and the MCP tools
(``routers/mcp_sse.py``) drive goal create/update/progress/delete through these
helpers so the two transports cannot drift in behavior. Lives in ``utils`` so
neither router imports the other (routers must never import from other routers).

Goals are measurable, long-horizon objectives (a ``target_value`` the user works
toward, with ``current_value`` progress and history), so this completes the MCP
write surface alongside memories and action items: an assistant can set a goal
the user mentions, log progress against it, and clean up stale goals.
"""

import logging
from typing import List, Optional, Union

import database.goals as goals_db
from utils.mcp_data import clean_goal

logger = logging.getLogger(__name__)

MAX_TITLE_CHARS = 200
_GOAL_TYPES = ('boolean', 'scale', 'numeric')


class GoalError(Exception):
    """Base class for goal write failures the routers map to transport codes."""


class GoalNotFound(GoalError):
    """No goal with that id exists for this user."""


def _normalize_title(title: Optional[str]) -> str:
    if title is None:
        raise ValueError("title is required")
    text = title.strip()
    if not text:
        raise ValueError("title cannot be empty")
    if len(text) > MAX_TITLE_CHARS:
        raise ValueError(f"title is too long (max {MAX_TITLE_CHARS} characters)")
    return text


def _as_number(value: Union[int, float, str], field: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field} must be a number")


def create_goal(
    uid: str,
    title: str,
    target_value: Union[int, float, str],
    goal_type: str = 'scale',
    current_value: Union[int, float, str] = 0,
    min_value: Union[int, float, str] = 0,
    max_value: Union[int, float, str] = 10,
    unit: Optional[str] = None,
) -> dict:
    """Create a goal and return its cleaned MCP shape. Omi keeps at most a few
    active goals; the database deactivates the oldest when the cap is reached."""
    text = _normalize_title(title)
    if goal_type not in _GOAL_TYPES:
        raise ValueError(f"goal_type must be one of: {', '.join(_GOAL_TYPES)}")
    goal_data = {
        'title': text,
        'goal_type': goal_type,
        'target_value': _as_number(target_value, 'target_value'),
        'current_value': _as_number(current_value, 'current_value'),
        'min_value': _as_number(min_value, 'min_value'),
        'max_value': _as_number(max_value, 'max_value'),
        'unit': unit,
    }
    return clean_goal(goals_db.create_goal(uid, goal_data))


def update_goal(
    uid: str,
    goal_id: str,
    title: Optional[str] = None,
    target_value: Union[int, float, str, None] = None,
    current_value: Union[int, float, str, None] = None,
    unit: Optional[str] = None,
    min_value: Union[int, float, str, None] = None,
    max_value: Union[int, float, str, None] = None,
) -> dict:
    """Update a goal's definition. Only the fields provided are changed."""
    updates: dict = {}
    if title is not None:
        updates['title'] = _normalize_title(title)
    if target_value is not None:
        updates['target_value'] = _as_number(target_value, 'target_value')
    if current_value is not None:
        updates['current_value'] = _as_number(current_value, 'current_value')
    if unit is not None:
        updates['unit'] = unit
    if min_value is not None:
        updates['min_value'] = _as_number(min_value, 'min_value')
    if max_value is not None:
        updates['max_value'] = _as_number(max_value, 'max_value')
    if not updates:
        raise ValueError("Provide at least one field to update")

    goal = goals_db.update_goal(uid, goal_id, updates)
    if goal is None:
        raise GoalNotFound("Goal not found")
    return clean_goal(goal)


def update_goal_progress(uid: str, goal_id: str, current_value: Union[int, float, str]) -> dict:
    """Log progress against a goal (also recorded to its history)."""
    value = _as_number(current_value, 'current_value')
    goal = goals_db.update_goal_progress(uid, goal_id, value)
    if goal is None:
        raise GoalNotFound("Goal not found")
    return clean_goal(goal)


def delete_goal(uid: str, goal_id: str) -> None:
    """Delete a goal."""
    if not goals_db.delete_goal(uid, goal_id):
        raise GoalNotFound("Goal not found")


def get_goal_history(uid: str, goal_id: str, days: int = 30) -> List[dict]:
    """Return a goal's recorded progress points over the last ``days`` days."""
    try:
        days = int(days)
    except (TypeError, ValueError):
        raise ValueError("days must be an integer")
    days = max(1, min(days, 365))
    return goals_db.get_goal_history(uid, goal_id, days=days)
