import copy
import datetime as dt
import json
from pathlib import Path
import unittest
from provision import plan, validate


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.spec = json.loads((Path(__file__).parents[2] / "docs/experiments/summary-feedback-layout.json").read_text())
        self.now = dt.datetime(2026, 9, 22, tzinfo=dt.timezone.utc)

    def test_plan_cannot_launch(self):
        result = plan(self.spec, 123, self.now)
        self.assertTrue(result["dry_run"])
        self.assertFalse(result["requests"][0]["body"]["active"])
        self.assertEqual(result["requests"][0]["body"]["filters"]["groups"][0]["rollout_percentage"], 0)
        self.assertIsNone(result["requests"][1]["body"]["start_date"])
        self.assertNotIn("/launch/", json.dumps(result))

    def test_required_operational_fields(self):
        for field in ("owner", "hypothesis", "primary_metric", "guardrails", "targeting", "variants", "expires_at", "collision_policy", "analysis"):
            spec = copy.deepcopy(self.spec)
            del spec[field]
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate(spec, self.now)

    def test_bad_weights_expiry_status_and_project(self):
        for changes in ({"status": "running"}, {"expires_at": "2020-01-01T00:00:00Z"},
                        {"variants": [{"key": "control", "rollout_percentage": 50}, {"key": "test", "rollout_percentage": 20}]}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                validate({**self.spec, **changes}, self.now)
        with self.assertRaises(ValueError):
            plan(self.spec, "../other", self.now)

class FakeResponse:
    status = 200

    def __init__(self, payload):
        import io
        self.stream = io.BytesIO(json.dumps(payload).encode())

    def read(self, *args):
        return self.stream.read(*args)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class MockManagementHttp:
    """In-memory PostHog HTTP fixture, with paginated discovery and read-back."""
    def __init__(self):
        self.flags, self.experiments, self.requests = {}, {}, []
        self.fail_experiment_create = False
        self.foreign_next = False

    def open(self, request, timeout):
        import urllib.parse
        import urllib.error
        parsed = urllib.parse.urlsplit(request.full_url)
        self.requests.append((request.method, parsed.path, request.data))
        assert request.get_header("Authorization") == "Bearer mocked-secret"
        assert timeout == 20
        collection = self.flags if "/feature_flags/" in parsed.path else self.experiments
        tail = parsed.path.rstrip("/").split("/")[-1]
        if request.method == "GET":
            if tail.isdigit():
                return FakeResponse(collection[int(tail)])
            if "offset=" not in parsed.query:
                return FakeResponse({"results": [], "next": "https://foreign.invalid/steal" if self.foreign_next else request.full_url + ("&" if parsed.query else "?") + "offset=1"})
            return FakeResponse({"results": list(collection.values()), "next": None})
        if collection is self.experiments and self.fail_experiment_create:
            self.fail_experiment_create = False
            raise urllib.error.URLError("synthetic offline")
        value = json.loads(request.data)
        value["id"] = len(collection) + 1
        if collection is self.experiments:
            value["status"] = "draft"
        collection[value["id"]] = value
        return FakeResponse(value)


class ReconcileTests(unittest.TestCase):
    def setUp(self):
        from provision import ManagementApi
        self.spec = json.loads((Path(__file__).parents[2] / "docs/experiments/summary-feedback-layout.json").read_text())
        self.draft = plan(self.spec, 123, dt.datetime(2026, 9, 22, tzinfo=dt.timezone.utc))
        self.api = ManagementApi("https://us.posthog.com", 123, "mocked-secret")
        self.http = MockManagementHttp()
        self.api.opener = self.http

    def apply(self):
        from provision import reconcile
        return reconcile(self.draft, self.api)

    def test_real_metric_and_exposure_payloads(self):
        body = self.draft["requests"][1]["body"]
        metric = body["metrics"][0]
        self.assertEqual(metric["kind"], "ExperimentMetric")
        self.assertEqual(metric["metric_type"], "funnel")
        self.assertEqual(metric["conversion_window"], 24)
        self.assertEqual(metric["conversion_window_unit"], "hour")
        self.assertEqual(metric["series"][0]["event"], "Product Journey Outcome")
        self.assertEqual({p["key"]: p["value"] for p in metric["series"][0]["properties"]},
                         {"journey": "summary_feedback", "outcome": "success", "experiment_context_verified": True,
                          f"$feature/{self.spec['key']}": ["control", "compact"]})
        self.assertEqual([metric["goal"] for metric in body["metrics_secondary"]], ["decrease"])
        guardrail = body["metrics_secondary"][0]["series"][0]
        self.assertEqual(guardrail["event"], "Product Journey Outcome")
        self.assertEqual({p["key"]: p["value"] for p in guardrail["properties"]},
                         {"journey": "summary_feedback", "outcome": "failure", "experiment_context_verified": True,
                          f"$feature/{self.spec['key']}": ["control", "compact"]})
        exposure = body["exposure_criteria"]["exposure_config"]
        self.assertEqual(exposure["event"], "experiment_exposed")
        self.assertEqual({p["key"]: p["value"] for p in exposure["properties"]},
                         {"experiment_key": self.spec["key"], "experiment_version": 1, "experiment_qa": False})
        all_metrics = body["metrics"] + body["metrics_secondary"]
        self.assertEqual(len({metric["uuid"] for metric in all_metrics}), 2)

    def test_create_and_idempotent_paginated_reconcile(self):
        receipt = self.apply()
        self.assertEqual(receipt["created"], ["flag", "experiment"])
        self.assertFalse(self.http.flags[1]["active"])
        second = self.apply()
        self.assertEqual(second["created"], [])
        self.assertEqual(len([r for r in self.http.requests if r[0] == "POST"]), 2)

    def test_partial_failure_resumes_without_duplicate_flag(self):
        from provision import ProvisionError
        self.http.fail_experiment_create = True
        with self.assertRaises(ProvisionError):
            self.apply()
        self.assertEqual(len(self.http.flags), 1)
        self.assertEqual(len(self.http.experiments), 0)
        receipt = self.apply()
        self.assertEqual(receipt["created"], ["experiment"])
        self.assertEqual(len(self.http.flags), 1)

    def test_active_scheduled_and_completed_experiments_never_mutate(self):
        from provision import ProvisionError
        self.apply()
        for change in ({"status": "running", "start_date": "2026-09-22T00:00:00Z"},
                       {"status": "complete"}, {"scheduling_config": {"start_date": "2026-10-01"}}):
            original = copy.deepcopy(self.http.experiments[1])
            self.http.experiments[1].update(change)
            self.http.requests.clear()
            with self.subTest(change=change), self.assertRaises(ProvisionError):
                self.apply()
            self.assertFalse(any(r[0] != "GET" for r in self.http.requests))
            self.http.experiments[1] = original

    def test_active_flag_foreign_owner_version_and_metric_drift_refused(self):
        from provision import ProvisionError
        self.apply()
        changes = [(self.http.flags, {"active": True}), (self.http.flags, {"name": "someone else's flag"}),
                   (self.http.experiments, {"description": "foreign or changed version"}),
                   (self.http.experiments, {"metrics": []})]
        for collection, change in changes:
            original = copy.deepcopy(collection[1])
            collection[1].update(change)
            self.http.requests.clear()
            with self.subTest(change=change), self.assertRaises(ProvisionError):
                self.apply()
            self.assertFalse(any(r[0] != "GET" for r in self.http.requests))
            collection[1] = original

    def test_foreign_pagination_is_blocked_before_token_send(self):
        from provision import ProvisionError
        self.http.foreign_next = True
        with self.assertRaises(ProvisionError):
            self.apply()
        self.assertEqual(len(self.http.requests), 1)

    def test_missing_credentials_and_mutating_existing_endpoints_refused(self):
        from provision import ManagementApi, ProvisionError
        with self.assertRaises(ProvisionError):
            ManagementApi("https://us.posthog.com", 123, "")
        with self.assertRaises(ProvisionError):
            self.api.request("POST", "/api/projects/123/experiments/1/launch/", {})
        with self.assertRaises(ProvisionError):
            self.api.request("PATCH", "/api/projects/123/experiments/1/", {})
        self.assertEqual(self.http.requests, [])


if __name__ == "__main__":
    unittest.main()
