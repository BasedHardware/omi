"""Low-cardinality observability for speaker presentation degradation."""

from functools import lru_cache

from prometheus_client import Counter


@lru_cache(maxsize=1)
def _counter():
    return Counter('omi_speaker_display_count_guard_total', 'Display projections collapsing excess unnamed voices')


def record_count_guard() -> None:
    _counter().inc()
