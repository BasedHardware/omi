"""Per-owner admission. Downstream work follows the stored recording marker."""

import os

from config.rollout_cohorts import in_rollout_cohort, parse_cohort, valid_uid
from utils.conversations.v3 import client_capability
from utils.episodes import client_gate


def conversations_v3_enabled(uid: str) -> bool:
    """``beta``: TestFlight-seen owners with a v3-capable app. ``all``: owners with a v3-capable app.

    Neither admits an owner whose apps all predate v3: those builds show the raw recording a capture
    ends with as a blank card that 404s (utils/conversations/v3/client_capability.py). The episodes
    marker alone is not proof: code before #25500 also wrote it for store-channel episode callers.
    """
    if not uid or os.getenv('CONVERSATIONS_V3', '').strip().lower() == 'off':
        return False
    stage = os.getenv('CONVERSATIONS_V3_STAGE', 'beta').strip().lower()
    if stage == 'beta' and client_gate.client_seen_cached(uid) and client_capability.capable_cached(uid):
        return True
    if stage == 'all' and client_capability.capable_cached(uid):
        return True
    return in_rollout_cohort(uid, 'conversations-v3')


def live_recap_enabled(uid: str) -> bool:
    """Only explicit authenticated testers. Empty or invalid config closes the whole cohort."""
    raw = os.getenv('CONVERSATIONS_V3_LIVE_RECAP_COHORT', '')
    if not valid_uid(uid) or not all(token.strip().lower().startswith('uid:') for token in raw.split(',')):
        return False
    parsed = parse_cohort(raw)
    if parsed is None:
        return False
    members, _ = parsed
    return not any(set(member) & set('*?[]') for member in members) and uid in members


def live_title_enabled() -> bool:
    return os.getenv('CONVERSATIONS_V3_LIVE_TITLE', 'on').strip().lower() == 'on'


ROTATION_COHORT = 'v3-recording-rotation'
ROTATION_DEFAULTS = (180.0, 300.0)


def recording_rotation_enabled(uid: str) -> bool:
    """Listen seals long v3 recordings at short pauses. ``off`` (default), ``cohort`` or ``on``."""
    mode = os.getenv('CONVERSATIONS_V3_RECORDING_ROTATION', 'off').strip().lower()
    if mode == 'on':
        return True
    return mode == 'cohort' and in_rollout_cohort(uid, ROTATION_COHORT)


def rotation_seconds() -> tuple[float, float]:
    """(minimum age, hard cap) of a rotated recording; an invalid pair keeps the defaults."""
    try:
        age = float(os.getenv('CONVERSATIONS_V3_ROTATION_MIN_SECONDS', str(ROTATION_DEFAULTS[0])))
        cap = float(os.getenv('CONVERSATIONS_V3_ROTATION_MAX_SECONDS', str(ROTATION_DEFAULTS[1])))
    except ValueError:
        return ROTATION_DEFAULTS
    if not 60 <= age <= cap <= 3600:
        return ROTATION_DEFAULTS
    return age, cap


def manual_end_home_visible_enabled() -> bool:
    return os.getenv('CONVERSATIONS_V3_MANUAL_END_HOME_VISIBLE', 'on').strip().lower() not in {
        'off',
        'false',
        '0',
        'no',
    }


def stretch_cohesion_enabled() -> bool:
    return os.getenv('CONVERSATIONS_V3_STRETCH_COHESION', 'on').strip().lower() not in {'off', 'false', '0', 'no'}


DEFAULT_BOUNDARY_SECONDS = 300
HISTORICAL_SITDOWN_TIMING = (900, 3600)
# Stamped by the transaction that makes new recording speech visible; custom lock timing counts from it.
SPEECH_LANDED_FIELD = 'v3_speech_landed_at'


def _boundary_seconds(key: str, maximum: int) -> int:
    try:
        value = int(os.getenv(key, str(DEFAULT_BOUNDARY_SECONDS)))
    except ValueError:
        return DEFAULT_BOUNDARY_SECONDS
    return value if 120 <= value <= maximum else DEFAULT_BOUNDARY_SECONDS


def boundary_seconds(*, cohesion: bool) -> tuple[int, int]:
    if not cohesion:
        return DEFAULT_BOUNDARY_SECONDS, DEFAULT_BOUNDARY_SECONDS
    return (
        _boundary_seconds('CONVERSATIONS_V3_SILENCE_GAP_SECONDS', 1800),
        _boundary_seconds('CONVERSATIONS_V3_LOCK_SECONDS', 3600),
    )


def backfill_enabled() -> bool:
    return os.getenv('CONVERSATIONS_V3_BACKFILL', 'off').strip().lower() == 'on'


def episode_build_bucket(raw: str) -> str:
    boundary = os.getenv('CONVERSATIONS_V3_FIRST_APP_BUILD', '').strip()
    if not boundary.isdecimal() or not raw.isdecimal() or int(boundary) <= 0 or int(raw) <= 0:
        return 'unknown'
    return 'v3_capable' if int(raw) >= int(boundary) else 'pre_v3'
