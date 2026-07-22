#!/usr/bin/env python3
"""Validate the narrow, digest-pinned Pusher chart-only recovery profile.

The workflow supplies only Kubernetes object JSON/YAML to this program.  It
never reads ConfigMap values, Secret values, or pod logs.  The profile permits
only the known REDIS_DB_HOST source repair and an image identity that is already
an exact digest; any other chart-owned workload drift fails before Helm writes.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
from pathlib import Path
from typing import Any

import yaml

DIGEST = re.compile(r"^sha256:[a-f0-9]{64}$")
ENVIRONMENTS = {"dev", "prod"}
VOLATILE_METADATA = {
    "creationTimestamp",
    "generation",
    "managedFields",
    "resourceVersion",
    "selfLink",
    "uid",
}
# Kubernetes API-server/controller-populated Deployment fields that are absent
# from ``helm template`` output.  ``normalize()`` strips them so the drift
# comparison does not spuriously fail on a healthy live Deployment.
VOLATILE_DEPLOYMENT_ANNOTATIONS = {
    "deployment.kubernetes.io/revision",
    "meta.helm.sh/release-name",
    "meta.helm.sh/release-namespace",
}
VOLATILE_DEPLOYMENT_SPEC = {
    "revisionHistoryLimit",
}
VOLATILE_POD_TEMPLATE_SPEC = {
    "restartPolicy",
    "dnsPolicy",
    "schedulerName",
}
VOLATILE_CONTAINER_FIELDS = {
    "terminationMessagePath",
    "terminationMessagePolicy",
}

# Cluster-added Service fields absent from ``helm template`` output.
VOLATILE_SERVICE_SPEC = {
    "clusterIP",
    "clusterIPs",
    "healthCheckNodePort",
    "ipFamilies",
    "ipFamilyPolicy",
}
GKE_CONTROLLER_STATUS_ANNOTATIONS = {
    "Service": {"cloud.google.com/neg-status"},
    "Ingress": {
        "ingress.kubernetes.io/backends",
        "ingress.kubernetes.io/forwarding-rule",
        "ingress.kubernetes.io/target-proxy",
        "ingress.kubernetes.io/url-map",
    },
}
GKE_INGRESS_FINALIZERS = {
    "networking.gke.io/ingress-finalizer",
    "networking.gke.io/ingress-finalizer-V2",
}
POD_SECURITY_DEFAULTS = {
    "fsGroupChangePolicy": "Always",
    "supplementalGroupsPolicy": "Merge",
}
CONTAINER_SECURITY_DEFAULTS = {
    "allowPrivilegeEscalation": True,
    "privileged": False,
    "readOnlyRootFilesystem": False,
    "runAsNonRoot": False,
}


def load_object(path: str) -> dict[str, Any]:
    """Load exactly one Kubernetes object without ever serializing its data."""
    documents = [doc for doc in yaml.safe_load_all(Path(path).read_text(encoding="utf-8")) if isinstance(doc, dict)]
    if len(documents) != 1:
        raise ValueError(f"{path} must contain exactly one Kubernetes object")
    return documents[0]


def load_rendered_deployment(path: str) -> dict[str, Any]:
    documents = [doc for doc in yaml.safe_load_all(Path(path).read_text(encoding="utf-8")) if isinstance(doc, dict)]
    deployments = [doc for doc in documents if doc.get("kind") == "Deployment"]
    if len(deployments) != 1:
        raise ValueError("rendered chart must contain exactly one Deployment")
    return deployments[0]


def rendered_resource(path: str, kind: str, name: str) -> dict[str, Any]:
    documents = [doc for doc in yaml.safe_load_all(Path(path).read_text(encoding="utf-8")) if isinstance(doc, dict)]
    matches = [doc for doc in documents if doc.get("kind") == kind and doc.get("metadata", {}).get("name") == name]
    if len(matches) != 1:
        raise ValueError(f"rendered chart must contain exactly one {kind}/{name}")
    return matches[0]


def expected_targets(environment: str) -> tuple[str, str, str, str]:
    if environment not in ENVIRONMENTS:
        raise ValueError("environment must be dev or prod")
    return (
        f"{environment}-omi-backend",
        f"{environment}-omi-pusher",
        f"{environment}-omi-pusher",
        f"{environment}-omi-backend-config",
    )


def validate_identity(repository: str, digest: str, expected_repository: str | None = None) -> list[str]:
    failures: list[str] = []
    leaf = repository.rsplit("/", 1)[-1]
    if not repository or "@" in repository or "://" in repository or repository.endswith(":") or ":" in leaf:
        failures.append("image repository must be a non-empty repository without a tag or digest")
    if not DIGEST.fullmatch(digest):
        failures.append("image digest must be sha256:<64 lowercase hex characters>")
    if expected_repository and repository != expected_repository:
        failures.append("image repository does not match the selected environment's approved Pusher repository")
    return failures


def primary_container(deployment: dict[str, Any]) -> dict[str, Any]:
    containers = deployment.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])
    matches = [item for item in containers if isinstance(item, dict) and item.get("name") == "pusher"]
    if len(matches) != 1:
        raise ValueError("Pusher Deployment must contain exactly one pusher container")
    return matches[0]


def redis_entry(deployment: dict[str, Any]) -> dict[str, Any]:
    entries = [entry for entry in primary_container(deployment).get("env", []) if entry.get("name") == "REDIS_DB_HOST"]
    if len(entries) != 1:
        raise ValueError("Pusher Deployment must contain exactly one REDIS_DB_HOST entry")
    return entries[0]


def validate_redis_source(deployment: dict[str, Any], configmap: str) -> list[str]:
    try:
        entry = redis_entry(deployment)
    except ValueError as exc:
        return [str(exc)]
    value_from = entry.get("valueFrom")
    expected = {"name": configmap, "key": "REDIS_DB_HOST"}
    if not isinstance(value_from, dict) or value_from.get("configMapKeyRef") != expected:
        return ["REDIS_DB_HOST must use the selected backend ConfigMap key"]
    if value_from.get("secretKeyRef") is not None:
        return ["REDIS_DB_HOST must not retain a Secret source"]
    return []


def image_of(deployment: dict[str, Any]) -> str:
    image = primary_container(deployment).get("image")
    if not isinstance(image, str):
        raise ValueError("Pusher container image is missing")
    return image


def validate_target(obj: dict[str, Any], kind: str, name: str, namespace: str) -> list[str]:
    metadata = obj.get("metadata", {})
    if obj.get("kind") != kind:
        return [f"expected {kind}, found {obj.get('kind')!r}"]
    failures = []
    if metadata.get("name") != name:
        failures.append(f"expected {kind} name {name}")
    if metadata.get("namespace") not in (None, namespace):
        failures.append(f"expected {kind} namespace {namespace}")
    return failures


def is_concurrent_rollout(deployment: dict[str, Any]) -> bool:
    metadata = deployment.get("metadata", {})
    status = deployment.get("status", {})
    generation = metadata.get("generation")
    observed = status.get("observedGeneration")
    return generation is None or observed is None or generation != observed


def ready_replicas(deployment: dict[str, Any]) -> int:
    value = deployment.get("status", {}).get("readyReplicas", 0)
    return value if isinstance(value, int) else 0


def normalize(obj: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(obj)
    result.pop("status", None)
    metadata = result.get("metadata")
    if isinstance(metadata, dict):
        for key in VOLATILE_METADATA:
            metadata.pop(key, None)
        metadata.pop("namespace", None)
        annotations = metadata.get("annotations")
        if isinstance(annotations, dict):
            for key in VOLATILE_DEPLOYMENT_ANNOTATIONS:
                annotations.pop(key, None)
            for key in GKE_CONTROLLER_STATUS_ANNOTATIONS.get(result.get("kind"), set()):
                annotations.pop(key, None)
            if not annotations:
                metadata.pop("annotations", None)
        if result.get("kind") == "Ingress":
            finalizers = metadata.get("finalizers")
            if isinstance(finalizers, list):
                metadata["finalizers"] = [item for item in finalizers if item not in GKE_INGRESS_FINALIZERS]
                if not metadata["finalizers"]:
                    metadata.pop("finalizers", None)
    if result.get("kind") == "Service":
        spec = result.get("spec", {})
        for key in VOLATILE_SERVICE_SPEC:
            spec.pop(key, None)
        # These fields are defaulted by the Service API when the chart omits
        # them. Strip only their documented defaults; non-default policies are
        # meaningful drift and must remain visible to the recovery profile.
        if spec.get("internalTrafficPolicy") == "Cluster":
            spec.pop("internalTrafficPolicy", None)
        if spec.get("sessionAffinity") == "None":
            spec.pop("sessionAffinity", None)
        if spec.get("sessionAffinityConfig") == {}:
            spec.pop("sessionAffinityConfig", None)
    if result.get("kind") == "Deployment":
        _strip_deployment_defaults(result)
    return remove_nulls(result)


def _strip_deployment_defaults(deployment: dict[str, Any]) -> None:
    """Remove Deployment-specific API-server/controller defaults absent from helm template."""
    spec = deployment.get("spec", {})
    for key in VOLATILE_DEPLOYMENT_SPEC:
        spec.pop(key, None)
    if spec.get("minReadySeconds") == 0:
        spec.pop("minReadySeconds", None)

    template = spec.get("template", {})
    template_spec = template.get("spec", {})
    for key in VOLATILE_POD_TEMPLATE_SPEC:
        template_spec.pop(key, None)
    if template_spec.get("serviceAccount") == template_spec.get("serviceAccountName"):
        template_spec.pop("serviceAccount", None)
    _strip_default_security_context(template_spec, "securityContext", POD_SECURITY_DEFAULTS)

    for container in template_spec.get("containers", []):
        for key in VOLATILE_CONTAINER_FIELDS:
            container.pop(key, None)
        _strip_default_security_context(container, "securityContext", CONTAINER_SECURITY_DEFAULTS)
        for probe_name in ("livenessProbe", "readinessProbe", "startupProbe"):
            probe = container.get(probe_name)
            if not isinstance(probe, dict):
                continue
            http_get = probe.get("httpGet")
            if isinstance(http_get, dict) and http_get.get("scheme") == "HTTP":
                http_get.pop("scheme", None)
            if probe.get("successThreshold") == 1:
                probe.pop("successThreshold", None)


def _strip_default_security_context(parent: dict[str, Any], field: str, defaults: dict[str, Any]) -> None:
    context = parent.get(field)
    if not isinstance(context, dict):
        return
    for key, value in defaults.items():
        if context.get(key) == value:
            context.pop(key, None)
    if not context:
        parent.pop(field, None)


def remove_nulls(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: remove_nulls(child) for key, child in value.items() if child is not None}
    if isinstance(value, list):
        return [remove_nulls(child) for child in value]
    return value


def replace_env_by_name(entries: list[dict[str, Any]], desired: dict[str, Any]) -> list[dict[str, Any]]:
    """Model Kubernetes named-list strategic merge, including explicit null deletion."""
    result = copy.deepcopy(entries)
    for index, entry in enumerate(result):
        if entry.get("name") == desired.get("name"):
            result[index] = strategic_merge(entry, desired)
            return result
    result.append(copy.deepcopy(desired))
    return result


def strategic_merge(live: Any, desired: Any) -> Any:
    if desired is None:
        return None
    if not isinstance(live, dict) or not isinstance(desired, dict):
        return copy.deepcopy(desired)
    merged = copy.deepcopy(live)
    for key, value in desired.items():
        if value is None:
            merged.pop(key, None)
        else:
            merged[key] = strategic_merge(merged.get(key), value)
    return merged


def allowed_recovery_drift(
    live: dict[str, Any], rendered: dict[str, Any], *, autoscaling_enabled: bool = False
) -> list[str]:
    """Compare chart-owned objects after replacing only image and REDIS source."""
    adapted = copy.deepcopy(live)
    try:
        live_container = primary_container(adapted)
        desired_container = primary_container(rendered)
        live_container["image"] = desired_container["image"]
        live_container["env"] = replace_env_by_name(live_container.get("env", []), redis_entry(rendered))
    except ValueError as exc:
        return [str(exc)]
    # The HPA is the replica-count authority.  Helm intentionally omits the
    # Deployment replica count when that HPA is present; only discard the
    # live controller value in that exact case.  Never strip a rendered value.
    if autoscaling_enabled:
        adapted.get("spec", {}).pop("replicas", None)
    return (
        []
        if normalize(adapted) == normalize(rendered)
        else ["recovery profile would change Deployment fields outside the exact image and REDIS_DB_HOST transition"]
    )


def hpa_controls_deployment(hpa: dict[str, Any], deployment_name: str) -> bool:
    """Return true only for an apps/v1 HPA targetting this exact Deployment."""
    target = hpa.get("spec", {}).get("scaleTargetRef")
    return target == {"apiVersion": "apps/v1", "kind": "Deployment", "name": deployment_name}


def validate_chart_owned_resource_drift(live: dict[str, Any], rendered: dict[str, Any], kind: str) -> list[str]:
    """Require Service/HPA/PDB identity and spec to remain unchanged."""
    return (
        []
        if normalize(live) == normalize(rendered)
        else [f"recovery profile would change {kind} outside the allowlist"]
    )


def configmap_has_key(configmap: dict[str, Any], name: str, namespace: str) -> list[str]:
    failures = validate_target(configmap, "ConfigMap", name, namespace)
    data = configmap.get("data")
    if not isinstance(data, dict) or "REDIS_DB_HOST" not in data:
        failures.append("required ConfigMap key REDIS_DB_HOST is unavailable")
    return failures


def serving_pusher_digests(pods: dict[str, Any]) -> set[str]:
    """Read image IDs from Ready Pusher containers, never resolving a mutable tag."""
    digests: set[str] = set()
    ready_containers = 0
    for pod in pods.get("items", []):
        for status in pod.get("status", {}).get("containerStatuses", []):
            if status.get("name") != "pusher" or not status.get("ready"):
                continue
            ready_containers += 1
            image_id = status.get("imageID")
            match = re.search(r"sha256:[a-f0-9]{64}", image_id or "")
            if not match:
                raise ValueError("a Ready Pusher container has no immutable image digest status")
            digests.add(match.group(0))
    if not ready_containers:
        raise ValueError("no Ready Pusher container image status is available")
    return digests


def serving_pusher_images(pods: dict[str, Any]) -> set[str]:
    """Return full repository@digest identities from Ready serving containers."""
    images: set[str] = set()
    for pod in pods.get("items", []):
        for status in pod.get("status", {}).get("containerStatuses", []):
            if status.get("name") != "pusher" or not status.get("ready"):
                continue
            image_id = status.get("imageID") or ""
            identity = image_id.split("://", 1)[-1]
            if not re.fullmatch(r"[a-z0-9][a-z0-9./_-]*@sha256:[a-f0-9]{64}", identity):
                raise ValueError("a Ready Pusher container has no full immutable repository and digest status")
            images.add(identity)
    if not images:
        raise ValueError("no Ready Pusher container image status is available")
    return images


def redact(obj: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(obj)
    for key in ("data", "stringData", "binaryData"):
        result.pop(key, None)
    return result


def evidence(deployment: dict[str, Any], configmap: dict[str, Any], baseline: int) -> dict[str, Any]:
    return {
        "deployment_image": image_of(deployment),
        "deployment_generation": deployment.get("metadata", {}).get("generation"),
        "configmap_resource_version": configmap.get("metadata", {}).get("resourceVersion"),
        "ready_baseline": baseline,
        "ready_replicas": ready_replicas(deployment),
        "configmap": redact(configmap),
    }


def preflight(args: argparse.Namespace) -> list[str]:
    namespace, release, deployment_name, configmap_name = expected_targets(args.environment)
    failures = validate_identity(args.repository, args.digest, args.expected_repository)
    if args.namespace != namespace or args.release != release or args.deployment != deployment_name:
        failures.append("selected namespace, release, or Deployment is not the selected environment's Pusher target")
    live = load_object(args.live_deployment)
    rendered = load_rendered_deployment(args.rendered)
    configmap = load_object(args.live_configmap)
    failures += validate_target(live, "Deployment", deployment_name, namespace)
    failures += validate_target(rendered, "Deployment", deployment_name, namespace)
    failures += configmap_has_key(configmap, configmap_name, namespace)
    expected_image = f"{args.repository}@{args.digest}"
    try:
        if image_of(rendered) != expected_image:
            failures.append("rendered Pusher image is not the admitted exact digest")
    except ValueError as exc:
        failures.append(str(exc))
    failures += validate_redis_source(rendered, configmap_name)
    autoscaling_enabled = False
    if args.live_hpa:
        try:
            live_hpa = load_object(args.live_hpa)
            rendered_hpa = rendered_resource(args.rendered, "HorizontalPodAutoscaler", release)
            autoscaling_enabled = hpa_controls_deployment(live_hpa, deployment_name) and hpa_controls_deployment(
                rendered_hpa, deployment_name
            )
        except ValueError:
            # The normal chart-owned resource validation below reports the
            # malformed or missing HPA.  Keep Deployment replicas fail-closed.
            pass
    failures += allowed_recovery_drift(live, rendered, autoscaling_enabled=autoscaling_enabled)
    if not args.live_pods:
        failures.append("recovery preflight is missing live Pusher pod image-status evidence")
    else:
        try:
            images = serving_pusher_images(load_object(args.live_pods))
            if images != {f"{args.repository}@{args.digest}"}:
                failures.append("serving Ready Pusher repository and digest do not exactly match the admitted image")
        except ValueError as exc:
            failures.append(str(exc))
    for kind, name, supplied in (
        ("Service", release, args.live_service),
        ("HorizontalPodAutoscaler", release, args.live_hpa),
        ("PodDisruptionBudget", release, args.live_pdb),
        ("Ingress", release, args.live_ingress),
        ("ServiceAccount", release, args.live_serviceaccount),
        ("BackendConfig", f"{args.environment}-pusher-backend-config", args.live_backendconfig),
    ):
        if not supplied:
            failures.append(f"recovery preflight is missing live {kind} evidence")
            continue
        live_resource = load_object(supplied)
        failures += validate_target(live_resource, kind, name, namespace)
        try:
            failures += validate_chart_owned_resource_drift(
                live_resource, rendered_resource(args.rendered, kind, name), kind
            )
        except ValueError as exc:
            failures.append(str(exc))
    if args.expected_evidence:
        previous = json.loads(Path(args.expected_evidence).read_text(encoding="utf-8"))
        if previous.get("deployment_image") != image_of(live):
            failures.append("Pusher image identity changed after the captured preflight")
        if previous.get("configmap_resource_version") != configmap.get("metadata", {}).get("resourceVersion"):
            failures.append("Pusher ConfigMap identity changed after the captured preflight")
    if is_concurrent_rollout(live):
        failures.append("concurrent Pusher rollout detected")
    if ready_replicas(live) < args.ready_baseline:
        failures.append("Pusher Ready count is below the declared containment baseline")
    if not failures and args.evidence:
        Path(args.evidence).write_text(
            json.dumps(evidence(live, configmap, args.ready_baseline), indent=2) + "\n", encoding="utf-8"
        )
    return failures


def postverify(args: argparse.Namespace) -> list[str]:
    namespace, _release, deployment_name, configmap_name = expected_targets(args.environment)
    deployment = load_object(args.live_deployment)
    failures = validate_target(deployment, "Deployment", deployment_name, namespace)
    try:
        if image_of(deployment) != f"{args.repository}@{args.digest}":
            failures.append("serving Pusher image is not the admitted exact digest")
    except ValueError as exc:
        failures.append(str(exc))
    failures += validate_redis_source(deployment, configmap_name)
    if ready_replicas(deployment) < args.ready_baseline:
        failures.append("Pusher Ready count is below the declared containment baseline")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("preflight", "postverify"))
    parser.add_argument("--environment", required=True, choices=sorted(ENVIRONMENTS))
    parser.add_argument("--namespace", required=True)
    parser.add_argument("--release", default="")
    parser.add_argument("--deployment", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--expected-repository")
    parser.add_argument("--digest", required=True)
    parser.add_argument("--ready-baseline", type=int, required=True)
    parser.add_argument("--live-deployment", required=True)
    parser.add_argument("--live-configmap")
    parser.add_argument("--rendered")
    parser.add_argument("--evidence")
    parser.add_argument("--expected-evidence")
    parser.add_argument("--live-service")
    parser.add_argument("--live-hpa")
    parser.add_argument("--live-pdb")
    parser.add_argument("--live-pods")
    parser.add_argument("--live-ingress")
    parser.add_argument("--live-serviceaccount")
    parser.add_argument("--live-backendconfig")
    args = parser.parse_args()
    if args.ready_baseline <= 0:
        parser.error("--ready-baseline must be positive")
    if args.mode == "preflight" and (not args.live_configmap or not args.rendered):
        parser.error("preflight requires --live-configmap and --rendered")
    failures = preflight(args) if args.mode == "preflight" else postverify(args)
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    print(f"Pusher chart-only {args.mode} passed without exposing ConfigMap values.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
