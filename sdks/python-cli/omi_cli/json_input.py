"""Decode user-provided JSON that the HTTP serializer can encode."""

from __future__ import annotations

import json
import math
from typing import Any, NoReturn


def _reject_constant(value: str) -> NoReturn:
    raise ValueError(f"JSON numbers must be finite; got {value}")


def _finite_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("JSON number is outside the supported finite range")
    return number


def load_json_input(value: str | bytes) -> Any:
    """Reject non-finite numbers and strings that cannot be encoded as UTF-8.

    JSON strings are unchanged, and bytes retain json.loads' encoding detection.
    Invalid input raises ValueError (including JSONDecodeError and UnicodeError).
    """
    parsed = json.loads(value, parse_constant=_reject_constant, parse_float=_finite_float)
    pending = [parsed]
    while pending:
        item = pending.pop()
        if isinstance(item, str):
            item.encode("utf-8")
        elif isinstance(item, list):
            pending.extend(item)
        elif isinstance(item, dict):
            pending.extend(item)
            pending.extend(item.values())
    return parsed
