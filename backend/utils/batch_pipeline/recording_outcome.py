"""Leader-owned, once-a-minute recording-outcome samples. Scrapes never do IO.

The outcome SLI for "a recording gets a transcript and a summary within minutes":
of batch-live recordings that finished 45 to 15 minutes ago, how many have a
transcript and how many have a summary. The denominator is the finished
recordings themselves, independent of every pipeline stage, so a stall anywhere
lowers the share instead of dropping work out of the cohort. A latency histogram
only observes work that completes and cannot show this.
"""

import logging
import threading
import time

from prometheus_client.core import GaugeMetricFamily

from config.policy import kill_switch
from database.batch_pipeline_recording_outcome import recording_outcome_counts

PREFIX = 'omi_batch_pipeline_recording_outcome_'
METRICS = {
    'finished_window_total': 'Completed batch-live recordings that finished 45 to 15 minutes before the sample',
    'transcribed_window_total': 'Recordings in the finished window whose transcript has landed',
    'summarized_window_total': 'Recordings in the finished window that have a summary',
    'sample_age_seconds': 'Seconds since the last successful recording-outcome count triple',
    'sample_timestamp_seconds': 'Unix time anchoring the last successful recording-outcome finished window',
}
SAMPLE_SECONDS = 60
# Counts older than this are withdrawn so a stopped sampler cannot keep a healthy share on the board.
# Three samples: one slow pass or a lease handoff does not blank the board.
EXPIRY_SECONDS = 180


def enabled() -> bool:
    return kill_switch('BATCH_PIPELINE_RECORDING_OUTCOME_ENABLED', log=False)


class RecordingOutcome:
    def __init__(self, registry):
        self._lock = threading.Lock()
        self._refresh_lock = threading.Lock()
        self._due = 0.0
        self._observed = None
        # (finished, transcribed, summarized, sample unix time) from the last successful triple.
        self._counts: tuple[int, int, int, float] | None = None
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
                self._due = time.monotonic() + SAMPLE_SECONDS
            try:
                sample_time = time.time()
                counts = recording_outcome_counts(store.client, sample_time)
                with self._lock:
                    self._counts = (*counts, sample_time)
                    self._observed = time.monotonic()
            except Exception as error:
                # A failed triple withdraws the counts (never a fresh zero); the age keeps advancing.
                with self._lock:
                    self._counts = None
                logging.getLogger(__name__).warning(
                    'event=batch_recording_outcome outcome=retry exception_type=%s', type(error).__name__
                )
        finally:
            self._refresh_lock.release()

    def collect(self):
        with self._lock:
            if not enabled() or not self._active or self._observed is None:
                return
            age = max(0.0, time.monotonic() - self._observed)
            values: dict[str, float] = {'sample_age_seconds': age}
            if self._counts is not None and age < EXPIRY_SECONDS:
                finished, transcribed, summarized, sample_time = self._counts
                values.update(
                    finished_window_total=finished,
                    transcribed_window_total=transcribed,
                    summarized_window_total=summarized,
                    sample_timestamp_seconds=sample_time,
                )
        for name, value in values.items():
            yield GaugeMetricFamily(PREFIX + name, METRICS[name], value=value)
