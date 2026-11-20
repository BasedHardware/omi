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
RESOURCES = "deployments,statefulsets,daemonsets,jobs,cronjobs,horizontalpodautoscalers"
IMAGE = re.compile(re.escape(REPOSITORY) + r"@sha256:[a-f0-9]{64}\Z")


# Set only by the workflow's dry-run step. While set to any value, every non-read API call that is
# not a server dry-run is refused before it reaches kubectl, and the deploy command refuses outright.
# The dry-run command itself requires the exact value "1".
DRY_RUN_ENV = "WORKER_IMAGE_ONLY_DRY_RUN"


def dry_run_mode():
    return DRY_RUN_ENV in os.environ


def require_dry_run_env():
    require(os.environ.get(DRY_RUN_ENV) == "1", f"dry-run command requires {DRY_RUN_ENV}=1")


def require_dry_run_allows(args):
    if dry_run_mode():
        read = bool(args) and args[0] == "get"
        # Exactly one dry-run option, and it is server: a later or conflicting flag could override it.
        dry = [a for a in args if a == "--dry-run" or str(a).startswith("--dry-run=")]
        preview = bool(args) and args[0] == "patch" and dry == ["--dry-run=server"]
        require(read or preview, "write refused in dry-run mode")


def guarded(run):
    def call(*args):
        require_dry_run_allows(args)
        return run(*args)

    return call


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


# HorizontalPodAutoscalers own .spec.replicas on exactly these Deployments (chart-defined), so
# identity hashes exclude that one field for them only, and only while the same read proves a live
# HPA (minReplicas >= 1) targets each of them; the HPA objects are bound by UID and spec hash.
# Every other workload, including the operator-scaled T4 fallback, keeps its replica count bound;
# image, UID and any other spec change still refuses.
HPA_DEPLOYMENTS = frozenset({TARGET, "record-seal-worker"})
# Fields the Job controller and API defaulting add to a CronJob-created Job, with their defaults.
JOB_DEFAULTED = {
    "completionMode": "NonIndexed",
    "completions": 1,
    "parallelism": 1,
    "suspend": False,
    "manualSelector": False,
    "podReplacementPolicy": "TerminatingOrFailed",
}
JOB_GENERATED_LABELS = frozenset(
    {"batch.kubernetes.io/controller-uid", "batch.kubernetes.io/job-name", "controller-uid", "job-name"}
)


def identity_spec(obj):
    spec = copy.deepcopy(obj["spec"])
    if obj["kind"] == "Deployment" and obj["metadata"].get("name") in HPA_DEPLOYMENTS:
        spec.pop("replicas", None)
    return spec


def no_surge_strategy(strategy):
    """Recreate, or RollingUpdate with an explicit zero maxSurge: a roll never asks for a GPU beyond
    the replica count. Kubernetes defaults an omitted maxSurge to 25%, so absence refuses."""
    if strategy.get("type") == "Recreate":
        return "rollingUpdate" not in strategy
    if strategy.get("type") != "RollingUpdate":
        return False
    rolling = strategy.get("rollingUpdate") or {}
    return "maxSurge" in rolling and rolling["maxSurge"] in (0, "0", "0%")


def worker_images(spec):
    return {
        (field, c.get("name")): c.get("image", "")
        for field in ("containers", "initContainers")
        for c in spec.get(field, [])
        if c.get("image", "").startswith(REPOSITORY)
    }


def cronjob_history(obj, cronjobs):
    """A Job whose controller is a CronJob in the same read, running that CronJob's current worker
    images, is that CronJob's run history.

    The CronJob itself stays bound (its jobTemplate is hashed), so a template or image change
    still refuses. Jobs with no controller, a controller absent from the read, or worker images
    that differ from the owner's jobTemplate stay bound.
    """
    if obj["kind"] != "Job":
        return False
    owners = [r for r in obj["metadata"].get("ownerReferences", []) if r.get("controller")]
    if len(owners) != 1 or owners[0].get("kind") != "CronJob" or not owners[0].get("uid"):
        return False
    owner = cronjobs.get(owners[0].get("uid"))
    if owner is None or not re.fullmatch(re.escape(owner["metadata"]["name"]) + r"-\d+", obj["metadata"]["name"]):
        return False
    # The whole run must be the owner's current template: pod spec, template annotations, and every
    # Job field either equal to the jobTemplate or a controller default. Anything else stays bound.
    spec, template = obj["spec"], owner["spec"]["jobTemplate"]["spec"]
    for key, value in spec.items():
        if key in ("template", "selector"):
            continue
        if key in template:
            if value != template[key]:
                return False
        elif JOB_DEFAULTED.get(key, object()) != value:
            return False
    if any(key not in spec for key in template if key not in ("template", "selector")):
        return False
    run_meta, owner_meta = spec["template"].get("metadata", {}), template["template"].get("metadata", {})
    run_labels, owner_labels = run_meta.get("labels", {}), owner_meta.get("labels", {})
    # The selector and generated labels must be exactly what the Job controller writes for this Job.
    uid, name = obj["metadata"].get("uid"), obj["metadata"]["name"]
    generated = {
        "batch.kubernetes.io/controller-uid": uid,
        "controller-uid": uid,
        "batch.kubernetes.io/job-name": name,
        "job-name": name,
    }
    if not uid or spec.get("selector") != {"matchLabels": {"batch.kubernetes.io/controller-uid": uid}}:
        return False
    if any(run_labels.get(k) != v for k, v in generated.items()):
        return False
    return (
        spec["template"]["spec"] == template["template"]["spec"]
        and run_meta.get("annotations") == owner_meta.get("annotations")
        and {k: v for k, v in run_labels.items() if k not in JOB_GENERATED_LABELS} == owner_labels
    )


def kubectl(*args):
    # The only process boundary in this helper; the dry-run restriction is enforced here as well as in
    # guarded(), so no caller can reach the API with a write while the mode env is set.
    require_dry_run_allows(args)
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
    require(no_surge_strategy(obj["spec"].get("strategy", {})), "worker must roll without surge GPUs")
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
    return {"uid": meta["uid"], "image": image, "spec_sha256": digest(identity_spec(obj))}, index


def autoscalers(items):
    """Bind the HPA that owns each HPA_DEPLOYMENTS replica count; refuse if any is unproven."""
    bindings = []
    for name in sorted(HPA_DEPLOYMENTS):
        owners = [
            o for o in items
            if o["kind"] == "HorizontalPodAutoscaler"
            and o["spec"].get("scaleTargetRef", {}).get("kind") == "Deployment"
            and o["spec"]["scaleTargetRef"].get("apiVersion") == "apps/v1"
            and o["spec"]["scaleTargetRef"].get("name") == name
        ]
        require(len(owners) == 1, f"replica exclusion needs exactly one HPA for {name}")
        hpa = owners[0]
        require(
            hpa["metadata"].get("uid")
            and not hpa["metadata"].get("deletionTimestamp")
            and hpa["spec"].get("minReplicas", 1) >= 1,
            f"HPA for {name} is unproven",
        )
        bindings.append(
            {
                "kind": "HorizontalPodAutoscaler",
                "name": hpa["metadata"]["name"],
                "uid": hpa["metadata"]["uid"],
                "field": "scaleTargetRef",
                "container": name,
                "image": "",
                "spec_sha256": digest(hpa["spec"]),
            }
        )
    return bindings


def bindings(items):
    """Everything a release must hold constant: owning HPAs plus shared worker-image consumers."""
    return sorted(autoscalers(items) + consumers(items), key=lambda b: (b["kind"], b["name"], b["field"], b["container"]))


def consumers(items):
    bindings = []
    cronjobs = {o["metadata"]["uid"]: o for o in items if o["kind"] == "CronJob" and o["metadata"].get("uid")}
    for obj in items:
        meta = obj["metadata"]
        require(meta.get("namespace") == NAMESPACE, "consumer outside target namespace")
        if obj["kind"] == "HorizontalPodAutoscaler":
            continue
        if obj["kind"] == "Deployment" and meta["name"] == TARGET:
            continue
        for field in ("containers", "initContainers"):
            for container in pod_spec(obj).get(field, []):
                image = container.get("image", "")
                if image.startswith(REPOSITORY + "@") or image.startswith(REPOSITORY + ":") or image == REPOSITORY:
                    require(IMAGE.fullmatch(image), "shared consumer has a mutable/invalid image")
                    if cronjob_history(obj, cronjobs):
                        continue
                    bindings.append(
                        {
                            "kind": obj["kind"],
                            "name": meta["name"],
                            "uid": meta["uid"],
                            "field": field,
                            "container": container["name"],
                            "image": image,
                            "spec_sha256": digest(identity_spec(obj)),
                        }
                    )
    return sorted(bindings, key=lambda b: (b["kind"], b["name"], b["field"], b["container"]))


def snapshot(run=kubectl):
    obj = run("get", "deployment", TARGET, "-o", "json")
    state, _ = target_state(obj)
    shared = bindings(run("get", RESOURCES, "-o", "json")["items"])
    return obj, {"target": state, "consumers": shared}


def patch_for(obj, image, allow_same=False):
    state, index = target_state(obj)
    require(IMAGE.fullmatch(image), "candidate must be an immutable worker digest")
    require(allow_same or image != state["image"], "candidate already serving; refuse an unneeded roll")
    path = f"/spec/template/spec/containers/{index}/image"
    return [
        {"op": "test", "path": "/metadata/uid", "value": state["uid"]},
        {"op": "test", "path": "/metadata/resourceVersion", "value": obj["metadata"]["resourceVersion"]},
        {"op": "test", "path": path, "value": state["image"]},
        {"op": "replace", "path": path, "value": image},
    ]


def require_t4_serves(workloads, image):
    # Replica counts are excluded from identity hashes, so an activated T4 fallback is checked
    # directly wherever the worker image is asserted (before the write and after the roll).
    for sibling in workloads:
        if sibling["kind"] == "Deployment" and sibling["metadata"]["name"] == TARGET + "-t4":
            if sibling["spec"].get("replicas", 1) > 0:
                spec = pod_spec(sibling)
                require(
                    all(c["image"] == image for c in spec["containers"] if c["name"] == "worker")
                    and any(c["name"] == "worker" for c in spec["containers"])
                    and all(img == image for img in worker_images(spec).values()),
                    "active T4 fallback must already serve the candidate",
                )


def private_json(path, data):
    # Receipts contain image identities and hashes only, never runtime environment values.
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as handle:
        json.dump(data, handle, indent=2)
        handle.write("\n")


def require_companion_serves(obj, actual, image):
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


def preflight(baseline, image, run, rollback_receipt=None, allow_same=False):
    """Every gate the writer applies before its first API write; shared by deploy and dry-run."""
    if rollback_receipt is not None:
        require(
            baseline == {"target": rollback_receipt["after"], "consumers": rollback_receipt["consumers"]},
            "rollback baseline must match the saved release receipt",
        )
        require(image == rollback_receipt["before"]["image"], "rollback must restore the recorded prior image")
    obj, actual = snapshot(run)
    require(actual == baseline, "target or shared-consumer drift from admitted baseline")
    patch_for(obj, image, allow_same=allow_same)
    require_companion_serves(obj, actual, image)
    require_t4_serves(run("get", RESOURCES, "-o", "json")["items"], image)
    expected = copy.deepcopy(obj)
    _, index = target_state(obj)
    expected["spec"]["template"]["spec"]["containers"][index]["image"] = image
    after, _ = target_state(expected)
    if rollback_receipt is not None:
        require(after == rollback_receipt["before"], "rollback must restore the exact recorded prior runtime spec")
    return obj, actual, index, after, expected


def deploy(baseline, image, receipt_path, run=kubectl, rollback_receipt=None):
    require(not dry_run_mode(), "deploy refused in dry-run mode")
    run = guarded(run)
    obj, actual, index, after, expected = preflight(baseline, image, run, rollback_receipt)
    receipt = {"before": actual["target"], "after": after, "consumers": actual["consumers"]}
    private_json(receipt_path, receipt)
    # An HPA rescale since the first read bumps resourceVersion; rebuild the CAS patch from a fresh
    # read whose identity (UID, image, spec without replicas) must still equal the admitted one.
    # A rescale after this read still fails the resourceVersion test (API conflict) and refuses.
    fresh = run("get", "deployment", TARGET, "-o", "json")
    require(target_state(fresh)[0] == actual["target"], "target drift immediately before write")
    patch = patch_for(fresh, image)
    expected = copy.deepcopy(fresh)
    expected["spec"]["template"]["spec"]["containers"][index]["image"] = image
    # The CAS patch applies to the exact object just read, so admission must leave the whole spec,
    # replicas included, as expected; only cross-read identity checks tolerate autoscaling.
    exact = digest(expected["spec"])
    # Safe, reviewable image diff (the patch actually sent) and exact reverse identity.
    print(json.dumps({"deployment": TARGET, "namespace": NAMESPACE, "patch": patch, "rollback": receipt}), flush=True)
    preview = run("patch", "deployment", TARGET, "--type=json", "-p", json.dumps(patch), "--dry-run=server", "-o", "json")
    require(
        target_state(preview)[0] == after and digest(preview["spec"]) == exact,
        "admission dry-run changed runtime configuration",
    )
    # Re-read siblings immediately before the CAS write. They are never mutated here.
    final = run("get", RESOURCES, "-o", "json")["items"]
    require(bindings(final) == baseline["consumers"], "consumer drift")
    require_t4_serves(final, image)
    result = run("patch", "deployment", TARGET, "--type=json", "-p", json.dumps(patch), "-o", "json")
    require(
        target_state(result)[0] == after and digest(result["spec"]) == exact,
        "admission changed runtime configuration; stop and escalate",
    )
    return receipt


def server_preview(run, obj, image, allow_same=False):
    """Server dry-run of the image patch against obj; returns (expected identity, patch, admitted object)."""
    _, index = target_state(obj)
    patch = patch_for(obj, image, allow_same=allow_same)
    expected = copy.deepcopy(obj)
    expected["spec"]["template"]["spec"]["containers"][index]["image"] = image
    after, _ = target_state(expected)
    preview = run("patch", "deployment", TARGET, "--type=json", "-p", json.dumps(patch), "--dry-run=server", "-o", "json")
    require(
        target_state(preview)[0] == after and digest(preview["spec"]) == digest(expected["spec"]),
        "admission dry-run changed runtime configuration",
    )
    return after, patch, preview


def dry_run(baseline, image, receipt_path, run=kubectl, rollback_receipt=None):
    """Run every writer gate and the server admission dry-run, without any write.

    Without a rollback receipt (before a forward roll):
      * forward: if ``image`` differs from live, the writer's preflight and a server dry-run of the
        forward patch; the inverse patch built from that would-be post-roll object must restore the
        live identity exactly (offline, the server cannot stage two steps);
      * prior-image admission: a server dry-run of the live (prior) image against fresh live state.
        This is a no-op patch: it proves admission of the prior spec and the UID/resourceVersion
        tests, not the rollback CAS, which needs the forward state to exist.
    With a rollback receipt (after a forward roll): the rollback writer's exact preflight and a
    server dry-run of the real inverse patch (image test on the forward digest) against live state.
    """
    require_dry_run_env()
    run = guarded(run)
    _, live = snapshot(run)
    live_image = live["target"]["image"]
    same = image == live_image and rollback_receipt is None
    obj, actual, index, after, expected = preflight(baseline, image, run, rollback_receipt, allow_same=same)
    fresh = run("get", "deployment", TARGET, "-o", "json")
    require(target_state(fresh)[0] == actual["target"], "target drift immediately before dry-run")
    result = {"mode": "dry-run", "baseline": actual, "forward": None, "prior_image_admission": None, "inverse": None,
              "inverse_admission": "not verified before the forward roll; rehearse with worker_rollback_receipt"}
    if rollback_receipt is not None:
        identity, patch, _ = server_preview(run, fresh, image)
        require(identity == rollback_receipt["before"], "inverse dry-run does not restore the recorded prior identity")
        result["inverse"] = {"admitted": True, "image": image, "patch": patch, "restores": identity,
                             "cas": "real rollback patch against the post-forward live state"}
        result["inverse_admission"] = "verified: server dry-run of the real rollback CAS patch"
    else:
        if not same:
            identity, patch, admitted = server_preview(run, fresh, image)
            require(identity == after, "forward preview identity differs from the writer's expected identity")
            # The same receipt deploy() would write: both identities from preflight's single read.
            receipt = {"before": actual["target"], "after": after, "consumers": actual["consumers"]}
            # The inverse the rollback writer would send is built from the server's admitted post-roll
            # object (not a local copy), and applying it to that object must restore `before` exactly.
            post_roll = copy.deepcopy(admitted)
            reverse = patch_for(post_roll, live_image)
            require(reverse[0]["value"] == actual["target"]["uid"] and reverse[2]["value"] == image
                    and reverse[3]["value"] == live_image, "inverse patch shape")
            post_roll["spec"]["template"]["spec"]["containers"][target_state(post_roll)[1]]["image"] = live_image
            restored = target_state(post_roll)[0]
            inverse_restores_before = restored == receipt["before"]
            require(inverse_restores_before, "inverse of the forward patch does not restore the live identity")
            # The rollback writer's sibling gates run against the prior image; siblings never move, so
            # a gate that the forward passes only on the candidate (active T4, companion) blocks the inverse.
            workloads = run("get", RESOURCES, "-o", "json")["items"]
            try:
                require_companion_serves(obj, actual, live_image)
                require_t4_serves(workloads, live_image)
            except ValueError as exc:
                raise ValueError(f"inverse would refuse after the forward roll: {exc}") from None
            result["forward"] = {"admitted": True, "after": identity, "patch": patch, "would_write_receipt": receipt,
                                 "inverse_patch": reverse, "inverse_restores_before": inverse_restores_before,
                                 "inverse_patch_note": "identity and shape check only, not replayable: the rollback "
                                                       "writer rebuilds the CAS patch from the post-forward live object"}
        identity, patch, _ = server_preview(run, fresh, live_image, allow_same=True)
        require(identity == actual["target"], "prior-image admission changed the live identity")
        result["prior_image_admission"] = {"admitted": True, "image": live_image, "patch": patch, "noop": True}
    final = run("get", RESOURCES, "-o", "json")["items"]
    require(bindings(final) == baseline["consumers"], "consumer drift")
    require_t4_serves(final, image)
    private_json(receipt_path, result)
    print(json.dumps(result), flush=True)
    return result


def verify(receipt, run=kubectl):
    run = guarded(run)
    _, actual = snapshot(run)
    require(actual == {"target": receipt["after"], "consumers": receipt["consumers"]}, "post-roll runtime/consumer drift")
    require_t4_serves(run("get", RESOURCES, "-o", "json")["items"], receipt["after"]["image"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["inventory", "deploy", "dry-run", "verify"])
    parser.add_argument("--baseline")
    parser.add_argument("--image")
    parser.add_argument("--receipt")
    parser.add_argument("--rollback-receipt")
    args = parser.parse_args()
    if args.command == "inventory":
        print(json.dumps(snapshot()[1], indent=2))
    elif args.command == "dry-run":
        require(args.baseline and args.image and args.receipt, "dry-run needs baseline, image and receipt")
        rollback = json.loads(Path(args.rollback_receipt).read_text()) if args.rollback_receipt else None
        if args.rollback_receipt:
            require(isinstance(rollback, dict), "rollback receipt must be an object")
        dry_run(json.loads(Path(args.baseline).read_text()), args.image, args.receipt, rollback_receipt=rollback)
    elif args.command == "deploy":
        require(not dry_run_mode(), "deploy refused in dry-run mode")
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
