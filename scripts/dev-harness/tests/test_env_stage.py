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


def test_nondefault_port_offset_propagates_to_every_harness_service() -> None:
    cfg = config.load_config(REPO_ROOT, env={"OMI_HARNESS_PORT_OFFSET": "321"})

    assert cfg.firestore_host == "127.0.0.1:8406"
    assert cfg.auth_host == "127.0.0.1:9420"
    assert cfg.redis_port == 6701
    assert cfg.typesense_port == 8429
    assert cfg.backend_url == "http://127.0.0.1:8321"
    assert cfg.desktop_backend_url == "http://127.0.0.1:10522"

    backend_env = config.child_env_for(cfg)
    desktop_env = config.desktop_backend_child_env_for(cfg)
    assert backend_env["FIRESTORE_EMULATOR_HOST"] == cfg.firestore_host
    assert backend_env["FIREBASE_AUTH_EMULATOR_HOST"] == cfg.auth_host
    assert backend_env["REDIS_DB_PORT"] == "6701"
    assert backend_env["TYPESENSE_HOST_PORT"] == "8429"
    assert backend_env["PORT"] == "8321"
    assert desktop_env["PORT"] == "10522"
