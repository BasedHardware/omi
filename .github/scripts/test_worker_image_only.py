"""Offline behavioral fixtures for the SCA-2149 preservation primitive."""

import copy
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
import subprocess

import yaml

import worker_image_only as worker


OLD = worker.REPOSITORY + "@sha256:" + "1" * 64
NEW = worker.REPOSITORY + "@sha256:" + "2" * 64


def deployment(name=worker.TARGET):
    return {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {"name": name, "namespace": worker.NAMESPACE, "uid": name + "-uid", "resourceVersion": "17"},
        "spec": {
            "replicas": 8,
            "strategy": {"type": "Recreate"},
            "selector": {"matchLabels": {"app": name}},
            "template": {
                "metadata": {"annotations": {"operator-owned": "preserve"}, "labels": {"app": name}},
                "spec": {
                    "serviceAccountName": "existing-worker",
                    "terminationGracePeriodSeconds": 1500,
                    "nodeSelector": {"pool": "gpu"},
                    "tolerations": [{"key": "gpu", "operator": "Exists", "effect": "NoSchedule"}],
                    "affinity": {"nodeAffinity": {"preferredDuringSchedulingIgnoredDuringExecution": []}},
                    "volumes": [{"name": "runtime", "secret": {"secretName": "existing"}}],
                    "containers": [
                        {
                            "name": "worker",
                            "image": OLD,
                            "env": [
                                {"name": "FIRESTORE_READ_LEVERS", "value": "{}"},
                                {"name": "PRIVATE", "value": "do-not-print-this"},
                                {"name": "TOKEN", "valueFrom": {"secretKeyRef": {"name": "existing", "key": "token"}}},
                            ],
                            "resources": {"limits": {"nvidia.com/gpu": "1", "memory": "32Gi"}},
                            "volumeMounts": [{"name": "runtime", "mountPath": "/runtime", "readOnly": True}],
                        }
                    ],
                },
            },
        },
    }


class Cluster:
    """Execute real JSON-patch tests/replacement against a mutable fake API object."""

    def __init__(self):
        self.target = deployment()
        self.siblings = [deployment("record-seal-worker"), deployment(worker.TARGET + "-t4")]
        self.siblings[-1]["spec"]["replicas"] = 0
        self.writes = 0
        self.drift_on_patch = False
        self.consumer_reads = 0
        self.drift_on_consumer_read = 0
        self.admission_mutates = False

    def __call__(self, *args):
        if args[0] == "get":
            if args[1] == "deployment":
                return copy.deepcopy(self.target)
            self.consumer_reads += 1
            if self.consumer_reads == self.drift_on_consumer_read:
                self.siblings[0]["spec"]["replicas"] += 1
            return {"items": copy.deepcopy([self.target, *self.siblings])}
        if self.drift_on_patch and "--dry-run=server" not in args:
            self.target["metadata"]["resourceVersion"] = "18"
        patch = json.loads(args[args.index("-p") + 1])
        candidate = copy.deepcopy(self.target)
        for op in patch:
            parent = candidate
            parts = op["path"].strip("/").split("/")
            for key in parts[:-1]:
                parent = parent[int(key)] if isinstance(parent, list) else parent[key]
            key = parts[-1]
            if op["op"] == "test":
                if parent[key] != op["value"]:
                    raise ValueError("API conflict")
            else:
                parent[key] = op["value"]
        if self.admission_mutates:
            candidate["spec"]["replicas"] = 2
        if "--dry-run=server" not in args:
            self.target = candidate
            self.writes += 1
        return copy.deepcopy(candidate)


class PreservationTests(unittest.TestCase):
    def setUp(self):
        self.cluster = Cluster()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.receipt_path = Path(self.tmp.name) / "receipt.json"
        self.baseline = worker.snapshot(self.cluster)[1]

    def deploy(self):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            receipt = worker.deploy(self.baseline, NEW, self.receipt_path, self.cluster)
        self.output = output.getvalue()
        return receipt

    def test_only_image_changes_and_empty_levers_valuefrom_and_all_runtime_fields_survive(self):
        original = copy.deepcopy(self.cluster.target)
        siblings = copy.deepcopy(self.cluster.siblings)
        receipt = self.deploy()
        worker.verify(receipt, self.cluster)
        self.cluster.target["spec"]["template"]["spec"]["containers"][0]["image"] = OLD
        self.assertEqual(original, self.cluster.target)
        self.assertEqual(siblings, self.cluster.siblings)
        self.assertEqual(self.cluster.writes, 1)
        self.assertNotIn("do-not-print-this", self.output + self.receipt_path.read_text())
        self.assertNotIn("secretKeyRef", self.output + self.receipt_path.read_text())

    def test_rollback_reconstitutes_exact_prior_spec_with_fresh_cas(self):
        before = copy.deepcopy(self.cluster.target["spec"])
        receipt = self.deploy()
        self.cluster.target["metadata"]["resourceVersion"] = "99"  # rollout status updates are normal
        baseline = worker.snapshot(self.cluster)[1]
        with contextlib.redirect_stdout(io.StringIO()):
            reverse = worker.deploy(baseline, OLD, self.receipt_path, self.cluster, rollback_receipt=receipt)
        worker.verify(reverse, self.cluster)
        self.assertEqual(self.cluster.writes, 2)
        self.assertEqual(self.cluster.target["spec"], before)

    def test_target_spec_drift_refuses_before_write(self):
        self.cluster.target["spec"]["replicas"] = 7
        with self.assertRaisesRegex(ValueError, "drift"):
            self.deploy()
        self.assertEqual(self.cluster.writes, 0)

    def test_concurrent_write_is_atomically_rejected_by_cas(self):
        self.cluster.drift_on_patch = True
        with self.assertRaisesRegex(ValueError, "API conflict"):
            self.deploy()
        self.assertEqual(self.cluster.writes, 0)

    def test_admission_dry_run_cannot_change_runtime_configuration(self):
        self.cluster.admission_mutates = True
        with self.assertRaisesRegex(ValueError, "admission dry-run"):
            self.deploy()
        self.assertEqual(self.cluster.writes, 0)

    def test_sibling_drift_immediately_before_patch_refuses(self):
        self.cluster.drift_on_consumer_read = self.cluster.consumer_reads + 3
        with self.assertRaisesRegex(ValueError, "consumer drift"):
            self.deploy()
        self.assertEqual(self.cluster.writes, 0)

    def test_unaccounted_shared_consumers_refuse(self):
        self.cluster.siblings.append(deployment("new-repair-consumer"))
        with self.assertRaisesRegex(ValueError, "drift"):
            self.deploy()
        self.assertEqual(self.cluster.writes, 0)

    def test_wrong_namespace_name_kind_strategy_container_and_mutable_image_refuse(self):
        for mutate in (
            lambda o: o["metadata"].update(namespace="dev-omi-backend"),
            lambda o: o["metadata"].update(name="wrong"),
            lambda o: o.update(kind="StatefulSet"),
            lambda o: o["spec"]["strategy"].update(type="RollingUpdate"),
            lambda o: o["spec"]["template"]["spec"]["containers"].append(copy.deepcopy(o["spec"]["template"]["spec"]["containers"][0])),
            lambda o: o["spec"]["template"]["spec"]["containers"][0].update(name="not-worker"),
            lambda o: o["spec"]["template"]["spec"]["containers"][0].update(image=worker.REPOSITORY + ":main"),
        ):
            with self.subTest(mutate=mutate):
                self.cluster.target = deployment()
                mutate(self.cluster.target)
                with self.assertRaises(ValueError):
                    self.deploy()
                self.assertEqual(self.cluster.writes, 0)

    def test_invalid_candidate_and_already_serving_refuse(self):
        for image in (OLD, worker.REPOSITORY + ":latest", "gcr.io/other@sha256:" + "2" * 64):
            with self.subTest(image=image), self.assertRaises(ValueError):
                worker.deploy(self.baseline, image, self.receipt_path, self.cluster)
        self.assertEqual(self.cluster.writes, 0)

    def test_active_t4_and_required_companion_cannot_be_silently_left_old(self):
        self.cluster.siblings[-1]["spec"]["replicas"] = 1
        self.baseline = worker.snapshot(self.cluster)[1]
        with self.assertRaisesRegex(ValueError, "active T4"):
            self.deploy()
        self.cluster.siblings[-1]["spec"]["replicas"] = 0
        self.cluster.target["metadata"]["annotations"] = {"omi.ai/required-companion-deployment": "record-seal-worker"}
        self.baseline = worker.snapshot(self.cluster)[1]
        with self.assertRaisesRegex(ValueError, "required companion"):
            self.deploy()
        self.assertEqual(self.cluster.writes, 0)

    def test_verify_and_rollback_fail_on_runtime_or_sibling_drift(self):
        receipt = self.deploy()
        self.cluster.target["spec"]["template"]["spec"]["containers"][0]["env"][0]["value"] = '{"changed":1}'
        with self.assertRaisesRegex(ValueError, "drift"):
            worker.verify(receipt, self.cluster)
        with self.assertRaisesRegex(ValueError, "drift"):
            worker.deploy({"target": receipt["after"], "consumers": receipt["consumers"]}, OLD, self.receipt_path, self.cluster, rollback_receipt=receipt)

    def test_rollback_refuses_forged_image_baseline_and_prior_spec(self):
        receipt = self.deploy()
        baseline = worker.snapshot(self.cluster)[1]
        for changed_receipt, image, changed_baseline in (
            (receipt, NEW, baseline),
            ({**receipt, "before": {**receipt["before"], "spec_sha256": "forged"}}, OLD, baseline),
            (receipt, OLD, {**baseline, "consumers": []}),
        ):
            with self.subTest(image=image), self.assertRaises(ValueError):
                worker.deploy(changed_baseline, image, self.receipt_path, self.cluster, rollback_receipt=changed_receipt)
        self.assertEqual(self.cluster.writes, 1)

    def test_rollback_uses_the_same_dry_run_and_cas_guards(self):
        receipt = self.deploy()
        baseline = worker.snapshot(self.cluster)[1]
        self.cluster.admission_mutates = True
        with self.assertRaisesRegex(ValueError, "dry-run"), contextlib.redirect_stdout(io.StringIO()):
            worker.deploy(baseline, OLD, self.receipt_path, self.cluster, rollback_receipt=receipt)
        self.cluster.admission_mutates = False
        self.cluster.drift_on_patch = True
        with self.assertRaisesRegex(ValueError, "API conflict"), contextlib.redirect_stdout(io.StringIO()):
            worker.deploy(baseline, OLD, self.receipt_path, self.cluster, rollback_receipt=receipt)
        self.assertEqual(self.cluster.writes, 1)

    def test_cronjob_job_and_init_container_bindings_are_accounted_for(self):
        obj = deployment("record-seal-repair")
        obj["kind"] = "CronJob"
        obj["spec"] = {"suspend": True, "jobTemplate": {"spec": {"template": obj["spec"]["template"]}}}
        pod = worker.pod_spec(obj)
        pod["initContainers"] = [{"name": "init", "image": NEW}]
        bindings = worker.consumers([obj])
        self.assertEqual(len(bindings), 2)
        self.assertEqual({b["field"] for b in bindings}, {"containers", "initContainers"})
        obj["kind"] = "Job"
        obj["spec"] = obj["spec"]["jobTemplate"]["spec"]
        self.assertEqual(len(worker.consumers([obj])), 2)


class WorkflowTests(unittest.TestCase):
    """Integration tripwires complement the behavioral API tests; no cloud approval simulation."""

    @classmethod
    def setUpClass(cls):
        cls.workflow = yaml.safe_load(Path(__file__).parents[1].joinpath("workflows/gcp_diarizer.yml").read_text())
        cls.steps = cls.workflow["jobs"]["deploy"]["steps"]

    def step(self, name):
        return next(s for s in self.steps if s.get("name") == name)

    def test_default_helm_path_and_success_only_writer_keep_existing_controls(self):
        helm = self.step("Deploy Diarizer to GKE cluster using Helm")
        writer = self.step("Deploy worker image preserving live runtime")
        self.assertEqual(helm["if"], "inputs.preserve_live_worker != true")
        self.assertEqual(writer["if"], "inputs.preserve_live_worker == true")
        self.assertIn('helm -n "$DEPLOY_NAMESPACE" upgrade --install', helm["run"])
        self.assertIn("environment", self.workflow["jobs"]["deploy"])
        self.assertFalse(self.workflow["concurrency"]["cancel-in-progress"])
        self.assertIn("'prod-train'", self.workflow["concurrency"]["group"])
        names = [s.get("name") for s in self.steps]
        for gate in ("Select merged production source and image tag", "Verify serving Firestore indexes", "Verify promoted worker digest"):
            self.assertLess(names.index(gate), names.index(writer["name"]))
        # No always(), continue-on-error, or second job can route around a failed gate.
        self.assertNotIn("continue-on-error", writer)
        self.assertEqual(list(self.workflow["jobs"]), ["deploy"])
        immutable = self.step("Checkout immutable worker image-only control")
        self.assertEqual(immutable["with"]["ref"], "${{ github.workflow_sha }}")
        self.assertEqual(immutable["with"]["sparse-checkout"], "/.github/scripts/worker_image_only.py")
        self.assertFalse(immutable["with"]["sparse-checkout-cone-mode"])
        self.assertNotIn(".github/scripts", self.step("Checkout immutable Firestore gate controls")["with"]["sparse-checkout"])
        self.assertIn("--rollback-receipt", writer["run"])

    def test_input_validation_executes_and_refuses_wrong_scope(self):
        step = self.step("Validate Environment Input")
        for environment, service, preserve, baseline, expected in (
            ("prod", "batch-pipeline-worker", "true", "{}", 0),
            ("development", "batch-pipeline-worker", "true", "{}", 1),
            ("prod", "diarizer", "true", "{}", 1),
            ("prod", "batch-pipeline-worker", "true", "", 1),
            ("prod", "diarizer", "false", "", 0),
            ("development", "diarizer", "false", "{}", 1),
        ):
            script = step["run"].replace("${{ github.event.inputs.environment }}", environment).replace("${{ inputs.environment }}", environment)
            with self.subTest(environment=environment, service=service, preserve=preserve):
                result = subprocess.run(
                    ["bash", "-e", "-c", script],
                    env={"SERVICE": service, "PRESERVE_LIVE": preserve, "LIVE_BASELINE": baseline, "ROLLBACK_RECEIPT": ""},
                    capture_output=True,
                )
                self.assertEqual(result.returncode, expected)

    def test_failed_source_ancestry_or_invalid_ref_cannot_reach_writer(self):
        script = self.step("Select merged production source and image tag")["run"]
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            git = root / "git"
            git.write_text(
                '#!/bin/bash\n'
                'if [[ "$1" == merge-base ]]; then exit 1; fi\n'
                'if [[ "$1" == rev-parse ]]; then echo aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa; fi\n'
            )
            git.chmod(0o755)
            for ref in ("unmerged-branch", "b" * 40):
                marker = root / "writer-reached"
                result = subprocess.run(
                    ["bash", "-e", "-c", script + '\nprintf writer > "$WRITE_MARKER"\n'],
                    env={
                        "PATH": str(root) + os.pathsep + os.defpath,
                        "DEPLOY_ENVIRONMENT": "prod",
                        "DEPLOY_REF": ref,
                        "PRESERVE_LIVE": "true",
                        "GITHUB_OUTPUT": str(root / "output"),
                        "WRITE_MARKER": str(marker),
                    },
                    capture_output=True,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(marker.exists())

    def test_source_floor_refusal_precedes_forward_and_reverse_writer(self):
        script = self.step("Select merged production source and image tag")["run"]
        floor = "f3902ec5435809d95ac7c15f6be7e9f056564d3d"
        self.assertIn(f"git merge-base --is-ancestor {floor}", script)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            git = root / "git"
            git.write_text(
                '#!/bin/bash\n'
                f'if [[ "$1" == merge-base && "$3" == {floor} ]]; then exit 1; fi\n'
                'if [[ "$1" == rev-parse ]]; then echo aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa; fi\n'
            )
            git.chmod(0o755)
            marker = root / "writer-reached"
            result = subprocess.run(
                ["bash", "-e", "-c", script + '\nprintf writer > "$WRITE_MARKER"\n'],
                env={"PATH": str(root) + os.pathsep + os.defpath, "DEPLOY_ENVIRONMENT": "prod", "DEPLOY_REF": "b" * 40,
                     "PRESERVE_LIVE": "true", "GITHUB_OUTPUT": str(root / "output"), "WRITE_MARKER": str(marker)},
                capture_output=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(marker.exists())

    def test_rollback_input_requires_same_preserve_path_and_explicit_source_digest(self):
        step = self.step("Validate Environment Input")
        script = step["run"].replace("${{ github.event.inputs.environment }}", "prod").replace("${{ inputs.environment }}", "prod")
        for preserve, ref, image, break_glass, expected in (
            ("true", "a" * 40, "sha256:" + "1" * 64, "false", 0),
            ("false", "a" * 40, "sha256:" + "1" * 64, "false", 1),
            ("true", "main", "sha256:" + "1" * 64, "false", 1),
            ("true", "a" * 40, "", "false", 1),
            ("true", "a" * 40, "sha256:" + "1" * 64, "true", 1),
        ):
            with self.subTest(preserve=preserve, ref=ref, image=image):
                result = subprocess.run(["bash", "-e", "-c", script],
                    env={"SERVICE": "batch-pipeline-worker", "PRESERVE_LIVE": preserve, "LIVE_BASELINE": "{}",
                         "ROLLBACK_RECEIPT": "{}", "SOURCE_REF": ref, "CANDIDATE_DIGEST": image, "BREAK_GLASS_LOCK": break_glass}, capture_output=True)
                self.assertEqual(result.returncode, expected)


if __name__ == "__main__":
    unittest.main()
