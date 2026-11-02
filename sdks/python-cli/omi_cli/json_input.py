"""Decode user-provided JSON that the HTTP serializer can encode."""

from __future__ import annotations

import json
import math
from typing import Any, NoReturn

# On 3.14 json.loads accepts deeper input than json.dumps can write back out,
# so cap the depth here instead of leaning on the interpreter running out first.
MAX_NESTING_DEPTH = 500

_DEPTH_MESSAGE = "JSON nesting depth exceeds the supported limit"


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
    Invalid input raises ValueError (including JSONDecodeError, UnicodeError,
    and nesting past MAX_NESTING_DEPTH, which callers already map to UsageError
    via the ValueError contract).
    """
    try:
        parsed = json.loads(value, parse_constant=_reject_constant, parse_float=_finite_float)
    except RecursionError:
        raise ValueError(_DEPTH_MESSAGE) from None
    pending: list[tuple[Any, int]] = [(parsed, 1)]
    while pending:
        item, depth = pending.pop()
        if isinstance(item, str):
            item.encode("utf-8")
        elif isinstance(item, list):
            if depth > MAX_NESTING_DEPTH:
                raise ValueError(_DEPTH_MESSAGE)
            pending.extend((child, depth + 1) for child in item)
        elif isinstance(item, dict):
            if depth > MAX_NESTING_DEPTH:
                raise ValueError(_DEPTH_MESSAGE)
            pending.extend((key, depth) for key in item)
            pending.extend((child, depth + 1) for child in item.values())
    return parsed
