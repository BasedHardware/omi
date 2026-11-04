"""Independent short-recording compute floor; notes-v2 serve retains its floor."""

from config.refactor_modes import default_on, serving_for

NOTES_SHORT_CLIP_FLOOR_ENV = 'NOTES_SHORT_CLIP_FLOOR'


def floor_serving(uid: str) -> bool:
    return default_on(NOTES_SHORT_CLIP_FLOOR_ENV) or serving_for('NOTES_PACKET_V2_MODE', uid)
