#!/usr/bin/env python3
"""Rehearse the Pusher image-only patch against an isolated Kubernetes API server."""

from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
REPO = "BasedHardware/omi"
NAMESPACE = "prod-omi-backend"
TARGET = "prod-omi-pusher"
SHARED = ("configmap", "prod-omi-backend-config")
IMAGE = re.compile(r"gcr\.io/based-hardware/(?:backend-)?pusher@sha256:[a-f0-9]{64}")
SHA = re.compile(r"[a-f0-9]{40}")
NAME = re.compile(r"[a-z0-9][a-z0-9.-]{0,252}")
PROOF_ID = re.compile(r"[A-Za-z0-9_-]{1,100}")
ADMISSION = {
    "mutatingwebhookconfigurations.admissionregistration.k8s.io",
    "validatingwebhookconfigurations.admissionregistration.k8s.io",
    "validatingadmissionpolicies.admissionregistration.k8s.io",
    "validatingadmissionpolicybindings.admissionregistration.k8s.io",
}
STORAGE_METADATA = {"uid", "resourceVersion", "generation", "creationTimestamp", "managedFields"}


class Refused(Exception):
    """A categorical failure that is safe to include in a release receipt."""


def require(condition, reason):
    if not condition:
        raise Refused(reason)


def run(args, reason, *, stdin=None):
    result = subprocess.run(args, input=stdin, cwd=ROOT, capture_output=True, text=True, check=False, timeout=120)
    require(result.returncode == 0, reason)
    return result.stdout


def version(obj):
    if obj is None:
        return None
    metadata = obj["metadata"]
    result = [metadata["uid"], metadata["resourceVersion"]]
    require(all(isinstance(item, str) and item for item in result), "object_identity_missing")
    return result


def comparable(obj):
    metadata = {key: value for key, value in obj["metadata"].items() if key not in STORAGE_METADATA}
    return {**{key: value for key, value in obj.items() if key not in {"metadata", "status"}}, "metadata": metadata}


def container_index(obj):
    require(
        obj["apiVersion"] == "apps/v1"
        and obj["kind"] == "Deployment"
        and obj["metadata"]["namespace"] == NAMESPACE
        and obj["metadata"]["name"] == TARGET
        and not obj["metadata"].get("deletionTimestamp"),
        "wrong_target",
    )
    containers = obj["spec"]["template"]["spec"]["containers"]
    matches = [index for index, container in enumerate(containers) if container["name"] == "pusher"]
    require(len(matches) == 1, "pusher_container_ambiguous")
    return matches[0]


def current_image(obj):
    return obj["spec"]["template"]["spec"]["containers"][container_index(obj)]["image"]


def with_image(obj, image):
    expected = copy.deepcopy(comparable(obj))
    expected["spec"]["template"]["spec"]["containers"][container_index(obj)]["image"] = image
    return expected


def guarded_patch(obj, expected, desired, *, allow_same=False):
    require(IMAGE.fullmatch(expected) and IMAGE.fullmatch(desired), "unpinned_image")
    require(current_image(obj) == expected and (allow_same or expected != desired), "unexpected_current_image")
    uid, revision = version(obj)
    path = f"/spec/template/spec/containers/{container_index(obj)}"
    return [
        {"op": "test", "path": "/metadata/uid", "value": uid},
        {"op": "test", "path": "/metadata/resourceVersion", "value": revision},
        {"op": "test", "path": f"{path}/name", "value": "pusher"},
        {"op": "test", "path": f"{path}/image", "value": expected},
        {"op": "replace", "path": f"{path}/image", "value": desired},
    ]


class Cluster:
    def __init__(self, kubeconfig, context, *, isolated=False):
        self.command = (
            "kubectl",
            "--kubeconfig",
            str(kubeconfig.resolve()),
            "--context",
            context,
            "--request-timeout=30s",
        )
        self.isolated = isolated

    def call(self, *args, reason="kubernetes_read_failed", stdin=None):
        response = run([*self.command, *args], reason, stdin=stdin)
        return json.loads(response) if response.strip() else None

    def get(self, resource, name=None, *, namespace=None, optional=False):
        args = ["get", resource]
        if name is not None:
            args.append(name)
        if namespace is not None:
            args.extend(("--namespace", namespace))
        if optional:
            args.append("--ignore-not-found")
        result = self.call(*args, "-o", "json")
        if optional and result and result.get("kind") == "List" and result.get("items") == []:
            return None
        return result

    def identity(self):
        return self.call("auth", "whoami", "-o", "json")["status"]["userInfo"]

    def server(self):
        config = self.call("config", "view", "--minify", "-o", "json")
        require(len(config["clusters"]) == 1, "cluster_endpoint_ambiguous")
        cluster = config["clusters"][0]["cluster"]
        require(
            cluster["server"].startswith("https://") and not cluster.get("insecure-skip-tls-verify"),
            "cluster_tls_not_verified",
        )
        return cluster["server"]

    def api_version(self):
        return self.call("version", "-o", "json")["serverVersion"]["gitVersion"]

    def admission_resources(self):
        response = run(
            [
                *self.command,
                "api-resources",
                "--cached=false",
                "--api-group=admissionregistration.k8s.io",
                "-o",
                "name",
            ],
            "admission_discovery_unavailable",
        )
        return set(response.split())

    def deployment(self):
        return self.get("deployment.apps", TARGET, namespace=NAMESPACE)

    def assert_no_rehearsal_pods(self):
        for resource in ("pods", "replicasets.apps"):
            require(self.get(resource, namespace=NAMESPACE)["items"] == [], "isolated_controllers_active")

    def transition(self, obj, expected, desired, *, dry_run=True, allow_same=False):
        require(dry_run or self.isolated, "production_write_refused")
        patch = guarded_patch(obj, expected, desired, allow_same=allow_same)
        mode = "--dry-run=server" if dry_run else "--dry-run=none"
        admitted = self.call(
            "patch",
            "deployment.apps",
            TARGET,
            "--namespace",
            NAMESPACE,
            "--type=json",
            "--patch-file=/dev/stdin",
            mode,
            "-o",
            "json",
            reason="server_dry_run_rejected" if dry_run else "isolated_patch_failed_reconcile_before_retry",
            stdin=json.dumps(patch),
        )
        require(
            admitted["metadata"]["uid"] == version(obj)[0] and comparable(admitted) == with_image(obj, desired),
            "admission_changed_more_than_image",
        )
        return admitted


def config_references(value):
    """Find direct and projected ConfigMap/Secret references without reading their content."""
    kinds = {
        "configMap": "configmap",
        "configMapRef": "configmap",
        "configMapKeyRef": "configmap",
        "secret": "secret",
        "secretRef": "secret",
        "secretKeyRef": "secret",
    }
    if isinstance(value, dict):
        for key, item in value.items():
            if key in kinds and isinstance(item, dict):
                name = item.get("name") or item.get("secretName")
                if isinstance(name, str) and name:
                    yield (kinds[key], name), item.get("optional") is True
            if key == "imagePullSecrets" and isinstance(item, list):
                for secret in item:
                    yield ("secret", secret["name"]), False
            yield from config_references(item)
    elif isinstance(value, list):
        for item in value:
            yield from config_references(item)


def validate_proof(proof):
    fields = {
        "schema",
        "id",
        "evidence",
        "valid_until",
        "prior_image",
        "candidate_image",
        "source_sha",
        "qualification_run_id",
        "effective_user",
        "server_urls",
        "namespace_uids",
        "live_deployment",
        "isolated_deployment",
        "extra_admission_resources",
        "live_dependencies",
    }
    require(set(proof) == fields and proof["schema"] == 1 and PROOF_ID.fullmatch(proof["id"]), "invalid_release_proof")
    evidence_fields = {
        "admission_and_isolation",
        "effective_startup_inputs",
        "shared_consumer_inventory",
        "writer_exclusion",
    }
    require(
        set(proof["evidence"]) == evidence_fields
        and all(PROOF_ID.fullmatch(ref) for ref in proof["evidence"].values()),
        "release_evidence_missing",
    )
    expiry = datetime.fromisoformat(proof["valid_until"])
    require(expiry.tzinfo and datetime.now(timezone.utc) < expiry, "release_proof_expired")
    require(
        isinstance(proof["effective_user"], dict) and bool(proof["effective_user"].get("username")),
        "reviewed_effective_identity_missing",
    )
    require(
        IMAGE.fullmatch(proof["prior_image"])
        and IMAGE.fullmatch(proof["candidate_image"])
        and proof["prior_image"].split("@")[1] != proof["candidate_image"].split("@")[1]
        and SHA.fullmatch(proof["source_sha"])
        and proof["source_sha"] != "0" * 40
        and isinstance(proof["qualification_run_id"], int)
        and not isinstance(proof["qualification_run_id"], bool)
        and proof["qualification_run_id"] > 0,
        "invalid_candidate_identity",
    )


def check_provenance(proof):
    source = proof["source_sha"]
    candidate = proof["candidate_image"]
    repository, digest = candidate.split("@")
    dev_repository = repository.replace("/based-hardware/", "/based-hardware-dev/", 1)
    run_id = str(proof["qualification_run_id"])
    gh = ["gh", "api"]
    path = f"repos/{REPO}"
    main = run([*gh, f"{path}/git/ref/heads/main", "--jq", ".object.sha"], "fresh_main_unavailable").strip()
    require(SHA.fullmatch(main), "fresh_main_invalid")
    git = ["git", "-C", str(ROOT)]
    require(run([*git, "rev-parse", "origin/main"], "fresh_main_unavailable").strip() == main, "fetch_fresh_main")
    run([*git, "merge-base", "--is-ancestor", source, main], "source_not_merged")
    scripts = ROOT / "backend/scripts"
    closure = run(
        [sys.executable, str(scripts / "verify_pusher_source_closure.py"), "--image-repository", dev_repository],
        "source_closure_unavailable",
    ).splitlines()
    require(closure, "source_closure_unavailable")
    run([*git, "diff", "--quiet", source, main, "--", *closure], "source_or_chart_closure_changed")

    with tempfile.TemporaryDirectory(prefix="pusher-qualification-") as tmp:
        directory = Path(tmp)
        eligibility = directory / "eligibility.json"
        eligibility.write_text(
            run(
                [
                    *gh,
                    f"{path}/actions/workflows/release-eligibility.yml/runs"
                    f"?event=push&branch=main&status=completed&head_sha={source}",
                ],
                "release_eligibility_unavailable",
            ),
            encoding="utf-8",
        )
        run(
            [
                sys.executable,
                str(ROOT / ".github/scripts/verify_backend_release_admission.py"),
                "--sha",
                source,
                "--repository",
                REPO,
                "--workflow-runs",
                str(eligibility),
                "--require-first-attempt",
            ],
            "source_admission_failed",
        )
        workflow_id = run(
            [
                *gh,
                f"{path}/actions/workflows/gcp_backend_pusher_auto_deploy.yml",
                "--jq",
                ".id",
            ],
            "qualification_workflow_unavailable",
        ).strip()
        metadata = directory / "run.json"
        metadata.write_text(
            run([*gh, f"{path}/actions/runs/{run_id}"], "qualification_run_unavailable"), encoding="utf-8"
        )
        require(
            json.loads(metadata.read_text(encoding="utf-8"))["head_repository"]["full_name"] == REPO,
            "qualification_repository_mismatch",
        )
        artifacts = directory / "artifacts"
        run(
            [
                "gh",
                "run",
                "download",
                run_id,
                "--repo",
                REPO,
                "-n",
                "pusher-dev-qualification",
                "--dir",
                str(artifacts),
            ],
            "qualification_artifact_unavailable",
        )
        run(
            [
                sys.executable,
                str(scripts / "verify_pusher_promotion_evidence.py"),
                "--phase",
                "qualification",
                "--evidence",
                str(artifacts / "pusher-dev-qualification.json"),
                "--deployment-receipt",
                str(artifacts / "pusher-dev-deployment-receipt.json"),
                "--run-json",
                str(metadata),
                "--expected-digest",
                digest,
                "--expected-repository",
                dev_repository,
                "--expected-workflow-id",
                workflow_id,
                "--expected-run-id",
                run_id,
                "--expected-qualification-source-sha",
                source,
            ],
            "development_qualification_failed",
        )

    for image in (f"{dev_repository}@{digest}", candidate, proof["prior_image"]):
        remote_digest = run(
            ["gcloud", "container", "images", "describe", image, "--format=value(image_summary.digest)"],
            "registry_digest_unavailable",
        ).strip()
        require(remote_digest == image.split("@")[1], "registry_digest_mismatch")


def read_admission(cluster, reviewed_resources):
    namespace = cluster.get("namespace", NAMESPACE)
    policies = {}
    versions = [version(namespace)]
    discovered = cluster.admission_resources()
    require(ADMISSION <= discovered, "mandatory_admission_api_unavailable")
    for resource in sorted(discovered | set(reviewed_resources)):
        listing = cluster.get(resource)
        require(not listing["metadata"].get("continue"), "incomplete_admission_inventory")
        objects = sorted(listing["items"], key=lambda obj: obj["metadata"]["name"])
        policies[resource] = [comparable(obj) for obj in objects]
        versions.extend(version(obj) for obj in objects)
    return (cluster.api_version(), comparable(namespace), policies), versions


class Rehearsal:
    def __init__(self, live, isolated, proof):
        validate_proof(proof)
        self.live = live
        self.isolated = isolated
        self.proof = proof
        self.prior = proof["prior_image"]
        self.candidate = proof["candidate_image"]

    def observe(self, expected_live, expected_isolated):
        validate_proof(self.proof)
        live, isolated = self.live.deployment(), self.isolated.deployment()
        require(version(live)[0] == self.proof["live_deployment"][0], "live_uid_changed")
        require(version(isolated)[0] == self.proof["isolated_deployment"][0], "isolated_uid_changed")
        require(version(live)[0] != version(isolated)[0], "isolation_not_distinct")
        require(
            current_image(live) == expected_live and current_image(isolated) == expected_isolated,
            "observed_image_changed",
        )
        require(with_image(live, self.prior) == with_image(isolated, self.prior), "deployment_baseline_differs")

        require(
            self.live.identity() == self.isolated.identity() == self.proof["effective_user"],
            "effective_identity_differs",
        )
        servers = [self.live.server(), self.isolated.server()]
        require(servers[0] != servers[1] and servers == self.proof["server_urls"], "cluster_endpoint_mismatch")
        reviewed = self.proof["extra_admission_resources"]
        require(
            isinstance(reviewed, list) and all(NAME.fullmatch(resource) for resource in reviewed),
            "invalid_admission_inventory",
        )
        live_admission, live_versions = read_admission(self.live, reviewed)
        isolated_admission, isolated_versions = read_admission(self.isolated, reviewed)
        require(live_versions[0][0] != isolated_versions[0][0], "isolation_namespace_not_distinct")
        require([live_versions[0][0], isolated_versions[0][0]] == self.proof["namespace_uids"], "namespace_uid_changed")
        require(live_admission == isolated_admission, "admission_configuration_differs")
        self.isolated.assert_no_rehearsal_pods()

        expected = {}
        for item in self.proof["live_dependencies"]:
            kind, name = item["resource"], item["name"]
            require(
                NAME.fullmatch(kind) and NAME.fullmatch(name) and (kind, name) not in expected,
                "invalid_dependency_inventory",
            )
            expected[kind, name] = item["version"]
        references = list(config_references(live["spec"]["template"]["spec"]))
        refs = {ref for ref, _ in references}
        require(
            SHARED in refs and refs <= expected.keys() and expected[SHARED] is not None,
            "shared_reference_or_dependency_missing",
        )
        require(
            all(optional or expected[ref] is not None for ref, optional in references),
            "required_dependency_absent",
        )
        for (kind, name), identity_version in sorted(expected.items()):
            actual = self.live.get(kind, name, namespace=NAMESPACE, optional=True)
            require(version(actual) == identity_version, "live_dependency_changed")
        validate_proof(self.proof)
        return live, isolated, [live_versions, isolated_versions]

    def recheck(self, live, isolated, policies):
        fresh_live, fresh_isolated, fresh_policies = self.observe(current_image(live), current_image(isolated))
        require(
            version(fresh_live) == version(live)
            and comparable(fresh_live) == comparable(live)
            and version(fresh_isolated) == version(isolated)
            and comparable(fresh_isolated) == comparable(isolated)
            and fresh_policies == policies,
            "state_changed_during_verification",
        )

    def rehearse(self, result):
        result["stage"] = "observe_prior"
        live, prior, policies = self.observe(self.prior, self.prior)
        require(
            version(live) == self.proof["live_deployment"] and version(prior) == self.proof["isolated_deployment"],
            "reviewed_baseline_changed",
        )
        result["stage"] = "preview_forward_and_prior"
        live_forward = self.live.transition(live, self.prior, self.candidate)
        live_prior = self.live.transition(live, self.prior, self.prior, allow_same=True)
        isolated_forward = self.isolated.transition(prior, self.prior, self.candidate)
        require(comparable(live_forward) == comparable(isolated_forward), "forward_admission_differs")
        self.recheck(live, prior, policies)

        result["stage"] = "isolated_forward"
        # Only the isolated cluster persists the candidate. The returned resourceVersion becomes
        # the inverse precondition, after a fresh read proves this is still that exact object.
        candidate = self.isolated.transition(prior, self.prior, self.candidate, dry_run=False)
        require(version(candidate)[1] != version(prior)[1], "isolated_forward_not_persisted")
        self.recheck(live, candidate, policies)
        result["stage"] = "isolated_inverse"
        preview = self.isolated.transition(candidate, self.candidate, self.prior)
        require(comparable(preview) == comparable(live_prior), "inverse_admission_differs")
        self.recheck(live, candidate, policies)
        restored = self.isolated.transition(candidate, self.candidate, self.prior, dry_run=False)
        require(version(restored)[1] != version(candidate)[1], "isolated_inverse_not_persisted")
        self.recheck(live, restored, policies)
        result.update(
            live_baseline=version(live),
            isolated_restored=version(restored),
            isolated_candidate=version(candidate),
            admission_versions=policies,
        )

    def verify_inverse(self, rehearsal, result):
        result["stage"] = "observe_live_candidate"
        require(
            rehearsal["status"] == "PASS"
            and rehearsal["mode"] == "rehearse"
            and all(
                rehearsal[key] == result[key]
                for key in (
                    "proof_id",
                    "proof_sha256",
                    "prior_image",
                    "candidate_image",
                    "source_sha",
                    "qualification_run_id",
                )
            )
            and rehearsal["live_baseline"] == self.proof["live_deployment"],
            "rehearsal_receipt_mismatch",
        )
        live, prior, policies = self.observe(self.candidate, self.prior)
        result["observed_candidate"] = version(live)
        require(version(live)[1] != rehearsal["live_baseline"][1], "live_candidate_not_persisted")
        require(
            version(prior) == rehearsal["isolated_restored"] and policies == rehearsal["admission_versions"],
            "rehearsed_baseline_or_policy_changed",
        )
        result["stage"] = "server_dry_run_exact_live_inverse"
        reverse = self.live.transition(live, self.candidate, self.prior)
        require(comparable(reverse) == comparable(prior), "live_inverse_differs_from_rehearsal")
        self.recheck(live, prior, policies)


def read_json(path):
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("rehearse", "verify-inverse"))
    parser.add_argument("--proof", type=Path, required=True, help="Release-approved evidence and object bindings")
    parser.add_argument("--live-kubeconfig", type=Path, required=True)
    parser.add_argument("--live-context", required=True)
    parser.add_argument("--isolated-kubeconfig", type=Path, required=True)
    parser.add_argument("--isolated-context", required=True)
    parser.add_argument("--rehearsal-receipt", type=Path)
    args = parser.parse_args()
    if (args.mode == "verify-inverse") != (args.rehearsal_receipt is not None):
        parser.error("--rehearsal-receipt is required only for verify-inverse")

    result = {"schema": 1, "mode": args.mode, "status": "REFUSED", "stage": "read_proof"}
    try:
        proof = read_json(args.proof)
        rehearsal = Rehearsal(
            Cluster(args.live_kubeconfig, args.live_context),
            Cluster(args.isolated_kubeconfig, args.isolated_context, isolated=True),
            proof,
        )
        # Bind the Release evidence packet, which carries identities and evidence IDs, never runtime values.
        proof_sha = hashlib.sha256(json.dumps(proof, sort_keys=True).encode()).hexdigest()
        result.update(
            proof_id=proof["id"],
            proof_sha256=proof_sha,
            **{
                key: proof[key]
                for key in (
                    "prior_image",
                    "candidate_image",
                    "source_sha",
                    "qualification_run_id",
                )
            },
        )
        if args.mode == "rehearse":
            result["stage"] = "verify_provenance"
            check_provenance(proof)
            rehearsal.rehearse(result)
        else:
            rehearsal.verify_inverse(read_json(args.rehearsal_receipt), result)
        result.update(status="PASS", stage="complete")
    except Refused as error:
        result["reason"] = str(error)
    except (OSError, ValueError, KeyError, TypeError, AttributeError, IndexError, subprocess.TimeoutExpired):
        result["reason"] = "missing_invalid_or_unavailable_evidence"
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
