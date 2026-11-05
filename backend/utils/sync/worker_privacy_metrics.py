"""Retain privacy counters across isolated job exits, including SIGKILL.

The child selects Prometheus mmap values before its first import. Only one
child runs at a time. The supervisor scrapes its live counters and folds the
final snapshot after reaping the entire process group, then removes its owned
temporary directory. Storage is bounded by metric cardinality, not job count.
"""

from collections import defaultdict
from collections.abc import Iterator
import os
import tempfile

from prometheus_client import CollectorRegistry, generate_latest, multiprocess
from prometheus_client.core import Metric
from prometheus_client.registry import Collector

COUNTERS = frozenset(
    {
        'privacy_checks',
        'privacy_check_calls',
        'privacy_check_reads',
        'privacy_conversations_walked',
        'privacy_decision_mismatch',
        'privacy_shadow_checks',
        'privacy_memo_requests',
        'privacy_memo_ineligible',
    }
)


MetricKey = tuple[str, str, str, tuple[tuple[str, str], ...]]


class WorkerPrivacyMetrics(Collector):
    def __init__(self):
        self._directory: tempfile.TemporaryDirectory[str] | None = None
        self._totals: defaultdict[MetricKey, float] = defaultdict(float)

    def begin_job(self) -> dict[str, str]:
        assert self._directory is None
        self._directory = tempfile.TemporaryDirectory(prefix='sync-worker-privacy-')
        return {**os.environ, 'PROMETHEUS_MULTIPROC_DIR': self._directory.name}

    def _snapshot(self) -> dict[MetricKey, float]:
        if self._directory is None:
            return {}
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry, path=self._directory.name)
        return {
            (metric.name, metric.documentation, sample.name, tuple(sorted(sample.labels.items()))): sample.value
            for metric in registry.collect()
            if metric.type == 'counter' and metric.name in COUNTERS
            for sample in metric.samples
            if sample.name == metric.name + '_total'
        }

    def finish_job(self) -> None:
        # Called only after child AND executor leaves have been killed/reaped.
        for key, value in self._snapshot().items():
            self._totals[key] += value
        if self._directory is not None:
            self._directory.cleanup()
            self._directory = None

    def collect(self) -> Iterator[Metric]:
        totals = self._totals.copy()
        for key, value in self._snapshot().items():
            totals[key] += value
        metrics: dict[str, Metric] = {}
        for (name, documentation, sample, labels), value in totals.items():
            metric = metrics.setdefault(name, Metric(name, documentation, 'counter'))
            metric.add_sample(sample, dict(labels), value)
        yield from metrics.values()

    def render(self) -> bytes:
        registry = CollectorRegistry()
        registry.register(self)
        return generate_latest(registry)
