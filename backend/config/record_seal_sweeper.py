"""Process controls for the sweeper host; never overrides admitted job policy."""

import os


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
