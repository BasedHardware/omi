"""Hard-scope chat retrieval to a conversation and/or timeframe (#4515).

PageContext used to be a soft prompt hint only. When the client sends a conversation
id and/or start/end dates, tools must fail-closed so answers cannot escape that window.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional, Tuple

from models.chat import PageContext


def build_chat_scope(context: Optional[PageContext]) -> Optional[Dict[str, Any]]:
    """Return a tool-facing scope dict, or None when the client did not request hard scope."""
    if context is None:
        return None

    scope: Dict[str, Any] = {}
    ctx_id = context.id if isinstance(context.id, str) else ""
    if context.type == "conversation" and ctx_id.strip():
        scope["conversation_id"] = ctx_id.strip()
    start_date = context.start_date if isinstance(context.start_date, str) else ""
    end_date = context.end_date if isinstance(context.end_date, str) else ""
    if start_date.strip():
        scope["start_date"] = start_date.strip()
    if end_date.strip():
        scope["end_date"] = end_date.strip()

    return scope or None


def _parse_iso_dt(value: Optional[str]) -> Tuple[Optional[datetime], Optional[str]]:
    if not value:
        return None, None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as e:
        return None, f"Invalid date format: {value} ({e})"
    if dt.tzinfo is None:
        return None, (
            "Date must include timezone in YYYY-MM-DDTHH:MM:SS+HH:MM form "
            f"(e.g. '2024-01-19T15:00:00-08:00'): {value}"
        )
    return dt, None


def apply_chat_scope_dates(
    scope: Optional[Dict[str, Any]],
    start_date: Optional[str],
    end_date: Optional[str],
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Intersect tool dates with chat_scope dates.

    Returns ``(start_date, end_date, error)``. Scope wins when the tool omits a bound;
    when both are set, the intersection is used (max start, min end).
    """
    if not scope:
        return start_date, end_date, None

    scope_start = scope.get("start_date")
    scope_end = scope.get("end_date")
    if not scope_start and not scope_end:
        return start_date, end_date, None

    tool_start_dt, err = _parse_iso_dt(start_date)
    if err:
        return None, None, err
    tool_end_dt, err = _parse_iso_dt(end_date)
    if err:
        return None, None, err
    scope_start_dt, err = _parse_iso_dt(scope_start if isinstance(scope_start, str) else None)
    if err:
        return None, None, f"chat_scope start_date: {err}"
    scope_end_dt, err = _parse_iso_dt(scope_end if isinstance(scope_end, str) else None)
    if err:
        return None, None, f"chat_scope end_date: {err}"

    starts = [d for d in (tool_start_dt, scope_start_dt) if d is not None]
    ends = [d for d in (tool_end_dt, scope_end_dt) if d is not None]
    final_start = max(starts) if starts else None
    final_end = min(ends) if ends else None
    if final_start is not None and final_end is not None and final_start > final_end:
        return None, None, "Requested date range is outside the active chat timeframe scope."

    return (
        final_start.isoformat() if final_start else None,
        final_end.isoformat() if final_end else None,
        None,
    )


def chat_scope_from_config(configurable: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(configurable, dict):
        return None
    scope = configurable.get("chat_scope")
    return scope if isinstance(scope, dict) and scope else None
