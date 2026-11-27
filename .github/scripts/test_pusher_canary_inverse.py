#!/usr/bin/env python3
"""Check the smallest-radius canary inverse proof against a guarded kubectl fake."""

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pusher_canary_inverse as inverse

BASELINE = "gcr.io/based-hardware/pusher@sha256:" + "a" * 64
CANDIDATE = "gcr.io/based-hardware/pusher@sha256:" + "b" * 64
SOURCE = "3" * 40


def canary_deployment(image=CANDIDATE, name="prod-omi-pusher-canary-42"):
    return {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {"name": name, "namespace": "prod-omi-backend", "uid": "canary-uid", "resourceVersion": "7", "generation": 1},
        "spec": {
            "replicas": 1,
            "template": {
                "spec": {
                    "containers": [
                        {"name": "sidecar", "image": "gcr.io/based-hardware/sidecar@sha256:" + "c" * 64},
                        {"name": "pusher", "image": image},
                    ]
                }
            },
        },
    }


def live_deployment(image=BASELINE):
    obj = canary_deployment(image=image, name="prod-omi-pusher")
    obj["metadata"]["uid"] = "live-uid"
    return obj


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

    def record(self):
        with patch.object(inverse, "kubectl_json", side_effect=self.kubectl):
            return inverse.record("prod-omi-backend", "prod-omi-pusher-canary-42", CANDIDATE, BASELINE, 42, SOURCE)

    def test_records_guarded_candidate_to_baseline_server_dry_run(self):
        receipt = self.record()
        self.assertEqual(receipt["status"], "PASS")
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

    def test_patch_preconditions_are_uid_resource_version_container_and_old_digest(self):
        with patch.object(inverse, "kubectl_json", side_effect=self.kubectl):
            inverse.record("prod-omi-backend", "prod-omi-pusher-canary-42", CANDIDATE, BASELINE, 42, SOURCE)
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
                inverse.record("prod-omi-backend", "prod-omi-pusher-canary-42", CANDIDATE, BASELINE, 42, SOURCE)

    def test_main_writes_a_refused_receipt_and_fails_closed(self):
        self.canary = canary_deployment(image=BASELINE)
        with tempfile.TemporaryDirectory() as tmp, patch.object(inverse, "kubectl_json", side_effect=self.kubectl), patch(
            "builtins.print"
        ):
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
                    "--output",
                    str(output),
                ]
            )
            receipt = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(code, 1)
        self.assertEqual((receipt["status"], receipt["reason"]), ("REFUSED", "canary_does_not_hold_candidate"))

    def test_main_rejects_an_unpinned_baseline(self):
        self.baseline = live_deployment(image=live_deployment()["spec"]["template"]["spec"]["containers"][0]["image"])
        with tempfile.TemporaryDirectory() as tmp, patch.object(inverse, "kubectl_json", side_effect=self.kubectl), patch(
            "builtins.print"
        ):
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
                    "--output",
                    str(output),
                ]
            )
            receipt = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(code, 1)
        self.assertEqual(receipt["reason"], "baseline_image_unpinned_or_equal")


if __name__ == "__main__":
    unittest.main()
