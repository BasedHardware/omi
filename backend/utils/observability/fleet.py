"""Bounded fleet counters and cumulative histogram deltas (no invented sums)."""

from threading import Lock

from prometheus_client import REGISTRY, Counter
from prometheus_client.core import HistogramMetricFamily

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


class FleetHistograms:
    def __init__(self):
        self._lock = Lock()
        self._counts = {}

    def describe(self):
        # Avoid schema/file IO when the global registry registers the collector.
        return []

    def add(self, name, platform, channel, buckets):
        with self._lock:
            key = (name, platform, channel)
            current = self._counts.setdefault(key, [0] * len(buckets))
            for index, bucket in enumerate(buckets):
                current[index] += bucket['count']

    def collect(self):
        with self._lock:
            snapshot = {key: list(value) for key, value in self._counts.items()}
        families = {}
        for (name, platform, channel), counts in snapshot.items():
            family = families.setdefault(
                name,
                HistogramMetricFamily(
                    'omi_client_' + name,
                    'Client cumulative bucket deltas; sum unavailable.',
                    labels=['platform', 'build_channel'],
                ),
            )
            edges = registry()['histograms'][name]['buckets']
            family.add_metric([platform, channel], [[str(edge), count] for edge, count in zip(edges, counts)], None)
            family.add_sample(family.name + '_count', {'platform': platform, 'build_channel': channel}, counts[-1])
        yield from families.values()


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
