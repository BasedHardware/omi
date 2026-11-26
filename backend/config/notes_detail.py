"""Default-on long-note detail budget; shared prompt and validation limits."""

from config.refactor_modes import default_on

NOTES_SCALED_DETAIL_ENV = 'CONVERSATION_NOTES_SCALED_DETAIL_ENABLED'
NOTES_DETAIL_FROM_WORDS = 5000
NOTES_DETAIL_WORD_RATIO = 0.10
NOTES_DETAIL_MIN_TARGET_WORDS = 800
NOTES_DETAIL_MAX_WORDS = 3500
NOTES_DETAIL_WORDS_PER_SECTION = 2000
NOTES_DETAIL_MAX_SECTIONS = 20


def notes_scaled_detail_enabled() -> bool:
    return default_on(NOTES_SCALED_DETAIL_ENV)
