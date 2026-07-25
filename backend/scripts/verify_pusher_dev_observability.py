#!/usr/bin/env python3
"""Keep Pusher dev-bake telemetry visible without treating health as success.

This source-only gate proves the development Prometheus instance has an
environment-isolated Pusher scrape and that its dashboard exposes connection,
drain, and backend-listen reconnect-circuit signals.  It deliberately does not
query a live Prometheus API or generate traffic.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEV_VALUES = ROOT / "backend/charts/monitoring/kube-prometheus-stack/dev_omi_monitoring_values.yaml"
PUSHER_VALUES = ROOT / "backend/charts/pusher/dev_omi_pusher_values.yaml"
DASHBOARD = ROOT / "backend/charts/monitoring/dashboards/gke/pusher.json"
METRICS = ROOT / "backend/utils/metrics.py"
EXPECTED_METRICS = (
    "pusher_active_ws_connections",
    "pusher_ready",
    "pusher_drain_in_progress",
    "pusher_circuit_breaker_state",
    "pusher_circuit_breaker_rejections_total",
)


def pusher_scrape_block(values: str) -> str | None:
    match = re.search(r"(?ms)^\s*- job_name: pusher-metrics\n(?P<block>.*?)(?=^\s*- job_name:|\Z)", values)
    return match.group(0) if match else None


def dashboard_expressions(payload: dict) -> set[str]:
    expressions: set[str] = set()
    for panel in payload.get("panels", []):
        if not isinstance(panel, dict):
            continue
        for target in panel.get("targets", []):
            if isinstance(target, dict) and isinstance(target.get("expr"), str):
                expressions.add(target["expr"])
    return expressions


def validate(root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    pusher_values = (root / PUSHER_VALUES.relative_to(ROOT)).read_text(encoding="utf-8")
    for annotation in ('prometheus.io/scrape: "true"', 'prometheus.io/port: "8080"', 'prometheus.io/path: "/metrics"'):
        if annotation not in pusher_values:
            errors.append(f"dev Pusher chart must keep {annotation} for the isolated development scrape")

    scrape = pusher_scrape_block((root / DEV_VALUES.relative_to(ROOT)).read_text(encoding="utf-8"))
    if scrape is None:
        errors.append("development Prometheus must define the pusher-metrics scrape job")
    else:
        for fragment in (
            "credentials_file: /etc/prometheus/secrets/metrics-scrape-token/token",
            "__meta_kubernetes_pod_annotation_prometheus_io_scrape",
            "regex: pusher",
        ):
            if fragment not in scrape:
                errors.append(f"development pusher-metrics scrape must include {fragment!r}")

    metric_text = (root / METRICS.relative_to(ROOT)).read_text(encoding="utf-8")
    for metric in EXPECTED_METRICS:
        if f"'{metric}'" not in metric_text:
            errors.append(f"Pusher dev-bake dashboard signal {metric!r} is not emitted")

    try:
        dashboard = json.loads((root / DASHBOARD.relative_to(ROOT)).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"Pusher dashboard is not valid JSON: {exc}")
    else:
        expressions = "\n".join(dashboard_expressions(dashboard))
        for metric in EXPECTED_METRICS:
            if metric not in expressions:
                errors.append(f"Pusher dashboard must expose development-visible {metric!r}")
    return errors


def main() -> int:
    errors = validate()
    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        return 1
    print("OK: dev Pusher bake has isolated scrape and connection/drain/reconnect visibility.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
