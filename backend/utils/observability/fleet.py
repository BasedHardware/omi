"""Bounded fleet counters and cumulative histogram deltas (no invented sums)."""

from collections.abc import Iterable
from threading import Lock
from typing import Any

from prometheus_client import REGISTRY, Counter
from prometheus_client.core import CounterMetricFamily, Metric
from prometheus_client.registry import Collector

from config.fleet_telemetry import REASONS, registry

EVENTS = Counter(
    'omi_client_events_total', 'Client aggregated event deltas.', ['event', 'outcome', 'platform', 'build_channel']
)
REJECTED = Counter('omi_client_telemetry_rejected_total', 'Rejected fleet beacon requests.', ['reason'])
UPLOADS = Counter(
    'omi_sync_upload_total',
    'Server-observed upload attempts: 202 is accepted, not completed.',
    ['outcome', 'platform', 'build_channel'],
)


class FleetHistograms(Collector):
    def __init__(self) -> None:
        self._lock = Lock()
        self._counts: dict[tuple[str, str, str], list[int]] = {}

    def describe(self) -> Iterable[Metric]:
        # Avoid schema/file IO when the global registry registers the collector.
        return []

    def add(self, name: str, platform: str, channel: str, buckets: list[dict[str, Any]]) -> None:
        with self._lock:
            key = (name, platform, channel)
            current = self._counts.setdefault(key, [0] * len(buckets))
            for index, bucket in enumerate(buckets):
                current[index] += bucket['count']

    def collect(self) -> Iterable[Metric]:
        with self._lock:
            snapshot = {key: list(value) for key, value in self._counts.items()}
        families: dict[str, tuple[CounterMetricFamily, CounterMetricFamily]] = {}
        for (name, platform, channel), counts in snapshot.items():
            buckets, total = families.setdefault(
                name,
                (
                    CounterMetricFamily(
                        'omi_client_' + name + '_bucket',
                        'Client cumulative bucket deltas; exact sum unavailable.',
                        labels=['platform', 'build_channel', 'le'],
                    ),
                    CounterMetricFamily(
                        'omi_client_' + name + '_count',
                        'Client histogram observation deltas.',
                        labels=['platform', 'build_channel'],
                    ),
                ),
            )
            # GMP drops histogram families without a sum. These are independent
            # counters because bucket deltas cannot recover the measured sum.
            edges = registry()['histograms'][name]['buckets']
            for edge, count in zip(edges, counts):
                buckets.add_metric([platform, channel, str(edge)], count)
            total.add_metric([platform, channel], counts[-1])
        for pair in families.values():
            yield from pair


HISTOGRAMS = FleetHistograms()
REGISTRY.register(HISTOGRAMS)


def reject(reason):
    if reason not in REASONS:
        raise ValueError('unregistered fleet rejection')
    REJECTED.labels(reason=reason).inc()


def record_summary(payload):
    platform, channel = payload['platform'], payload['build_channel']
    for item in payload['counters']:
        EVENTS.labels(item['event'], item['outcome'], platform, channel).inc(item['count'])
    for item in payload['histograms']:
        HISTOGRAMS.add(item['name'], platform, channel, item['buckets'])


def record_upload(outcome, platform, channel):
    spec = registry()
    platform = platform.lower() if isinstance(platform, str) else 'unknown'
    channel = channel.lower() if isinstance(channel, str) else 'unknown'
    UPLOADS.labels(
        outcome,
        platform if platform in spec['platforms'] else 'unknown',
        channel if channel in spec['build_channels'] else 'unknown',
    ).inc()
