from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dev_harness import config, providers, safety

REPO_ROOT = Path(__file__).resolve().parents[3]


def _real_env(api_key: str = "sk-local-dev-test-key") -> dict[str, str]:
    deepgram = "dg-local-dev-test-key"
    return {
        "PROVIDER_MODE": "real",
        "OPENAI_API_KEY": api_key,
        "DEEPGRAM_API_KEY": deepgram,
        "OMI_LOCAL_OPENAI_ACCOUNT": "local-openai-dev-account",
        "OMI_LOCAL_OPENAI_PROJECT": "local-openai-dev-project",
        "OMI_LOCAL_OPENAI_KEY_SHA256_12": providers.secret_fingerprint(api_key),
        "OMI_LOCAL_DEEPGRAM_ACCOUNT": "local-deepgram-dev-account",
        "OMI_LOCAL_DEEPGRAM_PROJECT": "local-deepgram-dev-project",
        "OMI_LOCAL_DEEPGRAM_KEY_SHA256_12": providers.secret_fingerprint(deepgram),
        "OMI_LOCAL_HOSTED_ML_ACCOUNT": "local-hosted-ml",
        "OMI_LOCAL_HOSTED_ML_PROJECT": "loopback-only",
    }


def test_credential_checker_real_and_offline_modes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("OMI_LOCAL_STATE_ROOT", str(tmp_path / "state"))
    for key in _real_env():
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("PROVIDER_MODE", "real")

    real_missing = providers.provider_preflight(REPO_ROOT)

    assert not real_missing.ok
    assert any("OPENAI_API_KEY" in item for item in real_missing.missing)
    assert any("OMI_LOCAL_OPENAI_ACCOUNT" in item for item in real_missing.missing)
    assert any("sha256 first 12" in item for item in real_missing.missing) is False

    monkeypatch.setenv("PROVIDER_MODE", "offline")
    offline = providers.provider_preflight(REPO_ROOT)

    assert offline.ok
    assert offline.enabled_external_providers == ()
    assert "openai" in offline.offline_fake_sources
    assert "backend/testing/e2e/fakes/llm.py" in offline.offline_fake_sources["openai"]


def test_real_mode_accepts_approved_fingerprints_without_leaking_secrets() -> None:
    env = _real_env()
    report = providers.provider_preflight(REPO_ROOT, env=env)

    assert report.ok
    assert set(report.enabled_external_providers) == {"openai", "deepgram", "hosted-ml-local-http"}
    assert report.fingerprints["openai"] == env["OMI_LOCAL_OPENAI_KEY_SHA256_12"]
    rendered = "\n".join(providers.status_lines(report))
    assert env["OPENAI_API_KEY"] not in rendered
    assert env["DEEPGRAM_API_KEY"] not in rendered
    assert "sha256:" in rendered


def test_endpoint_and_capability_allowlists() -> None:
    broker = providers.ProviderBroker(REPO_ROOT, env=_real_env())

    broker.check_request(
        providers.ProviderRequest(
            provider="openai",
            capability="llm.chat",
            endpoint="https://api.openai.com/v1/chat/completions",
            estimated_cost_usd=0.01,
        )
    )

    with pytest.raises(providers.ProviderPolicyError, match="Capability"):
        broker.check_request(
            providers.ProviderRequest(
                provider="openai",
                capability="llm.finetune",
                endpoint="https://api.openai.com/v1/chat/completions",
                estimated_cost_usd=0.01,
            )
        )
    with pytest.raises(providers.ProviderPolicyError, match="Endpoint"):
        broker.check_request(
            providers.ProviderRequest(
                provider="openai",
                capability="llm.chat",
                endpoint="https://api.evil.example/v1/chat/completions",
                estimated_cost_usd=0.01,
            )
        )
    with pytest.raises(providers.ProviderPolicyError, match="estimated cost"):
        broker.check_request(
            providers.ProviderRequest(
                provider="openai",
                capability="llm.chat",
                endpoint="https://api.openai.com/v1/chat/completions",
            )
        )


def test_hosted_vector_and_external_state_writes_are_rejected() -> None:
    broker = providers.ProviderBroker(REPO_ROOT, env=_real_env())

    with pytest.raises(providers.ProviderPolicyError, match="vector/index writes"):
        broker.check_request(
            providers.ProviderRequest(
                provider="openai",
                capability="embedding.read",
                endpoint="https://api.openai.com/v1/embeddings",
                estimated_cost_usd=0.01,
                uses_vector_or_index_write=True,
            )
        )
    with pytest.raises(providers.ProviderPolicyError, match="durable external side effects"):
        broker.check_request(
            providers.ProviderRequest(
                provider="openai",
                capability="llm.chat",
                endpoint="https://api.openai.com/v1/chat/completions",
                estimated_cost_usd=0.01,
                uses_webhook=True,
            )
        )
    with pytest.raises(providers.ProviderPolicyError, match="replay"):
        broker.check_request(
            providers.ProviderRequest(
                provider="openai",
                capability="llm.chat",
                endpoint="https://api.openai.com/v1/chat/completions",
                estimated_cost_usd=0.01,
                replay_after_restart=True,
            )
        )


def test_offline_mode_uses_hermetic_shared_fake_provider_wrapper() -> None:
    registry = providers.OfflineProviderRegistry(REPO_ROOT)
    fake_paths = registry.fake_source_paths()

    assert fake_paths["openai"].endswith("backend/testing/e2e/fakes/llm.py")
    llm_fake = registry.load_fake("openai")
    response = llm_fake.make_openai_chat_response()
    assert response["id"] == "chatcmpl-fake-e2e-test"

    offline_broker = providers.ProviderBroker(REPO_ROOT, env={"PROVIDER_MODE": "offline"})
    offline_broker.check_request(
        providers.ProviderRequest(
            provider="openai",
            capability="llm.chat",
            endpoint="https://api.openai.com/v1/chat/completions",
            estimated_cost_usd=0.0,
        )
    )


def test_provider_secrets_not_emitted_in_child_env_status_or_config_digest(tmp_path: Path) -> None:
    env = os.environ.copy()
    env.update(_real_env(api_key="sk-super-secret-local-provider-key"))
    env["OMI_LOCAL_STATE_ROOT"] = str(tmp_path / "state")
    env["PYTHONPATH"] = f"{REPO_ROOT / 'scripts' / 'dev-harness'}:{env.get('PYTHONPATH', '')}"

    cfg = config.load_config(REPO_ROOT, env=env, create_layout=True)
    child = config.child_env_for(cfg)
    assert child.get("OPENAI_API_KEY") != env["OPENAI_API_KEY"]
    assert env["OPENAI_API_KEY"] not in "\n".join(providers.status_lines(providers.provider_preflight(REPO_ROOT, env=env)))

    result = subprocess.run(
        [sys.executable, "-m", "dev_harness.cli", "up"],
        cwd=REPO_ROOT,
        env={**env, "PATH": "/tmp/no-tools"},
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=30,
    )
    assert result.returncode == 1
    assert env["OPENAI_API_KEY"] not in result.stdout
    digest = cfg.layout.config_digest_path.read_text(encoding="utf-8") if cfg.layout.config_digest_path.exists() else ""
    assert env["OPENAI_API_KEY"] not in digest


def test_offline_child_env_rejects_provider_credentials() -> None:
    parent = {"PATH": "/usr/bin", "OPENAI_API_KEY": "sk-secret", "PROVIDER_MODE": "offline"}
    env = safety.build_child_env(parent, provider_mode="offline")
    assert "OPENAI_API_KEY" not in env

    with pytest.raises(safety.SafetyError, match="provider credential"):
        safety.build_child_env(parent, provider_mode="offline", extra={"OPENAI_API_KEY": "sk-secret"})
