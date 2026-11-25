#!/usr/bin/env python3
"""Change the production batch worker's literal depth under the GKE workflow lock."""

from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from worker_image_only import NAMESPACE, REPOSITORY, TARGET, kubectl, pod_spec, require, target_state

DEPTH = "BATCH_PIPELINE_WORKER_PIPELINE_DEPTH"
SIBLINGS = (
    ("Deployment", f"{TARGET}-t4"),
    ("Deployment", "record-seal-worker"),
    ("CronJob", "record-seal-repair"),
    ("CronJob", "record-seal-sweeper"),
)
ROLLOUT_TIMEOUT = 3000


def validate_inputs(current, target, digest, uid, version):
    require(current in ("3", "4") and target in ("3", "4"), "depths must be 3 or 4")
    require(current != target, "target depth must differ from expected current depth")
    require(re.fullmatch(r"sha256:[a-f0-9]{64}", digest), "expected digest must be an immutable SHA-256 digest")
    require(re.fullmatch(r"[a-f0-9]{8}(-[a-f0-9]{4}){3}-[a-f0-9]{12}", uid), "invalid expected Deployment UID")
    require(re.fullmatch(r"[1-9][0-9]*", version), "invalid expected Deployment resourceVersion")


def depth_entry(obj):
    state, index = target_state(obj)
    strategy = obj["spec"]["strategy"]
    rolling = strategy.get("rollingUpdate", {})
    surge = rolling.get("maxSurge")
    require(
        strategy["type"] == "RollingUpdate"
        and (type(surge) is int and surge == 0 or surge in ("0", "0%"))
        and rolling.get("maxUnavailable") == "50%",
        "expected RollingUpdate with maxSurge 0 and maxUnavailable 50%",
    )
    entries = pod_spec(obj)["containers"][index].get("env", [])
    matches = [i for i, entry in enumerate(entries) if entry.get("name") == DEPTH]
    require(len(matches) == 1, "expected exactly one worker depth entry")
    env_index = matches[0]
    entry = entries[env_index]
    require(
        entry.keys() == {"name", "value"} and entry["value"] in ("3", "4"),
        "worker depth must be a literal 3 or 4",
    )
    return state, index, env_index, entry


def get_primary(run):
    return run("get", "deployment", TARGET, "-o", "json")


def sibling_specs(run):
    resources = [f"{kind.lower()}/{name}" for kind, name in SIBLINGS]
    snapshot = {}
    for obj in run("get", *resources, "-o", "json")["items"]:
        meta = obj["metadata"]
        key = (obj["kind"], meta["name"])
        require(
            key in SIBLINGS
            and key not in snapshot
            and meta["namespace"] == NAMESPACE
            and meta.get("uid")
            and not meta.get("deletionTimestamp"),
            "unexpected or unstable sibling identity",
        )
        template = obj["spec"]["template"] if obj["kind"] == "Deployment" else obj["spec"]["jobTemplate"]
        require(bool(template["spec"]), "missing sibling template")
        snapshot[key] = (meta["uid"], template)
    require(snapshot.keys() == set(SIBLINGS), "missing sibling Deployment or CronJob")
    return snapshot


def admitted(obj, expected, uid, message, *, after_rollout=False):
    state, _, _, _ = depth_entry(obj)
    actual = obj["spec"]
    if after_rollout:
        # HPA owns replicas. Admission checks below still bind the exact count.
        actual = {key: value for key, value in actual.items() if key != "replicas"}
        expected = {key: value for key, value in expected.items() if key != "replicas"}
    require(state["uid"] == uid and actual == expected, message)


def patch_primary(run, patch, *, preview):
    flags = ("--dry-run=server",) if preview else ()
    return run("patch", "deployment", TARGET, "--type=json", "-p", json.dumps(patch), *flags, "-o", "json")


def rollout_status():
    result = subprocess.run(
        ["kubectl", "-n", NAMESPACE, "rollout", "status", f"deployment/{TARGET}", f"--timeout={ROLLOUT_TIMEOUT}s"],
        capture_output=True,
        timeout=ROLLOUT_TIMEOUT + 30,
    )
    require(result.returncode == 0, "worker rollout wait failed; inspect production state before retrying")


def execute(operation, current, target, digest, uid, version, emit, *, run=kubectl, wait=rollout_status):
    require(operation in ("plan", "apply"), "expected plan or apply")
    validate_inputs(current, target, digest, uid, version)
    image = f"{REPOSITORY}@{digest}"
    live = get_primary(run)
    state, index, env_index, entry = depth_entry(live)
    require(state["uid"] == uid, "Deployment UID changed")
    require(live["metadata"]["resourceVersion"] == version, "Deployment resourceVersion changed")
    require(state["image"] == image, "worker image does not match expected digest")
    require(entry["value"] == current, "worker depth does not match expected current depth")
    siblings = sibling_specs(run)

    worker_path = f"/spec/template/spec/containers/{index}"
    entry_path = f"{worker_path}/env/{env_index}"
    value_path = f"{entry_path}/value"
    tests = [
        {"op": "test", "path": "/metadata/uid", "value": uid},
        {"op": "test", "path": "/metadata/resourceVersion", "value": version},
        {"op": "test", "path": f"{worker_path}/name", "value": "worker"},
        {"op": "test", "path": f"{worker_path}/image", "value": image},
        {"op": "test", "path": entry_path, "value": entry},
    ]
    forward = tests + [{"op": "replace", "path": value_path, "value": target}]
    inverse = [
        {"op": "test", "path": value_path, "value": target},
        {"op": "replace", "path": value_path, "value": current},
    ]
    expected = copy.deepcopy(live)
    pod_spec(expected)["containers"][index]["env"][env_index]["value"] = target
    preview = patch_primary(run, forward, preview=True)
    admitted(preview, expected["spec"], uid, "forward server dry-run differs beyond the admitted depth change")
    require(sibling_specs(run) == siblings, "sibling template drift during forward rehearsal")
    # A dry-run does not persist the forward object. Exercise the reverse operations
    # after the forward operations in one request and check the admitted, restored spec.
    restored = patch_primary(run, forward + inverse, preview=True)
    admitted(restored, live["spec"], uid, "inverse server dry-run did not restore the admitted live spec")
    require(sibling_specs(run) == siblings, "sibling template drift during inverse rehearsal")
    fresh = get_primary(run)
    require(fresh["metadata"]["resourceVersion"] == version, "Deployment changed during rehearsal")
    admitted(fresh, live["spec"], uid, "Deployment drift during rehearsal")
    emit(
        {
            "phase": "pre-write server dry-runs",
            "operation": operation,
            "deployment": f"{NAMESPACE}/{TARGET}",
            "uid": uid,
            "resourceVersion": version,
            "image": image,
            "readyReplicasBefore": live.get("status", {}).get("readyReplicas", 0),
            "forward": {"before": current, "after": target, "only_spec_change": DEPTH},
            "inverse": {"before": target, "after": current, "composed_server_dry_run": True},
            "strategy": {"type": "RollingUpdate", "maxSurge": 0, "maxUnavailable": "50%"},
            "preserved_sibling_templates": [f"{kind}/{name}" for kind, name in SIBLINGS],
        }
    )
    if operation == "plan":
        return

    # Never rebase the CAS on a later resourceVersion or retry a failed write.
    try:
        result = patch_primary(run, forward, preview=False)
        admitted(result, expected["spec"], uid, "write admission differed from rehearsal; inspect live state")
    finally:
        # An API or response error can leave a write in flight. Keep the lock
        # through the bounded wait even if the patch result could not be verified.
        wait()
    readback = get_primary(run)
    admitted(readback, expected["spec"], uid, "post-rollout Deployment drift", after_rollout=True)
    require(sibling_specs(run) == siblings, "post-rollout sibling template drift")
    ready = readback.get("status", {}).get("readyReplicas", 0)
    emit({"phase": "rollout readback", "uid": uid, "image": image, "depth": target, "readyReplicas": ready})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("plan", "apply"))
    for option in ("current", "target", "digest", "uid", "version", "source"):
        parser.add_argument(f"--{option}", required=True)
    args = parser.parse_args()

    def emit(receipt):
        receipt["reviewedSource"] = args.source
        receipt["workflowSHA"] = os.environ["GITHUB_WORKFLOW_SHA"]
        with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf-8") as summary:
            summary.write(f"### Worker depth-only receipt\n\n```json\n{json.dumps(receipt, indent=2)}\n```\n\n")

    try:
        require(os.environ.get("GITHUB_ACTIONS") == "true", "worker depth mode requires GitHub Actions")
        require(os.environ.get("GITHUB_REF") == "refs/heads/main", "worker depth mode requires main")
        require(re.fullmatch(r"[a-f0-9]{40}", args.source), "invalid reviewed source")
        execute(args.operation, args.current, args.target, args.digest, args.uid, args.version, emit)
    except (KeyError, TypeError, AttributeError, json.JSONDecodeError, OSError, subprocess.TimeoutExpired):
        print("Worker depth operation failed while processing Kubernetes state or the receipt", file=sys.stderr)
        return 1
    except ValueError as error:
        print(f"Worker depth operation refused: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
