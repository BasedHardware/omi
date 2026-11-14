"""Recorded-time intake and episode ownership. Ship-on operator rollback switches."""

import os


def late_audio_intake_enabled() -> bool:
    return os.getenv('LATE_AUDIO_SYNC_INTAKE_ENABLED', 'true').strip().lower() not in {'false', 'off', '0', 'no'}


def recorded_episodes_enabled() -> bool:
    return os.getenv('EPISODE_RECORDED_TIME_ENABLED', 'true').strip().lower() not in {'false', 'off', '0', 'no'}


def batch_close_attach_enabled() -> bool:
    return os.getenv('EPISODE_BATCH_CLOSE_ATTACH_ENABLED', 'true').strip().lower() not in {'false', 'off', '0', 'no'}


def batch_admission_attach_enabled() -> bool:
    """Attach a batch capture to its episode when it is admitted, not only at audio close.

    Off restores the pre-admission behaviour: the capture stays a standalone Home
    row for the length of the recording and joins at audio close.
    """
    return os.getenv('EPISODE_BATCH_ADMISSION_ATTACH_ENABLED', 'true').strip().lower() not in {
        'false',
        'off',
        '0',
        'no',
    }


def live_timer_start_enabled() -> bool:
    return os.getenv('EPISODE_LIVE_TIMER_START_ENABLED', 'true').strip().lower() not in {'false', 'off', '0', 'no'}
