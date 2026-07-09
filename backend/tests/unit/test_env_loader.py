from __future__ import annotations

import os
from pathlib import Path

import pytest

from utils.env_loader import (
    STAGE_ENV_FILENAMES,
    load_backend_env,
    resolve_stage_from_env,
    stage_env_filename,
    stage_env_path,
    stage_from_env,
)


def test_stage_from_env_explicit() -> None:
    assert stage_from_env({"OMI_ENV_STAGE": "dev"}) == "dev"
    assert stage_from_env({"OMI_ENV_STAGE": "LOCAL"}) == "local"


def test_stage_from_env_infers_offline_from_provider_mode() -> None:
    assert stage_from_env({"PROVIDER_MODE": "offline"}) == "offline"
    assert stage_from_env({"OMI_ENV_STAGE": "local", "PROVIDER_MODE": "offline"}) == "local"


def test_stage_from_env_unset() -> None:
    assert stage_from_env({}) is None


def test_stage_from_env_invalid() -> None:
    with pytest.raises(ValueError, match="OMI_ENV_STAGE"):
        stage_from_env({"OMI_ENV_STAGE": "staging"})


def test_stage_env_filename_local_uses_legacy_name() -> None:
    assert stage_env_filename("local") == ".env.local-dev"
    assert STAGE_ENV_FILENAMES["offline"] == ".env.offline"


def test_load_backend_env_stage_then_personal_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env.local-dev").write_text("SHARED=value\nPERSONAL=from-stage\n", encoding="utf-8")
    (tmp_path / ".env").write_text("PERSONAL=from-personal\n", encoding="utf-8")
    monkeypatch.setenv("OMI_ENV_STAGE", "local")
    for key in ("SHARED", "PERSONAL"):
        monkeypatch.delenv(key, raising=False)

    loaded = load_backend_env(tmp_path)

    assert loaded == [tmp_path / ".env.local-dev", tmp_path / ".env"]
    assert os.environ["SHARED"] == "value"
    assert os.environ["PERSONAL"] == "from-personal"


def test_load_backend_env_legacy_dotenv_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("LEGACY_ONLY=1\n", encoding="utf-8")
    monkeypatch.delenv("OMI_ENV_STAGE", raising=False)
    monkeypatch.delenv("PROVIDER_MODE", raising=False)
    monkeypatch.delenv("LEGACY_ONLY", raising=False)

    loaded = load_backend_env(tmp_path)

    assert loaded == [tmp_path / ".env"]
    assert os.environ["LEGACY_ONLY"] == "1"


def test_load_backend_env_respects_existing_os_environ(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / ".env").write_text("PRECEDENCE=from-file\n", encoding="utf-8")
    monkeypatch.delenv("OMI_ENV_STAGE", raising=False)
    monkeypatch.setenv("PRECEDENCE", "from-shell")

    load_backend_env(tmp_path)

    assert os.environ["PRECEDENCE"] == "from-shell"


def test_stage_env_path() -> None:
    base = Path("/tmp/backend")
    assert stage_env_path("dev", base) == base / ".env.dev"


def test_resolve_stage_from_env_invalid_falls_back() -> None:
    assert resolve_stage_from_env({"OMI_ENV_STAGE": "staging"}) is None


def test_load_backend_env_offline_ignores_provider_keys_in_personal_dotenv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env.offline").write_text("ENVIRONMENT=local-offline\n", encoding="utf-8")
    (tmp_path / ".env").write_text(
        "OPENAI_API_KEY=sk-leaked\nDEEPGRAM_API_KEY=dg-leaked\nADMIN_KEY=local-admin\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("OMI_ENV_STAGE", "offline")
    for key in ("OPENAI_API_KEY", "DEEPGRAM_API_KEY", "ADMIN_KEY", "ENVIRONMENT"):
        monkeypatch.delenv(key, raising=False)

    load_backend_env(tmp_path)

    assert os.environ["ENVIRONMENT"] == "local-offline"
    assert os.environ["ADMIN_KEY"] == "local-admin"
    assert "OPENAI_API_KEY" not in os.environ
    assert "DEEPGRAM_API_KEY" not in os.environ


def test_load_backend_env_skips_adc_when_auth_emulator_active(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env.local-dev").write_text(
        "FIREBASE_AUTH_EMULATOR_HOST=127.0.0.1:9099\n" "GOOGLE_APPLICATION_CREDENTIALS=google-credentials.json\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("OMI_ENV_STAGE", "local")
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)

    load_backend_env(tmp_path)

    assert os.environ["FIREBASE_AUTH_EMULATOR_HOST"] == "127.0.0.1:9099"
    assert "GOOGLE_APPLICATION_CREDENTIALS" not in os.environ


def test_load_backend_env_invalid_stage_uses_legacy_dotenv_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("LEGACY_ONLY=1\n", encoding="utf-8")
    monkeypatch.setenv("OMI_ENV_STAGE", "staging")
    monkeypatch.delenv("LEGACY_ONLY", raising=False)

    loaded = load_backend_env(tmp_path)

    assert loaded == [tmp_path / ".env"]
    assert os.environ["LEGACY_ONLY"] == "1"


def test_load_backend_env_skips_disk_when_harness_instance_set(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env.local-dev").write_text("SHOULD_NOT_LOAD=1\n", encoding="utf-8")
    monkeypatch.setenv("OMI_ENV_STAGE", "local")
    monkeypatch.setenv("OMI_HARNESS_INSTANCE", "default")
    monkeypatch.delenv("SHOULD_NOT_LOAD", raising=False)

    loaded = load_backend_env(tmp_path)

    assert loaded == []
    assert "SHOULD_NOT_LOAD" not in os.environ
