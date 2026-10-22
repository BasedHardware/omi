"""Content-free attribution at the local send boundary; never changes health votes."""

import logging

from prometheus_client import Counter

logger = logging.getLogger(__name__)
PROVIDERS = frozenset({'parakeet', 'soniox', 'modulate', 'deepgram'})
PHASES = frozenset({'raw_send', 'raw_refused', 'usage_accounting', 'capture_mapping', 'finalize', 'send_call'})
ERROR_CLASSES = frozenset({'TypeError', 'ValueError', 'AttributeError', 'RuntimeError', 'TimeoutError', 'OSError'})
LOCAL_SEND_FAILURES = Counter(
    'omi_stt_local_send_failures_total',
    'Local send boundary failures, including bookkeeping and finalize; not independent provider failures',
    ['provider', 'phase', 'exception_class'],
)


def bounded_local_send_provider(provider) -> str:
    """Stable provider label: PROVIDERS member (or enum value) else 'other'."""
    provider = getattr(provider, 'value', provider)
    return provider if provider in PROVIDERS else 'other'


def record_local_send_failure(provider, phase, raw, error=None):
    """Never retain exception text, PCM, user/session IDs or endpoints."""
    try:
        provider = bounded_local_send_provider(provider)
        phase = phase if phase in PHASES else 'other'
        name = type(error).__name__ if error is not None else 'none'
        name = name if name in ERROR_CLASSES or name == 'none' else 'other'
        try:
            dead = 'true' if raw.is_connection_dead is True else 'false'
        except Exception:
            dead = 'unknown'
        closed = 'true' if getattr(raw, '_closed', False) is True else 'false'
        proxy = 'cap' if getattr(raw, 'cap_dispatch_socket', False) is True else 'direct'
        LOCAL_SEND_FAILURES.labels(
            provider=bounded_local_send_provider(provider), phase=phase, exception_class=name
        ).inc()
        logger.warning(
            'event=live_stt_local_send_failure provider=%s phase=%s exception_class=%s '
            'raw_dead=%s raw_closed=%s proxy=%s',
            provider,
            phase,
            name,
            dead,
            closed,
            proxy,
        )
    except Exception:
        # Observability cannot make an accepted packet fail or mask its cause.
        pass
