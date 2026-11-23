"""Export bounded device-signal gauges from durable collector aggregates."""

import logging
import os
from datetime import datetime, timedelta, timezone
from collections.abc import Iterator
from threading import Lock

from prometheus_client import REGISTRY
from prometheus_client.core import GaugeMetricFamily, Metric

from database._client import get_firestore_client
from database.device_signals import load_hour_snapshot

logger = logging.getLogger(__name__)


class DeviceSignalCollector:
    def __init__(self) -> None:
        self._lock = Lock()
        self._refresh_after = datetime.min.replace(tzinfo=timezone.utc)
        self._snapshot = None

    def describe(self) -> tuple[GaugeMetricFamily, ...]:
        return self._metrics()

    @staticmethod
    def _metrics() -> (
        tuple[GaugeMetricFamily, GaugeMetricFamily, GaugeMetricFamily, GaugeMetricFamily, GaugeMetricFamily]
    ):
        return (
            GaugeMetricFamily("omi_client_device_signal_hour_start_seconds", "UTC start of the exported hour"),
            GaugeMetricFamily(
                "omi_client_device_signal_reporting_owners", "Owners reporting device coverage in the hour"
            ),
            GaugeMetricFamily("omi_client_device_signal_baseline_hours", "Prior hours with device coverage"),
            GaugeMetricFamily(
                "omi_client_device_signal_hourly_owners", "Distinct owners in the exported hour", labels=["signal"]
            ),
            GaugeMetricFamily(
                "omi_client_device_signal_baseline_owners",
                "Median per positive covered baseline hour",
                labels=["signal"],
            ),
        )

    def collect(self) -> Iterator[Metric]:
        with self._lock:
            now = datetime.now(timezone.utc)
            if now >= self._refresh_after:
                try:
                    self._snapshot = load_hour_snapshot(get_firestore_client(), now)
                    # Pick up the new closed hour at :10 even if the cache is still fresh.
                    self._refresh_after = now.replace(second=0, microsecond=0) + timedelta(minutes=5 - now.minute % 5)
                except Exception:
                    logger.warning("device signal export failed", exc_info=True)
                    self._snapshot = None
                    self._refresh_after = now + timedelta(seconds=30)
            snapshot = self._snapshot
        if snapshot is None:
            return

        hour, owners, baseline_hours, values = snapshot
        start, reporting, history, counts, medians = self._metrics()
        start.add_metric([], hour.timestamp())
        reporting.add_metric([], owners)
        history.add_metric([], baseline_hours)
        if owners:
            for signal, (count, baseline) in values.items():
                counts.add_metric([signal], count)
                medians.add_metric([signal], baseline)
        yield from (start, reporting, history, counts, medians)


_collector = DeviceSignalCollector()


def register_device_signal_metrics() -> None:
    if os.environ.get("CLIENT_TELEMETRY_DEVICE_SIGNALS_EXPORT", "").strip().lower() != "on":
        return
    try:
        REGISTRY.register(_collector)
    except ValueError:
        # App startup can run again in the same process.
        return
