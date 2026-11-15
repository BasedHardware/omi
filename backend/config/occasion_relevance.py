"""Occasion-aware retention; default-on rollback, independent of temporal intake."""

import os


def enabled() -> bool:
    return os.getenv('CONVERSATION_OCCASION_RELEVANCE_ENABLED', 'true').strip().lower() not in {
        'false',
        '0',
        'off',
        'no',
    }
