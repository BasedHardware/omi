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
