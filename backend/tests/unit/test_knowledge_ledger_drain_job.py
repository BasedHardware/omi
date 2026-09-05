from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from utils.memory import knowledge_ledger_drain as ledger_drain


def _load_job():
    path = Path(__file__).resolve().parents[2] / "modal" / "knowledge_ledger_drain_job.py"
    spec = importlib.util.spec_from_file_location("_knowledge_ledger_drain_job_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Executing the job module pulls the whole drain dependency graph (firebase_admin and
# utils.memory.*), which costs ~1.5s of CPU on a cold interpreter and starts gRPC's
# background threads. Loading it at import time keeps that out of every phase the
# fast-unit duration guard measures; as a module-scoped fixture the cost was charged to
# whichever test happened to request it first.
JOB = _load_job()


def test_entrypoint_executes_independent_drain(monkeypatch):
    job = JOB
    called = []

    async def run(**kwargs):
        assert kwargs["uid_allowlist"] == {"uid-owner"}
        called.append(True)
        return SimpleNamespace(errors=[])

    monkeypatch.setenv(ledger_drain.LEDGER_DRAIN_ENABLED_ENV, "true")
    monkeypatch.setenv(ledger_drain.LEDGER_DRAIN_UID_ALLOWLIST_ENV, "uid-owner")
    monkeypatch.setattr(job, "_init_firebase", lambda: None)
    monkeypatch.setattr(job, "run_knowledge_ledger_drain", run)

    job.main()

    assert called == [True]


def test_entrypoint_fails_when_a_page_reports_errors(monkeypatch):
    job = JOB

    async def run(**_kwargs):
        return SimpleNamespace(errors=["uid=redacted:migration:RuntimeError"])

    monkeypatch.setenv(ledger_drain.LEDGER_DRAIN_ENABLED_ENV, "true")
    monkeypatch.setenv(ledger_drain.LEDGER_DRAIN_UID_ALLOWLIST_ENV, "uid-owner")
    monkeypatch.setattr(job, "_init_firebase", lambda: None)
    monkeypatch.setattr(job, "run_knowledge_ledger_drain", run)

    with pytest.raises(RuntimeError, match=r"completed with 1 error\(s\)"):
        job.main()


def test_entrypoint_default_off_skips_firebase_and_inventory(monkeypatch):
    job = JOB
    called = []

    monkeypatch.delenv(ledger_drain.LEDGER_DRAIN_ENABLED_ENV, raising=False)
    monkeypatch.setattr(job, "_init_firebase", lambda: called.append("firebase"))
    monkeypatch.setattr(job, "run_knowledge_ledger_drain", lambda **_kwargs: called.append("drain"))

    job.main()

    assert called == []


def test_adc_firebase_initialization_pins_auth_audience(monkeypatch):
    observed = {}
    monkeypatch.delenv("SERVICE_ACCOUNT_JSON", raising=False)
    monkeypatch.setattr(JOB, "firebase_admin_options", lambda: {"projectId": "based-hardware"})
    monkeypatch.setattr(JOB.firebase_admin, "initialize_app", lambda **kwargs: observed.update(kwargs))

    JOB._init_firebase()

    assert observed == {"options": {"projectId": "based-hardware"}}


def test_entrypoint_enabled_without_allowlist_fails_before_firebase(monkeypatch):
    job = JOB
    called = []

    monkeypatch.setenv(ledger_drain.LEDGER_DRAIN_ENABLED_ENV, "true")
    monkeypatch.delenv(ledger_drain.LEDGER_DRAIN_UID_ALLOWLIST_ENV, raising=False)
    monkeypatch.setattr(job, "_init_firebase", lambda: called.append("firebase"))

    with pytest.raises(RuntimeError, match="requires an explicit UID allowlist"):
        job.main()

    assert called == []


@pytest.mark.parametrize(
    "workflow_name",
    ["gcp_daily_memory_sweep_job.yml", "gcp_daily_memory_sweep_job_auto_dev.yml"],
)
def test_admitted_deploy_lane_provisions_an_independent_job_and_scheduler(workflow_name):
    root = Path(__file__).resolve().parents[3]
    workflow = (root / ".github" / "workflows" / workflow_name).read_text(encoding="utf-8")

    assert "Dockerfile.knowledge_ledger_drain_job" in workflow
    assert "job: ${{ env.LEDGER_DRAIN_SERVICE }}" in workflow
    assert "knowledge_ledger_drain_job_env_vars" in workflow
    assert "knowledge-ledger-drain-hourly" in workflow
    assert '--cloud-run-job "$LEDGER_DRAIN_SERVICE"' in workflow
    assert 'gcloud run jobs add-iam-policy-binding "$LEDGER_DRAIN_SERVICE"' in workflow
    assert '--member="serviceAccount:${SCHEDULER_SERVICE_ACCOUNT}"' in workflow
    assert '--role="roles/run.invoker"' in workflow
    assert workflow.index("Deploy independent ledger drain to Cloud Run") < workflow.index(
        "Authorize ledger drain Scheduler invocations"
    )
    assert workflow.index("Authorize ledger drain Scheduler invocations") < workflow.index(
        "Provision hourly Scheduler trigger from admitted source"
    )


def test_runtime_manifest_keeps_the_drain_bounded_and_authorized():
    root = Path(__file__).resolve().parents[3]
    manifest = yaml.safe_load((root / "backend" / "deploy" / "runtime_env.yaml").read_text(encoding="utf-8"))

    for environment in ("dev", "prod"):
        job = manifest["environments"][environment]["cloud_run"]["jobs"]["knowledge-ledger-drain-job"]
        assert job["flags"]["--task-timeout"] == "1200s"
        assert job["flags"]["--max-retries"] == "1"
        assert job["env"]["MEMORY_ENABLED"]["value"] == "on"
        assert set(job["secrets"]) == {
            "ENCRYPTION_SECRET",
            "POSTHOG_PROJECT_API_KEY",
            "SERVICE_ACCOUNT_JSON",
        }

    dev_env = manifest["environments"]["dev"]["cloud_run"]["jobs"]["knowledge-ledger-drain-job"]["env"]
    assert dev_env["KNOWLEDGE_LEDGER_DRAIN_ENABLED"]["value"] == "false"
    assert dev_env["KNOWLEDGE_LEDGER_DRAIN_UID_ALLOWLIST"]["value"] == ("9OqYLlKJv4hmeYpIhwJcHBR975i2")
    prod_env = manifest["environments"]["prod"]["cloud_run"]["jobs"]["knowledge-ledger-drain-job"]["env"]
    assert prod_env["KNOWLEDGE_LEDGER_DRAIN_ENABLED"]["value"] == "false"
    assert prod_env["KNOWLEDGE_LEDGER_DRAIN_UID_ALLOWLIST"]["value"] == ""
