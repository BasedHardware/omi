from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dev_harness import config, safety

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_child_env_for_offline_mode() -> None:
    cfg = config.HarnessConfig(
        repo_root=REPO_ROOT,
        instance="default",
        provider_mode="offline",
        layout=safety.layout_for_instance(REPO_ROOT, "default"),
    )
    child = config.child_env_for(cfg)
    assert child["PROVIDER_MODE"] == "offline"
    assert child["OMI_HARNESS_INSTANCE"] == "default"
    assert child["FIREBASE_API_KEY"] == config.LOCAL_FIREBASE_API_KEY
    assert child["OMI_LLM_GATEWAY_FEATURE_MODE"] == "off"


def test_child_env_for_real_mode() -> None:
    cfg = config.HarnessConfig(
        repo_root=REPO_ROOT,
        instance="default",
        provider_mode="real",
        layout=safety.layout_for_instance(REPO_ROOT, "default"),
    )
    child = config.child_env_for(cfg)
    assert child["PROVIDER_MODE"] == "real"
    assert child["BASE_API_URL"] == cfg.backend_url
    assert child["OMI_LOCAL_STORAGE_ROOT"] == str(cfg.layout.services_dir / "storage")
    assert child["OMI_LOCAL_STORAGE_BASE_URL"] == f"{cfg.backend_url}/_local/storage"
    assert child["BUCKET_SPEECH_PROFILES"] == "speech-profiles"
    assert child["BUCKET_MEMORIES_RECORDINGS"] == "memories-recordings"
    assert child["BUCKET_SCREEN_FRAMES"] == "screen-frames"
    assert child["SCREEN_FRAME_SIGNING_SECRET"] == config.LOCAL_SCREEN_FRAME_SIGNING_SECRET
    # Without this the harness backend refuses every adjudication with 409, which is
    # correct for production and useless for the machine meant to exercise the feature.
    assert child["SCREEN_FRAME_EGRESS_ENABLED"] == "true"


def test_offline_mode_still_supplies_the_screen_frame_signing_secret() -> None:
    # The name matches the provider-credential regex on "SECRET"; it is a harness-local
    # HMAC key, and refusing it offline would make the egress routes fail closed for the
    # one mode that needs no external credentials at all.
    cfg = config.HarnessConfig(
        repo_root=REPO_ROOT,
        instance="default",
        provider_mode="offline",
        layout=safety.layout_for_instance(REPO_ROOT, "default"),
    )
    child = config.child_env_for(cfg)
    assert child["SCREEN_FRAME_SIGNING_SECRET"] == config.LOCAL_SCREEN_FRAME_SIGNING_SECRET


def test_nondefault_port_offset_propagates_to_every_harness_service() -> None:
    cfg = config.load_config(REPO_ROOT, env={"OMI_HARNESS_PORT_OFFSET": "321"})

    assert cfg.firestore_host == "127.0.0.1:8406"
    assert cfg.auth_host == "127.0.0.1:9420"
    assert cfg.redis_port == 6701
    assert cfg.typesense_port == 8429
    assert cfg.backend_url == "http://127.0.0.1:8321"
    assert cfg.desktop_backend_url == "http://127.0.0.1:10522"
    assert cfg.llm_gateway_url == "http://127.0.0.1:9401"
    assert cfg.llm_gateway_service_token == f"{config.LOCAL_LLM_GATEWAY_SERVICE_TOKEN}:{cfg.instance}"

    backend_env = config.child_env_for(cfg)
    desktop_env = config.desktop_backend_child_env_for(cfg)
    assert backend_env["FIRESTORE_EMULATOR_HOST"] == cfg.firestore_host
    assert backend_env["FIREBASE_AUTH_EMULATOR_HOST"] == cfg.auth_host
    assert backend_env["REDIS_DB_PORT"] == "6701"
    assert backend_env["TYPESENSE_HOST_PORT"] == "8429"
    assert backend_env["PORT"] == "8321"
    assert desktop_env["PORT"] == "10522"
    assert backend_env["OMI_LLM_GATEWAY_URL"] == cfg.llm_gateway_url
    assert desktop_env["OMI_LLM_GATEWAY_URL"] == cfg.llm_gateway_url
    assert backend_env["OMI_LLM_GATEWAY_SERVICE_TOKEN"] == cfg.llm_gateway_service_token
    assert desktop_env["OMI_LLM_GATEWAY_SERVICE_TOKEN"] == cfg.llm_gateway_service_token
    assert backend_env["OMI_LLM_GATEWAY_FEATURE_MODE"] == "gateway"
    assert desktop_env["OMI_LLM_GATEWAY_FEATURE_MODE"] == "gateway"


def test_offline_child_env_uses_direct_llm_feature_mode() -> None:
    cfg = config.HarnessConfig(
        repo_root=REPO_ROOT,
        instance="offline-qa",
        provider_mode="offline",
        layout=safety.layout_for_instance(REPO_ROOT, "offline-qa"),
    )
    backend_env = config.child_env_for(cfg)
    desktop_env = config.desktop_backend_child_env_for(cfg)
    assert backend_env["OMI_LLM_GATEWAY_FEATURE_MODE"] == "off"
    assert desktop_env["OMI_LLM_GATEWAY_FEATURE_MODE"] == "off"
    assert desktop_env["OMI_LLM_STUB"] == "1"


def test_llm_gateway_port_override_is_isolated_from_shared_default() -> None:
    cfg = config.load_config(
        REPO_ROOT,
        env={
            "OMI_HARNESS_PORT_OFFSET": "10",
            "OMI_HARNESS_LLM_GATEWAY_PORT": "19080",
            "OMI_LOCAL_INSTANCE": "qa-offset",
        },
    )
    assert cfg.llm_gateway_port == 19080
    assert cfg.llm_gateway_url == "http://127.0.0.1:19080"
    assert cfg.llm_gateway_service_token.endswith(":qa-offset")
    assert config.child_env_for(cfg)["OMI_LLM_GATEWAY_URL"] == "http://127.0.0.1:19080"
