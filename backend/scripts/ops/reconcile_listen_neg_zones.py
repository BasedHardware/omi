#!/usr/bin/env python3
"""Attach every zonal listen NEG to its global load-balancer backend service."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from typing import Any, Sequence
from urllib.parse import urlparse

NEG_STATUS_ANNOTATION = "cloud.google.com/neg-status"
NEG_GROUP_PATH = "networkEndpointGroups"
RECONCILE_PERMISSIONS = (
    "compute.backendServices.get",
    "compute.backendServices.list",
    "compute.backendServices.update",
    "compute.networkEndpointGroups.get",
    "compute.networkEndpointGroups.list",
    "compute.networkEndpointGroups.use",
    "compute.globalOperations.get",
)
_DENIED_PERMISSION_RE = re.compile(r"\b(?:required|permission)\s+['\"]?(compute\.[A-Za-z0-9.]+)['\"]?", re.IGNORECASE)
_DENIED_RESOURCE_RE = re.compile(
    r"\b(?:for|on)\s+(?:resource\s+)?['\"]?"
    r"((?:https?://www\.googleapis\.com/compute/v1/)?"
    r"projects/[A-Za-z0-9._-]+/(?:global/backendServices/[A-Za-z0-9._-]+|"
    r"zones/[A-Za-z0-9-]+/networkEndpointGroups/[A-Za-z0-9._-]+))['\"]?",
    re.IGNORECASE,
)

# Backend fields exposed by `gcloud compute backend-services add-backend`.
CAPACITY_FIELDS = {
    "maxRatePerEndpoint": "--max-rate-per-endpoint",
    "maxConnectionsPerEndpoint": "--max-connections-per-endpoint",
    "maxInFlightRequestsPerEndpoint": "--max-in-flight-requests-per-endpoint",
    "maxInFlightRequests": "--max-in-flight-requests",
}
BALANCING_MODES = {"IN_FLIGHT", "RATE", "CONNECTION"}


class ReconcileError(Exception):
    """An actionable error that contains no raw cloud or Kubernetes output."""


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True, help="GCP project containing the backend service and NEGs")
    parser.add_argument("--namespace", required=True, help="Kubernetes namespace containing the listen Service")
    parser.add_argument("--service", required=True, help="Listen Kubernetes Service name")
    parser.add_argument("--backend-service", required=True, help="Global Compute backend service name")
    parser.add_argument(
        "--dry-run", action="store_true", help="Read current state and report changes without attaching NEGs"
    )
    return parser.parse_args(argv)


def _validate_args(args: argparse.Namespace) -> None:
    if not re.fullmatch(r"[a-z][a-z0-9-]{0,62}", args.project):
        raise ReconcileError("invalid project identifier")
    for value, label in (
        (args.namespace, "namespace"),
        (args.service, "service"),
        (args.backend_service, "backend service"),
    ):
        if not re.fullmatch(r"[a-z][a-z0-9-]{0,62}", value):
            raise ReconcileError(f"invalid {label} identifier")


def _permission_denied(stderr: str) -> bool:
    lowered = stderr.lower()
    return any(
        marker in lowered
        for marker in (
            "permission_denied",
            "permission denied",
            "does not have permission",
            "not authorized",
            "403 forbidden",
            "required 'compute.",
            'required "compute.',
        )
    )


def _permission_denial_details(stderr: str) -> tuple[str | None, str | None]:
    """Extract only a Compute permission and known resource path from gcloud output."""
    permission_match = _DENIED_PERMISSION_RE.search(stderr)
    resource_match = _DENIED_RESOURCE_RE.search(stderr)
    resource = resource_match.group(1) if resource_match else None
    if resource and resource.startswith("https://www.googleapis.com/compute/v1/"):
        resource = resource.removeprefix("https://www.googleapis.com/compute/v1/")
    elif resource and resource.startswith("http://www.googleapis.com/compute/v1/"):
        resource = resource.removeprefix("http://www.googleapis.com/compute/v1/")
    return permission_match.group(1) if permission_match else None, resource


def _run_json(command: Sequence[str], *, operation: str, permission: str | None = None) -> Any:
    try:
        result = subprocess.run(command, check=False, capture_output=True, text=True)
    except OSError:
        raise ReconcileError(f"{operation} could not start") from None
    if result.returncode != 0:
        if permission and _permission_denied(result.stderr):
            scope = "the target backend service" if permission.startswith("compute.backendServices.") else "the project"
            raise ReconcileError(f"{operation} denied; grant {permission} on {scope}")
        raise ReconcileError(f"{operation} failed")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        raise ReconcileError(f"{operation} returned invalid JSON") from None


def _zone_from_resource(value: str) -> str | None:
    """Read a zone name from a Compute resource URL, or accept a bare zone."""
    parsed = urlparse(value)
    parts = parsed.path.strip("/").split("/") if parsed.scheme else value.strip("/").split("/")
    if len(parts) == 1 and re.fullmatch(r"[a-z]+-[a-z]+[0-9]+-[a-z]", parts[0]):
        return parts[0]
    for index, part in enumerate(parts[:-1]):
        if part == "zones" and index + 1 < len(parts):
            zone = parts[index + 1]
            if re.fullmatch(r"[a-z]+-[a-z]+[0-9]+-[a-z]", zone):
                return zone
    return None


def _neg_status_from_service(service: Any) -> tuple[str, set[str]]:
    try:
        raw_status = service["metadata"]["annotations"][NEG_STATUS_ANNOTATION]
        status = json.loads(raw_status)
        groups = status["network_endpoint_groups"]
        declared_zone_values = status["zones"]
    except (KeyError, TypeError, json.JSONDecodeError):
        raise ReconcileError("listen Service has no valid NEG status annotation") from None
    if not isinstance(groups, dict) or len(groups) != 1:
        raise ReconcileError("listen Service NEG status must identify exactly one exposed NEG")
    neg_name = next(iter(groups.values()))
    if not isinstance(neg_name, str) or not re.fullmatch(r"[a-z][a-z0-9-]{0,62}", neg_name):
        raise ReconcileError("listen Service NEG status contains an invalid NEG name")
    if not isinstance(declared_zone_values, list) or not declared_zone_values:
        raise ReconcileError("listen Service NEG status has no declared zones")
    declared_zones = set()
    for value in declared_zone_values:
        zone = _zone_from_resource(value) if isinstance(value, str) else None
        if zone is None:
            raise ReconcileError("listen Service NEG status contains an invalid zone")
        declared_zones.add(zone)
    return neg_name, declared_zones


def _neg_owner(item: dict[str, Any]) -> tuple[str, str, str, str] | None:
    """GKE writes cluster-uid/namespace/service-name/port into a NEG's description."""
    try:
        owner = json.loads(item.get("description") or "")
        return (owner["cluster-uid"], owner["namespace"], owner["service-name"], str(owner["port"]))
    except (KeyError, TypeError, ValueError):
        return None


def _neg_zones(
    neg_list: Any, expected_name: str, allowed_zones: set[str], *, namespace: str, service: str
) -> tuple[set[str], set[str]]:
    """Return (zones, owned zones outside the Service's declared list).

    The Service's neg-status zone list can lag the NEGs GKE actually created:
    on 2026-10-18 it listed a/b/c while GKE had created an f NEG for the same
    Service when fallback-pool listen pods landed there. An exact-name zonal NEG
    outside the declared zones is in scope only when its GKE owner metadata
    names the same cluster, namespace, Service and port as the declared-zone
    NEGs; anything else still fails closed and is never attached.
    """
    if not isinstance(neg_list, list):
        raise ReconcileError("NEG listing returned an unexpected response")
    declared: dict[str, dict[str, Any]] = {}
    undeclared: dict[str, dict[str, Any]] = {}
    out_of_scope: set[str] = set()
    for item in neg_list:
        if not isinstance(item, dict) or item.get("name") != expected_name:
            continue
        zone_value = item.get("zone")
        zone = _zone_from_resource(zone_value) if isinstance(zone_value, str) else None
        # `gcloud compute network-endpoint-groups list` covers global, regional, and
        # every zonal scope by default, while GKE only guarantees custom NEG name
        # uniqueness within a region. Regional/global exact-name resources are
        # always rejected, never attached.
        if zone is None:
            out_of_scope.add("a regional or global scope")
            continue
        bucket = declared if zone in allowed_zones else undeclared
        if zone in bucket:
            raise ReconcileError("NEG listing returned duplicate resources for a zone")
        bucket[zone] = item
    if not declared:
        raise ReconcileError("no exact-name zonal NEGs were found")
    owners = {_neg_owner(item) for item in declared.values()}
    owner = next(iter(owners)) if len(owners) == 1 else None
    if owner is None or owner[1] != namespace or owner[2] != service:
        raise ReconcileError("declared-zone NEGs do not share GKE owner metadata for the listen Service")
    owned_extra: set[str] = set()
    for zone, item in undeclared.items():
        if _neg_owner(item) == owner:
            owned_extra.add(zone)
        else:
            out_of_scope.add(zone)
    if out_of_scope:
        detail = ", ".join(sorted(out_of_scope))
        raise ReconcileError(f"exact-name NEGs exist outside the listen Service's declared zones: {detail}")
    return set(declared) | owned_extra, owned_extra


def _group_name_and_zone(group: str) -> tuple[str, str] | None:
    parsed = urlparse(group)
    parts = parsed.path.strip("/").split("/") if parsed.scheme else group.strip("/").split("/")
    try:
        index = parts.index(NEG_GROUP_PATH)
        name = parts[index + 1]
    except (ValueError, IndexError):
        return None
    zone = _zone_from_resource(group)
    if not re.fullmatch(r"[a-z][a-z0-9-]{0,62}", name) or zone is None:
        return None
    return name, zone


def _settings(backends: Any) -> tuple[str, str, list[tuple[str, Any]], str]:
    if not isinstance(backends, list) or not backends:
        raise ReconcileError("backend service has no attached backends to copy settings from")
    signatures: set[tuple[Any, ...]] = set()
    for backend in backends:
        if not isinstance(backend, dict):
            raise ReconcileError("backend service contains an invalid backend entry")
        mode = backend.get("balancingMode")
        scaler = backend.get("capacityScaler")
        traffic_duration = backend.get("trafficDuration")
        if not isinstance(mode, str) or mode not in BALANCING_MODES:
            raise ReconcileError("attached backend balancing mode or capacity scaler is unavailable")
        if isinstance(scaler, bool) or not isinstance(scaler, (int, float)):
            raise ReconcileError("attached backend balancing mode or capacity scaler is unavailable")
        if not isinstance(traffic_duration, str) or not traffic_duration:
            raise ReconcileError("attached backend traffic duration is unavailable")
        values = tuple((field, backend.get(field)) for field in CAPACITY_FIELDS)
        if any(
            value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)))
            for _, value in values
        ):
            raise ReconcileError("attached backend capacity limit is invalid")
        signatures.add((mode, scaler, values, traffic_duration))
    if len(signatures) != 1:
        raise ReconcileError("attached backends disagree on balancing settings or traffic duration")

    mode, scaler, values, traffic_duration = next(iter(signatures))
    selected = [(field, value) for field, value in values if value is not None]
    if mode == "IN_FLIGHT":
        applicable = [
            field for field, _ in selected if field in ("maxInFlightRequestsPerEndpoint", "maxInFlightRequests")
        ]
        if len(applicable) != 1:
            raise ReconcileError("IN_FLIGHT backend must expose exactly one supported request limit")
        if traffic_duration != "LONG":
            raise ReconcileError("IN_FLIGHT backend traffic duration is not LONG")
    elif mode == "RATE" and not any(field == "maxRatePerEndpoint" for field, _ in selected):
        raise ReconcileError("RATE backend maxRatePerEndpoint is unavailable")
    elif mode == "CONNECTION" and not any(field == "maxConnectionsPerEndpoint" for field, _ in selected):
        raise ReconcileError("CONNECTION backend maxConnectionsPerEndpoint is unavailable")
    if len(selected) > 1:
        raise ReconcileError("attached backend exposes multiple mutually exclusive capacity limits")
    return mode, str(scaler), selected, traffic_duration


def _add_backend_command(
    *,
    project: str,
    service: str,
    neg_name: str,
    zone: str,
    mode: str,
    scaler: str,
    capacity: Sequence[tuple[str, Any]],
    traffic_duration: str,
) -> list[str]:
    command = [
        "gcloud",
        "compute",
        "backend-services",
        "add-backend",
        service,
        f"--network-endpoint-group={neg_name}",
        f"--network-endpoint-group-zone={zone}",
        f"--balancing-mode={mode}",
        f"--capacity-scaler={scaler}",
        "--global",
        f"--project={project}",
        "--quiet",
    ]
    if mode == "IN_FLIGHT":
        command.append(f"--traffic-duration={traffic_duration}")
    for field, value in capacity:
        command.append(f"{CAPACITY_FIELDS[field]}={value}")
    return command


def reconcile(args: argparse.Namespace) -> None:
    _validate_args(args)
    service = _run_json(
        ["kubectl", "--namespace", args.namespace, "get", "service", args.service, "--output=json"],
        operation="listen Service lookup",
    )
    neg_name, declared_zones = _neg_status_from_service(service)

    listed_negs = _run_json(
        [
            "gcloud",
            "compute",
            "network-endpoint-groups",
            "list",
            f"--filter=name={neg_name}",
            "--format=json",
            f"--project={args.project}",
        ],
        operation="NEG listing",
        permission="compute.networkEndpointGroups.list",
    )
    zones, owned_extra = _neg_zones(
        listed_negs, neg_name, declared_zones, namespace=args.namespace, service=args.service
    )
    if owned_extra:
        print(
            "NEG zones outside the Service's declared list, accepted by matching GKE owner metadata: "
            + ", ".join(sorted(owned_extra))
        )
    unlisted_declared_zones = declared_zones - zones
    if unlisted_declared_zones:
        missing = ", ".join(sorted(unlisted_declared_zones))
        raise ReconcileError(f"listen Service status declares zones with no listable NEG: {missing}")

    backend_service = _run_json(
        [
            "gcloud",
            "compute",
            "backend-services",
            "describe",
            args.backend_service,
            "--global",
            "--format=json",
            f"--project={args.project}",
        ],
        operation="backend service read",
        permission="compute.backendServices.get",
    )
    if not isinstance(backend_service, dict):
        raise ReconcileError("backend service read returned an unexpected response")
    backends = backend_service.get("backends")
    if not isinstance(backends, list) or not backends:
        raise ReconcileError("backend service has no attached backends to copy settings from")

    attached_zones: set[str] = set()
    for backend in backends:
        group = backend.get("group") if isinstance(backend, dict) else None
        identity = _group_name_and_zone(group) if isinstance(group, str) else None
        if identity is None or identity[0] != neg_name:
            raise ReconcileError("backend service contains an unexpected backend group")
        attached_zones.add(identity[1])

    mode, scaler, capacity, traffic_duration = _settings(backends)
    missing_zones = sorted(zones - attached_zones)
    print(f"NEG zones discovered ({len(zones)}): {', '.join(sorted(zones))}")
    print(
        f"NEG zones already attached ({len(zones & attached_zones)}): {', '.join(sorted(zones & attached_zones)) or 'none'}"
    )
    print(f"NEG zones missing ({len(missing_zones)}): {', '.join(missing_zones) or 'none'}")

    if args.dry_run:
        print(f"dry-run: would attach {len(missing_zones)} zone(s)")
        return

    for zone in missing_zones:
        command = _add_backend_command(
            project=args.project,
            service=args.backend_service,
            neg_name=neg_name,
            zone=zone,
            mode=mode,
            scaler=scaler,
            capacity=capacity,
            traffic_duration=traffic_duration,
        )
        try:
            result = subprocess.run(command, check=False, capture_output=True, text=True)
        except OSError:
            raise ReconcileError(f"failed to attach zone {zone}: gcloud could not start") from None
        if result.returncode != 0:
            if _permission_denied(result.stderr):
                denied_permission, denied_resource = _permission_denial_details(result.stderr)
                detail = denied_permission or "permission unavailable"
                if denied_resource:
                    detail += f" on {denied_resource}"
                permissions = ", ".join(RECONCILE_PERMISSIONS)
                raise ReconcileError(
                    f"failed to attach zone {zone}: permission denied ({detail}); "
                    f"required permissions: {permissions}"
                )
            raise ReconcileError(f"failed to attach zone {zone}: backend update failed")
    print(
        f"reconciled: {len(zones)} NEG zone(s), {len(zones & attached_zones)} already attached, {len(missing_zones)} added"
    )


def main(argv: Sequence[str] | None = None) -> int:
    try:
        reconcile(_parse_args(argv))
    except ReconcileError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
