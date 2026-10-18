#!/usr/bin/env python3
"""Export backend-listen NEG endpoint coverage for the production LB."""

from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass
from typing import Any, Mapping, Protocol
from urllib.parse import quote

from prometheus_client import CollectorRegistry, Counter, Gauge, start_http_server

DEFAULT_ZONES = ("us-central1-a", "us-central1-b", "us-central1-c", "us-central1-f")
ZONE_PATTERN = re.compile(r"^[a-z]+(?:-[a-z0-9]+)+-[a-z]$")
MAX_ZONES = 12
BACKEND_SERVICE = "custom-domains-api-omi-me-backend-listen-49a4-be"
NEG_NAME = "prod-backend-listen-neg"
POD_SELECTOR = "app.kubernetes.io/instance=prod-omi-backend-listen"
KUBE_SA_DIR = "/var/run/secrets/kubernetes.io/serviceaccount"
COMPUTE_SCOPE = "https://www.googleapis.com/auth/cloud-platform"
STAGES = (
    "backend_service",
    "zone_config",
    "attached_endpoints",
    "zone_neg",
    "zone_endpoints",
    "pods",
    "nodes",
    "unexpected",
)
LOG = logging.getLogger("neg_coverage_exporter")


class ApiError(RuntimeError):
    def __init__(self, status_code: int, message: str = "API request failed") -> None:
        super().__init__(message)
        self.status_code = status_code


class CollectionError(RuntimeError):
    def __init__(self, stage: str) -> None:
        if stage not in STAGES:
            stage = "unexpected"
        super().__init__(stage)
        self.stage = stage


class NotFound(ApiError):
    def __init__(self) -> None:
        super().__init__(404, "resource not found")


class ComputeReader(Protocol):
    def get_backend_service(self, name: str) -> Mapping[str, Any]: ...

    def get_zonal_neg(self, zone: str, name: str) -> Mapping[str, Any]: ...

    def list_network_endpoints(self, zone: str, name: str) -> set[str]: ...


class KubernetesReader(Protocol):
    def ready_pod_ips_by_zone(self) -> dict[str, set[str]]: ...


@dataclass(frozen=True)
class ZoneCoverage:
    ready_pods: int
    attached_ready_endpoints: int
    neg_attached: int
    neg_endpoints: int


def configured_zones(raw: str | None) -> tuple[str, ...]:
    zones = tuple(part.strip() for part in (raw or ",".join(DEFAULT_ZONES)).split(",") if part.strip())
    if not zones or len(zones) > MAX_ZONES or len(set(zones)) != len(zones):
        raise ValueError(f"zones must contain 1 to {MAX_ZONES} unique entries")
    if any(not ZONE_PATTERN.fullmatch(zone) for zone in zones):
        raise ValueError("zone names must be fixed GCP zone identifiers")
    return zones


def _group_identity(group_url: str, project: str) -> tuple[str, str]:
    """Return (zone, NEG name) from a Compute API group URL."""
    match = re.search(
        r"/projects/([^/]+)/zones/([^/]+)/networkEndpointGroups/([^/?#]+)$",
        group_url,
    )
    if not match or match.group(1) != project:
        raise ValueError("backend contains an unsupported NEG reference")
    return match.group(2), match.group(3)


def compare_coverage(
    zones: tuple[str, ...],
    attached_endpoint_ips: Mapping[str, set[str]],
    canonical_neg_endpoint_ips: Mapping[str, set[str]],
    attached_canonical_zones: set[str],
    ready_pod_ips: Mapping[str, set[str]],
) -> dict[str, ZoneCoverage]:
    """Compare LB-attached endpoint IPs with Ready listen pod IPs by zone."""
    result: dict[str, ZoneCoverage] = {}
    for zone in zones:
        ready = set(ready_pod_ips.get(zone, set()))
        result[zone] = ZoneCoverage(
            ready_pods=len(ready),
            attached_ready_endpoints=len(set(attached_endpoint_ips.get(zone, set())) & ready),
            neg_attached=int(zone in attached_canonical_zones),
            neg_endpoints=len(set(canonical_neg_endpoint_ips.get(zone, set()))),
        )
    return result


class ComputeRestReader:
    """Small read-only Compute REST client using the pod's Workload Identity."""

    def __init__(self, project: str) -> None:
        self._session = None
        self._project = project
        self._base = "https://compute.googleapis.com/compute/v1"

    def _json(self, method: str, path: str, *, params: dict[str, str] | None = None) -> dict[str, Any]:
        if self._session is None:
            import google.auth
            from google.auth.transport.requests import AuthorizedSession

            credentials, _ = google.auth.default(scopes=[COMPUTE_SCOPE])
            self._session = AuthorizedSession(credentials)
        response = self._session.request(method, f"{self._base}{path}", params=params, timeout=15)
        if response.status_code == 404:
            raise NotFound()
        if not response.ok:
            raise ApiError(response.status_code)
        return response.json()

    def get_backend_service(self, name: str) -> Mapping[str, Any]:
        return self._json(
            "GET", f"/projects/{quote(self._project, safe='')}/global/backendServices/{quote(name, safe='')}"
        )

    def get_zonal_neg(self, zone: str, name: str) -> Mapping[str, Any]:
        return self._json(
            "GET",
            f"/projects/{quote(self._project, safe='')}/zones/{quote(zone, safe='')}/networkEndpointGroups/{quote(name, safe='')}",
        )

    def list_network_endpoints(self, zone: str, name: str) -> set[str]:
        path = (
            f"/projects/{quote(self._project, safe='')}/zones/{quote(zone, safe='')}"
            f"/networkEndpointGroups/{quote(name, safe='')}/listNetworkEndpoints"
        )
        page_token: str | None = None
        ips: set[str] = set()
        while True:
            params = {"pageToken": page_token} if page_token else None
            # The Compute API requires an empty request body for this method.
            page = self._json("POST", path, params=params)
            for item in page.get("items", []):
                endpoint = item.get("networkEndpoint") or {}
                ip = endpoint.get("ipAddress")
                if not ip:
                    raise ValueError("network endpoint has no IPv4 address")
                ips.add(ip)
            page_token = page.get("nextPageToken")
            if not page_token:
                return ips


class KubernetesRestReader:
    """Reads Ready listen pods and their node zone through in-cluster auth."""

    def __init__(self, namespace: str, selector: str) -> None:
        import requests

        host = os.environ["KUBERNETES_SERVICE_HOST"]
        port = os.environ.get("KUBERNETES_SERVICE_PORT_HTTPS", "443")
        self._base = f"https://{host}:{port}"
        self._namespace = namespace
        self._selector = selector
        self._ca = f"{KUBE_SA_DIR}/ca.crt"
        self._token_file = f"{KUBE_SA_DIR}/token"
        self._session = requests.Session()

    def _get(self, path: str, *, params: dict[str, str] | None = None) -> dict[str, Any]:
        with open(self._token_file, encoding="utf-8") as token_file:
            token = token_file.read().strip()
        response = self._session.get(
            f"{self._base}{path}",
            params=params,
            headers={"Authorization": f"Bearer {token}"},
            verify=self._ca,
            timeout=10,
        )
        if not response.ok:
            raise ApiError(response.status_code)
        return response.json()

    def _listen_pods(self) -> list[dict[str, Any]]:
        path = f"/api/v1/namespaces/{quote(self._namespace, safe='')}/pods"
        page_token: str | None = None
        pods: list[dict[str, Any]] = []
        while True:
            params = {"labelSelector": self._selector, "limit": "500"}
            if page_token:
                params["continue"] = page_token
            page = self._get(path, params=params)
            pods.extend(page.get("items", []))
            page_token = (page.get("metadata") or {}).get("continue")
            if not page_token:
                return pods

    def ready_pod_ips_by_zone(self) -> dict[str, set[str]]:
        try:
            pods = self._listen_pods()
        except Exception as exc:
            LOG.debug("Kubernetes pod read failed: %s", type(exc).__name__)
            raise CollectionError("pods") from None

        ready: list[tuple[str, str]] = []
        for pod in pods:
            conditions = (pod.get("status") or {}).get("conditions") or []
            if not any(item.get("type") == "Ready" and item.get("status") == "True" for item in conditions):
                continue
            pod_ip = (pod.get("status") or {}).get("podIP")
            node_name = (pod.get("spec") or {}).get("nodeName")
            if not pod_ip or not node_name:
                raise CollectionError("pods")
            ready.append((pod_ip, node_name))

        node_zones: dict[str, str] = {}
        try:
            for _, node_name in ready:
                if node_name in node_zones:
                    continue
                node = self._get(f"/api/v1/nodes/{quote(node_name, safe='')}")
                labels = (node.get("metadata") or {}).get("labels") or {}
                zone = labels.get("topology.kubernetes.io/zone") or labels.get("failure-domain.beta.kubernetes.io/zone")
                if not zone:
                    raise ValueError("node has no zone label")
                node_zones[node_name] = zone
        except Exception as exc:
            LOG.debug("Kubernetes node read failed: %s", type(exc).__name__)
            raise CollectionError("nodes") from None

        result: dict[str, set[str]] = {}
        for pod_ip, node_name in ready:
            result.setdefault(node_zones[node_name], set()).add(pod_ip)
        return result


class CoverageCollector:
    def __init__(
        self,
        compute: ComputeReader,
        kubernetes: KubernetesReader,
        project: str,
        zones: tuple[str, ...],
        backend_service: str = BACKEND_SERVICE,
        neg_name: str = NEG_NAME,
    ) -> None:
        self.compute = compute
        self.kubernetes = kubernetes
        self.project = project
        self.zones = zones
        self.backend_service = backend_service
        self.neg_name = neg_name

    def collect(self) -> dict[str, ZoneCoverage]:
        try:
            backend = self.compute.get_backend_service(self.backend_service)
        except Exception:
            raise CollectionError("backend_service") from None

        groups: set[tuple[str, str]] = set()
        try:
            for backend_ref in backend.get("backends") or []:
                group_url = backend_ref.get("group")
                if not group_url:
                    continue
                groups.add(_group_identity(group_url, self.project))
            if any(zone not in self.zones for zone, _ in groups):
                raise ValueError("backend service references an unconfigured zone")
        except Exception:
            raise CollectionError("zone_config") from None

        endpoint_cache: dict[tuple[str, str], set[str]] = {}
        attached_endpoint_ips: dict[str, set[str]] = {}
        try:
            for zone, name in sorted(groups):
                ips = self.compute.list_network_endpoints(zone, name)
                endpoint_cache[(zone, name)] = ips
                attached_endpoint_ips.setdefault(zone, set()).update(ips)
        except Exception:
            raise CollectionError("attached_endpoints") from None

        canonical_neg_endpoint_ips: dict[str, set[str]] = {}
        attached_canonical_zones: set[str] = set()
        for zone in self.zones:
            canonical_key = (zone, self.neg_name)
            if canonical_key in groups:
                attached_canonical_zones.add(zone)
            try:
                self.compute.get_zonal_neg(zone, self.neg_name)
            except NotFound:
                if zone in attached_canonical_zones:
                    raise CollectionError("zone_neg") from None
                canonical_neg_endpoint_ips[zone] = set()
                continue
            except Exception:
                raise CollectionError("zone_neg") from None
            try:
                ips = endpoint_cache.get(canonical_key)
                if ips is None:
                    ips = self.compute.list_network_endpoints(zone, self.neg_name)
                    endpoint_cache[canonical_key] = ips
                canonical_neg_endpoint_ips[zone] = set(ips)
            except Exception:
                raise CollectionError("zone_endpoints") from None

        try:
            ready_pod_ips = self.kubernetes.ready_pod_ips_by_zone()
            if any(zone not in self.zones for zone in ready_pod_ips):
                raise CollectionError("zone_config")
        except CollectionError:
            raise
        except Exception:
            raise CollectionError("pods") from None

        return compare_coverage(
            self.zones,
            attached_endpoint_ips,
            canonical_neg_endpoint_ips,
            attached_canonical_zones,
            ready_pod_ips,
        )


class CoverageMetrics:
    def __init__(self) -> None:
        self.registry = CollectorRegistry()
        self.ready_pods = Gauge(
            "omi_listen_lb_ready_pods", "Ready backend-listen pods by zone", ("zone",), registry=self.registry
        )
        self.attached_ready = Gauge(
            "omi_listen_lb_attached_ready_endpoints",
            "Ready pod IPs present in a NEG attached to the listen backend service by zone",
            ("zone",),
            registry=self.registry,
        )
        self.neg_attached = Gauge(
            "omi_listen_lb_neg_attached",
            "Whether the canonical listen NEG is attached by zone",
            ("zone",),
            registry=self.registry,
        )
        self.neg_endpoints = Gauge(
            "omi_listen_lb_neg_endpoints",
            "Endpoints in the canonical listen NEG by zone",
            ("zone",),
            registry=self.registry,
        )
        self.last_success = Gauge(
            "omi_listen_lb_exporter_last_success_timestamp_seconds",
            "Unix timestamp of the last complete successful exporter collection",
            registry=self.registry,
        )
        self.errors = Counter(
            "omi_listen_lb_exporter_errors_total",
            "Failed exporter collections by bounded stage",
            ("stage",),
            registry=self.registry,
        )
        for stage in STAGES:
            self.errors.labels(stage=stage).inc(0)

    def update(self, values: Mapping[str, ZoneCoverage], timestamp: float) -> None:
        for zone, value in values.items():
            self.ready_pods.labels(zone=zone).set(value.ready_pods)
            self.attached_ready.labels(zone=zone).set(value.attached_ready_endpoints)
            self.neg_attached.labels(zone=zone).set(value.neg_attached)
            self.neg_endpoints.labels(zone=zone).set(value.neg_endpoints)
        self.last_success.set(timestamp)


def run_exporter() -> None:
    project = os.environ.get("NEG_COVERAGE_PROJECT", "based-hardware")
    zones = configured_zones(os.environ.get("NEG_COVERAGE_ZONES"))
    backend_name = os.environ.get("NEG_COVERAGE_BACKEND_SERVICE", BACKEND_SERVICE)
    neg_name = os.environ.get("NEG_COVERAGE_NEG_NAME", NEG_NAME)
    namespace = os.environ.get("NEG_COVERAGE_K8S_NAMESPACE", "prod-omi-backend")
    selector = os.environ.get("NEG_COVERAGE_POD_SELECTOR", POD_SELECTOR)
    interval = max(5, int(os.environ.get("NEG_COVERAGE_INTERVAL_SECONDS", "60")))
    port = int(os.environ.get("PORT", "8080"))

    collector = CoverageCollector(
        ComputeRestReader(project),
        KubernetesRestReader(namespace, selector),
        project,
        zones,
        backend_name,
        neg_name,
    )
    metrics = CoverageMetrics()
    start_http_server(port, addr="0.0.0.0", registry=metrics.registry)

    next_run = time.monotonic()
    while True:
        next_run += interval
        try:
            values = collector.collect()
            metrics.update(values, time.time())
        except CollectionError as exc:
            metrics.errors.labels(stage=exc.stage).inc()
            LOG.warning("coverage collection failed at stage=%s", exc.stage)
        except Exception as exc:  # Keep /metrics available for unexpected library errors.
            metrics.errors.labels(stage="unexpected").inc()
            LOG.warning("coverage collection failed at stage=unexpected error_type=%s", type(exc).__name__)
        time.sleep(max(0, next_run - time.monotonic()))


if __name__ == "__main__":
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
    run_exporter()
