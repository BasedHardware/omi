"""Kill switch for planned idle-boundary live STT cost reselection."""

import os


def idle_reopen_cost_reselect_enabled() -> bool:
    return os.getenv('STT_IDLE_REOPEN_COST_RESELECT_ENABLED', 'true').strip().lower() not in {
        '0',
        'false',
        'off',
        'no',
        'disabled',
    }
