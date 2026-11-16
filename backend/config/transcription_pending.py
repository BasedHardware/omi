"""Presentation and retry repairs; independent default-on kill switches."""

from config.refactor_modes import default_on

HOME_TRANSCRIPTION_SEAL_WAIT_ENABLED_ENV = 'HOME_TRANSCRIPTION_SEAL_WAIT_ENABLED'
CONVERSATION_PENDING_TRANSCRIPTION_RETRY_ENABLED_ENV = 'CONVERSATION_PENDING_TRANSCRIPTION_RETRY_ENABLED'
HOME_STALE_EMPTY_CAPTURE_NOISE_ENABLED_ENV = 'HOME_STALE_EMPTY_CAPTURE_NOISE_ENABLED'


def seal_wait_enabled() -> bool:
    return default_on(HOME_TRANSCRIPTION_SEAL_WAIT_ENABLED_ENV)


def pending_retry_enabled() -> bool:
    return default_on(CONVERSATION_PENDING_TRANSCRIPTION_RETRY_ENABLED_ENV)


def stale_empty_noise_enabled() -> bool:
    return default_on(HOME_STALE_EMPTY_CAPTURE_NOISE_ENABLED_ENV)
