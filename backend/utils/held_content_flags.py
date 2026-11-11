"""Default-off held-content admission; capability is never an entitlement."""

import os

HELD_CONTENT_ENABLED = 'HELD_CONTENT_ENABLED'


def enabled() -> bool:
    return os.getenv(HELD_CONTENT_ENABLED, 'false').lower() == 'true'


def capable(capability: str | None) -> bool:
    return enabled() and capability == '1'
