"""Serving-only rollback; write coverage stays maintained while Home is off."""

import os


def home_feed_enabled() -> bool:
    return os.getenv('HOME_FEED_ENABLED', 'true').strip().lower() not in {'0', 'false', 'off', 'no'}
