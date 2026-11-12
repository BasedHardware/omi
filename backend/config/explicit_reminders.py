"""Pure runtime control shared by reminder admission and durable export delivery."""

import os

FLAG = 'ACTION_ITEM_REMINDER_REDESIGN_ENABLED'
POLICY_REVISION = 'explicit-reminders-v1'


def enabled() -> bool:
    value = os.getenv(FLAG)
    return value is None or value.strip().casefold() in {'1', 'true', 'yes', 'on'}
