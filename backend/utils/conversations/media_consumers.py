"""Every derived consumer delegates serving and shadow to the shared media gate."""

from importlib import import_module
from config.refactor_modes import shadow_or_serve
from utils.conversations.calls_metrics import observe


def _policy():
    return import_module('utils.conversations.relevance_content').exclude_from_derived


def is_excluded(uid, conversation, *, consumer):
    if not shadow_or_serve('MEDIA_NOISE_MODE'):
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
