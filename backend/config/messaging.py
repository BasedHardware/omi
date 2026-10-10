"""Messaging rollout is off unless both the switch and exact uid cohort admit it."""

import os


def cohort_enabled(uid):
    return os.getenv('OMI_MESSAGING_CHANNELS', 'off').lower() == 'on' and uid in {
        value.strip() for value in os.getenv('OMI_MESSAGING_CHANNELS_UIDS', '').split(',') if value.strip()
    }
