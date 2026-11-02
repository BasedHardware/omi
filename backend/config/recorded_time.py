"""Recorded-time intake and episode ownership. Ship-on operator rollback switches."""

import os


def late_audio_intake_enabled() -> bool:
    return os.getenv('LATE_AUDIO_SYNC_INTAKE_ENABLED', 'true').strip().lower() not in {'false', 'off', '0', 'no'}


def recorded_episodes_enabled() -> bool:
    return os.getenv('EPISODE_RECORDED_TIME_ENABLED', 'true').strip().lower() not in {'false', 'off', '0', 'no'}


def live_timer_start_enabled() -> bool:
    return os.getenv('EPISODE_LIVE_TIMER_START_ENABLED', 'true').strip().lower() not in {'false', 'off', '0', 'no'}
