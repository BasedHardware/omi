"""Process controls for the sweeper host; never overrides admitted job policy."""

import os
import math


def budget_seconds() -> float:
    value = float(os.getenv('RECORD_SEAL_SWEEPER_BUDGET_SECONDS', '150'))
    if not math.isfinite(value) or not 1 <= value <= 180:
        raise ValueError('invalid sweep budget')
    return value


def limits() -> tuple[int, int]:
    discovery = int(os.getenv('RECORD_SEAL_SWEEPER_DISCOVERY_LIMIT', '32'))
    seals = int(os.getenv('RECORD_SEAL_SWEEPER_SEAL_LIMIT', '4'))
    if not 1 <= discovery <= 128 or not 1 <= seals <= 64:
        raise ValueError('invalid sweep limits')
    return discovery, seals


def enabled() -> bool:
    return os.getenv('RECORD_SEAL_SWEEPER_ENABLED', 'true').strip().lower() == 'true'


def mode() -> str:
    value = os.getenv('RECORD_SEAL_SWEEPER_MODE', 'apply')
    if value not in {'plan', 'apply'}:
        raise ValueError('invalid sweep mode')
    return value


def require_production_runtime() -> None:
    if os.getenv('FIRESTORE_EMULATOR_HOST') or os.getenv('OMI_ENV_STAGE') != 'prod':
        raise ValueError('production in-cluster runtime required')
