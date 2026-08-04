#!/usr/bin/env python3
"""Fail closed before a Pusher Helm mutation when live capacity cannot surge.

This command is deliberately read-only.  It renders the exact digest-pinned
chart input, reads Kubernetes metadata, and proves that the desired surge pods
can fit on currently Ready, schedulable nodes that satisfy Pusher's placement
constraints.  It never reads ConfigMap/Secret payloads and never creates a
resource or sends application traffic.
"""

from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation
import json
import math
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
IMAGE_RE = re.compile(r"^(?P<repository>[a-z0-9][a-z0-9._/-]*)@(?P<digest>sha256:[a-f0-9]{64})$")
MEMORY_FACTORS = {
    "": 1,
    "Ki": 1024,
    "Mi": 1024**2,
    "Gi": 1024**3,
    "Ti": 1024**4,
    "K": 1000,
    "M": 1000**2,
    "G": 1000**3,
    "T": 1000**4,
}


class GateError(ValueError):
    """A required deployment-control input is missing or cannot be trusted."""


@dataclass(frozen=True)
class Resources:
    cpu_millicores: int
    memory_bytes: int

    def add(self, other: "Resources") -> "Resources":
        return Resources(self.cpu_millicores + other.cpu_millicores, self.memory_bytes + other.memory_bytes)

    def fits_in(self, other: "Resources") -> bool:
        return self.cpu_millicores <= other.cpu_millicores and self.memory_bytes <= other.memory_bytes

    def subtract(self, other: "Resources") -> "Resources":
        return Resources(self.cpu_millicores - other.cpu_millicores, self.memory_bytes - other.memory_bytes)


ZERO = Resources(0, 0)


def parse_image_reference(image: str) -> tuple[str, str]:
    match = IMAGE_RE.fullmatch(image)
    if match is None:
        raise GateError("Pusher deployment image must be an exact repository@sha256 digest, never a mutable tag")
    return match.group("repository"), match.group("digest")


def _decimal(value: object, field: str) -> Decimal:
    if not isinstance(value, (str, int, float)):
        raise GateError(f"{field} must be a Kubernetes quantity")
    try:
        return Decimal(str(value))
    except InvalidOperation as exc:
        raise GateError(f"{field} must be a Kubernetes quantity, got {value!r}") from exc


def parse_cpu(value: object, field: str) -> int:
    raw = str(value)
    quantity = _decimal(raw[:-1], field) if raw.endswith("m") else _decimal(raw, field) * 1000
    if quantity < 0 or quantity != quantity.to_integral_value():
        raise GateError(f"{field} must resolve to a non-negative whole millicore quantity")
    return int(quantity)


def parse_memory(value: object, field: str) -> int:
    raw = str(value)
    suffix = next(
        (candidate for candidate in sorted(MEMORY_FACTORS, key=len, reverse=True) if raw.endswith(candidate)), None
    )
    if suffix is None:
        raise GateError(f"{field} must be a Kubernetes memory quantity")
    number = raw[: -len(suffix)] if suffix else raw
    quantity = _decimal(number, field) * MEMORY_FACTORS[suffix]
    if quantity < 0 or quantity != quantity.to_integral_value():
        raise GateError(f"{field} must resolve to a non-negative whole byte quantity")
    return int(quantity)


def resource_requests(container: dict[str, Any], *, required: bool, context: str) -> Resources:
    resources = container.get("resources")
    requests = resources.get("requests") if isinstance(resources, dict) else None
    if not isinstance(requests, dict):
        if required:
            raise GateError(f"{context} must define cpu and memory resource requests")
        return ZERO
    cpu = requests.get("cpu")
    memory = requests.get("memory")
    if required and (cpu is None or memory is None):
        raise GateError(f"{context} must define cpu and memory resource requests")
    return Resources(
        parse_cpu(cpu, f"{context}.resources.requests.cpu") if cpu is not None else 0,
        parse_memory(memory, f"{context}.resources.requests.memory") if memory is not None else 0,
    )


def pod_requests(pod: dict[str, Any]) -> Resources:
    spec = pod.get("spec") if isinstance(pod.get("spec"), dict) else {}
    app = ZERO
    for container in spec.get("containers", []) if isinstance(spec.get("containers"), list) else []:
        if isinstance(container, dict):
            app = app.add(resource_requests(container, required=False, context="existing pod container"))
    init = ZERO
    for container in spec.get("initContainers", []) if isinstance(spec.get("initContainers"), list) else []:
        if isinstance(container, dict):
            candidate = resource_requests(container, required=False, context="existing init container")
            init = Resources(
                max(init.cpu_millicores, candidate.cpu_millicores), max(init.memory_bytes, candidate.memory_bytes)
            )
    overhead = spec.get("overhead") if isinstance(spec.get("overhead"), dict) else {}
    return Resources(
        max(app.cpu_millicores, init.cpu_millicores)
        + (parse_cpu(overhead["cpu"], "pod overhead cpu") if "cpu" in overhead else 0),
        max(app.memory_bytes, init.memory_bytes)
        + (parse_memory(overhead["memory"], "pod overhead memory") if "memory" in overhead else 0),
    )


def node_allocatable(node: dict[str, Any]) -> Resources:
    status = node.get("status") if isinstance(node.get("status"), dict) else {}
    values = status.get("allocatable") if isinstance(status.get("allocatable"), dict) else {}
    if "cpu" not in values or "memory" not in values:
        raise GateError(f"node {node_name(node)!r} does not expose cpu and memory allocatable capacity")
    return Resources(
        parse_cpu(values["cpu"], "node allocatable cpu"), parse_memory(values["memory"], "node allocatable memory")
    )


def node_name(node: dict[str, Any]) -> str:
    metadata = node.get("metadata") if isinstance(node.get("metadata"), dict) else {}
    name = metadata.get("name")
    if not isinstance(name, str) or not name:
        raise GateError("cluster returned a node without metadata.name")
    return name


def _ready(node: dict[str, Any]) -> bool:
    status = node.get("status") if isinstance(node.get("status"), dict) else {}
    conditions = status.get("conditions") if isinstance(status.get("conditions"), list) else []
    return any(
        isinstance(item, dict) and item.get("type") == "Ready" and item.get("status") == "True" for item in conditions
    )


def _expression_matches(labels: dict[str, str], expression: dict[str, Any]) -> bool:
    key = expression.get("key")
    operator = expression.get("operator")
    values = expression.get("values", [])
    if not isinstance(key, str) or not isinstance(operator, str) or not isinstance(values, list):
        raise GateError("Pusher node affinity contains an invalid match expression")
    actual = labels.get(key)
    if operator == "In":
        return actual in values
    if operator == "NotIn":
        return actual is None or actual not in values
    if operator == "Exists":
        return actual is not None
    if operator == "DoesNotExist":
        return actual is None
    if operator in {"Gt", "Lt"}:
        if actual is None or len(values) != 1:
            return False
        try:
            return int(actual) > int(values[0]) if operator == "Gt" else int(actual) < int(values[0])
        except (TypeError, ValueError):
            return False
    raise GateError(f"Pusher node affinity uses unsupported operator {operator!r}")


def _tolerates(taint: dict[str, Any], tolerations: list[dict[str, Any]]) -> bool:
    effect = taint.get("effect")
    if effect not in {"NoSchedule", "NoExecute"}:
        return True
    key = taint.get("key")
    value = taint.get("value")
    for item in tolerations:
        if item.get("key") != key or item.get("effect") not in {None, "", effect}:
            continue
        operator = item.get("operator", "Equal")
        if operator == "Exists" or (operator == "Equal" and item.get("value") == value):
            return True
    return False


def node_matches_pod(node: dict[str, Any], pod_spec: dict[str, Any]) -> bool:
    if not _ready(node) or pod_spec.get("nodeName"):
        return False
    spec = node.get("spec") if isinstance(node.get("spec"), dict) else {}
    if spec.get("unschedulable"):
        return False
    metadata = node.get("metadata") if isinstance(node.get("metadata"), dict) else {}
    labels = metadata.get("labels") if isinstance(metadata.get("labels"), dict) else {}
    labels = {str(key): str(value) for key, value in labels.items()}
    node_selector = pod_spec.get("nodeSelector") if isinstance(pod_spec.get("nodeSelector"), dict) else {}
    if any(labels.get(str(key)) != str(value) for key, value in node_selector.items()):
        return False
    affinity = pod_spec.get("affinity") if isinstance(pod_spec.get("affinity"), dict) else {}
    node_affinity = affinity.get("nodeAffinity") if isinstance(affinity.get("nodeAffinity"), dict) else {}
    required = node_affinity.get("requiredDuringSchedulingIgnoredDuringExecution")
    if isinstance(required, dict):
        terms = required.get("nodeSelectorTerms")
        if not isinstance(terms, list) or not terms:
            raise GateError("Pusher required node affinity must contain at least one nodeSelectorTerm")
        if not any(
            isinstance(term, dict)
            and all(_expression_matches(labels, expression) for expression in term.get("matchExpressions", []))
            for term in terms
        ):
            return False
    tolerations = pod_spec.get("tolerations") if isinstance(pod_spec.get("tolerations"), list) else []
    tolerations = [item for item in tolerations if isinstance(item, dict)]
    taints = spec.get("taints") if isinstance(spec.get("taints"), list) else []
    return all(not isinstance(taint, dict) or _tolerates(taint, tolerations) for taint in taints)


def surge_count(current_deployment: dict[str, Any], desired_deployment: dict[str, Any]) -> int:
    status = current_deployment.get("status") if isinstance(current_deployment.get("status"), dict) else {}
    spec = current_deployment.get("spec") if isinstance(current_deployment.get("spec"), dict) else {}
    replicas = status.get("replicas", spec.get("replicas", 1))
    if not isinstance(replicas, int) or replicas < 1:
        raise GateError("live Pusher deployment must report at least one current replica")
    desired_spec = desired_deployment.get("spec") if isinstance(desired_deployment.get("spec"), dict) else {}
    strategy = desired_spec.get("strategy") if isinstance(desired_spec.get("strategy"), dict) else {}
    rolling = strategy.get("rollingUpdate") if isinstance(strategy.get("rollingUpdate"), dict) else {}
    value = rolling.get("maxSurge")
    if isinstance(value, int):
        surge = value
    elif isinstance(value, str) and value.endswith("%"):
        try:
            surge = math.ceil(replicas * int(value[:-1]) / 100)
        except ValueError as exc:
            raise GateError("rendered Pusher maxSurge must be an integer or percentage") from exc
    elif isinstance(value, str):
        try:
            surge = int(value)
        except ValueError as exc:
            raise GateError("rendered Pusher maxSurge must be an integer or percentage") from exc
    else:
        raise GateError("rendered Pusher Deployment is missing RollingUpdate maxSurge")
    if surge < 1:
        raise GateError("rendered Pusher maxSurge must provide at least one surge pod")
    return surge


def capacity_evidence(
    desired_deployment: dict[str, Any],
    current_deployment: dict[str, Any],
    nodes: list[dict[str, Any]],
    pods: list[dict[str, Any]],
) -> tuple[list[str], dict[str, int]]:
    """Return fail-closed capacity findings for the next exact Pusher surge wave."""

    desired_spec = desired_deployment.get("spec") if isinstance(desired_deployment.get("spec"), dict) else {}
    template = desired_spec.get("template") if isinstance(desired_spec.get("template"), dict) else {}
    pod_spec = template.get("spec") if isinstance(template.get("spec"), dict) else {}
    containers = pod_spec.get("containers") if isinstance(pod_spec.get("containers"), list) else []
    pusher = next((item for item in containers if isinstance(item, dict) and item.get("name") == "pusher"), None)
    if pusher is None:
        raise GateError("rendered Pusher Deployment is missing its primary pusher container")
    requested = resource_requests(pusher, required=True, context="rendered pusher container")
    surge = surge_count(current_deployment, desired_deployment)
    needed = Resources(requested.cpu_millicores * surge, requested.memory_bytes * surge)
    usage = {node_name(node): ZERO for node in nodes}
    for pod in pods:
        spec = pod.get("spec") if isinstance(pod.get("spec"), dict) else {}
        status = pod.get("status") if isinstance(pod.get("status"), dict) else {}
        node = spec.get("nodeName")
        if not isinstance(node, str) or node not in usage or status.get("phase") in {"Succeeded", "Failed"}:
            continue
        usage[node] = usage[node].add(pod_requests(pod))
    candidates: list[tuple[str, Resources]] = []
    for node in nodes:
        if not node_matches_pod(node, pod_spec):
            continue
        name = node_name(node)
        candidates.append((name, node_allocatable(node).subtract(usage[name])))
    if not candidates:
        return (["no Ready, schedulable node satisfies the rendered Pusher node affinity and tolerations"], {})
    fitting = [(name, available) for name, available in candidates if needed.fits_in(available)]
    details = {
        "candidate_nodes": len(candidates),
        "fitting_nodes": len(fitting),
        "surge_pods": surge,
        "required_cpu_millicores": needed.cpu_millicores,
        "required_memory_bytes": needed.memory_bytes,
    }
    if fitting:
        return [], details
    return (
        [
            "insufficient schedulable Pusher headroom for the next surge wave: "
            f"need {needed.cpu_millicores}m CPU and {needed.memory_bytes} bytes memory for {surge} surge pod(s)"
        ],
        details,
    )


def kubectl_json(arguments: list[str]) -> dict[str, Any]:
    result = subprocess.run(["kubectl", *arguments, "-o", "json"], check=False, capture_output=True, text=True)
    if result.returncode:
        detail = (result.stderr or result.stdout).strip().splitlines()
        raise GateError(detail[-1] if detail else "kubectl metadata query failed")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise GateError("kubectl did not return JSON metadata") from exc
    if not isinstance(payload, dict):
        raise GateError("kubectl did not return an object")
    return payload


def render_deployment(root: Path, environment: str, image: str) -> dict[str, Any]:
    repository, digest = parse_image_reference(image)
    chart = root / "backend/charts/pusher"
    values = chart / f"{environment}_omi_pusher_values.yaml"
    result = subprocess.run(
        [
            "helm",
            "template",
            f"{environment}-omi-pusher",
            str(chart),
            "-f",
            str(values),
            "--set-string",
            f"image.repository={repository}",
            "--set-string",
            f"image.digest={digest}",
            "--set-string",
            "image.tag=",
            "--set-string",
            "image.pullPolicy=IfNotPresent",
        ],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise GateError(result.stderr.strip() or "helm template failed")
    documents = [
        item
        for item in yaml.safe_load_all(result.stdout)
        if isinstance(item, dict) and item.get("kind") == "Deployment"
    ]
    if len(documents) != 1:
        raise GateError("digest-pinned Pusher render must contain exactly one Deployment")
    container = next(
        (
            item
            for item in documents[0].get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])
            if isinstance(item, dict) and item.get("name") == "pusher"
        ),
        None,
    )
    if not isinstance(container, dict) or container.get("image") != image:
        raise GateError("rendered Pusher Deployment did not preserve the exact requested digest identity")
    return documents[0]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", required=True, choices=("dev", "prod"))
    parser.add_argument("--namespace", required=True)
    parser.add_argument("--image", required=True, help="Exact repository@sha256 image selected for this deployment")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()

    try:
        deployment = render_deployment(args.root.resolve(), args.environment, args.image)
        current = kubectl_json(["-n", args.namespace, "get", "deployment", f"{args.environment}-omi-pusher"])
        nodes = kubectl_json(["get", "nodes"]).get("items")
        pods = kubectl_json(["get", "pods", "--all-namespaces"]).get("items")
        if not isinstance(nodes, list) or not isinstance(pods, list):
            raise GateError("cluster metadata list response is malformed")
        failures, evidence = capacity_evidence(
            deployment,
            current,
            [item for item in nodes if isinstance(item, dict)],
            [item for item in pods if isinstance(item, dict)],
        )
    except GateError as exc:
        failures = [str(exc)]
        evidence = {}
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    print(
        "OK: live Pusher capacity gate passed: "
        f"{evidence['fitting_nodes']}/{evidence['candidate_nodes']} matching nodes fit "
        f"{evidence['surge_pods']} surge pod(s) requiring {evidence['required_cpu_millicores']}m CPU and "
        f"{evidence['required_memory_bytes']} bytes memory."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
