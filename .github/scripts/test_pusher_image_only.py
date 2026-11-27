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

import pusher_canary_inverse as inverse_script
import pusher_image_only as control
import pusher_image_rehearsal as helper
from pusher_release_receipt import config_fingerprint

SOURCE = "3" * 40
WORKFLOW_SHA = "a" * 40
CANARY_WORKFLOW_SHA = "d" * 40
REPO, DIGEST = ("gcr.io/based-hardware/pusher", "sha256:" + "b" * 64)
CANDIDATE = f"{REPO}@{DIGEST}"
PREVIEW_RUN = 41
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
        self.config_map = {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {"name": "prod-omi-backend-config", "uid": "configmap-uid", "resourceVersion": "1"},
            "data": {"STT_SERVICE_MODELS": "dg-nova-3,modulate-velma-2,parakeet"},
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
            return copy.deepcopy(self.config_map) if name == "prod-omi-backend-config" else None
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
            # A committed write moves resourceVersion, so a later guarded patch must re-read it.
            changed["metadata"]["resourceVersion"] = str(int(changed["metadata"]["resourceVersion"]) + 1)
            self.target = changed
        return copy.deepcopy(changed)


def live_patches(fake):
    return [ops for dry, ops in fake.requests if not dry and ops and ops[0]["op"] == "test"]


def packet_for(mode):
    packet = {
        "schema": 2,
        "mode": mode,
        "source_sha": SOURCE,
        "prior_image": control.BASELINE,
        "candidate_image": CANDIDATE,
        "qualification_run_id": 10,
    }
    if mode in {"canary", "promote"}:
        packet["reviewed_preview"] = {"run_id": PREVIEW_RUN}
        packet["canary"] = {"run_id": CANARY_RUN}
    return packet


def run_metadata(run_id, *, workflow=control.PROMOTION_WORKFLOW, event="workflow_dispatch", head_sha=WORKFLOW_SHA, **overrides):
    """GitHub `GET /actions/runs/{id}` shape, trimmed to the fields the verifier reads."""
    return {
        "id": run_id,
        "workflow_id": 18,
        "path": f".github/workflows/{workflow}",
        "event": event,
        "head_branch": "main",
        "head_sha": head_sha,
        "run_attempt": 1,
        "head_repository": {"full_name": control.REPO},
        "status": "completed",
        "conclusion": "success",
    } | overrides


def approvals(*entries):
    """GitHub `GET /actions/runs/{id}/approvals` shape."""
    return [
        {"state": state, "comment": "", "environments": [{"name": environment}], "user": {"login": login}}
        for state, environment, login in entries
    ]


class ImageOnlyTest(unittest.TestCase):
    def setUp(self):
        self.fake = FakeLive()
        self.live = control.ReadOnlyCluster(self.fake)
        self.writer = control.LiveWriter(self.fake)
        self.packet = packet_for("preview")
        self.command = self.enterContext(patch.object(control, "run", return_value=""))
        self.enterContext(patch.object(control, "check_qualification", return_value={"qualified": True}))
        self.enterContext(patch.object(control, "verify_canary_cleanup"))
        self.enterContext(patch.object(control, "check_capacity"))
        self.preview = self.enterContext(patch.object(control, "check_reviewed_preview", return_value={"live_baseline": ["deploy-uid", "11"]}))
        self.canary = self.enterContext(
            patch.object(
                control,
                "check_canary",
                side_effect=lambda *args: args[1].update(canary_run_id=CANARY_RUN, canary_inverse_receipt="PASS") or {"artifacts": True},
            )
        )
        self.environment = self.enterContext(
            patch.object(control, "check_effective_environment", side_effect=lambda _live, _artifacts, result: result.update(effective_environment="equal"))
        )
        self.ready = self.enterContext(
            patch.object(
                control,
                "verify_ready",
                side_effect=lambda _live, deployment, image, **_kwargs: {"deployment_uid": "deploy-uid", "generation": deployment["metadata"]["generation"], "ready_replicas": 3, "image": image},
            )
        )
        self.status_report = self.enterContext(patch.object(control, "deploy_status_report"))

    def result(self, mode):
        return {"mode": mode, "workflow_sha": WORKFLOW_SHA, "run_id": 100, **control.evidence_binding(self.packet)}

    def promote_packet(self):
        return packet_for("promote")

    def refuse(self, *, inverse_dry_run=True, reverse_live=False):
        def admit(_old, ops, dry):
            reverse = ops[3]["value"] == CANDIDATE and ops[4]["value"] == control.BASELINE
            if reverse and dry and inverse_dry_run:
                raise helper.Refused("server_dry_run_rejected")
            if reverse and not dry and reverse_live:
                raise helper.Refused("live_patch_unconfirmed_reconcile_before_retry")
            return None

        self.fake.admit = admit

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
        self.assertEqual(forward["effective_environment"], "equal")
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

    def test_promote_and_canary_refuse_when_the_effective_environment_differs(self):
        self.environment.side_effect = helper.Refused("effective_environment_differs")
        for mode in ("canary", "promote"):
            with self.subTest(mode=mode):
                packet = packet_for(mode)
                with self.assertRaisesRegex(helper.Refused, "effective_environment_differs"):
                    control.execute(mode, packet, self.live, self.result(mode), writer=self.writer if mode == "promote" else None)
        self.assertEqual(live_patches(self.fake), [])

    def test_refused_inverse_makes_one_fresh_reverse_and_verifies_the_baseline(self):
        self.refuse()
        result = self.result("promote")
        with self.assertRaises(control.Reversed):
            control.execute("promote", self.promote_packet(), self.live, result, writer=self.writer)
        forward, reverse = live_patches(self.fake)
        self.assertEqual(forward[-1]["value"], CANDIDATE)
        # Fresh preconditions: same UID, the post-move resourceVersion, the pusher
        # container and the candidate image, then the one replace to the baseline.
        self.assertEqual(
            reverse,
            [
                {"op": "test", "path": "/metadata/uid", "value": "deploy-uid"},
                {"op": "test", "path": "/metadata/resourceVersion", "value": "12"},
                {"op": "test", "path": "/spec/template/spec/containers/1/name", "value": "pusher"},
                {"op": "test", "path": "/spec/template/spec/containers/1/image", "value": CANDIDATE},
                {"op": "replace", "path": "/spec/template/spec/containers/1/image", "value": control.BASELINE},
            ],
        )
        self.assertEqual(helper.current_image(self.fake.target), control.BASELINE)
        self.assertEqual(result["reason"], "REFUSED_INVERSE_REVERSED")
        self.assertEqual(result["live_inverse_server_dry_run"], "REFUSED")
        self.assertEqual(result["serving_image"], control.BASELINE)
        self.assertEqual(self.ready.call_args.args[2], control.BASELINE)
        self.status_report.assert_called_with(strict=True)

    def test_refused_reverse_holds_and_makes_no_further_patches(self):
        self.refuse(reverse_live=True)
        result = self.result("promote")
        with self.assertRaises(control.Hold):
            control.execute("promote", self.promote_packet(), self.live, result, writer=self.writer)
        self.assertEqual(result["reason"], "REFUSED_INVERSE")
        self.assertEqual(result["stage"], "hold_refused_inverse")
        self.assertEqual(result["hold_stage"], "reverse_patch_failed")
        self.assertEqual(result["serving_image_observed"], CANDIDATE)
        self.assertIn("rollout undo", result["manual_restore_path"])
        self.assertEqual(helper.current_image(self.fake.target), CANDIDATE)
        # The forward patch and exactly one reverse attempt; nothing after it.
        self.assertEqual([ops[-1]["value"] for ops in live_patches(self.fake)], [CANDIDATE, control.BASELINE])
        self.assertEqual(len([dry for dry, ops in self.fake.requests if not dry]), 2)
        self.status_report.assert_called_once_with(strict=False)

    def test_unverified_reverse_serving_holds_without_another_patch(self):
        self.refuse()

        def ready(_live, deployment, image, **_kwargs):
            raise helper.Refused("pusher_replica_replacement_incomplete")

        self.ready.side_effect = ready
        result = self.result("promote")
        with self.assertRaises(control.Hold):
            control.execute("promote", self.promote_packet(), self.live, result, writer=self.writer)
        self.assertEqual((result["reason"], result["hold_stage"]), ("REFUSED_INVERSE", "reverse_serving_unverified"))
        self.assertEqual(result["serving_image_observed"], control.BASELINE)
        self.assertEqual(len(live_patches(self.fake)), 2)

    def test_reverse_refuses_to_patch_when_the_object_changed_after_the_move(self):
        self.refuse()
        original = self.fake.call

        def call(*args, **kwargs):
            value = original(*args, **kwargs)
            if "--dry-run=none" in args:
                self.fake.target = copy.deepcopy(self.fake.target)
                self.fake.target["metadata"]["uid"] = "replaced-uid"
            return value

        self.fake.call = call
        result = self.result("promote")
        with self.assertRaises(control.Hold):
            control.execute("promote", self.promote_packet(), self.live, result, writer=self.writer)
        self.assertEqual(result["reverse_refusal"], "reverse_preconditions_changed")
        self.assertEqual(len(live_patches(self.fake)), 1)

    def test_canary_verifies_the_recorded_inverse_and_never_writes(self):
        packet = packet_for("canary")
        result = self.result("canary")
        control.execute("canary", packet, self.live, result)
        self.assertEqual(result["canary_inverse_receipt"], "PASS")
        self.assertEqual(result["effective_environment"], "equal")
        self.preview.assert_called_once()
        self.assertEqual(helper.current_image(self.fake.target), control.BASELINE)
        self.assertTrue(all(dry for dry, _ in self.fake.requests))
        self.assertEqual(live_patches(self.fake), [])

    def test_read_only_modes_skip_the_deploy_status_gate(self):
        for mode in ("preview", "canary"):
            control.execute(mode, packet_for(mode), self.live, self.result(mode))
        self.status_report.assert_not_called()

    def test_success_paths_run_strict_deploy_status_gate_after_readiness(self):
        order = []
        ready = self.ready.side_effect
        self.ready.side_effect = lambda *args, **kwargs: order.append("ready") or ready(*args, **kwargs)
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


def canary_artifacts(live=None):
    live = live or FakeLive()
    return {
        "evidence": {"status": "PASS", "fixture": "canonical"},
        "deployment_receipt": {
            "run_id": CANARY_RUN,
            "source_sha": SOURCE,
            "image": {"repository": REPO, "digest": DIGEST},
            "config_sha256": config_fingerprint(live.config_map, expected_name="prod-omi-backend-config"),
            "live_identity": {"deployment_uid": "canary-uid"},
        },
        "semantic_receipt": {"status": "PASS"},
        "inverse_receipt": {
            "schema": 1,
            "status": "PASS",
            "run_id": CANARY_RUN,
            "workflow_sha": CANARY_WORKFLOW_SHA,
            "source_sha": SOURCE,
            "mode": "canary_only",
            "candidate_image": CANDIDATE,
            "baseline_image": control.BASELINE,
            "dry_run": "server",
            "live_deployment": {
                "name": control.TARGET,
                "uid": "deploy-uid",
                "template_sha256": inverse_script.template_sha256(live.target),
            },
            "template_parity": {
                "live_deployment": control.TARGET,
                "canary_deployment": f"prod-omi-pusher-canary-{CANARY_RUN}",
                "excluded": list(inverse_script.PARITY_EXCLUDED),
                "normalized": list(inverse_script.PARITY_NORMALIZED),
                "classes": {name: "equal" for name in control.PARITY_CLASSES},
            },
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


class EvidenceGateTest(unittest.TestCase):
    def setUp(self):
        self.packet = packet_for("promote")
        self.result = {"workflow_sha": WORKFLOW_SHA, "run_id": 100, **control.evidence_binding(self.packet)}
        self.metadata = run_metadata(CANARY_RUN, head_sha=CANARY_WORKFLOW_SHA)

    def canary_mocks(self, artifacts, *, validation=None, approved=("Git-on-my-level",)):
        return (
            patch.object(control, "workflow_run_metadata", return_value=self.metadata),
            patch.object(control, "download_canary", return_value=artifacts),
            patch.object(control, "_validate_canary", return_value=validation),
            patch.object(control, "run_approvals", return_value=list(approved)),
            patch.object(control, "accepted_workflow_revision"),
        )

    def test_check_canary_binds_run_evidence_approval_and_recorded_inverse(self):
        artifacts = canary_artifacts()
        fetch, download, validate, approvals_, revision = self.canary_mocks(artifacts)
        with fetch as fetched, download, validate as validated, approvals_ as approved, revision as accepted:
            self.assertIs(control.check_canary(self.packet, self.result, {"deployment": "qualified"}), artifacts)
        fetched.assert_called_once_with(CANARY_RUN, control.PROMOTION_WORKFLOW)
        accepted.assert_called_once_with(CANARY_WORKFLOW_SHA, WORKFLOW_SHA)
        approved.assert_called_once_with(CANARY_RUN)
        self.assertEqual(validated.call_args.kwargs["expected_canary_workflow_sha"], CANARY_WORKFLOW_SHA)
        self.assertEqual(self.result["canary_run_id"], CANARY_RUN)
        self.assertEqual(self.result["canary_workflow_sha"], CANARY_WORKFLOW_SHA)
        self.assertEqual(self.result["approvals"], {"canary": ["Git-on-my-level"]})
        self.assertEqual(self.result["canary_inverse_receipt"], "PASS")

    def test_check_canary_refuses_each_unbound_path(self):
        cases = (
            ("wrong-image", "wrong_canary_image"),
            ("wrong-source", "canary_source_sha_mismatch"),
            ("noncanonical-evidence", "canonical_canary_refused"),
            ("wrong-inverse", "canary_inverse_receipt_refused"),
            ("wrong-inverse-mode", "canary_inverse_receipt_refused"),
            ("wrong-inverse-workflow", "canary_inverse_receipt_refused"),
            ("missing-parity", "canary_inverse_receipt_refused"),
            ("missing-catch-all", "canary_inverse_receipt_refused"),
            ("missing-live-binding", "canary_inverse_receipt_refused"),
        )
        for case, reason in cases:
            with self.subTest(case=case):
                artifacts = canary_artifacts()
                inverse = artifacts["inverse_receipt"]
                validation = None
                if case == "wrong-image":
                    artifacts["deployment_receipt"]["image"]["digest"] = "sha256:" + "f" * 64
                elif case == "wrong-source":
                    artifacts["deployment_receipt"]["source_sha"] = "f" * 40
                elif case == "noncanonical-evidence":
                    validation = ["canary_digest_mismatch"]
                elif case == "wrong-inverse-mode":
                    inverse["mode"] = "deploy"
                elif case == "wrong-inverse-workflow":
                    inverse["workflow_sha"] = WORKFLOW_SHA
                elif case == "missing-parity":
                    inverse["template_parity"]["classes"]["container_env"] = "unknown"
                elif case == "missing-catch-all":
                    del inverse["template_parity"]["classes"]["other_template_fields"]
                elif case == "missing-live-binding":
                    del inverse["live_deployment"]
                else:
                    inverse["preconditions"]["container"] = "listener"
                mocks = self.canary_mocks(artifacts, validation=validation)
                with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], self.assertRaisesRegex(helper.Refused, reason):
                    control.check_canary(self.packet, self.result, {"deployment": "qualified"})

    def test_check_canary_refuses_without_a_prod_approval_or_at_a_changed_revision(self):
        for failure, reason in (
            ("run_approvals", "prod_environment_approval_missing"),
            ("accepted_workflow_revision", "evidence_workflow_revision_changed"),
        ):
            with self.subTest(failure=failure):
                mocks = self.canary_mocks(canary_artifacts())
                with mocks[0], mocks[1], mocks[2], mocks[3], mocks[4], patch.object(
                    control, failure, side_effect=helper.Refused(reason)
                ), self.assertRaisesRegex(helper.Refused, reason):
                    control.check_canary(self.packet, self.result, {"deployment": "qualified"})

    def produce_preview_receipt(self):
        """Run the real preview producer (main) end to end on the cluster fake."""
        fake = FakeLive()
        packet = packet_for("preview")
        env = {
            "IMAGE_ONLY_MODE": "preview",
            "GITHUB_WORKFLOW_SHA": WORKFLOW_SHA,
            "GITHUB_RUN_ID": str(PREVIEW_RUN),
            "PUSHER_IMAGE_ONLY_EVIDENCE": json.dumps(packet),
            "SOURCE_SHA": SOURCE,
            "QUALIFICATION_RUN_ID": "10",
            "REQUESTED_DIGEST": DIGEST,
            "KUBECONFIG": "live-kubeconfig",
            "LIVE_CONTEXT": "live",
        }
        with (
            patch.dict(os.environ, env),
            patch.object(control, "workflow_run_metadata", return_value=run_metadata(PREVIEW_RUN, status="in_progress")),
            patch.object(control, "run_approvals", return_value=["Git-on-my-level"]),
            patch.object(control, "check_qualification", return_value={"qualified": True}),
            patch.object(control, "run", return_value=""),
            patch.object(control, "Cluster", return_value=fake),
            patch("builtins.print") as output,
        ):
            self.assertEqual(control.main(), 0)
        return json.loads(output.call_args.args[0])

    def consume(self, receipt, *, head_sha=WORKFLOW_SHA):
        def download(args, reason):
            self.assertEqual((args[:3], reason), (["gh", "run", "download"], "protected_run_receipt_unavailable"))
            (Path(args[args.index("--dir") + 1]) / "receipt.json").write_text(json.dumps(receipt), encoding="utf-8")
            return ""

        with (
            patch.object(control, "workflow_run_metadata", return_value=run_metadata(PREVIEW_RUN, head_sha=head_sha)) as fetch,
            patch.object(control, "run_approvals", return_value=["Git-on-my-level"]),
            patch.object(control, "accepted_workflow_revision") as accepted,
            patch.object(control, "run", side_effect=download),
        ):
            preview = control.check_reviewed_preview(self.packet, self.result)
        fetch.assert_called_once_with(PREVIEW_RUN, control.PROMOTION_WORKFLOW)
        accepted.assert_called_once_with(head_sha, WORKFLOW_SHA)
        return preview

    def test_promote_consumes_the_real_preview_producer_receipt(self):
        receipt = self.produce_preview_receipt()
        self.assertNotIn("proof_id", receipt)
        self.assertNotIn("release_approval", receipt)
        self.assertEqual(receipt["approvals"], {"current": ["Git-on-my-level"]})
        preview = self.consume(receipt)
        self.assertEqual(preview["live_baseline"], ["deploy-uid", "11"])
        self.assertEqual(self.result["approvals"], {"preview": ["Git-on-my-level"]})
        self.assertEqual(self.result["reviewed_preview_run_id"], PREVIEW_RUN)

    def test_reviewed_preview_refuses_an_unbound_or_incomplete_receipt(self):
        receipt = self.produce_preview_receipt()
        for overrides, reason in (
            ({"live_baseline_server_dry_run": "REFUSED"}, "reviewed_forward_preview_missing"),
            ({"binding_sha256": "f" * 64}, "reviewed_forward_preview_missing"),
            ({"candidate_image": f"{REPO}@sha256:" + "f" * 64}, "reviewed_forward_preview_missing"),
            ({"workflow_sha": "c" * 40}, "reviewed_forward_preview_missing"),
            ({"mode": "canary"}, "reviewed_forward_preview_missing"),
            ({"run_id": PREVIEW_RUN + 1}, "protected_run_receipt_refused"),
        ):
            with self.subTest(overrides=overrides), self.assertRaisesRegex(helper.Refused, reason):
                self.consume(receipt | overrides)

    def test_validate_packet_requires_exact_ids_only_shape_and_binds_dispatch_at_runtime(self):
        dispatch = {"id": 100, "status": "in_progress", "conclusion": None}
        with patch.object(control, "workflow_run_metadata", return_value=dispatch) as fetch:
            control.validate_packet(self.packet, "promote", WORKFLOW_SHA, 100)
            control.validate_packet(packet_for("rollback"), "rollback", WORKFLOW_SHA, 100)
        fetch.assert_called_with(100, control.PROMOTION_WORKFLOW, expected_sha=WORKFLOW_SHA, require_success=False)

        mutations = (
            ("run_id", lambda packet: packet.update(run_id=100)),
            ("mode", lambda packet: packet.update(mode="preview")),
            ("schema", lambda packet: packet.update(schema=1)),
            ("candidate_image", lambda packet: packet.update(candidate_image=control.BASELINE)),
            ("release_approval", lambda packet: packet.update(release_approval="release-approval")),
            ("review_id", lambda packet: packet["reviewed_preview"].update(review_id="review-41")),
            ("preservation_review", lambda packet: packet["canary"].update(preservation_review={"id": "x"})),
            ("canary_workflow_sha", lambda packet: packet["canary"].update(workflow_sha="d" * 40)),
            ("self_reference", lambda packet: packet["canary"].update(run_id=100)),
            ("same_preview_and_canary", lambda packet: packet["canary"].update(run_id=PREVIEW_RUN)),
            ("missing_canary", lambda packet: packet.pop("canary")),
        )
        for name, mutate in mutations:
            with self.subTest(mutation=name):
                packet = json.loads(json.dumps(self.packet))
                mutate(packet)
                with patch.object(control, "workflow_run_metadata", return_value=dispatch), self.assertRaises(helper.Refused):
                    control.validate_packet(packet, "promote", WORKFLOW_SHA, 100)

    def metadata_answers(self, metadata, workflow_ids):
        def answer(args, reason):
            if reason == "evidence_workflow_unavailable":
                return str(workflow_ids[args[2].rsplit("/", 1)[1]])
            return json.dumps(metadata)

        return patch.object(control, "run", side_effect=answer)

    def test_workflow_run_metadata_accepts_the_push_qualifier_and_dispatched_promotions(self):
        # Shaped like run 45961874722: the automatic development qualifier on push to main.
        qualification = run_metadata(
            45961874722,
            workflow=control.QUALIFICATION_WORKFLOW,
            event="push",
            head_sha=SOURCE,
            workflow_id=220336364,
        )
        ids = {control.QUALIFICATION_WORKFLOW: 220336364, control.PROMOTION_WORKFLOW: 18}
        with self.metadata_answers(qualification, ids):
            self.assertEqual(
                control.workflow_run_metadata(45961874722, control.QUALIFICATION_WORKFLOW, expected_sha=SOURCE), qualification
            )
        with self.metadata_answers(qualification | {"run_attempt": 2}, ids):
            control.workflow_run_metadata(45961874722, control.QUALIFICATION_WORKFLOW, expected_sha=SOURCE)
        promotion = run_metadata(42)
        with self.metadata_answers(promotion, ids):
            self.assertEqual(control.workflow_run_metadata(42, control.PROMOTION_WORKFLOW, expected_sha=WORKFLOW_SHA), promotion)
            self.assertEqual(control.workflow_run_metadata(42, control.PROMOTION_WORKFLOW), promotion)

    def test_workflow_run_metadata_refuses_the_wrong_event_attempt_workflow_or_source(self):
        ids = {control.QUALIFICATION_WORKFLOW: 220336364, control.PROMOTION_WORKFLOW: 18}
        qualification = run_metadata(
            7, workflow=control.QUALIFICATION_WORKFLOW, event="push", head_sha=SOURCE, workflow_id=220336364
        )
        promotion = run_metadata(42)
        cases = (
            (qualification | {"event": "workflow_dispatch"}, control.QUALIFICATION_WORKFLOW, SOURCE),
            (qualification | {"path": ".github/workflows/gcp_backend_pusher.yml"}, control.QUALIFICATION_WORKFLOW, SOURCE),
            (qualification | {"head_branch": "feature"}, control.QUALIFICATION_WORKFLOW, SOURCE),
            (promotion | {"event": "push"}, control.PROMOTION_WORKFLOW, WORKFLOW_SHA),
            (promotion | {"run_attempt": 2}, control.PROMOTION_WORKFLOW, WORKFLOW_SHA),
            (promotion | {"head_sha": "b" * 40}, control.PROMOTION_WORKFLOW, WORKFLOW_SHA),
            (promotion | {"conclusion": "failure"}, control.PROMOTION_WORKFLOW, WORKFLOW_SHA),
            (promotion | {"workflow_id": 19}, control.PROMOTION_WORKFLOW, WORKFLOW_SHA),
            (promotion | {"head_repository": {"full_name": "other/repo"}}, control.PROMOTION_WORKFLOW, WORKFLOW_SHA),
        )
        for metadata, workflow, sha in cases:
            with self.subTest(metadata=metadata), self.metadata_answers(metadata, ids), self.assertRaises(helper.Refused):
                control.workflow_run_metadata(metadata["id"], workflow, expected_sha=sha)

    def test_run_approvals_resolves_prod_reviewers_from_the_api(self):
        def answer(value):
            return patch.object(control, "run", return_value=json.dumps(value))

        with answer(approvals(("approved", "prod", "Git-on-my-level"))) as call:
            self.assertEqual(control.run_approvals(42), ["Git-on-my-level"])
        self.assertEqual(call.call_args.args[0], ["gh", "api", f"repos/{control.REPO}/actions/runs/42/approvals"])
        for value in (
            [],
            approvals(("approved", "development", "Git-on-my-level")),
            approvals(("approved", "prod", "Git-on-my-level"), ("rejected", "prod", "someone")),
            {"message": "Not Found"},
        ):
            with self.subTest(value=value), answer(value), self.assertRaises(helper.Refused):
                control.run_approvals(42)

    def test_accepted_workflow_revision_requires_identical_evidence_controls(self):
        with patch.object(control, "run", return_value="") as call:
            control.accepted_workflow_revision(WORKFLOW_SHA, WORKFLOW_SHA)
            call.assert_not_called()
            control.accepted_workflow_revision(CANARY_WORKFLOW_SHA, WORKFLOW_SHA)
        ancestry, diff = (entry.args for entry in call.call_args_list)
        self.assertEqual(ancestry[0][-3:], ["--is-ancestor", CANARY_WORKFLOW_SHA, WORKFLOW_SHA])
        self.assertEqual(diff[0][-len(control.CONTROL_PATHS) - 1 :], ["--", *control.CONTROL_PATHS])
        self.assertIn(".github/scripts/pusher_canary_inverse.py", control.CONTROL_PATHS)

        def changed(args, reason):
            if "diff" in args:
                raise helper.Refused(reason)
            return ""

        with patch.object(control, "run", side_effect=changed), self.assertRaisesRegex(helper.Refused, "evidence_workflow_revision_changed"):
            control.accepted_workflow_revision(CANARY_WORKFLOW_SHA, WORKFLOW_SHA)

    def test_effective_environment_compares_config_and_template_redacted(self):
        fake = FakeLive()
        result = {}
        control.check_effective_environment(control.ReadOnlyCluster(fake), canary_artifacts(fake), result)
        self.assertEqual(
            result["effective_environment"],
            {"runtime_config_map": "equal", "pod_template": "equal", "live_template_since_canary": "equal"},
        )

    def test_effective_environment_refuses_each_difference_without_values(self):
        def config_changed(fake, _artifacts):
            fake.config_map["data"]["STT_SERVICE_MODELS"] = "private-value"

        def parity_differs(_fake, artifacts):
            artifacts["inverse_receipt"]["template_parity"]["classes"]["other_template_fields"] = "differs"

        def template_changed(fake, _artifacts):
            fake.target["spec"]["template"]["spec"]["hostNetwork"] = True

        for mutate, field in (
            (config_changed, "runtime_config_map"),
            (parity_differs, "pod_template"),
            (template_changed, "live_template_since_canary"),
        ):
            with self.subTest(field=field):
                fake = FakeLive()
                artifacts = canary_artifacts(fake)
                mutate(fake, artifacts)
                result = {}
                with self.assertRaisesRegex(helper.Refused, "effective_environment_differs"):
                    control.check_effective_environment(control.ReadOnlyCluster(fake), artifacts, result)
                self.assertEqual(result["effective_environment"][field], "differs")
                self.assertEqual({value for value in result["effective_environment"].values()} - {"equal", "differs"}, set())
                self.assertNotIn("private-value", json.dumps(result))

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

    def test_download_canary_reads_the_evidence_and_the_separate_inverse_artifact(self):
        names = []

        def download(args, _reason):
            artifact = args[args.index("-n") + 1]
            names.append(artifact)
            directory = Path(args[args.index("--dir") + 1])
            files = (
                ["pusher-prod-canary-inverse-receipt.json"]
                if artifact == control.INVERSE_ARTIFACT
                else ["pusher-prod-canary-evidence.json", "pusher-prod-canary-deployment-receipt.json", "pusher-prod-canary-semantic-probe.json"]
            )
            for name in files:
                (directory / name).write_text(json.dumps({"file": name}), encoding="utf-8")
            return ""

        with patch.object(control, "run", side_effect=download):
            artifacts = control.download_canary(42)
        self.assertEqual(names, [control.CANARY_ARTIFACT, control.INVERSE_ARTIFACT])
        self.assertEqual(artifacts["inverse_receipt"], {"file": "pusher-prod-canary-inverse-receipt.json"})
        self.assertEqual(set(artifacts), {"evidence", "deployment_receipt", "semantic_receipt", "inverse_receipt"})

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
        self.packet = packet_for("preview")
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

    def run_main(self, *, execute=None, env=None, approvers=("Git-on-my-level",)):
        def default_execute(_mode, _packet, _live, result, *, writer=None):
            self.assertIsNotNone(writer) if _mode in {"promote", "rollback"} else self.assertIsNone(writer)
            result["stage"] = "deploy_status_report"
            control.deploy_status_report(strict=True)

        approval = (
            patch.object(control, "run_approvals", return_value=list(approvers))
            if approvers
            else patch.object(control, "run_approvals", side_effect=helper.Refused("prod_environment_approval_missing"))
        )
        with (
            patch.dict(os.environ, env or self.env),
            patch.object(control, "workflow_run_metadata", return_value={"id": 100, "status": "in_progress"}),
            approval,
            patch.object(control, "Cluster"),
            patch.object(control, "execute", side_effect=execute or default_execute),
            patch.object(control.subprocess, "run", return_value=SimpleNamespace(returncode=1)),
            patch("builtins.print") as output,
        ):
            code = control.main()
        return code, json.loads(output.call_args.args[0])

    def promote_env(self):
        return dict(self.env, IMAGE_ONLY_MODE="promote", PUSHER_IMAGE_ONLY_EVIDENCE=json.dumps(packet_for("promote")))

    def test_main_binds_the_dispatch_run_and_its_api_approval(self):
        code, receipt = self.run_main(
            execute=lambda _mode, _packet, _live, result, *, writer=None: result.update(stage="deploy_status_report"),
            env=self.promote_env(),
        )
        self.assertEqual((code, receipt["status"], receipt["run_id"]), (0, "PASS", 100))
        self.assertEqual(receipt["approvals"], {"current": ["Git-on-my-level"]})
        self.assertEqual(receipt["binding_sha256"], control.evidence_binding(packet_for("promote"))["binding_sha256"])
        self.assertNotIn("proof_id", receipt)
        self.assertEqual(receipt["source_sha"], SOURCE)

    def test_main_refuses_without_a_prod_approval_of_this_run(self):
        code, receipt = self.run_main(approvers=())
        self.assertEqual((code, receipt["reason"]), (1, "prod_environment_approval_missing"))

    def test_main_refuses_a_packet_that_names_its_own_run(self):
        env = dict(self.env, PUSHER_IMAGE_ONLY_EVIDENCE=json.dumps(self.packet | {"run_id": 100}))
        code, receipt = self.run_main(env=env)
        self.assertEqual((code, receipt["reason"]), (1, "protected_evidence_mismatch"))

    def test_main_refuses_dispatch_inputs_not_bound_to_the_evidence(self):
        code, receipt = self.run_main(env=dict(self.env, REQUESTED_DIGEST="sha256:" + "f" * 64))
        self.assertEqual((code, receipt["reason"]), (1, "dispatch_evidence_mismatch"))

    def test_main_reports_hold_and_reversed_outcomes(self):
        for error, status, reason in (
            (control.Hold("REFUSED_INVERSE"), "HOLD", "REFUSED_INVERSE"),
            (control.Reversed("REFUSED_INVERSE_REVERSED"), "REVERSED", "REFUSED_INVERSE_REVERSED"),
        ):
            with self.subTest(status=status):
                code, receipt = self.run_main(
                    execute=lambda _mode, _packet, _live, result, *, writer=None, error=error: (_ for _ in ()).throw(error),
                    env=self.promote_env(),
                )
                self.assertEqual((code, receipt["status"], receipt["reason"]), (1, status, reason))

    def image_only_job(self):
        workflow = (control.ROOT / ".github/workflows/gcp_backend_pusher.yml").read_text(encoding="utf-8")
        match = re.search(r"(?ms)^  pusher-image-only:\n(.*?)(?=^  [A-Za-z0-9_-]+:|\Z)", workflow)
        self.assertIsNotNone(match)
        return match.group(1)

    def test_image_only_job_timeout_covers_rollout_and_receipt_work(self):
        timeout = re.search(r"(?m)^    timeout-minutes: (\d+)\s*$", self.image_only_job())
        self.assertIsNotNone(timeout)
        # Forward rollout plus one reverse rollout, and the receipt work around them.
        self.assertGreaterEqual(int(timeout.group(1)), 2 * (control.ROLLOUT_TIMEOUT // 60) + 25)
        self.assertLessEqual(int(timeout.group(1)), 360)

    def test_image_only_job_has_no_packet_or_isolated_secret(self):
        job = self.image_only_job()
        self.assertNotIn("PUSHER_IMAGE_ONLY_PACKET", job)
        self.assertNotIn("PUSHER_IMAGE_ONLY_ISOLATED_KUBECONFIG", job)
        self.assertIn("inputs.pusher_image_only_evidence", job)

    def test_hold_escalation_uses_existing_credentials_and_carries_the_restore_path(self):
        job = self.image_only_job()
        permissions = re.search(r"(?ms)^    permissions:\n(.*?)^    \S", job).group(1)
        # Approvals are read with actions: read; no issue is opened, so no issues: write.
        self.assertIn("actions: read", permissions)
        self.assertNotIn("issues", permissions)
        self.assertNotIn("gh issue create", job)
        notifier = job.split("- name: Notify Release of the held inverse", 1)[1].split("- name:", 1)[0]
        self.assertIn("rollout undo deployment/prod-omi-pusher", notifier)
        self.assertIn("rollout status", notifier)
        summary = job.split("- name: Summarize the held or reversed inverse", 1)[1].split("- name:", 1)[0]
        self.assertIn("GITHUB_STEP_SUMMARY", summary)
        self.assertIn("manual_restore_path", summary)
        self.assertIn("REFUSED_INVERSE_REVERSED", job)


class CanaryOnlyWorkflowTest(unittest.TestCase):
    """The canary_only stop is the canary evidence producer for the image-only promote."""

    PROMOTE_STEPS = (
        "Apply non-secret pusher runtime config",
        "Verify reconciled pusher ConfigMap and Secret references",
        "Verify live Pusher surge capacity and digest render",
        "Deploy Pusher to GKE cluster using Helm",
        "Record exact live production Pusher deployment receipt",
        "Reverify live finalization alert route after production rollout",
        "Verify final production Pusher matches the canary-qualified candidate",
        "Upload exact live production Pusher deployment receipt",
        "Generate deployment summary",
        "Notify deployment status on Telegram",
    )

    def setUp(self):
        self.text = (control.ROOT / ".github/workflows/gcp_backend_pusher.yml").read_text(encoding="utf-8")
        deploy = self.text.split("\n  deploy:\n", 1)[1].split("\n  pusher-image-only:", 1)[0]
        self.job = deploy
        self.blocks = {}
        for block in re.split(r"\n      - name: ", deploy):
            name, _, rest = block.partition("\n")
            self.blocks[name.strip()] = rest

    def test_new_dispatch_input_and_job_stop(self):
        inputs = self.text.split("workflow_dispatch:", 1)[1].split("\n# ", 1)[0]
        self.assertIn("pusher_canary_only:", inputs)
        self.assertIn("type: boolean", inputs)
        self.assertIn("CANARY_ONLY: ${{ inputs.pusher_canary_only }}", self.job)

    def test_every_promote_step_is_gated_but_canary_steps_are_not(self):
        for name in self.PROMOTE_STEPS:
            with self.subTest(step=name):
                self.assertIn(name, self.blocks)
                self.assertIn("env.CANARY_ONLY != 'true'", self.blocks[name])
        for name in (
            "Create isolated production Pusher and listener canary",
            "Prove the canary inverse admission at one replica",
            "Upload protected production Pusher canary evidence",
            "Upload the canary inverse receipt",
            "Remove isolated production Pusher canary",
        ):
            with self.subTest(step=name):
                self.assertIn(name, self.blocks)
                self.assertNotIn("env.CANARY_ONLY != 'true'", self.blocks[name])

    def test_stop_sits_after_canary_cleanup_and_before_shared_config(self):
        order = [
            "Create isolated production Pusher and listener canary",
            "Prove the canary inverse admission at one replica",
            "Remove isolated production Pusher canary",
            "Apply non-secret pusher runtime config",
        ]
        offsets = [self.job.index(name) for name in order]
        self.assertEqual(offsets, sorted(offsets))

    def test_canary_inverse_runs_only_on_the_canary_only_producer(self):
        # A regular deploy can redeploy the serving image (baseline == candidate);
        # the inverse must not run, fail or gate that path.
        for name in ("Prove the canary inverse admission at one replica", "Upload the canary inverse receipt"):
            with self.subTest(step=name):
                condition = re.search(r"(?m)^        if: (.*)$", self.blocks[name]).group(1)
                self.assertTrue(condition.endswith("&& inputs.pusher_canary_only"), condition)
        inverse = self.blocks["Prove the canary inverse admission at one replica"]
        self.assertIn('--workflow-sha "$GITHUB_WORKFLOW_SHA"', inverse)
        self.assertIn('--canary-config-map "$PUSHER_CANARY_CONFIG"', inverse)
        self.assertNotIn("--mode", inverse)
        # The shared canary evidence artifact must not require the canary_only receipt.
        shared = self.blocks["Upload protected production Pusher canary evidence"]
        self.assertNotIn("pusher-prod-canary-inverse-receipt.json", shared)
        self.assertIn(f"name: {control.INVERSE_ARTIFACT}", self.blocks["Upload the canary inverse receipt"])

    def test_canary_only_validates_production_pusher_inputs(self):
        validation = self.text.split("Validate Environment Input", 1)[1]
        self.assertIn("CANARY_ONLY_INPUT", validation)
        self.assertIn("canary_only requires a prod Pusher dispatch", validation)


if __name__ == "__main__":
    unittest.main()
