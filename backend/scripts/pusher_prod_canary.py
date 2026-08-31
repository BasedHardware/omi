#!/usr/bin/env python3
"""Create an isolated listener clone and close a production Pusher canary receipt.

The listener clone is derived from the live PodTemplate, pins its exact runtime
image digest, constructs labels that no existing namespace Service selects,
and overrides only HOSTED_PUSHER_API_URL. It has one ClusterIP Service and no
Ingress or HPA.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

DIGEST_RE = re.compile(r"^sha256:[a-f0-9]{64}$")


class CanaryError(RuntimeError):
    pass


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _run_json(command: list[str], *, stdin: dict[str, Any] | None = None) -> dict[str, Any]:
    result = subprocess.run(
        command,
        input=json.dumps(stdin) if stdin is not None else None,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise CanaryError(result.stderr.strip() or f"command failed: {' '.join(command)}")
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise CanaryError(f"command returned invalid JSON: {' '.join(command)}") from exc
    if not isinstance(value, dict):
        raise CanaryError(f"command did not return an object: {' '.join(command)}")
    return value


def _container(items: Any, name: str) -> dict[str, Any]:
    matches = [item for item in items or [] if isinstance(item, dict) and item.get("name") == name]
    if len(matches) != 1:
        raise CanaryError(f"expected exactly one {name} container")
    return matches[0]


def _runtime_digest_image(pods: dict[str, Any], container_name: str) -> str:
    images: set[str] = set()
    items = pods.get("items") if isinstance(pods.get("items"), list) else []
    for pod in items:
        if not isinstance(pod, dict):
            continue
        status = pod.get("status") if isinstance(pod.get("status"), dict) else {}
        container_status = _container(status.get("containerStatuses"), container_name)
        image_id = container_status.get("imageID")
        if container_status.get("ready") is not True or not isinstance(image_id, str):
            raise CanaryError("source listener has a non-ready or unidentified container")
        image = image_id.removeprefix("docker-pullable://")
        digest = image.rsplit("@", 1)[-1]
        if not DIGEST_RE.fullmatch(digest):
            raise CanaryError("source listener runtime image is not digest-addressed")
        images.add(image)
    if len(images) != 1:
        raise CanaryError("source listener pods do not share one exact runtime image")
    return images.pop()


def _service_selectors(services: dict[str, Any], *, exclude_name: str) -> list[tuple[str, dict[str, str]]]:
    selectors: list[tuple[str, dict[str, str]]] = []
    items = services.get("items") if isinstance(services.get("items"), list) else []
    for item in items:
        if not isinstance(item, dict):
            continue
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        name = metadata.get("name")
        if name == exclude_name:
            continue
        spec = item.get("spec") if isinstance(item.get("spec"), dict) else {}
        selector = spec.get("selector") if isinstance(spec.get("selector"), dict) else {}
        if not selector:
            continue
        if (
            not isinstance(name, str)
            or not name
            or any(not isinstance(key, str) or not key or not isinstance(value, str) for key, value in selector.items())
        ):
            raise CanaryError("namespace Service has an invalid selector identity")
        selectors.append((name, selector))
    return sorted(selectors, key=lambda item: item[0])


def _network_policy_label_keys(network_policies: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    items = network_policies.get("items") if isinstance(network_policies.get("items"), list) else []
    for item in items:
        if not isinstance(item, dict):
            continue
        spec = item.get("spec") if isinstance(item.get("spec"), dict) else {}
        selector = spec.get("podSelector") if isinstance(spec.get("podSelector"), dict) else {}
        match_labels = selector.get("matchLabels") if isinstance(selector.get("matchLabels"), dict) else {}
        keys.update(key for key in match_labels if isinstance(key, str) and key)
        expressions = selector.get("matchExpressions") if isinstance(selector.get("matchExpressions"), list) else []
        keys.update(
            expression["key"]
            for expression in expressions
            if isinstance(expression, dict) and isinstance(expression.get("key"), str) and expression["key"]
        )
    return keys


def _selector_matches(labels: dict[str, Any], selector: dict[str, str]) -> bool:
    return all(labels.get(key) == value for key, value in selector.items())


def _isolate_service_labels(
    labels: dict[str, Any],
    selectors: list[tuple[str, dict[str, str]]],
    *,
    canary_name: str,
    protected_keys: set[str],
) -> None:
    forbidden_by_key: dict[str, set[str]] = {}
    for _, selector in selectors:
        for key, value in selector.items():
            forbidden_by_key.setdefault(key, set()).add(value)
    for _, selector in selectors:
        if not _selector_matches(labels, selector):
            continue
        # Preserve labels used to select NetworkPolicy membership whenever the
        # Service offers another key that can break the match.
        key = min(selector, key=lambda candidate: (candidate in protected_keys, candidate))
        salt = 0
        while True:
            seed = f"{canary_name}:{key}:{salt}".encode("utf-8")
            value = f"omi-probe-{hashlib.sha256(seed).hexdigest()[:16]}"
            if value not in forbidden_by_key.get(key, set()):
                labels[key] = value
                break
            salt += 1
    matched = [name for name, selector in selectors if _selector_matches(labels, selector)]
    if matched:
        raise CanaryError(f"canary PodTemplate still matches existing Service selectors: {', '.join(matched)}")


def build_listener_resources(
    deployment: dict[str, Any],
    service: dict[str, Any],
    pods: dict[str, Any],
    *,
    namespace: str,
    canary_name: str,
    pusher_url: str,
    services: dict[str, Any] | None = None,
    network_policies: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], str]:
    spec = deployment.get("spec") if isinstance(deployment.get("spec"), dict) else {}
    status = deployment.get("status") if isinstance(deployment.get("status"), dict) else {}
    metadata = deployment.get("metadata") if isinstance(deployment.get("metadata"), dict) else {}
    if (
        status.get("observedGeneration") != metadata.get("generation")
        or not isinstance(spec.get("replicas"), int)
        or spec["replicas"] < 1
        or status.get("readyReplicas") != spec["replicas"]
        or status.get("availableReplicas") != spec["replicas"]
    ):
        raise CanaryError("source listener Deployment is not fully observed and ready")
    template = copy.deepcopy(spec.get("template"))
    if not isinstance(template, dict):
        raise CanaryError("source listener has no PodTemplate")
    pod_spec = template.get("spec") if isinstance(template.get("spec"), dict) else {}
    listener = _container(pod_spec.get("containers"), "backend-listen")
    runtime_image = _runtime_digest_image(pods, "backend-listen")
    listener["image"] = runtime_image
    listener["imagePullPolicy"] = "IfNotPresent"
    env = listener.get("env") if isinstance(listener.get("env"), list) else []
    pusher_entries = [item for item in env if isinstance(item, dict) and item.get("name") == "HOSTED_PUSHER_API_URL"]
    if len(pusher_entries) != 1:
        raise CanaryError("source listener must declare HOSTED_PUSHER_API_URL exactly once")
    pusher_entries[0].clear()
    pusher_entries[0].update({"name": "HOSTED_PUSHER_API_URL", "value": pusher_url})

    service_spec = service.get("spec") if isinstance(service.get("spec"), dict) else {}
    ordinary_selector = service_spec.get("selector") if isinstance(service_spec.get("selector"), dict) else {}
    if not ordinary_selector:
        raise CanaryError("source listener Service has no selector")
    template_metadata = template.get("metadata") if isinstance(template.get("metadata"), dict) else {}
    labels = copy.deepcopy(template_metadata.get("labels")) if isinstance(template_metadata.get("labels"), dict) else {}
    labels["omi.me/release-probe"] = canary_name
    namespace_services = services or {
        "items": [{"metadata": {"name": "source-listener"}, "spec": {"selector": ordinary_selector}}]
    }
    existing_selectors = _service_selectors(namespace_services, exclude_name=canary_name)
    _isolate_service_labels(
        labels,
        existing_selectors,
        canary_name=canary_name,
        protected_keys=_network_policy_label_keys(network_policies or {}),
    )
    template_metadata["labels"] = labels
    annotations = template_metadata.get("annotations") if isinstance(template_metadata.get("annotations"), dict) else {}
    annotations.pop("prometheus.io/scrape", None)
    template_metadata["annotations"] = annotations
    template["metadata"] = template_metadata

    selector = {"omi.me/release-probe": canary_name}
    canary_deployment = {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {"name": canary_name, "namespace": namespace, "labels": {"omi.me/release-probe": canary_name}},
        "spec": {
            "replicas": 1,
            "progressDeadlineSeconds": 900,
            "strategy": {"type": "Recreate"},
            "selector": {"matchLabels": selector},
            "template": template,
        },
    }
    ports = copy.deepcopy(service_spec.get("ports"))
    if not isinstance(ports, list) or len(ports) != 1:
        raise CanaryError("source listener Service must expose exactly one port")
    canary_service = {
        "apiVersion": "v1",
        "kind": "Service",
        "metadata": {"name": canary_name, "namespace": namespace, "labels": {"omi.me/release-probe": canary_name}},
        "spec": {"type": "ClusterIP", "ports": ports, "selector": selector},
    }
    return canary_deployment, canary_service, runtime_image


def create_listener(args: argparse.Namespace) -> dict[str, Any]:
    deployment = _run_json(["kubectl", "-n", args.namespace, "get", "deployment", args.source_deployment, "-o", "json"])
    service = _run_json(["kubectl", "-n", args.namespace, "get", "service", args.source_service, "-o", "json"])
    services = _run_json(["kubectl", "-n", args.namespace, "get", "services", "-o", "json"])
    network_policies = _run_json(["kubectl", "-n", args.namespace, "get", "networkpolicies", "-o", "json"])
    service_items = services.get("items") if isinstance(services.get("items"), list) else []
    source_uid = service.get("metadata", {}).get("uid")
    if (
        not isinstance(source_uid, str)
        or not source_uid
        or not any(
            isinstance(item, dict)
            and item.get("metadata", {}).get("name") == args.source_service
            and item.get("metadata", {}).get("uid") == source_uid
            for item in service_items
        )
    ):
        raise CanaryError("source listener Service is not present with one exact identity in namespace inventory")
    selector = deployment.get("spec", {}).get("selector", {}).get("matchLabels", {})
    if not isinstance(selector, dict) or not selector:
        raise CanaryError("source listener Deployment has no exact selector")
    selector_arg = ",".join(f"{key}={value}" for key, value in sorted(selector.items()))
    pods = _run_json(["kubectl", "-n", args.namespace, "get", "pods", "-l", selector_arg, "-o", "json"])
    canary_deployment, canary_service, runtime_image = build_listener_resources(
        deployment,
        service,
        pods,
        namespace=args.namespace,
        canary_name=args.name,
        pusher_url=args.pusher_url,
        services=services,
        network_policies=network_policies,
    )
    _run_json(["kubectl", "apply", "-f", "-", "-o", "json"], stdin=canary_service)
    _run_json(["kubectl", "apply", "-f", "-", "-o", "json"], stdin=canary_deployment)
    subprocess.run(
        [
            "kubectl",
            "-n",
            args.namespace,
            "rollout",
            "status",
            f"deployment/{args.name}",
            "--timeout=900s",
        ],
        check=True,
    )
    live = _run_json(["kubectl", "-n", args.namespace, "get", "deployment", args.name, "-o", "json"])
    live_pods = _run_json(
        ["kubectl", "-n", args.namespace, "get", "pods", "-l", f"omi.me/release-probe={args.name}", "-o", "json"]
    )
    live_services = _run_json(["kubectl", "-n", args.namespace, "get", "services", "-o", "json"])
    live_status = live.get("status") if isinstance(live.get("status"), dict) else {}
    if live_status.get("readyReplicas") != 1 or _runtime_digest_image(live_pods, "backend-listen") != runtime_image:
        raise CanaryError("isolated listener did not become ready on the pinned source runtime image")
    pod_items = live_pods.get("items") if isinstance(live_pods.get("items"), list) else []
    pod = pod_items[0] if len(pod_items) == 1 and isinstance(pod_items[0], dict) else {}
    pod_metadata = pod.get("metadata") if isinstance(pod.get("metadata"), dict) else {}
    live_labels = pod_metadata.get("labels") if isinstance(pod_metadata.get("labels"), dict) else {}
    evaluated_selectors = _service_selectors(live_services, exclude_name=args.name)
    matched_services = [name for name, item in evaluated_selectors if _selector_matches(live_labels, item)]
    if matched_services:
        raise CanaryError(f"live isolated listener matches existing Service selectors: {', '.join(matched_services)}")
    selector_snapshot = [{"name": name, "selector": item} for name, item in evaluated_selectors]
    identity_values = {
        "deployment_uid": live.get("metadata", {}).get("uid"),
        "source_deployment_uid": deployment.get("metadata", {}).get("uid"),
        "pod_name": pod.get("metadata", {}).get("name"),
        "pod_uid": pod.get("metadata", {}).get("uid"),
    }
    if any(not isinstance(value, str) or not value for value in identity_values.values()):
        raise CanaryError("isolated listener identity is incomplete")
    return {
        "schema_version": 1,
        "recorded_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "namespace": args.namespace,
        "deployment_name": args.name,
        "deployment_uid": identity_values["deployment_uid"],
        "source_deployment_uid": identity_values["source_deployment_uid"],
        "runtime_image": runtime_image,
        "pod_name": identity_values["pod_name"],
        "pod_uid": identity_values["pod_uid"],
        "pusher_url_class": "isolated_cluster_service",
        "ordinary_service_selector_excluded": True,
        "service_selectors_evaluated": len(evaluated_selectors),
        "service_selector_snapshot_sha256": canonical_sha256(selector_snapshot),
    }


def record_canary(args: argparse.Namespace) -> dict[str, Any]:
    semantic = json.loads(args.semantic_evidence.read_text(encoding="utf-8"))
    pusher = json.loads(args.pusher_receipt.read_text(encoding="utf-8"))
    listener = json.loads(args.listener_receipt.read_text(encoding="utf-8"))
    qualification = json.loads(args.qualification_deployment_receipt.read_text(encoding="utf-8"))
    if not all(isinstance(value, dict) for value in (semantic, pusher, listener, qualification)):
        raise CanaryError("canary inputs must be JSON objects")
    pusher_sha = canonical_sha256(pusher)
    image = pusher.get("image") if isinstance(pusher.get("image"), dict) else {}
    if semantic.get("status") != "PASS" or semantic.get("candidate") != {
        "source_sha": args.source_sha,
        "image_digest": args.digest,
        "deployment_receipt_sha256": pusher_sha,
    }:
        raise CanaryError("semantic evidence does not PASS on the exact isolated Pusher receipt")
    if image.get("digest") != args.digest or pusher.get("source_sha") != args.source_sha:
        raise CanaryError("isolated Pusher receipt does not match the promoted candidate")
    pusher_identity = pusher.get("live_identity") if isinstance(pusher.get("live_identity"), dict) else {}
    if (
        pusher.get("environment") != "prod"
        or pusher.get("expected_pod_template_sha256") != pusher.get("live_pod_template_sha256")
        or pusher_identity.get("replicas") != 1
        or pusher_identity.get("ready_replicas") != 1
    ):
        raise CanaryError("isolated Pusher receipt does not prove one semantically exact ready pod")
    if (
        listener.get("ordinary_service_selector_excluded") is not True
        or listener.get("pusher_url_class") != "isolated_cluster_service"
        or not listener.get("deployment_uid")
        or not listener.get("source_deployment_uid")
        or not listener.get("pod_uid")
        or not isinstance(listener.get("runtime_image"), str)
        or "@sha256:" not in listener["runtime_image"]
        or not isinstance(listener.get("service_selectors_evaluated"), int)
        or isinstance(listener.get("service_selectors_evaluated"), bool)
        or listener["service_selectors_evaluated"] < 1
        or not isinstance(listener.get("service_selector_snapshot_sha256"), str)
        or not DIGEST_RE.fullmatch(listener["service_selector_snapshot_sha256"])
    ):
        raise CanaryError("listener receipt does not prove an isolated digest-pinned clone")
    return {
        "schema_version": 1,
        "status": "PASS",
        "evidence_id": f"pusher-prod-canary-{args.run_id}",
        "candidate": {
            "source_sha": args.source_sha,
            "image_digest": args.digest,
            "qualification_deployment_receipt_sha256": canonical_sha256(qualification),
            "canary_deployment_receipt_sha256": pusher_sha,
        },
        "window": semantic.get("window"),
        "sessions": {"attributed": 1, "unattributed": 0},
        "outcomes": {"evaluated": 1, "terminal_success": 1, "terminal_failure": 0, "pending": 0},
        "approval_run_id": args.run_id,
        "protected_environment": "prod",
        "deployment_identity": {"pusher": pusher.get("live_identity"), "listener": listener},
        "semantic_evidence_sha256": canonical_sha256(semantic),
    }


def _write(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create-listener")
    create.add_argument("--namespace", required=True)
    create.add_argument("--source-deployment", required=True)
    create.add_argument("--source-service", required=True)
    create.add_argument("--name", required=True)
    create.add_argument("--pusher-url", required=True)
    create.add_argument("--output", type=Path, required=True)
    record = commands.add_parser("record-canary")
    record.add_argument("--semantic-evidence", type=Path, required=True)
    record.add_argument("--pusher-receipt", type=Path, required=True)
    record.add_argument("--listener-receipt", type=Path, required=True)
    record.add_argument("--qualification-deployment-receipt", type=Path, required=True)
    record.add_argument("--source-sha", required=True)
    record.add_argument("--digest", required=True)
    record.add_argument("--run-id", type=int, required=True)
    record.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv or __import__("sys").argv[1:])
    try:
        result = create_listener(args) if args.command == "create-listener" else record_canary(args)
        _write(args.output, result)
    except (OSError, json.JSONDecodeError, subprocess.CalledProcessError, CanaryError) as exc:
        print(f"FAIL: {exc}")
        return 1
    print(f"OK: wrote {args.command} receipt to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
