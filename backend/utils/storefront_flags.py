"""Dark backend storefront admission. No caller header can enable it."""

# LIFECYCLE: permanent
import os


def enabled() -> bool:
    return os.getenv('STOREFRONT_LADDER_V1_ENABLED', 'false') == 'true'
