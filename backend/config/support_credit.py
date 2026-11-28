"""Support transcription credit: storage identity and kill switch. Dependency-free."""

from config.refactor_modes import default_on

# users/{uid}.<FIELD> is a map keyed by the support action id that granted it.
FIELD = 'support_transcription_credit'
ENABLED_ENV = 'SUPPORT_TRANSCRIPTION_CREDIT_ENABLED'
DEFAULT_EXPIRES_DAYS = 30
# Bounds the months the balance arithmetic reads (one usage total per prior month).
MAX_EXPIRES_DAYS = 90


def enabled() -> bool:
    """Kill switch, on unless set off. Off ignores stored credits; it never erases them."""
    return default_on(ENABLED_ENV)
