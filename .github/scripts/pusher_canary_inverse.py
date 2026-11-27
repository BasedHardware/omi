#!/usr/bin/env python3
"""Record the smallest-radius candidate→baseline admission proof.

The canonical canary is a separate Deployment (`prod-omi-pusher-canary-<run>`)
created with the candidate image at one replica. Immediately after it is ready,
this records a `kubectl --dry-run=server` patch that would restore the image the
main Pusher was serving before the move. It is the only object that currently
holds the candidate, so the inverse is proven there before any promote.

The guarded patch is the same shape the live image-only write uses: UID,
resourceVersion, container name and old digest preconditions, then one replace.
"""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import re
import subprocess
import sys

from pusher_image_rehearsal import Refused, require, version

IMAGE = re.compile(r"gcr\.io/based-hardware/(?:backend-)?pusher@sha256:[a-f0-9]{64}")
NAME = re.compile(r"[a-z0-9][a-z0-9.-]{0,252}")
STORAGE_METADATA = {"uid", "resourceVersion", "generation", "creationTimestamp", "managedFields"}


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


def kubectl_json(args, *, stdin=None):
    result = subprocess.run(
        ["kubectl", *args], input=stdin, capture_output=True, text=True, check=False, timeout=120
    )
    require(result.returncode == 0, "canary_admission_probe_failed")
    return json.loads(result.stdout)


def record(namespace, name, candidate, baseline, run_id, source_sha):
    require(NAME.fullmatch(namespace) and NAME.fullmatch(name), "invalid_canary_name")
    require(type(run_id) is int and run_id > 0 and re.fullmatch(r"[a-f0-9]{40}", source_sha) is not None, "invalid_canary_identity")
    canary = kubectl_json(["get", "deployment", name, "--namespace", namespace, "-o", "json"])
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
        "run_id": run_id,
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
    }


def parse_args(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--namespace", required=True)
    parser.add_argument("--name", required=True, help="isolated canary Deployment name")
    parser.add_argument("--candidate-image", required=True)
    parser.add_argument("--baseline-deployment", required=True, help="Deployment whose current image is the restore target")
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument("--source-sha", required=True)
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
