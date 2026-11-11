"""Cell-store rollout declaration. Serving wiring belongs to the enrollment lane."""

import os

MODES = ('off', 'shadow', 'primary')


def mode() -> str:
    value = os.getenv('CELL_STORE_MODE', 'off')
    if value not in MODES:
        raise ValueError(f'CELL_STORE_MODE must be one of {MODES}')
    return value
