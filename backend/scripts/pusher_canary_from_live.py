#!/usr/bin/env python3
"""Derive the isolated production Pusher canary from the live Pusher workload.

SCA-4763 (Release selection, 2026-11-28). The protected image-only chain must
qualify the candidate image against the environment production will keep. A
canary rendered from the dispatching main cannot do that: it carries main's
current ConfigMap projection and chart values, while the image-only promote
deliberately preserves the live Deployment template and the live runtime
ConfigMap. The first protected canary verification refused with
`effective_environment_differs` (run 46139487564) for exactly that reason.

So the canary is a copy of the live objects, never a render:

* the runtime ConfigMap is an exact copy of the live one (`data` and
  `binaryData` included), so its fingerprint equals the live fingerprint;
* the Deployment is the live Pusher PodTemplate with only the Pusher image
  replaced, the canary name applied to the workload identity labels, and every
  ConfigMap reference redirected to the copied map;
* the Service is a plain ClusterIP that selects only the canary pod and carries
  the live container port. It has no ingress, NEG or backend-config annotation.

Nothing else is templated. Every live PodTemplate field is carried over, which
is what makes the canary parity and effective-environment gates meaningful.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import subprocess
import sys
from typing import Any

LIVE_DEPLOYMENT = "prod-omi-pusher"
LIVE_CONFIG_MAP = "prod-omi-backend-config"
LIVE_SERVICE = "prod-omi-pusher"
CANARY_DEPLOYMENT_PREFIX = "prod-omi-pusher-canary-"
CANARY_CONFIG_MAP_PREFIX = "prod-omi-backend-config-canary-"
# Bounded Kubernetes object names; the workflow builds them from GITHUB_RUN_ID.
NAME = re.compile(r"[a-z0-9]([-a-z0-9]*[a-z0-9])?\Z")
IMAGE = re.compile(r"gcr\.io/based-hardware/(?:backend-)?pusher@sha256:[a-f0-9]{64}\Z")
DERIVED_BY = "omi-canary-derivation"


class DeriveError(ValueError):
    """The live workload cannot produce a safe isolated canary."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise DeriveError(message)


def _name(value: Any, *, what: str) -> str:
    require(
        isinstance(value, str) and NAME.fullmatch(value) is not None and len(value) <= 63,
        f"{what} is not a bounded name",
    )
    return value


def _kind(obj: Any, kind: str) -> dict[str, Any]:
    require(isinstance(obj, dict), f"live {kind} is not a Kubernetes object")
    require(obj.get("kind") == kind, f"live object is not a {kind}")
    return obj


def _containers(spec: dict[str, Any]) -> list[dict[str, Any]]:
    containers = spec.get("containers")
    require(isinstance(containers, list), "live PodTemplate has no containers")
    return [item for item in containers if isinstance(item, dict)]


def _redirect(live_name: str, canary_name: str, reference: dict[str, Any] | None) -> bool:
    if isinstance(reference, dict) and reference.get("name") == live_name:
        reference["name"] = canary_name
        return True
    return False


def _redirect_pod_config_references(spec: dict[str, Any], *, live_name: str, canary_name: str) -> int:
    """Point every ConfigMap reference at the isolated copy; return how many moved."""

    moved = 0
    for container in [*_containers(spec), *(spec.get("initContainers") or [])]:
        for source in container.get("envFrom") or []:
            if isinstance(source, dict) and _redirect(live_name, canary_name, source.get("configMapRef")):
                moved += 1
        for entry in container.get("env") or []:
            if not isinstance(entry, dict):
                continue
            value_from = entry.get("valueFrom")
            if isinstance(value_from, dict) and _redirect(live_name, canary_name, value_from.get("configMapKeyRef")):
                moved += 1
    for volume in spec.get("volumes") or []:
        if not isinstance(volume, dict):
            continue
        if _redirect(live_name, canary_name, volume.get("configMap")):
            moved += 1
        projected = volume.get("projected")
        if isinstance(projected, dict):
            for source in projected.get("sources") or []:
                if isinstance(source, dict) and _redirect(live_name, canary_name, source.get("configMap")):
                    moved += 1
    return moved


def derive_config_map(live: dict[str, Any], *, name: str, namespace: str) -> dict[str, Any]:
    """Copy the live runtime ConfigMap byte for byte under the canary name."""

    _kind(live, "ConfigMap")
    canary = _name(name, what="canary ConfigMap name")
    require(canary.startswith(CANARY_CONFIG_MAP_PREFIX), "canary ConfigMap must use the canary name prefix")
    live_name = live.get("metadata", {}).get("name")
    require(canary != live_name, "canary ConfigMap must not reuse the live name")
    data = live.get("data") if isinstance(live.get("data"), dict) else {}
    binary_data = live.get("binaryData") if isinstance(live.get("binaryData"), dict) else {}
    require(bool(data or binary_data), "live ConfigMap carries no data to copy")
    derived: dict[str, Any] = {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {
            "name": canary,
            "namespace": namespace,
            "labels": {"app.kubernetes.io/managed-by": DERIVED_BY, "app.kubernetes.io/instance": canary},
        },
        "data": copy.deepcopy(data),
    }
    if binary_data:
        derived["binaryData"] = copy.deepcopy(binary_data)
    return derived


def derive_deployment(
    live: dict[str, Any],
    *,
    name: str,
    namespace: str,
    image: str,
    canary_config_map: str,
    live_config_map: str,
) -> dict[str, Any]:
    """Copy the live PodTemplate, changing only image, canary names and ConfigMap refs."""

    _kind(live, "Deployment")
    canary = _name(name, what="canary Deployment name")
    require(canary.startswith(CANARY_DEPLOYMENT_PREFIX), "canary Deployment must use the canary name prefix")
    canary_map = _name(canary_config_map, what="canary ConfigMap name")
    live_map = _name(live_config_map, what="live ConfigMap name")
    require(
        isinstance(image, str) and IMAGE.fullmatch(image) is not None, "candidate image must be an exact Pusher digest"
    )
    metadata = live.get("metadata") if isinstance(live.get("metadata"), dict) else {}
    live_name = metadata.get("name")
    require(canary != live_name, "canary Deployment must not reuse the live name")
    spec = live.get("spec")
    require(isinstance(spec, dict), "live Deployment has no spec")
    template = spec.get("template")
    require(isinstance(template, dict) and isinstance(template.get("spec"), dict), "live Deployment has no PodTemplate")

    derived = copy.deepcopy(live)
    derived["metadata"] = {
        "name": canary,
        "namespace": namespace,
        "labels": {
            **(metadata.get("labels") or {}),
            "app.kubernetes.io/instance": canary,
            # The canary owns no Helm release; only the workload metadata says so.
            "app.kubernetes.io/managed-by": DERIVED_BY,
        },
        "annotations": {},
    }
    derived.pop("status", None)
    derived_spec = derived["spec"]
    derived_spec["replicas"] = 1
    selector = derived_spec.get("selector")
    if isinstance(selector, dict) and isinstance(selector.get("matchLabels"), dict):
        selector["matchLabels"]["app.kubernetes.io/instance"] = canary

    derived_template = derived_spec["template"]
    derived_template.pop("creationTimestamp", None)
    template_metadata = derived_template.setdefault("metadata", {})
    labels = template_metadata.setdefault("labels", {})
    require(isinstance(labels, dict), "live PodTemplate labels are not a mapping")
    labels["app.kubernetes.io/instance"] = canary

    live_pusher = [item for item in _containers(template["spec"]) if item.get("name") == "pusher"]
    require(len(live_pusher) == 1, "live PodTemplate must contain exactly one pusher container")
    require(image != live_pusher[0].get("image"), "candidate image equals the live image")
    pusher_containers = [item for item in _containers(derived_template["spec"]) if item.get("name") == "pusher"]
    require(len(pusher_containers) == 1, "derived PodTemplate must contain exactly one pusher container")
    pusher_containers[0]["image"] = image

    moved = _redirect_pod_config_references(derived_template["spec"], live_name=live_map, canary_name=canary_map)
    require(moved > 0, "live PodTemplate references no runtime ConfigMap to isolate")
    remaining = _redirect_pod_config_references(derived_template["spec"], live_name=live_map, canary_name=live_map)
    require(remaining == 0, "live runtime ConfigMap reference remained in the derived canary")
    return derived


def derive_service(live: dict[str, Any], *, name: str, namespace: str) -> dict[str, Any]:
    """Create a plain ClusterIP that selects only the canary and nothing else."""

    _kind(live, "Service")
    canary = _name(name, what="canary Service name")
    require(canary.startswith(CANARY_DEPLOYMENT_PREFIX), "canary Service must use the canary name prefix")
    spec = live.get("spec")
    require(isinstance(spec, dict), "live Service has no spec")
    ports = copy.deepcopy(spec.get("ports"))
    require(isinstance(ports, list) and bool(ports), "live Service exposes no ports to copy")
    return {
        "apiVersion": "v1",
        "kind": "Service",
        "metadata": {
            "name": canary,
            "namespace": namespace,
            "labels": {
                "app.kubernetes.io/name": "pusher",
                "app.kubernetes.io/instance": canary,
                "app.kubernetes.io/managed-by": DERIVED_BY,
            },
        },
        "spec": {
            "type": "ClusterIP",
            "selector": {"app.kubernetes.io/name": "pusher", "app.kubernetes.io/instance": canary},
            "ports": ports,
        },
    }


def kubectl(kube_context: str | None, args: list[str], *, stdin: str | None = None) -> str:
    command = ["kubectl", *(["--context", kube_context] if kube_context else []), *args]
    result = subprocess.run(command, input=stdin, capture_output=True, text=True)
    if result.returncode != 0:
        raise DeriveError(f"kubectl {' '.join(args)} failed")
    return result.stdout


def read_object(kube_context: str | None, kind: str, name: str, namespace: str) -> dict[str, Any]:
    return json.loads(kubectl(kube_context, ["-n", namespace, "get", kind, name, "-o", "json"]))


def apply_object(kube_context: str | None, obj: dict[str, Any], namespace: str) -> None:
    kubectl(kube_context, ["-n", namespace, "apply", "-f", "-"], stdin=json.dumps(obj))


def _print(value: dict[str, Any]) -> None:
    print(json.dumps(value, sort_keys=True))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("config-map", "workload"))
    parser.add_argument("--namespace", default="prod-omi-backend")
    parser.add_argument("--kube-context")
    parser.add_argument("--live-config-map", default=LIVE_CONFIG_MAP)
    parser.add_argument("--live-deployment", default=LIVE_DEPLOYMENT)
    parser.add_argument("--live-service", default=LIVE_SERVICE)
    parser.add_argument("--canary-config-map")
    parser.add_argument("--canary-name")
    parser.add_argument("--image")
    args = parser.parse_args(argv)
    if args.command == "config-map" and not args.canary_config_map:
        parser.error("config-map requires --canary-config-map")
    if args.command == "workload" and not (args.canary_name and args.canary_config_map and args.image):
        parser.error("workload requires --canary-name, --canary-config-map and --image")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.command == "config-map":
            live = read_object(args.kube_context, "configmap", args.live_config_map, args.namespace)
            canary = derive_config_map(live, name=args.canary_config_map, namespace=args.namespace)
            apply_object(args.kube_context, canary, args.namespace)
            _print(
                {
                    "config_map": args.canary_config_map,
                    "copied_from": args.live_config_map,
                    "keys": len(canary.get("data") or {}),
                    "binary_keys": len(canary.get("binaryData") or {}),
                }
            )
            return 0
        live_deployment = read_object(args.kube_context, "deployment", args.live_deployment, args.namespace)
        live_service = read_object(args.kube_context, "service", args.live_service, args.namespace)
        deployment = derive_deployment(
            live_deployment,
            name=args.canary_name,
            namespace=args.namespace,
            image=args.image,
            canary_config_map=args.canary_config_map,
            live_config_map=args.live_config_map,
        )
        service = derive_service(live_service, name=args.canary_name, namespace=args.namespace)
        apply_object(args.kube_context, service, args.namespace)
        apply_object(args.kube_context, deployment, args.namespace)
        _print({"deployment": args.canary_name, "service": args.canary_name, "derived_from": args.live_deployment})
        return 0
    except (DeriveError, OSError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
