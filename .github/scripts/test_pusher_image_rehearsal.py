#!/usr/bin/env python3
"""Exercise the production rehearsal orchestration with a conditional API fake."""

import copy
from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import pusher_image_rehearsal as helper

PRIOR = "gcr.io/based-hardware/pusher@sha256:" + "1" * 64
CANDIDATE = "gcr.io/based-hardware/backend-pusher@sha256:" + "2" * 64
ACTOR = {"username": "release", "groups": ["release", "system:authenticated"]}


def metadata(name, uid, namespace=None):
    value = {"name": name, "uid": uid, "resourceVersion": "1", "labels": {"admit": "pusher"}}
    if namespace:
        value["namespace"] = namespace
    return value


class Server(helper.Cluster):
    def __init__(self, cluster):
        super().__init__(Path(cluster), cluster, isolated=cluster == "isolated")
        self.cluster = cluster
        self.actor = ACTOR
        self.requests = []
        self.read_requests = []
        self.secret_metadata_reads = []
        self.full_secret_reads = 0
        self.secret_versions = {}
        self.after_request = lambda: None
        self.admit = lambda old, new, dry: None
        self.resources = set(helper.ADMISSION) | {
            "mutatingadmissionpolicies.admissionregistration.k8s.io",
            "mutatingadmissionpolicybindings.admissionregistration.k8s.io",
        }
        self.namespace = {"metadata": metadata(helper.NAMESPACE, f"ns-{cluster}")}
        self.config = {"metadata": metadata(helper.SHARED[1], f"map-{cluster}"), "data": {"PRIVATE": "fake-value"}}
        self.webhook = {
            "metadata": metadata("pusher-admission", f"webhook-{cluster}"),
            "webhooks": [
                {
                    "name": "check.example.test",
                    "rules": [{"operations": ["UPDATE"], "resources": ["deployments"]}],
                    "namespaceSelector": {"matchLabels": {"admit": "pusher"}},
                    "objectSelector": {"matchLabels": {"admit": "pusher"}},
                    "matchConditions": [{"name": "release", "expression": 'request.userInfo.username == "release"'}],
                    "failurePolicy": "Fail",
                }
            ],
        }
        self.target = {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": metadata(helper.TARGET, f"target-{cluster}", helper.NAMESPACE),
            "spec": {
                "selector": {"matchLabels": {"app": "pusher"}},
                "template": {
                    "metadata": {"labels": {"app": "pusher"}},
                    "spec": {
                        "containers": [
                            {"name": "sidecar", "image": "sidecar"},
                            {
                                "name": "pusher",
                                "image": PRIOR,
                                "envFrom": [{"configMapRef": {"name": helper.SHARED[1]}}],
                                "env": [
                                    {"name": "PUSHER_PRIVACY_MEMO", "value": "false"},
                                    {
                                        "name": "OPTIONAL",
                                        "valueFrom": {
                                            "secretKeyRef": {
                                                "name": "absent-secret",
                                                "key": "lease",
                                                "optional": True,
                                            }
                                        },
                                    },
                                    {"name": "EMPTY", "value": ""},
                                ],
                            },
                        ],
                        "volumes": [
                            {
                                "name": "shared",
                                "projected": {
                                    "sources": [
                                        {"configMap": {"name": helper.SHARED[1]}},
                                    ]
                                },
                            }
                        ],
                    },
                },
            },
        }

    def server(self):
        return f"https://{self.cluster}.example.test"

    def identity(self):
        return copy.deepcopy(self.actor)

    def api_version(self):
        return "v1.34.2"

    def admission_resources(self):
        return set(self.resources)

    def get(self, resource, name=None, *, namespace=None, optional=False):
        self.read_requests.append((resource, name, namespace, optional))
        if resource == "secret":
            self.full_secret_reads += 1
        if resource == "deployment.apps":
            return copy.deepcopy(self.target)
        if resource == "namespace":
            return copy.deepcopy(self.namespace)
        if resource == "configmap":
            return copy.deepcopy(self.config)
        if resource == "secret" and optional:
            return None
        items = [self.webhook] if resource == "validatingwebhookconfigurations.admissionregistration.k8s.io" else []
        return {"metadata": {}, "items": copy.deepcopy(items)}

    def secret_version(self, name, *, namespace, optional=False):
        self.secret_metadata_reads.append((name, namespace, optional))
        return self.secret_versions.get(name)

    def call(self, *args, reason, stdin):
        # Kubernetes applies each JSON Patch test to the stored object. Dry-run
        # executes admission over oldObject/object and leaves storage untouched.
        assert args[:3] == ("patch", "deployment.apps", helper.TARGET)
        assert args[3:7] == ("--namespace", helper.NAMESPACE, "--type=json", "--patch-file=/dev/stdin")
        dry = args[7] == "--dry-run=server"
        assert dry or args[7] == "--dry-run=none"
        operations = json.loads(stdin)
        self.requests.append((dry, operations))
        result = copy.deepcopy(self.target)
        for op in operations:
            parent = result
            *keys, key = op["path"].strip("/").split("/")
            for part in keys:
                parent = parent[int(part)] if isinstance(parent, list) else parent[part]
            if op["op"] == "test":
                helper.require(parent[key] == op["value"], reason)
            else:
                assert op["op"] == "replace"
                parent[key] = op["value"]
        self.admit(self.target, result, dry)
        if not dry:
            result["metadata"]["resourceVersion"] = str(int(result["metadata"]["resourceVersion"]) + 1)
            self.target = copy.deepcopy(result)
        self.after_request()
        return result


class RehearsalTest(unittest.TestCase):
    def setUp(self):
        self.live, self.isolated = Server("live"), Server("isolated")
        self.proof = {
            "schema": 1,
            "id": "test-proof",
            "evidence": {
                "admission_and_isolation": "admission-1",
                "effective_startup_inputs": "inputs-1",
                "shared_consumer_inventory": "consumers-1",
                "writer_exclusion": "fence-1",
            },
            "valid_until": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
            "prior_image": PRIOR,
            "candidate_image": CANDIDATE,
            "source_sha": "3" * 40,
            "qualification_run_id": 10,
            "effective_user": ACTOR,
            "server_urls": [self.live.server(), self.isolated.server()],
            "live_deployment": helper.version(self.live.target),
            "isolated_deployment": helper.version(self.isolated.target),
            "namespace_uids": [helper.version(server.namespace)[0] for server in (self.live, self.isolated)],
            "extra_admission_resources": [],
            "live_dependencies": [
                {"resource": helper.SHARED[0], "name": helper.SHARED[1], "version": helper.version(self.live.config)},
                {"resource": "secret", "name": "absent-secret", "version": None},
            ],
        }
        self.rehearsal = helper.Rehearsal(self.live, self.isolated, self.proof)

    def result(self, mode):
        return {
            "mode": mode,
            "proof_id": self.proof["id"],
            "proof_sha256": "4" * 64,
            **{
                key: self.proof[key] for key in ("source_sha", "qualification_run_id", "prior_image", "candidate_image")
            },
        }

    def test_forward_real_inverse_and_immediate_live_preview(self):
        seen = []
        for cluster in (self.live, self.isolated):
            cluster.target["metadata"]["annotations"] = {helper.DEPLOYMENT_REVISION: "7"}

        def observe(old, new, dry):
            if helper.current_image(old) == CANDIDATE and helper.current_image(new) == PRIOR:
                seen.append((old["metadata"]["uid"], old["metadata"]["resourceVersion"], dry))

        self.isolated.admit = self.live.admit = observe
        prior = copy.deepcopy(self.live.target)
        config = copy.deepcopy(self.live.config)
        result = self.result("rehearse")
        self.rehearsal.rehearse(result)
        result["status"] = "PASS"
        self.assertEqual(self.live.target, prior)
        self.assertEqual(self.live.config, config)
        self.assertEqual(helper.comparable(self.isolated.target), helper.comparable(prior))
        self.assertEqual([dry for dry, _ in self.isolated.requests], [True, False, True, False])
        self.assertEqual([dry for dry, _ in self.live.requests], [True, True])
        self.assertEqual(len(seen), 2)
        inverse = self.isolated.requests[2][1]
        self.assertEqual(
            inverse,
            [
                {"op": "test", "path": "/metadata/uid", "value": "target-isolated"},
                {"op": "test", "path": "/metadata/resourceVersion", "value": "2"},
                {"op": "test", "path": "/spec/template/spec/containers/1/name", "value": "pusher"},
                {"op": "test", "path": "/spec/template/spec/containers/1/image", "value": CANDIDATE},
                {"op": "replace", "path": "/spec/template/spec/containers/1/image", "value": PRIOR},
            ],
        )
        self.assertNotIn("fake-value", json.dumps(result))
        self.assertNotIn("PUSHER_PRIVACY_MEMO", json.dumps(result))
        # Simulate a separately authorized Release move. The helper has no live write command.
        self.live.target["spec"] = helper.with_image(prior, CANDIDATE)["spec"]
        self.live.target["metadata"]["resourceVersion"] = "34"
        self.live.target["metadata"]["annotations"][helper.DEPLOYMENT_REVISION] = "8"
        after = self.result("verify-inverse")
        self.rehearsal.verify_inverse(result, after)
        self.assertEqual(seen[-1], ("target-live", "34", True))
        self.assertEqual(self.live.requests[-1][1], helper.guarded_patch(self.live.target, CANDIDATE, PRIOR))
        self.assertEqual(self.live.target["metadata"]["annotations"][helper.DEPLOYMENT_REVISION], "8")
        self.assertEqual(self.live.config, config)
        self.assertEqual(helper.current_image(self.live.target), CANDIDATE)
        self.assertTrue(all(dry for dry, _ in self.live.requests))

    def test_post_move_revision_exception_refuses_drift_and_admission_rewrites(self):
        for cluster in (self.live, self.isolated):
            cluster.target["metadata"]["annotations"] = {helper.DEPLOYMENT_REVISION: "7", "fixture": "preserved"}
        result = self.result("rehearse")
        self.rehearsal.rehearse(result)
        result["status"] = "PASS"
        self.live.target["spec"] = helper.with_image(self.live.target, CANDIDATE)["spec"]
        self.live.target["metadata"]["resourceVersion"] = "34"
        candidate = copy.deepcopy(self.live.target)
        requests_before = len(self.live.requests)
        for revision, other_annotation, reason in (
            ("6", "preserved", "deployment_revision_regressed"),
            (None, "preserved", "deployment_revision_regressed"),
            ("invalid", "preserved", "invalid_deployment_revision"),
            ("8", "changed", "deployment_baseline_differs"),
        ):
            with self.subTest(revision=revision, other_annotation=other_annotation):
                self.live.target = copy.deepcopy(candidate)
                annotations = self.live.target["metadata"]["annotations"]
                if revision is None:
                    del annotations[helper.DEPLOYMENT_REVISION]
                else:
                    annotations[helper.DEPLOYMENT_REVISION] = revision
                annotations["fixture"] = other_annotation
                with self.assertRaisesRegex(helper.Refused, reason):
                    self.rehearsal.verify_inverse(result, self.result("verify-inverse"))
                self.assertEqual(len(self.live.requests), requests_before)

        self.live.target = copy.deepcopy(candidate)
        self.live.target["metadata"]["annotations"][helper.DEPLOYMENT_REVISION] = "8"

        def rewrite_revision(old, new, dry):
            new["metadata"]["annotations"][helper.DEPLOYMENT_REVISION] = "9"

        self.live.admit = rewrite_revision
        with self.assertRaisesRegex(helper.Refused, "admission_changed_more_than_image"):
            self.rehearsal.verify_inverse(result, self.result("verify-inverse"))

    def test_refuses_different_identity_selectors_and_policy_discovery(self):
        split = [
            (lambda: setattr(self.isolated, "actor", {**ACTOR, "groups": ["other"]}), "effective_identity_differs"),
            (lambda: self.isolated.namespace["metadata"]["labels"].clear(), "admission_configuration_differs"),
            (
                lambda: self.isolated.webhook["webhooks"][0]["matchConditions"].clear(),
                "admission_configuration_differs",
            ),
            (
                lambda: self.isolated.resources.remove("mutatingadmissionpolicies.admissionregistration.k8s.io"),
                "admission_configuration_differs",
            ),
        ]
        for mutate, reason in split:
            with self.subTest(reason=reason):
                self.setUp()
                mutate()
                with self.assertRaisesRegex(helper.Refused, reason):
                    self.rehearsal.rehearse(self.result("rehearse"))
                self.assertEqual(self.isolated.requests, [])

    def test_refuses_inverse_admission_mutation(self):
        def mutate(old, new, dry):
            if helper.current_image(old) == CANDIDATE and helper.current_image(new) == PRIOR:
                new["spec"]["template"]["spec"]["containers"][1]["envFrom"].clear()

        self.isolated.admit = mutate
        with self.assertRaisesRegex(helper.Refused, "admission_changed_more_than_image"):
            self.rehearsal.rehearse(self.result("rehearse"))
        self.assertEqual(helper.current_image(self.isolated.target), CANDIDATE)
        self.assertEqual(helper.current_image(self.live.target), PRIOR)

    def test_refuses_live_dependency_or_object_change_before_first_write(self):
        for item, reason in (
            (self.live.config, "live_dependency_changed"),
            (self.live.target, "server_dry_run_rejected"),
        ):
            with self.subTest(reason=reason):
                self.live.after_request = lambda: item["metadata"].update(resourceVersion="20")
                with self.assertRaisesRegex(helper.Refused, reason):
                    self.rehearsal.rehearse(self.result("rehearse"))
                item["metadata"]["resourceVersion"] = "1"
                self.assertTrue(all(dry for dry, _ in self.isolated.requests))

    def test_secret_dependency_reads_only_metadata_identity(self):
        self.rehearsal.rehearse(self.result("rehearse"))
        self.assertGreater(self.live.secret_metadata_reads.count(("absent-secret", helper.NAMESPACE, True)), 0)
        self.assertEqual(self.live.full_secret_reads, 0)

    def test_refuses_unreferenced_dependency_before_reading_it(self):
        self.proof["live_dependencies"].append({"resource": "secret", "name": "unused-secret", "version": None})
        with self.assertRaisesRegex(helper.Refused, "dependency_inventory_mismatch"):
            self.rehearsal.observe(PRIOR, PRIOR)
        self.assertEqual(self.live.secret_metadata_reads, [])
        self.assertEqual(self.live.full_secret_reads, 0)

    def test_rejects_unsupported_dependency_and_admission_resources_before_reads(self):
        self.proof["live_dependencies"][0]["resource"] = "pods"
        with self.assertRaisesRegex(helper.Refused, "invalid_dependency_inventory"):
            helper.Rehearsal(self.live, self.isolated, self.proof)
        self.assertEqual(self.live.read_requests, [])

        self.proof["live_dependencies"][0]["resource"] = helper.SHARED[0]
        self.proof["extra_admission_resources"] = ["secrets"]
        with self.assertRaisesRegex(helper.Refused, "invalid_admission_inventory"):
            helper.Rehearsal(self.live, self.isolated, self.proof)
        self.assertEqual(self.live.read_requests, [])

    def test_partial_metadata_response_returns_identity_without_secret_data(self):
        payload = {
            "apiVersion": "meta.k8s.io/v1",
            "kind": "PartialObjectMetadata",
            "metadata": {
                "name": "secret",
                "namespace": helper.NAMESPACE,
                "uid": "secret-uid",
                "resourceVersion": "9",
            },
        }

        class Response(io.BytesIO):
            headers = {"Content-Type": "application/json;as=PartialObjectMetadata;g=meta.k8s.io;v=v1"}

        response = Response(json.dumps(payload).encode())
        self.assertEqual(helper.partial_metadata_version(response, "secret", helper.NAMESPACE), ["secret-uid", "9"])

        class FullSecretResponse:
            headers = {"Content-Type": "application/json"}

            def read(self, *_args):
                raise AssertionError("a full Secret response must not be read")

        with self.assertRaisesRegex(helper.Refused, "secret_metadata_only_response_unavailable"):
            helper.partial_metadata_version(FullSecretResponse(), "secret", helper.NAMESPACE)

    def test_secret_version_uses_partial_metadata_request_and_closes_proxy(self):
        class Listener:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def bind(self, _address):
                pass

            def getsockname(self):
                return "127.0.0.1", 32123

        class Connection:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

        class Proxy:
            terminated = False

            def poll(self):
                return 0 if self.terminated else None

            def terminate(self):
                self.terminated = True

            def wait(self, timeout=None):
                return 0

        class Response(io.BytesIO):
            headers = {"Content-Type": "application/json;as=PartialObjectMetadata;g=meta.k8s.io;v=v1"}

        response = Response(
            json.dumps(
                {
                    "apiVersion": "meta.k8s.io/v1",
                    "kind": "PartialObjectMetadata",
                    "metadata": {
                        "name": "private-token",
                        "namespace": helper.NAMESPACE,
                        "uid": "secret-uid",
                        "resourceVersion": "9",
                    },
                }
            ).encode()
        )

        class Opener:
            def open(self, _request, timeout):
                self.timeout = timeout
                self.request = _request
                return response

        opener = Opener()
        proxy = Proxy()
        with (
            patch.object(helper.socket, "socket", return_value=Listener()),
            patch.object(helper.socket, "create_connection", return_value=Connection()),
            patch.object(helper.subprocess, "Popen", return_value=proxy) as start_proxy,
            patch.object(helper, "build_opener", return_value=opener),
            patch.object(helper, "ProxyHandler") as proxy_handler,
        ):
            identity = helper.Cluster(Path("fixture-kubeconfig"), "prod").secret_version(
                "private-token", namespace=helper.NAMESPACE
            )

        self.assertEqual(identity, ["secret-uid", "9"])
        self.assertIn("proxy", start_proxy.call_args.args[0])
        proxy_handler.assert_called_once_with({})
        sent_request = opener.request
        self.assertEqual(
            sent_request.get_header("Accept"),
            "application/json;as=PartialObjectMetadata;g=meta.k8s.io;v=v1",
        )
        self.assertTrue(sent_request.full_url.endswith(f"/api/v1/namespaces/{helper.NAMESPACE}/secrets/private-token"))
        self.assertTrue(proxy.terminated)

    def test_rejects_conflict_and_production_write_at_api_boundary(self):
        snapshot = copy.deepcopy(self.isolated.target)
        self.isolated.target["metadata"]["resourceVersion"] = "88"
        with self.assertRaisesRegex(helper.Refused, "isolated_patch_failed"):
            self.isolated.transition(snapshot, PRIOR, CANDIDATE, dry_run=False)
        with self.assertRaisesRegex(helper.Refused, "production_write_refused"):
            self.live.transition(self.live.target, PRIOR, CANDIDATE, dry_run=False)
        self.assertEqual(self.live.requests, [])

    def test_refuses_absent_required_dependency(self):
        for cluster in (self.live, self.isolated):
            container = cluster.target["spec"]["template"]["spec"]["containers"][1]
            container["env"][1]["valueFrom"]["secretKeyRef"]["optional"] = False
        with self.assertRaisesRegex(helper.Refused, "required_dependency_absent"):
            self.rehearsal.rehearse(self.result("rehearse"))
        self.assertEqual(self.live.requests, [])
        self.assertEqual(self.isolated.requests, [])

    def test_failed_exact_live_inverse_leaves_candidate_and_refuses(self):
        result = self.result("rehearse")
        self.rehearsal.rehearse(result)
        result["status"] = "PASS"
        self.live.target["spec"] = helper.with_image(self.live.target, CANDIDATE)["spec"]
        self.live.target["metadata"]["resourceVersion"] = "9"
        self.live.admit = lambda old, new, dry: helper.require(False, "blocked_by_webhook")
        after = self.result("verify-inverse")
        with self.assertRaisesRegex(helper.Refused, "blocked_by_webhook"):
            self.rehearsal.verify_inverse(result, after)
        self.assertEqual(after["stage"], "server_dry_run_exact_live_inverse")
        self.assertEqual(after["observed_candidate"], ["target-live", "9"])
        self.assertEqual(helper.current_image(self.live.target), CANDIDATE)
        self.assertTrue(all(dry for dry, _ in self.live.requests))

    def test_failed_provenance_emits_a_redacted_receipt_and_uses_no_cluster(self):
        args = [
            "script",
            "rehearse",
            "--proof",
            "packet",
            "--live-kubeconfig",
            "live",
            "--live-context",
            "live",
            "--isolated-kubeconfig",
            "rehearsal",
            "--isolated-context",
            "isolated",
        ]
        with (
            patch.object(helper.sys, "argv", args),
            patch.object(helper, "read_json", return_value=self.proof),
            patch.object(helper, "check_provenance", side_effect=helper.Refused("registry_digest_mismatch")),
            patch.object(helper.Cluster, "call", side_effect=AssertionError("unexpected Kubernetes request")),
            patch("builtins.print") as output,
        ):
            self.assertEqual(helper.main(), 1)
        receipt = json.loads(output.call_args.args[0])
        self.assertEqual(receipt["status"], "REFUSED")
        self.assertEqual(receipt["stage"], "verify_provenance")
        self.assertEqual(receipt["reason"], "registry_digest_mismatch")
        self.assertNotIn("effective_user", receipt)

    def test_provenance_checks_qualified_repository_source_run_and_registry_parity(self):
        source = self.proof["source_sha"]
        main = "4" * 40
        prod_repo, digest = CANDIDATE.split("@")
        dev_repo = "gcr.io/based-hardware-dev/backend-pusher"
        seen = []

        def command(args, reason):
            seen.append((args, reason))
            if reason == "fresh_main_unavailable":
                return main
            if reason == "qualification_run_unavailable":
                return '{"head_repository":{"full_name":"BasedHardware/omi"}}'
            if reason == "source_closure_unavailable":
                return "backend/pusher\nbackend/charts/pusher\n"
            if reason == "qualification_workflow_unavailable":
                return "18"
            if reason == "qualification_artifact_unavailable":
                path = Path(args[args.index("--dir") + 1])
                path.mkdir()
                (path / "pusher-dev-deployment-receipt.json").write_text('{"receipt": "qualified"}', encoding="utf-8")
            if reason == "registry_digest_unavailable":
                return args[4].split("@")[1]
            return ""

        with patch.object(helper, "run", side_effect=command):
            self.assertEqual(helper.check_provenance(self.proof), {"receipt": "qualified"})

        commands = {reason: args for args, reason in seen}
        self.assertIn(f"head_sha={source}", commands["release_eligibility_unavailable"][2])
        self.assertIn("--require-first-attempt", commands["source_admission_failed"])
        self.assertEqual(commands["source_not_merged"][-2:], [source, main])
        self.assertEqual(
            commands["source_or_chart_closure_changed"][-5:],
            [
                source,
                main,
                "--",
                "backend/pusher",
                "backend/charts/pusher",
            ],
        )
        verifier = commands["development_qualification_failed"]
        for flag, value in {
            "--expected-repository": dev_repo,
            "--expected-digest": digest,
            "--expected-qualification-source-sha": source,
            "--expected-workflow-id": "18",
            "--expected-run-id": "10",
        }.items():
            self.assertEqual(verifier[verifier.index(flag) + 1], value)
        self.assertEqual(
            [args[4] for args, reason in seen if reason == "registry_digest_unavailable"],
            [
                f"{dev_repo}@{digest}",
                f"{prod_repo}@{digest}",
                PRIOR,
            ],
        )


if __name__ == "__main__":
    unittest.main()
