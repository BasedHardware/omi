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


def _health_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> config.HarnessConfig:
    monkeypatch.setenv("PROVIDER_MODE", "offline")
    monkeypatch.setenv("OMI_LOCAL_STATE_ROOT", str(tmp_path / "state"))
    monkeypatch.setattr(cli, "_process_records", lambda _cfg: [])
    monkeypatch.setattr(cli, "_port_open", lambda *_args, **_kwargs: True)
    return config.load_config(REPO_ROOT, create_layout=True)


def test_wait_health_reports_a_service_that_never_becomes_healthy(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cfg = _health_config(monkeypatch, tmp_path)
    monkeypatch.setattr(
        cli,
        "_http_ok",
        lambda url, headers=None: (False, "connection refused") if "/docs" in url else (True, "HTTP 200"),
    )
    monkeypatch.setattr(cli, "_HEALTH_TIMEOUTS", {**cli._HEALTH_TIMEOUTS, "backend": 0.4})

    failures = cli._wait_health(cfg)

    assert len(failures) == 1, failures
    assert failures[0].startswith("backend: not healthy after")
    assert "connection refused" in failures[0]


def test_wait_health_ignores_a_service_that_recovers_before_its_deadline(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cfg = _health_config(monkeypatch, tmp_path)
    attempts = {"backend": 0}

    def fake_http_ok(url: str, headers: dict[str, str] | None = None) -> tuple[bool, str]:
        if "/docs" in url:
            attempts["backend"] += 1
            if attempts["backend"] < 3:
                return False, "connection refused"
        return True, "HTTP 200"

    monkeypatch.setattr(cli, "_http_ok", fake_http_ok)

    assert cli._wait_health(cfg) == []
    assert attempts["backend"] == 3


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
