"""Bounded, content-free lifecycle observations; failures never advance freshness."""

import logging
import math
import threading
from datetime import datetime, timezone

from prometheus_client import Gauge, REGISTRY

PAGE_LIMIT = 1000
COHORT_SECONDS = 86400
# A rolling 24h window alone includes known 8-24h incident stock.
COHORT_START = datetime(2026, 11, 4, 9, 27, tzinfo=timezone.utc).timestamp()


def seconds(value):
    if isinstance(value, datetime):
        value = value.timestamp()
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError('finite lifecycle clock required')
    return float(value)


SILENCE_CENSUS_INTERVAL_SECONDS = 6 * 60 * 60
SILENCE_CENSUS_STATES = ('app_active_no_audio', 'app_active_with_audio', 'audio_no_app_activity')
SILENCE_CENSUS_SOURCES = ('omi', 'desktop', 'other')


class SilenceCensusMetrics:
    """Six-hour bounded user observations; partial counts are never exact zeros."""

    def __init__(self, *, registry=REGISTRY, interval_seconds=SILENCE_CENSUS_INTERVAL_SECONDS):
        self.users = Gauge(
            'omi_audio_silence_census',
            'Unique classifiable users in the 24h bounded observation; lower bounds when partial',
            ('state', 'source'),
            registry=registry,
        )
        self.partial = Gauge(
            'omi_audio_silence_census_partial',
            '1 when source saturation, unclassifiable evidence or the hard read budget makes counts lower bounds',
            registry=registry,
        )
        self.observed = Gauge(
            'omi_audio_silence_census_observed_at_seconds',
            'Last completed bounded silence-census observation, including a partial observation',
            registry=registry,
        )
        self.interval_seconds = interval_seconds
        self._lock = threading.Lock()
        self._due = 0.0

    def refresh(self, now, sample):
        if not self._lock.acquire(blocking=False):
            return
        try:
            if now < self._due:
                return
            self._due = now + self.interval_seconds
            try:
                result = sample()
            except Exception as error:
                logging.getLogger(__name__).warning(
                    'event=audio_silence_census outcome=unavailable exception_type=%s', type(error).__name__
                )
                return
            for state in SILENCE_CENSUS_STATES:
                for source in SILENCE_CENSUS_SOURCES:
                    self.users.labels(state, source).set(result['counts'][state, source])
            self.partial.set(int(result['partial']))
            self.observed.set(now)
        finally:
            self._lock.release()


class PhaseMetrics:
    """One bounded source, serialized across its supervised refresh callers.

    Count is a lower bound when truncated. Age is only for entries in the
    configured recent cohort; it never includes historical stock.
    """

    def __init__(self, prefix, labels, *, registry=REGISTRY):
        self.age = Gauge(
            prefix + '_new_oldest_age_seconds', 'Oldest recent-cohort state entry age', labels, registry=registry
        )
        self.count = Gauge(
            prefix + '_count', 'Bounded stock count; lower bound when truncated', labels, registry=registry
        )
        self.truncated = Gauge(
            prefix + '_scan_truncated', 'Bound reached or a lifecycle clock is unknown', labels, registry=registry
        )
        self.observed = Gauge(
            prefix + '_observed_at_seconds', 'Last successful lifecycle observation', registry=registry
        )
        self._lock = threading.Lock()
        self._due = 0.0

    def refresh(self, now, sample):
        if not self._lock.acquire(blocking=False):
            return
        try:
            if now < self._due:
                return
            self._due = now + 300
            try:
                rows = sample()
            except Exception as error:
                logging.getLogger(__name__).warning(
                    'event=lifecycle_sample outcome=unavailable exception_type=%s', type(error).__name__
                )
                return
            for label, (age, count, truncated) in rows.items():
                self.age.labels(label).set(age)
                self.count.labels(label).set(count)
                self.truncated.labels(label).set(int(truncated))
            self.observed.set(now)
        finally:
            self._lock.release()


def cohort_age(rows, field, now, lookback=COHORT_SECONDS):
    clocks = [seconds(row[field]) for row in rows]
    return max((now - clock for clock in clocks if now - lookback <= clock <= now), default=0)
