"""Call-time directory enrollment controls; off creates no serving resources."""

import math
import os

MODES = ('off', 'new_owners')


def mode() -> str:
    value = os.getenv('DIRECTORY_ROUTING_MODE', 'off')
    if value not in MODES:
        raise ValueError(f'DIRECTORY_ROUTING_MODE must be one of {MODES}')
    return value


def routing_active() -> bool:
    return mode() != 'off'


def _bounded(name: str, default: float, upper: float) -> float:
    value = float(os.getenv(name, str(default)))
    if not math.isfinite(value):
        raise ValueError(f'{name} must be finite')
    return max(0.0, min(upper, value))


def new_owner_percent_env() -> float:
    return _bounded('DIRECTORY_ROUTING_NEW_OWNER_PERCENT', 0.0, 100.0)


def directory_pool_size() -> int:
    return max(1, min(2, int(os.getenv('DIRECTORY_PG_POOL_SIZE', '2'))))


def cell_pool_size() -> int:
    return max(1, min(2, int(os.getenv('CELLS_PG_POOL_SIZE', '2'))))


def wipe_writer_drain_seconds() -> float:
    return _bounded('CELL_WIPE_WRITER_DRAIN_SECONDS', 5.0, 60.0)
