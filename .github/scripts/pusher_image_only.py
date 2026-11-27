#!/usr/bin/env python3
"""Execute the protected Pusher image-only transition through live admission.

Production is the only admission surface. SCA-3161 closed the isolated rehearsal
route (GKE Warden's webhooks live in the managed control plane), so every probe
here is a `kubectl --dry-run=server` call against the live namespace. The single
live write is unchanged: the guarded JSON Patch of the Pusher container image.

Evidence is a non-secret dispatch input (`PUSHER_IMAGE_ONLY_EVIDENCE`). Nothing
in it is trusted: every referenced run is fetched from the GitHub API and its
receipt is read from that run's artifact. The dispatching run id is bound from
`GITHUB_RUN_ID`, never from the packet.
"""

from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from pusher_image_rehearsal import (
    IMAGE,
    NAMESPACE,
    PROOF_ID,
    REPO,
    ROOT,
    SHA,
    SHARED,
    TARGET,
    Cluster,
    Refused,
    check_provenance,
    comparable,
    config_references,
    read_admission,
    read_json,
    require,
    run,
    version,
)

sys.path.insert(0, str(ROOT / "backend/scripts"))
from pusher_release_receipt import ReceiptError, validate_live_identity
from verify_pusher_live_deployment_gate import GateError, capacity_evidence
from verify_pusher_promotion_evidence import _validate_canary, canonical_sha256

BASELINE = "gcr.io/based-hardware/pusher@sha256:f26e8757759fe6907a9ef0e4c31d0a08a8ed527d777db5f472b33bffcff6d925"
REQUIRED_FIXES = (
    "8609f6c25c6c4d6586dbc87c17e75e59a66b8f1f",  # #25779
    "b3e8f449964e0afd801305d5199fe7b9d9e784a2",  # #26249
)
ROLLOUT_TIMEOUT = 9600
RECEIPT_ARTIFACT = "pusher-image-only-receipt"
CANARY_ARTIFACT = "pusher-prod-canary-evidence"
PROMOTION_WORKFLOW = "gcp_backend_pusher.yml"
QUALIFICATION_WORKFLOW = "gcp_backend_pusher_auto_deploy.yml"
PACKET_FIELDS = frozenset(
    {
        "schema",
        "mode",
        "source_sha",
        "prior_image",
        "candidate_image",
        "qualification_run_id",
        "release_approval",
    }
)
MODES = {"preview", "canary", "promote", "rollback"}
# Condition 1: a refused post-move inverse is a HOLD, never an auto-reverse loop.
# The same admission chain would most likely refuse the reverse patch as well, so
# the operator restores the prior object under Release custody instead.
MANUAL_RESTORE_PATH = (
    "Release prod-operator: restore the prior Pusher ReplicaSet or Deployment template in "
    f"{NAMESPACE} (kubectl rollout undo deployment/{TARGET} or an equivalent template restore), "
    "verify the pinned baseline digest is serving, then dispatch a fresh approved operation."
)
# Same gate and arguments as the ordinary Pusher deploy success path (.github/AGENTS.md).
STATUS_REPORT = (
    sys.executable,
    "backend/scripts/deploy_status_report.py",
    "--env",
    "prod",
    "--include-gke",
    "--gke-service",
    "pusher",
)
STATUS_REPORT_TIMEOUT = 300


class Hold(Exception):
    """The live write happened and the inverse was refused; no further patch is safe."""


def pusher_container(obj, name):
    require(
        obj["apiVersion"] == "apps/v1"
        and obj["kind"] == "Deployment"
        and obj["metadata"]["namespace"] == NAMESPACE
        and obj["metadata"]["name"] == name
        and not obj["metadata"].get("deletionTimestamp"),
        "wrong_target",
    )
    containers = obj["spec"]["template"]["spec"]["containers"]
    matches = [index for index, container in enumerate(containers) if container["name"] == "pusher"]
    require(len(matches) == 1, "pusher_container_ambiguous")
    return matches[0]


def image_of(obj, name):
    return obj["spec"]["template"]["spec"]["containers"][pusher_container(obj, name)]["image"]


def with_image(obj, name, image):
    expected = copy.deepcopy(comparable(obj))
    expected["spec"]["template"]["spec"]["containers"][pusher_container(obj, name)]["image"] = image
    return expected


def guarded_image_patch(obj, name, expected, desired, *, allow_same=False):
    """The one patch shape. Preconditions are unchanged: UID, resourceVersion, container, old image."""
    require(
        IMAGE.fullmatch(expected) and IMAGE.fullmatch(desired) and (allow_same or expected != desired),
        "unpinned_image",
    )
    require(image_of(obj, name) == expected, "unexpected_current_image")
    uid, revision = version(obj)
    path = f"/spec/template/spec/containers/{pusher_container(obj, name)}"
    return [
        {"op": "test", "path": "/metadata/uid", "value": uid},
        {"op": "test", "path": "/metadata/resourceVersion", "value": revision},
        {"op": "test", "path": f"{path}/name", "value": "pusher"},
        {"op": "test", "path": f"{path}/image", "value": expected},
        {"op": "replace", "path": f"{path}/image", "value": desired},
    ]


def submit_image_patch(cluster, obj, name, expected, desired, *, dry_run, allow_same=False):
    patch = guarded_image_patch(obj, name, expected, desired, allow_same=allow_same)
    mode = "--dry-run=server" if dry_run else "--dry-run=none"
    admitted = cluster.call(
        "patch",
        "deployment.apps",
        name,
        "--namespace",
        NAMESPACE,
        "--type=json",
        "--patch-file=/dev/stdin",
        mode,
        "-o",
        "json",
        reason="server_dry_run_rejected" if dry_run else "live_patch_unconfirmed_reconcile_before_retry",
        stdin=json.dumps(patch),
    )
    require(
        admitted["metadata"]["uid"] == version(obj)[0] and comparable(admitted) == with_image(obj, name, desired),
        "admission_changed_more_than_image",
    )
    return admitted


class ReadOnlyCluster:
    """Live production reads plus server-side admission dry-runs.

    There is deliberately no member that can issue a persistent patch: every
    probe passes `--dry-run=server` in code, and `call` refuses anything but
    reads. The preview and canary paths hold only this type.
    """

    def __init__(self, cluster):
        self._cluster = cluster

    def get(self, *args, **kwargs):
        return self._cluster.get(*args, **kwargs)

    def call(self, *args, **kwargs):
        require(bool(args) and args[0] in {"get", "api-resources", "version", "auth", "config"}, "preview_write_refused")
        return self._cluster.call(*args, **kwargs)

    def deployment(self, name=TARGET):
        return self.get("deployment.apps", name, namespace=NAMESPACE)

    def secret_version(self, *args, **kwargs):
        return self._cluster.secret_version(*args, **kwargs)

    def identity(self):
        return self._cluster.identity()

    def server(self):
        return self._cluster.server()

    def api_version(self):
        return self._cluster.api_version()

    def admission_resources(self):
        return self._cluster.admission_resources()

    def probe(self, obj, name, expected, desired, *, allow_same=False):
        return submit_image_patch(self._cluster, obj, name, expected, desired, dry_run=True, allow_same=allow_same)


class LiveWriter(ReadOnlyCluster):
    """The single guarded live patch. Only the promote and rollback paths hold it."""

    def patch_image(self, obj, name, expected, desired):
        return submit_image_patch(self._cluster, obj, name, expected, desired, dry_run=False)


def dependency_versions(live, deployment):
    """Identity of every referenced ConfigMap/Secret, read without their content."""
    references = list(config_references(deployment["spec"]["template"]["spec"]))
    require(SHARED in {reference for reference, _ in references}, "dependency_inventory_mismatch")
    inventory = []
    for (kind, name), optional in sorted(references):
        if kind == "secret":
            observed = live.secret_version(name, namespace=NAMESPACE, optional=True)
        else:
            observed = version(live.get(kind, name, namespace=NAMESPACE, optional=True))
        require(optional or observed is not None, "required_dependency_absent")
        inventory.append({"resource": kind, "name": name, "version": observed})
    return inventory


def state(live):
    """The live custody snapshot the preview is reviewed against."""
    deployment = live.deployment()
    identity = live.identity()
    require(
        isinstance(identity, dict) and isinstance(identity.get("username"), str) and identity["username"],
        "effective_identity_missing",
    )
    admission, _ = read_admission(live, [])
    namespace = live.get("namespace", NAMESPACE)
    return {
        "deployment": version(deployment),
        "generation": deployment["metadata"]["generation"],
        "deployment_sha256": canonical_sha256(comparable(deployment)),
        "namespace_uid": version(namespace)[0],
        "image": image_of(deployment, TARGET),
        "effective_user": identity["username"],
        "server_url": live.server(),
        "admission_sha256": canonical_sha256(admission),
        "dependencies": dependency_versions(live, deployment),
    }


def require_unchanged(live, before, expected_image):
    after = state(live)
    require(after == before and after["image"] == expected_image, "state_changed_while_verifying")
    return after


def summary(snapshot):
    return {
        "live_baseline": snapshot["deployment"],
        "effective_user": snapshot["effective_user"],
        "server_url": snapshot["server_url"],
        "namespace_uid": snapshot["namespace_uid"],
        "admission_sha256": snapshot["admission_sha256"],
        "dependencies_sha256": canonical_sha256(snapshot["dependencies"]),
    }


def evidence_binding(packet):
    """Receipt fields that tie every run to the exact candidate and source."""
    return {
        "proof_id": packet["release_approval"],
        "proof_sha256": canonical_sha256(
            {key: packet[key] for key in ("source_sha", "prior_image", "candidate_image", "qualification_run_id")}
        ),
        "prior_image": packet["prior_image"],
        "candidate_image": packet["candidate_image"],
        "source_sha": packet["source_sha"],
        "qualification_run_id": packet["qualification_run_id"],
    }


def validate_packet(packet, mode, workflow_sha, run_id):
    """Condition 4: the packet carries ids only, and its shape is exact for the mode."""
    required = PACKET_FIELDS | ({"reviewed_preview"} if mode in {"canary", "promote"} else set())
    required |= {"canary"} if mode in {"canary", "promote"} else set()
    require(
        isinstance(packet, dict)
        and packet.get("schema") == 2
        and packet.get("mode") == mode
        and mode in MODES
        and set(packet) == required
        and "run_id" not in packet
        and SHA.fullmatch(packet.get("source_sha") or "")
        and packet["source_sha"] != "0" * 40
        and packet["prior_image"] == BASELINE
        and IMAGE.fullmatch(packet.get("candidate_image") or "")
        and packet["candidate_image"].split("@")[1] != BASELINE.split("@")[1]
        and type(packet.get("qualification_run_id")) is int
        and packet["qualification_run_id"] > 0
        and PROOF_ID.fullmatch(packet.get("release_approval") or ""),
        "protected_evidence_mismatch",
    )
    if mode in {"canary", "promote"}:
        review = packet["reviewed_preview"]
        require(
            isinstance(review, dict)
            and set(review) == {"run_id", "review_id"}
            and type(review["run_id"]) is int
            and review["run_id"] > 0
            and review["run_id"] != run_id
            and PROOF_ID.fullmatch(review["review_id"]),
            "reviewed_forward_preview_missing",
        )
        canary = packet["canary"]
        require(
            isinstance(canary, dict)
            and set(canary) == {"run_id", "workflow_sha", "preservation_review"}
            and type(canary["run_id"]) is int
            and canary["run_id"] > 0
            and canary["run_id"] != run_id
            and SHA.fullmatch(canary["workflow_sha"]),
            "canary_evidence_missing",
        )
    dispatch = workflow_run_metadata(run_id, PROMOTION_WORKFLOW, expected_sha=workflow_sha, require_success=False)
    require(dispatch["status"] == "in_progress", "protected_run_unqualified")


def workflow_run_metadata(run_id, workflow_file, *, expected_sha, require_success=True):
    """Fetch one referenced run and prove it is this repo, this workflow and this source."""
    require(type(run_id) is int and run_id > 0, "invalid_evidence_run_id")
    repo = f"repos/{REPO}"
    workflow_id = int(
        run(
            ["gh", "api", f"{repo}/actions/workflows/{workflow_file}", "--jq", ".id"],
            "evidence_workflow_unavailable",
        )
    )
    metadata = json.loads(run(["gh", "api", f"{repo}/actions/runs/{run_id}"], "evidence_run_unavailable"))
    require(
        metadata["id"] == run_id
        and metadata["workflow_id"] == workflow_id
        and metadata["event"] == "workflow_dispatch"
        and metadata["head_branch"] == "main"
        and metadata["head_sha"] == expected_sha
        and metadata["run_attempt"] == 1
        and metadata["head_repository"]["full_name"] == REPO,
        "evidence_run_unqualified",
    )
    if require_success:
        require(metadata["status"] == "completed" and metadata["conclusion"] == "success", "evidence_run_not_successful")
    return metadata


def download_receipt(run_id):
    require(type(run_id) is int and run_id > 0, "invalid_receipt_run_id")
    with tempfile.TemporaryDirectory(prefix="pusher-image-only-receipt-") as tmp:
        run(
            ["gh", "run", "download", str(run_id), "--repo", REPO, "-n", RECEIPT_ARTIFACT, "--dir", tmp],
            "protected_run_receipt_unavailable",
        )
        receipt = read_json(Path(tmp) / "receipt.json")
    require(receipt["status"] == "PASS" and receipt["run_id"] == run_id, "protected_run_receipt_refused")
    return receipt


def download_canary(run_id):
    """Fetch the canonical canary evidence and its inverse receipt from the named run."""
    require(type(run_id) is int and run_id > 0, "invalid_canary_run")
    names = {
        "evidence": "pusher-prod-canary-evidence.json",
        "deployment_receipt": "pusher-prod-canary-deployment-receipt.json",
        "semantic_receipt": "pusher-prod-canary-semantic-probe.json",
        "inverse_receipt": "pusher-prod-canary-inverse-receipt.json",
    }
    with tempfile.TemporaryDirectory(prefix="pusher-canary-evidence-") as tmp:
        run(
            ["gh", "run", "download", str(run_id), "--repo", REPO, "-n", CANARY_ARTIFACT, "--dir", tmp],
            "canary_artifact_unavailable",
        )
        return {key: read_json(Path(tmp) / name) for key, name in names.items()}


def check_qualification(packet):
    """Condition 4: the qualification run is fetched, then its artifact is re-verified."""
    workflow_run_metadata(packet["qualification_run_id"], QUALIFICATION_WORKFLOW, expected_sha=packet["source_sha"])
    return check_provenance({key: packet[key] for key in ("prior_image", "candidate_image", "source_sha", "qualification_run_id")})


def check_reviewed_preview(packet, result):
    review = packet["reviewed_preview"]
    workflow_run_metadata(review["run_id"], PROMOTION_WORKFLOW, expected_sha=result["workflow_sha"])
    preview = download_receipt(review["run_id"])
    require(
        preview["mode"] == "preview"
        and preview["stage"] == "complete"
        and preview["status"] == "PASS"
        and preview["run_id"] == review["run_id"]
        and preview["forward_server_dry_run"] == "PASS"
        and preview["live_baseline_server_dry_run"] == "PASS"
        and preview["release_approval"] == packet["release_approval"]
        and all(
            preview[key] == result[key] for key in ("workflow_sha", "proof_sha256", "candidate_image", "source_sha")
        ),
        "reviewed_forward_preview_missing",
    )
    return preview


def check_canary(packet, result, qualification_receipt):
    """Condition 4: fetch the canary run, then bind its evidence and inverse receipt."""
    canary = packet["canary"]
    run_id = canary["run_id"]
    workflow_sha = canary["workflow_sha"]
    metadata = workflow_run_metadata(run_id, PROMOTION_WORKFLOW, expected_sha=workflow_sha)
    artifacts = download_canary(run_id)
    deployment = artifacts["deployment_receipt"]
    require(
        deployment["image"]
        == {"repository": packet["candidate_image"].split("@")[0], "digest": packet["candidate_image"].split("@")[1]},
        "wrong_canary_image",
    )
    require(deployment["source_sha"] == packet["source_sha"], "canary_source_sha_mismatch")
    require(
        not _validate_canary(
            artifacts["evidence"],
            artifacts["semantic_receipt"],
            metadata,
            deployment,
            source_sha=packet["source_sha"],
            digest=packet["candidate_image"].split("@")[1],
            qualification_deployment_receipt_sha256=canonical_sha256(qualification_receipt),
            expected_canary_workflow_id=metadata["workflow_id"],
            expected_canary_run_id=run_id,
            expected_canary_workflow_sha=workflow_sha,
        ),
        "canonical_canary_refused",
    )
    check_canary_inverse(artifacts["inverse_receipt"], packet, deployment)
    evidence_hash = canonical_sha256(artifacts["evidence"])
    review = canary["preservation_review"]
    require(
        isinstance(review, dict)
        and set(review) == {"id", "proof_sha256", "evidence_sha256", "baseline"}
        and PROOF_ID.fullmatch(review["id"])
        and review["proof_sha256"] == result["proof_sha256"]
        and review["evidence_sha256"] == evidence_hash
        and review["baseline"] == packet["prior_image"],
        "preserved_canary_review_missing",
    )
    result.update(
        canary_run_id=run_id,
        canary_evidence_sha256=evidence_hash,
        canary_inverse_receipt="PASS",
        reviewed_preview=dict(packet["reviewed_preview"]),
    )


def check_canary_inverse(inverse, packet, deployment):
    """Condition 2: the candidate→baseline dry-run ran on the isolated canary object."""
    live_identity = deployment["live_identity"]
    require(
        isinstance(inverse, dict)
        and inverse.get("schema") == 1
        and inverse.get("status") == "PASS"
        and inverse.get("run_id") == packet["canary"]["run_id"]
        and inverse.get("source_sha") == packet["source_sha"]
        and inverse.get("candidate_image") == packet["candidate_image"]
        and inverse.get("baseline_image") == packet["prior_image"]
        and inverse.get("dry_run") == "server"
        and inverse.get("deployment", {}).get("namespace") == NAMESPACE
        and inverse.get("deployment", {}).get("name") == canary_target(packet["canary"]["run_id"])
        and inverse.get("deployment", {}).get("image") == packet["candidate_image"]
        and inverse.get("deployment", {}).get("uid") == live_identity.get("deployment_uid")
        and inverse.get("preconditions")
        == {
            "uid": inverse["deployment"]["uid"],
            "resourceVersion": inverse["deployment"]["resourceVersion"],
            "container": "pusher",
            "image": packet["candidate_image"],
        }
        and inverse.get("admitted_image") == packet["prior_image"],
        "canary_inverse_receipt_refused",
    )


def canary_target(run_id):
    return f"prod-omi-pusher-canary-{run_id}"


def verify_canary_cleanup(cluster, run_id):
    names = (canary_target(run_id), f"prod-omi-listener-canary-{run_id}")
    for kind in ("deployment.apps", "service"):
        for name in names:
            require(cluster.get(kind, name, namespace=NAMESPACE, optional=True) is None, "canary_cleanup_incomplete")
    for pod in cluster.get("pods", namespace=NAMESPACE)["items"]:
        require(not pod["metadata"]["name"].startswith(names), "canary_pods_still_present")


def check_capacity(cluster, current, admitted):
    autoscaler = cluster.get("configmap", "cluster-autoscaler-status", namespace="kube-system", optional=True)
    failures, _ = capacity_evidence(
        admitted,
        current,
        cluster.get("nodes")["items"],
        cluster.call("get", "pods", "--all-namespaces", "-o", "json")["items"],
        (autoscaler or {}).get("data", {}).get("status"),
    )
    require(not failures, "live_preserved_template_has_insufficient_capacity")


def deploy_status_report(*, strict):
    """Run the shared deploy-status report; strict on success paths, diagnostic after a failure."""
    try:
        completed = subprocess.run(
            STATUS_REPORT,
            cwd=ROOT,
            stdin=subprocess.DEVNULL,
            # The receipt is the only stdout payload; the report goes to the job log.
            stdout=sys.stderr,
            stderr=sys.stderr,
            check=False,
            timeout=STATUS_REPORT_TIMEOUT,
        )
    except (OSError, subprocess.TimeoutExpired):
        if strict:
            raise
        return
    require(not strict or completed.returncode == 0, "deploy_status_report_failed")


def verify_ready(cluster, deployment, image, *, name=TARGET):
    """Judge readiness on the ReplicaSet the Deployment controller treats as new.

    Pods of earlier ReplicaSets that are already terminating are ordinary draining
    after `kubectl rollout status` succeeds; they are not counted. Active pods of an
    earlier ReplicaSet, or any new pod that is not Running, still refuse.
    """
    deployment_uid = version(deployment)[0]
    owned = [
        rs
        for rs in cluster.get("replicasets.apps", namespace=NAMESPACE)["items"]
        if owned_by(rs, "Deployment", {deployment_uid})
    ]
    # Same selection as the Deployment controller: template equality ignoring the hash label.
    template = pod_template(deployment)
    current = [rs for rs in owned if pod_template(rs) == template]
    require(len(current) == 1, "pusher_new_replicaset_unresolved")
    new_uid = version(current[0])[0]
    old_uids = {version(rs)[0] for rs in owned} - {new_uid}
    pods = cluster.get("pods", namespace=NAMESPACE)["items"]
    new_pods = [pod for pod in pods if owned_by(pod, "ReplicaSet", {new_uid})]
    old_active = [
        pod for pod in pods if owned_by(pod, "ReplicaSet", old_uids) and not pod["metadata"].get("deletionTimestamp")
    ]
    replicas = deployment["spec"]["replicas"]
    require(
        deployment["status"]["updatedReplicas"] == replicas == len(new_pods)
        and not old_active
        and all(
            not pod["metadata"].get("deletionTimestamp") and pod["status"]["phase"] == "Running" for pod in new_pods
        ),
        "pusher_replica_replacement_incomplete",
    )
    repository, digest = image.split("@")
    return validate_live_identity(
        deployment,
        {"items": new_pods},
        namespace=NAMESPACE,
        repository=repository,
        digest=digest,
        expected_deployment_name=name,
    )


def owned_by(obj, kind, uids):
    return any(
        owner.get("controller") is True and owner["kind"] == kind and owner["uid"] in uids
        for owner in obj["metadata"].get("ownerReferences", [])
    )


def pod_template(obj):
    template = copy.deepcopy(obj["spec"]["template"])
    template.get("metadata", {}).get("labels", {}).pop("pod-template-hash", None)
    return template


def verify_serving(live, before, changed, image, result):
    """Wait for the rollout and prove the new ReplicaSet is the serving one."""
    try:
        run(
            [
                *live._cluster.command,
                "rollout",
                "status",
                f"deployment/{TARGET}",
                "-n",
                NAMESPACE,
                f"--timeout={ROLLOUT_TIMEOUT}s",
            ],
            "rollout_unconfirmed",
            timeout=ROLLOUT_TIMEOUT + 30,
        )
    except (Refused, subprocess.TimeoutExpired):
        deploy_status_report(strict=False)
        raise
    deployed = live.deployment()
    require(
        deployed["metadata"]["generation"] == changed["metadata"]["generation"] and image_of(deployed, TARGET) == image,
        "deployment_generation_changed_after_patch",
    )
    identity = verify_ready(live, deployed, image)
    after = state(live)
    require(
        after["namespace_uid"] == before["namespace_uid"]
        and after["dependencies"] == before["dependencies"]
        and after["effective_user"] == before["effective_user"],
        "custody_changed_during_rollout",
    )
    result["stage"] = "deploy_status_report"
    deploy_status_report(strict=True)
    return identity


def execute(mode, packet, live, result, *, writer=None):
    """Run one operation. `live` is read-only; only promote and rollback receive a writer."""
    require((writer is not None) == (mode in {"promote", "rollback"}), "invalid_execution_binding")
    candidate = packet["candidate_image"]
    if mode == "rollback":
        return rollback(packet, live, writer, result)

    result["stage"] = "verify_qualified_candidate"
    for fix in REQUIRED_FIXES:
        run(["git", "merge-base", "--is-ancestor", fix, packet["source_sha"]], "required_gcs_fix_missing")
    qualification_receipt = check_qualification(packet)
    if mode in {"canary", "promote"}:
        result["stage"] = "verify_canary_evidence"
        check_canary(packet, result, qualification_receipt)

    result["stage"] = "observe_baseline"
    before = state(live)
    require(before["image"] == BASELINE, "observed_image_changed")
    result.update(summary(before))
    if mode == "promote":
        preview = check_reviewed_preview(packet, result)
        require(before["deployment"] == preview["live_baseline"], "reviewed_baseline_changed")

    baseline = live.deployment()
    result["stage"] = "server_dry_run_forward"
    admitted = live.probe(baseline, TARGET, BASELINE, candidate)
    result["forward_server_dry_run"] = "PASS"
    result["stage"] = "server_dry_run_baseline_self"
    # Primary rollback evidence: the baseline object, re-submitted against today's
    # admission. Warden evaluates the object, so the oldObject difference between
    # this dry-run and a real restore does not change the verdict.
    live.probe(baseline, TARGET, BASELINE, BASELINE, allow_same=True)
    result["live_baseline_server_dry_run"] = "PASS"
    result["rollback_evidence"] = "baseline_self_server_dry_run"
    require_unchanged(live, before, BASELINE)
    if mode in {"preview", "canary"}:
        return

    verify_canary_cleanup(live, result["canary_run_id"])
    result["stage"] = "check_live_surge_capacity"
    check_capacity(live, baseline, admitted)
    require_unchanged(live, before, BASELINE)

    result["stage"] = "live_patch_attempted"
    changed = writer.patch_image(baseline, TARGET, BASELINE, candidate)
    # Retain exact change evidence even if a later gate fails. Do not retry an uncertain write.
    result.update(patch_observed=version(changed), requested_image=candidate)

    result["stage"] = "server_dry_run_post_move_inverse"
    after = live.deployment()
    require(image_of(after, TARGET) == candidate, "live_candidate_not_persisted")
    try:
        live.probe(after, TARGET, candidate, BASELINE)
    except Refused as error:
        # Condition 1: hold. An immediate reverse patch is the same transition and
        # would most likely be refused too, so traffic stays as it is and Release
        # performs the manual restore under custody.
        result.update(
            stage="hold_refused_inverse",
            reason="REFUSED_INVERSE",
            inverse_refusal=str(error),
            manual_restore_path=MANUAL_RESTORE_PATH,
            serving_image_observed=image_of(live.deployment(), TARGET),
        )
        deploy_status_report(strict=False)
        raise Hold("REFUSED_INVERSE") from None
    result["live_inverse_server_dry_run"] = "PASS"

    result["stage"] = "verify_serving"
    identity = verify_serving(live, before, changed, candidate, result)
    result.update(
        deploy_status_report="PASS",
        serving_image=candidate,
        serving_deployment_uid=identity["deployment_uid"],
        serving_generation=identity["generation"],
        ready_replicas=identity["ready_replicas"],
    )


def rollback(packet, live, writer, result):
    result["stage"] = "verify_baseline_registry"
    digest = run(
        ["gcloud", "container", "images", "describe", BASELINE, "--format=value(image_summary.digest)"],
        "baseline_registry_unavailable",
    ).strip()
    require(digest == BASELINE.split("@")[1], "baseline_registry_mismatch")
    result["stage"] = "observe_candidate"
    before = state(live)
    require(before["image"] == packet["candidate_image"], "observed_image_changed")
    result.update(summary(before))
    result["stage"] = "server_dry_run_inverse"
    live.probe(live.deployment(), TARGET, packet["candidate_image"], BASELINE)
    result["live_inverse_server_dry_run"] = "PASS"
    require_unchanged(live, before, packet["candidate_image"])
    result["stage"] = "live_patch_attempted"
    changed = writer.patch_image(live.deployment(), TARGET, packet["candidate_image"], BASELINE)
    result.update(patch_observed=version(changed), requested_image=BASELINE)
    result["stage"] = "verify_serving"
    identity = verify_serving(live, before, changed, BASELINE, result)
    result.update(
        deploy_status_report="PASS",
        serving_image=BASELINE,
        serving_deployment_uid=identity["deployment_uid"],
        serving_generation=identity["generation"],
        ready_replicas=identity["ready_replicas"],
    )


def main():
    result = {"schema": 2, "status": "REFUSED", "stage": "read_protected_evidence"}
    try:
        mode = os.environ["IMAGE_ONLY_MODE"]
        workflow_sha = os.environ["GITHUB_WORKFLOW_SHA"]
        run_id = int(os.environ["GITHUB_RUN_ID"])
        packet = json.loads(os.environ["PUSHER_IMAGE_ONLY_EVIDENCE"])
        result.update(mode=mode, workflow_sha=workflow_sha, run_id=run_id)
        validate_packet(packet, mode, workflow_sha, run_id)
        require(
            packet["source_sha"] == os.environ["SOURCE_SHA"]
            and packet["candidate_image"].split("@")[1] == os.environ["REQUESTED_DIGEST"]
            and packet["qualification_run_id"] == int(os.environ["QUALIFICATION_RUN_ID"]),
            "dispatch_evidence_mismatch",
        )
        result.update(evidence_binding(packet))
        with tempfile.TemporaryDirectory(prefix="pusher-image-only-") as _tmp:
            raw = Cluster(Path(os.environ["KUBECONFIG"]), os.environ["LIVE_CONTEXT"], isolated=False)
            live = ReadOnlyCluster(raw)
            writer = LiveWriter(raw) if mode in {"promote", "rollback"} else None
            execute(mode, packet, live, result, writer=writer)
        result.update(status="PASS", stage="complete")
    except Hold as error:
        result.update(status="HOLD", reason=str(error))
    except Refused as error:
        result["reason"] = str(error)
    except (ReceiptError, GateError):
        result["reason"] = "canary_readiness_or_capacity_unproven"
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        AttributeError,
        IndexError,
        subprocess.TimeoutExpired,
    ):
        result["reason"] = "missing_invalid_or_unavailable_evidence"
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
