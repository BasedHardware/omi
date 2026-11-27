#!/usr/bin/env python3
"""Record the smallest-radius candidate→baseline admission proof.

The canonical canary is a separate Deployment (`prod-omi-pusher-canary-<run>`)
created with the candidate image at one replica. Immediately after it is ready,
this records a `kubectl --dry-run=server` patch that would restore the image the
main Pusher was serving before the move. It is the only object that currently
holds the candidate, so the inverse is proven there before any promote.

The guarded patch is the same shape the live image-only write uses: UID,
resourceVersion, container name and old digest preconditions, then one replace.

It runs only on a `pusher_canary_only` dispatch, the canary evidence producer for
the protected image-only promote. A regular deploy may redeploy the serving image,
so a candidate→baseline inverse is not applicable there.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

from pusher_image_rehearsal import Refused, config_references, require, version

IMAGE = re.compile(r"gcr\.io/based-hardware/(?:backend-)?pusher@sha256:[a-f0-9]{64}")
SHA = re.compile(r"[a-f0-9]{40}")
NAME = re.compile(r"[a-z0-9][a-z0-9.-]{0,252}")
STORAGE_METADATA = {"uid", "resourceVersion", "generation", "creationTimestamp", "managedFields"}
CONTAINER_FIELDS = (
    "env",
    "envFrom",
    "command",
    "args",
    "ports",
    "resources",
    "volumeMounts",
    "securityContext",
    "imagePullPolicy",
    "lifecycle",
    "startupProbe",
    "livenessProbe",
    "readinessProbe",
)
POD_FIELDS = (
    ("service_account", "serviceAccountName"),
    ("node_selector", "nodeSelector"),
    ("tolerations", "tolerations"),
    ("affinity", "affinity"),
    ("pod_security_context", "securityContext"),
    ("init_containers", "initContainers"),
    ("topology_spread", "topologySpreadConstraints"),
    ("priority_class", "priorityClassName"),
    ("restart_policy", "restartPolicy"),
    ("termination_grace", "terminationGracePeriodSeconds"),
    ("dns_config", "dnsConfig"),
    ("volumes", "volumes"),
)
PARITY_CLASSES = (
    "container_names",
    *(f"container_{field}" for field in CONTAINER_FIELDS),
    "pod_labels",
    "pod_annotations",
    *(label for label, _ in POD_FIELDS),
    "dependency_references",
    # Catch-all: every Pod template field not named above (hostNetwork, dnsPolicy,
    # unlisted container fields, ...), so an unlisted difference cannot read `equal`.
    "other_template_fields",
)
# Not startup inputs: the canary runs the candidate by design, the hash label is
# controller-generated, and `kubectl rollout restart` stamps a restart time.
RESTARTED_AT = "kubectl.kubernetes.io/restartedAt"
PARITY_EXCLUDED = (
    "containers[*].image",
    "metadata.labels.pod-template-hash",
    f"metadata.annotations.{RESTARTED_AT}",
)
# The canary's two deliberate isolation renames, mapped back before comparison.
PARITY_NORMALIZED = ("release_name", "runtime_config_map")


def read_json(path):
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path, value):
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


def comparable(obj):
    metadata = {key: value for key, value in obj["metadata"].items() if key not in STORAGE_METADATA}
    return {**{key: value for key, value in obj.items() if key not in {"metadata", "status"}}, "metadata": metadata}


def container_index(obj, name):
    require(
        obj.get("apiVersion") == "apps/v1"
        and obj.get("kind") == "Deployment"
        and obj["metadata"]["name"] == name
        and not obj["metadata"].get("deletionTimestamp"),
        "wrong_canary_target",
    )
    containers = obj["spec"]["template"]["spec"]["containers"]
    matches = [index for index, container in enumerate(containers) if container["name"] == "pusher"]
    require(len(matches) == 1, "pusher_container_ambiguous")
    return matches[0]


def image_of(obj, name):
    return obj["spec"]["template"]["spec"]["containers"][container_index(obj, name)]["image"]


def with_image(obj, name, image):
    expected = copy.deepcopy(comparable(obj))
    expected["spec"]["template"]["spec"]["containers"][container_index(obj, name)]["image"] = image
    return expected


def guarded_patch(obj, name, expected, desired):
    require(IMAGE.fullmatch(expected) and IMAGE.fullmatch(desired) and expected != desired, "unpinned_canary_image")
    require(image_of(obj, name) == expected, "canary_does_not_hold_candidate")
    uid, revision = version(obj)
    path = f"/spec/template/spec/containers/{container_index(obj, name)}"
    return [
        {"op": "test", "path": "/metadata/uid", "value": uid},
        {"op": "test", "path": "/metadata/resourceVersion", "value": revision},
        {"op": "test", "path": f"{path}/name", "value": "pusher"},
        {"op": "test", "path": f"{path}/image", "value": expected},
        {"op": "replace", "path": f"{path}/image", "value": desired},
    ]


def pod_template(obj):
    template = copy.deepcopy(obj["spec"]["template"])
    template.setdefault("metadata", {}).get("labels", {}).pop("pod-template-hash", None)
    return template


def template_sha256(obj):
    """Identity of a Deployment's Pod template, so a later run can prove it is unchanged."""
    encoded = json.dumps(pod_template(obj), sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _containers(template):
    return {container["name"]: container for container in template["spec"]["containers"]}


def _strip_images(items):
    stripped = []
    for item in items or []:
        if isinstance(item, dict):
            stripped.append({key: value for key, value in item.items() if key != "image"})
        else:
            stripped.append(item)
    return stripped


def _pod_metadata(template):
    metadata = template.get("metadata") or {}
    return {
        key: {
            field: value
            for field, value in (metadata.get(key) or {}).items()
            if field not in {"pod-template-hash", RESTARTED_AT}
        }
        for key in ("labels", "annotations")
    }


def _rename(value, names):
    """Map exact canary-only string values (its release and ConfigMap names) to live ones."""
    if isinstance(value, dict):
        return {key: _rename(item, names) for key, item in value.items()}
    if isinstance(value, list):
        return [_rename(item, names) for item in value]
    if isinstance(value, str):
        return names.get(value, value)
    return value


def _remainder(template):
    """Every template field the named classes do not cover; images are excluded."""
    rest = copy.deepcopy(template)
    metadata = rest.get("metadata") or {}
    for key in ("labels", "annotations"):
        metadata.pop(key, None)
    spec = rest.get("spec") or {}
    for _, key in POD_FIELDS:
        spec.pop(key, None)
    spec["containers"] = {
        container["name"]: {
            key: value for key, value in container.items() if key not in {"name", "image", *CONTAINER_FIELDS}
        }
        for container in spec.pop("containers", [])
    }
    return rest


def _equal(left, right):
    return "equal" if left == right else "differs"


def template_parity(canary, live, *, canary_name, live_name, canary_config_map=None, live_config_map=None):
    """Redacted per-field-class comparison of the canary and live Pod templates.

    Images are excluded everywhere: the canary is supposed to run the candidate.
    The canary's release name and isolated ConfigMap name are mapped to the live
    names first; any other difference, including a field no class names, reads
    `differs`. Only `equal`/`differs` is recorded, never a field value.
    """
    names = {canary_name: live_name}
    if canary_config_map and live_config_map:
        names[canary_config_map] = live_config_map
    canary_template, live_template = _rename(pod_template(canary), names), pod_template(live)
    canary_containers, live_containers = _containers(canary_template), _containers(live_template)
    classes = {"container_names": _equal(sorted(canary_containers), sorted(live_containers))}
    for field in CONTAINER_FIELDS:
        classes[f"container_{field}"] = _equal(
            {name: item.get(field) for name, item in sorted(canary_containers.items())},
            {name: item.get(field) for name, item in sorted(live_containers.items())},
        )
    canary_metadata, live_metadata = _pod_metadata(canary_template), _pod_metadata(live_template)
    classes["pod_labels"] = _equal(canary_metadata["labels"], live_metadata["labels"])
    classes["pod_annotations"] = _equal(canary_metadata["annotations"], live_metadata["annotations"])
    for label, key in POD_FIELDS:
        canary_value, live_value = canary_template["spec"].get(key), live_template["spec"].get(key)
        if key == "initContainers":
            canary_value, live_value = _strip_images(canary_value), _strip_images(live_value)
        classes[label] = _equal(canary_value, live_value)
    classes["dependency_references"] = _equal(
        sorted(config_references(canary_template["spec"])), sorted(config_references(live_template["spec"]))
    )
    classes["other_template_fields"] = _equal(_remainder(canary_template), _remainder(live_template))
    return {
        "live_deployment": live_name,
        "canary_deployment": canary_name,
        "excluded": list(PARITY_EXCLUDED),
        "normalized": list(PARITY_NORMALIZED),
        "classes": classes,
    }


def kubectl_json(args, *, stdin=None):
    result = subprocess.run(
        ["kubectl", *args], input=stdin, capture_output=True, text=True, check=False, timeout=120
    )
    require(result.returncode == 0, "canary_admission_probe_failed")
    return json.loads(result.stdout)


def record(
    namespace,
    name,
    candidate,
    baseline,
    run_id,
    source_sha,
    live_name,
    *,
    workflow_sha,
    canary_config_map=None,
    live_config_map=None,
):
    require(NAME.fullmatch(namespace) and NAME.fullmatch(name) and NAME.fullmatch(live_name), "invalid_canary_name")
    require(
        all(NAME.fullmatch(value) for value in (canary_config_map, live_config_map) if value is not None),
        "invalid_canary_name",
    )
    require(
        type(run_id) is int
        and run_id > 0
        and SHA.fullmatch(source_sha) is not None
        and SHA.fullmatch(workflow_sha or "") is not None,
        "invalid_canary_identity",
    )
    canary = kubectl_json(["get", "deployment", name, "--namespace", namespace, "-o", "json"])
    live = kubectl_json(["get", "deployment", live_name, "--namespace", namespace, "-o", "json"])
    patch = guarded_patch(canary, name, candidate, baseline)
    admitted = kubectl_json(
        [
            "patch",
            "deployment",
            name,
            "--namespace",
            namespace,
            "--type=json",
            "--patch-file=/dev/stdin",
            "--dry-run=server",
            "-o",
            "json",
        ],
        stdin=json.dumps(patch),
    )
    uid, revision = version(canary)
    require(
        admitted["metadata"]["uid"] == uid and comparable(admitted) == with_image(canary, name, baseline),
        "canary_inverse_changed_more_than_image",
    )
    return {
        "schema": 1,
        "status": "PASS",
        "mode": "canary_only",
        "run_id": run_id,
        "workflow_sha": workflow_sha,
        "source_sha": source_sha,
        "candidate_image": candidate,
        "baseline_image": baseline,
        "dry_run": "server",
        "deployment": {
            "namespace": namespace,
            "name": name,
            "uid": uid,
            "resourceVersion": revision,
            "generation": canary["metadata"].get("generation"),
            "image": candidate,
        },
        "preconditions": {
            "uid": uid,
            "resourceVersion": revision,
            "container": "pusher",
            "image": candidate,
        },
        "admitted_image": baseline,
        # The live object the parity was measured against. Promote re-reads it and
        # refuses unless this exact template is still the one it would patch.
        "live_deployment": {"name": live_name, "uid": version(live)[0], "template_sha256": template_sha256(live)},
        "template_parity": template_parity(
            canary,
            live,
            canary_name=name,
            live_name=live_name,
            canary_config_map=canary_config_map,
            live_config_map=live_config_map,
        ),
    }


def parse_args(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--namespace", required=True)
    parser.add_argument("--name", required=True, help="isolated canary Deployment name")
    parser.add_argument("--candidate-image", required=True)
    parser.add_argument("--baseline-deployment", required=True, help="Deployment whose current image is the restore target")
    parser.add_argument("--canary-config-map", help="the canary's isolated runtime ConfigMap name")
    parser.add_argument("--live-config-map", help="the live runtime ConfigMap name it stands in for")
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--workflow-sha", required=True, help="GITHUB_WORKFLOW_SHA of the producing run")
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    result = {"schema": 1, "status": "REFUSED"}
    try:
        require(IMAGE.fullmatch(args.candidate_image), "unpinned_canary_image")
        baseline_deployment = kubectl_json(
            ["get", "deployment", args.baseline_deployment, "--namespace", args.namespace, "-o", "json"]
        )
        baseline = image_of(baseline_deployment, args.baseline_deployment)
        require(IMAGE.fullmatch(baseline) and baseline != args.candidate_image, "baseline_image_unpinned_or_equal")
        result = record(
            args.namespace,
            args.name,
            args.candidate_image,
            baseline,
            args.run_id,
            args.source_sha,
            args.baseline_deployment,
            workflow_sha=args.workflow_sha,
            canary_config_map=args.canary_config_map,
            live_config_map=args.live_config_map,
        )
    except Refused as error:
        result["reason"] = str(error)
    except (OSError, ValueError, KeyError, TypeError, IndexError, subprocess.TimeoutExpired):
        result["reason"] = "canary_inverse_unavailable"
    write_json(args.output, result)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
