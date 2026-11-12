"""Sample cache hits without waiting for, publishing, or logging fresh values."""

import math
import os
import random
from collections.abc import Mapping

from prometheus_client import Counter

from database.monthly_usage_totals import FIELDS as USAGE_FIELDS
from utils.episodes.metrics import reuse_or_create

SHADOW = reuse_or_create(
    Counter,
    'omi_read_cache_shadow_total',
    'Sampled read-cache agreement; episode_members compares keys only and cannot detect content staleness',
    ['cache', 'result'],
)
READ_TIMEOUT_SECONDS = 5.0


class ShadowSkipped(Exception):
    """A bounded shadow read cannot produce a complete comparable value."""


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
    Callers pass private cache snapshots; returned responses are deep copies.
    """
    if cache not in {'usage_month', 'episode_members'}:
        return
    try:
        rate = float(os.getenv('OMI_READ_CACHE_SHADOW_RATE', '0.01'))
    except (TypeError, ValueError):
        return
    if not math.isfinite(rate) or rate <= 0:
        return
    try:
        if (sample or random.random)() >= min(rate, 1.0):
            return
        # Retain the raw private snapshot: callers cannot mutate it, and sorting
        # or projecting it belongs entirely to the background worker.

        def compare():
            try:
                from database.fsr_read_cache import fresh_reads

                expected = _canonical(cache, cached)
                with fresh_reads():
                    actual = _canonical(cache, fetch(READ_TIMEOUT_SECONDS))
                agrees = (
                    expected == actual
                    if cache == 'episode_members'
                    else all(math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-6) for a, b in zip(expected, actual))
                )
                _record(cache, 'match' if agrees else 'mismatch')
            except ShadowSkipped:
                _record(cache, 'skipped')
            except Exception:
                _record(cache, 'error')

        from utils.executors import ExecutorSaturatedError, read_cache_shadow_executor, submit_with_context

        try:
            submit_with_context(read_cache_shadow_executor, compare)
        except ExecutorSaturatedError:
            _record(cache, 'skipped')
    except Exception:
        _record(cache, 'error')
