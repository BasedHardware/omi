"""Leader-owned, once-a-minute fresh-delivery samples. Scrapes never do IO."""

import logging
import threading
import time

from prometheus_client.core import GaugeMetricFamily

from config.policy import kill_switch
from database.batch_pipeline_fresh_guard import fresh_committed_counts

PREFIX = 'omi_batch_pipeline_fresh_'
METRICS = {
    'committed_window_total': 'Fresh results committed 10–20 minutes before the sample',
    'unprojected_window_total': 'Fresh results in the commit window still pending projection',
    'unprojected_ratio': 'Pending share of fresh results in the commit window',
    'guard_sample_age_seconds': 'Seconds since the last successful fresh-delivery count pair',
}


def enabled() -> bool:
    return kill_switch('BATCH_PIPELINE_FRESH_GUARD_ENABLED', log=False)


class FreshGuard:
    def __init__(self, registry):
        self._lock = threading.Lock()
        self._refresh_lock = threading.Lock()
        self._due = 0.0
        self._observed = None
        self._counts = None
        self._active = False
        registry.register(self)

    def describe(self):
        for name, help_text in METRICS.items():
            yield GaugeMetricFamily(PREFIX + name, help_text)

    def deactivate(self):
        with self._lock:
            self._active = False
            self._counts = None

    def refresh(self, store):
        # Serialize RPCs and cadence with concurrent reconcile/supervisor calls.
        if not self._refresh_lock.acquire(blocking=False):
            return
        try:
            with self._lock:
                if not enabled():
                    self._active = False
                    self._counts = None
                    return
                self._active = True
                if time.monotonic() < self._due:
                    return
                self._due = time.monotonic() + 60
                self._counts = None
            try:
                total, pending = fresh_committed_counts(store.client, store.namespace, time.time())
                with self._lock:
                    self._counts = (total, pending)
                    self._observed = time.monotonic()
            except Exception as error:
                logging.getLogger(__name__).warning(
                    'event=batch_fresh_guard outcome=retry exception_type=%s', type(error).__name__
                )
        finally:
            self._refresh_lock.release()

    def collect(self):
        with self._lock:
            if not enabled() or not self._active or self._observed is None:
                return
            age = max(0.0, time.monotonic() - self._observed)
            values = {'guard_sample_age_seconds': age}
            # Stopped supervision cannot keep publishing a healthy ratio.
            if self._counts is not None and age < 120:
                total, pending = self._counts
                values.update(committed_window_total=total, unprojected_window_total=pending)
                if total:
                    values['unprojected_ratio'] = pending / total
        for name, value in values.items():
            yield GaugeMetricFamily(PREFIX + name, METRICS[name], value=value)
