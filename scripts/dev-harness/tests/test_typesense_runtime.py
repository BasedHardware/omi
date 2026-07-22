from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dev_harness import config
from dev_harness import cli

REPO_ROOT = Path(__file__).resolve().parents[3]


def _cfg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> config.HarnessConfig:
    monkeypatch.setenv("OMI_LOCAL_STATE_ROOT", str(tmp_path / "state"))
    return config.load_config(REPO_ROOT)


def test_explicit_runtime_env_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OMI_TYPESENSE_RUNTIME", "native")
    assert cli.typesense_runtime() == "native"
    monkeypatch.setenv("OMI_TYPESENSE_RUNTIME", "docker")
    assert cli.typesense_runtime() == "docker"


def test_invalid_runtime_env_fails_loud(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OMI_TYPESENSE_RUNTIME", "podman")
    with pytest.raises(SystemExit):
        cli.typesense_runtime()


def test_auto_prefers_docker_when_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OMI_TYPESENSE_RUNTIME", raising=False)
    monkeypatch.delenv("OMI_TYPESENSE_SERVER_BIN", raising=False)
    monkeypatch.setattr(cli.shutil, "which", lambda name: "/usr/local/bin/docker" if name == "docker" else None)
    assert cli.typesense_runtime() == "docker"


def test_auto_falls_back_to_native_binary(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OMI_TYPESENSE_RUNTIME", raising=False)
    monkeypatch.delenv("OMI_TYPESENSE_SERVER_BIN", raising=False)
    monkeypatch.setattr(
        cli.shutil, "which", lambda name: "/opt/homebrew/bin/typesense-server" if name == "typesense-server" else None
    )
    assert cli.typesense_runtime() == "native"


def test_auto_without_either_keeps_docker_for_preflight_ownership(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OMI_TYPESENSE_RUNTIME", raising=False)
    monkeypatch.delenv("OMI_TYPESENSE_SERVER_BIN", raising=False)
    monkeypatch.setattr(cli.shutil, "which", lambda name: None)
    assert cli.typesense_runtime() == "docker"


def test_native_command_uses_binary_and_pinned_loopback_port(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    binary = tmp_path / "typesense-server"
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setenv("OMI_TYPESENSE_RUNTIME", "native")
    monkeypatch.setenv("OMI_TYPESENSE_SERVER_BIN", str(binary))
    cfg = _cfg(tmp_path, monkeypatch)

    command = cli._typesense_command(cfg)

    assert command[0] == str(binary)
    assert "--api-address" in command and "127.0.0.1" in command
    assert "--api-port" in command and str(config.TYPESENSE_PORT) in command
    assert config.LOCAL_TYPESENSE_API_KEY in command
    assert "docker" not in command


def test_native_override_missing_binary_fails_loud(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("OMI_TYPESENSE_RUNTIME", "native")
    monkeypatch.setenv("OMI_TYPESENSE_SERVER_BIN", str(tmp_path / "missing-binary"))
    cfg = _cfg(tmp_path, monkeypatch)

    with pytest.raises(SystemExit):
        cli._typesense_command(cfg)


def test_docker_command_keeps_pinned_image(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("OMI_TYPESENSE_RUNTIME", "docker")
    cfg = _cfg(tmp_path, monkeypatch)

    command = cli._typesense_command(cfg)

    assert command[0] == "docker"
    assert f"typesense/typesense:{config.TYPESENSE_PINNED_VERSION}" in command


def test_preflight_native_runtime_reports_missing_binary(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("PROVIDER_MODE", "offline")
    monkeypatch.setenv("OMI_TYPESENSE_RUNTIME", "native")
    monkeypatch.delenv("OMI_TYPESENSE_SERVER_BIN", raising=False)
    monkeypatch.setattr(cli.shutil, "which", lambda name: None)
    cfg = _cfg(tmp_path, monkeypatch)

    missing, _warnings = cli.prerequisite_report(cfg)

    assert any("typesense-server" in item for item in missing)
    assert not any(item.startswith("docker ") for item in missing)
