"""Production preflight compares only named, allowlisted resources."""

import json
import runpy
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/monitoring_preflight.py"


@pytest.fixture
def preflight():
    return SimpleNamespace(**runpy.run_path(str(SCRIPT)))


def test_preflight_only_reads_allowlisted_objects_and_reports_paths(preflight, monkeypatch, capsys):
    calls = []

    def run(argv, **kwargs):
        calls.append(argv)
        if argv[0] == "helm":
            return subprocess.CompletedProcess(
                argv,
                0,
                stdout="""\
apiVersion: v1
kind: Secret
metadata: {name: secret-name}
data: {token: secret-value}
---
apiVersion: v1
kind: ConfigMap
metadata: {name: monitoring-config}
data: {allowed.yaml: desired-private-value}
""",
            )
        return subprocess.CompletedProcess(
            argv,
            0,
            stdout=json.dumps(
                {
                    "apiVersion": "v1",
                    "kind": "ConfigMap",
                    "metadata": {"name": "monitoring-config", "resourceVersion": "1"},
                    "data": {"allowed.yaml": "live-private-value"},
                }
            ),
        )

    monkeypatch.setattr(subprocess, "run", run)
    assert preflight.compare_release("release", "chart", "1.2.3", [], "readonly-path")
    assert calls[0][:4] == ["helm", "template", "release", "chart"]
    assert calls[1] == [
        "kubectl",
        "--kubeconfig",
        "readonly-path",
        "--context",
        preflight.CONTEXT,
        "--namespace",
        preflight.NAMESPACE,
        "--request-timeout=15s",
        "get",
        "configmaps",
        "monitoring-config",
        "--ignore-not-found",
        "-o",
        "json",
    ]
    assert len(calls) == 2
    assert capsys.readouterr().out.splitlines() == [
        "release chart=chart version=1.2.3",
        '  prod-omi-monitoring ConfigMap/monitoring-config changed=["/data/allowed.yaml"]',
    ]


def test_preflight_release_pins(preflight):
    releases = list(preflight.release_renders())
    assert [(name, version) for name, _, version, _ in releases] == [
        ("prod-omi-cloud-run-sync-metrics-exporter", "4.8.3"),
        ("prod-omi-cloud-run-metrics-exporter", "4.8.3"),
        ("prod-omi-kube-prometheus-stack", "75.15.1"),
    ]
    assert any(flag.endswith("gmp/frontend-values.prod.yaml") for flag in releases[-1][-1])
    assert any(flag.startswith("grafana.podAnnotations.omi-stats-proxy-sha256=") for flag in releases[-1][-1])
