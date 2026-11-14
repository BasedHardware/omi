#!/usr/bin/env python3
"""Narrow image-only writer for the canonical GPU workflow. Never renders Helm values."""

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

NAMESPACE = "prod-omi-backend"
TARGET = "prod-omi-batch-pipeline-worker"
REPOSITORY = "gcr.io/based-hardware/batch-pipeline-worker"
RESOURCES = "deployments,statefulsets,daemonsets,jobs,cronjobs"
IMAGE = re.compile(re.escape(REPOSITORY) + r"@sha256:[a-f0-9]{64}\Z")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def kubectl(*args):
    result = subprocess.run(
        ["kubectl", "-n", NAMESPACE, *args, "--request-timeout=30s"],
        capture_output=True,
        text=True,
        timeout=45,
    )
    # Do not echo server responses, which may contain a private Deployment definition.
    require(result.returncode == 0, "kubectl failed; no automatic retry (refresh the release packet)")
    return json.loads(result.stdout)


def pod_spec(obj):
    spec = obj["spec"]
    if obj["kind"] == "CronJob":
        return spec["jobTemplate"]["spec"]["template"]["spec"]
    return spec["template"]["spec"]


def target_state(obj):
    require(obj.get("apiVersion") == "apps/v1" and obj.get("kind") == "Deployment", "wrong target kind")
    meta = obj["metadata"]
    require(meta.get("namespace") == NAMESPACE and meta.get("name") == TARGET, "wrong deployment target")
    require(meta.get("uid") and meta.get("resourceVersion") and not meta.get("deletionTimestamp"), "unstable target")
    require(obj["spec"].get("strategy", {}).get("type") == "Recreate", "worker must use Recreate")
    containers = pod_spec(obj)["containers"]
    matches = [i for i, c in enumerate(containers) if c.get("name") == "worker"]
    require(len(matches) == 1, "ambiguous worker container")
    index = matches[0]
    image = containers[index]["image"]
    require(IMAGE.fullmatch(image), "live worker image must be an immutable worker digest")
    require(
        sum(c.get("image", "").startswith(REPOSITORY) for c in containers + pod_spec(obj).get("initContainers", [])) == 1,
        "ambiguous worker image consumers in target",
    )
    return {"uid": meta["uid"], "image": image, "spec_sha256": digest(obj["spec"])}, index


def consumers(items):
    bindings = []
    for obj in items:
        meta = obj["metadata"]
        require(meta.get("namespace") == NAMESPACE, "consumer outside target namespace")
        if obj["kind"] == "Deployment" and meta["name"] == TARGET:
            continue
        for field in ("containers", "initContainers"):
            for container in pod_spec(obj).get(field, []):
                image = container.get("image", "")
                if image.startswith(REPOSITORY + "@") or image.startswith(REPOSITORY + ":") or image == REPOSITORY:
                    require(IMAGE.fullmatch(image), "shared consumer has a mutable/invalid image")
                    bindings.append(
                        {
                            "kind": obj["kind"],
                            "name": meta["name"],
                            "uid": meta["uid"],
                            "field": field,
                            "container": container["name"],
                            "image": image,
                            "spec_sha256": digest(obj["spec"]),
                        }
                    )
    return sorted(bindings, key=lambda b: (b["kind"], b["name"], b["field"], b["container"]))


def snapshot(run=kubectl):
    obj = run("get", "deployment", TARGET, "-o", "json")
    state, _ = target_state(obj)
    shared = consumers(run("get", RESOURCES, "-o", "json")["items"])
    return obj, {"target": state, "consumers": shared}


def patch_for(obj, image):
    state, index = target_state(obj)
    require(IMAGE.fullmatch(image), "candidate must be an immutable worker digest")
    require(image != state["image"], "candidate already serving; refuse an unneeded roll")
    path = f"/spec/template/spec/containers/{index}/image"
    return [
        {"op": "test", "path": "/metadata/uid", "value": state["uid"]},
        {"op": "test", "path": "/metadata/resourceVersion", "value": obj["metadata"]["resourceVersion"]},
        {"op": "test", "path": path, "value": state["image"]},
        {"op": "replace", "path": path, "value": image},
    ]


def private_json(path, data):
    # Receipts contain image identities and hashes only, never runtime environment values.
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as handle:
        json.dump(data, handle, indent=2)
        handle.write("\n")


def deploy(baseline, image, receipt_path, run=kubectl, rollback_receipt=None):
    if rollback_receipt is not None:
        require(
            baseline == {"target": rollback_receipt["after"], "consumers": rollback_receipt["consumers"]},
            "rollback baseline must match the saved release receipt",
        )
        require(image == rollback_receipt["before"]["image"], "rollback must restore the recorded prior image")
    obj, actual = snapshot(run)
    require(actual == baseline, "target or shared-consumer drift from admitted baseline")
    patch = patch_for(obj, image)
    # Keep existing rollout/report gates satisfiable without silently rolling siblings.
    companion = obj["metadata"].get("annotations", {}).get("omi.ai/required-companion-deployment")
    for binding in actual["consumers"]:
        if binding["kind"] == "Deployment" and binding["name"] == companion:
            require(binding["image"] == image, "required companion must already serve the candidate")
    if companion:
        require(
            any(b["kind"] == "Deployment" and b["name"] == companion for b in actual["consumers"]),
            "required companion missing from shared-image inventory",
        )
    workloads = run("get", RESOURCES, "-o", "json")["items"]
    for sibling in workloads:
        if sibling["kind"] == "Deployment" and sibling["metadata"]["name"] == TARGET + "-t4":
            if sibling["spec"].get("replicas", 1) > 0:
                require(
                    all(c["image"] == image for c in pod_spec(sibling)["containers"] if c["name"] == "worker")
                    and any(c["name"] == "worker" for c in pod_spec(sibling)["containers"]),
                    "active T4 fallback must already serve the candidate",
                )
    expected = copy.deepcopy(obj)
    _, index = target_state(obj)
    expected["spec"]["template"]["spec"]["containers"][index]["image"] = image
    after, _ = target_state(expected)
    if rollback_receipt is not None:
        require(after == rollback_receipt["before"], "rollback must restore the exact recorded prior runtime spec")
    receipt = {"before": actual["target"], "after": after, "consumers": actual["consumers"]}
    private_json(receipt_path, receipt)
    # Safe, reviewable image diff and exact reverse identity; never print the full spec.
    print(json.dumps({"deployment": TARGET, "namespace": NAMESPACE, "patch": patch, "rollback": receipt}), flush=True)
    preview = run("patch", "deployment", TARGET, "--type=json", "-p", json.dumps(patch), "--dry-run=server", "-o", "json")
    require(target_state(preview)[0] == after, "admission dry-run changed runtime configuration")
    # Re-read siblings immediately before the CAS write. They are never mutated here.
    require(consumers(run("get", RESOURCES, "-o", "json")["items"]) == baseline["consumers"], "consumer drift")
    result = run("patch", "deployment", TARGET, "--type=json", "-p", json.dumps(patch), "-o", "json")
    require(target_state(result)[0] == after, "admission changed runtime configuration; stop and escalate")
    return receipt


def verify(receipt, run=kubectl):
    _, actual = snapshot(run)
    require(actual == {"target": receipt["after"], "consumers": receipt["consumers"]}, "post-roll runtime/consumer drift")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["inventory", "deploy", "verify"])
    parser.add_argument("--baseline")
    parser.add_argument("--image")
    parser.add_argument("--receipt")
    parser.add_argument("--rollback-receipt")
    args = parser.parse_args()
    if args.command == "inventory":
        print(json.dumps(snapshot()[1], indent=2))
    elif args.command == "deploy":
        require(args.baseline and args.image and args.receipt, "deploy needs baseline, image and receipt")
        rollback = json.loads(Path(args.rollback_receipt).read_text()) if args.rollback_receipt else None
        if args.rollback_receipt:
            require(isinstance(rollback, dict), "rollback receipt must be an object")
        deploy(json.loads(Path(args.baseline).read_text()), args.image, args.receipt, rollback_receipt=rollback)
    else:
        require(args.receipt, "receipt required")
        receipt = json.loads(Path(args.receipt).read_text())
        verify(receipt)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, TypeError, OSError, subprocess.TimeoutExpired) as exc:
        # No private object dump in exception text.
        detail = str(exc) if type(exc) is ValueError else type(exc).__name__
        print(f"worker image-only operation refused: {detail}", file=sys.stderr)
        sys.exit(1)
