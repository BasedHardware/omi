#!/usr/bin/env python3
"""Focused tests for the provider-neutral mobile distribution contract."""

import importlib.util
from pathlib import Path
import sys
import unittest

SPEC = importlib.util.spec_from_file_location(
    "mobile_distribution", Path(__file__).with_name("mobile_distribution.py")
)
assert SPEC and SPEC.loader
mod = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = mod
SPEC.loader.exec_module(mod)

SHA = "a" * 40


def build(*, status="finished", platform="ios", outcome="distributed", verification="verified"):
    return {
        "status": status,
        "commit": SHA,
        "distribution_evidence": {
            "schema": mod.SCHEMA,
            "platform": platform,
            "source_sha": SHA,
            "outcome": outcome,
            "verification": verification,
        },
    }


class TestMobileDistribution(unittest.TestCase):
    def test_normalizes_successful_codemagic_android_publishing(self):
        detail = {
            "status": "finished",
            "commit": {"hash": SHA},
            "buildActions": [{"type": "publishing", "status": "success"}],
        }
        normalized = mod.normalize_codemagic_build(detail, platform="android", workflow_id="android-internal-auto")
        self.assertTrue(mod.is_baseline_eligible(normalized, platform="android"))

    def test_android_without_provider_distribution_evidence_is_unverified(self):
        detail = {"status": "finished", "commit": {"hash": SHA}}
        normalized = mod.normalize_codemagic_build(detail, platform="android", workflow_id="android-internal-auto")
        self.assertFalse(mod.is_baseline_eligible(normalized, platform="android"))

    def test_unsupported_android_receipt_is_not_treated_as_distribution_evidence(self):
        detail = {
            "status": "finished",
            "commit": {"hash": SHA},
            "googlePlayTasks": [{"status": "success"}],
        }
        normalized = mod.normalize_codemagic_build(detail, platform="android", workflow_id="android-internal-auto")
        self.assertFalse(mod.is_baseline_eligible(normalized, platform="android"))

    def test_android_parent_evidence_requires_the_exact_workflow(self):
        detail = {
            "status": "finished",
            "commit": {"hash": SHA},
            "buildActions": [{"type": "publishing", "status": "success"}],
        }
        for workflow_id in (None, "android-internal", "ios-internal-auto"):
            with self.subTest(workflow_id=workflow_id):
                normalized = mod.normalize_codemagic_build(detail, platform="android", workflow_id=workflow_id)
                self.assertFalse(mod.is_baseline_eligible(normalized, platform="android"))

    def test_normalizes_only_successful_ios_store_tasks(self):
        detail = {
            "status": "finished",
            "commit": {"hash": SHA},
            "buildActions": [{"type": "publishing", "status": "success"}],
            "appStoreConnectTasks": [{"status": "failed"}],
        }
        self.assertFalse(
            mod.is_baseline_eligible(
                mod.normalize_codemagic_build(detail, platform="ios", workflow_id="ios-internal-auto"),
                platform="ios",
            )
        )
        detail["appStoreConnectTasks"] = [{"name": "App Store Connect distribution", "status": "success"}]
        self.assertTrue(
            mod.is_baseline_eligible(
                mod.normalize_codemagic_build(detail, platform="ios", workflow_id="ios-internal-auto"),
                platform="ios",
            )
        )

    def test_rejects_extra_or_wrong_distribution_tasks(self):
        detail = {
            "status": "finished",
            "commit": {"hash": SHA},
            "buildActions": [
                {"type": "publishing", "status": "success"},
                {"type": "publishing", "status": "failed"},
            ],
            "appStoreConnectTasks": [{"name": "IPA upload", "status": "success"}],
        }
        normalized = mod.normalize_codemagic_build(detail, platform="ios", workflow_id="ios-internal-auto")
        self.assertFalse(mod.is_baseline_eligible(normalized, platform="ios"))

    def test_failed_publishing_children_cannot_advance_baseline(self):
        for status in ("failed", "cancelled", "pending"):
            with self.subTest(status=status):
                detail = {
                    "status": "finished",
                    "commit": {"hash": SHA},
                    "buildActions": [
                        {
                            "type": "publishing",
                            "status": "success",
                            "subActions": [{"name": "store distribution", "status": status}],
                        }
                    ],
                    "appStoreConnectTasks": [
                        {"name": "App Store Connect distribution", "status": "success"}
                    ],
                }
                normalized = mod.normalize_codemagic_build(detail, platform="ios", workflow_id="ios-internal-auto")
                self.assertFalse(mod.is_baseline_eligible(normalized, platform="ios"))

    def test_malformed_publishing_children_are_unverified(self):
        for child_records in (None, [None], ["not an object"], [{"name": "store distribution"}], []):
            with self.subTest(child_records=child_records):
                detail = {
                    "status": "finished",
                    "commit": {"hash": SHA},
                    "buildActions": [
                        {"type": "publishing", "status": "success", "subActions": child_records}
                    ],
                    "appStoreConnectTasks": [
                        {"name": "App Store Connect distribution", "status": "success"}
                    ],
                }
                normalized = mod.normalize_codemagic_build(detail, platform="ios", workflow_id="ios-internal-auto")
                self.assertFalse(mod.is_baseline_eligible(normalized, platform="ios"))

    def test_malformed_ios_task_entries_return_original_build(self):
        for tasks in ([None], ["not an object"], [{"status": "success"}, None]):
            with self.subTest(tasks=tasks):
                detail = {
                    "status": "finished",
                    "commit": {"hash": SHA},
                    "buildActions": [{"type": "publishing", "status": "success"}],
                    "appStoreConnectTasks": tasks,
                }
                normalized = mod.normalize_codemagic_build(detail, platform="ios", workflow_id="ios-internal-auto")
                self.assertIs(normalized, detail)
                self.assertFalse(mod.is_baseline_eligible(normalized, platform="ios"))

    def test_malformed_ios_tasks_do_not_affect_android_evaluation(self):
        detail = {
            "status": "finished",
            "commit": {"hash": SHA},
            "buildActions": [{"type": "publishing", "status": "success"}],
            "appStoreConnectTasks": [None],
        }
        ios = mod.normalize_codemagic_build(detail, platform="ios", workflow_id="ios-internal-auto")
        android = mod.normalize_codemagic_build(detail, platform="android", workflow_id="android-internal-auto")
        self.assertFalse(mod.is_baseline_eligible(ios, platform="ios"))
        self.assertTrue(mod.is_baseline_eligible(android, platform="android"))

    def test_malformed_build_actions_do_not_raise_or_cross_contaminate_platforms(self):
        for actions in (None, True, 1, [None], [{"status": "success"}, "not an object"]):
            with self.subTest(actions=actions):
                detail = {
                    "status": "finished",
                    "commit": {"hash": SHA},
                    "buildActions": actions,
                    "appStoreConnectTasks": [
                        {"name": "App Store Connect distribution", "status": "success"}
                    ],
                }
                ios = mod.normalize_codemagic_build(detail, platform="ios", workflow_id="ios-internal-auto")
                android = mod.normalize_codemagic_build(detail, platform="android", workflow_id="android-internal-auto")
                self.assertIs(ios, detail)
                self.assertIs(android, detail)
                self.assertFalse(mod.is_baseline_eligible(ios, platform="ios"))
                self.assertFalse(mod.is_baseline_eligible(android, platform="android"))

    def test_failed_post_publish_task_cannot_advance_baseline(self):
        self.assertFalse(
            mod.is_baseline_eligible(
                build(verification="failed"),
                platform="ios",
            )
        )

    def test_missing_evidence_is_fail_closed(self):
        record = build()
        del record["distribution_evidence"]
        self.assertFalse(mod.is_baseline_eligible(record, platform="ios"))

    def test_verified_distribution_is_eligible(self):
        self.assertTrue(mod.is_baseline_eligible(build(), platform="ios"))

    def test_explicit_skipped_no_op_is_eligible_without_distribution_success(self):
        self.assertTrue(
            mod.is_baseline_eligible(
                build(status="skipped", outcome="no-op", verification="not_applicable"),
                platform="ios",
            )
        )

    def test_skipped_build_without_explicit_no_op_is_rejected(self):
        self.assertFalse(mod.is_baseline_eligible(build(status="skipped"), platform="ios"))

    def test_malformed_payload_is_fail_closed(self):
        malformed = build()
        malformed["distribution_evidence"]["unexpected"] = "value"
        self.assertFalse(mod.is_baseline_eligible(malformed, platform="ios"))

    def test_platform_mismatch_is_rejected(self):
        self.assertFalse(mod.is_baseline_eligible(build(platform="android"), platform="ios"))

    def test_source_mismatch_is_rejected(self):
        mismatched = build()
        mismatched["distribution_evidence"]["source_sha"] = "b" * 40
        self.assertFalse(mod.is_baseline_eligible(mismatched, platform="ios"))


if __name__ == "__main__":
    unittest.main()
