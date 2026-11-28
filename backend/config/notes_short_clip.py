"""Independent short-recording compute floor."""

from config.refactor_modes import default_on

NOTES_SHORT_CLIP_FLOOR_ENV = 'NOTES_SHORT_CLIP_FLOOR'


def floor_serving() -> bool:
    return default_on(NOTES_SHORT_CLIP_FLOOR_ENV)
