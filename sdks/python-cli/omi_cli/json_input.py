"""Decode user-provided JSON without numbers the HTTP serializer cannot send."""

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
    """Reject NaN, infinities, and exponents that overflow Python's float range.

    JSON strings are unchanged, and bytes retain json.loads' encoding detection.
    Invalid input raises ValueError (including JSONDecodeError).
    """
    return json.loads(value, parse_constant=_reject_constant, parse_float=_finite_float)
