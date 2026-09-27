import importlib.util
from pathlib import Path
import subprocess

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "provision_day3_reengagement_scheduler.py"
SPEC = importlib.util.spec_from_file_location("provision_day3_reengagement_scheduler", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
provision = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(provision)

PROJECT = "based-hardware"
REGION = "us-central1"
SERVICE_ACCOUNT = "memory-maintenance-scheduler@based-hardware.iam.gserviceaccount.com"


class _Runner:
    def __init__(self, describe_returncode: int):
        self.describe_returncode = describe_returncode
        self.calls: list[list[str]] = []

    def __call__(self, args, **kwargs):
        self.calls.append(list(args))
        returncode = self.describe_returncode if args[1:4] == ["scheduler", "jobs", "describe"] else 0
        return subprocess.CompletedProcess(args, returncode, "", "")


def _ensure(runner):
    return provision.ensure_scheduler(project=PROJECT, region=REGION, service_account=SERVICE_ACCOUNT, runner=runner)


@pytest.mark.parametrize("describe_returncode, action", [(0, "update"), (1, "create")])
def test_invoker_is_granted_before_the_trigger_is_written(describe_returncode, action):
    runner = _Runner(describe_returncode)

    assert _ensure(runner) == action

    binding = runner.calls[0]
    assert binding[:5] == ["gcloud", "run", "jobs", "add-iam-policy-binding", provision.EXPECTED_CLOUD_RUN_JOB]
    assert f"--member=serviceAccount:{SERVICE_ACCOUNT}" in binding
    assert "--role=roles/run.invoker" in binding
    assert f"--region={REGION}" in binding and f"--project={PROJECT}" in binding
    written = [call for call in runner.calls if call[1:4] == ["scheduler", "jobs", action]]
    assert len(written) == 1
    assert f"--oauth-service-account-email={SERVICE_ACCOUNT}" in written[0]


def test_binding_failure_stops_before_the_trigger_is_written():
    calls: list[list[str]] = []

    def runner(args, **kwargs):
        calls.append(list(args))
        if "add-iam-policy-binding" in args:
            raise subprocess.CalledProcessError(1, args)
        return subprocess.CompletedProcess(args, 0, "", "")

    with pytest.raises(subprocess.CalledProcessError):
        _ensure(runner)
    assert len(calls) == 1


def test_binding_refuses_a_foreign_job():
    with pytest.raises(ValueError):
        provision.invoker_binding_args(
            project=PROJECT, region=REGION, cloud_run_job="other-job", service_account=SERVICE_ACCOUNT
        )
