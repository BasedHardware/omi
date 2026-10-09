#!/usr/bin/env python3
"""Offline report and alert fixtures for the bounded weekly sampler."""

import unittest
from datetime import datetime, timezone

from measure_ci_budget import DAYS, Github, collect, summarize, upsert_issue


class FakeGithub(Github):
    def __init__(self):
        self.repo = "BasedHardware/omi"
        self.calls = []

    def request(self, method, path, body=None):
        self.calls.append((method, path, body))
        if method == "GET":
            return {"items": [{"title": "Weekly CI budget audit", "number": 12}]}
        return {}


class SamplerTests(unittest.TestCase):
    def setUp(self):
        self.budget = {
            "workflows": {"checks.yml": {"triggers": {"pull_request": {}}}},
            "jobs": {"checks.yml/test": {"display_name": "Test", "expected_runs_per_day": 1, "budget_p50_minutes": 2, "runner_counts": {"linux": 1}, "owner": "CI maintainers"}},
            "caps": {"internal_time_to_signal_minutes": 10, "pr_linux_minutes_per_day": 10, "pr_macos_minutes_per_day": 10},
        }
        self.now = datetime(2026, 9, 28, tzinfo=timezone.utc)

    def test_skips_zero_job_and_skipped_jobs(self):
        run = {"head_repository": {"full_name": "BasedHardware/omi"}, "head_sha": "abc", "created_at": "2026-09-28T00:00:00Z"}
        sample = {"workflow": "checks.yml", "repository": "BasedHardware/omi", "run": run, "jobs": [{"name": "Test", "conclusion": "skipped"}]}
        report = summarize(self.budget, [sample], self.now)
        self.assertEqual(report["jobs"]["checks.yml/test"]["count"], 0)
        self.assertIn("under-sampled", " ".join(report["problems"]))

    def test_over_budget_p50_and_issue_dedupe(self):
        run = {"head_repository": {"full_name": "BasedHardware/omi"}, "head_sha": "abc", "created_at": "2026-09-28T00:00:00Z"}
        sample = {"workflow": "checks.yml", "repository": "BasedHardware/omi", "run": run, "jobs": [{"name": "Test", "conclusion": "success", "started_at": "2026-09-28T00:00:00Z", "completed_at": "2026-09-28T00:03:00Z"}]}
        report = summarize(self.budget, [sample], self.now)
        self.assertIn("p50", " ".join(report["problems"]))
        api = FakeGithub()
        upsert_issue(api, report, "report")
        self.assertEqual(api.calls[-1][0:2], ("PATCH", "/repos/BasedHardware/omi/issues/12"))

    def test_collect_uses_one_bounded_daily_page_per_workflow(self):
        class EmptyGithub(FakeGithub):
            def request(self, method, path, body=None):
                self.calls.append((method, path, body))
                return {"workflow_runs": []}

        api = EmptyGithub()
        self.assertEqual(collect(api, self.budget, self.now), [])
        self.assertEqual(len(api.calls), DAYS)
        self.assertTrue(all("per_page=1" in path for _, path, _ in api.calls))


if __name__ == "__main__":
    unittest.main()
