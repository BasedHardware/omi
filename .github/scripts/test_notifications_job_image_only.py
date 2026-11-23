#!/usr/bin/env python3
"""Exercise image-only job updates against a Cloud Run v2 API double."""

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend/scripts"))

import notifications_job_image_only as deploy

CANDIDATE = f"{deploy.REPOSITORY}@sha256:{'a' * 64}"
SOURCE = "b" * 40
EXPECTED = {deploy.ENDPOINT: "http://gateway.internal", deploy.BLANK: ""}


class CloudRun:
    def __init__(self):
        self.job = {
            "name": deploy.JOB,
            "uid": "job-uid",
            "etag": "etag-66",
            "generation": "66",
            "observedGeneration": "66",
            "terminalCondition": {"state": "CONDITION_SUCCEEDED"},
            "annotations": {"owner": "release"},
            "template": {
                "taskCount": 2,
                "template": {
                    "timeout": "3600s",
                    "serviceAccount": "notifications@example.org",
                    "containers": [
                        {"name": "collector", "image": "example.org/collector:1"},
                        {
                            "name": deploy.CONTAINER,
                            "image": deploy.ROLLBACK,
                            "env": [
                                {"name": deploy.ENDPOINT, "value": EXPECTED[deploy.ENDPOINT]},
                                {"name": deploy.BLANK},
                                {"name": "SECRET", "valueSource": {"secretKeyRef": {"secret": "id", "version": "1"}}},
                            ],
                        },
                    ],
                },
            },
        }
        self.patches = []
        self.drift_validation = None
        self.race_on_apply = False
        self.writes = 0

    def __call__(self, path, body=None):
        if path == deploy.JOB:
            return copy.deepcopy(self.job)
        self.patches.append((path, copy.deepcopy(body)))
        validate = path == deploy.JOB + "?validateOnly=true"
        if self.race_on_apply and not validate:
            self.job["etag"] = "concurrent-etag"
        if body["etag"] != self.job["etag"]:
            return {"done": True, "error": {"code": 10}}
        result = copy.deepcopy(body)
        result["@type"] = "type.googleapis.com/google.cloud.run.v2.Job"
        result["updateTime"] = "output-only"
        deploy.literal_env(result)[deploy.BLANK].setdefault("value", "")
        if validate:
            if self.drift_validation == deploy.app_container(result)["image"]:
                result["template"]["template"]["timeout"] = "1200s"
        else:
            self.writes += 1
            generation = str(int(self.job["generation"]) + 1)
            self.job = {
                **deploy.configuration(body),
                "generation": generation,
                "observedGeneration": generation,
                "etag": f"etag-{generation}",
                "uid": self.job["uid"],
                "terminalCondition": {"state": "CONDITION_SUCCEEDED"},
            }
        name = "projects/based-hardware/locations/us-central1/operations/op-" + str(len(self.patches))
        if validate:
            return {"name": name, "metadata": result}
        return {"done": True, "name": name, "response": result}


class ImageOnlyTest(unittest.TestCase):
    def setUp(self):
        self.api = CloudRun()

    def change(self, action="validate", receipt=None, generation="66"):
        return deploy.change_image(
            self.api, mode=f"image-only-{action}", source=SOURCE, generation=generation,
            candidate=CANDIDATE, expected_env=EXPECTED, receipt=receipt,
        )

    def test_validate_apply_rollback_preserve_configuration(self):
        before = copy.deepcopy(self.api.job)
        receipt = self.change()
        self.assertEqual(self.api.job, before)
        self.assertEqual([p[0] for p in self.api.patches], [deploy.JOB + "?validateOnly=true"] * 2)
        self.assertEqual([deploy.app_container(p[1])["image"] for p in self.api.patches], [CANDIDATE, deploy.ROLLBACK])
        self.assertEqual(self.change("apply", receipt)["installed_image"], CANDIDATE)
        self.assertEqual(self.api.patches[-1][1]["etag"], "etag-66")
        self.assertEqual(self.change("rollback", receipt, "67")["installed_image"], deploy.ROLLBACK)
        self.assertEqual(self.api.patches[-1][1]["etag"], "etag-67")
        deploy.assert_projection(self.api.job, before)
        self.assertEqual(self.api.writes, 2)

    def test_accepts_job_name_with_prod_project_number(self):
        self.api.job["name"] = deploy.JOB.replace("/based-hardware/", "/208440318997/")
        self.assertEqual(self.change()["job"], deploy.JOB)

    def test_rejects_validation_without_full_projection(self):
        def request(path, body=None):
            if body is not None:
                return {"done": True, "response": {"@type": deploy.JOB_TYPE}}
            return self.api(path)

        with self.assertRaisesRegex(ValueError, "Unexpected or deleted"):
            deploy.change_image(
                request, mode="image-only-validate", source=SOURCE, generation="66",
                candidate=CANDIDATE, expected_env=EXPECTED,
            )

    def test_rejects_stale_etag_in_get_to_patch_race(self):
        receipt = self.change()
        self.api.race_on_apply = True
        with self.assertRaisesRegex(ValueError, "code 10"):
            self.change("apply", receipt)
        self.assertEqual(self.api.writes, 0)
        self.assertEqual(self.api.patches[-1][1]["etag"], "etag-66")

    def test_rejects_wrong_or_duplicate_container(self):
        containers = self.api.job["template"]["template"]["containers"]
        original = copy.deepcopy(containers)
        for name in ("renamed", deploy.CONTAINER):
            with self.subTest(name=name):
                containers[:] = copy.deepcopy(original)
                containers[int(name == "renamed")]["name"] = name
                with self.assertRaisesRegex(ValueError, "exactly one"):
                    self.change()
        self.assertFalse(self.api.patches)

    def test_rejects_endpoint_mismatch_and_secret_backed_blank(self):
        entries = deploy.literal_env(self.api.job)
        entries[deploy.ENDPOINT]["value"] = "http://wrong.internal"
        with self.assertRaisesRegex(ValueError, deploy.ENDPOINT):
            self.change()
        entries[deploy.ENDPOINT]["value"] = EXPECTED[deploy.ENDPOINT]
        entries[deploy.BLANK]["valueSource"] = {"secretKeyRef": {"secret": "id"}}
        with self.assertRaisesRegex(ValueError, deploy.BLANK):
            self.change()
        self.assertFalse(self.api.patches)

    def test_rejects_forward_and_inverse_server_drift(self):
        for image in (CANDIDATE, deploy.ROLLBACK):
            with self.subTest(image=image):
                self.api.drift_validation = image
                with self.assertRaisesRegex(ValueError, "configuration drift"):
                    self.change()
        self.assertEqual(self.api.writes, 0)

    def test_rejects_setting_drift_after_receipt(self):
        receipt = self.change()
        self.api.job["template"]["template"]["containers"][0]["image"] += "-changed"
        with self.assertRaisesRegex(ValueError, "differs from the validation receipt"):
            self.change("apply", receipt)
        self.assertEqual(self.api.writes, 0)

    def test_rejects_stale_generation_and_wrong_rollback_digest(self):
        receipt = self.change()
        self.change("apply", receipt)
        with self.assertRaisesRegex(ValueError, "approved generation"):
            self.change("rollback", receipt)
        deploy.app_container(self.api.job)["image"] = deploy.ROLLBACK
        with self.assertRaisesRegex(ValueError, "exact forward image digest"):
            self.change("rollback", receipt, "67")
        self.assertEqual(self.api.writes, 1)

    def test_workflow_gates_and_isolates_the_image_only_job(self):
        workflow = (ROOT / ".github/workflows/gcp_notifications_job.yml").read_text()
        full, image_only = workflow.split("\n  image-only:\n", 1)
        self.assertIn("    if: inputs.mode == 'full'", full)
        self.assertIn("group: deploy-cloud-run-notifications-job-${{ github.event.inputs.environment }}", full)
        self.assertIn("cancel-in-progress: false", full)
        self.assertIn("    environment: prod", image_only)
        self.assertIn('test "$GITHUB_REF" = refs/heads/main', image_only)
        self.assertIn('test "$TARGET_ENVIRONMENT" = prod', image_only)
        for forbidden in ("deploy-cloudrun", "scheduler_reconcile", "gcloud monitoring", "gcloud logging",
                          "attach_cloud_run_gmp_sidecar", "jobs run"):
            self.assertNotIn(forbidden, image_only)


if __name__ == "__main__":
    unittest.main()
