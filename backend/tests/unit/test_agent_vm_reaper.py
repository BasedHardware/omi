"""Contract tests for agent VM reaper selection + apply refuse gate."""

from __future__ import annotations

import importlib.util
import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "backend" / "scripts" / "agent_vm_reaper.py"
APPLY = ROOT / "backend" / "scripts" / "apply-agent-vm-reaper.sh"
MANIFEST = ROOT / "backend" / "charts" / "agent-vm-reaper" / "prod_agent_vm_reaper_cronjob.yaml"

NOW = datetime(2026, 7, 23, 6, 0, tzinfo=timezone.utc)


@pytest.fixture()
def reaper():
    """Load the reaper script as a module without polluting sys.modules."""
    spec = importlib.util.spec_from_file_location("agent_vm_reaper", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _inst(name: str, status: str, *, created_hours_ago: float, stopped_hours_ago: float | None = None):
    created = (NOW - timedelta(hours=created_hours_ago)).isoformat()
    out = {
        "name": name,
        "zone": "https://www.googleapis.com/compute/v1/projects/based-hardware/zones/us-central1-a",
        "status": status,
        "creationTimestamp": created,
    }
    if stopped_hours_ago is not None:
        out["lastStopTimestamp"] = (NOW - timedelta(hours=stopped_hours_ago)).isoformat()
    return out


def test_selects_terminated_past_grace_only(reaper):
    instances = [
        _inst("omi-agent-fresh", "TERMINATED", created_hours_ago=20, stopped_hours_ago=1),
        _inst("omi-agent-aged", "TERMINATED", created_hours_ago=40, stopped_hours_ago=13),
        _inst("other-vm", "TERMINATED", created_hours_ago=40, stopped_hours_ago=13),
    ]
    selected = reaper.select_reapable(instances, now=NOW, terminated_min_age_hours=12)
    assert [i["name"] for i in selected] == ["omi-agent-aged"]


def test_running_vms_are_never_reaped(reaper):
    """RUNNING VMs must not be reaped regardless of age — agent-proxy keepalive
    means the reaper has no safe signal to delete active sessions."""
    instances = [
        _inst("omi-agent-young", "RUNNING", created_hours_ago=12),
        _inst("omi-agent-old", "RUNNING", created_hours_ago=49),
    ]
    selected = reaper.select_reapable(instances, now=NOW, terminated_min_age_hours=12)
    assert selected == []


def test_cli_dry_run_default_does_not_delete(tmp_path, monkeypatch, reaper):
    import json

    fixture = tmp_path / "instances.json"
    fixture.write_text(
        json.dumps([_inst("omi-agent-aged", "TERMINATED", created_hours_ago=40, stopped_hours_ago=13)]),
        encoding="utf-8",
    )

    deleted = []

    def _boom(*_a, **_k):
        deleted.append(True)
        raise AssertionError("delete must not run in dry-run")

    monkeypatch.setattr(reaper, "delete_instance", _boom)
    monkeypatch.delenv("AGENT_VM_REAPER_LIVE", raising=False)
    rc = reaper.main(
        [
            "--instances-json",
            str(fixture),
            "--dry-run",
            "--terminated-min-age-hours",
            "12",
        ]
    )
    assert rc == 0
    assert deleted == []


def test_cli_refuses_live_without_env_gate(tmp_path, monkeypatch, reaper):
    import json

    fixture = tmp_path / "instances.json"
    fixture.write_text(
        json.dumps([_inst("omi-agent-aged", "TERMINATED", created_hours_ago=40, stopped_hours_ago=13)]),
        encoding="utf-8",
    )
    monkeypatch.delenv("AGENT_VM_REAPER_LIVE", raising=False)
    monkeypatch.delenv("KUBERNETES_SERVICE_HOST", raising=False)
    rc = reaper.main(
        [
            "--instances-json",
            str(fixture),
            "--no-dry-run",
            "--live",
            "--terminated-min-age-hours",
            "12",
        ]
    )
    assert rc == 2


def test_cli_refuses_live_without_live_flag_outside_cluster(tmp_path, monkeypatch, reaper):
    import json

    fixture = tmp_path / "instances.json"
    fixture.write_text(
        json.dumps([_inst("omi-agent-aged", "TERMINATED", created_hours_ago=40, stopped_hours_ago=13)]),
        encoding="utf-8",
    )
    monkeypatch.setenv("AGENT_VM_REAPER_LIVE", "1")
    monkeypatch.delenv("KUBERNETES_SERVICE_HOST", raising=False)
    rc = reaper.main(
        [
            "--instances-json",
            str(fixture),
            "--no-dry-run",
            "--terminated-min-age-hours",
            "12",
        ]
    )
    assert rc == 2


def test_cli_live_deletes_when_gated(tmp_path, monkeypatch, reaper):
    import json

    fixture = tmp_path / "instances.json"
    fixture.write_text(
        json.dumps([_inst("omi-agent-aged", "TERMINATED", created_hours_ago=40, stopped_hours_ago=13)]),
        encoding="utf-8",
    )
    calls = []

    def _fake_delete(project, name, zone):
        calls.append((project, name, zone))

    monkeypatch.setattr(reaper, "delete_instance", _fake_delete)
    monkeypatch.setenv("AGENT_VM_REAPER_LIVE", "1")
    monkeypatch.delenv("KUBERNETES_SERVICE_HOST", raising=False)
    rc = reaper.main(
        [
            "--instances-json",
            str(fixture),
            "--no-dry-run",
            "--live",
            "--project",
            "based-hardware",
            "--terminated-min-age-hours",
            "12",
        ]
    )
    assert rc == 0
    assert calls == [("based-hardware", "omi-agent-aged", "us-central1-a")]


def test_cli_returns_failure_when_live_delete_fails(tmp_path, monkeypatch, reaper):
    """Live deletes that hit GCE/IAM errors must exit non-zero so the
    CronJob's restartPolicy: OnFailure retries (review: #10390)."""
    import json

    fixture = tmp_path / "instances.json"
    fixture.write_text(
        json.dumps([_inst("omi-agent-fail", "TERMINATED", created_hours_ago=40, stopped_hours_ago=13)]),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        reaper,
        "delete_instance",
        lambda *_a, **_k: (_ for _ in ()).throw(subprocess.CalledProcessError(1, ["gcloud"])),
    )
    monkeypatch.setenv("AGENT_VM_REAPER_LIVE", "1")
    monkeypatch.delenv("KUBERNETES_SERVICE_HOST", raising=False)
    rc = reaper.main(
        [
            "--instances-json",
            str(fixture),
            "--no-dry-run",
            "--live",
            "--terminated-min-age-hours",
            "12",
        ]
    )
    assert rc == 1


def test_in_cluster_live_deletes_without_live_flag(tmp_path, monkeypatch, reaper):
    import json

    fixture = tmp_path / "instances.json"
    fixture.write_text(
        json.dumps([_inst("omi-agent-aged", "TERMINATED", created_hours_ago=40, stopped_hours_ago=13)]),
        encoding="utf-8",
    )
    calls = []
    monkeypatch.setattr(reaper, "delete_instance", lambda p, n, z: calls.append((p, n, z)))
    monkeypatch.setenv("AGENT_VM_REAPER_LIVE", "1")
    monkeypatch.setenv("KUBERNETES_SERVICE_HOST", "10.0.0.1")
    rc = reaper.main(
        [
            "--instances-json",
            str(fixture),
            "--no-dry-run",
            "--project",
            "based-hardware",
            "--terminated-min-age-hours",
            "12",
        ]
    )
    assert rc == 0
    assert calls == [("based-hardware", "omi-agent-aged", "us-central1-a")]


def test_apply_script_refuses_without_gate():
    env = os.environ.copy()
    env.pop("AGENT_VM_REAPER_APPLY", None)
    proc = subprocess.run(
        ["bash", str(APPLY)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1
    assert "REFUSED" in proc.stderr


def test_cronjob_manifest_defaults_are_safe():
    docs = list(yaml.safe_load_all(MANIFEST.read_text(encoding="utf-8")))
    cron = next(d for d in docs if d and d.get("kind") == "CronJob")
    container = cron["spec"]["jobTemplate"]["spec"]["template"]["spec"]["containers"][0]
    env = {item["name"]: item["value"] for item in container["env"]}
    assert env["DRY_RUN"] == "true"
    assert env["REAP_TERMINATED_MIN_AGE_HOURS"] == "12"
    assert "REAP_RUNNING_AGE_DAYS" not in env
    assert container["command"] == ["python3"]
    assert container["args"] == ["/scripts/agent_vm_reaper.py"]
    volumes = cron["spec"]["jobTemplate"]["spec"]["template"]["spec"]["volumes"]
    assert volumes[0]["configMap"]["name"] == "prod-agent-vm-reaper-script"
