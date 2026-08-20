"""Configuration primitives for the local dev harness."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from dotenv import dotenv_values

from . import providers, safety

FIRESTORE_PORT = 8085
AUTH_PORT = 9099
BACKEND_PORT = 8000
LLM_GATEWAY_PORT = 9080
DESKTOP_BACKEND_PORT = 10201
REDIS_PORT = 6380
TYPESENSE_PORT = 8108
# The official container listens on its internal default unless an explicit
# --api-port is supplied. Harness instances vary only the loopback host port.
TYPESENSE_CONTAINER_PORT = 8108
TYPESENSE_PINNED_VERSION = "27.1"
LOCAL_TYPESENSE_API_KEY = "local-typesense-api-key-not-real"
LOCAL_FIREBASE_API_KEY = "local-firebase-auth-emulator-api-key"
LOCAL_LLM_GATEWAY_SERVICE_TOKEN = "local-dev-llm-gateway-service-token-not-real"
PORT_OFFSET_ENV = "OMI_HARNESS_PORT_OFFSET"
PORT_OVERRIDE_ENVS = {
    "firestore": "OMI_HARNESS_FIRESTORE_PORT",
    "auth": "OMI_HARNESS_AUTH_PORT",
    "backend": "OMI_HARNESS_BACKEND_PORT",
    "desktop_backend": "OMI_HARNESS_DESKTOP_BACKEND_PORT",
    "redis": "OMI_HARNESS_REDIS_PORT",
    "typesense": "OMI_HARNESS_TYPESENSE_PORT",
    "llm_gateway": "OMI_HARNESS_LLM_GATEWAY_PORT",
}
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
    firestore_port: int = FIRESTORE_PORT
    auth_port: int = AUTH_PORT
    backend_port: int = BACKEND_PORT
    desktop_backend_port: int = DESKTOP_BACKEND_PORT
    redis_host: str = "127.0.0.1"
    redis_port: int = REDIS_PORT
    typesense_port: int = TYPESENSE_PORT
    dev_bind_host: str = "127.0.0.1"
    llm_gateway_port: int = LLM_GATEWAY_PORT

    @property
    def firestore_host(self) -> str:
        return f"127.0.0.1:{self.firestore_port}"

    @property
    def auth_host(self) -> str:
        return f"127.0.0.1:{self.auth_port}"

    @property
    def backend_host(self) -> str:
        return f"127.0.0.1:{self.backend_port}"

    @property
    def desktop_backend_host(self) -> str:
        return f"127.0.0.1:{self.desktop_backend_port}"

    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/0?omi_instance={self.instance}"

    @property
    def backend_url(self) -> str:
        return f"http://{self.backend_host}"

    @property
    def desktop_backend_url(self) -> str:
        return f"http://{self.desktop_backend_host}"

    @property
    def llm_gateway_url(self) -> str:
        return f"http://127.0.0.1:{self.llm_gateway_port}"

    @property
    def llm_gateway_service_token(self) -> str:
        # Isolate tokens per harness instance so parallel offsets cannot reuse
        # the shared local default and accidentally authorize each other.
        return f"{LOCAL_LLM_GATEWAY_SERVICE_TOKEN}:{self.instance}"


def repo_root_from(path: Path) -> Path:
    current = path.resolve()
    for candidate in (current, *current.parents):
        if (candidate / "AGENTS.md").is_file() and (candidate / ".git").exists():
            return candidate
    return Path(__file__).resolve().parents[3]


def provider_mode_from_env(env: Mapping[str, str] | None = None) -> str:
    return providers.provider_mode_from_env(env)


DEV_BIND_HOST_ENV = "OMI_DEV_BIND_HOST"
# Falls back to OMI_DEV_HOST (app/setup.sh:53) so a contributor who follows the
# documented physical-device setup — set OMI_DEV_HOST to the Mac's reachable
# address — gets a harness that actually listens there too, not just an app
# built to expect it (#11774). OMI_DEV_BIND_HOST exists for the narrower case
# of wanting an asymmetric bind (e.g. a different advertise vs. listen address).
APP_DEV_HOST_ENV = "OMI_DEV_HOST"


def dev_bind_host_from_env(env: Mapping[str, str] | None = None) -> str:
    """Resolve what the harness's HTTP services and Firebase emulators bind to.

    Defaults to loopback-only, preserving today's behavior. Binds all
    interfaces (0.0.0.0) when a private LAN/CGNAT address is requested, rather
    than that literal address, so loopback callers (health checks, a booted
    simulator) keep working alongside the newly reachable LAN/tailnet address.
    Fails closed (SafetyError) on a publicly routable address.
    """

    source = os.environ if env is None else env
    requested = source.get(DEV_BIND_HOST_ENV, "").strip() or source.get(APP_DEV_HOST_ENV, "").strip()
    if not requested:
        return "127.0.0.1"
    safety.validate_dev_bind_host(requested, name=DEV_BIND_HOST_ENV)
    if safety.is_loopback_host(requested):
        return "127.0.0.1"
    return "0.0.0.0"


def _port_from_env(source: Mapping[str, str], name: str, default: int, offset: int) -> int:
    raw = source.get(PORT_OVERRIDE_ENVS[name], "").strip()
    try:
        value = int(raw) if raw else default + offset
    except ValueError as exc:
        raise safety.SafetyError(f"{PORT_OVERRIDE_ENVS[name]} must be an integer, got {raw!r}") from exc
    if not 1 <= value <= 65535:
        raise safety.SafetyError(f"{PORT_OVERRIDE_ENVS[name]} resolved outside valid port range: {value}")
    return value


def harness_ports_from_env(env: Mapping[str, str] | None = None) -> dict[str, int]:
    """Resolve one isolated loopback port set while preserving dev defaults."""

    source = os.environ if env is None else env
    raw_offset = source.get(PORT_OFFSET_ENV, "0").strip()
    try:
        offset = int(raw_offset)
    except ValueError as exc:
        raise safety.SafetyError(f"{PORT_OFFSET_ENV} must be an integer, got {raw_offset!r}") from exc
    if not 0 <= offset <= 50000:
        raise safety.SafetyError(f"{PORT_OFFSET_ENV} must be between 0 and 50000, got {offset}")
    defaults = {
        "firestore": FIRESTORE_PORT,
        "auth": AUTH_PORT,
        "backend": BACKEND_PORT,
        "desktop_backend": DESKTOP_BACKEND_PORT,
        "redis": REDIS_PORT,
        "typesense": TYPESENSE_PORT,
        "llm_gateway": LLM_GATEWAY_PORT,
    }
    ports = {name: _port_from_env(source, name, default, offset) for name, default in defaults.items()}
    duplicates = sorted(port for port in set(ports.values()) if list(ports.values()).count(port) > 1)
    if duplicates:
        raise safety.SafetyError(f"Harness ports must be distinct; duplicate values: {duplicates}")
    return ports


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
    ports = harness_ports_from_env(source)
    dev_bind_host = dev_bind_host_from_env(source)
    cfg = HarnessConfig(
        repo_root=repo_root.resolve(),
        instance=instance,
        provider_mode=provider_mode,
        layout=layout,
        firestore_port=ports["firestore"],
        auth_port=ports["auth"],
        backend_port=ports["backend"],
        desktop_backend_port=ports["desktop_backend"],
        redis_port=ports["redis"],
        typesense_port=ports["typesense"],
        llm_gateway_port=ports["llm_gateway"],
        dev_bind_host=dev_bind_host,
    )
    parsed = parse_secrets_file(cfg)
    if parsed.secrets.get("PROVIDER_MODE"):
        provider_mode = provider_mode_from_env({**dict(source), **parsed.secrets})
        cfg = HarnessConfig(
            repo_root=cfg.repo_root,
            instance=cfg.instance,
            provider_mode=provider_mode,
            layout=cfg.layout,
            firestore_port=cfg.firestore_port,
            auth_port=cfg.auth_port,
            backend_port=cfg.backend_port,
            desktop_backend_port=cfg.desktop_backend_port,
            redis_port=cfg.redis_port,
            typesense_port=cfg.typesense_port,
            llm_gateway_port=cfg.llm_gateway_port,
            dev_bind_host=cfg.dev_bind_host,
        )
    safety.validate_harness_runtime_config(
        project_id=cfg.project_id,
        database_id=cfg.database_id,
        emulator_hosts={"Firestore emulator": cfg.firestore_host, "Firebase Auth emulator": cfg.auth_host},
    )
    return cfg


def _harness_service_extra(cfg: HarnessConfig) -> dict[str, str]:
    # Offline harness uses direct/stub LLM paths. OMI_ENV_STAGE=offline is not a
    # gateway-local stage, so FEATURE_MODE=gateway would make gateway_client reject
    # startup while still advertising gateway routing.
    gateway_feature_mode = "off" if cfg.provider_mode == "offline" else "gateway"
    return {
        "OMI_HARNESS_INSTANCE": cfg.instance,
        "OMI_HARNESS_STATE_ROOT": str(cfg.layout.state_root),
        "FIRESTORE_EMULATOR_HOST": cfg.firestore_host,
        "FIREBASE_AUTH_EMULATOR_HOST": cfg.auth_host,
        "FIREBASE_AUTH_PROJECT_ID": cfg.project_id,
        "FIREBASE_PROJECT_ID": cfg.project_id,
        "FIRESTORE_DATABASE_ID": cfg.database_id,
        "FIREBASE_API_KEY": LOCAL_FIREBASE_API_KEY,
        "MEMORY_MODE": "read",
        "MEMORY_CANONICAL_CONSOLIDATION_ENABLED": "true",
        "REDIS_DB_HOST": cfg.redis_host,
        "REDIS_DB_PORT": str(cfg.redis_port),
        "REDIS_DB_PASSWORD": "",
        "ENVIRONMENT": "local-dev-harness",
        "ENCRYPTION_SECRET": "omi_local_dev_harness_32_byte_test_secret_not_prod",
        "ADMIN_KEY": "local-dev-admin-key-",
        "TYPESENSE_HOST": "127.0.0.1",
        "TYPESENSE_HOST_PORT": str(cfg.typesense_port),
        "TYPESENSE_API_KEY": LOCAL_TYPESENSE_API_KEY,
        "TYPESENSE_PROTOCOL": "http",
        "BASE_API_URL": cfg.backend_url,
        "API_BASE_URL": cfg.backend_url,
        "OMI_LLM_GATEWAY_URL": cfg.llm_gateway_url,
        "OMI_LLM_GATEWAY_SERVICE_TOKEN": cfg.llm_gateway_service_token,
        "OMI_LLM_GATEWAY_FEATURE_MODE": gateway_feature_mode,
    }


def child_env_for(cfg: HarnessConfig) -> dict[str, str]:
    extra = {
        **_harness_service_extra(cfg),
        "PORT": str(cfg.backend_port),
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
        "PORT": str(cfg.desktop_backend_port),
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
