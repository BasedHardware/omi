#!/usr/bin/env python3
"""Check the smallest-radius canary inverse proof against a guarded kubectl fake."""

import copy
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

import pusher_canary_inverse as inverse

BASELINE = "gcr.io/based-hardware/pusher@sha256:" + "a" * 64
CANDIDATE = "gcr.io/based-hardware/pusher@sha256:" + "b" * 64
SOURCE = "3" * 40
WORKFLOW_SHA = "a" * 40
CANARY = "prod-omi-pusher-canary-42"
CANARY_CONFIG = "prod-omi-backend-config-canary-42"
LIVE_CONFIG = "prod-omi-backend-config"


def deployment(image, name, config_map):
    """Helm-rendered shape: release-named labels and the runtime ConfigMap reference."""
    return {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {"name": name, "namespace": "prod-omi-backend", "uid": "canary-uid", "resourceVersion": "7", "generation": 1},
        "spec": {
            "replicas": 1,
            "template": {
                "metadata": {"labels": {"app.kubernetes.io/name": "pusher", "app.kubernetes.io/instance": name}},
                "spec": {
                    "serviceAccountName": "prod-omi-pusher",
                    "containers": [
                        {"name": "sidecar", "image": "gcr.io/based-hardware/sidecar@sha256:" + "c" * 64},
                        {
                            "name": "pusher",
                            "image": image,
                            "envFrom": [{"configMapRef": {"name": config_map}}],
                            "env": [
                                {"name": "X", "valueFrom": {"configMapKeyRef": {"name": config_map, "key": "X"}}},
                                {"name": "S", "valueFrom": {"secretKeyRef": {"name": "backend-secrets", "key": "S"}}},
                            ],
                            "terminationMessagePolicy": "File",
                        },
                    ],
                    "dnsPolicy": "ClusterFirst",
                },
            },
        },
    }


def canary_deployment(image=CANDIDATE, name=CANARY):
    return deployment(image, name, CANARY_CONFIG)


def live_deployment(image=BASELINE):
    obj = deployment(image, "prod-omi-pusher", LIVE_CONFIG)
    obj["metadata"]["uid"] = "live-uid"
    return obj


class FakeMetadata:
    """Metadata-only reads: ConfigMap identity and Secret PartialObjectMetadata, never data."""

    def __init__(self):
        self.versions = {
            ("secret", "backend-secrets"): ["secret-uid", "2"],
            ("configmap", CANARY_CONFIG): ["canary-config-uid", "1"],
            ("configmap", LIVE_CONFIG): ["config-uid", "1"],
        }
        self.reads = []

    def secret_version(self, name, *, namespace, optional=False):
        self.reads.append(("secret", name))
        return self.versions.get(("secret", name))

    def get(self, kind, name, *, namespace=None, optional=False):
        self.reads.append((kind, name))
        observed = self.versions.get((kind, name))
        return None if observed is None else {"metadata": {"uid": observed[0], "resourceVersion": observed[1], "name": name}}


def resolve(obj, path):
    current = obj
    for part in path.strip("/").split("/"):
        current = current[int(part)] if isinstance(current, list) else current[part]
    return current


def assign(obj, path, value):
    parts = path.strip("/").split("/")
    parent = obj
    for part in parts[:-1]:
        parent = parent[int(part)] if isinstance(parent, list) else parent[part]
    key = parts[-1]
    if isinstance(parent, list):
        parent[int(key)] = value
    else:
        parent[key] = value


class InverseTest(unittest.TestCase):
    def setUp(self):
        self.canary = canary_deployment()
        self.baseline = live_deployment()
        self.requests = []
        self.metadata = FakeMetadata()

    def kubectl(self, args, *, stdin=None):
        self.requests.append(list(args))
        if args[0] == "get":
            return copy.deepcopy(self.canary if args[2] == "prod-omi-pusher-canary-42" else self.baseline)
        changed = copy.deepcopy(self.canary)
        for op in json.loads(stdin):
            if op["op"] == "test":
                if resolve(changed, op["path"]) != op["value"]:
                    raise inverse.Refused("canary_admission_probe_failed")
            else:
                assign(changed, op["path"], op["value"])
        return changed

    def record(self, **overrides):
        arguments = {
            "workflow_sha": WORKFLOW_SHA,
            "cluster": self.metadata,
            "canary_config_map": CANARY_CONFIG,
            "live_config_map": LIVE_CONFIG,
        } | overrides
        with patch.object(inverse, "kubectl_json", side_effect=self.kubectl):
            return inverse.record(
                "prod-omi-backend", CANARY, CANDIDATE, BASELINE, 42, SOURCE, "prod-omi-pusher", **arguments
            )

    def test_records_guarded_candidate_to_baseline_server_dry_run(self):
        receipt = self.record()
        self.assertEqual(receipt["status"], "PASS")
        self.assertEqual(receipt["mode"], "canary_only")
        self.assertEqual(receipt["workflow_sha"], WORKFLOW_SHA)
        self.assertEqual(
            receipt["live_deployment"],
            {"name": "prod-omi-pusher", "uid": "live-uid", "template_sha256": inverse.template_sha256(self.baseline)},
        )
        self.assertEqual(receipt["dry_run"], "server")
        self.assertEqual(receipt["candidate_image"], CANDIDATE)
        self.assertEqual(receipt["baseline_image"], BASELINE)
        self.assertEqual(receipt["admitted_image"], BASELINE)
        self.assertEqual(
            receipt["preconditions"],
            {"uid": "canary-uid", "resourceVersion": "7", "container": "pusher", "image": CANDIDATE},
        )
        patch = self.requests[-1]
        self.assertIn("--dry-run=server", patch)
        self.assertIn("--type=json", patch)

    def test_template_parity_is_redacted_and_excludes_the_image(self):
        receipt = self.record()
        parity = receipt["template_parity"]
        self.assertEqual(parity["live_deployment"], "prod-omi-pusher")
        self.assertEqual(parity["canary_deployment"], "prod-omi-pusher-canary-42")
        self.assertEqual(parity["excluded"], list(inverse.PARITY_EXCLUDED))
        self.assertEqual(parity["normalized"], ["release_name", "runtime_config_map"])
        self.assertEqual(set(parity["classes"]), set(inverse.PARITY_CLASSES))
        self.assertTrue(all(value in {"equal", "differs"} for value in parity["classes"].values()))
        # The image and the canary's release/ConfigMap names are the only differences.
        self.assertEqual(set(parity["classes"].values()), {"equal"})
        self.assertNotIn(CANDIDATE, json.dumps(parity))
        self.assertNotIn(BASELINE, json.dumps(parity))

    def test_template_parity_reports_a_field_class_difference(self):
        self.baseline["spec"]["template"]["spec"]["containers"][1]["env"] = [{"name": "X", "value": "y"}]
        receipt = self.record()
        self.assertEqual(receipt["template_parity"]["classes"]["container_env"], "differs")
        self.assertEqual(receipt["template_parity"]["classes"]["container_resources"], "equal")

    def test_template_parity_catches_unlisted_fields(self):
        cases = (
            ("hostNetwork", lambda spec: spec.update(hostNetwork=True)),
            ("dnsPolicy", lambda spec: spec.update(dnsPolicy="Default")),
            ("container workingDir", lambda spec: spec["containers"][1].update(workingDir="/tmp")),
            ("terminationMessagePolicy", lambda spec: spec["containers"][1].update(terminationMessagePolicy="FallbackToLogsOnError")),
        )
        for name, mutate in cases:
            with self.subTest(field=name):
                self.baseline = live_deployment()
                mutate(self.baseline["spec"]["template"]["spec"])
                classes = self.record()["template_parity"]["classes"]
                self.assertEqual(classes["other_template_fields"], "differs")
                self.assertEqual({key for key, value in classes.items() if value == "differs"}, {"other_template_fields"})
                self.assertNotIn("FallbackToLogsOnError", json.dumps(classes))

    def test_template_parity_only_maps_the_canary_names(self):
        # Without the ConfigMap mapping, the isolated ConfigMap reference is a real difference.
        classes = self.record(canary_config_map=None, live_config_map=None)["template_parity"]["classes"]
        self.assertEqual(classes["container_envFrom"], "differs")
        self.assertEqual(classes["dependency_references"], "differs")
        # A live reference to some other ConfigMap is never mapped away.
        self.baseline["spec"]["template"]["spec"]["containers"][1]["envFrom"] = [{"configMapRef": {"name": "other-config"}}]
        classes = self.record()["template_parity"]["classes"]
        self.assertEqual(classes["container_envFrom"], "differs")
        self.assertEqual(classes["dependency_references"], "differs")

    def test_template_parity_ignores_a_rollout_restart_stamp(self):
        self.baseline["spec"]["template"]["metadata"]["annotations"] = {inverse.RESTARTED_AT: "2026-11-27T00:00:00Z"}
        self.assertEqual(self.record()["template_parity"]["classes"]["pod_annotations"], "equal")
        self.baseline["spec"]["template"]["metadata"]["annotations"]["other"] = "x"
        self.assertEqual(self.record()["template_parity"]["classes"]["pod_annotations"], "differs")

    def test_patch_preconditions_are_uid_resource_version_container_and_old_digest(self):
        self.record()
        ops = inverse.guarded_patch(self.canary, "prod-omi-pusher-canary-42", CANDIDATE, BASELINE)
        self.assertEqual(
            [(op["op"], op["path"]) for op in ops],
            [
                ("test", "/metadata/uid"),
                ("test", "/metadata/resourceVersion"),
                ("test", "/spec/template/spec/containers/1/name"),
                ("test", "/spec/template/spec/containers/1/image"),
                ("replace", "/spec/template/spec/containers/1/image"),
            ],
        )
        self.assertEqual(ops[3]["value"], CANDIDATE)
        self.assertEqual(ops[4]["value"], BASELINE)

    def test_records_metadata_only_dependency_versions_at_startup(self):
        dependencies = self.record()["dependencies"]
        self.assertEqual(dependencies["names"], [["secret", "backend-secrets"]])
        self.assertEqual(dependencies["excluded"], "runtime_config_map")
        self.assertEqual((dependencies["probe_sha256"], dependencies["stable"]), (None, False))
        self.assertEqual(len(dependencies["startup_sha256"]), 64)
        self.assertNotIn("secret-uid", json.dumps(dependencies))
        self.assertIn(("secret", "backend-secrets"), self.metadata.reads)

    def recheck(self, receipt):
        with patch.object(inverse, "kubectl_json", side_effect=self.kubectl):
            return inverse.recheck(
                receipt, self.metadata, namespace="prod-omi-backend", name=CANARY, run_id=42, canary_config_map=CANARY_CONFIG
            )

    def test_recheck_after_the_probe_requires_stable_dependency_versions(self):
        receipt = self.record()
        checked = self.recheck(receipt)
        self.assertEqual(checked["dependencies"]["probe_sha256"], receipt["dependencies"]["startup_sha256"])
        self.assertTrue(checked["dependencies"]["stable"])
        for change in (["secret-uid", "3"], ["other-uid", "2"], None):
            with self.subTest(change=change):
                self.metadata.versions[("secret", "backend-secrets")] = change
                with self.assertRaisesRegex(inverse.Refused, "canary_dependencies_changed|required_dependency_absent"):
                    self.recheck(receipt)

    def test_recheck_refuses_a_replaced_canary(self):
        receipt = self.record()
        self.canary["metadata"]["uid"] = "replaced-uid"
        with self.assertRaisesRegex(inverse.Refused, "canary_replaced_during_probe"):
            self.recheck(receipt)

    def test_recheck_main_rewrites_the_receipt_and_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "receipt.json"
            output.write_text(json.dumps(self.record()), encoding="utf-8")
            self.metadata.versions[("secret", "backend-secrets")] = ["secret-uid", "9"]
            with patch.object(inverse, "kubectl_json", side_effect=self.kubectl), patch.object(
                inverse, "live_cluster", return_value=self.metadata
            ), patch("builtins.print"):
                code = inverse.main([*self.argv(output), "--canary-config-map", CANARY_CONFIG, "--recheck"])
            receipt = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual((code, receipt["status"], receipt["reason"]), (1, "REFUSED", "canary_dependencies_changed"))

    def argv(self, output):
        return [
            "--namespace",
            "prod-omi-backend",
            "--name",
            CANARY,
            "--candidate-image",
            CANDIDATE,
            "--baseline-deployment",
            "prod-omi-pusher",
            "--run-id",
            "42",
            "--source-sha",
            SOURCE,
            "--workflow-sha",
            WORKFLOW_SHA,
            "--output",
            str(output),
        ]

    def test_helper_paths_cover_the_helper_and_its_first_party_imports(self):
        root = Path(inverse.__file__).resolve().parents[2]
        self.assertEqual(
            inverse.INVERSE_HELPER_PATHS,
            (".github/scripts/pusher_canary_inverse.py", ".github/scripts/pusher_image_rehearsal.py"),
        )
        first_party = {path.stem for path in (root / ".github/scripts").glob("*.py")}
        for relative in inverse.INVERSE_HELPER_PATHS:
            source = (root / relative).read_text(encoding="utf-8")
            imported = set(re.findall(r"(?m)^(?:from|import) ([A-Za-z_][A-Za-z0-9_]*)", source))
            self.assertLessEqual(imported & first_party, {Path(path).stem for path in inverse.INVERSE_HELPER_PATHS}, relative)

    def test_refuses_without_the_producing_workflow_revision(self):
        with self.assertRaisesRegex(inverse.Refused, "invalid_canary_identity"):
            self.record(workflow_sha="main")

    def test_refuses_when_the_canary_does_not_hold_the_candidate(self):
        self.canary = canary_deployment(image=BASELINE)
        with self.assertRaisesRegex(inverse.Refused, "canary_does_not_hold_candidate"):
            self.record()

    def test_refuses_when_admission_changes_more_than_the_image(self):
        def changed(args, *, stdin=None):
            self.requests.append(list(args))
            if args[0] == "get":
                return copy.deepcopy(self.canary if args[2] == "prod-omi-pusher-canary-42" else self.baseline)
            admitted = copy.deepcopy(self.canary)
            admitted["spec"]["template"]["spec"]["containers"][0]["env"] = []
            return admitted

        with patch.object(inverse, "kubectl_json", side_effect=changed):
            with self.assertRaisesRegex(inverse.Refused, "canary_inverse_changed_more_than_image"):
                inverse.record(
                    "prod-omi-backend",
                    CANARY,
                    CANDIDATE,
                    BASELINE,
                    42,
                    SOURCE,
                    "prod-omi-pusher",
                    workflow_sha=WORKFLOW_SHA,
                    cluster=self.metadata,
                )

    def test_main_writes_a_refused_receipt_and_fails_closed(self):
        self.canary = canary_deployment(image=BASELINE)
        with tempfile.TemporaryDirectory() as tmp, patch.object(inverse, "kubectl_json", side_effect=self.kubectl), patch.object(
            inverse, "live_cluster", return_value=self.metadata
        ), patch("builtins.print"):
            output = Path(tmp) / "receipt.json"
            code = inverse.main(
                [
                    "--namespace",
                    "prod-omi-backend",
                    "--name",
                    "prod-omi-pusher-canary-42",
                    "--candidate-image",
                    CANDIDATE,
                    "--baseline-deployment",
                    "prod-omi-pusher",
                    "--run-id",
                    "42",
                    "--source-sha",
                    SOURCE,
                    "--workflow-sha",
                    WORKFLOW_SHA,
                    "--output",
                    str(output),
                ]
            )
            receipt = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(code, 1)
        self.assertEqual((receipt["status"], receipt["reason"]), ("REFUSED", "canary_does_not_hold_candidate"))

    def test_main_rejects_an_unpinned_baseline(self):
        self.baseline = live_deployment(image=live_deployment()["spec"]["template"]["spec"]["containers"][0]["image"])
        with tempfile.TemporaryDirectory() as tmp, patch.object(inverse, "kubectl_json", side_effect=self.kubectl), patch.object(
            inverse, "live_cluster", return_value=self.metadata
        ), patch("builtins.print"):
            output = Path(tmp) / "receipt.json"
            code = inverse.main(
                [
                    "--namespace",
                    "prod-omi-backend",
                    "--name",
                    "prod-omi-pusher-canary-42",
                    "--candidate-image",
                    CANDIDATE,
                    "--baseline-deployment",
                    "prod-omi-pusher",
                    "--run-id",
                    "42",
                    "--source-sha",
                    SOURCE,
                    "--workflow-sha",
                    WORKFLOW_SHA,
                    "--output",
                    str(output),
                ]
            )
            receipt = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(code, 1)
        self.assertEqual(receipt["reason"], "baseline_image_unpinned_or_equal")


if __name__ == "__main__":
    unittest.main()
