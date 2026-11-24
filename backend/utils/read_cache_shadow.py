"""Sample cache hits without waiting for, publishing, or logging fresh values."""

import math
import os
import random
from datetime import datetime

from google.api_core.exceptions import Aborted
from collections.abc import Mapping

from prometheus_client import Counter

from database.monthly_usage_totals import FIELDS as USAGE_FIELDS, usage_month_epoch
from utils.episodes.metrics import reuse_or_create

SHADOW = reuse_or_create(
    Counter,
    'omi_read_cache_shadow_total',
    'Sampled read-cache agreement; episode_members compares keys only and cannot detect content staleness',
    ['cache', 'result'],
)
MONTH_SHADOW = reuse_or_create(
    Counter,
    'omi_usage_month_total_shadow_total',
    'Sampled monthly usage comparisons against the hourly Firestore snapshot',
    ['service', 'epoch', 'path', 'outcome', 'delta_bucket'],
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

        _submit(compare, lambda: _record(cache, 'skipped'))
    except Exception:
        _record(cache, 'error')


def _submit(compare, skipped):
    from utils.executors import ExecutorSaturatedError, read_cache_shadow_executor, submit_with_context

    try:
        submit_with_context(read_cache_shadow_executor, compare)
    except ExecutorSaturatedError:
        skipped()


def compare_cached_month(uid, date, start_date, expected, client, metadata):
    source = metadata if isinstance(metadata, Mapping) else {}
    compare_month('cache_hit', uid, date, start_date, expected, client, source.get('read_time'), source.get('epoch'))


def compare_month(path, uid, date, start_date, served, client, read_time, epoch):
    """Sample the exact value and cutoff served, without a fresh read on the caller."""
    from database.firestore_document_probe import firestore_metrics_service_name

    def record(outcome, bucket='none'):
        try:
            MONTH_SHADOW.labels(
                service=firestore_metrics_service_name(),
                epoch=epoch or 'unknown',
                path=path,
                outcome=outcome,
                delta_bucket=bucket,
            ).inc()
            if path == 'cache_hit':
                _record('usage_month', 'skipped' if outcome == 'race' else outcome)
        except Exception:
            pass

    try:
        if os.getenv('OMI_USAGE_MONTH_TOTAL_SHADOW_ENABLED', 'true').strip().lower() in {'0', 'false', 'off', 'no'}:
            return
        try:
            rate = float(os.getenv('OMI_USAGE_MONTH_TOTAL_SHADOW_RATE', '0.01'))
        except ValueError:
            return
        if not math.isfinite(rate) or rate <= 0 or random.random() >= min(rate, 1.0):
            return

        # Only admit a timestamp we can actually use. Report unversioned cache
        # entries under the configured epoch, without crediting them as coverage.
        if not isinstance(read_time, datetime) or epoch is None:
            epoch = usage_month_epoch()
            record('skipped')
            return
        if path == 'cache_hit' and epoch != usage_month_epoch():
            # A cache hit may outlive a reader epoch change. It does not qualify
            # either epoch's cache behavior as equivalent.
            epoch = usage_month_epoch()
            record('race')
            return
        # Both the caller and Redis may return mutable dictionaries.
        expected = tuple(served.get(field, 0) for field in USAGE_FIELDS)

        def compare():
            try:
                from database.user_usage import read_hourly_usage_for_shadow

                actual = _canonical(
                    'usage_month',
                    read_hourly_usage_for_shadow(
                        uid, date, start_date, READ_TIMEOUT_SECONDS, firestore_client=client, read_time=read_time
                    ),
                )
                mismatched = [
                    abs(before - after)
                    for field, before, after in zip(USAGE_FIELDS, expected, actual)
                    if not _same_usage(field, before, after)
                ]
                if mismatched:
                    record('mismatch', _delta_bucket(max(mismatched)))
                else:
                    record('match')
            except Aborted:
                record('race')
            except ShadowSkipped:
                record('skipped')
            except Exception:
                record('error')

        _submit(compare, lambda: record('skipped'))
    except Exception:
        record('error')


def _delta_bucket(delta):
    for bound in (1, 60, 3600):
        if delta <= bound:
            return f'le_{bound}'
    return 'gt_3600'


def _same_usage(field, before, after):
    if type(before) not in (int, float) or not math.isfinite(before):
        raise ValueError('invalid served usage')
    if field in {'transcription_seconds', 'speech_seconds'}:
        return math.isclose(before, after, rel_tol=1e-12, abs_tol=1e-6)
    return before == after
