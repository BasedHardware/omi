"""Sample cache hits without waiting for, publishing, or logging fresh values."""

import math
import os
import random
from collections.abc import Mapping

from prometheus_client import Counter

from utils.episodes.metrics import reuse_or_create

SHADOW = reuse_or_create(
    Counter,
    'omi_read_cache_shadow_total',
    'Sampled read-cache agreement with fresh durable reads',
    ['cache', 'result'],
)
USAGE_FIELDS = ('transcription_seconds', 'words_transcribed', 'insights_gained', 'memories_created', 'speech_seconds')
READ_TIMEOUT_SECONDS = 5.0


def _canonical(cache, value):
    if not isinstance(value, Mapping):
        raise ValueError('invalid shadow value')
    if cache == 'episode_members':
        return tuple(sorted(value))
    totals = tuple(value[field] for field in USAGE_FIELDS)
    if any(type(total) not in (int, float) or not math.isfinite(total) for total in totals):
        raise ValueError('invalid shadow totals')
    return totals


def _record(cache, result):
    try:
        SHADOW.labels(cache=cache, result=result).inc()
    except Exception:
        pass


def compare_hit(cache, cached, fetch, *, sample=None):
    """Nonblocking admission; fetch(timeout) must bound RPCs and bypass all caches.

    The dedicated executor admits at most two outstanding comparisons per process
    and has no queue. Sampling and telemetry failures never escape to the reader.
    Canonicalize before returning so caller mutations cannot change the baseline.
    """
    if cache not in {'usage_month', 'episode_members'}:
        return
    try:
        rate = float(os.getenv('OMI_READ_CACHE_SHADOW_RATE', '0.01'))
        if not math.isfinite(rate) or rate <= 0 or (sample or random.random)() >= min(rate, 1.0):
            return
        expected = _canonical(cache, cached)

        def compare():
            try:
                from database.fsr_read_cache import fresh_reads

                with fresh_reads():
                    actual = _canonical(cache, fetch(READ_TIMEOUT_SECONDS))
                _record(cache, 'match' if expected == actual else 'mismatch')
            except Exception:
                _record(cache, 'error')

        from utils.executors import read_cache_shadow_executor, submit_with_context

        submit_with_context(read_cache_shadow_executor, compare)
    except Exception:
        _record(cache, 'error')
