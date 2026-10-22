"""V4 consumers delegate content-kind admission to V2's shared authority.

The lanes merge independently. If V2 is not installed, preserve legacy output
and report the missing serving dependency rather than invent another policy.
"""

from importlib import import_module
from config.refactor_modes import serving_for
from utils.conversations.calls_metrics import observe


def _policy():
    return import_module('utils.conversations.relevance_content').exclude_from_derived


def is_excluded(uid, conversation, *, consumer):
    if not serving_for('MEDIA_NOISE_MODE', uid):
        return False
    try:
        return _policy()(uid, conversation, consumer=consumer)
    except ImportError:
        observe('media_consumer', 'error')
        from utils.observability.fallback import record_fallback

        record_fallback(
            component='conversation_notes',
            from_mode='content_kind',
            to_mode='legacy_content',
            reason='dependency_unavailable',
            outcome='degraded',
        )
        return False


def eligible_conversations(uid, rows):
    return [row for row in rows if not is_excluded(uid, row, consumer='daily_summary')]
