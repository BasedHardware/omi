import importlib.util
from pathlib import Path
from typing import Any

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "validate_x_connector_sync_scheduler.py"
SPEC = importlib.util.spec_from_file_location("validate_x_connector_sync_scheduler", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
scheduler_validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(scheduler_validator)

ROOT = Path(__file__).resolve().parents[3]
PROJECT = "based-hardware-dev"
REGION = "us-central1"
SCHEDULER_JOB = "x-connector-sync-6h"
CLOUD_RUN_JOB = "x-connector-sync-job"
EXPECTED_RESOURCE_NAME = f"projects/{PROJECT}/locations/{REGION}/jobs/{SCHEDULER_JOB}"
EXPECTED_TARGET_URI = (
    f"https://run.googleapis.com/v2/projects/{PROJECT}"
    f"/locations/{REGION}/jobs/{CLOUD_RUN_JOB}:run"
)
EXPECTED_SCHEDULER_SA = f"x-connector-sync-scheduler@{PROJECT}.iam.gserviceaccount.com"


def _contract():
    return scheduler_validator.SchedulerContract(
        project=PROJECT,
        region=REGION,
        scheduler_job=SCHEDULER_JOB,
        cloud_run_job=CLOUD_RUN_JOB,
    )


def _valid_state() -> dict[str, Any]:
    return {
        "name": EXPECTED_RESOURCE_NAME,
        "schedule": "0 */6 * * *",
        "state": "ENABLED",
        "timeZone": "Etc/UTC",
        "httpTarget": {
            "httpMethod": "POST",
            "oauthToken": {"serviceAccountEmail": EXPECTED_SCHEDULER_SA},
            "uri": EXPECTED_TARGET_URI,
        },
    }


def test_validate_scheduler_state_accepts_exact_6h_contract():
    assert scheduler_validator.validate_scheduler_state(_valid_state(), _contract()) == []
    assert _contract().resource_name == EXPECTED_RESOURCE_NAME
    assert _contract().target_uri == EXPECTED_TARGET_URI
    assert _contract().scheduler_service_account == EXPECTED_SCHEDULER_SA


@pytest.mark.parametrize(
    ("path", "wrong_value", "expected_error"),
    [
        (("name",), "projects/wrong/locations/us-central1/jobs/x-connector-sync-6h", "name must equal"),
        (("state",), "PAUSED", "state must equal"),
        (("schedule",), "0 * * * *", "schedule must equal"),
        (("timeZone",), "America/New_York", "timeZone must equal"),
        (("httpTarget", "httpMethod"), "GET", "httpTarget.httpMethod must equal"),
        (("httpTarget", "uri"), "https://example.invalid/run", "httpTarget.uri must equal"),
        (
            ("httpTarget", "oauthToken", "serviceAccountEmail"),
            "wrong-scheduler@based-hardware-dev.iam.gserviceaccount.com",
            "httpTarget.oauthToken.serviceAccountEmail must equal",
        ),
        (
            ("httpTarget", "oauthToken", "serviceAccountEmail"),
            " ",
            "httpTarget.oauthToken.serviceAccountEmail must equal",
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


def _main_argv(state_file: Path) -> list[str]:
    return [
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


def test_main_rejects_invalid_json_without_cloud_calls(tmp_path):
    state_file = tmp_path / "scheduler.json"
    state_file.write_text("not-json", encoding="utf-8")

    assert scheduler_validator.main(_main_argv(state_file)) == 2


def test_main_rejects_non_utf8_state_file(tmp_path):
    state_file = tmp_path / "scheduler.json"
    state_file.write_bytes(b"\xff\xfe invalid")

    assert scheduler_validator.main(_main_argv(state_file)) == 2


def test_main_fails_on_contract_drift(tmp_path):
    state_file = tmp_path / "scheduler.json"
    state = _valid_state()
    state["schedule"] = "0 * * * *"
    state_file.write_text(__import__("json").dumps(state), encoding="utf-8")

    assert scheduler_validator.main(_main_argv(state_file)) == 1


def test_main_passes_exact_contract(tmp_path):
    state_file = tmp_path / "scheduler.json"
    state_file.write_text(__import__("json").dumps(_valid_state()), encoding="utf-8")

    assert scheduler_validator.main(_main_argv(state_file)) == 0


def test_deploy_workflow_gates_success_on_read_only_scheduler_validation():
    workflow = (ROOT / ".github" / "workflows" / "gcp_x_connector_sync_job.yml").read_text(encoding="utf-8")

    assert "gcloud scheduler jobs describe" in workflow
    assert "x-connector-sync-6h" in workflow
    assert "validate_x_connector_sync_scheduler.py" in workflow
    assert "--state-file" in workflow
    assert "--project" in workflow
    assert "--region" in workflow
    assert "--scheduler-job" in workflow
    assert "--cloud-run-job" in workflow
    assert workflow.index("uses: google-github-actions/deploy-cloudrun@v3") < workflow.index(
        "validate_x_connector_sync_scheduler.py"
    )
    assert "scheduler jobs create" not in workflow
    assert "scheduler jobs update" not in workflow
    assert "scheduler jobs resume" not in workflow
    assert "verify-llm-gateway-serving" not in workflow
    assert "probe-llm-gateway-from-cloud-run" not in workflow
