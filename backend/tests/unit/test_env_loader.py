from __future__ import annotations

import os
from pathlib import Path

import pytest

from utils.env_loader import (
    firebase_admin_options,
    STAGE_ENV_FILENAMES,
    load_backend_env,
    resolve_stage_from_env,
    stage_env_filename,
    stage_env_path,
    stage_from_env,
)
from utils.firebase_admin_runtime import (
    firebase_verify_only_credential,
    install_firebase_auth_mutation_guard,
    install_google_adc_guard,
)


def test_firebase_admin_options_uses_explicit_auth_project_only() -> None:
    assert firebase_admin_options({"FIREBASE_AUTH_PROJECT_ID": " based-hardware "}) == {"projectId": "based-hardware"}
    assert firebase_admin_options({"FIREBASE_PROJECT_ID": "data-project"}) is None


def test_local_jit_qa_firebase_is_verify_only() -> None:
    from google.auth.credentials import AnonymousCredentials

    credential = firebase_verify_only_credential({"OMI_JIT_QA_LOCAL_STACK": "1"})
    assert credential is not None
    assert isinstance(credential.get_credential(), AnonymousCredentials)
    assert firebase_verify_only_credential({}) is None


def test_cloud_jit_qa_firebase_is_verify_only_without_blocking_firestore_adc() -> None:
    from google.auth.credentials import AnonymousCredentials

    environment = {
        "OMI_JIT_QA_AUTH_ONLY": "true",
        "OMI_ENV_STAGE": "dev",
        "GOOGLE_CLOUD_PROJECT": "based-hardware-dev",
    }
    credential = firebase_verify_only_credential(environment)
    assert credential is not None
    assert isinstance(credential.get_credential(), AnonymousCredentials)


def test_cloud_jit_qa_verify_only_fence_normalizes_stage_and_project() -> None:
    credential = firebase_verify_only_credential(
        {
            "OMI_JIT_QA_AUTH_ONLY": " TRUE ",
            "OMI_ENV_STAGE": " DEV ",
            "GOOGLE_CLOUD_PROJECT": " based-hardware-dev ",
        }
    )
    assert credential is not None


def test_local_jit_qa_blocks_firebase_auth_mutations() -> None:
    class FakeAuth:
        pass

    fake = FakeAuth()
    from utils.firebase_admin_runtime import _AUTH_MUTATORS

    for name in _AUTH_MUTATORS:
        setattr(fake, name, lambda: None)
    assert install_firebase_auth_mutation_guard({"OMI_JIT_QA_LOCAL_STACK": "1"}, auth_module=fake)
    with pytest.raises(RuntimeError, match="mutations are disabled"):
        fake.delete_user("real-user")


def test_local_jit_qa_blocks_real_firebase_auth_module_before_network() -> None:
    from firebase_admin import auth as firebase_auth
    from utils.firebase_admin_runtime import _AUTH_MUTATORS

    originals = {name: getattr(firebase_auth, name) for name in _AUTH_MUTATORS}
    try:
        assert install_firebase_auth_mutation_guard({"OMI_JIT_QA_LOCAL_STACK": "1"}, auth_module=firebase_auth)
        with pytest.raises(RuntimeError, match="mutations are disabled"):
            firebase_auth.delete_user("must-not-reach-firebase")
    finally:
        for name, function in originals.items():
            setattr(firebase_auth, name, function)


def test_local_jit_qa_google_adc_guard_blocks_discovery() -> None:
    class FakeGoogleAuth:
        @staticmethod
        def default():
            return object(), "unsafe"

    assert install_google_adc_guard({"OMI_JIT_QA_LOCAL_STACK": "1"}, google_auth_module=FakeGoogleAuth)
    with pytest.raises(RuntimeError, match="Google ADC is disabled"):
        FakeGoogleAuth.default()


def test_google_adc_guard_is_inert_outside_local_jit() -> None:
    class FakeGoogleAuth:
        @staticmethod
        def default():
            return object(), "unchanged"

    original = FakeGoogleAuth.default
    assert not install_google_adc_guard({}, google_auth_module=FakeGoogleAuth)
    assert FakeGoogleAuth.default is original


def test_cloud_qa_auth_only_fence_blocks_auth_mutations_but_keeps_firestore_adc() -> None:
    class FakeAuth:
        pass

    fake = FakeAuth()
    from utils.firebase_admin_runtime import _AUTH_MUTATORS

    for name in _AUTH_MUTATORS:
        setattr(fake, name, lambda: None)
    environment = {
        "OMI_JIT_QA_AUTH_ONLY": "true",
        "OMI_ENV_STAGE": "dev",
        "GOOGLE_CLOUD_PROJECT": "based-hardware-dev",
    }
    assert install_firebase_auth_mutation_guard(environment, auth_module=fake)
    assert not install_google_adc_guard(environment, google_auth_module=FakeAuth)


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
        "FIREBASE_AUTH_EMULATOR_HOST=127.0.0.1:9099\n"
        "GOOGLE_APPLICATION_CREDENTIALS=google-credentials.json\n"
        "FIREBASE_AUTH_CREDENTIALS_PATH=firebase-auth.json\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("OMI_ENV_STAGE", "local")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/tmp/inherited-google-credentials.json")
    monkeypatch.setenv("SERVICE_ACCOUNT_JSON", '{"type":"service_account"}')
    monkeypatch.setenv("FIREBASE_AUTH_CREDENTIALS_PATH", "/tmp/inherited-firebase-auth.json")

    load_backend_env(tmp_path)

    assert os.environ["FIREBASE_AUTH_EMULATOR_HOST"] == "127.0.0.1:9099"
    assert "GOOGLE_APPLICATION_CREDENTIALS" not in os.environ
    assert "SERVICE_ACCOUNT_JSON" not in os.environ
    assert "FIREBASE_AUTH_CREDENTIALS_PATH" not in os.environ


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
