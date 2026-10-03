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


def test_http_failures_show_method_status_and_redacted_path_without_query_or_body():
    class FailingSession:
        def get(self, _url, **_kwargs):
            return Response({"error": {"message": "response-body-secret"}}, status_code=403)

    url = (
        "https://secretmanager.googleapis.com/v1/projects/based-hardware/secrets/"
        "private-secret-name/versions/private-version:access?alt=json&access_token=query-secret"
    )
    with pytest.raises(reconcile.ReconcileError) as error:
        reconcile._request(FailingSession(), "get", url)

    message = str(error.value)
    assert message == (
        "HTTP GET /v1/projects/based-hardware/secrets/[REDACTED]/versions/[REDACTED]:access returned status 403"
    )
    for sensitive_value in ("private-secret-name", "private-version", "response-body-secret", "query-secret", "?"):
        assert sensitive_value not in message


def test_manifest_declares_both_projects_and_frame_retention_jobs_without_retired_agent_vm():
    manifest = reconcile.load_manifest()
    assert manifest["environments"]["dev"]["project"] == "based-hardware-dev"
    assert manifest["environments"]["prod"]["project"] == "based-hardware"
    dev_jobs = {job["name"]: job for job in manifest["environments"]["dev"]["jobs"]}
    prod_jobs = {job["name"]: job for job in manifest["environments"]["prod"]["jobs"]}
    assert set(dev_jobs) == {
        "daily-memory-sweep-hourly",
        "day3-reengagement-email-daily",
        "frame-request-retention-hourly",
        "knowledge-ledger-drain-hourly",
        "memory-maintenance-hourly",
        "sync-backfill-uid-sequencer",
    }
    assert set(prod_jobs) == {
        "day3-reengagement-email-daily",
        "finops-unit-cost-daily",
        "frame-request-retention-hourly",
        "notifications-job-scheduler-trigger",
        "omi-admin-stats-precompute",
        "sentry-feedback-poll",
        "sync-backfill-uid-sequencer",
    }
    assert "agent-vm-reconciler-5m" not in dev_jobs
    for env_jobs, project in ((dev_jobs, "based-hardware-dev"), (prod_jobs, "based-hardware")):
        job = env_jobs["frame-request-retention-hourly"]
        assert job["lifecycle"] == "planned"
        assert job["schedule"] == "0 * * * *"
        assert job["time_zone"] == "Etc/UTC"
        assert job["state"] == "ENABLED"
        assert job["target"]["uri"] == (
            f"https://run.googleapis.com/v2/projects/{project}/locations/us-central1/"
            "jobs/frame-request-retention-job:run"
        )
        assert job["target"]["oauth"]["service_account"] == (
            f"frame-retention-scheduler@{project}.iam.gserviceaccount.com"
        )


def _planned_frame_retention_manifest():
    manifest = copy.deepcopy(reconcile.load_manifest())
    for environment in manifest["environments"].values():
        environment["jobs"] = [job for job in environment["jobs"] if job["name"] == "frame-request-retention-hourly"]
    return manifest


def test_check_reports_missing_planned_job_without_counting_a_difference():
    manifest = _planned_frame_retention_manifest()
    session = FakeSession()

    differences, messages = reconcile.reconcile(
        session,
        manifest,
        "dev",
        "based-hardware-dev",
        apply=False,
        include_unlisted=False,
    )

    assert differences == []
    assert messages == [
        "PLANNED projects/based-hardware-dev/locations/us-central1/jobs/frame-request-retention-hourly: not deployed"
    ]


def test_full_apply_skips_planned_job_unless_it_is_explicitly_selected():
    manifest = _planned_frame_retention_manifest()
    session = FakeSession()

    differences, messages = reconcile.reconcile(
        session,
        manifest,
        "dev",
        "based-hardware-dev",
        apply=True,
        include_unlisted=False,
    )

    assert differences == []
    assert messages == [
        "PLANNED projects/based-hardware-dev/locations/us-central1/jobs/frame-request-retention-hourly: "
        "skipped; select it explicitly with --jobs to deploy"
    ]
    assert session.calls == []


def test_explicitly_selected_planned_job_can_be_created():
    manifest = _planned_frame_retention_manifest()
    session = FakeSession()
    resource = "projects/based-hardware-dev/locations/us-central1/jobs/frame-request-retention-hourly"

    differences, messages = reconcile.reconcile(
        session,
        manifest,
        "dev",
        "based-hardware-dev",
        apply=True,
        selected_jobs={"frame-request-retention-hourly"},
        include_unlisted=False,
    )

    assert differences == [resource]
    assert messages == [f"APPLIED {resource}: missing, state"]
    assert [
        (method, kwargs.get("params", {}).get("jobId")) for method, _, kwargs in session.calls if method == "post"
    ] == [("post", "frame-request-retention-hourly")]


def test_check_validates_a_planned_job_after_it_exists():
    manifest = _planned_frame_retention_manifest()
    project = "based-hardware-dev"
    job = manifest["environments"]["dev"]["jobs"][0]
    resource = f"projects/{project}/locations/us-central1/jobs/frame-request-retention-hourly"
    current = reconcile.desired_resource(FakeSession(), project, job)
    current.update({"name": resource, "state": "ENABLED"})

    differences, messages = reconcile.reconcile(
        FakeSession(current),
        manifest,
        "dev",
        project,
        apply=False,
        include_unlisted=False,
    )

    assert differences == []
    assert messages == [f"MATCH {resource}"]


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


def test_owner_scheduler_checks_are_scoped_and_central_reconcile_remains_full_manifest():
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    owner_checks = {
        ".github/actions/sync-backfill-lifecycle/action.yml": "--check --jobs sync-backfill-uid-sequencer",
        ".github/workflows/gcp_daily_memory_sweep_job.yml": "--jobs \"$SCHEDULER_JOB\" \"$LEDGER_DRAIN_SCHEDULER_JOB\"",
        ".github/workflows/gcp_daily_memory_sweep_job_auto_dev.yml": "--jobs \"$SCHEDULER_JOB\" \"$LEDGER_DRAIN_SCHEDULER_JOB\"",
        ".github/workflows/gcp_day3_reengagement_email_job.yml": "--check --jobs \"$SCHEDULER_JOB\"",
        ".github/workflows/gcp_day3_reengagement_email_job_auto_dev.yml": "--check --jobs \"$SCHEDULER_JOB\"",
        ".github/workflows/gcp_frame_request_retention_job.yml": "--check --jobs \"$SCHEDULER_JOB\"",
        ".github/workflows/gcp_memory_maintenance_job.yml": "--check --jobs \"$SCHEDULER_JOB\"",
        ".github/workflows/gcp_memory_maintenance_job_auto_dev.yml": "--check --jobs \"$SCHEDULER_JOB\"",
        ".github/workflows/gcp_notifications_job.yml": "--check --jobs notifications-job-scheduler-trigger",
    }
    for relative_path, scoped_args in owner_checks.items():
        text = (root / relative_path).read_text(encoding="utf-8")
        assert scoped_args in text, relative_path
        scheduler_calls = [segment[:400] for segment in text.split("scheduler_reconcile.py")[1:]]
        check_commands = [command for command in scheduler_calls if "--check" in command]
        assert check_commands, relative_path
        assert all("--jobs" in command for command in check_commands), relative_path

    admin_workflow = (root / ".github/workflows/gcp_admin.yml").read_text(encoding="utf-8")
    assert "scheduler_reconcile.py" not in admin_workflow
    assert "omi-admin-stats-precompute" not in admin_workflow

    central_workflow = (root / ".github/workflows/gcp_scheduler_reconcile.yml").read_text(encoding="utf-8")
    assert "--apply" in central_workflow
    assert "--check" in central_workflow

    jobs_yaml = (root / "backend/deploy/scheduler/jobs.yaml").read_text(encoding="utf-8")
    admin_job = jobs_yaml.split("- name: omi-admin-stats-precompute", 1)[1].split("- name:", 1)[0]
    assert "owner: .github/workflows/gcp_scheduler_reconcile.yml" in admin_job

    central = (root / ".github/workflows/gcp_scheduler_reconcile.yml").read_text(encoding="utf-8")
    assert '--project "$PROJECT_ID" --check' in central
    assert '--project "$PROJECT_ID" --check --jobs' not in central
