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
import socket
import subprocess
import sys
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import ProxyHandler, Request, build_opener

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
ADMISSION_RESOURCES = ADMISSION | {
    "mutatingadmissionpolicies.admissionregistration.k8s.io",
    "mutatingadmissionpolicybindings.admissionregistration.k8s.io",
}
DEPENDENCY_RESOURCES = {"configmap", "secret"}
STORAGE_METADATA = {"uid", "resourceVersion", "generation", "creationTimestamp", "managedFields"}
DEPLOYMENT_REVISION = "deployment.kubernetes.io/revision"


class Refused(Exception):
    """A categorical failure that is safe to include in a release receipt."""


def require(condition, reason):
    if not condition:
        raise Refused(reason)


def run(args, reason, *, stdin=None, timeout=120):
    result = subprocess.run(args, input=stdin, cwd=ROOT, capture_output=True, text=True, check=False, timeout=timeout)
    require(result.returncode == 0, reason)
    return result.stdout


def version(obj):
    if obj is None:
        return None
    metadata = obj["metadata"]
    result = [metadata["uid"], metadata["resourceVersion"]]
    require(all(isinstance(item, str) and item for item in result), "object_identity_missing")
    return result


def partial_metadata_version(response, name, namespace):
    # The request names only the PartialObjectMetadata media type, with no fallback, so an API
    # server that cannot honour it answers 406 rather than a full Secret. GKE (through
    # `kubectl proxy`) labels the metadata-only body plain `application/json`, dropping the
    # `as=` parameters (run 46027266977), so the header admits JSON and the body check below
    # decides: anything but a bare PartialObjectMetadata object is refused without echoing it.
    content_type = response.headers.get("Content-Type", "").lower().replace(" ", "")
    media_type, _, params = content_type.partition(";")
    require(
        media_type == "application/json"
        and (
            not params
            or ("as=partialobjectmetadata" in params and "g=meta.k8s.io" in params and "v=v1" in params)
        ),
        "secret_metadata_only_response_unavailable",
    )
    try:
        result = json.load(response)
    except (json.JSONDecodeError, UnicodeDecodeError):
        require(False, "secret_metadata_only_response_invalid")
    require(
        isinstance(result, dict)
        and result.get("apiVersion") == "meta.k8s.io/v1"
        and result.get("kind") == "PartialObjectMetadata"
        and set(result) <= {"apiVersion", "kind", "metadata"}
        and isinstance(result.get("metadata"), dict),
        "secret_metadata_only_response_invalid",
    )
    metadata = result["metadata"]
    require(
        metadata.get("name") == name and metadata.get("namespace") == namespace, "secret_metadata_identity_mismatch"
    )
    return version(result)


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


def post_move_baseline(isolated, live, prior_image):
    expected = with_image(isolated, prior_image)
    revisions = []
    for deployment in (isolated, live):
        annotation = deployment["metadata"].get("annotations", {}).get(DEPLOYMENT_REVISION)
        if annotation is None:
            revisions.append(0)
        else:
            require(re.fullmatch(r"[1-9][0-9]{0,18}", annotation), "invalid_deployment_revision")
            revision = int(annotation)
            require(revision < 2**63, "invalid_deployment_revision")
            revisions.append(revision)
    baseline_revision, live_revision = revisions
    require(live_revision >= baseline_revision, "deployment_revision_regressed")
    if live_revision > baseline_revision:
        # The live controller can advance this annotation after the image move.
        # The isolated API server has no Deployment controller.
        expected["metadata"].setdefault("annotations", {})[DEPLOYMENT_REVISION] = str(live_revision)
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

    def secret_version(self, name, *, namespace, optional=False):
        """Read only Secret identity through Kubernetes PartialObjectMetadata negotiation."""
        require(NAME.fullmatch(name) and NAME.fullmatch(namespace), "invalid_dependency_inventory")
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]

        proxy = None
        try:
            proxy = subprocess.Popen(
                [*self.command, "proxy", "--address=127.0.0.1", f"--port={port}"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            deadline = time.monotonic() + 10
            while True:
                require(proxy.poll() is None, "secret_metadata_proxy_unavailable")
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                        break
                except OSError:
                    require(time.monotonic() < deadline, "secret_metadata_proxy_unavailable")
                    time.sleep(0.05)

            path = f"/api/v1/namespaces/{quote(namespace, safe='')}/secrets/{quote(name, safe='')}"
            request = Request(
                f"http://127.0.0.1:{port}{path}",
                headers={"Accept": "application/json;as=PartialObjectMetadata;g=meta.k8s.io;v=v1"},
            )
            try:
                opener = build_opener(ProxyHandler({}))
                with opener.open(request, timeout=30) as response:
                    return partial_metadata_version(response, name, namespace)
            except HTTPError as error:
                if optional and error.code == 404:
                    return None
                raise Refused("secret_metadata_read_failed") from None
            except (OSError, URLError, TimeoutError):
                raise Refused("secret_metadata_read_failed") from None
        except OSError:
            raise Refused("secret_metadata_proxy_unavailable") from None
        finally:
            if proxy is not None:
                try:
                    if proxy.poll() is None:
                        proxy.terminate()
                    proxy.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proxy.kill()
                    proxy.wait()
                except OSError:
                    pass

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
        return self._submit_image_patch(obj, expected, desired, dry_run=dry_run, allow_same=allow_same)

    def _submit_image_patch(self, obj, expected, desired, *, dry_run, allow_same=False):
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
            reason="server_dry_run_rejected" if dry_run else self.patch_failure_reason,
            stdin=json.dumps(patch),
        )
        require(
            admitted["metadata"]["uid"] == version(obj)[0] and comparable(admitted) == with_image(obj, desired),
            "admission_changed_more_than_image",
        )
        return admitted

    patch_failure_reason = "isolated_patch_failed_reconcile_before_retry"


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
    admission_resources = proof["extra_admission_resources"]
    require(
        isinstance(admission_resources, list)
        and all(isinstance(resource, str) and resource in ADMISSION_RESOURCES for resource in admission_resources)
        and len(set(admission_resources)) == len(admission_resources),
        "invalid_admission_inventory",
    )
    dependencies = proof["live_dependencies"]
    require(
        isinstance(dependencies, list)
        and all(
            isinstance(item, dict)
            and set(item) == {"resource", "name", "version"}
            and isinstance(item["resource"], str)
            and item["resource"] in DEPENDENCY_RESOURCES
            and isinstance(item["name"], str)
            and NAME.fullmatch(item["name"])
            and (
                item["version"] is None
                or isinstance(item["version"], list)
                and len(item["version"]) == 2
                and all(isinstance(part, str) and part for part in item["version"])
            )
            for item in dependencies
        )
        and len({(item["resource"], item["name"]) for item in dependencies}) == len(dependencies),
        "invalid_dependency_inventory",
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
        qualification_receipt = read_json(artifacts / "pusher-dev-deployment-receipt.json")

    for image in (f"{dev_repository}@{digest}", candidate, proof["prior_image"]):
        remote_digest = run(
            ["gcloud", "container", "images", "describe", image, "--format=value(image_summary.digest)"],
            "registry_digest_unavailable",
        ).strip()
        require(remote_digest == image.split("@")[1], "registry_digest_mismatch")
    return qualification_receipt


def read_admission(cluster, reviewed_resources):
    require(
        isinstance(reviewed_resources, list)
        and all(isinstance(resource, str) and resource in ADMISSION_RESOURCES for resource in reviewed_resources)
        and len(set(reviewed_resources)) == len(reviewed_resources),
        "invalid_admission_inventory",
    )
    namespace = cluster.get("namespace", NAMESPACE)
    policies = {}
    versions = [version(namespace)]
    discovered = cluster.admission_resources()
    require(ADMISSION <= discovered, "mandatory_admission_api_unavailable")
    require(discovered <= ADMISSION_RESOURCES and set(reviewed_resources) <= discovered, "invalid_admission_inventory")
    for resource in sorted(discovered):
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

    def observe(self, expected_live, expected_isolated, *, post_move=False):
        validate_proof(self.proof)
        live, isolated = self.live.deployment(), self.isolated.deployment()
        require(version(live)[0] == self.proof["live_deployment"][0], "live_uid_changed")
        require(version(isolated)[0] == self.proof["isolated_deployment"][0], "isolated_uid_changed")
        require(version(live)[0] != version(isolated)[0], "isolation_not_distinct")
        require(
            current_image(live) == expected_live and current_image(isolated) == expected_isolated,
            "observed_image_changed",
        )
        expected = post_move_baseline(isolated, live, self.prior) if post_move else with_image(isolated, self.prior)
        require(with_image(live, self.prior) == expected, "deployment_baseline_differs")

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
                kind in DEPENDENCY_RESOURCES and NAME.fullmatch(name) and (kind, name) not in expected,
                "invalid_dependency_inventory",
            )
            expected[kind, name] = item["version"]
        references = list(config_references(live["spec"]["template"]["spec"]))
        refs = {ref for ref, _ in references}
        require(
            SHARED in refs and refs == expected.keys() and expected[SHARED] is not None,
            "dependency_inventory_mismatch",
        )
        require(
            all(optional or expected[ref] is not None for ref, optional in references),
            "required_dependency_absent",
        )
        for (kind, name), identity_version in sorted(expected.items()):
            if kind == "secret":
                actual_version = self.live.secret_version(name, namespace=NAMESPACE, optional=True)
            else:
                actual_version = version(self.live.get(kind, name, namespace=NAMESPACE, optional=True))
            require(actual_version == identity_version, "live_dependency_changed")
        validate_proof(self.proof)
        return live, isolated, [live_versions, isolated_versions]

    def recheck(self, live, isolated, policies, *, post_move=False):
        fresh_live, fresh_isolated, fresh_policies = self.observe(
            current_image(live), current_image(isolated), post_move=post_move
        )
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
        self.check_receipt(rehearsal, result)
        live, prior, policies = self.observe(self.candidate, self.prior, post_move=True)
        result["observed_candidate"] = version(live)
        require(version(live)[1] != rehearsal["live_baseline"][1], "live_candidate_not_persisted")
        self.check_rehearsed_state(rehearsal, prior, policies)
        result["stage"] = "server_dry_run_exact_live_inverse"
        reverse = self.live.transition(live, self.candidate, self.prior)
        require(
            comparable(reverse) == post_move_baseline(prior, live, self.prior), "live_inverse_differs_from_rehearsal"
        )
        self.recheck(live, prior, policies, post_move=True)
        return live, prior, policies

    def check_receipt(self, rehearsal, result):
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

    def check_rehearsed_state(self, rehearsal, prior, policies):
        require(
            version(prior) == rehearsal["isolated_restored"] and policies == rehearsal["admission_versions"],
            "rehearsed_baseline_or_policy_changed",
        )


def read_json(path):
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def proof_receipt_fields(proof):
    # The proof carries identities and evidence IDs, never runtime values.
    return {
        "proof_id": proof["id"],
        "proof_sha256": hashlib.sha256(json.dumps(proof, sort_keys=True).encode()).hexdigest(),
        **{key: proof[key] for key in ("prior_image", "candidate_image", "source_sha", "qualification_run_id")},
    }


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
        result.update(proof_receipt_fields(proof))
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
