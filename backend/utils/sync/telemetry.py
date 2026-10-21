from config.sync_telemetry import (
    bounded_correlation_ref,
    bounded_exception_class,
    bounded_sync_phase,
    new_attempt_ref,
)
from utils.sync.lanes import SyncLane

__all__ = [
    'bounded_correlation_ref',
    'bounded_exception_class',
    'bounded_exception_reason',
    'bounded_exception_type',
    'bounded_sync_lane',
    'bounded_sync_model',
    'bounded_sync_phase',
    'new_attempt_ref',
]

_SYNC_STT_MODELS = {'nova-3', 'velma-2', 'parakeet'}


def bounded_sync_model(model: str | None) -> str:
    normalized = (model or '').strip().lower()
    return normalized if normalized in _SYNC_STT_MODELS else 'unknown'


def bounded_sync_lane(lane: str | None) -> str:
    return lane if lane in {SyncLane.FRESH.value, SyncLane.BACKFILL.value} else 'unknown'


# Languages the sync empty-retry measurement stratifies by. Mirrors the STT
# routing language registry's base codes; anything else is 'other', so the
# label space stays closed even for a bogus detected language.
_SYNC_RETRY_LANGUAGES = frozenset(
    {'multi', 'en', 'es', 'fr', 'de', 'pt', 'it', 'nl', 'ja', 'ko', 'zh', 'hi', 'ru', 'ar', 'tr'}
)


def bounded_sync_language(language: str | None) -> str:
    token = (language or '').strip().lower().split('-', 1)[0]
    return token if token in _SYNC_RETRY_LANGUAGES else 'other'


def bounded_exception_type(error: BaseException) -> str:
    name = error.__class__.__name__
    return name if name.replace('_', '').isalnum() and len(name) <= 64 else 'Exception'


def bounded_exception_reason(error: BaseException) -> str:
    """Log-safe exception text so a bare ``assert`` is visible as ``empty``."""
    text = ' '.join(str(error).split())
    if not text:
        return 'empty'
    cleaned = ''.join(ch if ch.isalnum() or ch in ' ._:-=' else '_' for ch in text)
    cleaned = cleaned.strip(' _')[:120]
    return cleaned or 'empty'


_FINALIZE_SITES = {
    'database/action_item_refresh.py': 'action_item_refresh',
    'database/sync_bridges.py': 'bridge_receipt',
    'database/conversations.py': 'conversation_store',
    'utils/sync/fsr_metadata.py': 'bridge_metadata',
    'utils/conversations/merge_conversations.py': 'bridge_effects',
    'utils/other/storage.py': 'audio_storage',
    'utils/sync/bridge.py': 'bridge',
    'utils/sync/intake_completion.py': 'intake_completion',
}


def finalize_exception_site(error: BaseException) -> str:
    """Deepest known code boundary, without emitting paths, locals or exception text."""
    site = 'other'
    traceback = error.__traceback__
    while traceback is not None:
        filename = traceback.tb_frame.f_code.co_filename.replace('\\', '/')
        for suffix, token in _FINALIZE_SITES.items():
            if filename.endswith('/' + suffix):
                site = token
        traceback = traceback.tb_next
    return site
