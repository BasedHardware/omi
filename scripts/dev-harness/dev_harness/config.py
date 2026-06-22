"""Configuration primitives for the local dev harness."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from . import providers, safety

FIRESTORE_PORT = 8085
AUTH_PORT = 9099
BACKEND_PORT = 8000
REDIS_PORT = 6380
PROVIDER_MODES = providers.PROVIDER_MODES
CORE_PROVIDER_ENV = ("OPENAI_API_KEY", "DEEPGRAM_API_KEY")


@dataclass(frozen=True)
class HarnessConfig:
    repo_root: Path
    instance: str
    provider_mode: str
    layout: safety.HarnessLayout
    project_id: str = safety.DEFAULT_LOCAL_FIREBASE_PROJECT_ID
    database_id: str = safety.DEFAULT_FIRESTORE_DATABASE_ID
    firestore_host: str = f"127.0.0.1:{FIRESTORE_PORT}"
    auth_host: str = f"127.0.0.1:{AUTH_PORT}"
    backend_host: str = f"127.0.0.1:{BACKEND_PORT}"
    redis_host: str = "127.0.0.1"
    redis_port: int = REDIS_PORT

    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/0?omi_instance={self.instance}"

    @property
    def backend_url(self) -> str:
        return f"http://{self.backend_host}"


def repo_root_from(path: Path) -> Path:
    current = path.resolve()
    for candidate in (current, *current.parents):
        if (candidate / "AGENTS.md").is_file() and (candidate / ".git").exists():
            return candidate
    return Path(__file__).resolve().parents[3]


def provider_mode_from_env(env: Mapping[str, str] | None = None) -> str:
    return providers.provider_mode_from_env(env)


def load_config(repo_root: Path, env: Mapping[str, str] | None = None, *, create_layout: bool = False) -> HarnessConfig:
    source = os.environ if env is None else env
    instance = safety.validate_instance_name(source.get("OMI_LOCAL_INSTANCE", safety.DEFAULT_INSTANCE_NAME))
    provider_mode = provider_mode_from_env(source)
    layout = (
        safety.create_state_layout(repo_root, instance, source)
        if create_layout
        else safety.layout_for_instance(repo_root, instance, source)
    )
    cfg = HarnessConfig(repo_root=repo_root.resolve(), instance=instance, provider_mode=provider_mode, layout=layout)
    safety.validate_harness_runtime_config(
        project_id=cfg.project_id,
        database_id=cfg.database_id,
        emulator_hosts={"Firestore emulator": cfg.firestore_host, "Firebase Auth emulator": cfg.auth_host},
    )
    return cfg


def child_env_for(cfg: HarnessConfig) -> dict[str, str]:
    return safety.build_child_env(
        provider_mode=cfg.provider_mode,
        extra={
            "OMI_HARNESS_INSTANCE": cfg.instance,
            "OMI_HARNESS_STATE_ROOT": str(cfg.layout.state_root),
            "FIRESTORE_EMULATOR_HOST": cfg.firestore_host,
            "FIREBASE_AUTH_EMULATOR_HOST": cfg.auth_host,
            "FIREBASE_AUTH_PROJECT_ID": cfg.project_id,
            "REDIS_DB_HOST": cfg.redis_host,
            "REDIS_DB_PORT": str(cfg.redis_port),
            "REDIS_DB_PASSWORD": "",
            "PORT": str(BACKEND_PORT),
            "ENVIRONMENT": "local-dev-harness",
            "ENCRYPTION_SECRET": "omi_local_dev_harness_32_byte_test_secret_not_prod",
            "ADMIN_KEY": "local-dev-admin-key-",
            "TYPESENSE_HOST": "127.0.0.1",
            "TYPESENSE_HOST_PORT": "8108",
            "TYPESENSE_API_KEY": "local-typesense-api-key-not-real",
            "PYTHONUNBUFFERED": "1",
        },
    )
