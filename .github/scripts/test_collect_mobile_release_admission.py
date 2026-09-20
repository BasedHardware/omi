#!/usr/bin/env python3
"""Hermetic tests for authenticated mobile admission collection."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest

SCRIPT = Path(__file__).with_name("collect_mobile_release_admission.py")
SPEC = importlib.util.spec_from_file_location("collect_mobile_release_admission", SCRIPT)
assert SPEC and SPEC.loader
collector = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = collector
SPEC.loader.exec_module(collector)

SHA = "a" * 40
MAIN = "b" * 40
REPOSITORY = "BasedHardware/omi"
RELEASE_RUNS_PATH = f"/repos/{REPOSITORY}/actions/runs?head_sha={SHA}&event=push&branch=main&per_page=100"


def responses() -> dict[str, dict[str, object]]:
    return {
        f"/repos/{REPOSITORY}/git/ref/heads/main": {"object": {"sha": MAIN}},
        f"/repos/{REPOSITORY}/compare/{SHA}...{MAIN}": {"status": "ahead"},
        f"/repos/{REPOSITORY}/actions/runs?head_sha={SHA}&event=push&branch=main&per_page=100": {
            "workflow_runs": [{
                "name": "Release Eligibility",
                "path": ".github/workflows/release-eligibility.yml",
                "event": "push",
                "status": "completed",
                "conclusion": "success",
                "run_attempt": 1,
                "head_branch": "main",
                "head_sha": SHA,
                "repository": {"full_name": REPOSITORY},
            }],
        },
        f"/repos/{REPOSITORY}/commits/{SHA}/check-runs?per_page=100": {
            "check_runs": [{
                "name": "Mobile Release Eligibility",
                "status": "completed",
                "conclusion": "success",
                "head_sha": SHA,
                "details_url": "https://github.com/BasedHardware/omi/actions/runs/12345/job/67890",
            }],
        },
        f"/repos/{REPOSITORY}/actions/runs/12345": {
            "name": "Mobile App Checks",
            "path": ".github/workflows/mobile-app-checks.yml",
            "event": "push",
            "status": "completed",
            "conclusion": "success",
            "run_attempt": 1,
            "head_branch": "main",
            "head_sha": SHA,
            "repository": {"full_name": REPOSITORY},
        },
        f"/repos/{REPOSITORY}/actions/runs/12345/jobs?per_page=100": {
            "jobs": [{
                "id": 67890,
                "name": "Mobile Release Eligibility",
                "status": "completed",
                "conclusion": "success",
            }],
        },
    }


def add_page_two_evidence(data: dict[str, dict[str, object]]) -> None:
    release_path = f"/repos/{REPOSITORY}/actions/runs?head_sha={SHA}&event=push&branch=main&per_page=100"
    checks_path = f"/repos/{REPOSITORY}/commits/{SHA}/check-runs?per_page=100"
    jobs_path = f"/repos/{REPOSITORY}/actions/runs/12345/jobs?per_page=100"

    release = data[release_path]["workflow_runs"][0]
    aggregate = data[checks_path]["check_runs"][0]
    job = data[jobs_path]["jobs"][0]
    data[release_path]["workflow_runs"] = [{} for _ in range(collector.GITHUB_PAGE_SIZE)]
    data[checks_path]["check_runs"] = [{} for _ in range(collector.GITHUB_PAGE_SIZE)]
    data[jobs_path]["jobs"] = [{} for _ in range(collector.GITHUB_PAGE_SIZE)]
    data[f"{release_path}&page=2"] = {"workflow_runs": [release]}
    data[f"{checks_path}&page=2"] = {"check_runs": [aggregate]}
    data[f"{jobs_path}&page=2"] = {"jobs": [job]}


class CollectorTests(unittest.TestCase):
    def test_collects_and_revalidates_exact_success(self) -> None:
        data = responses()
        proof = collector.collect_from_github(lambda path: data[path], repository=REPOSITORY, source_sha=SHA)
        self.assertEqual(proof["source_sha"], SHA)
        self.assertEqual(proof["mobile_aggregate"]["check_name"], "Mobile Release Eligibility")

    def test_rejects_wrong_sha_or_missing_proof(self) -> None:
        data = responses()
        data[RELEASE_RUNS_PATH]["workflow_runs"] = []
        with self.assertRaises(collector.AdmissionCollectionError):
            collector.collect_from_github(lambda path: data[path], repository=REPOSITORY, source_sha=SHA)

    def test_rejects_rerun_and_failed_aggregate(self) -> None:
        data = responses()
        data[RELEASE_RUNS_PATH]["workflow_runs"][0]["run_attempt"] = 2
        with self.assertRaises(collector.AdmissionCollectionError):
            collector.collect_from_github(lambda path: data[path], repository=REPOSITORY, source_sha=SHA)

        data = responses()
        data[f"/repos/{REPOSITORY}/commits/{SHA}/check-runs?per_page=100"]["check_runs"][0]["conclusion"] = "failure"
        with self.assertRaises(collector.AdmissionCollectionError):
            collector.collect_from_github(lambda path: data[path], repository=REPOSITORY, source_sha=SHA)

    def test_collects_exact_release_aggregate_and_job_from_page_two(self) -> None:
        data = responses()
        add_page_two_evidence(data)

        proof = collector.collect_from_github(lambda path: data[path], repository=REPOSITORY, source_sha=SHA)

        self.assertEqual(proof["release_eligibility"]["head_sha"], SHA)
        self.assertEqual(proof["mobile_aggregate"]["check_name"], "Mobile Release Eligibility")

    def test_rejects_malformed_or_exhausted_pagination(self) -> None:
        data = responses()
        release_path = RELEASE_RUNS_PATH
        data[release_path]["workflow_runs"] = [{} for _ in range(collector.GITHUB_PAGE_SIZE)]
        data[f"{release_path}&page=2"] = {"workflow_runs": {"unexpected": "object"}}
        with self.assertRaises(collector.AdmissionCollectionError):
            collector.collect_from_github(lambda path: data[path], repository=REPOSITORY, source_sha=SHA)

        data = responses()
        data[release_path]["workflow_runs"] = [{} for _ in range(collector.GITHUB_PAGE_SIZE)]
        for page_number in range(2, collector.MAX_PAGINATION_PAGES + 1):
            data[f"{release_path}&page={page_number}"] = {
                "workflow_runs": [{} for _ in range(collector.GITHUB_PAGE_SIZE)]
            }
        with self.assertRaises(collector.AdmissionCollectionError):
            collector.collect_from_github(lambda path: data[path], repository=REPOSITORY, source_sha=SHA)


if __name__ == "__main__":
    unittest.main()
