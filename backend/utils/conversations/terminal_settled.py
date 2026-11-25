"""The settled timestamp every writer stamps when it moves a conversation to completed.

``terminal_family_at`` was only written by the terminal-family claim, so rows that
settled through any other writer (capture close, failure terminals, v3 settles)
carried no settle time. Each such writer runs its patch through ``stamp`` so the
field is present on every completed row. It records when the row settled, not when
its summary became ready: a capture-close writer settles before transcription.

Only the timestamp is written. The family itself stays owned by the claim, so no
writer can invent ``success`` over a failure family.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping, MutableMapping, TypeVar

from config.refactor_modes import default_on, serving_for

FIELD = 'terminal_family_at'
MODE = 'CONVERSATION_TERMINAL_FAMILY_MODE'

Patch = TypeVar('Patch', bound=MutableMapping[str, Any])


def serving(uid: str) -> bool:
    """The terminal-family kill switch; the on|off surface maps to the shared serve mode."""
    return default_on(MODE) and serving_for(MODE, uid, default='serve')


def settle(current: Mapping[str, Any], *, now: datetime, enabled: bool) -> dict[str, datetime]:
    """Fields a write that moves ``current`` onto completed adds; splat into a literal payload.

    Pure: the caller reads the clock and the kill switch. A row that is already
    completed, or already stamped, gets nothing, so replays never move the time.
    """
    if enabled and current.get('status') != 'completed' and not current.get(FIELD):
        return {FIELD: now}
    return {}


def stamp(current: Mapping[str, Any], updates: Patch, *, now: datetime, enabled: bool) -> Patch:
    """``settle`` for a built payload: stamps ``updates`` in place when it moves the row onto completed."""
    if updates.get('status') == 'completed' and not updates.get(FIELD):
        updates.update(settle(current, now=now, enabled=enabled))
    return updates
