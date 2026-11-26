#!/usr/bin/env python3
"""Execute the protected Pusher image-only transition using reviewed Release evidence."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml
from pusher_image_rehearsal import (
    NAMESPACE,
    PROOF_ID,
    REPO,
    ROOT,
    SHA,
    TARGET,
    Cluster,
    Refused,
    Rehearsal,
    check_provenance,
    proof_receipt_fields,
    read_json,
    require,
    run,
    version,
)

sys.path.insert(0, str(ROOT / "backend/scripts"))
from pusher_prod_canary import CanaryError, _selector_matches, _service_selectors
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


class ProtectedCluster(Cluster):
    # The rehearsal entry point retains its dry-run-only production guard.
    patch_failure_reason = "live_patch_unconfirmed_reconcile_before_retry"

    def apply_image(self, deployment, expected, desired):
        return self._submit_image_patch(deployment, expected, desired, dry_run=False)


def check_canary(packet, rehearsal, qualification_receipt, result):
    """Validate canonical evidence and its separate preservation review."""
    canary = packet["canary"]
    deployment = canary["deployment_receipt"]
    evidence = canary["evidence"]
    semantic = canary["semantic_receipt"]
    workflow_sha = canary["workflow_sha"]
    run_id = evidence["approval_run_id"]
    require(type(run_id) is int and run_id > 0 and SHA.fullmatch(workflow_sha), "invalid_canary_run")
    repository, digest = rehearsal.candidate.split("@")
    require(deployment["image"] == {"repository": repository, "digest": digest}, "wrong_canary_image")
    require(
        canary["preservation_review"]
        == {
            "id": canary["preservation_review"]["id"],
            "proof_sha256": proof_receipt_fields(rehearsal.proof)["proof_sha256"],
            "evidence_sha256": canonical_sha256(evidence),
            "baseline": rehearsal.proof["live_deployment"],
        }
        and PROOF_ID.fullmatch(canary["preservation_review"]["id"]),
        "preserved_canary_review_missing",
    )
    require(workflow_sha == result["workflow_sha"], "canary_workflow_sha_mismatch")
    metadata = protected_workflow_run(run_id, workflow_sha)
    require(
        not _validate_canary(
            evidence,
            semantic,
            metadata,
            deployment,
            source_sha=rehearsal.proof["source_sha"],
            digest=digest,
            qualification_deployment_receipt_sha256=canonical_sha256(qualification_receipt),
            expected_canary_workflow_id=metadata["workflow_id"],
            expected_canary_run_id=run_id,
            expected_canary_workflow_sha=workflow_sha,
        ),
        "canonical_canary_refused",
    )
    evidence_hash = canonical_sha256(evidence)
    if result["mode"] == "canary":
        require(run_id == result["run_id"] and metadata["status"] == "in_progress", "wrong_live_canary_run")
    else:
        require_completed_workflow_run(metadata)
        attestation = download_receipt(run_id)
        require(
            attestation["mode"] == "canary"
            and attestation["stage"] == "complete"
            and attestation["canary_evidence_sha256"] == evidence_hash
            and attestation["proof_sha256"] == result["proof_sha256"]
            and attestation["workflow_sha"] == result["workflow_sha"],
            "preserved_canary_attestation_mismatch",
        )
    result.update(canary_run_id=run_id, canary_evidence_sha256=evidence_hash)
    return deployment


def owned_by(obj, kind, uids):
    return any(
        owner.get("controller") is True and owner["kind"] == kind and owner["uid"] in uids
        for owner in obj["metadata"].get("ownerReferences", [])
    )


def verify_ready(cluster, deployment, image, *, name=TARGET):
    replicasets = cluster.get("replicasets.apps", namespace=NAMESPACE)["items"]
    deployment_uid = version(deployment)[0]
    replicasets = {version(rs)[0] for rs in replicasets if owned_by(rs, "Deployment", {deployment_uid})}
    pods = [
        pod for pod in cluster.get("pods", namespace=NAMESPACE)["items"] if owned_by(pod, "ReplicaSet", replicasets)
    ]
    replicas = deployment["spec"]["replicas"]
    require(
        deployment["status"]["updatedReplicas"] == replicas == len(pods)
        and all(not pod["metadata"].get("deletionTimestamp") and pod["status"]["phase"] == "Running" for pod in pods),
        "pusher_replica_replacement_incomplete",
    )
    repository, digest = image.split("@")
    return validate_live_identity(
        deployment,
        {"items": pods},
        namespace=NAMESPACE,
        repository=repository,
        digest=digest,
        expected_deployment_name=name,
    )


def canary_target(run_id):
    return f"prod-omi-pusher-canary-{run_id}"


def verify_canary_live(cluster, admitted, receipt):
    name = canary_target(receipt["run_id"])
    canary = cluster.get("deployment.apps", name, namespace=NAMESPACE)
    require(
        canary["spec"]["template"]["spec"] == admitted["spec"]["template"]["spec"],
        "canary_pod_spec_differs_from_preserved_candidate",
    )
    image = f'{receipt["image"]["repository"]}@{receipt["image"]["digest"]}'
    require(
        verify_ready(cluster, canary, image, name=name) == receipt["live_identity"],
        "canary_ready_pods_differ_from_probe_receipt",
    )
    pod_identity = receipt["live_identity"]["pods"][0]
    pod = cluster.get("pod", pod_identity["name"], namespace=NAMESPACE)
    selectors = _service_selectors(cluster.get("services", namespace=NAMESPACE), exclude_name=name)
    require(
        pod["metadata"]["uid"] == pod_identity["uid"]
        and all(not _selector_matches(pod["metadata"]["labels"], selector) for _, selector in selectors),
        "canary_pod_selected_by_ordinary_service",
    )


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


def protected_workflow_run(run_id, workflow_sha):
    require(type(run_id) is int and run_id > 0, "invalid_receipt_run_id")
    repo = f"repos/{REPO}"
    workflow_id = int(
        run(
            ["gh", "api", f"{repo}/actions/workflows/gcp_backend_pusher.yml", "--jq", ".id"],
            "protected_workflow_unavailable",
        )
    )
    metadata = json.loads(run(["gh", "api", f"{repo}/actions/runs/{run_id}"], "protected_run_unavailable"))
    require(
        metadata["id"] == run_id
        and metadata["workflow_id"] == workflow_id
        and metadata["event"] == "workflow_dispatch"
        and metadata["head_branch"] == "main"
        and metadata["head_sha"] == workflow_sha
        and metadata["run_attempt"] == 1
        and metadata["head_repository"]["full_name"] == REPO,
        "protected_receipt_run_unqualified",
    )
    return metadata


def require_completed_workflow_run(metadata):
    require(metadata["status"] == "completed" and metadata["conclusion"] == "success", "protected_run_not_successful")


def check_reviewed_preview(packet, result):
    review = packet["reviewed_preview"]
    require(PROOF_ID.fullmatch(review["review_id"]), "reviewed_forward_preview_missing")
    require_completed_workflow_run(protected_workflow_run(review["run_id"], result["workflow_sha"]))
    preview = download_receipt(review["run_id"])
    require(
        preview["mode"] == "preview"
        and preview["stage"] == "complete"
        and preview["forward_server_dry_run"] == "PASS"
        and all(
            preview[key] == result[key] for key in ("workflow_sha", "proof_sha256", "candidate_image", "live_baseline")
        ),
        "reviewed_forward_preview_missing",
    )


def execute(mode, packet, rehearsal, result):
    receipt = packet["rehearsal_receipt"]
    rehearsal.check_receipt(receipt, result)
    live = rehearsal.live
    if mode == "rollback":
        result["stage"] = "verify_baseline_registry"
        digest = run(
            ["gcloud", "container", "images", "describe", BASELINE, "--format=value(image_summary.digest)"],
            "baseline_registry_unavailable",
        ).strip()
        require(digest == BASELINE.split("@")[1], "baseline_registry_mismatch")
        current, isolated, policies = rehearsal.verify_inverse(receipt, result)
        result["live_inverse_server_dry_run"] = "PASS"
        old, new = rehearsal.candidate, BASELINE
    else:
        result["stage"] = "verify_qualified_candidate"
        source = rehearsal.proof["source_sha"]
        for fix in REQUIRED_FIXES:
            run(["git", "merge-base", "--is-ancestor", fix, source], "required_gcs_fix_missing")
        qualification_receipt = check_provenance(rehearsal.proof)
        if mode in {"canary", "promote"}:
            result["stage"] = "verify_canonical_canary"
            canary_receipt = check_canary(packet, rehearsal, qualification_receipt, result)
        result["stage"] = "server_dry_run_forward"
        old, new = BASELINE, rehearsal.candidate
        current, isolated, policies = rehearsal.observe(old, old)
        result["live_baseline"] = version(current)
        require(version(current) == receipt["live_baseline"], "reviewed_baseline_changed")
        rehearsal.check_rehearsed_state(receipt, isolated, policies)
        verify_ready(live, current, old)
        admitted = live.transition(current, old, new)
        result["forward_server_dry_run"] = "PASS"
        if mode == "canary":
            verify_canary_live(live, admitted, canary_receipt)
        rehearsal.recheck(current, isolated, policies)
        if mode in {"preview", "canary"}:
            return
        check_reviewed_preview(packet, result)
        require(PROOF_ID.fullmatch(packet["reviewed_inverse_rehearsal"]), "reviewed_inverse_rehearsal_missing")
        verify_canary_cleanup(live, result["canary_run_id"])
        result["stage"] = "check_live_surge_capacity"
        check_capacity(live, current, admitted)

    rehearsal.recheck(current, isolated, policies, post_move=mode == "rollback")
    result["stage"] = "live_patch_attempted"
    changed = live.apply_image(current, old, new)
    # Retain exact change evidence even if a later gate fails. Do not retry an uncertain write.
    result.update(patch_observed=version(changed), requested_image=new)
    if mode == "promote":
        rehearsal.verify_inverse(receipt, result)
        result["live_inverse_server_dry_run"] = "PASS"

    result["stage"] = "verify_serving"
    run(
        [*live.command, "rollout", "status", f"deployment/{TARGET}", "-n", NAMESPACE, f"--timeout={ROLLOUT_TIMEOUT}s"],
        "rollout_unconfirmed",
        timeout=ROLLOUT_TIMEOUT + 30,
    )
    deployed, restored, observed_policies = rehearsal.observe(new, BASELINE, post_move=True)
    rehearsal.check_rehearsed_state(receipt, restored, observed_policies)
    require(
        deployed["metadata"]["generation"] == changed["metadata"]["generation"],
        "deployment_generation_changed_after_patch",
    )
    identity = verify_ready(live, deployed, new)
    rehearsal.recheck(deployed, restored, observed_policies, post_move=True)
    result.update(
        serving_image=new,
        serving_deployment_uid=identity["deployment_uid"],
        serving_generation=identity["generation"],
        ready_replicas=identity["ready_replicas"],
    )


def main():
    result = {"schema": 1, "status": "REFUSED", "stage": "read_protected_packet"}
    try:
        mode = os.environ["IMAGE_ONLY_MODE"]
        workflow_sha = os.environ["GITHUB_WORKFLOW_SHA"]
        run_id = int(os.environ["GITHUB_RUN_ID"])
        result.update(mode=mode, workflow_sha=workflow_sha, run_id=run_id)
        isolated_yaml = os.environ.pop("PUSHER_IMAGE_ONLY_ISOLATED_KUBECONFIG")
        packet = json.loads(os.environ.pop("PUSHER_IMAGE_ONLY_PACKET"))
        proof = packet["proof"]
        require(
            packet["schema"] == 1
            and packet["mode"] == mode
            and packet["workflow_sha"] == workflow_sha
            and packet["run_id"] == run_id
            and (mode == "preview" or PROOF_ID.fullmatch(packet["release_approval"]))
            and mode in {"preview", "canary", "promote", "rollback"},
            "protected_run_approval_mismatch",
        )
        require(
            proof["prior_image"] == BASELINE
            and proof["source_sha"] == os.environ["SOURCE_SHA"]
            and proof["qualification_run_id"] == int(os.environ["QUALIFICATION_RUN_ID"])
            and proof["candidate_image"].split("@")[1] == os.environ["REQUESTED_DIGEST"],
            "dispatch_candidate_or_baseline_mismatch",
        )
        isolated_config = yaml.safe_load(isolated_yaml)
        require(
            all(
                not ({"exec", "auth-provider", "tokenFile", "client-key", "client-certificate"} & user["user"].keys())
                for user in isolated_config["users"]
            )
            and all("certificate-authority" not in item["cluster"] for item in isolated_config["clusters"]),
            "isolated_kubeconfig_must_be_self_contained",
        )
        with tempfile.TemporaryDirectory(prefix="pusher-image-only-") as tmp:
            isolated_file = Path(tmp) / "isolated-kubeconfig"
            isolated_file.write_text(isolated_yaml, encoding="utf-8")
            live = ProtectedCluster(Path(os.environ["KUBECONFIG"]), os.environ["LIVE_CONTEXT"])
            isolated = Cluster(isolated_file, isolated_config["current-context"], isolated=True)
            rehearsal = Rehearsal(live, isolated, proof)
            result.update(proof_receipt_fields(proof))
            execute(mode, packet, rehearsal, result)
        result.update(status="PASS", stage="complete")
    except Refused as error:
        result["reason"] = str(error)
    except (CanaryError, ReceiptError, GateError):
        result["reason"] = "canary_readiness_or_capacity_unproven"
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        AttributeError,
        IndexError,
        subprocess.TimeoutExpired,
        yaml.YAMLError,
    ):
        result["reason"] = "missing_invalid_or_unavailable_evidence"
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
