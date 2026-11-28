#!/usr/bin/env python3
"""Execute the protected Pusher image-only transition through live admission.

Production is the only admission surface. SCA-3161 closed the isolated rehearsal
route (GKE Warden's webhooks live in the managed control plane), so every probe
here is a `kubectl --dry-run=server` call against the live namespace. The single
live write is unchanged: the guarded JSON Patch of the Pusher container image.

Evidence is a non-secret dispatch input (`PUSHER_IMAGE_ONLY_EVIDENCE`) of run
ids only. Nothing in it is trusted: every referenced run is fetched from the
GitHub API, its prod-environment approvals are read from the run's `approvals`
endpoint, and its receipt is read from that run's artifact. The dispatching run
id is bound from `GITHUB_RUN_ID`, never from the packet.
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
sys.path.insert(0, str(ROOT / ".github/scripts"))
from pusher_canary_inverse import (
    INVERSE_HELPER_PATHS,
    PARITY_CLASSES,
    PARITY_EXCLUDED,
    PARITY_NORMALIZED,
    dependency_inventory,
    inventory_sha256,
    template_sha256,
)
from pusher_release_receipt import ReceiptError, config_fingerprint, validate_live_identity
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
INVERSE_ARTIFACT = "pusher-prod-canary-inverse-receipt"
PROMOTION_WORKFLOW = "gcp_backend_pusher.yml"
QUALIFICATION_WORKFLOW = "gcp_backend_pusher_auto_deploy.yml"
# The producer event of each workflow. The automatic development qualifier runs on
# a push to main; the protected promotion workflow is dispatched. Only the
# protected runs must be first attempts (the job refuses reruns itself); the
# qualifier keeps the same rule as verify_pusher_promotion_evidence.py.
WORKFLOW_EVENTS = {PROMOTION_WORKFLOW: "workflow_dispatch", QUALIFICATION_WORKFLOW: "push"}
FIRST_ATTEMPT_ONLY = frozenset({PROMOTION_WORKFLOW})
# A referenced preview or canary run is accepted only from a main revision whose
# evidence producers and verifiers are byte-identical to this run's revision.
CONTROL_PATHS = (
    ".github/workflows/gcp_backend_pusher.yml",
    ".github/scripts/pusher_image_only.py",
    ".github/scripts/pusher_canary_inverse.py",
    ".github/scripts/pusher_image_rehearsal.py",
    "backend/scripts/pusher_release_receipt.py",
    "backend/scripts/pusher_canary_from_live.py",
    "backend/scripts/pusher_prod_canary.py",
    "backend/scripts/pusher_semantic_probe.py",
    "backend/scripts/verify_pusher_promotion_evidence.py",
)
APPROVAL_ENVIRONMENT = "prod"
PACKET_FIELDS = frozenset(
    {
        "schema",
        "mode",
        "source_sha",
        "prior_image",
        "candidate_image",
        "qualification_run_id",
    }
)
BINDING_FIELDS = ("source_sha", "prior_image", "candidate_image", "qualification_run_id")
MODES = {"preview", "canary", "promote", "rollback"}
# Condition 1: a refused post-move inverse gets exactly one guarded reverse patch.
# Any other failure once the forward write was attempted goes through the same
# recovery: the single reverse when fresh preconditions are known, otherwise a
# HOLD. Nothing patches after a HOLD; the operator restores under Release custody.
REFUSED_INVERSE = "REFUSED_INVERSE"
UNCERTAIN_AFTER_WRITE = "UNCERTAIN_AFTER_WRITE"
REVERSE_OUTCOMES = ("not_attempted", "rejected_on_preconditions", "rejected", "unconfirmed", "succeeded")
RUNBOOK = "backend/docs/runbooks/pusher-image-preservation-proposal.md"
MANUAL_RESTORE_PATH = (
    f"Release prod-operator, per {RUNBOOK} (Manual recovery after a HOLD): confirm deployment/{TARGET} in "
    f"{NAMESPACE} still has the receipt's deployment_uid_before, and stop and escalate if it does not. "
    "List the rollout history and choose the revision whose pusher image is verified to read "
    f"{BASELINE}; restore only with kubectl -n {NAMESPACE} rollout undo deployment/{TARGET} "
    "--to-revision=<that verified revision>, never an unpinned undo. Then wait for rollout status and read back "
    "that digest on every ready pod and a clean deploy_status_report.py --env prod --include-gke --gke-service pusher. "
    "If the restore is refused or the readback differs, leave traffic as it is and escalate to Release."
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
    """After the forward write, recovery could not prove the baseline; no further patch is safe."""


class Reversed(Exception):
    """After the forward write failed a gate, the one guarded reverse restored and verified the baseline."""


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


def mark_write_attempt(marker, *, expected, desired):
    """Durably record that a live patch is about to be sent, before it is sent.

    If the process dies after the patch and before printing its receipt, the
    workflow's detector still sees this marker and pages UNCERTAIN_AFTER_WRITE.
    A marker that cannot be made durable refuses the write.
    """
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps({"expected": expected, "desired": desired}, sort_keys=True) + "\n"
        descriptor = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            os.write(descriptor, line.encode("utf-8"))
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        directory = os.open(marker.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except OSError:
        raise Refused("write_marker_unavailable") from None


class LiveWriter(ReadOnlyCluster):
    """The single guarded live patch. Only the promote and rollback paths hold it."""

    def __init__(self, cluster, marker):
        super().__init__(cluster)
        require(isinstance(marker, Path), "write_marker_unavailable")
        self._marker = marker

    def patch_image(self, obj, name, expected, desired):
        mark_write_attempt(self._marker, expected=expected, desired=desired)
        return submit_image_patch(self._cluster, obj, name, expected, desired, dry_run=False)


def dependency_versions(live, deployment):
    """Identity of every referenced ConfigMap/Secret, read without their content.

    The same reader the canary producer uses, so promote can compare the two.
    """
    pod_spec = deployment["spec"]["template"]["spec"]
    require(SHARED in {reference for reference, _ in config_references(pod_spec)}, "dependency_inventory_mismatch")
    return dependency_inventory(live, pod_spec, NAMESPACE)


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
    """Receipt fields that tie every run to the exact candidate and source.

    The preview emits exactly these fields and promote compares exactly these
    fields, so one schema serves producer and consumer.
    """
    fields = {key: packet[key] for key in BINDING_FIELDS}
    return {"binding_sha256": canonical_sha256(fields), **fields}


def validate_packet(packet, mode, workflow_sha, run_id):
    """Condition 4: the packet carries run ids only, and its shape is exact for the mode.

    Review and approval are not packet fields: they are resolved from the GitHub
    API for every referenced run and for this run.
    """
    required = PACKET_FIELDS | ({"reviewed_preview", "canary"} if mode in {"canary", "promote"} else set())
    require(
        isinstance(packet, dict)
        and packet.get("schema") == 2
        and packet.get("mode") == mode
        and mode in MODES
        and set(packet) == required
        and SHA.fullmatch(packet.get("source_sha") or "")
        and packet["source_sha"] != "0" * 40
        and packet["prior_image"] == BASELINE
        and IMAGE.fullmatch(packet.get("candidate_image") or "")
        and packet["candidate_image"].split("@")[1] != BASELINE.split("@")[1]
        and type(packet.get("qualification_run_id")) is int
        and packet["qualification_run_id"] > 0,
        "protected_evidence_mismatch",
    )
    if mode in {"canary", "promote"}:
        for key, reason in (("reviewed_preview", "reviewed_forward_preview_missing"), ("canary", "canary_evidence_missing")):
            reference = packet[key]
            require(
                isinstance(reference, dict)
                and set(reference) == {"run_id"}
                and type(reference["run_id"]) is int
                and reference["run_id"] > 0
                and reference["run_id"] != run_id,
                reason,
            )
        require(packet["reviewed_preview"]["run_id"] != packet["canary"]["run_id"], "protected_evidence_mismatch")
    dispatch = workflow_run_metadata(run_id, PROMOTION_WORKFLOW, expected_sha=workflow_sha, require_success=False)
    require(dispatch["status"] == "in_progress", "protected_run_unqualified")


def workflow_run_metadata(run_id, workflow_file, *, expected_sha=None, require_success=True):
    """Fetch one referenced run and prove it is this repo, this workflow, its producer event and source."""
    require(type(run_id) is int and run_id > 0, "invalid_evidence_run_id")
    require(workflow_file in WORKFLOW_EVENTS, "evidence_workflow_unknown")
    repo = f"repos/{REPO}"
    workflow_id = int(
        run(
            ["gh", "api", f"{repo}/actions/workflows/{workflow_file}", "--jq", ".id"],
            "evidence_workflow_unavailable",
        )
    )
    metadata = json.loads(run(["gh", "api", f"{repo}/actions/runs/{run_id}"], "evidence_run_unavailable"))
    attempt = metadata["run_attempt"]
    require(
        metadata["id"] == run_id
        and metadata["workflow_id"] == workflow_id
        and metadata["path"] == f".github/workflows/{workflow_file}"
        and metadata["event"] == WORKFLOW_EVENTS[workflow_file]
        and metadata["head_branch"] == "main"
        and SHA.fullmatch(metadata["head_sha"] or "")
        and (expected_sha is None or metadata["head_sha"] == expected_sha)
        and type(attempt) is int
        and (attempt == 1 if workflow_file in FIRST_ATTEMPT_ONLY else attempt >= 1)
        and metadata["head_repository"]["full_name"] == REPO,
        "evidence_run_unqualified",
    )
    if require_success:
        require(metadata["status"] == "completed" and metadata["conclusion"] == "success", "evidence_run_not_successful")
    return metadata


def accepted_workflow_revision(revision, workflow_sha):
    """A referenced run's workflow revision is accepted only if its evidence code equals ours."""
    require(SHA.fullmatch(revision or "") and SHA.fullmatch(workflow_sha or ""), "evidence_workflow_revision_invalid")
    if revision == workflow_sha:
        return
    git = ["git", "-C", str(ROOT)]
    run([*git, "merge-base", "--is-ancestor", revision, workflow_sha], "evidence_workflow_revision_not_on_main")
    run([*git, "diff", "--quiet", revision, workflow_sha, "--", *CONTROL_PATHS], "evidence_workflow_revision_changed")


def run_approvals(run_id):
    """Approver logins of the run's prod-environment deployment review, from the GitHub API.

    `GET /repos/{owner}/{repo}/actions/runs/{run_id}/approvals` needs `actions: read`
    for GITHUB_TOKEN. Any rejected prod review, or no approved one, refuses.
    """
    require(type(run_id) is int and run_id > 0, "invalid_evidence_run_id")
    approvals = json.loads(
        run(["gh", "api", f"repos/{REPO}/actions/runs/{run_id}/approvals"], "environment_approvals_unavailable")
    )
    require(isinstance(approvals, list), "environment_approvals_unavailable")
    prod = [
        approval
        for approval in approvals
        if any(environment.get("name") == APPROVAL_ENVIRONMENT for environment in approval.get("environments") or [])
    ]
    require(bool(prod) and all(approval.get("state") == "approved" for approval in prod), "prod_environment_approval_missing")
    logins = sorted({approval["user"]["login"] for approval in prod})
    require(all(isinstance(login, str) and login for login in logins), "prod_environment_approval_missing")
    return logins


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
    artifacts = {
        CANARY_ARTIFACT: {
            "evidence": "pusher-prod-canary-evidence.json",
            "deployment_receipt": "pusher-prod-canary-deployment-receipt.json",
            "semantic_receipt": "pusher-prod-canary-semantic-probe.json",
        },
        INVERSE_ARTIFACT: {"inverse_receipt": "pusher-prod-canary-inverse-receipt.json"},
    }
    result = {}
    for artifact, names in artifacts.items():
        with tempfile.TemporaryDirectory(prefix="pusher-canary-evidence-") as tmp:
            run(
                ["gh", "run", "download", str(run_id), "--repo", REPO, "-n", artifact, "--dir", tmp],
                "canary_artifact_unavailable",
            )
            result.update({key: read_json(Path(tmp) / name) for key, name in names.items()})
    return result


def check_qualification(packet, workflow_sha):
    """Condition 4: the qualification run is fetched, then its artifact is re-verified.

    The qualified revision must already carry this revision's canary inverse helper,
    byte for byte: a qualification that predates it cannot back a canary that ran it.
    """
    metadata = workflow_run_metadata(
        packet["qualification_run_id"], QUALIFICATION_WORKFLOW, expected_sha=packet["source_sha"]
    )
    run(
        ["git", "-C", str(ROOT), "diff", "--quiet", metadata["head_sha"], workflow_sha, "--", *INVERSE_HELPER_PATHS],
        "qualification_predates_inverse_helper",
    )
    return check_provenance({key: packet[key] for key in ("prior_image", "candidate_image", "source_sha", "qualification_run_id")})


def check_reviewed_preview(packet, result):
    """The preview run is fetched, its prod approval resolved, then its own receipt compared."""
    run_id = packet["reviewed_preview"]["run_id"]
    metadata = workflow_run_metadata(run_id, PROMOTION_WORKFLOW)
    accepted_workflow_revision(metadata["head_sha"], result["workflow_sha"])
    approvers = run_approvals(run_id)
    preview = download_receipt(run_id)
    require(
        preview["schema"] == 2
        and preview["mode"] == "preview"
        and preview["stage"] == "complete"
        and preview["status"] == "PASS"
        and preview["run_id"] == run_id
        and preview["workflow_sha"] == metadata["head_sha"]
        and preview["forward_server_dry_run"] == "PASS"
        and preview["live_baseline_server_dry_run"] == "PASS"
        and all(preview[key] == result[key] for key in ("binding_sha256", *BINDING_FIELDS)),
        "reviewed_forward_preview_missing",
    )
    result.setdefault("approvals", {})["preview"] = approvers
    result.update(reviewed_preview_run_id=run_id, reviewed_preview_workflow_sha=metadata["head_sha"])
    return preview


def check_canary(packet, result, qualification_receipt):
    """Condition 4: fetch the canary run, resolve its approval, then bind its evidence and inverse."""
    run_id = packet["canary"]["run_id"]
    metadata = workflow_run_metadata(run_id, PROMOTION_WORKFLOW)
    workflow_sha = metadata["head_sha"]
    accepted_workflow_revision(workflow_sha, result["workflow_sha"])
    approvers = run_approvals(run_id)
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
    check_canary_inverse(artifacts["inverse_receipt"], packet, deployment, workflow_sha)
    result.setdefault("approvals", {})["canary"] = approvers
    result.update(
        canary_run_id=run_id,
        canary_workflow_sha=workflow_sha,
        canary_evidence_sha256=canonical_sha256(artifacts["evidence"]),
        canary_inverse_receipt="PASS",
    )
    return artifacts


def check_canary_inverse(inverse, packet, deployment, workflow_sha):
    """Condition 2: the candidate→baseline dry-run ran on the isolated canary object."""
    live_identity = deployment["live_identity"]
    run_id = packet["canary"]["run_id"]
    parity = inverse.get("template_parity") if isinstance(inverse, dict) else None
    live = inverse.get("live_deployment") if isinstance(inverse, dict) else None
    require(
        isinstance(inverse, dict)
        and inverse.get("schema") == 1
        and inverse.get("status") == "PASS"
        and inverse.get("run_id") == run_id
        and inverse.get("workflow_sha") == workflow_sha
        and inverse.get("source_sha") == packet["source_sha"]
        and inverse.get("candidate_image") == packet["candidate_image"]
        and inverse.get("baseline_image") == packet["prior_image"]
        and inverse.get("mode") == "canary_only"
        and inverse.get("dry_run") == "server"
        and isinstance(parity, dict)
        and parity.get("live_deployment") == TARGET
        and parity.get("canary_deployment") == canary_target(run_id)
        and parity.get("excluded") == list(PARITY_EXCLUDED)
        and parity.get("normalized") == list(PARITY_NORMALIZED)
        and isinstance(parity.get("classes"), dict)
        and set(parity["classes"]) == set(PARITY_CLASSES)
        and all(value in {"equal", "differs"} for value in parity["classes"].values())
        and isinstance(inverse.get("dependencies"), dict)
        and set(inverse["dependencies"])
        == {"names", "runtime_config_map", "prestart_sha256", "startup_sha256", "probe_sha256", "shared_sha256", "stable"}
        # The full inventory, isolated runtime ConfigMap included, held from before
        # the canary's first pod through its probe.
        and inverse["dependencies"]["runtime_config_map"] == canary_config_map(run_id)
        and ["configmap", canary_config_map(run_id)] in inverse["dependencies"]["names"]
        and inverse["dependencies"]["stable"] is True
        and all(
            isinstance(inverse["dependencies"][key], str) and len(inverse["dependencies"][key]) == 64
            for key in ("prestart_sha256", "shared_sha256")
        )
        and inverse["dependencies"]["prestart_sha256"]
        == inverse["dependencies"]["startup_sha256"]
        == inverse["dependencies"]["probe_sha256"]
        and isinstance(live, dict)
        and set(live) == {"name", "uid", "template_sha256"}
        and live["name"] == TARGET
        and isinstance(live["uid"], str)
        and live["uid"]
        and inverse.get("deployment", {}).get("namespace") == NAMESPACE
        and inverse.get("deployment", {}).get("name") == canary_target(run_id)
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


def check_effective_environment(live, artifacts, before, result):
    """Finding 5: the canary's startup inputs must equal what the live Pusher will start with.

    The canary ran against a freshly rendered isolated ConfigMap and a freshly
    rendered template; an image-only promote keeps the live ConfigMap and template.
    Reuses the canary-to-production ConfigMap hash of the regular Helm path
    (verify_pusher_promotion_evidence.py) and the canary's redacted template
    parity, and requires the live template to be the one that parity measured.
    Referenced Secrets and ConfigMaps must keep the metadata identity (UID and
    resourceVersion) the canary saw at startup and at probe time, so a rotation
    between canary and promote refuses. Only `equal`/`differs` per input class is
    recorded.
    """
    deployment = live.deployment()
    inverse = artifacts["inverse_receipt"]
    config_map = live.get("configmap", SHARED[1], namespace=NAMESPACE)
    classes = {
        "runtime_config_map": (
            "equal"
            if config_fingerprint(config_map, expected_name=SHARED[1]) == artifacts["deployment_receipt"]["config_sha256"]
            else "differs"
        ),
        "pod_template": (
            "equal" if all(value == "equal" for value in inverse["template_parity"]["classes"].values()) else "differs"
        ),
        "dependency_versions": (
            "equal"
            if inventory_sha256(before["dependencies"], exclude=SHARED) == inverse["dependencies"]["shared_sha256"]
            else "differs"
        ),
        "live_template_since_canary": (
            "equal"
            if inverse["live_deployment"]
            == {"name": TARGET, "uid": version(deployment)[0], "template_sha256": template_sha256(deployment)}
            else "differs"
        ),
    }
    result["effective_environment"] = classes
    require(all(value == "equal" for value in classes.values()), "effective_environment_differs")


def canary_target(run_id):
    return f"prod-omi-pusher-canary-{run_id}"


def canary_config_map(run_id):
    return f"prod-omi-backend-config-canary-{run_id}"


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
    patched_uid = version(changed)[0]
    # A replacement Deployment with the same image and generation is not the object
    # this run patched; it must never read as PASS or REVERSED.
    require(
        version(deployed)[0] == patched_uid == before["deployment"][0],
        "deployment_replaced_after_patch",
    )
    require(
        deployed["metadata"]["generation"] == changed["metadata"]["generation"] and image_of(deployed, TARGET) == image,
        "deployment_generation_changed_after_patch",
    )
    identity = verify_ready(live, deployed, image)
    require(identity["deployment_uid"] == patched_uid, "deployment_replaced_after_patch")
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
    qualification_receipt = check_qualification(packet, result["workflow_sha"])
    if mode in {"canary", "promote"}:
        result["stage"] = "verify_canary_evidence"
        artifacts = check_canary(packet, result, qualification_receipt)

    result["stage"] = "observe_baseline"
    before = state(live)
    require(before["image"] == BASELINE, "observed_image_changed")
    result.update(summary(before), deployment_uid_before=before["deployment"][0])
    if mode in {"canary", "promote"}:
        result["stage"] = "verify_reviewed_preview"
        preview = check_reviewed_preview(packet, result)
        require(before["deployment"] == preview["live_baseline"], "reviewed_baseline_changed")
        result["stage"] = "compare_effective_environment"
        check_effective_environment(live, artifacts, before, result)

    baseline = live.deployment()
    result["stage"] = "server_dry_run_forward"
    admitted = live.probe(baseline, TARGET, BASELINE, candidate)
    result["forward_server_dry_run"] = "PASS"
    result["stage"] = "server_dry_run_baseline_self"
    # Current-state rollback evidence: today's admission accepts the baseline
    # object. Warden evaluates the object, so the oldObject difference between
    # this dry-run and a real restore does not change the verdict (scoped ruling).
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

    # From here on the forward write has been attempted. Every exception, not only an
    # admission refusal, goes through recovery: there is no path back to main()'s
    # generic evidence error, and nothing retries the forward write.
    result.update(stage="live_patch_attempted", live_write_attempted=True, reverse_patch="not_attempted")
    try:
        changed = writer.patch_image(baseline, TARGET, BASELINE, candidate)
        result.update(patch_observed=version(changed), patched_deployment_uid=version(changed)[0], requested_image=candidate)
        result["stage"] = "read_post_move_state"
        after = live.deployment()
        require(
            version(after)[0] == before["deployment"][0] and image_of(after, TARGET) == candidate,
            "live_candidate_not_persisted",
        )
        result["stage"] = "server_dry_run_post_move_inverse"
        live.probe(after, TARGET, candidate, BASELINE)
    except Exception as error:
        if isinstance(error, Refused) and result["stage"] == "server_dry_run_post_move_inverse":
            # Admission answered and refused the inverse (or changed more than the image).
            result.update(live_inverse_server_dry_run="REFUSED", inverse_refusal=str(error))
            recover(live, writer, before, candidate, result, trigger=REFUSED_INVERSE)
        else:
            # The write, the post-write read or the probe did not answer: outcome unknown.
            result.update(live_inverse_server_dry_run="UNPROVEN", post_write_failure=categorical(error))
            recover(live, writer, before, candidate, result, trigger=UNCERTAIN_AFTER_WRITE)
    result["live_inverse_server_dry_run"] = "PASS"

    result["stage"] = "verify_serving"
    try:
        identity = verify_serving(live, before, changed, candidate, result)
    except Exception as error:
        # The single rollout wait is spent; reversing now would start a second
        # unbounded rollout past the job ceiling. Hold with the observed state.
        result["post_write_failure"] = categorical(error)
        hold(live, result, "forward_serving_unverified", reason=UNCERTAIN_AFTER_WRITE)
    result.update(
        deploy_status_report="PASS",
        serving_image=candidate,
        serving_deployment_uid=identity["deployment_uid"],
        serving_generation=identity["generation"],
        ready_replicas=identity["ready_replicas"],
    )


def categorical(error):
    """A receipt-safe label: Refused reasons are categorical; anything else is its type only."""
    return str(error) if isinstance(error, Refused) else f"unexpected_{type(error).__name__}"


def hold(live, result, hold_stage, *, reason):
    """End in a HOLD with the observed state. Nothing after this point may patch."""
    try:
        observed = live.deployment()
        observed_uid, observed_image = version(observed)[0], image_of(observed, TARGET)
    except Exception:  # The hold must be reported even if the read fails.
        observed_uid, observed_image = "unread", "unread"
    result.update(
        stage="hold",
        hold_stage=hold_stage,
        reason=reason,
        manual_restore_path=MANUAL_RESTORE_PATH,
        deployment_uid_observed=observed_uid,
        serving_image_observed=observed_image,
    )
    deploy_status_report(strict=False)
    raise Hold(reason)


def recover(live, writer, before, candidate, result, *, trigger):
    """After a failed post-write gate: the one reverse if fresh preconditions are known, else HOLD."""
    result["stage"] = "recover_after_write"
    try:
        observed = live.deployment()
        known = version(observed)[0] == before["deployment"][0] and image_of(observed, TARGET) == candidate
    except Exception as error:
        result["post_write_failure"] = result.get("post_write_failure") or categorical(error)
        hold(live, result, "post_write_state_unread", reason=UNCERTAIN_AFTER_WRITE)
    if not known:
        result["reverse_patch"] = "rejected_on_preconditions"
        hold(live, result, "post_write_state_unexpected", reason=UNCERTAIN_AFTER_WRITE)
    reverse_once(live, writer, before, candidate, result, trigger=trigger)


def reverse_once(live, writer, before, candidate, result, *, trigger):
    """Condition 1: exactly one guarded reverse patch after the forward write failed a gate.

    Fresh preconditions: the Deployment is re-read immediately before the patch, so
    it tests the same UID, the current resourceVersion, the pusher container and the
    candidate image. On success the baseline rollout and readiness are verified and
    the run reports REVERSED (still a failed promote). Any failure of the patch or
    of that verification is a HOLD with no further patch.
    """
    result["stage"] = "reverse_after_write"
    try:
        fresh = live.deployment()
        require(
            version(fresh)[0] == before["deployment"][0] and image_of(fresh, TARGET) == candidate,
            "reverse_preconditions_changed",
        )
    except Exception as error:
        result.update(reverse_patch="rejected_on_preconditions", reverse_refusal=categorical(error))
        hold(live, result, "reverse_preconditions_unproven", reason=trigger)
    try:
        reversed_obj = writer.patch_image(fresh, TARGET, candidate, BASELINE)
        result.update(
            reverse_patch="succeeded",
            reverse_patch_observed=version(reversed_obj),
            reverse_patched_deployment_uid=version(reversed_obj)[0],
        )
    except Exception as error:  # Any outcome but a confirmed reverse is uncertain: hold.
        result.update(
            reverse_patch="rejected" if isinstance(error, Refused) else "unconfirmed",
            reverse_refusal=categorical(error),
        )
        hold(live, result, "reverse_patch_failed", reason=trigger)
    try:
        result["stage"] = "verify_reverse_serving"
        identity = verify_serving(live, before, reversed_obj, BASELINE, result)
    except Exception as error:
        result["reverse_refusal"] = categorical(error)
        hold(live, result, "reverse_serving_unverified", reason=trigger)
    result.update(
        stage="reversed_after_write",
        reason=f"{trigger}_REVERSED",
        deploy_status_report="PASS",
        serving_image=BASELINE,
        serving_deployment_uid=identity["deployment_uid"],
        serving_generation=identity["generation"],
        ready_replicas=identity["ready_replicas"],
    )
    raise Reversed(f"{trigger}_REVERSED")


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
    result.update(summary(before), deployment_uid_before=before["deployment"][0])
    result["stage"] = "server_dry_run_inverse"
    live.probe(live.deployment(), TARGET, packet["candidate_image"], BASELINE)
    result["live_inverse_server_dry_run"] = "PASS"
    require_unchanged(live, before, packet["candidate_image"])
    result.update(stage="live_patch_attempted", live_write_attempted=True, reverse_patch="not_attempted")
    try:
        changed = writer.patch_image(live.deployment(), TARGET, packet["candidate_image"], BASELINE)
        result.update(patch_observed=version(changed), patched_deployment_uid=version(changed)[0], requested_image=BASELINE)
        result["stage"] = "verify_serving"
        identity = verify_serving(live, before, changed, BASELINE, result)
    except Exception as error:
        # Rollback is itself the reverse; a failure after its write is never retried.
        result["post_write_failure"] = categorical(error)
        hold(live, result, "rollback_unverified", reason=UNCERTAIN_AFTER_WRITE)
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
        # The approval of this run comes from the GitHub API, never the packet.
        # Agents and humans share one GitHub account, so this proves a prod
        # environment approval happened, not who in particular approved it.
        result["approvals"] = {"current": run_approvals(run_id)}
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
            writer = LiveWriter(raw, Path(os.environ["PUSHER_IMAGE_ONLY_WRITE_MARKER"])) if mode in {"promote", "rollback"} else None
            execute(mode, packet, live, result, writer=writer)
        result.update(status="PASS", stage="complete")
    except Hold as error:
        result.update(status="HOLD", reason=str(error))
    except Reversed as error:
        result.update(status="REVERSED", reason=str(error))
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
    except Exception as error:  # The receipt must always be printed.
        result["reason"] = f"unexpected_{type(error).__name__}"
    if result.get("live_write_attempted") and result["status"] not in {"PASS", "HOLD", "REVERSED"}:
        # Defence in depth: execute() routes every post-write failure to recovery, but a
        # write that was attempted must never end as an ordinary refusal that nobody pages.
        result.update(
            status="HOLD",
            post_write_failure=result.get("reason"),
            reason=UNCERTAIN_AFTER_WRITE,
            hold_stage=result.get("hold_stage") or "unhandled_after_write",
            manual_restore_path=MANUAL_RESTORE_PATH,
        )
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
