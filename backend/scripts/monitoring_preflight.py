#!/usr/bin/env python3
"""Render the pinned production monitoring releases and compare desired fields.

The caller supplies an already-authorized read-only kubeconfig. Only named
reads of the allowlisted resources are performed. The comparison ignores
server-added map keys and cannot predict Helm deletions or admission effects.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CHARTS = ROOT / "backend/charts/monitoring"
NAMESPACE = "prod-omi-monitoring"
CONTEXT = "gke_based-hardware_us-central1_prod-omi-gke"
CHART_REPO = "https://prometheus-community.github.io/helm-charts"
RESOURCES = {
    ("v1", "ConfigMap"): "configmaps",
    ("v1", "Service"): "services",
    ("apps/v1", "Deployment"): "deployments.apps",
    ("apps/v1", "StatefulSet"): "statefulsets.apps",
    ("apps/v1", "DaemonSet"): "daemonsets.apps",
    ("monitoring.coreos.com/v1", "ServiceMonitor"): "servicemonitors.monitoring.coreos.com",
    ("monitoring.coreos.com/v1", "PrometheusRule"): "prometheusrules.monitoring.coreos.com",
    ("monitoring.coreos.com/v1", "Prometheus"): "prometheuses.monitoring.coreos.com",
    ("monitoring.coreos.com/v1", "Alertmanager"): "alertmanagers.monitoring.coreos.com",
}
KUBE_NAME = re.compile(r"[a-z0-9](?:[-.a-z0-9]*[a-z0-9])?")
MISSING = object()


def release_renders():
    exporters = CHARTS / "prometheus-stackdriver-exporter"
    proxy_hash = hashlib.sha256((CHARTS / "grafana/stats_proxy.py").read_bytes()).hexdigest()
    yield (
        "prod-omi-cloud-run-sync-metrics-exporter",
        "prometheus-stackdriver-exporter",
        "4.8.3",
        ["--values", str(exporters / "prod_sync_omi_cloud_run_metrics_exporter.yaml")],
    )
    yield (
        "prod-omi-cloud-run-metrics-exporter",
        "prometheus-stackdriver-exporter",
        "4.8.3",
        ["--values", str(exporters / "prod_omi_cloud_run_metrics_exporter.yaml")],
    )
    yield (
        "prod-omi-kube-prometheus-stack",
        "kube-prometheus-stack",
        "75.15.1",
        [
            "--values",
            str(CHARTS / "kube-prometheus-stack/prod_omi_monitoring_values.yaml"),
            "--values",
            str(CHARTS / "gmp/frontend-values.prod.yaml"),
            "--set-string",
            f"grafana.podAnnotations.omi-stats-proxy-sha256={proxy_hash}",
        ],
    )


def desired_objects(rendered: str):
    for obj in yaml.safe_load_all(rendered):
        if not obj:
            continue
        kind = obj["kind"]
        resource = RESOURCES.get((obj["apiVersion"], kind))
        if resource is None:
            continue
        metadata = obj["metadata"]
        name = metadata["name"]
        if not isinstance(name, str) or not KUBE_NAME.fullmatch(name):
            raise ValueError("invalid rendered name")
        namespace = metadata.get("namespace", NAMESPACE)
        if namespace != NAMESPACE and (namespace, kind) != ("kube-system", "Service"):
            raise ValueError("unexpected rendered namespace")
        yield resource, kind, namespace, name, obj


def changed_paths(desired, live, path=""):
    if type(desired) is not type(live):
        yield path
    elif isinstance(desired, dict):
        for key, value in sorted(desired.items()):
            segment = key.replace("~", "~0").replace("/", "~1")
            yield from changed_paths(value, live.get(key, MISSING), f"{path}/{segment}")
    elif isinstance(desired, list):
        if len(desired) != len(live):
            yield path
        else:
            for i, (planned, current) in enumerate(zip(desired, live)):
                yield from changed_paths(planned, current, f"{path}/{i}")
    elif desired != live:
        yield path


def compare_release(release, chart, version, flags, kubeconfig):
    render = subprocess.run(
        [
            "helm",
            "template",
            release,
            chart,
            "--repo",
            CHART_REPO,
            "--version",
            version,
            "--namespace",
            NAMESPACE,
            *flags,
        ],
        capture_output=True,
        text=True,
        timeout=120,
        check=True,
    )
    objects = list(desired_objects(render.stdout))
    if not objects:
        raise ValueError("no comparable monitoring objects")
    print(f"{release} chart={chart} version={version}")
    for resource, kind, namespace, name, desired in objects:
        identity = f"{namespace} {kind}/{name}"
        try:
            result = subprocess.run(
                [
                    "kubectl",
                    "--kubeconfig",
                    str(kubeconfig),
                    "--context",
                    CONTEXT,
                    "--namespace",
                    namespace,
                    "--request-timeout=15s",
                    "get",
                    resource,
                    name,
                    "--ignore-not-found",
                    "-o",
                    "json",
                ],
                capture_output=True,
                text=True,
                timeout=20,
                check=True,
            )
            if not result.stdout.strip():
                print(f"  {identity} absent")
                continue
            live = json.loads(result.stdout)
            if not isinstance(live, dict) or live.get("metadata", {}).get("name") != name or live.get("kind") != kind:
                raise ValueError("unexpected live object")
            paths = list(changed_paths(desired, live))
        except (subprocess.SubprocessError, OSError, ValueError, AttributeError, TypeError):
            print(f"  {identity} read failed")
            return False
        print(f"  {identity} changed={json.dumps(paths)}" if paths else f"  {identity} matches")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kubeconfig", type=Path, required=True, help="production read-only kubeconfig")
    args = parser.parse_args()
    if not args.kubeconfig.is_file():
        parser.error("production read-only kubeconfig is missing")
    passed = True
    for release, chart, version, flags in release_renders():
        try:
            passed &= compare_release(release, chart, version, flags, args.kubeconfig)
        except (subprocess.SubprocessError, yaml.YAMLError, OSError, ValueError, KeyError, TypeError):
            print(f"{release} render or validation failed")
            passed = False
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
