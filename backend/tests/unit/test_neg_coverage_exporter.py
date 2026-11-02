from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

from scripts.neg_coverage_exporter import (
    ApiError,
    CollectionError,
    CoverageCollector,
    NotFound,
    ZoneCoverage,
    compare_coverage,
    configured_zones,
)

PROJECT = "based-hardware"
BACKEND = "custom-domains-api-omi-me-backend-listen-49a4-be"
NEG = "prod-backend-listen-neg"


class FakeCompute:
    def __init__(self, groups: list[tuple[str, str]], endpoints: dict[tuple[str, str], set[str]], missing=()):
        self.groups = groups
        self.endpoints = endpoints
        self.missing = set(missing)
        self.calls: list[tuple[Any, ...]] = []

    def get_backend_service(self, name: str) -> dict[str, Any]:
        self.calls.append(("get_backend_service", name))
        assert name == BACKEND
        backends = [
            {
                "group": f"https://www.googleapis.com/compute/v1/projects/{PROJECT}/zones/{zone}/networkEndpointGroups/{group}"
            }
            for zone, group in self.groups
        ]
        return {"backends": backends}

    def get_zonal_neg(self, zone: str, name: str) -> dict[str, str]:
        self.calls.append(("get_zonal_neg", zone, name))
        if (zone, name) in self.missing:
            raise NotFound()
        return {"name": name}

    def list_network_endpoints(self, zone: str, name: str) -> set[str]:
        self.calls.append(("list_network_endpoints", zone, name))
        return set(self.endpoints.get((zone, name), set()))


class FakeKubernetes:
    def __init__(self, ready: dict[str, set[str]]):
        self.ready = ready

    def ready_pod_ips_by_zone(self) -> dict[str, set[str]]:
        return self.ready


def test_compare_coverage_intersects_ready_pod_ips_with_attached_endpoints():
    zones = ("us-central1-a", "us-central1-c", "us-central1-f")
    result = compare_coverage(
        zones,
        {"us-central1-a": {"10.0.0.1"}, "us-central1-c": {"10.0.0.2", "10.0.0.3"}},
        {"us-central1-a": {"10.0.0.1"}, "us-central1-c": {"10.0.0.2", "10.0.0.3"}},
        {"us-central1-c"},
        {"us-central1-a": {"10.0.0.1", "10.0.0.4"}, "us-central1-c": {"10.0.0.2", "10.0.0.5"}},
    )

    assert result == {
        "us-central1-a": ZoneCoverage(2, 1, 0, 1),
        "us-central1-c": ZoneCoverage(2, 1, 1, 2),
        "us-central1-f": ZoneCoverage(0, 0, 0, 0),
    }


def test_collector_reads_attached_negs_and_fixed_zone_negs_without_listing_negs():
    zones = ("us-central1-a", "us-central1-c", "us-central1-f")
    compute = FakeCompute(
        groups=[("us-central1-c", NEG)],
        endpoints={
            ("us-central1-a", NEG): {"10.0.0.1"},
            ("us-central1-c", NEG): {"10.0.0.2", "10.0.0.3"},
        },
        missing={("us-central1-f", NEG)},
    )
    collector = CoverageCollector(
        compute,
        FakeKubernetes({"us-central1-a": {"10.0.0.1", "10.0.0.4"}, "us-central1-c": {"10.0.0.2", "10.0.0.5"}}),
        PROJECT,
        zones,
    )

    result = collector.collect()

    assert result["us-central1-a"] == ZoneCoverage(2, 0, 0, 1)
    assert result["us-central1-c"] == ZoneCoverage(2, 1, 1, 2)
    assert result["us-central1-f"] == ZoneCoverage(0, 0, 0, 0)
    assert ("get_backend_service", BACKEND) in compute.calls
    assert all(("get_zonal_neg", zone, NEG) in compute.calls for zone in zones)
    assert compute.calls.count(("list_network_endpoints", "us-central1-c", NEG)) == 1
    assert ("list_network_endpoints", "us-central1-f", NEG) not in compute.calls
    assert all("list_zonal_negs" not in call for call in compute.calls)


def test_collector_rejects_attached_zones_outside_the_bounded_zone_set():
    compute = FakeCompute(groups=[("us-central1-b", NEG)], endpoints={})
    collector = CoverageCollector(compute, FakeKubernetes({}), PROJECT, ("us-central1-a",))

    with pytest.raises(CollectionError) as error:
        collector.collect()

    assert error.value.stage == "zone_config"
    assert not any(call[0] == "list_network_endpoints" for call in compute.calls)


def test_collector_exports_unattached_endpoints_when_backend_has_no_groups():
    compute = FakeCompute(
        groups=[],
        endpoints={("us-central1-a", NEG): {"10.0.0.9"}},
    )
    collector = CoverageCollector(compute, FakeKubernetes({}), PROJECT, ("us-central1-a",))

    result = collector.collect()

    assert result["us-central1-a"] == ZoneCoverage(0, 0, 0, 1)


def test_collector_does_not_treat_non_404_neg_errors_as_absent():
    class ForbiddenCompute(FakeCompute):
        def get_zonal_neg(self, zone: str, name: str) -> dict[str, str]:
            raise ApiError(403)

    compute = ForbiddenCompute(groups=[("us-central1-a", NEG)], endpoints={})
    collector = CoverageCollector(compute, FakeKubernetes({}), PROJECT, ("us-central1-a",))

    with pytest.raises(CollectionError) as error:
        collector.collect()

    assert error.value.stage == "zone_neg"


def test_configured_zones_are_unique_valid_and_bounded():
    assert configured_zones(None) == ("us-central1-a", "us-central1-b", "us-central1-c", "us-central1-f")
    with pytest.raises(ValueError):
        configured_zones("us-central1-a,us-central1-a")
    with pytest.raises(ValueError):
        configured_zones(",".join(f"us-central1-{chr(97 + index)}" for index in range(13)))


def test_exporter_metrics_have_only_bounded_stage_and_zone_labels():
    from prometheus_client import generate_latest

    from scripts.neg_coverage_exporter import CoverageMetrics, STAGES

    metrics = CoverageMetrics()
    metrics.update({"us-central1-a": ZoneCoverage(5, 4, 1, 5)}, 123.0)
    rendered = generate_latest(metrics.registry).decode()

    for name in (
        "omi_listen_lb_ready_pods",
        "omi_listen_lb_attached_ready_endpoints",
        "omi_listen_lb_neg_attached",
        "omi_listen_lb_neg_endpoints",
        "omi_listen_lb_exporter_last_success_timestamp_seconds",
        "omi_listen_lb_exporter_errors_total",
    ):
        assert name in rendered
    assert 'zone="us-central1-a"' in rendered
    assert all(f'stage="{stage}"' in rendered for stage in STAGES)
    assert "endpoint_ip" not in rendered


def test_exporter_chart_does_not_render_kubernetes_rbac():
    repo_root = Path(__file__).resolve().parents[3]
    chart = repo_root / "backend/charts/monitoring/neg-coverage-exporter"
    result = subprocess.run(
        [
            "helm",
            "template",
            "prod-omi-neg-coverage-exporter",
            str(chart),
            "--namespace",
            "prod-omi-monitoring",
            "-f",
            str(chart / "prod-values.yaml"),
            "--set-string",
            "image.tag=test",
        ],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    resources = [doc for doc in yaml.safe_load_all(result.stdout) if doc]

    assert {resource["kind"] for resource in resources} == {
        "Deployment",
        "Service",
        "ServiceAccount",
        "ServiceMonitor",
    }
    assert not any(resource["apiVersion"].startswith("rbac.authorization.k8s.io/") for resource in resources)
