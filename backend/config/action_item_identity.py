"""Kill switches for keeping task identity across a conversation's action-item replace.

``ACTION_ITEM_IDENTITY_PRESERVE_ENABLED`` unset or blank means on. ``false``/``off``/``0``
is the kill switch, and any unrecognized value also means off, so a mistyped kill
switch can never leave the feature running. Off restores the previous replace exactly:
every task is recreated under a fresh id and offered to the user's task app again.

Pure module: stdlib only, the flags are read at the call boundary, never at import.
"""

from __future__ import annotations

import os

from config.refactor_switches import default_on as rollout_default_on

ACTION_ITEM_IDENTITY_PRESERVE_ENV = 'ACTION_ITEM_IDENTITY_PRESERVE_ENABLED'

_ON_VALUES = frozenset({'1', 'true', 'on', 'yes', 'enabled'})


def _default_on(name: str) -> bool:
    """Unset or blank is on; only an explicit on-token keeps it on when set."""
    raw = os.getenv(name, '').strip().lower()
    return rollout_default_on(name, not raw or raw in _ON_VALUES)


def action_item_identity_preserve_enabled() -> bool:
    return _default_on(ACTION_ITEM_IDENTITY_PRESERVE_ENV)


ACTION_ITEM_REFRESH_PRESERVE_ENV = 'ACTION_ITEM_REFRESH_PRESERVE_ENABLED'


def action_item_refresh_preserve_enabled() -> bool:
    """Preserve tasks on automatic refresh only; unset/blank on, unknown off."""
    return _default_on(ACTION_ITEM_REFRESH_PRESERVE_ENV)
