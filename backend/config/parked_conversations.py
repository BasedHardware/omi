"""Roll back new parked-status writes without changing first-open admission."""

import os


def parked_terminal_status_enabled() -> bool:
    return os.getenv('CONVERSATION_PARKED_TERMINAL_STATUS_ENABLED', 'true').strip().lower() not in {
        'false',
        'off',
        '0',
        'no',
    }
