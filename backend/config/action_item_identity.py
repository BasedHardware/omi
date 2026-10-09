"""Kill switches for keeping task identity across a conversation's action-item replace.

``ACTION_ITEM_IDENTITY_PRESERVE_ENABLED`` unset or blank means on. ``false``/``off``/``0``
is the kill switch, and any unrecognized value also means off, so a mistyped kill
switch can never leave the feature running. Off restores the previous replace exactly:
every task is recreated under a fresh id and offered to the user's task app again.

``ACTION_ITEM_IDENTITY_ANCHOR_SHADOW_ENABLED`` follows the same parse. It gates only the
measurement-only anchor shadow (log fields); it never changes what the replace writes.
Off also drops the one extra field the shadow adds to the prior-row read.

Pure module: stdlib only, the flags are read at the call boundary, never at import.
"""

from __future__ import annotations

import os

ACTION_ITEM_IDENTITY_PRESERVE_ENV = 'ACTION_ITEM_IDENTITY_PRESERVE_ENABLED'
ACTION_ITEM_IDENTITY_ANCHOR_SHADOW_ENV = 'ACTION_ITEM_IDENTITY_ANCHOR_SHADOW_ENABLED'

_ON_VALUES = frozenset({'1', 'true', 'on', 'yes', 'enabled'})


def _default_on(name: str) -> bool:
    """Unset or blank is on; only an explicit on-token keeps it on when set."""
    raw = os.getenv(name, '').strip().lower()
    return not raw or raw in _ON_VALUES


def action_item_identity_preserve_enabled() -> bool:
    return _default_on(ACTION_ITEM_IDENTITY_PRESERVE_ENV)


def action_item_identity_anchor_shadow_enabled() -> bool:
    return _default_on(ACTION_ITEM_IDENTITY_ANCHOR_SHADOW_ENV)


ACTION_ITEM_REFRESH_PRESERVE_ENV = 'ACTION_ITEM_REFRESH_PRESERVE_ENABLED'


def action_item_refresh_preserve_enabled() -> bool:
    """Preserve tasks on automatic refresh only; unset/blank on, unknown off."""
    return _default_on(ACTION_ITEM_REFRESH_PRESERVE_ENV)
