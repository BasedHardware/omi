#!/usr/bin/env python3
"""Behavioral tests for the proactive-delivery health monitor."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch


SCRIPT_DIR = Path(__file__).resolve().parent
MODULE_PATH = SCRIPT_DIR / "desktop_proactive_delivery_health.py"
WORKFLOW_PATH = SCRIPT_DIR.parent / "workflows" / "desktop_release_doctor.yml"
SPEC = importlib.util.spec_from_file_location("desktop_proactive_delivery_health", MODULE_PATH)
assert SPEC and SPEC.loader
health = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(health)


class _Response:
    def __init__(self, payload: object) -> None:
        self.payload = payload

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class ProactiveDeliveryHealthTests(unittest.TestCase):
    def test_exact_zero_alarms_only_with_a_sufficient_denominator(self) -> None:
        result = health.evaluate_counts(2_000, 0, 100, 80, 75)
        self.assertEqual(result["status"], "unhealthy")
        self.assertEqual(result["alarm_reason"], "advice_users_exactly_zero")
        self.assertEqual(result["value"], 0)

        low_sample = health.evaluate_counts(49, 0)
        self.assertEqual(low_sample["status"], "unknown")
        self.assertIsNone(low_sample["alarm_reason"])

    def test_nonzero_advice_population_is_healthy(self) -> None:
        result = health.evaluate_counts(100, 27, 20, 18, 16)
        self.assertEqual(result["status"], "healthy")
        self.assertEqual(result["value"], 0.27)
        self.assertFalse(result["privacy"]["user_identifiers_included"])
        doctor_metric = health.doctor_metric(result)
        self.assertEqual(doctor_metric["health_status"], "healthy")
        self.assertEqual(doctor_metric["numerator"], 27)
        self.assertIsNone(doctor_metric["alarm_reason"])

    def test_delivery_zero_alarms_but_preference_only_outcomes_are_unknown(self) -> None:
        broken_delivery = health.evaluate_counts(100, 27, 20, 0, 0)
        self.assertEqual(broken_delivery["status"], "unhealthy")
        self.assertEqual(broken_delivery["alarm_reason"], "delivered_outcomes_exactly_zero")

        preference_only = health.evaluate_counts(100, 27, 0, 0, 0)
        self.assertEqual(preference_only["status"], "unknown")

    def test_query_is_bounded_to_macos_pt24h_and_returns_counts_only(self) -> None:
        observed: dict[str, object] = {}

        def open_request(request: object, timeout: int) -> _Response:
            observed["request"] = request
            observed["timeout"] = timeout
            return _Response(
                {
                    "results": [[2024, 7, 20, 18, 6]],
                    "columns": [
                        "macos_dau",
                        "advice_users",
                        "eligible_delivery_outcomes",
                        "delivered_outcomes",
                        "delivered_users",
                    ],
                }
            )

        with patch.object(health.urllib.request, "urlopen", side_effect=open_request):
            counts = health.query_counts(
                host="https://us.posthog.com",
                project_id="123",
                personal_api_key="private-key",
            )

        self.assertEqual(counts, (2024, 7, 20, 18, 6))
        request = observed["request"]
        self.assertEqual(request.full_url, "https://us.posthog.com/api/projects/123/query/")
        self.assertEqual(request.get_header("Authorization"), "Bearer private-key")
        query = json.loads(request.data)["query"]["query"]
        self.assertIn("INTERVAL 24 HOUR", query)
        self.assertIn("uniq(person_id)", query)
        self.assertIn("com.omi.computer-macos", query)
        self.assertIn("properties['$os_name'] = 'macOS'", query)
        self.assertNotIn("properties['$os']", query)
        self.assertIn("Advice Generated", query)
        self.assertIn("Advice Delivery Outcome", query)
        self.assertIn("properties['outcome'] = 'delivered'", query)
        self.assertNotIn("properties['transcript']", query)
        self.assertNotIn("properties['content']", query)

    def test_rejects_non_https_hosts_and_non_numeric_projects(self) -> None:
        with self.assertRaises(ValueError):
            health._posthog_endpoint("http://posthog.example", "123")
        with self.assertRaises(ValueError):
            health._posthog_endpoint("https://posthog.example", "project")

    def test_workflow_has_a_scheduled_durable_alarm(self) -> None:
        # omi-test-quality: source-inspection -- static workflow wiring cannot be exercised by the query evaluator.
        workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
        scheduled_job = workflow.split("  proactive-health:\n", 1)[1]
        self.assertIn("schedule:", workflow)
        self.assertNotIn("environment: prod", scheduled_job)
        self.assertIn("secrets.POSTHOG_PERSONAL_API_KEY", scheduled_job)
        self.assertIn("vars.POSTHOG_PROJECT_ID", scheduled_job)
        self.assertIn("vars.POSTHOG_HOST", scheduled_job)
        self.assertIn("desktop_proactive_delivery_health.py", scheduled_job)
        self.assertIn("gh issue create", scheduled_job)
        self.assertIn("gh issue edit", scheduled_job)
        self.assertIn("gh issue close", scheduled_job)

    def test_workflow_treats_missing_posthog_config_as_neutral(self) -> None:
        # omi-test-quality: source-inspection -- the scheduled job must not turn missing Actions config into a red alarm.
        workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
        scheduled_job = workflow.split("  proactive-health:\n", 1)[1]
        self.assertIn("required_config=(POSTHOG_PERSONAL_API_KEY POSTHOG_PROJECT_ID POSTHOG_HOST)", scheduled_job)
        self.assertIn("status=unconfigured", scheduled_job)
        self.assertIn("No health alarm was created or updated.", scheduled_job)
        self.assertIn('"status": "monitor_error"', scheduled_job)
        self.assertNotIn("steps.health.outputs.status == 'unconfigured'", scheduled_job)


if __name__ == "__main__":
    unittest.main()
