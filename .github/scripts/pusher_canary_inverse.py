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
so a candidate→baseline inverse is not applicable there. The workflow executes
this helper and its rehearsal dependency from the immutable workflow-control
revision (`INVERSE_HELPER_PATHS`), and source admission binds the same paths.

It also records the metadata-only identity (UID and resourceVersion, never data)
of every Secret and ConfigMap the canary will reference, including its isolated
runtime ConfigMap: first before the canary Deployment exists (`--snapshot`, so
before its first pod loads its environment), again when the inverse is recorded,
and again after the semantic probe (`--recheck`). Any change refuses.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from pusher_image_rehearsal import Cluster, Refused, config_references, require, version

# The helper and everything it imports; executed from the workflow-control revision.
INVERSE_HELPER_PATHS = (".github/scripts/pusher_canary_inverse.py", ".github/scripts/pusher_image_rehearsal.py")

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


def dependency_inventory(cluster, pod_spec, namespace):
    """Metadata-only identity of every referenced ConfigMap and Secret, deduplicated.

    Secrets are read through PartialObjectMetadata (`Cluster.secret_version`), so no
    Secret value is fetched. Only `[uid, resourceVersion]` or `None` is kept.
    """
    references = {}
    for reference, optional in config_references(pod_spec):
        references[reference] = references.get(reference, True) and optional
    inventory = []
    for (kind, name), optional in sorted(references.items()):
        if kind == "secret":
            observed = cluster.secret_version(name, namespace=namespace, optional=True)
        else:
            observed = version(cluster.get(kind, name, namespace=namespace, optional=True))
        require(optional or observed is not None, "required_dependency_absent")
        inventory.append({"resource": kind, "name": name, "version": observed})
    return inventory


def inventory_sha256(inventory, *, exclude=None):
    """Redacted digest of an inventory, without the runtime ConfigMap compared by content."""
    kept = [item for item in inventory if (item["resource"], item["name"]) != exclude]
    encoded = json.dumps(kept, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def inventory_names(inventory):
    return [[item["resource"], item["name"]] for item in inventory]


def prestart_snapshot(cluster, *, namespace, name, live_name, run_id, canary_config_map, live_config_map):
    """Before the canary exists: the full inventory it will reference, isolated ConfigMap included.

    The canary's Pod template is the live template with only the candidate image, the
    canary identity labels and the runtime ConfigMap name changed (SCA-4763), so its
    references are the live template's with the runtime ConfigMap renamed to the
    isolated one. The recorded inventory later has to match the canary's own references
    exactly.
    """
    require(
        all(NAME.fullmatch(value or "") for value in (namespace, name, live_name, canary_config_map, live_config_map)),
        "invalid_canary_name",
    )
    require(type(run_id) is int and run_id > 0, "invalid_canary_identity")
    require(cluster.get("deployment.apps", name, namespace=namespace, optional=True) is None, "canary_already_started")
    require(
        not any(pod["metadata"]["name"].startswith(f"{name}-") for pod in cluster.get("pods", namespace=namespace)["items"]),
        "canary_already_started",
    )
    live = cluster.get("deployment.apps", live_name, namespace=namespace)
    pod_spec = _rename(live["spec"]["template"]["spec"], {live_config_map: canary_config_map})
    inventory = dependency_inventory(cluster, pod_spec, namespace)
    require(["configmap", canary_config_map] in inventory_names(inventory), "runtime_config_map_unreferenced")
    return {
        "schema": 1,
        "status": "PASS",
        "run_id": run_id,
        "canary_deployment": name,
        "canary_absent": True,
        "names": inventory_names(inventory),
        "sha256": inventory_sha256(inventory),
    }


def dependency_record(inventory, prestart, canary_config_map):
    """Startup evidence: the canary's own references equal the pre-start snapshot, unchanged."""
    require(prestart.get("status") == "PASS" and prestart.get("canary_absent") is True, "canary_prestart_snapshot_missing")
    require(inventory_names(inventory) == prestart["names"], "canary_dependency_references_differ")
    require(inventory_sha256(inventory) == prestart["sha256"], "canary_dependencies_changed_during_startup")
    return {
        "names": inventory_names(inventory),
        "runtime_config_map": canary_config_map,
        "prestart_sha256": prestart["sha256"],
        "startup_sha256": inventory_sha256(inventory),
        "probe_sha256": None,
        # Compared with the live Pusher's inventory, whose runtime ConfigMap differs
        # by design and is compared by content hash instead.
        "shared_sha256": inventory_sha256(inventory, exclude=("configmap", canary_config_map)),
        "stable": False,
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
    cluster,
    prestart,
    canary_config_map,
    live_config_map=None,
):
    require(NAME.fullmatch(namespace) and NAME.fullmatch(name) and NAME.fullmatch(live_name), "invalid_canary_name")
    require(
        NAME.fullmatch(canary_config_map or "")
        and all(NAME.fullmatch(value) for value in (live_config_map,) if value is not None),
        "invalid_canary_name",
    )
    require(prestart.get("run_id") == run_id and prestart.get("canary_deployment") == name, "canary_prestart_snapshot_missing")
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
        "dependencies": dependency_record(
            dependency_inventory(cluster, canary["spec"]["template"]["spec"], namespace), prestart, canary_config_map
        ),
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


def recheck(receipt, cluster, *, namespace, name, run_id):
    """After the semantic probe: re-read the full inventory and require the pre-start versions."""
    require(
        receipt.get("status") == "PASS"
        and receipt.get("run_id") == run_id
        and receipt.get("deployment", {}).get("name") == name
        and receipt.get("deployment", {}).get("namespace") == namespace
        and isinstance(receipt.get("dependencies"), dict),
        "canary_inverse_receipt_missing",
    )
    canary = kubectl_json(["get", "deployment", name, "--namespace", namespace, "-o", "json"])
    require(version(canary)[0] == receipt["deployment"]["uid"], "canary_replaced_during_probe")
    inventory = dependency_inventory(cluster, canary["spec"]["template"]["spec"], namespace)
    dependencies = receipt["dependencies"]
    require(
        inventory_names(inventory) == dependencies["names"]
        and inventory_sha256(inventory) == dependencies["prestart_sha256"] == dependencies["startup_sha256"],
        "canary_dependencies_changed",
    )
    return receipt | {"dependencies": dependencies | {"probe_sha256": inventory_sha256(inventory), "stable": True}}


def live_cluster(context):
    kubeconfig = Path(os.environ.get("KUBECONFIG") or "~/.kube/config").expanduser()
    if not context:
        result = subprocess.run(
            ["kubectl", "config", "current-context"], capture_output=True, text=True, check=False, timeout=30
        )
        require(result.returncode == 0 and result.stdout.strip(), "kubernetes_context_unavailable")
        context = result.stdout.strip()
    return Cluster(kubeconfig, context, isolated=False)


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
    parser.add_argument("--context", help="kubeconfig context (default: the current context)")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--prestart", type=Path, help="pre-start dependency snapshot written by --snapshot")
    phase = parser.add_mutually_exclusive_group()
    phase.add_argument(
        "--snapshot",
        action="store_true",
        help="before the canary exists: write its full dependency inventory to --output",
    )
    phase.add_argument(
        "--recheck",
        action="store_true",
        help="re-read the dependency versions recorded in --output after the probe and require them unchanged",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    result = {"schema": 1, "status": "REFUSED"}
    try:
        cluster = live_cluster(args.context)
        if args.snapshot:
            result = prestart_snapshot(
                cluster,
                namespace=args.namespace,
                name=args.name,
                live_name=args.baseline_deployment,
                run_id=args.run_id,
                canary_config_map=args.canary_config_map,
                live_config_map=args.live_config_map,
            )
            write_json(args.output, result)
            print(json.dumps(result, sort_keys=True))
            return 0
        if args.recheck:
            previous = read_json(args.output)
            result = previous | {"status": "REFUSED"}
            result = recheck(
                previous,
                cluster,
                namespace=args.namespace,
                name=args.name,
                run_id=args.run_id,
            )
            write_json(args.output, result)
            print(json.dumps(result, sort_keys=True))
            return 0
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
            cluster=cluster,
            prestart=read_json(args.prestart) if args.prestart else {},
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
