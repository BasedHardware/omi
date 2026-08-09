from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dev_harness import config, safety
from dev_harness import cli

REPO_ROOT = Path(__file__).resolve().parents[3]
DEV_HARNESS_ROOT = REPO_ROOT / "scripts" / "dev-harness"


def _prepend_dev_harness_pythonpath(env: dict[str, str]) -> None:
    entries = [str(DEV_HARNESS_ROOT)]
    if existing := env.get("PYTHONPATH"):
        entries.append(existing)
    env["PYTHONPATH"] = os.pathsep.join(entries)


def test_child_pythonpath_uses_the_selected_host_separator(tmp_path: Path) -> None:
    env = {"PYTHONPATH": str(tmp_path / "existing")}
    first = tmp_path / "scripts" / "dev-harness"
    second = tmp_path / "backend"

    cli._prepend_pythonpath(env, first, second)

    assert env["PYTHONPATH"].split(os.pathsep) == [str(first), str(second), str(tmp_path / "existing")]


def test_offline_check_skips_provider_credentials(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("DEEPGRAM_API_KEY", raising=False)
    monkeypatch.setenv("PROVIDER_MODE", "offline")
    monkeypatch.setenv("OMI_LOCAL_STATE_ROOT", str(tmp_path / "state"))
    cfg = config.load_config(REPO_ROOT)

    missing, warnings = cli.prerequisite_report(cfg)

    assert not any("OPENAI_API_KEY" in item or "DEEPGRAM_API_KEY" in item for item in missing)
    assert any("offline" in item for item in warnings)


def test_real_check_lists_provider_credentials(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "AGENTS.md").write_text("agents", encoding="utf-8")
    (repo / ".git").mkdir()
    (repo / "backend").mkdir()
    for key in ("OPENAI_API_KEY", "DEEPGRAM_API_KEY", "GEMINI_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("PROVIDER_MODE", "real")
    monkeypatch.setenv("OMI_LOCAL_STATE_ROOT", str(tmp_path / "state"))
    cfg = config.load_config(repo)

    missing, _warnings = cli.prerequisite_report(cfg)

    assert any("OPENAI_API_KEY" in item for item in missing)
    assert any("DEEPGRAM_API_KEY" in item for item in missing)


def test_firebase_command_writes_the_configured_emulator_ports(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("OMI_LOCAL_STATE_ROOT", str(tmp_path / "state"))
    monkeypatch.setenv("OMI_HARNESS_PORT_OFFSET", "321")
    cfg = config.load_config(REPO_ROOT, create_layout=True)
    command = cli._firebase_command(cfg)
    config_path = Path(command[command.index("--config") + 1])
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    assert payload["emulators"]["firestore"]["port"] == 8406
    assert payload["emulators"]["auth"]["port"] == 9420


def test_wait_health_returns_services_that_exhaust_their_deadlines(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("PROVIDER_MODE", "offline")
    monkeypatch.setenv("OMI_LOCAL_STATE_ROOT", str(tmp_path / "state"))
    cfg = config.load_config(REPO_ROOT)
    ticks = iter((0.0, 181.0))
    monkeypatch.setattr(cli.time, "time", lambda: next(ticks))
    monkeypatch.setattr(cli, "_process_records", lambda _cfg: [])

    failures = cli._wait_health(cfg)

    assert failures == [
        "firestore: not healthy after 45s at http://127.0.0.1:8085/",
        "auth: not healthy after 90s at http://127.0.0.1:9099/",
        "typesense: not healthy after 45s at http://127.0.0.1:8108/collections",
        "backend: not healthy after 180s at http://127.0.0.1:8000/docs",
        "desktop-backend: not healthy after 60s at http://127.0.0.1:10201/health",
        "redis: not healthy after 30s at 127.0.0.1:6380",
    ]


def test_wait_health_discards_transient_failure_after_recovery(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("PROVIDER_MODE", "offline")
    monkeypatch.setenv("OMI_LOCAL_STATE_ROOT", str(tmp_path / "state"))
    cfg = config.load_config(REPO_ROOT)
    ticks = iter((0.0, 1.0, 2.0))
    monkeypatch.setattr(cli.time, "time", lambda: next(ticks))
    monkeypatch.setattr(cli.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(cli, "_process_records", lambda _cfg: [])
    monkeypatch.setattr(cli, "_port_open", lambda _host, _port: True)
    outcomes = iter([(False, "connection refused")] * 5 + [(True, "ok")] * 5)
    monkeypatch.setattr(cli, "_http_ok", lambda _url, headers=None: next(outcomes))

    assert cli._wait_health(cfg) == []


def test_reset_command_is_idempotent_with_temp_state(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["PROVIDER_MODE"] = "offline"
    env["OMI_LOCAL_STATE_ROOT"] = str(tmp_path / "state")
    _prepend_dev_harness_pythonpath(env)

    for _ in range(2):
        result = subprocess.run(
            [sys.executable, "-m", "dev_harness.cli", "reset"],
            cwd=REPO_ROOT,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=30,
        )
        assert result.returncode == 0, result.stdout
        assert "Reset complete" in result.stdout

    layout = safety.layout_for_instance(REPO_ROOT, "default", env)
    assert layout.sentinel_path.is_file()
    safety.read_and_validate_sentinel(layout.state_root, repo_root=REPO_ROOT, instance="default")


def test_status_reports_seeded_scenario_and_summary_path(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["PROVIDER_MODE"] = "offline"
    env["OMI_LOCAL_STATE_ROOT"] = str(tmp_path / "state")
    _prepend_dev_harness_pythonpath(env)

    seed = subprocess.run(
        [sys.executable, "scripts/dev-harness/seed-memory-scenario.py", "happy_path", "--dry-run"],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=30,
    )
    assert seed.returncode == 0, seed.stdout

    result = subprocess.run(
        [sys.executable, "-m", "dev_harness.cli", "status"],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout
    assert "scenario_id: happy_path" in result.stdout
    assert "seeded_users: alice, bob, local_default_user" in result.stdout
    assert "session_summary_path:" in result.stdout
    assert "PROVIDER_MODE=offline active" in result.stdout


def test_session_summary_is_local_emulator_non_activation(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["PROVIDER_MODE"] = "offline"
    env["OMI_LOCAL_STATE_ROOT"] = str(tmp_path / "state")
    _prepend_dev_harness_pythonpath(env)

    seed = subprocess.run(
        [sys.executable, "scripts/dev-harness/seed-memory-scenario.py", "happy_path", "--dry-run"],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=30,
    )
    assert seed.returncode == 0, seed.stdout
    summary = subprocess.run(
        [sys.executable, "-m", "dev_harness.cli", "summary"],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=30,
    )
    assert summary.returncode == 0, summary.stdout
    path = Path(summary.stdout.strip())
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["evidence_class"] == "LOCAL_EMULATOR_DEV"
    assert payload["activation_eligible"] is False
    assert payload["provider_mode"] == "offline"
    assert payload["memory_write_attempt_instrumentation"]["instrumented"] is False
    assert "before_digest" in payload["protected_state_digest"]
    assert any("Not DEV_CLOUD_PROOF" in item for item in payload["non_claims"])
