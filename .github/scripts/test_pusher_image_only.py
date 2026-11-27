#!/usr/bin/env python3
"""Check the live-admission image-only control path against a guarded cluster fake."""

import copy
import json
import os
from pathlib import Path
import re
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import pusher_image_only as control
import pusher_image_rehearsal as helper

SOURCE = "3" * 40
WORKFLOW_SHA = "a" * 40
REPO, DIGEST = ("gcr.io/based-hardware/pusher", "sha256:" + "b" * 64)
CANDIDATE = f"{REPO}@{DIGEST}"
CANARY_RUN = 42
REAL_STATUS_REPORT = control.deploy_status_report


def resolve(obj, path):
    current = obj
    for part in path.strip("/").split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        current = current[int(part)] if isinstance(current, list) else current[part]
    return current


def assign(obj, path, value):
    parts = path.strip("/").replace("~1", "/").replace("~0", "~").split("/")
    parent = obj
    for part in parts[:-1]:
        parent = parent[int(part)] if isinstance(parent, list) else parent[part]
    key = parts[-1]
    if isinstance(parent, list):
        parent[int(key)] = value
    else:
        parent[key] = value


class FakeLive:
    """The production surface pusher_image_only reads, with a guarded patch."""

    command = ("kubectl",)

    def __init__(self, image=control.BASELINE):
        self.target = {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {
                "name": control.TARGET,
                "namespace": control.NAMESPACE,
                "uid": "deploy-uid",
                "resourceVersion": "11",
                "generation": 3,
            },
            "spec": {
                "replicas": 3,
                "template": {
                    "spec": {
                        "containers": [
                            {"name": "sidecar", "image": "gcr.io/based-hardware/sidecar@sha256:" + "c" * 64},
                            {"name": "pusher", "image": image},
                        ],
                        "env": [{"name": "X", "valueFrom": {"configMapKeyRef": {"name": "prod-omi-backend-config", "key": "Y"}}}],
                    }
                },
            },
            "status": {"updatedReplicas": 3},
        }
        self.namespace = {"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": control.NAMESPACE, "uid": "ns-uid", "resourceVersion": "4"}}
        self.admission = {
            resource: {"items": [{"apiVersion": "x", "kind": "Y", "metadata": {"name": f"policy-{index}"}}]}
            for index, resource in enumerate(sorted(helper.ADMISSION | {"mutatingadmissionpolicies.admissionregistration.k8s.io", "mutatingadmissionpolicybindings.admissionregistration.k8s.io"}))
        }
        self.requests = []
        self.admit = None
        self.policy_resource_version = "5"

    # Membership object surface ------------------------------------------------
    def deployment(self, name=control.TARGET):
        return copy.deepcopy(self.target)

    def identity(self):
        return {"username": "omi-ci-deployer-prod@based-hardware.iam.gserviceaccount.com"}

    def server(self):
        return "https://prod-cluster.example"

    def api_version(self):
        return "v1.32.1"

    def admission_resources(self):
        return set(self.admission)

    def secret_version(self, name, *, namespace, optional=False):
        self.requests.append((True, [{"op": "secret-version", "value": name}]))
        return ["secret-uid", "2"]

    def get(self, resource, name=None, *, namespace=None, optional=False):
        if resource == "deployment.apps":
            return copy.deepcopy(self.target) if name in (None, control.TARGET) else None
        if resource == "namespace":
            return copy.deepcopy(self.namespace)
        if resource == "configmap":
            return {"metadata": {"name": name, "uid": "configmap-uid", "resourceVersion": "1"}}
        if resource == "pods":
            return {"items": []}
        if resource in self.admission:
            return {
                "metadata": {},
                "items": [
                    {
                        **item,
                        "metadata": {**item["metadata"], "uid": f"{item['metadata']['name']}-uid", "resourceVersion": self.policy_resource_version},
                    }
                    for item in self.admission[resource]["items"]
                ],
            }
        if optional:
            return None
        raise AssertionError(f"unexpected read {resource}/{name}")

    def call(self, *args, reason="kubernetes_read_failed", stdin=None):
        if args[0] != "patch":
            raise AssertionError(f"unexpected call {args}")
        ops = json.loads(stdin)
        name = args[1]
        dry = "--dry-run=server" in args
        self.requests.append((dry, copy.deepcopy(ops)))
        if self.admit is not None:
            override = self.admit(self.target, ops, dry)
            if override is not None:
                return override
        changed = copy.deepcopy(self.target)
        for op in ops:
            if op["op"] == "test":
                if resolve(changed, op["path"]) != op["value"]:
                    raise helper.Refused(reason)
            elif op["op"] == "replace":
                assign(changed, op["path"], op["value"])
        if not dry:
            self.target = changed
        return changed


def live_patches(fake):
    return [ops for dry, ops in fake.requests if not dry and ops and ops[0]["op"] == "test"]


class ImageOnlyTest(unittest.TestCase):
    def setUp(self):
        self.fake = FakeLive()
        self.live = control.ReadOnlyCluster(self.fake)
        self.writer = control.LiveWriter(self.fake)
        self.packet = {
            "schema": 2,
            "mode": "preview",
            "source_sha": SOURCE,
            "prior_image": control.BASELINE,
            "candidate_image": CANDIDATE,
            "qualification_run_id": 10,
            "release_approval": "release-approval",
        }
        self.command = self.enterContext(patch.object(control, "run", return_value=""))
        self.enterContext(patch.object(control, "check_qualification", return_value={"qualified": True}))
        self.enterContext(patch.object(control, "verify_canary_cleanup"))
        self.enterContext(patch.object(control, "check_capacity"))
        self.preview = self.enterContext(patch.object(control, "check_reviewed_preview", return_value={"live_baseline": ["deploy-uid", "11"]}))
        self.canary = self.enterContext(
            patch.object(control, "check_canary", side_effect=lambda *args: args[1].update(canary_run_id=CANARY_RUN, canary_inverse_receipt="PASS"))
        )
        self.ready = self.enterContext(
            patch.object(
                control,
                "verify_ready",
                return_value={"deployment_uid": "deploy-uid", "generation": 3, "ready_replicas": 3},
            )
        )
        self.status_report = self.enterContext(patch.object(control, "deploy_status_report"))

    def result(self, mode):
        return {"mode": mode, "workflow_sha": WORKFLOW_SHA, "run_id": 100, **control.evidence_binding(self.packet)}

    def promote_packet(self):
        packet = dict(self.packet, mode="promote")
        packet["reviewed_preview"] = {"run_id": 41, "review_id": "review-41"}
        packet["canary"] = {
            "run_id": CANARY_RUN,
            "workflow_sha": "d" * 40,
            "preservation_review": {"id": "review-canary"},
        }
        return packet

    def test_preview_dry_runs_forward_and_baseline_self_and_requires_both_fixes(self):
        result = self.result("preview")
        control.execute("preview", self.packet, self.live, result)
        self.assertEqual([call.args[0][3] for call in self.command.call_args_list], list(control.REQUIRED_FIXES))
        self.assertEqual(result["forward_server_dry_run"], "PASS")
        self.assertEqual(result["live_baseline_server_dry_run"], "PASS")
        self.assertEqual(result["rollback_evidence"], "baseline_self_server_dry_run")
        self.assertEqual(self.fake.target, FakeLive().target)
        self.assertTrue(all(dry for dry, _ in self.fake.requests))
        self.assertIn("admission_sha256", result)
        self.assertIn("dependencies_sha256", result)

    def test_preview_path_cannot_reach_the_live_patch(self):
        self.assertFalse(hasattr(control.ReadOnlyCluster, "patch_image"))
        self.assertFalse(hasattr(control.ReadOnlyCluster, "apply_image"))
        with self.assertRaisesRegex(helper.Refused, "preview_write_refused"):
            self.live.call("patch", "deployment.apps", control.TARGET, "--dry-run=none", stdin="[]")
        with self.assertRaisesRegex(helper.Refused, "invalid_execution_binding"):
            control.execute("preview", self.packet, self.live, self.result("preview"), writer=self.writer)
        self.assertTrue(all(dry for dry, _ in self.fake.requests))

    def test_dependency_or_admission_drift_refuses_before_any_write(self):
        original = self.fake.get
        reads = {"admission": 0}

        def get(resource, name=None, **kwargs):
            value = original(resource, name, **kwargs)
            if resource in self.fake.admission:
                reads["admission"] += 1
                if reads["admission"] > 1:
                    value["items"][0]["metadata"]["name"] = "changed-policy"
            return value

        self.fake.get = get
        with self.assertRaisesRegex(helper.Refused, "state_changed_while_verifying"):
            control.execute("preview", self.packet, self.live, self.result("preview"))
        self.assertEqual(live_patches(self.fake), [])

    def test_promote_verifies_exact_live_inverse_then_rollback_restores_baseline(self):
        packet = self.promote_packet()
        forward = self.result("promote")
        control.execute("promote", packet, self.live, forward, writer=self.writer)
        self.assertEqual(forward["live_inverse_server_dry_run"], "PASS")
        self.assertEqual(forward["serving_image"], CANDIDATE)
        self.assertEqual(helper.current_image(self.fake.target), CANDIDATE)

        self.ready.reset_mock()
        self.command.return_value = control.BASELINE.split("@")[1]
        reverse = self.result("rollback")
        control.execute("rollback", packet, self.live, reverse, writer=self.writer)
        self.assertEqual(reverse["live_inverse_server_dry_run"], "PASS")
        self.assertEqual(reverse["serving_image"], control.BASELINE)
        self.assertEqual(helper.comparable(self.fake.target)["spec"], helper.comparable(FakeLive().target)["spec"])
        patches = live_patches(self.fake)
        self.assertEqual([ops[-1]["value"] for ops in patches], [CANDIDATE, control.BASELINE])
        self.assertTrue(all([op["op"] for op in ops] == ["test"] * 4 + ["replace"] for ops in patches))

    def test_refused_reverse_holds_and_makes_no_further_patches(self):
        def refuse_inverse(_old, ops, dry):
            if dry and ops[3]["value"] == CANDIDATE and ops[4]["value"] == control.BASELINE:
                raise helper.Refused("server_dry_run_rejected")
            return None

        self.fake.admit = refuse_inverse
        result = self.result("promote")
        with self.assertRaises(control.Hold):
            control.execute("promote", self.promote_packet(), self.live, result, writer=self.writer)
        self.assertEqual(result["reason"], "REFUSED_INVERSE")
        self.assertEqual(result["stage"], "hold_refused_inverse")
        self.assertEqual(result["serving_image_observed"], CANDIDATE)
        self.assertIn("prod-operator", result["manual_restore_path"])
        self.assertEqual(helper.current_image(self.fake.target), CANDIDATE)
        self.assertEqual(len(live_patches(self.fake)), 1)
        self.status_report.assert_called_once_with(strict=False)

    def test_canary_verifies_the_recorded_inverse_and_never_writes(self):
        packet = self.promote_packet()
        packet["mode"] = "canary"
        result = self.result("canary")
        control.execute("canary", packet, self.live, result)
        self.assertEqual(result["canary_inverse_receipt"], "PASS")
        self.assertEqual(helper.current_image(self.fake.target), control.BASELINE)
        self.assertTrue(all(dry for dry, _ in self.fake.requests))
        self.assertEqual(live_patches(self.fake), [])

    def test_read_only_modes_skip_the_deploy_status_gate(self):
        for mode in ("preview", "canary"):
            packet = self.promote_packet() if mode == "canary" else self.packet
            control.execute(mode, packet, self.live, self.result(mode))
        self.status_report.assert_not_called()

    def test_success_paths_run_strict_deploy_status_gate_after_readiness(self):
        order = []
        self.ready.side_effect = lambda *_args, **_kwargs: order.append("ready") or self.ready.return_value
        self.status_report.side_effect = lambda **kwargs: order.append(("report", kwargs))
        forward = self.result("promote")
        control.execute("promote", self.promote_packet(), self.live, forward, writer=self.writer)
        self.assertEqual(order[-2:], ["ready", ("report", {"strict": True})])
        self.assertEqual(forward["deploy_status_report"], "PASS")

    def test_failing_deploy_status_report_fails_the_success_path(self):
        result = self.result("promote")
        self.status_report.side_effect = REAL_STATUS_REPORT
        with patch.object(control.subprocess, "run", return_value=SimpleNamespace(returncode=1)) as report:
            with self.assertRaisesRegex(helper.Refused, "deploy_status_report_failed"):
                control.execute("promote", self.promote_packet(), self.live, result, writer=self.writer)
        self.assertEqual(report.call_args.args[0], control.STATUS_REPORT)
        self.assertEqual(result["stage"], "deploy_status_report")
        self.assertNotIn("serving_image", result)

    def test_failed_rollout_runs_diagnostic_report_and_stays_failed(self):
        def rollout(args, reason, **_kwargs):
            if reason == "rollout_unconfirmed":
                raise helper.Refused(reason)
            return ""

        self.command.side_effect = rollout
        with self.assertRaisesRegex(helper.Refused, "rollout_unconfirmed"):
            control.execute("promote", self.promote_packet(), self.live, self.result("promote"), writer=self.writer)
        self.status_report.assert_called_once_with(strict=False)


def canonical_receipt(**overrides):
    return {
        "schema": 2,
        "status": "PASS",
        "stage": "complete",
        "mode": "preview",
        "run_id": 41,
        "workflow_sha": WORKFLOW_SHA,
        "proof_sha256": "e" * 64,
        "candidate_image": CANDIDATE,
        "prior_image": control.BASELINE,
        "source_sha": SOURCE,
        "release_approval": "release-approval",
        "forward_server_dry_run": "PASS",
        "live_baseline_server_dry_run": "PASS",
        "live_baseline": ["deploy-uid", "11"],
    } | overrides


class EvidenceGateTest(unittest.TestCase):
    def setUp(self):
        self.packet = {
            "schema": 2,
            "mode": "promote",
            "source_sha": SOURCE,
            "prior_image": control.BASELINE,
            "candidate_image": CANDIDATE,
            "qualification_run_id": 10,
            "release_approval": "release-approval",
            "reviewed_preview": {"run_id": 41, "review_id": "review-41"},
            "canary": {
                "run_id": CANARY_RUN,
                "workflow_sha": "d" * 40,
                "preservation_review": {"id": "review-canary"},
            },
        }
        self.result = {"workflow_sha": WORKFLOW_SHA, "run_id": 100, **control.evidence_binding(self.packet)}
        self.metadata = {"id": CANARY_RUN, "workflow_id": 18, "status": "completed", "conclusion": "success", "head_sha": "d" * 40}

    def canary_artifacts(self):
        return {
            "evidence": {"status": "PASS", "fixture": "canonical"},
            "deployment_receipt": {
                "run_id": CANARY_RUN,
                "source_sha": SOURCE,
                "image": {"repository": REPO, "digest": DIGEST},
                "live_identity": {"deployment_uid": "canary-uid"},
            },
            "semantic_receipt": {"status": "PASS"},
            "inverse_receipt": {
                "schema": 1,
                "status": "PASS",
                "run_id": CANARY_RUN,
                "source_sha": SOURCE,
                "candidate_image": CANDIDATE,
                "baseline_image": control.BASELINE,
                "dry_run": "server",
                "deployment": {
                    "namespace": control.NAMESPACE,
                    "name": f"prod-omi-pusher-canary-{CANARY_RUN}",
                    "uid": "canary-uid",
                    "resourceVersion": "7",
                    "image": CANDIDATE,
                },
                "preconditions": {
                    "uid": "canary-uid",
                    "resourceVersion": "7",
                    "container": "pusher",
                    "image": CANDIDATE,
                },
                "admitted_image": control.BASELINE,
            },
        }

    def canary_mocks(self, artifacts, *, validation=None):
        return (
            patch.object(control, "workflow_run_metadata", return_value=self.metadata),
            patch.object(control, "download_canary", return_value=artifacts),
            patch.object(control, "_validate_canary", return_value=validation),
        )

    def test_check_canary_binds_run_evidence_and_recorded_inverse(self):
        artifacts = self.canary_artifacts()
        self.packet["canary"]["preservation_review"] = {
            "id": "review-canary",
            "proof_sha256": self.result["proof_sha256"],
            "evidence_sha256": control.canonical_sha256(artifacts["evidence"]),
            "baseline": control.BASELINE,
        }
        mocks = self.canary_mocks(artifacts)
        with mocks[0] as fetch, mocks[1], mocks[2]:
            control.check_canary(self.packet, self.result, {"deployment": "qualified"})
        fetch.assert_called_once_with(CANARY_RUN, control.PROMOTION_WORKFLOW, expected_sha="d" * 40)
        self.assertEqual(self.result["canary_run_id"], CANARY_RUN)
        self.assertEqual(self.result["canary_inverse_receipt"], "PASS")

    def test_check_canary_refuses_each_unbound_path(self):
        cases = (
            ("wrong-image", "wrong_canary_image"),
            ("wrong-source", "canary_source_sha_mismatch"),
            ("wrong-preservation", "preserved_canary_review_missing"),
            ("noncanonical-evidence", "canonical_canary_refused"),
            ("wrong-inverse", "canary_inverse_receipt_refused"),
        )
        for case, reason in cases:
            with self.subTest(case=case):
                artifacts = self.canary_artifacts()
                self.packet["canary"]["preservation_review"] = {
                    "id": "review-canary",
                    "proof_sha256": self.result["proof_sha256"],
                    "evidence_sha256": control.canonical_sha256(artifacts["evidence"]),
                    "baseline": control.BASELINE,
                }
                validation = None
                if case == "wrong-image":
                    artifacts["deployment_receipt"]["image"]["digest"] = "sha256:" + "f" * 64
                elif case == "wrong-source":
                    artifacts["deployment_receipt"]["source_sha"] = "f" * 40
                elif case == "wrong-preservation":
                    self.packet["canary"]["preservation_review"]["proof_sha256"] = "f" * 64
                elif case == "noncanonical-evidence":
                    validation = ["canary_digest_mismatch"]
                else:
                    artifacts["inverse_receipt"]["preconditions"]["container"] = "listener"
                mocks = self.canary_mocks(artifacts, validation=validation)
                with mocks[0], mocks[1], mocks[2], self.assertRaisesRegex(helper.Refused, reason):
                    control.check_canary(self.packet, self.result, {"deployment": "qualified"})

    def test_reviewed_preview_requires_a_successful_bound_run_and_both_dry_runs(self):
        review = self.packet["reviewed_preview"]
        with (
            patch.object(control, "workflow_run_metadata", return_value=self.metadata) as fetch,
            patch.object(control, "download_receipt", return_value=canonical_receipt(proof_sha256=self.result["proof_sha256"])),
        ):
            control.check_reviewed_preview(self.packet, self.result)
        fetch.assert_called_once_with(review["run_id"], control.PROMOTION_WORKFLOW, expected_sha=WORKFLOW_SHA)

        for overrides, reason in (
            ({"live_baseline_server_dry_run": "REFUSED"}, "reviewed_forward_preview_missing"),
            ({"run_id": 40}, "reviewed_forward_preview_missing"),
            ({"release_approval": "other"}, "reviewed_forward_preview_missing"),
            ({"proof_sha256": "f" * 64}, "reviewed_forward_preview_missing"),
        ):
            with self.subTest(reason=reason):
                with (
                    patch.object(control, "workflow_run_metadata", return_value=self.metadata),
                    patch.object(control, "download_receipt", return_value=canonical_receipt(**overrides)),
                    self.assertRaisesRegex(helper.Refused, reason),
                ):
                    control.check_reviewed_preview(self.packet, self.result)

    def test_validate_packet_requires_exact_shape_and_binds_dispatch_at_runtime(self):
        dispatch = {"id": 100, "status": "in_progress", "conclusion": None}
        with patch.object(control, "workflow_run_metadata", return_value=dispatch) as fetch:
            control.validate_packet(self.packet, "promote", WORKFLOW_SHA, 100)
        fetch.assert_called_once_with(100, control.PROMOTION_WORKFLOW, expected_sha=WORKFLOW_SHA, require_success=False)

        cases = (
            ("run_id", "protected_evidence_mismatch"),
            ("mode", "protected_evidence_mismatch"),
            ("schema", "protected_evidence_mismatch"),
            ("candidate_image", "protected_evidence_mismatch"),
        )
        for field, reason in cases:
            with self.subTest(field=field):
                packet = json.loads(json.dumps(self.packet))
                packet[field] = {"run_id": 100, "mode": "preview", "schema": 1, "candidate_image": control.BASELINE}[field]
                with patch.object(control, "workflow_run_metadata", return_value=dispatch), self.assertRaisesRegex(
                    helper.Refused, reason
                ):
                    control.validate_packet(packet, "promote", WORKFLOW_SHA, 100)
        packet = json.loads(json.dumps(self.packet))
        del packet["canary"]
        with patch.object(control, "workflow_run_metadata", return_value=dispatch), self.assertRaisesRegex(
            helper.Refused, "protected_evidence_mismatch"
        ):
            control.validate_packet(packet, "promote", WORKFLOW_SHA, 100)

    def test_workflow_run_metadata_checks_repo_workflow_source_and_conclusion(self):
        metadata = {
            "id": 42,
            "workflow_id": 18,
            "event": "workflow_dispatch",
            "head_branch": "main",
            "head_sha": WORKFLOW_SHA,
            "run_attempt": 1,
            "head_repository": {"full_name": control.REPO},
            "status": "completed",
            "conclusion": "success",
        }

        def answer(args, reason):
            return "18" if reason == "evidence_workflow_unavailable" else json.dumps(metadata)

        with patch.object(control, "run", side_effect=answer):
            self.assertEqual(control.workflow_run_metadata(42, control.PROMOTION_WORKFLOW, expected_sha=WORKFLOW_SHA), metadata)
        for field, value in (("head_sha", "b" * 40), ("conclusion", "failure"), ("workflow_id", 19), ("head_repository", {"full_name": "other/repo"})):
            with self.subTest(field=field):
                broken = dict(metadata, **{field: value})
                with patch.object(
                    control, "run", side_effect=lambda a, r, broken=broken: "18" if r == "evidence_workflow_unavailable" else json.dumps(broken)
                ):
                    with self.assertRaises(helper.Refused):
                        control.workflow_run_metadata(42, control.PROMOTION_WORKFLOW, expected_sha=WORKFLOW_SHA)

    def test_download_receipt_binds_pass_status_and_run_id(self):
        def download(args, reason):
            self.assertEqual(reason, "protected_run_receipt_unavailable")
            target = Path(args[args.index("--dir") + 1]) / "receipt.json"
            target.write_text(json.dumps({"status": "PASS", "run_id": 42}), encoding="utf-8")
            return ""

        with patch.object(control, "run", side_effect=download):
            self.assertEqual(control.download_receipt(42), {"status": "PASS", "run_id": 42})

        def mismatched(args, _reason):
            (Path(args[args.index("--dir") + 1]) / "receipt.json").write_text(
                json.dumps({"status": "PASS", "run_id": 43}), encoding="utf-8"
            )
            return ""

        with patch.object(control, "run", side_effect=mismatched):
            with self.assertRaisesRegex(helper.Refused, "protected_run_receipt_refused"):
                control.download_receipt(42)

    def test_check_capacity_accepts_proven_capacity_and_refuses_shortfall(self):
        class Cluster:
            def get(self, *_args, **_kwargs):
                return {"items": []}

            def call(self, *_args, **_kwargs):
                return {"items": []}

        with patch.object(control, "capacity_evidence", return_value=([], {})):
            control.check_capacity(Cluster(), {"live": "deployment"}, {"admitted": "deployment"})
        with patch.object(control, "capacity_evidence", return_value=(["insufficient_nodes"], {})):
            with self.assertRaisesRegex(helper.Refused, "live_preserved_template_has_insufficient_capacity"):
                control.check_capacity(Cluster(), {"live": "deployment"}, {"admitted": "deployment"})

    def test_verify_canary_cleanup_accepts_absence_and_refuses_leftovers(self):
        class Cluster:
            leftover = False

            def get(self, resource, name=None, **_kwargs):
                if resource == "pods":
                    items = [{"metadata": {"name": control.canary_target(42) + "-pod"}}] if self.leftover else []
                    return {"items": items}
                return {"leftover": True} if self.leftover and name == control.canary_target(42) else None

        cluster = Cluster()
        control.verify_canary_cleanup(cluster, 42)
        cluster.leftover = True
        with self.assertRaisesRegex(helper.Refused, "canary_cleanup_incomplete"):
            control.verify_canary_cleanup(cluster, 42)


class MainTest(unittest.TestCase):
    def setUp(self):
        self.packet = {
            "schema": 2,
            "mode": "preview",
            "source_sha": SOURCE,
            "prior_image": control.BASELINE,
            "candidate_image": CANDIDATE,
            "qualification_run_id": 10,
            "release_approval": "release-approval",
        }
        self.env = {
            "IMAGE_ONLY_MODE": "preview",
            "GITHUB_WORKFLOW_SHA": WORKFLOW_SHA,
            "GITHUB_RUN_ID": "100",
            "PUSHER_IMAGE_ONLY_EVIDENCE": json.dumps(self.packet),
            "SOURCE_SHA": SOURCE,
            "QUALIFICATION_RUN_ID": "10",
            "REQUESTED_DIGEST": DIGEST,
            "KUBECONFIG": "live-kubeconfig",
            "LIVE_CONTEXT": "live",
        }

    def run_main(self, *, execute=None, env=None):
        def default_execute(_mode, _packet, _live, result, *, writer=None):
            self.assertIsNotNone(writer) if _mode in {"promote", "rollback"} else self.assertIsNone(writer)
            result["stage"] = "deploy_status_report"
            control.deploy_status_report(strict=True)

        with (
            patch.dict(os.environ, env or self.env),
            patch.object(control, "workflow_run_metadata", return_value={"id": 100, "status": "in_progress"}),
            patch.object(control, "Cluster"),
            patch.object(control, "execute", side_effect=execute or default_execute),
            patch.object(control.subprocess, "run", return_value=SimpleNamespace(returncode=1)),
            patch("builtins.print") as output,
        ):
            code = control.main()
        return code, json.loads(output.call_args.args[0])

    def test_main_binds_the_dispatch_run_from_workflow_context(self):
        env = dict(self.env, IMAGE_ONLY_MODE="promote")
        env["PUSHER_IMAGE_ONLY_EVIDENCE"] = json.dumps(
            self.packet
            | {"mode": "promote", "reviewed_preview": {"run_id": 41, "review_id": "r"}, "canary": {"run_id": 42, "workflow_sha": "d" * 40, "preservation_review": {"id": "x"}}}
        )
        code, receipt = self.run_main(
            execute=lambda _mode, _packet, _live, result, *, writer=None: result.update(stage="deploy_status_report"),
            env=env,
        )
        self.assertEqual((code, receipt["status"], receipt["run_id"]), (0, "PASS", 100))
        self.assertEqual(receipt["proof_id"], "release-approval")
        self.assertEqual(receipt["source_sha"], SOURCE)

    def test_main_refuses_a_packet_that_names_its_own_run(self):
        env = dict(self.env, PUSHER_IMAGE_ONLY_EVIDENCE=json.dumps(self.packet | {"run_id": 100}))
        code, receipt = self.run_main(env=env)
        self.assertEqual((code, receipt["reason"]), (1, "protected_evidence_mismatch"))

    def test_main_refuses_dispatch_inputs_not_bound_to_the_evidence(self):
        code, receipt = self.run_main(env=dict(self.env, REQUESTED_DIGEST="sha256:" + "f" * 64))
        self.assertEqual((code, receipt["reason"]), (1, "dispatch_evidence_mismatch"))

    def test_main_reports_hold_for_a_refused_inverse(self):
        env = dict(self.env, IMAGE_ONLY_MODE="promote")
        env["PUSHER_IMAGE_ONLY_EVIDENCE"] = json.dumps(
            self.packet
            | {"mode": "promote", "reviewed_preview": {"run_id": 41, "review_id": "r"}, "canary": {"run_id": 42, "workflow_sha": "d" * 40, "preservation_review": {"id": "x"}}}
        )
        code, receipt = self.run_main(
            execute=lambda _mode, _packet, _live, result, *, writer=None: (_ for _ in ()).throw(control.Hold("REFUSED_INVERSE")),
            env=env,
        )
        self.assertEqual((code, receipt["status"], receipt["reason"]), (1, "HOLD", "REFUSED_INVERSE"))

    def test_image_only_job_timeout_covers_rollout_and_receipt_work(self):
        workflow = (control.ROOT / ".github/workflows/gcp_backend_pusher.yml").read_text(encoding="utf-8")
        match = re.search(r"(?ms)^  pusher-image-only:\n(.*?)(?=^  [A-Za-z0-9_-]+:|\Z)", workflow)
        self.assertIsNotNone(match)
        timeout = re.search(r"(?m)^    timeout-minutes: (\d+)\s*$", match.group(1))
        self.assertIsNotNone(timeout)
        self.assertGreaterEqual(int(timeout.group(1)), control.ROLLOUT_TIMEOUT // 60 + 50)

    def test_image_only_job_has_no_packet_or_isolated_secret(self):
        workflow = (control.ROOT / ".github/workflows/gcp_backend_pusher.yml").read_text(encoding="utf-8")
        match = re.search(r"(?ms)^  pusher-image-only:\n(.*?)(?=^  [A-Za-z0-9_-]+:|\Z)", workflow)
        self.assertNotIn("PUSHER_IMAGE_ONLY_PACKET", match.group(1))
        self.assertNotIn("PUSHER_IMAGE_ONLY_ISOLATED_KUBECONFIG", match.group(1))
        self.assertIn("inputs.pusher_image_only_evidence", match.group(1))


if __name__ == "__main__":
    unittest.main()
