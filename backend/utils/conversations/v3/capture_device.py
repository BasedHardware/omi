"""Reliability experiment ``end_button_by_device``: which app install sent an open conversation's latest speech.

Every recording carries ``client_device_id`` (``{platform}_{hash}``, utils/client_device.py), written by the
listening session and by every upload. The builder copies the one behind the latest speech line onto the
open conversation, and the live read serves it to the owner, so the app can tell that the conversation on
screen is fed by this phone without depending on its listening connection. Pure: no switch reads, no IO.
"""

import re
from collections.abc import Mapping, MutableMapping, Sequence
from typing import Any, Optional

FIELD = 'v3_capture_device_id'

_SHAPE = re.compile(r'(android|ios|linux|macos|web|windows)_[0-9a-f]{8}')


def _valid(value: Any) -> Optional[str]:
    return value if isinstance(value, str) and _SHAPE.fullmatch(value) else None


def latest(lines: Sequence[Mapping[str, Any]], recordings: Mapping[str, Mapping[str, Any]]) -> Optional[str]:
    """The device of the recording that carries the line ending last, or None when it names none."""
    if not lines:
        return None
    last = max(lines, key=lambda line: line['end'])
    return _valid((recordings.get(last['conversation_id']) or {}).get('client_device_id'))


def stamp(
    row: MutableMapping[str, Any], lines: Sequence[Mapping[str, Any]], recordings: Mapping[str, Mapping[str, Any]]
) -> None:
    """Set the field on a conversation row, or clear a stale one when the latest speech names no device."""
    device = latest(lines, recordings)
    if device:
        row[FIELD] = device
    else:
        row.pop(FIELD, None)


def served(row: Mapping[str, Any]) -> Optional[str]:
    """The stored value when it has the device-id shape; anything else is not served."""
    return _valid(row.get(FIELD))
