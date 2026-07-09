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
    return {
        "PROVIDER_MODE": "real",
        "OPENAI_API_KEY": api_key,
        "DEEPGRAM_API_KEY": "dg-local-dev-test-key",
        "GEMINI_API_KEY": "gemini-local-dev-test-key",
        "ANTHROPIC_API_KEY": "sk-ant-local-dev-test-key",
    }


def test_credential_checker_real_and_offline_modes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("OMI_LOCAL_STATE_ROOT", str(tmp_path / "state"))
    for key in _real_env():
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("PROVIDER_MODE", "real")

    real_missing = providers.provider_preflight(REPO_ROOT)

    assert not real_missing.ok
    assert any("OPENAI_API_KEY" in item for item in real_missing.missing)
    assert not any("OMI_LOCAL_" in item for item in real_missing.missing)

    monkeypatch.setenv("PROVIDER_MODE", "offline")
    offline = providers.provider_preflight(REPO_ROOT)

    assert offline.ok
    assert offline.enabled_external_providers == ()
    assert "openai" in offline.offline_fake_sources
    assert "backend/testing/e2e/fakes/llm.py" in offline.offline_fake_sources["openai"]


def test_real_mode_reports_fingerprints_without_leaking_secrets() -> None:
    env = _real_env()
    report = providers.provider_preflight(REPO_ROOT, env=env)

    assert report.ok
    assert set(report.enabled_external_providers) == {
        "openai",
        "deepgram",
        "gemini",
        "anthropic",
        "hosted-ml-local-http",
    }
    assert report.fingerprints["openai"] == providers.secret_fingerprint(env["OPENAI_API_KEY"])
    rendered = "\n".join(providers.status_lines(report))
    assert env["OPENAI_API_KEY"] not in rendered
    assert env["DEEPGRAM_API_KEY"] not in rendered
    assert env["GEMINI_API_KEY"] not in rendered
    assert env["ANTHROPIC_API_KEY"] not in rendered
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


def test_provider_secrets_injected_into_child_env(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    backend = repo / "backend"
    backend.mkdir(parents=True)
    (repo / "AGENTS.md").write_text("agents", encoding="utf-8")
    (repo / ".git").mkdir()
    secret = "sk-super-secret-local-provider-key"
    (backend / ".env.local-dev").write_text(
        "\n".join(
            [
                "PROVIDER_MODE=real",
                f"OPENAI_API_KEY={secret}",
                "DEEPGRAM_API_KEY=dg-local-dev-test-key",
                "GEMINI_API_KEY=gemini-local-dev-test-key",
                "ANTHROPIC_API_KEY=sk-ant-local-dev-test-key",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["OMI_LOCAL_STATE_ROOT"] = str(tmp_path / "state")
    env["PYTHONPATH"] = f"{REPO_ROOT / 'scripts' / 'dev-harness'}:{env.get('PYTHONPATH', '')}"
    for key in ("OPENAI_API_KEY", "DEEPGRAM_API_KEY", "GEMINI_API_KEY", "ANTHROPIC_API_KEY"):
        env.pop(key, None)

    cfg = config.load_config(repo, env=env, create_layout=True)
    child = config.child_env_for(cfg)
    desktop_child = config.desktop_backend_child_env_for(cfg)
    for key in ("OPENAI_API_KEY", "DEEPGRAM_API_KEY", "GEMINI_API_KEY", "ANTHROPIC_API_KEY"):
        expected = config.parse_secrets_file(cfg).secrets[key]
        assert child.get(key) == expected
        assert desktop_child.get(key) == expected
    assert secret not in "\n".join(
        providers.status_lines(providers.provider_preflight(repo, env=config.preflight_env(cfg)))
    )


def test_placeholder_secret_rejected() -> None:
    env = _real_env()
    env["OPENAI_API_KEY"] = "changeme"
    report = providers.provider_preflight(REPO_ROOT, env=env)
    assert not report.ok
    assert any("placeholder" in item.lower() for item in report.missing)


def test_parse_secrets_file_ignores_non_secret_keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "repo"
    backend = repo / "backend"
    backend.mkdir(parents=True)
    (repo / "AGENTS.md").write_text("agents", encoding="utf-8")
    (repo / ".git").mkdir()
    (backend / ".env.local-dev").write_text(
        "OPENAI_API_KEY=sk-file-key\nFIREBASE_PROJECT_ID=evil-project\nBASE_API_URL=http://evil\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("OMI_LOCAL_STATE_ROOT", str(tmp_path / "state"))
    cfg = config.load_config(repo, create_layout=True)
    parsed = config.parse_secrets_file(cfg)
    assert "FIREBASE_PROJECT_ID" in parsed.ignored_keys
    assert parsed.secrets.get("OPENAI_API_KEY") == "sk-file-key"
    child = config.child_env_for(cfg)
    assert child["FIREBASE_PROJECT_ID"] == safety.DEFAULT_LOCAL_FIREBASE_PROJECT_ID


def test_offline_child_env_rejects_provider_credentials() -> None:
    parent = {"PATH": "/usr/bin", "OPENAI_API_KEY": "sk-secret", "PROVIDER_MODE": "offline"}
    env = safety.build_child_env(parent, provider_mode="offline")
    assert "OPENAI_API_KEY" not in env

    with pytest.raises(safety.SafetyError, match="provider credential"):
        safety.build_child_env(parent, provider_mode="offline", extra={"OPENAI_API_KEY": "sk-secret"})
