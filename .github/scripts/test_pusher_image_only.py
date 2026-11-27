#!/usr/bin/env python3
"""Check workflow sequencing against the guarded rehearsal API fake."""

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
import test_pusher_image_rehearsal as fixture

REAL_STATUS_REPORT = control.deploy_status_report


class ProtectedServer(fixture.Server, control.ProtectedCluster):
    pass


class ImageOnlyTest(unittest.TestCase):
    def setUp(self):
        model = fixture.RehearsalTest()
        model.setUp()
        self.live = ProtectedServer("live")
        self.isolated = model.isolated
        for server in (self.live, self.isolated):
            server.target["spec"]["template"]["spec"]["containers"][1]["image"] = control.BASELINE
            server.target["metadata"]["generation"] = 1

        self.proof = model.proof | {"prior_image": control.BASELINE}
        self.rehearsal = helper.Rehearsal(self.live, self.isolated, self.proof)
        receipt = self.result("rehearse")
        self.rehearsal.rehearse(receipt)
        receipt["status"] = "PASS"
        self.packet = {"rehearsal_receipt": receipt, "reviewed_inverse_rehearsal": "approved-inverse"}
        self.live.requests.clear()
        self.baseline = copy.deepcopy(self.live.target)
        self.config = copy.deepcopy(self.live.config)
        self.command = self.enterContext(patch.object(control, "run", return_value=""))
        self.enterContext(patch.object(control, "check_provenance", return_value={"qualified": True}))
        self.ready = self.enterContext(
            patch.object(
                control,
                "verify_ready",
                return_value={"deployment_uid": "target-live", "generation": 1, "ready_replicas": 1},
            )
        )
        self.canary = self.enterContext(
            patch.object(control, "check_canary", side_effect=lambda *args: args[-1].update(canary_run_id=12))
        )
        self.preview = self.enterContext(patch.object(control, "check_reviewed_preview"))
        self.enterContext(patch.object(control, "verify_canary_cleanup"))
        self.enterContext(patch.object(control, "check_capacity"))
        self.status_report = self.enterContext(patch.object(control, "deploy_status_report"))

    def result(self, mode):
        return {"mode": mode, "workflow_sha": "a" * 40, **helper.proof_receipt_fields(self.proof)}

    def test_preview_is_read_only_and_requires_both_fixes(self):
        result = self.result("preview")
        control.execute("preview", self.packet, self.rehearsal, result)
        admitted_fix_calls = [call.args[0][3] for call in self.command.call_args_list]
        self.assertEqual(admitted_fix_calls, list(control.REQUIRED_FIXES))
        self.assertEqual(result["forward_server_dry_run"], "PASS")
        self.assertEqual(self.live.target, self.baseline)
        self.assertTrue(all(dry for dry, _ in self.live.requests))

    def test_missing_fix_or_canary_blocks_before_any_patch(self):
        self.command.side_effect = helper.Refused("required_gcs_fix_missing")
        with self.assertRaisesRegex(helper.Refused, "required_gcs_fix_missing"):
            control.execute("promote", self.packet, self.rehearsal, self.result("promote"))
        self.command.side_effect = None
        self.canary.side_effect = helper.Refused("preserved_canary_review_missing")
        with self.assertRaisesRegex(helper.Refused, "preserved_canary_review_missing"):
            control.execute("promote", self.packet, self.rehearsal, self.result("promote"))
        self.assertEqual(self.live.requests, [])

    def test_failed_review_prevents_persistent_patch(self):
        self.preview.side_effect = helper.Refused("reviewed_forward_preview_missing")
        with self.assertRaisesRegex(helper.Refused, "reviewed_forward_preview_missing"):
            control.execute("promote", self.packet, self.rehearsal, self.result("promote"))
        self.assertEqual(self.live.target, self.baseline)
        self.assertTrue(all(dry for dry, _ in self.live.requests))

    def test_canary_checks_preserved_deployment_and_uses_dry_run_only(self):
        self.canary.side_effect = None
        self.canary.return_value = {"receipt": "canary"}
        with patch.object(control, "verify_canary_live") as verify:
            control.execute("canary", self.packet, self.rehearsal, self.result("canary"))
        _, admitted, receipt = verify.call_args.args
        self.assertEqual(helper.current_image(admitted), fixture.CANDIDATE)
        self.assertEqual(receipt, {"receipt": "canary"})
        self.assertEqual(self.live.target, self.baseline)
        self.assertTrue(all(dry for dry, _ in self.live.requests))

    def test_promote_verifies_exact_live_inverse_then_rollback_restores_baseline(self):
        forward = self.result("promote")
        control.execute("promote", self.packet, self.rehearsal, forward)
        self.assertEqual(forward["live_inverse_server_dry_run"], "PASS")
        self.assertEqual(forward["serving_image"], fixture.CANDIDATE)
        self.assertEqual(self.live.config, self.config)

        self.ready.reset_mock()
        self.command.return_value = control.BASELINE.split("@")[1]
        reverse = self.result("rollback")
        control.execute("rollback", self.packet, self.rehearsal, reverse)
        self.assertEqual(reverse["live_inverse_server_dry_run"], "PASS")
        self.assertEqual(reverse["serving_image"], control.BASELINE)
        self.assertEqual(helper.comparable(self.live.target), helper.comparable(self.baseline))
        self.assertEqual(self.live.config, self.config)
        self.ready.assert_called_once()
        self.assertEqual(self.ready.call_args.args[2], control.BASELINE)
        patches = [ops for dry, ops in self.live.requests if not dry]
        self.assertEqual([ops[-1]["value"] for ops in patches], [fixture.CANDIDATE, control.BASELINE])
        self.assertTrue(all([op["op"] for op in ops] == ["test"] * 4 + ["replace"] for ops in patches))

    def test_read_only_modes_skip_the_deploy_status_gate(self):
        self.canary.side_effect = None
        with patch.object(control, "verify_canary_live"):
            for mode in ("preview", "canary"):
                control.execute(mode, self.packet, self.rehearsal, self.result(mode))
        self.status_report.assert_not_called()

    def test_success_paths_run_strict_deploy_status_gate_after_readiness(self):
        order = []
        self.ready.side_effect = lambda *_args, **_kwargs: order.append("ready") or self.ready.return_value
        self.status_report.side_effect = lambda **kwargs: order.append(("report", kwargs))
        forward = self.result("promote")
        control.execute("promote", self.packet, self.rehearsal, forward)
        self.assertEqual(order[-2:], ["ready", ("report", {"strict": True})])
        self.assertEqual(forward["deploy_status_report"], "PASS")

        order.clear()
        self.command.return_value = control.BASELINE.split("@")[1]
        reverse = self.result("rollback")
        control.execute("rollback", self.packet, self.rehearsal, reverse)
        self.assertEqual(order[-2:], ["ready", ("report", {"strict": True})])
        self.assertEqual(reverse["deploy_status_report"], "PASS")

    def test_failing_deploy_status_report_fails_the_success_path(self):
        result = self.result("promote")
        self.status_report.side_effect = REAL_STATUS_REPORT
        with patch.object(control.subprocess, "run", return_value=SimpleNamespace(returncode=1)) as report:
            with self.assertRaisesRegex(helper.Refused, "deploy_status_report_failed"):
                control.execute("promote", self.packet, self.rehearsal, result)
        self.assertEqual(report.call_args.args[0], control.STATUS_REPORT)
        self.assertEqual(result["stage"], "deploy_status_report")
        self.assertNotIn("serving_image", result)
        self.assertNotIn("deploy_status_report", result)

    def test_failed_rollout_runs_diagnostic_report_and_stays_failed(self):
        def rollout(args, reason, **_kwargs):
            if reason == "rollout_unconfirmed":
                raise helper.Refused(reason)
            return ""

        self.command.side_effect = rollout
        with self.assertRaisesRegex(helper.Refused, "rollout_unconfirmed"):
            control.execute("promote", self.packet, self.rehearsal, self.result("promote"))
        self.status_report.assert_called_once_with(strict=False)

    def test_failed_post_patch_inverse_keeps_candidate_for_reconciliation(self):
        def reject_inverse(old, proposed, dry):
            if dry and helper.current_image(old) == fixture.CANDIDATE:
                proposed["spec"]["template"]["spec"]["containers"][1]["env"] = []

        self.live.admit = reject_inverse
        result = self.result("promote")
        with self.assertRaisesRegex(helper.Refused, "admission_changed_more_than_image"):
            control.execute("promote", self.packet, self.rehearsal, result)
        self.assertEqual(helper.current_image(self.live.target), fixture.CANDIDATE)
        self.assertIn("patch_observed", result)
        self.assertNotIn("serving_image", result)
        self.assertEqual(sum(not dry for dry, _ in self.live.requests), 1)


DIGEST = fixture.CANDIDATE.split("@")[1]


def rs_template(image, *, hash_label=None, restarted=None):
    labels = {"app": "pusher"}
    if hash_label:
        labels["pod-template-hash"] = hash_label
    metadata = {"labels": labels}
    if restarted:
        metadata["annotations"] = {"kubectl.kubernetes.io/restartedAt": restarted}
    return {"metadata": metadata, "spec": {"containers": [{"name": "pusher", "image": image}]}}


def ready_pod(name, rs_uid, image, *, phase="Running", terminating=False):
    metadata = {
        "name": name,
        "uid": f"{name}-uid",
        "ownerReferences": [{"controller": True, "kind": "ReplicaSet", "uid": rs_uid}],
    }
    if terminating:
        metadata["deletionTimestamp"] = "2026-11-27T00:00:00Z"
    return {
        "metadata": metadata,
        "spec": {"containers": [{"name": "pusher", "image": image}]},
        "status": {
            "phase": phase,
            "containerStatuses": [
                {"name": "pusher", "ready": phase == "Running", "imageID": "gcr.io/x@" + image.split("@")[1]}
            ],
        },
    }


class VerifyReadyTest(unittest.TestCase):
    def setUp(self):
        self.deployment = {
            "metadata": {"name": control.TARGET, "uid": "deploy-uid", "resourceVersion": "9", "generation": 3},
            "spec": {"replicas": 2, "template": rs_template(fixture.CANDIDATE)},
            "status": {
                "observedGeneration": 3,
                "replicas": 2,
                "updatedReplicas": 2,
                "readyReplicas": 2,
                "availableReplicas": 2,
            },
        }
        owner = [{"controller": True, "kind": "Deployment", "uid": "deploy-uid"}]
        self.replicasets = [
            {
                "metadata": {"uid": "rs-new", "resourceVersion": "8", "ownerReferences": owner},
                "spec": {"template": rs_template(fixture.CANDIDATE, hash_label="new")},
            },
            {
                "metadata": {"uid": "rs-old", "resourceVersion": "7", "ownerReferences": owner},
                "spec": {"template": rs_template(control.BASELINE, hash_label="old")},
            },
        ]
        self.pods = [ready_pod("new-a", "rs-new", fixture.CANDIDATE), ready_pod("new-b", "rs-new", fixture.CANDIDATE)]

    def cluster(self):
        replicasets, pods = self.replicasets, self.pods

        class Cluster:
            def get(self, resource, name=None, **_kwargs):
                return {"items": {"replicasets.apps": replicasets, "pods": pods}[resource]}

        return Cluster()

    def test_terminating_old_replicaset_pods_do_not_block_readiness(self):
        self.pods += [
            ready_pod("old-a", "rs-old", control.BASELINE, terminating=True),
            ready_pod("old-b", "rs-old", control.BASELINE, phase="Failed", terminating=True),
        ]
        identity = control.verify_ready(self.cluster(), self.deployment, fixture.CANDIDATE)
        self.assertEqual([pod["name"] for pod in identity["pods"]], ["new-a", "new-b"])
        self.assertEqual(identity["ready_replicas"], 2)

    def test_restart_only_template_change_selects_the_new_replicaset(self):
        self.deployment["spec"]["template"] = rs_template(fixture.CANDIDATE, restarted="now")
        self.replicasets[0]["spec"]["template"] = rs_template(fixture.CANDIDATE, hash_label="new", restarted="now")
        self.replicasets[1]["spec"]["template"] = rs_template(fixture.CANDIDATE, hash_label="old")
        self.pods.append(ready_pod("old-a", "rs-old", fixture.CANDIDATE, terminating=True))
        identity = control.verify_ready(self.cluster(), self.deployment, fixture.CANDIDATE)
        self.assertEqual(len(identity["pods"]), 2)

    def test_new_pod_not_running_or_terminating_still_refuses(self):
        cases = {
            "pending": ready_pod("new-b", "rs-new", fixture.CANDIDATE, phase="Pending"),
            "terminating": ready_pod("new-b", "rs-new", fixture.CANDIDATE, terminating=True),
        }
        for case, pod in cases.items():
            with self.subTest(case=case):
                self.pods[1] = pod
                self.pods.append(ready_pod("old-a", "rs-old", control.BASELINE, terminating=True))
                with self.assertRaisesRegex(helper.Refused, "pusher_replica_replacement_incomplete"):
                    control.verify_ready(self.cluster(), self.deployment, fixture.CANDIDATE)
                self.pods = self.pods[:2]

    def test_active_old_pod_or_partial_update_still_refuses(self):
        self.pods.append(ready_pod("old-a", "rs-old", control.BASELINE))
        with self.assertRaisesRegex(helper.Refused, "pusher_replica_replacement_incomplete"):
            control.verify_ready(self.cluster(), self.deployment, fixture.CANDIDATE)
        self.pods.pop()
        self.deployment["status"]["updatedReplicas"] = 1
        with self.assertRaisesRegex(helper.Refused, "pusher_replica_replacement_incomplete"):
            control.verify_ready(self.cluster(), self.deployment, fixture.CANDIDATE)

    def test_missing_new_replicaset_or_wrong_digest_refuses(self):
        self.replicasets.pop(0)
        with self.assertRaisesRegex(helper.Refused, "pusher_new_replicaset_unresolved"):
            control.verify_ready(self.cluster(), self.deployment, fixture.CANDIDATE)
        self.setUp()
        with self.assertRaises(control.ReceiptError):
            control.verify_ready(self.cluster(), self.deployment, control.BASELINE)


class DeployStatusReportTest(unittest.TestCase):
    def test_strict_gate_uses_the_ordinary_deploy_arguments_and_fails_on_findings(self):
        self.assertEqual(
            control.STATUS_REPORT[1:],
            ("backend/scripts/deploy_status_report.py", "--env", "prod", "--include-gke", "--gke-service", "pusher"),
        )
        with patch.object(control.subprocess, "run", return_value=SimpleNamespace(returncode=0)) as report:
            control.deploy_status_report(strict=True)
        self.assertEqual(report.call_args.args[0], control.STATUS_REPORT)
        self.assertIsNot(report.call_args.kwargs["stdout"], control.subprocess.PIPE)
        with patch.object(control.subprocess, "run", return_value=SimpleNamespace(returncode=1)):
            with self.assertRaisesRegex(helper.Refused, "deploy_status_report_failed"):
                control.deploy_status_report(strict=True)
            control.deploy_status_report(strict=False)

    def test_failing_report_fails_the_job_with_a_refused_receipt(self):
        packet = {
            "schema": 1,
            "mode": "promote",
            "workflow_sha": "a" * 40,
            "run_id": 100,
            "release_approval": "release-approval",
            "proof": {
                "prior_image": control.BASELINE,
                "source_sha": "3" * 40,
                "qualification_run_id": 10,
                "candidate_image": fixture.CANDIDATE,
            },
        }
        env = {
            "IMAGE_ONLY_MODE": "promote",
            "GITHUB_WORKFLOW_SHA": "a" * 40,
            "GITHUB_RUN_ID": "100",
            "PUSHER_IMAGE_ONLY_ISOLATED_KUBECONFIG": (
                "apiVersion: v1\ncurrent-context: isolated\n"
                "clusters:\n- name: isolated\n  cluster:\n    server: https://isolated.example\n"
                "users:\n- name: isolated\n  user:\n    token: fixture\n"
            ),
            "PUSHER_IMAGE_ONLY_PACKET": json.dumps(packet),
            "SOURCE_SHA": "3" * 40,
            "QUALIFICATION_RUN_ID": "10",
            "REQUESTED_DIGEST": DIGEST,
            "KUBECONFIG": "live-kubeconfig",
            "LIVE_CONTEXT": "live",
        }

        def execute(_mode, _packet, _rehearsal, result):
            result["stage"] = "deploy_status_report"
            control.deploy_status_report(strict=True)

        with (
            patch.dict(os.environ, env),
            patch.object(control, "ProtectedCluster"),
            patch.object(control, "Cluster"),
            patch.object(control, "Rehearsal"),
            patch.object(control, "proof_receipt_fields", return_value={}),
            patch.object(control, "execute", side_effect=execute),
            patch.object(control.subprocess, "run", return_value=SimpleNamespace(returncode=1)),
            patch("builtins.print") as output,
        ):
            self.assertEqual(control.main(), 1)
        receipt = json.loads(output.call_args.args[0])
        self.assertEqual(
            (receipt["status"], receipt["stage"], receipt["reason"]),
            ("REFUSED", "deploy_status_report", "deploy_status_report_failed"),
        )


class EvidenceGateTest(unittest.TestCase):
    def setUp(self):
        model = fixture.RehearsalTest()
        model.setUp()
        self.proof = model.proof | {"prior_image": control.BASELINE}
        self.rehearsal = SimpleNamespace(candidate=fixture.CANDIDATE, proof=self.proof)
        self.workflow_sha = "a" * 40
        self.run_id = 42
        self.result = {
            **helper.proof_receipt_fields(self.proof),
            "workflow_sha": self.workflow_sha,
            "mode": "promote",
            "run_id": 100,
        }
        self.qualification_receipt = {"deployment": "qualified"}

    def canary_packet(self):
        evidence = {"approval_run_id": self.run_id, "fixture": "canonical-evidence"}
        repository, digest = fixture.CANDIDATE.split("@")
        return {
            "canary": {
                "deployment_receipt": {"image": {"repository": repository, "digest": digest}},
                "evidence": evidence,
                "semantic_receipt": {"status": "PASS"},
                "workflow_sha": self.workflow_sha,
                "preservation_review": {
                    "id": "preservation-review",
                    "proof_sha256": self.result["proof_sha256"],
                    "evidence_sha256": control.canonical_sha256(evidence),
                    "baseline": self.proof["live_deployment"],
                },
            }
        }

    def canary_mocks(self, packet, *, validation=None, attestation=None):
        metadata = {"workflow_id": 18, "status": "completed", "conclusion": "success"}
        evidence_hash = control.canonical_sha256(packet["canary"]["evidence"])
        attestation = attestation or {
            "mode": "canary",
            "stage": "complete",
            "canary_evidence_sha256": evidence_hash,
            "proof_sha256": self.result["proof_sha256"],
            "workflow_sha": self.workflow_sha,
        }
        return (
            patch.object(control, "protected_workflow_run", return_value=metadata),
            patch.object(control, "_validate_canary", return_value=validation),
            patch.object(control, "download_receipt", return_value=attestation),
        )

    def test_check_canary_accepts_bound_preservation_and_completion_receipts(self):
        packet = self.canary_packet()
        mocks = self.canary_mocks(packet)
        with mocks[0], mocks[1], mocks[2]:
            deployment = control.check_canary(packet, self.rehearsal, self.qualification_receipt, self.result)
        self.assertEqual(deployment, packet["canary"]["deployment_receipt"])
        self.assertEqual(self.result["canary_run_id"], self.run_id)
        self.assertEqual(self.result["canary_evidence_sha256"], control.canonical_sha256(packet["canary"]["evidence"]))

    def test_check_canary_refuses_each_unbound_evidence_path(self):
        cases = (
            ("wrong-image", "wrong_canary_image"),
            ("wrong-preservation-proof", "preserved_canary_review_missing"),
            ("wrong-workflow", "canary_workflow_sha_mismatch"),
            ("noncanonical-evidence", "canonical_canary_refused"),
            ("wrong-attestation", "preserved_canary_attestation_mismatch"),
            ("invalid-run", "invalid_canary_run"),
        )
        for case, reason in cases:
            with self.subTest(case=case):
                packet = self.canary_packet()
                result = dict(self.result)
                validation = None
                attestation = None
                if case == "wrong-image":
                    packet["canary"]["deployment_receipt"]["image"]["digest"] = "sha256:" + "f" * 64
                elif case == "wrong-preservation-proof":
                    packet["canary"]["preservation_review"]["proof_sha256"] = "f" * 64
                elif case == "wrong-workflow":
                    packet["canary"]["workflow_sha"] = "b" * 40
                elif case == "noncanonical-evidence":
                    validation = "canary_digest_mismatch"
                elif case == "wrong-attestation":
                    attestation = {
                        "mode": "canary",
                        "stage": "complete",
                        "canary_evidence_sha256": "f" * 64,
                        "proof_sha256": self.result["proof_sha256"],
                        "workflow_sha": self.workflow_sha,
                    }
                else:
                    packet["canary"]["evidence"]["approval_run_id"] = True
                mocks = self.canary_mocks(packet, validation=validation, attestation=attestation)
                with mocks[0], mocks[1], mocks[2], self.assertRaisesRegex(helper.Refused, reason):
                    control.check_canary(packet, self.rehearsal, self.qualification_receipt, result)

    def test_verify_canary_live_binds_template_pods_and_service_selectors(self):
        template = {"containers": [{"name": "pusher", "image": fixture.CANDIDATE}]}
        canary = {"spec": {"template": {"spec": template}}}
        identity = {"pods": [{"name": "canary-pod", "uid": "pod-uid"}]}
        receipt = {
            "run_id": 42,
            "image": dict(zip(("repository", "digest"), fixture.CANDIDATE.split("@"))),
            "live_identity": identity,
        }

        class Cluster:
            def get(self, resource, name=None, **_kwargs):
                if resource == "deployment.apps":
                    return canary
                if resource == "pod":
                    return {"metadata": {"uid": "pod-uid", "labels": {"app": "canary"}}}
                if resource == "services":
                    return {"items": []}
                raise AssertionError(resource)

        with (
            patch.object(control, "verify_ready", return_value=identity),
            patch.object(control, "_service_selectors", return_value=[("ordinary", {"app": "pusher"})]),
            patch.object(control, "_selector_matches", return_value=False),
        ):
            control.verify_canary_live(Cluster(), canary, receipt)

        with patch.object(control, "verify_ready", return_value=identity), patch.object(
            control, "_service_selectors", return_value=[("ordinary", {"app": "canary"})]
        ), patch.object(control, "_selector_matches", return_value=True):
            with self.assertRaisesRegex(helper.Refused, "canary_pod_selected_by_ordinary_service"):
                control.verify_canary_live(Cluster(), canary, receipt)

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

    def test_protected_workflow_run_checks_exact_workflow_and_head(self):
        metadata = {
            "id": 42,
            "workflow_id": 18,
            "event": "workflow_dispatch",
            "head_branch": "main",
            "head_sha": self.workflow_sha,
            "run_attempt": 1,
            "head_repository": {"full_name": control.REPO},
        }

        def qualified(args, reason):
            return "18" if reason == "protected_workflow_unavailable" else json.dumps(metadata)

        with patch.object(control, "run", side_effect=qualified):
            self.assertEqual(control.protected_workflow_run(42, self.workflow_sha), metadata)
        metadata["head_sha"] = "b" * 40
        with patch.object(control, "run", side_effect=qualified):
            with self.assertRaisesRegex(helper.Refused, "protected_receipt_run_unqualified"):
                control.protected_workflow_run(42, self.workflow_sha)

    def main_refusal(self, packet, kubeconfig):
        env = {
            "IMAGE_ONLY_MODE": "preview",
            "GITHUB_WORKFLOW_SHA": self.workflow_sha,
            "GITHUB_RUN_ID": "100",
            "PUSHER_IMAGE_ONLY_ISOLATED_KUBECONFIG": kubeconfig,
            "PUSHER_IMAGE_ONLY_PACKET": json.dumps(packet),
            "SOURCE_SHA": "3" * 40,
            "QUALIFICATION_RUN_ID": "10",
            "REQUESTED_DIGEST": fixture.CANDIDATE.split("@")[1],
        }
        with patch.dict(os.environ, env), patch("builtins.print") as output:
            self.assertEqual(control.main(), 1)
        return json.loads(output.call_args.args[0])

    def main_packet(self):
        return {
            "schema": 1,
            "mode": "preview",
            "workflow_sha": self.workflow_sha,
            "run_id": 100,
            "proof": {
                "prior_image": control.BASELINE,
                "source_sha": "3" * 40,
                "qualification_run_id": 10,
                "candidate_image": fixture.CANDIDATE,
            },
        }

    def test_main_refuses_packet_mode_and_run_id_mismatches(self):
        kubeconfig = "{}"
        cases = (("mode", "mode", "canary"), ("run_id", "run_id", 101))
        for _case, field, value in cases:
            with self.subTest(field=field):
                packet = self.main_packet()
                packet[field] = value
                receipt = self.main_refusal(packet, kubeconfig)
                self.assertEqual(receipt["reason"], "protected_run_approval_mismatch")

    def test_main_refuses_non_self_contained_isolated_kubeconfig(self):
        packet = self.main_packet()
        kubeconfig = (
            "apiVersion: v1\ncurrent-context: isolated\n"
            "clusters:\n- name: isolated\n  cluster:\n    server: https://isolated.example\n"
            "users:\n- name: isolated\n  user:\n    exec:\n      command: credential-helper\n"
        )
        receipt = self.main_refusal(packet, kubeconfig)
        self.assertEqual(receipt["reason"], "isolated_kubeconfig_must_be_self_contained")

    def test_main_refuses_dispatch_inputs_not_bound_to_protected_packet(self):
        packet = self.main_packet()
        packet["proof"]["candidate_image"] = control.BASELINE
        kubeconfig = (
            "apiVersion: v1\ncurrent-context: isolated\n"
            "clusters:\n- name: isolated\n  cluster:\n    server: https://isolated.example\n"
            "users:\n- name: isolated\n  user:\n    token: fixture\n"
        )
        receipt = self.main_refusal(packet, kubeconfig)
        self.assertEqual(receipt["reason"], "dispatch_candidate_or_baseline_mismatch")

    def test_image_only_job_timeout_covers_rollout_and_receipt_work(self):
        workflow = (control.ROOT / ".github/workflows/gcp_backend_pusher.yml").read_text(encoding="utf-8")
        match = re.search(r"(?ms)^  pusher-image-only:\n(.*?)(?=^  [A-Za-z0-9_-]+:|\Z)", workflow)
        self.assertIsNotNone(match)
        timeout = re.search(r"(?m)^    timeout-minutes: (\d+)\s*$", match.group(1))
        self.assertIsNotNone(timeout)
        self.assertGreaterEqual(int(timeout.group(1)), control.ROLLOUT_TIMEOUT // 60 + 50)


if __name__ == "__main__":
    unittest.main()
