"""Device Signals collector and committed Grafana rule coverage."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import shutil
import subprocess
from uuid import uuid4

import pytest

from config.client_telemetry import TelemetryContractError
from database.client_telemetry import accept_batch
from database.device_signals import load_hour_snapshot
from scripts.alert_backtest import evaluate
from tests.unit.fixtures.telemetry_memory_firestore import TelemetryMemoryFirestore
from utils import device_signal_metrics

NOW = datetime(2026, 11, 23, 12, 30, tzinfo=timezone.utc)
RULES = Path(__file__).resolve().parents[2] / "charts/monitoring/alerts/device-signals-prometheus.json"


class DeviceSignalStore(TelemetryMemoryFirestore):
    def get_all(self, refs, **kwargs):
        return (ref.get() for ref in refs)


def observation(event, *, ago=timedelta(hours=1), **attributes):
    return {
        "event_id": str(uuid4()),
        "occurred_at": (NOW - ago).isoformat(),
        "platform": "ios",
        "channel": "production",
        "family": "device_signal",
        "attributes": {"event": event, **attributes},
    }


def submit(db, owner, *observations):
    return accept_batch(
        owner,
        {"schema_version": 1, "batch_id": str(uuid4()), "observations": list(observations)},
        firestore_client=db,
        now=NOW,
    )


def test_distinct_counts_follow_event_hour_across_retries_and_concurrent_batches():
    db = DeviceSignalStore()
    earlier = timedelta(hours=2)
    payload = (
        observation("heartbeat"),
        observation("heartbeat", ago=earlier),
        observation("local_wal_stuck", over_age=True, over_count=True),
        observation("local_wal_stuck", ago=earlier),
        observation("recording_start_failed"),
        observation("upload_failed"),
        observation("capture_wedge_detected", block_reason="count_cap"),
        observation("capture_wedge_detected", block_reason="disk_reserve"),
        observation("capture_wedge_detected", block_reason="other"),
        observation("capture_wedge_detected"),
    )
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda owner: submit(db, owner, *payload), ["alice", "bob", "alice", "bob"]))
    assert sum(result["accepted_count"] for result in results) == 2 * len(payload)
    # Fresh ID for the same owner/hour must not inflate distinct counts.
    submit(db, "alice", observation("local_wal_stuck"))
    # Hour with a signal but no heartbeat is not part of the covered baseline.
    submit(db, "charlie", observation("recording_start_failed", ago=earlier + timedelta(hours=1)))

    hour, owners, baseline_hours, observed = load_hour_snapshot(db, NOW)
    assert hour == NOW.replace(hour=11, minute=0)
    assert owners == 2 and baseline_hours == 1
    for signal in (
        "local_wal_stuck",
        "wal_backlog_age_24h",
        "wal_backlog_over_cap",
        "recording_start_failed",
        "upload_failed",
        "capture_wedge_detected",
        "wedge_count_cap",
        "wedge_disk_reserve",
        "wedge_other",
    ):
        assert observed[signal] == (2, 2 if signal == "local_wal_stuck" else 0)

    for attrs in ({"over_age": "true"}, {"pending_wal_count": 721}):
        with pytest.raises(TelemetryContractError):
            submit(db, "alice", observation("local_wal_stuck", **attrs))


def test_export_distinguishes_empty_covered_hour_from_no_coverage_or_read_failure(monkeypatch):
    class FixedClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW

    db = DeviceSignalStore()
    monkeypatch.setattr(device_signal_metrics, "datetime", FixedClock)
    monkeypatch.setattr(device_signal_metrics, "get_firestore_client", lambda: db)

    def collect():
        return {metric.name: metric.samples for metric in device_signal_metrics.DeviceSignalCollector().collect()}

    metric = "omi_client_device_signal_hourly_owners"
    assert not collect()[metric]
    submit(db, "reporting-owner", observation("heartbeat"))
    assert collect()[metric] and all(sample.value == 0 for sample in collect()[metric])

    def failed(*args, **kwargs):
        raise OSError("test Firestore failure")

    monkeypatch.setattr(db, "get_all", failed)
    assert collect() == {}


def test_eight_device_signal_rules_fire_with_prometheus_and_grafana(tmp_path):
    promtool = shutil.which("promtool")
    if not promtool:
        pytest.skip("promtool is required for PromQL execution")
    rules = json.loads(RULES.read_text())
    floors = {
        "local_wal_stuck": 10,
        "recording_start_failed": 10,
        "upload_failed": 10,
        "wal_backlog_age_24h": 5,
        "wal_backlog_over_cap": 5,
        "wedge_count_cap": 10,
        "wedge_disk_reserve": 5,
        "wedge_other": 10,
    }
    assert len(rules) == len(floors)
    cases = []
    for rule, (signal, floor) in zip(rules, floors.items(), strict=True):
        expr = rule["data"][0]["model"]["expr"]
        for count, baseline, coverage, hour, expected in (
            (floor + 1, 2, 1, 0, 1),
            (floor, 2, 1, 0, 0),
            (floor + 2, (floor + 2) / 2, 1, 0, 0),
            (0, 0, 1, 0, 0),
            (floor + 1, 2, 0, 0, None),
            (floor + 1, 2, 1, -3600, None),
        ):
            frames = {"A": {(): [expected]} if expected is not None else {}}
            assert evaluate(rule, frames) == ({(): float(expected)} if expected is not None else {})
            metrics = {
                f'omi_client_device_signal_hourly_owners{{signal="{signal}"}}': count,
                f'omi_client_device_signal_baseline_owners{{signal="{signal}"}}': baseline,
                "omi_client_device_signal_hour_start_seconds": hour,
                "omi_client_device_signal_reporting_owners": coverage,
            }
            cases.append(
                {
                    "interval": "15m",
                    "input_series": [{"series": series, "values": f"{value}+0x5"} for series, value in metrics.items()],
                    "promql_expr_test": [
                        {
                            "expr": expr,
                            "eval_time": "75m",
                            "exp_samples": [{"labels": "{}", "value": expected}] if expected is not None else [],
                        }
                    ],
                }
            )
    fixture = tmp_path / "device-signals.yaml"
    fixture.write_text(json.dumps({"evaluation_interval": "15m", "tests": cases}))
    subprocess.run([promtool, "test", "rules", str(fixture)], check=True)
