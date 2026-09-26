import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from scripts import legacy_memory_retirement_readiness as readiness
from scripts import provision_daily_memory_sweep_scheduler as daily_scheduler
from scripts import validate_memory_maintenance_scheduler as scheduler_validator

BACKEND_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = BACKEND_ROOT / "scripts" / "legacy_memory_retirement_readiness.py"
FIXTURES = Path(__file__).parent / "fixtures" / "legacy_memory_retirement"


def _fixture(name: str) -> dict[str, Any]:
    value = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_active_flags_running_execution_and_enabled_scheduler_are_active() -> None:
    result = readiness.evaluate_snapshot(_fixture("active_running.json"))

    assert result.status == "ACTIVE"
    assert result.counts["active_maintenance_flags"] == 1
    assert result.counts["active_executions"] == 1
    assert result.counts["enabled_schedulers"] == 1
    assert result.reasons == ("maintenance_runtime_active",)


def test_pending_execution_is_live_activity_even_when_other_controls_are_paused() -> None:
    snapshot = _fixture("paused_no_executions.json")
    snapshot["inventories"]["executions"]["resources"] = [
        {
            "project": "sanitized-project",
            "region": "us-central1",
            "job": "memory-maintenance-job",
            "name": "execution-pending",
            "state": "PENDING",
        }
    ]

    result = readiness.evaluate_snapshot(snapshot)

    assert result.status == "ACTIVE"
    assert result.counts["active_executions"] == 1


def test_paused_scheduler_without_executions_is_not_deleted() -> None:
    result = readiness.evaluate_snapshot(_fixture("paused_no_executions.json"))

    assert result.status == "NO_LIVE_ACTIVITY"
    assert result.counts["paused_schedulers"] == 1
    assert result.reasons == ("maintenance_resources_present_without_live_activity",)


def test_complete_empty_inventories_prove_only_the_resources_absent() -> None:
    result = readiness.evaluate_snapshot(_fixture("proven_absent.json"))

    assert result.status == "DELETED"
    assert result.reasons == ("maintenance_resources_proven_absent",)
    assert all(count == 0 for count in result.counts.values())


def test_scheduler_target_contract_cannot_drift_from_authoritative_validator() -> None:
    contract = readiness.Contract(project="sanitized-project", region="us-central1")
    authoritative = scheduler_validator.SchedulerContract(
        project=contract.project,
        region=contract.region,
        scheduler_job=contract.scheduler_job,
        cloud_run_job=contract.cloud_run_job,
    )

    assert contract.scheduler_target_uri == authoritative.target_uri


def test_daily_replacement_has_a_distinct_retained_resource_contract() -> None:
    workflow = BACKEND_ROOT.parent / ".github" / "workflows" / "gcp_daily_memory_sweep_job.yml"
    dockerfile = BACKEND_ROOT / "modal" / "Dockerfile.daily_memory_sweep_job"
    docs = BACKEND_ROOT / "docs" / "doc" / "developer" / "daily-memory-sweep-job.md"
    assert workflow.is_file()
    assert dockerfile.is_file()
    assert docs.is_file()
    text = workflow.read_text(encoding="utf-8")
    assert "daily-memory-sweep-job" in text
    assert "daily-memory-sweep-hourly" in text
    assert readiness.EXPECTED_CLOUD_RUN_JOB == "memory-maintenance-job"
    assert readiness.EXPECTED_SCHEDULER_JOB == "memory-maintenance-hourly"
    runtime_images = json.loads((BACKEND_ROOT.parent / "backend" / "runtime_images.json").read_text(encoding="utf-8"))
    daily_images = [image for image in runtime_images["images"] if image["name"] == "daily-memory-sweep-job"]
    assert len(daily_images) == 1
    assert daily_images[0]["dockerfile"] == "backend/modal/Dockerfile.daily_memory_sweep_job"
    assert daily_images[0]["entrypoints"] == ["daily_memory_sweep_job"]
    assert set(daily_images[0]["deployment_workflows"]) == {
        ".github/workflows/gcp_daily_memory_sweep_job_auto_dev.yml",
        ".github/workflows/gcp_daily_memory_sweep_job.yml",
        ".github/workflows/jit_qa_cloud_run.yml",
    }


def test_daily_manual_deploy_is_main_only_admitted_and_provisions_scheduler() -> None:
    workflow = (BACKEND_ROOT.parent / ".github" / "workflows" / "gcp_daily_memory_sweep_job.yml").read_text(
        encoding="utf-8"
    )
    assert "release_sha:" in workflow
    assert "Require exact main dispatch ref" in workflow
    assert '"refs/heads/main"' in workflow
    assert "release-eligibility.yml" in workflow
    assert "verify_backend_release_admission.py" in workflow
    assert "--require-first-attempt" in workflow
    assert '"$DEPLOY_SHA" != "$main_sha"' in workflow
    assert "ref: ${{ steps.admitted_source.outputs.admitted_sha }}" in workflow
    assert "provision_daily_memory_sweep_scheduler.py" in workflow
    assert workflow.index("Checkout admitted source") < workflow.index("Provision hourly Scheduler trigger")
    assert workflow.index("Provision hourly Scheduler trigger") < workflow.index("Validate hourly Scheduler trigger")
    assert "Recheck admitted main before image publication" in workflow
    assert "Recheck admitted main before Cloud Run deployment" in workflow
    assert "branch:" not in workflow

    auto_workflow = (
        BACKEND_ROOT.parent / ".github" / "workflows" / "gcp_daily_memory_sweep_job_auto_dev.yml"
    ).read_text(encoding="utf-8")
    for admitted_workflow in (auto_workflow,):
        assert "workflow_run:" in admitted_workflow
        assert 'workflows: ["Release Eligibility"]' in admitted_workflow
        assert "Require successful first-attempt Release Eligibility push" in admitted_workflow
        assert "github.event.workflow_run.conclusion == 'success'" in admitted_workflow
        assert "github.event.workflow_run.run_attempt == 1" in admitted_workflow
        assert "release-eligibility.yml" in admitted_workflow
        assert "--require-first-attempt" in admitted_workflow
        assert '"$DEPLOY_SHA" == "$main_sha"' in admitted_workflow
        assert "ref: ${{ steps.admitted_source.outputs.admitted_sha }}" in admitted_workflow
        assert "Recheck admitted main before image publication" in admitted_workflow
        assert "Recheck admitted main before Cloud Run deployment" in admitted_workflow


def test_daily_scheduler_provisioner_creates_or_updates_only_the_retained_contract() -> None:
    commands = []

    class Result:
        returncode = 1
        stderr = "not found"

    def runner(command, **_kwargs):
        commands.append(command)
        return Result()

    action = daily_scheduler.ensure_scheduler(
        project="based-hardware-dev",
        region="us-central1",
        service_account="memory-maintenance-scheduler@based-hardware-dev.iam.gserviceaccount.com",
        runner=runner,
    )
    assert action == "create"
    assert commands[0][3] == "describe"
    assert commands[1][3:6] == ["create", "http", "daily-memory-sweep-hourly"]
    assert "jobs/daily-memory-sweep-job:run" in " ".join(commands[1])

    ledger_args = daily_scheduler.scheduler_http_args(
        "create",
        project="based-hardware-dev",
        region="us-central1",
        scheduler_job="knowledge-ledger-drain-hourly",
        cloud_run_job="knowledge-ledger-drain-job",
        service_account="scheduler@based-hardware-dev.iam.gserviceaccount.com",
    )
    assert "knowledge-ledger-drain-hourly" in ledger_args
    assert "jobs/knowledge-ledger-drain-job:run" in " ".join(ledger_args)

    with pytest.raises(ValueError, match="retained contract"):
        daily_scheduler.scheduler_http_args(
            "create",
            project="based-hardware-dev",
            region="us-central1",
            scheduler_job="memory-maintenance-hourly",
            cloud_run_job="daily-memory-sweep-job",
            service_account="scheduler@based-hardware-dev.iam.gserviceaccount.com",
        )

    update_commands = []

    class ExistingResult:
        returncode = 0

    def update_runner(command, **_kwargs):
        update_commands.append(command)
        return ExistingResult()

    assert (
        daily_scheduler.ensure_scheduler(
            project="based-hardware-dev",
            region="us-central1",
            service_account="memory-maintenance-scheduler@based-hardware-dev.iam.gserviceaccount.com",
            runner=update_runner,
        )
        == "update"
    )
    assert update_commands[1][3:6] == ["update", "http", "daily-memory-sweep-hourly"]
    assert update_commands[2][3] == "resume"


def test_legacy_entrypoint_cannot_reset_or_delete_daily_inventory_controls() -> None:
    legacy_entrypoint = BACKEND_ROOT / "modal" / "memory_maintenance_job.py"
    daily_entrypoint = BACKEND_ROOT / "modal" / "daily_memory_sweep_job.py"
    daily_inventory = BACKEND_ROOT / "utils" / "memory" / "daily_memory_sweep_inventory.py"
    legacy_source = legacy_entrypoint.read_text(encoding="utf-8")
    daily_source = daily_entrypoint.read_text(encoding="utf-8")
    inventory_source = daily_inventory.read_text(encoding="utf-8")

    assert "daily_memory" not in legacy_source
    assert "canonical_short_term_maintenance_cron" not in daily_source
    assert "memory_maintenance_job" not in daily_source
    assert "CANONICAL_MEMORY_MAINTENANCE_CURSOR_PATH" not in inventory_source
    assert "CANONICAL_MEMORY_MAINTENANCE_REGISTRY_COLLECTION" not in inventory_source


@pytest.mark.parametrize(
    ("fixture", "reason"),
    [
        ("duplicate.json", "duplicate_cloud_run_job"),
        ("malformed_missing.json", "cloud_run_jobs_inventory_incomplete"),
        ("malformed_missing.json", "scheduler_jobs_inventory_missing"),
        ("target_mismatch.json", "scheduler_target_mismatch"),
        ("identity_mismatch.json", "resource_project_or_region_mismatch"),
    ],
)
def test_ambiguous_or_mismatched_evidence_fails_closed(fixture: str, reason: str) -> None:
    result = readiness.evaluate_snapshot(_fixture(fixture))

    assert result.status == "UNKNOWN"
    assert reason in result.reasons


@pytest.mark.parametrize(
    "argv",
    [
        "gcloud run jobs describe memory-maintenance-job",
        ["gcloud", "run", "jobs", "delete", "memory-maintenance-job"],
        ["gcloud", "scheduler", "jobs", "pause", "memory-maintenance-hourly"],
        ["gcloud", "run", "jobs", "describe", "memory-maintenance-job", "--quiet=true"],
        ["gcloud", "run", "jobs", "describe", "memory-maintenance-job;rm"],
    ],
)
def test_gcloud_allowlist_rejects_shell_strings_mutations_and_unapproved_flags(argv: object) -> None:
    with pytest.raises(ValueError):
        readiness.validate_read_only_gcloud_argv(argv)


@pytest.mark.parametrize(
    "argv",
    [
        [
            "gcloud",
            "run",
            "jobs",
            "describe",
            "memory-maintenance-job",
            "--project=sanitized-project",
            "--region=us-central1",
            "--format=json",
        ],
        [
            "gcloud",
            "run",
            "jobs",
            "executions",
            "list",
            "--job=memory-maintenance-job",
            "--project=sanitized-project",
            "--region=us-central1",
            "--format=json",
        ],
        [
            "gcloud",
            "scheduler",
            "jobs",
            "describe",
            "memory-maintenance-hourly",
            "--project=sanitized-project",
            "--location=us-central1",
            "--format=json",
        ],
        [
            "gcloud",
            "scheduler",
            "jobs",
            "list",
            "--project=sanitized-project",
            "--location=us-central1",
            "--format=json",
        ],
    ],
)
def test_gcloud_allowlist_accepts_only_read_only_inventory_commands(argv: list[str]) -> None:
    assert readiness.validate_read_only_gcloud_argv(argv) == tuple(argv)


def test_cli_output_is_content_free_and_limited_to_status_counts_reasons() -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--snapshot", str(FIXTURES / "active_running.json")],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(completed.stdout)

    assert set(payload) == {"status", "counts", "reasons"}
    assert "sanitized-project" not in completed.stdout
    assert "MEMORY_CANONICAL" not in completed.stdout
    assert "target_uri" not in completed.stdout


def test_cli_returns_unknown_without_echoing_invalid_snapshot(tmp_path: Path) -> None:
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text('{"private": "do-not-echo"}', encoding="utf-8")

    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--snapshot", str(snapshot)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 2
    assert "do-not-echo" not in completed.stdout
    assert json.loads(completed.stdout)["status"] == "UNKNOWN"
