"""Call-time directory controls; erasure depends on bindings, serving on routing mode."""

import math
import os

MODES = ('off', 'new_owners')


def mode() -> str:
    value = os.getenv('DIRECTORY_ROUTING_MODE', 'off')
    if value not in MODES:
        raise ValueError(f'DIRECTORY_ROUTING_MODE must be one of {MODES}')
    return value


def routing_off() -> bool:
    """Synchronous auth bypass; other values are validated at the transport boundary."""
    return os.getenv('DIRECTORY_ROUTING_MODE', 'off') == 'off'


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


def directory_configured() -> bool:
    """Erasure is independent of routing, including partially configured bindings."""
    return any(
        os.getenv(name, '').strip()
        for name in ('DIRECTORY_PG_DSN', 'DIRECTORY_PG_HOST', 'DIRECTORY_PG_DATABASE', 'DIRECTORY_PG_USER')
    )


def cell_wipe_enabled() -> bool:
    """Separate destructive-operation kill switch; routing alone never enables wipe."""
    return os.getenv('CELL_DIRECTORY_WIPE_ENABLED', 'false').strip().lower() in {'true', '1', 'on', 'yes'}
