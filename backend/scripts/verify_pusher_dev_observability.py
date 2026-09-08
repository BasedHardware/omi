#!/usr/bin/env python3
"""Keep Pusher dev-bake telemetry visible without treating health as success.

This source-only gate proves the development Prometheus instance has
namespace- and environment-isolated Pusher and backend-listen scrapes.  Its
dashboard must expose connection, drain, reconnect/recovery, circuit-breaker,
and scrape-target health aggregates. It deliberately does not query a live
Prometheus API or generate traffic.
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
    "pusher_sessions_degraded",
)
DEV_NAMESPACE = "dev-omi-backend"
DEV_ENVIRONMENT = "dev"
SCRAPE_JOBS = {
    "pusher-metrics": "pusher",
    "backend-listen-metrics": "backend-listen",
}
DEV_WORKLOAD_VALUES = {
    PUSHER_VALUES: "pusher",
    ROOT / "backend/charts/backend-listen/dev_omi_backend_listen_values.yaml": "backend-listen",
}


def scrape_block(values: str, job_name: str) -> str | None:
    match = re.search(rf"(?ms)^\s*- job_name: {re.escape(job_name)}\n(?P<block>.*?)(?=^\s*- job_name:|\Z)", values)
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
    for values_path, workload in DEV_WORKLOAD_VALUES.items():
        workload_values = (root / values_path.relative_to(ROOT)).read_text(encoding="utf-8")
        for annotation in (
            'prometheus.io/scrape: "true"',
            'prometheus.io/port: "8080"',
            'prometheus.io/path: "/metrics"',
        ):
            if annotation not in workload_values:
                errors.append(f"dev {workload} chart must keep {annotation} for the isolated development scrape")
        if f"podLabels:\n  env: {DEV_ENVIRONMENT}" not in workload_values:
            errors.append(f"dev {workload} chart must label its scrape target env: {DEV_ENVIRONMENT}")

    monitoring_values = (root / DEV_VALUES.relative_to(ROOT)).read_text(encoding="utf-8")
    for job_name, workload in SCRAPE_JOBS.items():
        scrape = scrape_block(monitoring_values, job_name)
        if scrape is None:
            errors.append(f"development Prometheus must define the {job_name} scrape job")
            continue
        for fragment in (
            "credentials_file: /etc/prometheus/secrets/metrics-scrape-token/token",
            f"names:\n              - {DEV_NAMESPACE}",
            "__meta_kubernetes_namespace",
            f"regex: {DEV_NAMESPACE}",
            "__meta_kubernetes_pod_label_env",
            f"regex: {DEV_ENVIRONMENT}",
            "target_label: environment",
            f"regex: {workload}",
        ):
            if fragment not in scrape:
                errors.append(f"development {job_name} scrape must include {fragment!r}")

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
        if 'up{job=~"pusher-metrics|backend-listen-metrics"}' not in expressions:
            errors.append("Pusher dashboard must expose the isolated scrape target health aggregate")
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
