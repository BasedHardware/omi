"""Configuration primitives for the local dev harness."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from dotenv import dotenv_values

from . import providers, safety

FIRESTORE_PORT = 8085
AUTH_PORT = 9099
BACKEND_PORT = 8000
DESKTOP_BACKEND_PORT = 10201
REDIS_PORT = 6380
TYPESENSE_PORT = 8108
TYPESENSE_PINNED_VERSION = "27.1"
LOCAL_TYPESENSE_API_KEY = "local-typesense-api-key-not-real"
LOCAL_FIREBASE_API_KEY = "local-firebase-auth-emulator-api-key"
PROVIDER_MODES = providers.PROVIDER_MODES
CORE_PROVIDER_ENV = (
    "OPENAI_API_KEY",
    "DEEPGRAM_API_KEY",
    "GEMINI_API_KEY",
    "ANTHROPIC_API_KEY",
)
SECRETS_FILE_ALLOWED_KEYS = frozenset({"PROVIDER_MODE", *CORE_PROVIDER_ENV})


@dataclass(frozen=True)
class SecretsFileParseResult:
    secrets: dict[str, str]
    ignored_keys: tuple[str, ...]
    sources: dict[str, str]


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
    desktop_backend_host: str = f"127.0.0.1:{DESKTOP_BACKEND_PORT}"
    redis_host: str = "127.0.0.1"
    redis_port: int = REDIS_PORT

    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/0?omi_instance={self.instance}"

    @property
    def backend_url(self) -> str:
        return f"http://{self.backend_host}"

    @property
    def desktop_backend_url(self) -> str:
        return f"http://{self.desktop_backend_host}"


def repo_root_from(path: Path) -> Path:
    current = path.resolve()
    for candidate in (current, *current.parents):
        if (candidate / "AGENTS.md").is_file() and (candidate / ".git").exists():
            return candidate
    return Path(__file__).resolve().parents[3]


def provider_mode_from_env(env: Mapping[str, str] | None = None) -> str:
    return providers.provider_mode_from_env(env)


def secrets_file_path(cfg: HarnessConfig) -> Path:
    filename = ".env.offline" if cfg.provider_mode == "offline" else ".env.local-dev"
    return cfg.repo_root / "backend" / filename


def _credential_env_names(cfg: HarnessConfig) -> tuple[str, ...]:
    names: list[str] = []
    for spec in providers.default_provider_specs(cfg.repo_root):
        if spec.credential_env:
            names.append(spec.credential_env)
    return tuple(names)


def parse_secrets_file(cfg: HarnessConfig) -> SecretsFileParseResult:
    """Read provider secrets from the stage secrets file (file-first, ambient fallback)."""

    path = secrets_file_path(cfg)
    file_values = dotenv_values(path) if path.is_file() else {}
    ignored: list[str] = []
    secrets: dict[str, str] = {}
    sources: dict[str, str] = {}

    for key, raw in file_values.items():
        if key is None or raw is None:
            continue
        if key not in SECRETS_FILE_ALLOWED_KEYS:
            ignored.append(key)
            continue
        value = str(raw).strip()
        if value:
            secrets[key] = value
            sources[key] = "file"

    for key in _credential_env_names(cfg):
        if key in secrets:
            continue
        ambient = os.environ.get(key, "").strip()
        if ambient:
            secrets[key] = ambient
            sources[key] = "ambient"

    provider_mode = secrets.get("PROVIDER_MODE") or os.environ.get("PROVIDER_MODE", "").strip()
    if provider_mode:
        secrets["PROVIDER_MODE"] = provider_mode
        if "PROVIDER_MODE" not in sources:
            sources["PROVIDER_MODE"] = (
                "ambient" if provider_mode == os.environ.get("PROVIDER_MODE", "").strip() else "file"
            )

    return SecretsFileParseResult(
        secrets=secrets,
        ignored_keys=tuple(sorted(set(ignored))),
        sources=sources,
    )


def provider_secrets_from_file(cfg: HarnessConfig) -> dict[str, str]:
    """Return non-empty provider credential env vars (file-first, ambient fallback)."""

    parsed = parse_secrets_file(cfg)
    credential_names = set(_credential_env_names(cfg))
    return {key: value for key, value in parsed.secrets.items() if key in credential_names}


def preflight_env(cfg: HarnessConfig) -> dict[str, str]:
    """Merged ambient + secrets-file env used for provider preflight and dev-status."""

    merged = dict(os.environ)
    merged.update(parse_secrets_file(cfg).secrets)
    return merged


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
    parsed = parse_secrets_file(cfg)
    if parsed.secrets.get("PROVIDER_MODE"):
        provider_mode = provider_mode_from_env({**dict(source), **parsed.secrets})
        cfg = HarnessConfig(
            repo_root=cfg.repo_root,
            instance=cfg.instance,
            provider_mode=provider_mode,
            layout=cfg.layout,
        )
    safety.validate_harness_runtime_config(
        project_id=cfg.project_id,
        database_id=cfg.database_id,
        emulator_hosts={"Firestore emulator": cfg.firestore_host, "Firebase Auth emulator": cfg.auth_host},
    )
    return cfg


def _canonical_users_for_harness(cfg: HarnessConfig) -> str:
    manifest_path = cfg.layout.state_root / "manifests" / "canonical-auth-uids.json"
    if manifest_path.is_file():
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload = {}
        if isinstance(payload, dict):
            canonical = payload.get("canonical_users")
            if isinstance(canonical, list):
                values = [str(item).strip() for item in canonical if str(item).strip()]
                if values:
                    return ",".join(values)
            users = payload.get("users")
            if isinstance(users, dict):
                alice_uid = users.get("alice")
                if isinstance(alice_uid, str) and alice_uid.strip():
                    return alice_uid.strip()
            selected = payload.get("selected_user")
            if isinstance(selected, str) and selected.strip():
                return selected.strip()
    return os.environ.get("MEMORY_CANONICAL_USERS", "alice").strip()


def _harness_service_extra(cfg: HarnessConfig) -> dict[str, str]:
    canonical_users = _canonical_users_for_harness(cfg)
    return {
        "OMI_HARNESS_INSTANCE": cfg.instance,
        "OMI_HARNESS_STATE_ROOT": str(cfg.layout.state_root),
        "FIRESTORE_EMULATOR_HOST": cfg.firestore_host,
        "FIREBASE_AUTH_EMULATOR_HOST": cfg.auth_host,
        "FIREBASE_AUTH_PROJECT_ID": cfg.project_id,
        "FIREBASE_PROJECT_ID": cfg.project_id,
        "FIRESTORE_DATABASE_ID": cfg.database_id,
        "FIREBASE_API_KEY": LOCAL_FIREBASE_API_KEY,
        "MEMORY_CANONICAL_USERS": canonical_users,
        "REDIS_DB_HOST": cfg.redis_host,
        "REDIS_DB_PORT": str(cfg.redis_port),
        "REDIS_DB_PASSWORD": "",
        "ENVIRONMENT": "local-dev-harness",
        "ENCRYPTION_SECRET": "omi_local_dev_harness_32_byte_test_secret_not_prod",
        "ADMIN_KEY": "local-dev-admin-key-",
        "TYPESENSE_HOST": "127.0.0.1",
        "TYPESENSE_HOST_PORT": str(TYPESENSE_PORT),
        "TYPESENSE_API_KEY": LOCAL_TYPESENSE_API_KEY,
        "TYPESENSE_PROTOCOL": "http",
        "BASE_API_URL": cfg.backend_url,
        "API_BASE_URL": cfg.backend_url,
    }


def child_env_for(cfg: HarnessConfig) -> dict[str, str]:
    extra = {
        **_harness_service_extra(cfg),
        "PORT": str(BACKEND_PORT),
        "PYTHONUNBUFFERED": "1",
        "OMI_ENV_STAGE": "offline" if cfg.provider_mode == "offline" else "local",
    }
    if cfg.provider_mode != "offline":
        extra.update(provider_secrets_from_file(cfg))
    env = safety.build_child_env(provider_mode=cfg.provider_mode, extra=extra)
    if cfg.provider_mode == "offline":
        env.update(safety.offline_provider_placeholders())
    return env


def desktop_backend_child_env_for(cfg: HarnessConfig) -> dict[str, str]:
    extra = {
        **_harness_service_extra(cfg),
        "PORT": str(DESKTOP_BACKEND_PORT),
        "USE_VERTEX_AI": "false",
        "OMI_ENV_STAGE": "offline" if cfg.provider_mode == "offline" else "local",
    }
    if cfg.provider_mode != "offline":
        extra.update(provider_secrets_from_file(cfg))
    env = safety.build_child_env(provider_mode=cfg.provider_mode, extra=extra)
    if cfg.provider_mode == "offline":
        env.update(safety.offline_provider_placeholders())
        env["OMI_LLM_STUB"] = "1"
    return env
