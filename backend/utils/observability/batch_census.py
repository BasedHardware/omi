"""Census gauges: one exact count and one oldest-age reading per registered stock.

Series are created only when a process publishes a sample. A replica that never
ran the exporter exports nothing for these families rather than a zero, because
a zero is a real, healthy population. Read the replica whose
``omi_batch_pipeline_census_snapshot_timestamp_seconds`` is newest; never sum or
``max()`` the gauges themselves.

``oldest_age_seconds`` is ``-1`` when the stock has rows but no ageable clock
(the oldest-row projection returned nothing, the entry has no clock, or the only
rows carry a clock the query cannot order). It is ``0`` only for a genuinely
empty stock. A malformed clock on an otherwise readable stock is not a
measurement and is not reported as a small age.
"""

from __future__ import annotations

import logging
import math
import time
from typing import Any, Iterable, Mapping

from prometheus_client import Counter, Gauge

from config.batch_census import BY_KEY, ENTRIES, CensusEntry

logger = logging.getLogger(__name__)
LABELS = ('machine', 'state')
UNDATED_OLDEST_AGE_SENTINEL = -1.0

UNITS = Gauge(
    'omi_batch_pipeline_census_state_units',
    'Exact count of the registered stuck state. A stock with no sample exports no series, not zero',
    list(LABELS),
)
OLDEST_AGE = Gauge(
    'omi_batch_pipeline_census_state_oldest_age_seconds',
    'Age of the oldest row in the registered stock, from its declared clock. -1 means rows exist but '
    'none carries an ageable clock; 0 means the stock is empty',
    list(LABELS),
)
OBSERVED_AT = Gauge(
    'omi_batch_pipeline_census_state_observed_at_seconds',
    'Unix time of the last successful sample for this stock. An age alert must require this to be fresh',
    list(LABELS),
)
SNAPSHOT_TIMESTAMP = Gauge(
    'omi_batch_pipeline_census_snapshot_timestamp_seconds',
    'Unix time of the last completed census pass on this process. Read gauges from the replica where this is newest',
)
SAMPLE_FAILURES = Counter(
    'omi_batch_pipeline_census_sample_failures_total',
    'Census stock samples that failed; the previous reading is retained and the observation is not refreshed',
    list(LABELS),
)
STOCKS = Gauge(
    'omi_batch_pipeline_census_registered_stocks',
    'Registered stocks in this build, so a deploy that changes the vocabulary is visible next to the readings',
)


def _labels(entry: CensusEntry) -> dict[str, str]:
    return {'machine': entry.machine, 'state': entry.state}


def _age(sample: Any, now: float) -> float:
    units = getattr(sample, 'units', 0)
    if isinstance(units, bool) or not isinstance(units, int) or units <= 0:
        return 0.0
    oldest = getattr(sample, 'oldest_at', None)
    if isinstance(oldest, bool) or not isinstance(oldest, (int, float)) or not math.isfinite(oldest):
        return UNDATED_OLDEST_AGE_SENTINEL
    return max(0.0, now - float(oldest))


def publish(samples: Mapping[str, Any], *, failures: Iterable[str] = (), now: float | None = None) -> int:
    """Publish one pass. Returns the number of stocks published.

    Unknown keys are ignored so a rolling deploy that still holds old gauges
    cannot publish a stock this build no longer declares. A failed stock keeps
    its previous reading and its previous observation timestamp: the staleness
    of that timestamp is the signal, and it must not be refreshed with a value
    nobody measured.
    """
    moment = time.time() if now is None else now
    published = 0
    for key, sample in samples.items():
        entry = BY_KEY.get(key)
        if entry is None:
            continue
        labels = _labels(entry)
        try:
            UNITS.labels(**labels).set(max(0, int(getattr(sample, 'units', 0))))
            OLDEST_AGE.labels(**labels).set(_age(sample, moment))
            OBSERVED_AT.labels(**labels).set(moment)
        except Exception:
            logger.warning('event=batch_census_metric outcome=dropped key=%s', key)
            continue
        published += 1
    for key in failures:
        entry = BY_KEY.get(key)
        if entry is None:
            continue
        SAMPLE_FAILURES.labels(**_labels(entry)).inc()
    STOCKS.set(len(ENTRIES))
    SNAPSHOT_TIMESTAMP.set(moment)
    return published


__all__ = [
    'OLDEST_AGE',
    'OBSERVED_AT',
    'SAMPLE_FAILURES',
    'SNAPSHOT_TIMESTAMP',
    'STOCKS',
    'UNDATED_OLDEST_AGE_SENTINEL',
    'UNITS',
    'publish',
]
