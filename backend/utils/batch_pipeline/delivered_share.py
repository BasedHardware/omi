"""Per-route, per-language delivered share, sampled from bounded job metadata.

The 2026-11-13 Japanese miss was invisible because every batch signal was
either global or counted from the commit side. A provider unit that never
leaves ``vendor_held`` has no result row, so a commit-based ratio cannot see
it. This sample counts admissions instead, then asks whether each unit carries
the delivery stamp that ``ProjectionStore.acknowledge`` writes when the
transcript is published.

A recorded unit is *delivered in target* when the acknowledge happens within
``TARGET_SECONDS`` of admission. The share is per (route, language) cell, so a
language whose provider route stalls falls on its own row while the fleet-wide
number stays near normal.

Language labels are bounded to the codes the batch route tables can emit; any
code outside that vocabulary folds to ``other`` and an empty/undeclared
language folds to ``unknown``. Neither folded cell is alarmed, and the
``other`` volume is exported so a vocabulary gap stays visible.

Scrapes never read: one bounded metadata page per cohort, on the maintenance
leader, at most every ``SAMPLE_SECONDS``. A failed page removes the counts and
the ratio (never a synthetic zero) while the sample age keeps its last
successful value; the counts and ratio also expire in ``collect`` if
supervision stops.
"""

import logging
import threading
import time

from prometheus_client import Gauge
from prometheus_client.core import GaugeMetricFamily

from config.policy import kill_switch
from database.batch_pipeline_delivered_share import delivered_share_page

PREFIX = 'omi_batch_pipeline_delivered_share_'
SAMPLE_SECONDS = 300
# Counts and ratio stay readable for one missed 300 s sample.
FRESH_SECONDS = 600
OTHER = 'other'
UNKNOWN = 'unknown'
# Union of the deployed Parakeet and Modulate language tables; a code no route
# can emit is a bug or free text, so it must not become a new series.
LANGUAGES = frozenset(
    {
        'af',
        'ar',
        'az',
        'be',
        'bg',
        'bn',
        'bs',
        'ca',
        'cs',
        'cy',
        'da',
        'de',
        'el',
        'en',
        'es',
        'et',
        'eu',
        'fa',
        'fi',
        'fr',
        'gl',
        'gu',
        'he',
        'hi',
        'hr',
        'hu',
        'id',
        'it',
        'ja',
        'kk',
        'kn',
        'ko',
        'lt',
        'lv',
        'mk',
        'ml',
        'mr',
        'ms',
        'mt',
        'multi',
        'nl',
        'no',
        'pa',
        'pl',
        'pt',
        'ro',
        'ru',
        'sk',
        'sl',
        'sq',
        'sr',
        'sv',
        'sw',
        'ta',
        'te',
        'th',
        'tl',
        'tr',
        'uk',
        'ur',
        'vi',
        'zh',
    }
)
# The alarm compares a cell with its own trailing peak, then discounts it, so a
# sustained dip cannot lower the baseline under itself for a week. The rule's
# 7-day range is pinned by the contract test; keep the factor and floor here.
BASELINE_FACTOR = 0.7
MIN_VOLUME = 20
METRICS = {
    'ratio': 'Share of admitted units delivered within the target, per route and language',
    'admitted_units': 'Units admitted in the cohort window, per route and language',
    'units': 'Units admitted and delivered within the target, per route and language',
    'truncated': '1 when the cohort page hit its cap and the share covers only the oldest rows',
    'sample_age_seconds': 'Seconds since the last successful delivered-share page',
}
# Literal names for the alert emitter scan. The collector publishes these as
# GaugeMetricFamily children so an idle cell creates no series; these objects
# are never registered and never collected.
SCAN_ONLY = (
    Gauge('omi_batch_pipeline_delivered_share_ratio', METRICS['ratio'], ['route', 'language'], registry=None),
    Gauge(
        'omi_batch_pipeline_delivered_share_admitted_units',
        METRICS['admitted_units'],
        ['route', 'language'],
        registry=None,
    ),
    Gauge('omi_batch_pipeline_delivered_share_units', METRICS['units'], ['route', 'language'], registry=None),
    Gauge('omi_batch_pipeline_delivered_share_truncated', METRICS['truncated'], registry=None),
    Gauge('omi_batch_pipeline_delivered_share_sample_age_seconds', METRICS['sample_age_seconds'], registry=None),
)


def enabled() -> bool:
    return kill_switch('BATCH_PIPELINE_DELIVERED_SHARE_ENABLED', log=False)


def route_of(job: dict) -> str:
    """The route the unit executed, else its admission route, else unknown."""
    route = (job.get('stt_route') or {}).get('stt_route')
    if route not in ('parakeet', 'provider'):
        route = (job.get('policy') or {}).get('stt_route')
    return route if route in ('parakeet', 'provider') else 'unknown'


def language_of(job: dict) -> str:
    raw = (job.get('projection_binding') or {}).get('language')
    code = raw.split('-')[0].split('_')[0].strip().lower() if isinstance(raw, str) else ''
    if not code:
        return UNKNOWN
    return code if code in LANGUAGES else OTHER


def cells(rows) -> dict[tuple[str, str], tuple[int, int]]:
    """(route, language) -> (admitted, delivered in target). Pure; no IO."""
    result: dict[tuple[str, str], tuple[int, int]] = {}
    for job in rows:
        key = (route_of(job), language_of(job))
        admitted, delivered = result.get(key, (0, 0))
        result[key] = (admitted + 1, delivered + (1 if job.get('delivered_in_target') is True else 0))
    return result


def share(admitted: int, delivered: int) -> float | None:
    return delivered / admitted if admitted else None


def alarm_cells(cells_by_key, baselines) -> list[tuple[str, str, float, float]]:
    """Cells that would fire the Grafana baseline rule. Mirrors its arithmetic.

    ``baselines`` carries each cell's trailing peak; a cell with no observed
    baseline, folded language or too little volume cannot fire.
    """
    firing = []
    for (route, language), (admitted, delivered) in sorted(cells_by_key.items()):
        value, baseline = share(admitted, delivered), baselines.get((route, language))
        if language in (OTHER, UNKNOWN) or admitted < MIN_VOLUME or baseline is None:
            continue
        if value is not None and value < BASELINE_FACTOR * baseline:
            firing.append((route, language, value, baseline))
    return firing


class DeliveredShare:
    """Leader-owned sampler; the metrics registry owns collection."""

    def __init__(self, registry):
        self._lock = threading.Lock()
        self._refresh_lock = threading.Lock()
        self._due = 0.0
        self._observed = None
        self._sample = None
        self._active = False
        registry.register(self)

    def describe(self):
        for name, help_text in METRICS.items():
            yield GaugeMetricFamily(PREFIX + name, help_text)

    def deactivate(self):
        with self._lock:
            self._active = False
            self._sample = None

    def refresh(self, store):
        # One page in flight per process; a second reconcile tick skips.
        if not self._refresh_lock.acquire(blocking=False):
            return
        try:
            with self._lock:
                if not enabled():
                    self._active = False
                    self._sample = None
                    return
                self._active = True
                if time.monotonic() < self._due:
                    return
                self._due = time.monotonic() + SAMPLE_SECONDS
                self._sample = None
            try:
                rows, truncated = delivered_share_page(store.client, store.namespace, time.time())
                sample = (cells(rows), truncated)
                with self._lock:
                    self._sample = sample
                    self._observed = time.monotonic()
            except Exception as error:
                logging.getLogger(__name__).warning(
                    'event=batch_delivered_share outcome=retry exception_type=%s', type(error).__name__
                )
        finally:
            self._refresh_lock.release()

    def collect(self):
        with self._lock:
            if not enabled() or not self._active or self._observed is None:
                return
            age = max(0.0, time.monotonic() - self._observed)
            sample = self._sample
        yield GaugeMetricFamily(PREFIX + 'sample_age_seconds', METRICS['sample_age_seconds'], value=age)
        # Counts and ratio expire even if supervision stops; the age alone
        # keeps publishing so a stalled sampler is visible, never a healthy 0.
        if sample is None or age >= FRESH_SECONDS:
            return
        by_key, truncated = sample
        yield GaugeMetricFamily(PREFIX + 'truncated', METRICS['truncated'], value=1 if truncated else 0)
        admitted_family = GaugeMetricFamily(
            PREFIX + 'admitted_units', METRICS['admitted_units'], labels=['route', 'language']
        )
        delivered_family = GaugeMetricFamily(PREFIX + 'units', METRICS['units'], labels=['route', 'language'])
        ratio_family = GaugeMetricFamily(PREFIX + 'ratio', METRICS['ratio'], labels=['route', 'language'])
        for (route, language), (admitted, delivered) in sorted(by_key.items()):
            admitted_family.add_metric([route, language], admitted)
            delivered_family.add_metric([route, language], delivered)
            value = share(admitted, delivered)
            # An empty cohort has no ratio; a zero denominator is not a healthy zero.
            if value is not None:
                ratio_family.add_metric([route, language], value)
        yield admitted_family
        yield delivered_family
        if ratio_family.samples:
            yield ratio_family
