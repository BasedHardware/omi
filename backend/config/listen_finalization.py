"""Shared durable attempt-budget policy for workers and replay admission."""

import os


def replay_enabled() -> bool:
    """Kill switch for replay only; admission keeps its dispatch-mode gate."""
    return os.getenv('LISTEN_FINALIZATION_REPLAY_ENABLED', 'true').strip().lower() in {
        '1',
        'true',
        'yes',
        'on',
    }


def durable_attempt_cap_enabled() -> bool:
    return os.getenv('LISTEN_FINALIZATION_DURABLE_ATTEMPT_CAP_ENABLED', 'true').strip().lower() in {
        '1',
        'true',
        'yes',
        'on',
    }
