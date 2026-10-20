"""Bounded policy-source telemetry, emitted only after persistence."""

from __future__ import annotations

import logging
from threading import Lock
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from prometheus_client import Counter

logger = logging.getLogger(__name__)
_counter_lock = Lock()
_counter_instance: Counter | None = None


def _counter() -> Counter:
    global _counter_instance
    # lru_cache may construct twice under concurrent first admissions, which
    # would register a duplicate Prometheus collector after a successful commit.
    with _counter_lock:
        if _counter_instance is None:
            from prometheus_client import Counter

            _counter_instance = Counter(
                'omi_batch_unit_policy_total', 'Persisted batch policy snapshots by source', ['policy_source']
            )
        return _counter_instance


def record_policy_source(source: str, policy_id: str, *, count: int = 1):
    if source not in {'admission', 'fallback', 'stage'}:
        raise ValueError('bounded policy source required')
    try:
        if source == 'fallback':
            from utils.observability.fallback import record_fallback

            record_fallback(
                component='sync_dispatch', from_mode='none', to_mode='batch', reason='other', outcome='recovered'
            )
        _counter().labels(policy_source=source).inc(count)
        logger.info('event=batch_unit_policy policy_source=%s policy_id=%s count=%d', source, policy_id, count)
    except Exception:
        pass  # Telemetry cannot turn a committed admission/repair into a failed request.
