"""Pure capacity tests for the read-only live Pusher deployment gate."""

from __future__ import annotations

import runpy
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "verify_pusher_live_deployment_gate.py"


@pytest.fixture(scope="module")
def gate() -> SimpleNamespace:
    return SimpleNamespace(**runpy.run_path(str(SCRIPT)))


def node(*, cpu: str = "4", memory: str = "16Gi", labels: dict[str, str] | None = None, ready: bool = True) -> dict:
    return {
        "metadata": {"name": "pusher-node", "labels": labels or {"service": "pusher", "env": "prod", "version": "v3"}},
        "spec": {},
        "status": {
            "allocatable": {"cpu": cpu, "memory": memory},
            "conditions": [{"type": "Ready", "status": "True" if ready else "False"}],
        },
    }


def desired(*, max_surge: int = 2) -> dict:
    return {
        "spec": {
            "strategy": {"rollingUpdate": {"maxSurge": max_surge}},
            "template": {
                "spec": {
                    "affinity": {
                        "nodeAffinity": {
                            "requiredDuringSchedulingIgnoredDuringExecution": {
                                "nodeSelectorTerms": [
                                    {
                                        "matchExpressions": [
                                            {"key": "service", "operator": "In", "values": ["pusher"]},
                                            {"key": "env", "operator": "In", "values": ["prod"]},
                                            {"key": "version", "operator": "In", "values": ["v3"]},
                                        ]
                                    }
                                ]
                            }
                        }
                    },
                    "containers": [{"name": "pusher", "resources": {"requests": {"cpu": "700m", "memory": "4Gi"}}}],
                }
            },
        }
    }


def existing_pod(cpu: str, memory: str) -> dict:
    return {
        "spec": {
            "nodeName": "pusher-node",
            "containers": [{"resources": {"requests": {"cpu": cpu, "memory": memory}}}],
        },
        "status": {"phase": "Running"},
    }


def test_requires_exact_digest_identity(gate: SimpleNamespace) -> None:
    with pytest.raises(gate.GateError, match="exact repository@sha256"):
        gate.parse_image_reference("gcr.io/based-hardware/pusher:latest")


def test_render_fails_closed_when_digest_identity_is_not_preserved(
    gate: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    expected_digest = "a" * 64
    rendered_digest = "b" * 64
    rendered = f"""\
apiVersion: apps/v1
kind: Deployment
spec:
  template:
    spec:
      containers:
        - name: pusher
          image: gcr.io/example/pusher@sha256:{rendered_digest}
"""
    monkeypatch.setattr(
        gate.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout=rendered, stderr=""),
    )

    with pytest.raises(gate.GateError, match="did not preserve the exact requested digest identity"):
        gate.render_deployment(Path("."), "prod", f"gcr.io/example/pusher@sha256:{expected_digest}")


def test_kubectl_query_failure_fails_closed(gate: SimpleNamespace, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        gate.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1, stdout="", stderr="forbidden"),
    )

    with pytest.raises(gate.GateError, match="forbidden"):
        gate.kubectl_json(["get", "nodes"])


def test_reports_real_headroom_for_the_rendered_surge_wave(gate: SimpleNamespace) -> None:
    failures, evidence = gate.capacity_evidence(
        desired(), {"status": {"replicas": 12}}, [node()], [existing_pod("1", "4Gi")]
    )

    assert failures == []
    assert evidence["surge_pods"] == 2
    assert evidence["fitting_nodes"] == 1
    assert evidence["required_cpu_millicores"] == 1400
    assert evidence["required_memory_bytes"] == 8 * 1024**3


def test_fails_closed_when_matching_node_lacks_next_surge_capacity(gate: SimpleNamespace) -> None:
    failures, evidence = gate.capacity_evidence(
        desired(),
        {"status": {"replicas": 12}},
        [node(cpu="2", memory="10Gi")],
        [existing_pod("1", "4Gi")],
    )

    assert evidence["fitting_nodes"] == 0
    assert any("insufficient schedulable Pusher headroom" in failure for failure in failures)


def test_fails_closed_when_rendered_max_surge_is_zero(gate: SimpleNamespace) -> None:
    with pytest.raises(gate.GateError, match="at least one surge pod"):
        gate.capacity_evidence(desired(max_surge=0), {"status": {"replicas": 12}}, [node()], [])


def test_fails_closed_when_no_ready_node_matches_pusher_affinity(gate: SimpleNamespace) -> None:
    failures, evidence = gate.capacity_evidence(
        desired(),
        {"status": {"replicas": 12}},
        [node(labels={"service": "backend", "env": "prod", "version": "v3"})],
        [],
    )

    assert evidence == {}
    assert failures == ["no Ready, schedulable node satisfies the rendered Pusher node affinity and tolerations"]


def test_counts_init_container_peak_and_pod_overhead(gate: SimpleNamespace) -> None:
    pod = {
        "spec": {
            "containers": [{"resources": {"requests": {"cpu": "500m", "memory": "1Gi"}}}],
            "initContainers": [{"resources": {"requests": {"cpu": "900m", "memory": "2Gi"}}}],
            "overhead": {"cpu": "100m", "memory": "64Mi"},
        }
    }

    assert gate.pod_requests(pod) == gate.Resources(1000, 2 * 1024**3 + 64 * 1024**2)
