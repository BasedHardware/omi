"""Kill switch for keeping task identity across a conversation's action-item replace.

``ACTION_ITEM_IDENTITY_PRESERVE_ENABLED`` unset or blank means on. ``false``/``off``/``0``
is the kill switch, and any unrecognized value also means off, so a mistyped kill
switch can never leave the feature running. Off restores the previous replace exactly:
every task is recreated under a fresh id and offered to the user's task app again.

Pure module: stdlib only, the flag is read at the call boundary, never at import.
"""

from __future__ import annotations

import os

ACTION_ITEM_IDENTITY_PRESERVE_ENV = 'ACTION_ITEM_IDENTITY_PRESERVE_ENABLED'

_ON_VALUES = frozenset({'1', 'true', 'on', 'yes', 'enabled'})


def action_item_identity_preserve_enabled() -> bool:
    """Unset or blank is on; only an explicit on-token keeps it on when set."""
    raw = os.getenv(ACTION_ITEM_IDENTITY_PRESERVE_ENV, '').strip().lower()
    return not raw or raw in _ON_VALUES
