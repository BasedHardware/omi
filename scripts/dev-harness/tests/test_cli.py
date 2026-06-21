from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dev_harness import config, safety
from dev_harness import cli

REPO_ROOT = Path(__file__).resolve().parents[3]


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
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("DEEPGRAM_API_KEY", raising=False)
    monkeypatch.setenv("PROVIDER_MODE", "real")
    monkeypatch.setenv("OMI_LOCAL_STATE_ROOT", str(tmp_path / "state"))
    cfg = config.load_config(REPO_ROOT)

    missing, _warnings = cli.prerequisite_report(cfg)

    assert any("OPENAI_API_KEY" in item for item in missing)
    assert any("DEEPGRAM_API_KEY" in item for item in missing)


def test_reset_command_is_idempotent_with_temp_state(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["PROVIDER_MODE"] = "offline"
    env["OMI_LOCAL_STATE_ROOT"] = str(tmp_path / "state")
    env["PYTHONPATH"] = f"{REPO_ROOT / 'scripts' / 'dev-harness'}:{env.get('PYTHONPATH', '')}"

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
