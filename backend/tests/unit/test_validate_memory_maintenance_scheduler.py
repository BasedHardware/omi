import importlib.util
from pathlib import Path
from typing import Any

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "validate_memory_maintenance_scheduler.py"
SPEC = importlib.util.spec_from_file_location("validate_memory_maintenance_scheduler", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
scheduler_validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(scheduler_validator)

ROOT = Path(__file__).resolve().parents[3]
PROJECT = "based-hardware-dev"
REGION = "us-central1"
SCHEDULER_JOB = "memory-maintenance-hourly"
CLOUD_RUN_JOB = "memory-maintenance-job"


def _contract():
    return scheduler_validator.SchedulerContract(
        project=PROJECT,
        region=REGION,
        scheduler_job=SCHEDULER_JOB,
        cloud_run_job=CLOUD_RUN_JOB,
    )


def _valid_state() -> dict[str, Any]:
    contract = _contract()
    return {
        "name": contract.resource_name,
        "schedule": "0 * * * *",
        "state": "ENABLED",
        "timeZone": "Etc/UTC",
        "httpTarget": {
            "httpMethod": "POST",
            "oauthToken": {
                "serviceAccountEmail": "memory-maintenance-scheduler@based-hardware-dev.iam.gserviceaccount.com"
            },
            "uri": contract.target_uri,
        },
    }


def test_validate_scheduler_state_accepts_exact_hourly_contract():
    assert scheduler_validator.validate_scheduler_state(_valid_state(), _contract()) == []


@pytest.mark.parametrize(
    ("path", "wrong_value", "expected_error"),
    [
        (("name",), "projects/wrong/locations/us-central1/jobs/memory-maintenance-hourly", "name must equal"),
        (("state",), "PAUSED", "state must equal"),
        (("schedule",), "*/30 * * * *", "schedule must equal"),
        (("timeZone",), "America/New_York", "timeZone must equal"),
        (("httpTarget", "httpMethod"), "GET", "httpTarget.httpMethod must equal"),
        (("httpTarget", "uri"), "https://example.invalid/run", "httpTarget.uri must equal"),
        (
            ("httpTarget", "oauthToken", "serviceAccountEmail"),
            " ",
            "httpTarget.oauthToken.serviceAccountEmail must be a nonempty string",
        ),
    ],
)
def test_validate_scheduler_state_rejects_contract_drift(path, wrong_value, expected_error):
    state = _valid_state()
    target = state
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = wrong_value

    errors = scheduler_validator.validate_scheduler_state(state, _contract())

    assert any(expected_error in error for error in errors)


EXPECTED_SA = "memory-maintenance-scheduler@based-hardware-dev.iam.gserviceaccount.com"


def test_validate_scheduler_state_rejects_a_wrong_but_nonempty_service_account():
    """A nonempty-only check let any other principal pass the deploy gate."""
    contract = _contract()._replace(scheduler_service_account=EXPECTED_SA)
    state = _valid_state()
    state["httpTarget"]["oauthToken"]["serviceAccountEmail"] = "attacker@based-hardware-dev.iam.gserviceaccount.com"

    errors = scheduler_validator.validate_scheduler_state(state, contract)

    assert len(errors) == 1
    assert "serviceAccountEmail must equal" in errors[0]
    assert EXPECTED_SA in errors[0]


def test_validate_scheduler_state_accepts_the_expected_service_account():
    contract = _contract()._replace(scheduler_service_account=EXPECTED_SA)

    assert scheduler_validator.validate_scheduler_state(_valid_state(), contract) == []


def test_validate_scheduler_state_keeps_the_nonempty_floor_when_no_account_is_pinned():
    """Callers that cannot name their account keep today's weaker check, not none."""
    contract = _contract()
    assert contract.scheduler_service_account is None

    state = _valid_state()
    state["httpTarget"]["oauthToken"]["serviceAccountEmail"] = "anything@example.com"
    assert scheduler_validator.validate_scheduler_state(state, contract) == []

    state["httpTarget"]["oauthToken"]["serviceAccountEmail"] = "   "
    assert scheduler_validator.validate_scheduler_state(state, contract) == [
        "httpTarget.oauthToken.serviceAccountEmail must be a nonempty string"
    ]


def test_main_pins_the_service_account_from_the_cli(tmp_path):
    import json

    state_file = tmp_path / "state.json"
    state = _valid_state()
    state["httpTarget"]["oauthToken"]["serviceAccountEmail"] = "wrong@based-hardware-dev.iam.gserviceaccount.com"
    state_file.write_text(json.dumps(state), encoding="utf-8")
    argv = [
        "--state-file",
        str(state_file),
        "--project",
        PROJECT,
        "--region",
        REGION,
        "--scheduler-job",
        SCHEDULER_JOB,
        "--cloud-run-job",
        CLOUD_RUN_JOB,
    ]

    # Without the flag the wrong account still passes, which is the hole being closed.
    assert scheduler_validator.main(argv) == 0
    assert scheduler_validator.main(argv + ["--scheduler-service-account", EXPECTED_SA]) == 1


def test_main_reports_a_non_utf8_state_file_as_exit_2(tmp_path):
    """UnicodeDecodeError used to escape as a traceback instead of the documented code."""
    state_file = tmp_path / "state.json"
    state_file.write_bytes(b'{"name": "\xff\xfe not utf-8"}')

    assert (
        scheduler_validator.main(
            [
                "--state-file",
                str(state_file),
                "--project",
                PROJECT,
                "--region",
                REGION,
                "--scheduler-job",
                SCHEDULER_JOB,
                "--cloud-run-job",
                CLOUD_RUN_JOB,
            ]
        )
        == 2
    )


def test_main_rejects_invalid_json_without_cloud_calls(tmp_path):
    state_file = tmp_path / "scheduler.json"
    state_file.write_text("not-json", encoding="utf-8")

    exit_code = scheduler_validator.main(
        [
            "--state-file",
            str(state_file),
            "--project",
            PROJECT,
            "--region",
            REGION,
            "--scheduler-job",
            SCHEDULER_JOB,
            "--cloud-run-job",
            CLOUD_RUN_JOB,
        ]
    )

    assert exit_code == 2


@pytest.mark.parametrize(
    "workflow_name",
    [
        "gcp_memory_maintenance_job.yml",
        "gcp_memory_maintenance_job_auto_dev.yml",
    ],
)
def test_deploy_workflows_gate_success_on_read_only_scheduler_validation(workflow_name):
    workflow = (ROOT / ".github" / "workflows" / workflow_name).read_text(encoding="utf-8")

    assert "gcloud scheduler jobs describe" in workflow
    assert "memory-maintenance-hourly" in workflow
    assert "validate_memory_maintenance_scheduler.py" in workflow
    assert "--state-file" in workflow
    assert "--project" in workflow
    assert "--region" in workflow
    assert "--scheduler-job" in workflow
    assert "--cloud-run-job" in workflow
    assert workflow.index("uses: google-github-actions/deploy-cloudrun@v3") < workflow.index(
        "validate_memory_maintenance_scheduler.py"
    )
    assert "scheduler jobs create" not in workflow
    assert "scheduler jobs update" not in workflow
    assert "scheduler jobs resume" not in workflow


def test_frame_retention_workflow_resumes_only_a_verified_paused_scheduler():
    # omi-test-quality: source-inspection -- static workflow recovery contract
    workflow = (ROOT / ".github" / "workflows" / "gcp_frame_request_retention_job.yml").read_text(encoding="utf-8")

    state_read = "scheduler_state=$(gcloud scheduler jobs describe"
    paused_guard = 'if [[ "$scheduler_state" == "PAUSED" ]]; then'
    resume = 'gcloud scheduler jobs resume "$SCHEDULER_JOB"'
    unexpected_guard = 'elif [[ "$scheduler_state" != "ENABLED" ]]; then'
    validation = "validate_memory_maintenance_scheduler.py"
    assert state_read in workflow
    assert paused_guard in workflow
    assert resume in workflow
    assert unexpected_guard in workflow
    assert workflow.index(state_read) < workflow.index(paused_guard) < workflow.index(resume)
    assert workflow.index(resume) < workflow.index(validation)
