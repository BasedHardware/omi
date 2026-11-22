"""Gate new parked-status writes while older readers qualify."""

import os


def parked_terminal_status_enabled() -> bool:
    return os.getenv('CONVERSATION_PARKED_TERMINAL_STATUS_ENABLED', '').strip().lower() in {'true', 'on', '1', 'yes'}
