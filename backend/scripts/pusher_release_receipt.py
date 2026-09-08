#!/usr/bin/env python3
"""Create exact, non-secret Pusher deployment and qualification receipts.

The development workflow records what Kubernetes actually serves after a
rollout. A separate semantic-probe receipt may then qualify that deployment.
Missing probe evidence is recorded as ``NOT_RUN`` and production deliberately
rejects it.
"""

from __future__ import annotations

import argparse
import copy
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
DIGEST_RE = re.compile(r"^sha256:[a-f0-9]{64}$")
SHA_RE = re.compile(r"^[a-f0-9]{40}$")
RECEIPT_SCHEMA_VERSION = 1
QUALIFICATION_SCHEMA_VERSION = 2
CONTRACT_FILES = (
    ROOT / "backend/scripts/pusher_release_receipt.py",
    ROOT / "backend/scripts/pusher_semantic_probe.py",
    ROOT / "backend/scripts/pusher_prod_canary.py",
    ROOT / "backend/scripts/verify_pusher_live_alert_route.py",
    ROOT / "backend/scripts/runtime_env_capability_contracts.py",
    ROOT / "backend/scripts/runtime_env_validation/manifest.py",
    ROOT / "backend/scripts/validate-backend-runtime-env.py",
    ROOT / "backend/config/memory_rollout.py",
    ROOT / "backend/deploy/runtime_env/_base.yaml",
    ROOT / "backend/deploy/runtime_env/dev.overlay.yaml",
    ROOT / "backend/deploy/runtime_env/prod.overlay.yaml",
    ROOT / "backend/deploy/runtime_env.yaml",
    ROOT / "backend/scripts/verify_pusher_promotion_evidence.py",
    ROOT / "backend/testing/release_fixtures/transcription-release-probe.json",
    ROOT / "backend/testing/release_fixtures/transcription-release-probe.wav",
    ROOT / ".github/workflows/gcp_backend_pusher_auto_deploy.yml",
    ROOT / ".github/workflows/gcp_backend_pusher.yml",
)


class ReceiptError(ValueError):
    """The runtime state cannot prove the requested deployment identity."""


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def contract_fingerprint() -> str:
    return _canonical_sha256(
        {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in CONTRACT_FILES}
    )


def _run_json(command: list[str]) -> dict[str, Any]:
    result = subprocess.run(command, check=False, capture_output=True, text=True)
    if result.returncode:
        raise ReceiptError(result.stderr.strip() or f"command failed: {' '.join(command)}")
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ReceiptError(f"command returned invalid JSON: {' '.join(command)}") from exc
    if not isinstance(value, dict):
        raise ReceiptError(f"command did not return a JSON object: {' '.join(command)}")
    return value


def rendered_chart_documents(
    environment: str,
    repository: str,
    digest: str,
    *,
    release_name: str | None = None,
    isolated_canary: bool = False,
    config_map_name: str | None = None,
) -> list[dict[str, Any]]:
    if environment not in {"dev", "prod"}:
        raise ReceiptError("Pusher receipt environment must be dev or prod")
    if not DIGEST_RE.fullmatch(digest):
        raise ReceiptError("Pusher receipt requires an exact sha256 image digest")
    chart = ROOT / "backend/charts/pusher"
    release = release_name or f"{environment}-omi-pusher"
    runtime_config_map = config_map_name or f"{environment}-omi-backend-config"
    command = [
        "helm",
        "template",
        release,
        str(chart),
        "-f",
        str(chart / f"{environment}_omi_pusher_values.yaml"),
        "--set-string",
        f"image.repository={repository}",
        "--set-string",
        f"image.digest={digest}",
        "--set-string",
        "image.tag=",
        "--set-string",
        "image.pullPolicy=IfNotPresent",
        "--set-string",
        f"runtimeConfigMapName={runtime_config_map}",
    ]
    if isolated_canary:
        command.extend(
            [
                "--set-string",
                f"fullnameOverride={release}",
                "--set",
                "autoscaling.enabled=false",
                "--set",
                "replicaCount=1",
                "--set",
                "ingress.enabled=false",
                "--set-json",
                "podDisruptionBudget=null",
                "--set-string",
                f"service.backendConfig={release}-backend-config",
                "--set-json",
                "service.annotations={}",
            ]
        )
    result = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise ReceiptError(result.stderr.strip() or "Pusher Helm render failed")
    documents = [document for document in yaml.safe_load_all(result.stdout) if isinstance(document, dict)]
    documents.sort(key=lambda item: (str(item.get("kind", "")), str(item.get("metadata", {}).get("name", ""))))
    return documents


def pod_template_semantic_projection(template: dict[str, Any]) -> dict[str, Any]:
    """Project capability-relevant PodTemplate fields without API defaults."""
    spec = template.get("spec") if isinstance(template.get("spec"), dict) else {}
    containers = [
        item for item in spec.get("containers", []) if isinstance(item, dict) and item.get("name") == "pusher"
    ]
    if len(containers) != 1:
        raise ReceiptError("Pusher PodTemplate must contain exactly one named pusher container")
    container = containers[0]
    env = container.get("env") if isinstance(container.get("env"), list) else []
    memory_entries = [item for item in env if isinstance(item, dict) and item.get("name") == "MEMORY_ENABLED"]
    if len(memory_entries) != 1 or str(memory_entries[0].get("value", "")).strip().lower() not in {"on", "true", "1"}:
        raise ReceiptError("Pusher live PodTemplate MEMORY_ENABLED does not resolve to on")
    container_fields = (
        "name",
        "image",
        "imagePullPolicy",
        "command",
        "args",
        "envFrom",
        "ports",
        "livenessProbe",
        "readinessProbe",
        "startupProbe",
        "resources",
        "lifecycle",
        "securityContext",
        "volumeMounts",
    )
    pod_fields = (
        "serviceAccountName",
        "automountServiceAccountToken",
        "securityContext",
        "volumes",
        "nodeSelector",
        "affinity",
        "tolerations",
        "topologySpreadConstraints",
        "imagePullSecrets",
        "runtimeClassName",
    )
    projected_container = {field: copy.deepcopy(container[field]) for field in container_fields if field in container}
    projected_container["env"] = sorted(
        (copy.deepcopy(item) for item in env if isinstance(item, dict)), key=lambda item: str(item.get("name", ""))
    )
    for probe_name in ("livenessProbe", "readinessProbe", "startupProbe"):
        probe = projected_container.get(probe_name)
        if isinstance(probe, dict):
            probe.setdefault("initialDelaySeconds", 0)
            probe.setdefault("timeoutSeconds", 1)
            probe.setdefault("periodSeconds", 10)
            probe.setdefault("successThreshold", 1)
            probe.setdefault("failureThreshold", 3)
            http_get = probe.get("httpGet") if isinstance(probe.get("httpGet"), dict) else None
            if http_get is not None:
                http_get.setdefault("scheme", "HTTP")
    resources = projected_container.get("resources")
    if isinstance(resources, dict):
        for scope in ("requests", "limits"):
            values = resources.get(scope) if isinstance(resources.get(scope), dict) else None
            if values is not None:
                for resource_name in ("cpu", "memory"):
                    if resource_name in values:
                        values[resource_name] = _normalize_resource_quantity(resource_name, values[resource_name])
    return {
        "container": projected_container,
        "pod": {field: copy.deepcopy(spec[field]) for field in pod_fields if field in spec},
    }


def _normalize_resource_quantity(resource_name: str, raw: Any) -> str:
    value = str(raw)
    try:
        if resource_name == "cpu":
            milli = Decimal(value[:-1]) if value.endswith("m") else Decimal(value) * 1000
            return f"{format(milli.normalize(), 'f')}m"
        binary_units = {"Ki": 1024, "Mi": 1024**2, "Gi": 1024**3, "Ti": 1024**4}
        for suffix, multiplier in binary_units.items():
            if value.endswith(suffix):
                return str(int(Decimal(value[: -len(suffix)]) * multiplier))
        return str(int(Decimal(value)))
    except (InvalidOperation, ValueError):
        raise ReceiptError(f"Pusher PodTemplate has invalid {resource_name} quantity") from None


def rendered_chart_fingerprint(
    environment: str,
    repository: str,
    digest: str,
    *,
    release_name: str | None = None,
    isolated_canary: bool = False,
    config_map_name: str | None = None,
) -> str:
    return _canonical_sha256(
        rendered_chart_documents(
            environment,
            repository,
            digest,
            release_name=release_name,
            isolated_canary=isolated_canary,
            config_map_name=config_map_name,
        )
    )


def config_fingerprint(config_map: dict[str, Any], *, expected_name: str) -> str:
    metadata = config_map.get("metadata") if isinstance(config_map.get("metadata"), dict) else {}
    if metadata.get("name") != expected_name:
        raise ReceiptError(f"live ConfigMap identity does not match {expected_name}")
    data = config_map.get("data") if isinstance(config_map.get("data"), dict) else {}
    binary_data = config_map.get("binaryData") if isinstance(config_map.get("binaryData"), dict) else {}
    # Only the digest leaves this process; no ConfigMap value is included in a receipt.
    return _canonical_sha256({"data": data, "binaryData": binary_data})


def _pusher_image(container: dict[str, Any]) -> str | None:
    return container.get("image") if container.get("name") == "pusher" else None


def validate_live_identity(
    deployment: dict[str, Any],
    pods: dict[str, Any],
    *,
    namespace: str,
    repository: str,
    digest: str,
    expected_deployment_name: str | None = None,
) -> dict[str, Any]:
    expected_image = f"{repository}@{digest}"
    metadata = deployment.get("metadata") if isinstance(deployment.get("metadata"), dict) else {}
    spec = deployment.get("spec") if isinstance(deployment.get("spec"), dict) else {}
    status = deployment.get("status") if isinstance(deployment.get("status"), dict) else {}
    generation = metadata.get("generation")
    deployment_name = metadata.get("name")
    deployment_uid = metadata.get("uid")
    expected_name = expected_deployment_name or f"{namespace.split('-omi-backend', 1)[0]}-omi-pusher"
    if deployment_name != expected_name or not isinstance(deployment_uid, str) or not deployment_uid:
        raise ReceiptError("live Pusher Deployment identity is incomplete or unexpected")
    observed_generation = status.get("observedGeneration")
    replicas = status.get("replicas", 0)
    ready_replicas = status.get("readyReplicas", 0)
    available_replicas = status.get("availableReplicas", 0)
    if not isinstance(generation, int) or observed_generation != generation:
        raise ReceiptError("live Pusher Deployment generation is not fully observed")
    if not isinstance(replicas, int) or replicas < 1 or ready_replicas != replicas or available_replicas != replicas:
        raise ReceiptError("live Pusher Deployment is not fully ready and available")
    template = spec.get("template") if isinstance(spec.get("template"), dict) else {}
    pod_spec = template.get("spec") if isinstance(template.get("spec"), dict) else {}
    template_images = [
        image
        for item in pod_spec.get("containers", [])
        if isinstance(item, dict)
        for image in [_pusher_image(item)]
        if image
    ]
    if template_images != [expected_image]:
        raise ReceiptError("live Pusher Deployment template does not use the exact candidate digest")

    items = pods.get("items") if isinstance(pods.get("items"), list) else []
    identities: list[dict[str, Any]] = []
    for pod in items:
        if not isinstance(pod, dict):
            continue
        pod_metadata = pod.get("metadata") if isinstance(pod.get("metadata"), dict) else {}
        pod_spec = pod.get("spec") if isinstance(pod.get("spec"), dict) else {}
        pod_status = pod.get("status") if isinstance(pod.get("status"), dict) else {}
        spec_images = [
            image
            for item in pod_spec.get("containers", [])
            if isinstance(item, dict)
            for image in [_pusher_image(item)]
            if image
        ]
        statuses = [
            item
            for item in pod_status.get("containerStatuses", [])
            if isinstance(item, dict) and item.get("name") == "pusher"
        ]
        if spec_images != [expected_image] or len(statuses) != 1:
            raise ReceiptError("a live Pusher pod does not use the exact candidate image")
        image_id = statuses[0].get("imageID")
        pod_name = pod_metadata.get("name")
        pod_uid = pod_metadata.get("uid")
        if not isinstance(pod_name, str) or not pod_name or not isinstance(pod_uid, str) or not pod_uid:
            raise ReceiptError("a live Pusher pod identity is incomplete")
        if not isinstance(image_id, str) or not image_id.endswith(f"@{digest}") or statuses[0].get("ready") is not True:
            raise ReceiptError("a live Pusher pod has not started the exact candidate digest as Ready")
        identities.append({"name": pod_name, "uid": pod_uid, "image_id": image_id})
    if len(identities) != replicas:
        raise ReceiptError("live Pusher pod identities do not cover every ready replica")
    identities.sort(key=lambda item: str(item["name"]))
    return {
        "deployment_name": deployment_name,
        "deployment_uid": deployment_uid,
        "generation": generation,
        "observed_generation": observed_generation,
        "namespace": namespace,
        "ready_replicas": ready_replicas,
        "replicas": replicas,
        "pods": identities,
    }


def record_live_receipt(
    *,
    environment: str,
    namespace: str,
    repository: str,
    digest: str,
    source_sha: str,
    run_id: int,
    release_name: str | None = None,
    isolated_canary: bool = False,
    config_map_name: str | None = None,
) -> dict[str, Any]:
    if not SHA_RE.fullmatch(source_sha):
        raise ReceiptError("Pusher receipt requires a full lowercase source SHA")
    release = release_name or f"{environment}-omi-pusher"
    deployment = _run_json(["kubectl", "-n", namespace, "get", "deployment", release, "-o", "json"])
    pods = _run_json(
        ["kubectl", "-n", namespace, "get", "pods", "-l", f"app.kubernetes.io/instance={release}", "-o", "json"]
    )
    config_name = config_map_name or f"{environment}-omi-backend-config"
    config_map = _run_json(["kubectl", "-n", namespace, "get", "configmap", config_name, "-o", "json"])
    identity = validate_live_identity(
        deployment,
        pods,
        namespace=namespace,
        repository=repository,
        digest=digest,
        expected_deployment_name=release,
    )
    rendered_documents = rendered_chart_documents(
        environment,
        repository,
        digest,
        release_name=release,
        isolated_canary=isolated_canary,
        config_map_name=config_name,
    )
    expected_deployments = [
        document
        for document in rendered_documents
        if document.get("kind") == "Deployment" and document.get("metadata", {}).get("name") == release
    ]
    if len(expected_deployments) != 1:
        raise ReceiptError("rendered Pusher chart must contain exactly one expected Deployment")
    expected_template_sha = _canonical_sha256(
        pod_template_semantic_projection(expected_deployments[0].get("spec", {}).get("template", {}))
    )
    live_template_sha = _canonical_sha256(
        pod_template_semantic_projection(deployment.get("spec", {}).get("template", {}))
    )
    if live_template_sha != expected_template_sha:
        raise ReceiptError("live Pusher PodTemplate semantics do not match the rendered candidate")
    return {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "environment": "development" if environment == "dev" else "prod",
        "recorded_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "run_id": run_id,
        "source_sha": source_sha,
        "image": {"repository": repository, "digest": digest},
        "rendered_chart_sha256": _canonical_sha256(rendered_documents),
        "expected_pod_template_sha256": expected_template_sha,
        "live_pod_template_sha256": live_template_sha,
        "config_sha256": config_fingerprint(config_map, expected_name=config_name),
        "live_identity": identity,
    }


def _load_optional_evidence(path: Path | None, *, kind: str) -> dict[str, Any]:
    if path is None:
        return {
            "status": "NOT_RUN",
            "reason": f"NO_SAFE_{kind.upper()}_EVIDENCE_PRODUCER",
        }
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReceiptError(f"could not read {kind} evidence: {exc}") from exc
    if not isinstance(value, dict):
        raise ReceiptError(f"{kind} evidence must be a JSON object")
    return value


def record_qualification(deployment_receipt: dict[str, Any], *, semantic_probe_path: Path | None) -> dict[str, Any]:
    image = deployment_receipt.get("image") if isinstance(deployment_receipt.get("image"), dict) else {}
    semantic_probe = _load_optional_evidence(semantic_probe_path, kind="semantic_probe")
    return {
        "schema_version": QUALIFICATION_SCHEMA_VERSION,
        "qualification_status": "PASS" if semantic_probe.get("status") == "PASS" else "BLOCKED",
        "environment": "development",
        "workflow": "gcp_backend_pusher_auto_deploy.yml",
        "run_id": deployment_receipt.get("run_id"),
        "source_sha": deployment_receipt.get("source_sha"),
        "image_repository": image.get("repository"),
        "image_digest": image.get("digest"),
        "rendered_chart_sha256": deployment_receipt.get("rendered_chart_sha256"),
        "config_sha256": deployment_receipt.get("config_sha256"),
        "expected_pod_template_sha256": deployment_receipt.get("expected_pod_template_sha256"),
        "live_pod_template_sha256": deployment_receipt.get("live_pod_template_sha256"),
        "deployment_receipt_sha256": _canonical_sha256(deployment_receipt),
        "contract_sha256": contract_fingerprint(),
        "semantic_probe": semantic_probe,
    }


def _write(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    live = subparsers.add_parser("record-live")
    live.add_argument("--environment", choices=("dev", "prod"), required=True)
    live.add_argument("--namespace", required=True)
    live.add_argument("--repository", required=True)
    live.add_argument("--digest", required=True)
    live.add_argument("--source-sha", required=True)
    live.add_argument("--run-id", type=int, required=True)
    live.add_argument("--release-name")
    live.add_argument("--isolated-canary", action="store_true")
    live.add_argument("--config-map-name")
    live.add_argument("--output", type=Path, required=True)
    qualification = subparsers.add_parser("record-qualification")
    qualification.add_argument("--deployment-receipt", type=Path, required=True)
    qualification.add_argument("--semantic-probe-evidence", type=Path)
    qualification.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    try:
        if args.command == "record-live":
            value = record_live_receipt(
                environment=args.environment,
                namespace=args.namespace,
                repository=args.repository,
                digest=args.digest,
                source_sha=args.source_sha,
                run_id=args.run_id,
                release_name=args.release_name,
                isolated_canary=args.isolated_canary,
                config_map_name=args.config_map_name,
            )
        else:
            raw = json.loads(args.deployment_receipt.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ReceiptError("deployment receipt must be a JSON object")
            value = record_qualification(
                raw,
                semantic_probe_path=args.semantic_probe_evidence,
            )
        _write(args.output, value)
    except (OSError, json.JSONDecodeError, ReceiptError) as exc:
        print(f"FAIL: {exc}")
        return 1
    print(f"OK: wrote Pusher {args.command} evidence to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
