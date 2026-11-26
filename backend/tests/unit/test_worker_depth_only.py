"""Exercise the production depth CAS against private, synthetic Kubernetes objects."""

import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[3]
TOOLS = ROOT / ".github/scripts"
with patch.object(sys, "path", [str(TOOLS), *sys.path]):
    spec = importlib.util.spec_from_file_location("worker_depth_only", TOOLS / "worker_depth_only.py")
    depth = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(depth)

DIGEST = "sha256:" + "a" * 64
UID = "80db3851-b9b5-4b56-8e8e-1f80b8f3d8ff"
PRIVATE = "fixture-private-binding"


def workload(kind, name):
    api_version = "apps/v1" if kind == "Deployment" else "batch/v1"
    template = {
        "spec": {
            "containers": [
                {
                    "name": "worker",
                    "image": f"{depth.REPOSITORY}@{DIGEST}",
                    "env": [
                        {"name": "BATCH_PIPELINE_UID_ALLOWLIST", "value": PRIVATE},
                        {"name": depth.DEPTH, "value": "3"},
                    ],
                }
            ]
        }
    }
    spec = {"template": template}
    if kind == "Deployment":
        spec.update(
            replicas=10,
            strategy={
                "type": "RollingUpdate",
                "rollingUpdate": {
                    "maxSurge": 0,
                    "maxUnavailable": "50%",
                },
            },
        )
    else:
        spec = {"jobTemplate": {"spec": spec}}
    return {
        "apiVersion": api_version,
        "kind": kind,
        "metadata": {"namespace": depth.NAMESPACE, "name": name, "uid": UID, "resourceVersion": "47"},
        "spec": spec,
        "status": {"readyReplicas": 10},
    }


class Cluster:
    def __init__(self):
        self.primary = workload("Deployment", depth.TARGET)
        self.siblings = [workload(kind, name) for kind, name in depth.SIBLINGS]
        self.commands = []
        self.receipts = []
        self.previews = []
        self.writes = []
        self.patch_admission = {}
        self.sibling_admission = {}
        self.sibling_reads = 0
        self.primary_reads = 0
        self.primary_admission = {}

    def call(self, *args):
        self.commands.append(args)
        if args[:3] == ("get", "deployment", depth.TARGET):
            self.primary_reads += 1
            result = copy.deepcopy(self.primary)
            if self.primary_reads in self.primary_admission:
                self.primary_admission[self.primary_reads](result)
            return result
        if args[0] == "get":
            self.sibling_reads += 1
            if self.sibling_reads in self.sibling_admission:
                self.sibling_admission[self.sibling_reads](self.siblings)
            return {"items": copy.deepcopy(self.siblings)}
        assert args[:5] == ("patch", "deployment", depth.TARGET, "--type=json", "-p")
        ops = json.loads(args[5])
        requests = self.previews if "--dry-run=server" in args else self.writes
        requests.append(ops)
        result = copy.deepcopy(self.primary)
        for op in ops:
            *segments, leaf = op["path"][1:].split("/")
            node = result
            for segment in segments:
                node = node[int(segment) if isinstance(node, list) else segment]
            leaf = int(leaf) if isinstance(node, list) else leaf
            if op["op"] == "test":
                if node[leaf] != op["value"]:
                    raise ValueError("Kubernetes CAS conflict")
            else:
                assert op["op"] == "replace"
                node[leaf] = op["value"]
        admission = self.patch_admission.get(len(self.previews) + len(self.writes))
        if admission:
            admission(result)
        if requests is self.writes:
            self.primary = copy.deepcopy(result)
        return result

    def emit(self, receipt):
        self.commands.append("receipt")
        self.receipts.append(receipt)

    def wait(self):
        self.commands.append("rollout wait")

    def execute(self, *, operation="plan", current="3", target="4", digest=DIGEST, uid=UID, version="47"):
        depth.execute(operation, current, target, digest, uid, version, self.emit, run=self.call, wait=self.wait)


def depth_binding(obj):
    return depth.pod_spec(obj)["containers"][0]["env"][1]


class WorkerDepthOnlyTest(unittest.TestCase):
    def test_plan_sends_two_server_dry_runs_and_never_writes(self):
        cluster = Cluster()
        cluster.execute()
        forward, inverse = cluster.previews
        self.assertEqual(inverse[:-2], forward)
        self.assertEqual(
            inverse[-2:],
            [
                {"op": "test", "path": forward[-1]["path"], "value": "4"},
                {"op": "replace", "path": forward[-1]["path"], "value": "3"},
            ],
        )
        self.assertEqual(cluster.writes, [])
        self.assertNotIn("rollout wait", cluster.commands)
        self.assertEqual(depth_binding(cluster.primary)["value"], "3")
        self.assertNotIn(PRIVATE, json.dumps([cluster.receipts, cluster.previews]))
        self.assertEqual(len(cluster.receipts[0]["preserved_sibling_templates"]), 4)

    def test_apply_and_inverse_use_identical_forward_preview_and_write(self):
        for current, target in (("3", "4"), ("4", "3")):
            with self.subTest(current=current):
                cluster = Cluster()
                depth_binding(cluster.primary)["value"] = current
                cluster.execute(operation="apply", current=current, target=target)
                self.assertEqual(cluster.writes, [cluster.previews[0]])
                self.assertEqual(depth_binding(cluster.primary)["value"], target)
                self.assertTrue(all(op["op"] == "test" for op in cluster.writes[0][:-1]))
                self.assertEqual(cluster.commands[-5][0], "patch")
                self.assertNotIn("--dry-run=server", cluster.commands[-5])
                self.assertEqual(cluster.commands[-4], "rollout wait")
                self.assertEqual(cluster.commands[-6], "receipt")
                self.assertEqual(cluster.receipts[-1]["depth"], target)

    def test_invalid_inputs_refuse_before_kubernetes(self):
        for kwargs in (
            {"operation": "write"},
            {"current": "2"},
            {"target": "5"},
            {"target": "3"},
            {"digest": "latest"},
            {"uid": "wrong"},
            {"version": ""},
        ):
            with self.subTest(kwargs=kwargs):
                cluster = Cluster()
                with self.assertRaises(ValueError):
                    cluster.execute(**kwargs)
                self.assertEqual(cluster.commands, [])

    def test_live_identity_depth_and_digest_mismatches_refuse(self):
        for kwargs, message in (
            ({"uid": "005980ad-2c1b-4265-b3b4-30957ab9a423"}, "UID changed"),
            ({"version": "48"}, "resourceVersion changed"),
            ({"digest": "sha256:" + "b" * 64}, "expected digest"),
            ({"current": "4", "target": "3"}, "expected current depth"),
        ):
            with self.subTest(kwargs=kwargs):
                cluster = Cluster()
                with self.assertRaisesRegex(ValueError, message):
                    cluster.execute(operation="apply", **kwargs)
                self.assertEqual(cluster.previews, [])
                self.assertEqual(cluster.writes, [])

    def test_invalid_live_spec_refuses(self):
        for change in (
            lambda obj: obj["spec"]["strategy"].update(type="Recreate"),
            lambda obj: obj["spec"]["strategy"]["rollingUpdate"].update(maxSurge=1),
            lambda obj: obj["spec"]["strategy"]["rollingUpdate"].update(maxUnavailable="25%"),
            lambda obj: obj["metadata"].update(deletionTimestamp="now"),
            lambda obj: depth.pod_spec(obj)["containers"].append(depth.pod_spec(obj)["containers"][0]),
            lambda obj: depth.pod_spec(obj)["containers"][0]["env"].append(depth_binding(obj)),
            lambda obj: depth.pod_spec(obj)["containers"][0]["env"].pop(),
            lambda obj: depth_binding(obj).update(value="2"),
            lambda obj: depth_binding(obj).update(valueFrom={"secretKeyRef": {}}),
        ):
            with self.subTest(change=change):
                cluster = Cluster()
                change(cluster.primary)
                with self.assertRaises(ValueError):
                    cluster.execute(operation="apply")
                self.assertEqual(cluster.previews, [])
                self.assertEqual(cluster.writes, [])

    def test_each_server_dry_run_refuses_extra_changes(self):
        for phase in (1, 2):
            for change in (
                lambda obj: obj["metadata"].update(uid="different"),
                lambda obj: obj["spec"]["strategy"]["rollingUpdate"].update(maxUnavailable="25%"),
                lambda obj: depth.pod_spec(obj)["containers"][0].update(image=depth.REPOSITORY + "@sha256:" + "b" * 64),
                lambda obj: depth.pod_spec(obj)["containers"][0]["env"][0].update(value="injected"),
                lambda obj: obj["spec"].update(replicas=9),
            ):
                with self.subTest(phase=phase, change=change):
                    cluster = Cluster()
                    cluster.patch_admission[phase] = change
                    with self.assertRaises(ValueError):
                        cluster.execute(operation="apply")
                    self.assertEqual(cluster.writes, [])

    def test_missing_or_drifting_siblings_fail_closed(self):
        for index in range(len(depth.SIBLINGS)):
            for read in (1, 2, 3):
                with self.subTest(sibling=index, read=read):
                    cluster = Cluster()

                    def change(siblings):
                        if read == 1:
                            siblings.pop(index)
                        else:
                            depth.pod_spec(siblings[index])["affinity"] = {"changed": True}

                    cluster.sibling_admission[read] = change
                    with self.assertRaises(ValueError):
                        cluster.execute(operation="apply")
                    self.assertEqual(cluster.writes, [])

    def test_fresh_resource_version_refused_and_late_conflict_never_retried(self):
        cluster = Cluster()
        cluster.primary_admission[2] = lambda obj: obj["metadata"].update(resourceVersion="48")
        with self.assertRaisesRegex(ValueError, "changed during rehearsal"):
            cluster.execute(operation="apply")
        self.assertEqual(cluster.writes, [])

        cluster = Cluster()

        def emit_then_change(receipt):
            Cluster.emit(cluster, receipt)
            cluster.primary["metadata"]["resourceVersion"] = "48"

        with patch.object(cluster, "emit", side_effect=emit_then_change):
            with self.assertRaisesRegex(ValueError, "CAS conflict"):
                cluster.execute(operation="apply")
        self.assertEqual(len(cluster.writes), 1)
        self.assertEqual(depth_binding(cluster.primary)["value"], "3")
        self.assertIn("rollout wait", cluster.commands)

    def test_post_rollout_allows_replica_scaling_but_refuses_template_drift(self):
        cluster = Cluster()
        cluster.primary_admission[3] = lambda obj: obj["spec"].update(replicas=11)
        cluster.execute(operation="apply")

        cluster = Cluster()
        cluster.primary_admission[3] = lambda obj: depth_binding(obj).update(value="3")
        with self.assertRaisesRegex(ValueError, "post-rollout Deployment drift"):
            cluster.execute(operation="apply")


class WorkflowValidationTest(unittest.TestCase):
    def test_pod_health_is_a_strict_success_gate_only_for_depth_apply(self):
        workflow = yaml.load((ROOT / ".github/workflows/gcp_diarizer.yml").read_text(), Loader=yaml.BaseLoader)
        steps = workflow["jobs"]["deploy"]["steps"]
        names = [step.get("name") for step in steps]
        report_index = names.index("Verify worker depth apply pod health")
        self.assertGreater(report_index, names.index("Rehearse or apply the production worker depth CAS"))
        report = steps[report_index]
        self.assertEqual(
            report["if"],
            "inputs.mode == 'worker-depth-only' && inputs.depth_operation == 'apply' && inputs.worker_dry_run != true",
        )
        self.assertNotIn("continue-on-error", report)
        self.assertEqual(
            report["run"].strip(),
            "timeout 120 python3 backend/scripts/deploy_status_report.py --env prod --include-gke "
            "--gke-service batch-pipeline-worker",
        )

    def test_dispatch_gate(self):
        workflow = yaml.load((ROOT / ".github/workflows/gcp_diarizer.yml").read_text(), Loader=yaml.BaseLoader)
        self.assertIn("'prod-train'", workflow["concurrency"]["group"])
        self.assertIn("github.event.inputs.break_glass_lock != 'true'", workflow["concurrency"]["group"])
        self.assertEqual(workflow["concurrency"]["cancel-in-progress"], "false")
        first = workflow["jobs"]["deploy"]["steps"][0]
        fields = {
            "DEPTH_OPERATION": "plan",
            "TARGET_DEPTH": "4",
            "EXPECTED_CURRENT_DEPTH": "3",
            "EXPECTED_WORKER_DIGEST": DIGEST,
            "EXPECTED_WORKER_UID": UID,
            "EXPECTED_WORKER_RESOURCE_VERSION": "47",
            "MODE": "worker-depth-only",
            "GITHUB_REF": "refs/heads/main",
            "SERVICE": "batch-pipeline-worker",
            "SOURCE_REF": "a" * 40,
        }

        def invoke(environment="prod", **changes):
            script = first["run"].replace("${{ github.event.inputs.environment }}", environment)
            script = script.replace("${{ inputs.environment }}", environment)
            return subprocess.run(["bash", "-e", "-c", script], env={**fields, **changes}, capture_output=True)

        self.assertEqual(invoke().returncode, 0)
        self.assertEqual(invoke(DEPTH_OPERATION="apply").returncode, 0)
        for changes in (
            {"environment": "development"},
            {"GITHUB_REF": "refs/heads/other"},
            {"SERVICE": "diarizer"},
            {"MODE": "standard"},
            {"BREAK_GLASS_LOCK": "true"},
            {"DRY_RUN": "true"},
            {"PRESERVE_LIVE": "true"},
            {"ROLLBACK_RECEIPT": "{}"},
            {"LIVE_BASELINE": "{}"},
            {"CANDIDATE_DIGEST": DIGEST},
            {"RELEASE_VERSION": "legacy"},
            {"SOURCE_REF": "main"},
            {"EXPECTED_WORKER_RESOURCE_VERSION": ""},
            {"DEPTH_OPERATION": "invalid"},
        ):
            with self.subTest(changes=changes):
                self.assertNotEqual(invoke(**changes).returncode, 0)


if __name__ == "__main__":
    unittest.main()
