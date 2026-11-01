"""Audio custody is on unless an operator explicitly selects emergency rollback."""

import os


def enabled() -> bool:
    # Fail closed on misspellings/empty values. Only this literal is rollback.
    return os.getenv('AUDIO_DURABLE_OUTBOX_ENABLED', 'true').strip().lower() != 'false'
