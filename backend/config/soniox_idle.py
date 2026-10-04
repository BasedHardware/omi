"""Soniox paid idle transport lifetime; zero preserves the existing wire path."""

import math
import os


def idle_close_seconds() -> float:
    try:
        value = float(os.getenv('SONIOX_IDLE_CLOSE_SECONDS', '0'))
    except ValueError:
        return 0.0
    return value if math.isfinite(value) and value > 0 else 0.0
