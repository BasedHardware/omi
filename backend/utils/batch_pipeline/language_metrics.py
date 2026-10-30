"""Bounded routing evidence, independent of transcript/nonempty success."""

import logging

from prometheus_client import Counter

from config.prerecorded_language import language_class
from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)
ROUTES = Counter(
    'omi_batch_pipeline_language_route_total',
    'Batch speech routing by declared language capability, never transcript content',
    ['surface', 'language_class', 'route'],
)


def record_route(surface: str, language: str | None, route: str, *, segment_id: str | None = None) -> None:
    if surface not in {'prerecorded', 'intake', 'worker'} or route not in {'parakeet', 'multilingual', 'blocked'}:
        raise ValueError('closed language route required')
    classification = language_class(language)
    try:
        ROUTES.labels(surface, classification, route).inc()
        if surface == 'worker':
            logger.info(
                'event=batch_language_route surface=worker language_class=%s route=%s segment_id=%s',
                classification,
                route,
                segment_id,
            )
    except Exception:
        pass  # Routing quality must not depend on the telemetry exporter.


def record_admission_exclusion(language, reason, *, legacy_available: bool) -> None:
    """One bounded decision, whether intake or the earlier owner claim excludes it."""
    record_route('intake', language, 'multilingual' if legacy_available else 'blocked')
    if legacy_available:
        record_fallback(
            component='sync_dispatch', from_mode='batch', to_mode='legacy', reason='other', outcome='degraded'
        )
    logger.info('event=batch_admission_language outcome=excluded reason=%s', reason)
