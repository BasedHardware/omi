"""Cached export of durable retry counts; replicas mirror, never sum them."""

from threading import Lock

from prometheus_client import REGISTRY
from prometheus_client.core import CounterMetricFamily, GaugeMetricFamily
from prometheus_client.registry import Collector

from utils.observability.reasons import BatchFinalPassOutcome


class RetryTerminals(Collector):
    def __init__(self):
        self._lock = Lock()
        self._shards = {}
        self._observed_at = None

    def describe(self):
        return [
            CounterMetricFamily(
                'omi_transcription_final_pass_retry_terminal', 'Durable retry outcomes.', labels=['outcome']
            ),
            GaugeMetricFamily(
                'omi_transcription_final_pass_retry_terminal_observed_at_seconds', 'Last durable refresh.'
            ),
        ]

    def publish(self, shards, *, observed_at):
        # Refreshes can overlap. Neither an older snapshot nor a partial shard
        # read may lower a previously observed cumulative counter.
        with self._lock:
            for shard, counts in shards.items():
                current = self._shards.setdefault(shard, {})
                for outcome, count in counts.items():
                    current[outcome] = max(current.get(outcome, 0), count)
            self._observed_at = max(self._observed_at or 0, observed_at)

    def collect(self):
        with self._lock:
            observed_at = self._observed_at
            totals = dict.fromkeys(['success', *(outcome.value for outcome in BatchFinalPassOutcome)], 0)
            for counts in self._shards.values():
                for outcome, count in counts.items():
                    if outcome in totals:
                        totals[outcome] += count
        if observed_at is None:
            return
        counter, freshness = self.describe()
        for outcome, count in totals.items():
            counter.add_metric([outcome], count)
        freshness.add_metric([], observed_at)
        yield counter
        yield freshness


TERMINALS = RetryTerminals()
REGISTRY.register(TERMINALS)
