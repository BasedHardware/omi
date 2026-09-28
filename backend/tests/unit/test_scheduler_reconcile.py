from __future__ import annotations

import base64
import copy
import pytest

from scripts import scheduler_reconcile as reconcile


class Response:
    def __init__(self, payload=None, status_code=200):
        self.payload = payload or {}
        self.status_code = status_code

    def json(self):
        return self.payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError("http error")


class FakeSession:
    def __init__(self, current=None):
        self.current = current
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append(("get", url, kwargs))
        if ":access" in url:
            return Response({"payload": {"data": base64.b64encode(b"never-print-me").decode()}})
        if "/locations" in url and "/jobs" not in url:
            return Response({"locations": []})
        if "/jobs/" in url:
            return Response(self.current, 200 if self.current else 404)
        return Response({"jobs": []})

    def patch(self, url, **kwargs):
        self.calls.append(("patch", url, kwargs))
        return Response({})

    def post(self, url, **kwargs):
        self.calls.append(("post", url, kwargs))
        return Response({})


def test_secret_headers_are_resolved_in_memory_and_never_in_diff_output():
    session = FakeSession()
    manifest = reconcile.load_manifest()
    prod = manifest["environments"]["prod"]
    job = next(item for item in prod["jobs"] if item["name"] == "omi-admin-stats-precompute")

    desired = reconcile.desired_resource(session, prod["project"], job)
    assert desired["httpTarget"]["headers"] == {"x-cron-secret": "never-print-me"}
    current = copy.deepcopy(desired)
    current["httpTarget"]["headers"] = {"x-cron-secret": "different"}
    fields = reconcile.diff_fields(current, desired)
    assert fields == ["httpTarget.headers"]
    assert "never-print-me" not in str(fields)


def test_manifest_declares_both_projects_and_paused_agent_vm_job():
    manifest = reconcile.load_manifest()
    assert manifest["environments"]["dev"]["project"] == "based-hardware-dev"
    assert manifest["environments"]["prod"]["project"] == "based-hardware"
    assert {job["name"] for job in manifest["environments"]["dev"]["jobs"]} == {
        "agent-vm-reconciler-5m",
        "daily-memory-sweep-hourly",
        "day3-reengagement-email-daily",
        "knowledge-ledger-drain-hourly",
        "memory-maintenance-hourly",
        "sync-backfill-uid-sequencer",
    }
    assert {job["name"] for job in manifest["environments"]["prod"]["jobs"]} == {
        "day3-reengagement-email-daily",
        "finops-unit-cost-daily",
        "notifications-job-scheduler-trigger",
        "omi-admin-stats-precompute",
        "sentry-feedback-poll",
        "sync-backfill-uid-sequencer",
    }
    agent_vm = next(
        item for item in manifest["environments"]["dev"]["jobs"] if item["name"] == "agent-vm-reconciler-5m"
    )
    assert agent_vm["state"] == "PAUSED"


def test_project_is_pinned_and_apply_only_updates_declared_jobs():
    manifest = reconcile.load_manifest()
    with pytest.raises(reconcile.ReconcileError, match="project mismatch"):
        reconcile.reconcile(FakeSession(), manifest, "dev", "based-hardware", apply=True, include_unlisted=False)

    job = manifest["environments"]["dev"]["jobs"][0]
    current = {
        "name": f"projects/based-hardware-dev/locations/{job['region']}/jobs/{job['name']}",
        "schedule": "wrong",
        "timeZone": job["time_zone"],
        "httpTarget": {"uri": job["target"]["uri"], "httpMethod": "POST"},
        "state": "ENABLED",
    }
    session = FakeSession(current)
    differences, messages = reconcile.reconcile(
        session,
        manifest,
        "dev",
        "based-hardware-dev",
        apply=True,
        selected_jobs={job["name"]},
        include_unlisted=False,
    )
    assert differences == [current["name"]]
    assert messages[0].startswith("APPLIED ")
    assert any(call[0] == "patch" for call in session.calls)
    assert all("delete" not in call[0] for call in session.calls)


def test_check_reports_unlisted_job_without_deleting():
    manifest = reconcile.load_manifest()
    session = FakeSession()
    session.get = lambda url, **kwargs: Response(
        {"locations": [{"name": "projects/based-hardware-dev/locations/us-central1", "locationId": "us-central1"}]}
        if "/locations" in url and "/jobs" not in url
        else {"jobs": [{"name": "projects/based-hardware-dev/locations/us-central1/jobs/unlisted"}]}
    )
    differences, messages = reconcile.reconcile(
        session, manifest, "dev", "based-hardware-dev", apply=False, selected_jobs=set(), include_unlisted=True
    )
    assert differences == ["unlisted:us-central1/unlisted"]
    assert messages == [
        "UNLISTED projects/based-hardware-dev/locations/us-central1/jobs/unlisted: retained; no delete performed"
    ]
