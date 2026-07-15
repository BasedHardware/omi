#!/usr/bin/env python3
"""Validate prod MCP OAuth env wiring for backend-listen and api.omi.me deploys."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
RUNTIME_ENV = BACKEND / "deploy" / "runtime_env.yaml"
LISTEN_VALUES = BACKEND / "charts" / "backend-listen" / "prod_omi_backend_listen_values.yaml"
SECRETS_VALUES = BACKEND / "charts" / "backend-secrets" / "prod_omi_backend_secrets_values.yaml"

MCP_OAUTH_CONFIG_KEYS = (
    "MCP_AUTHORIZATION_SERVER_URL",
    "MCP_RESOURCE_URL",
    "MCP_OAUTH_CHATGPT_CLIENT_ID",
    "MCP_OAUTH_CHATGPT_REDIRECT_URIS",
    "MCP_OAUTH_PUBLIC_CLIENT_ID",
    "MCP_OAUTH_PUBLIC_REDIRECT_URIS",
    "MCP_OAUTH_CLAUDE_CLIENT_ID",
    "MCP_OAUTH_CLAUDE_CLIENT_NAME",
    "MCP_OAUTH_CLAUDE_REDIRECT_URIS",
)

MCP_OAUTH_SECRET_KEYS = (
    "MCP_OAUTH_CHATGPT_CLIENT_SECRET",
    "MCP_OAUTH_CLIENTS_JSON",
)

MCP_OAUTH_CLAUDE_CONFIG_KEYS = (
    "MCP_OAUTH_CLAUDE_CLIENT_ID",
    "MCP_OAUTH_CLAUDE_CLIENT_NAME",
    "MCP_OAUTH_CLAUDE_REDIRECT_URIS",
)


def _load_yaml(path: Path) -> dict[str, Any]:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    return loaded if isinstance(loaded, dict) else {}


def _env_names_from_listen_values(values: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    for entry in values.get("env", []) or []:
        if isinstance(entry, dict) and entry.get("name"):
            names.add(str(entry["name"]))
    return names


def _config_map_names_from_listen_values(values: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    for entry in values.get("envFrom", []) or []:
        if not isinstance(entry, dict):
            continue
        config_map = entry.get("configMapRef")
        if isinstance(config_map, dict) and config_map.get("name"):
            names.add(str(config_map["name"]))
    return names


def _secret_keys_from_secrets_values(values: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    external_secret = values.get("externalSecret", {})
    entries = external_secret.get("secretKeys", []) if isinstance(external_secret, dict) else []
    for entry in entries or []:
        if isinstance(entry, dict) and entry.get("secretKey"):
            keys.add(str(entry["secretKey"]))
    return keys


def _prod_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    environments = manifest.get("environments", {})
    prod = environments.get("prod", {}) if isinstance(environments, dict) else {}
    return prod if isinstance(prod, dict) else {}


def _runtime_env_binding(manifest: dict[str, Any], key: str) -> dict[str, Any]:
    gke = _prod_manifest(manifest).get("gke", {}).get("backend-listen", {})
    env = gke.get("env", {}) if isinstance(gke, dict) else {}
    binding = env.get(key, {}) if isinstance(env, dict) else {}
    return binding if isinstance(binding, dict) else {}


def _cloud_run_env_binding(manifest: dict[str, Any], service_name: str, key: str) -> dict[str, Any]:
    cloud_run = _prod_manifest(manifest).get("cloud_run", {})
    services = cloud_run.get("services", {}) if isinstance(cloud_run, dict) else {}
    service = services.get(service_name, {}) if isinstance(services, dict) else {}
    env = service.get("env", {}) if isinstance(service, dict) else {}
    binding = env.get(key, {}) if isinstance(env, dict) else {}
    return binding if isinstance(binding, dict) else {}


def _cloud_run_secret_keys(manifest: dict[str, Any], service_name: str) -> set[str]:
    cloud_run = _prod_manifest(manifest).get("cloud_run", {})
    services = cloud_run.get("services", {}) if isinstance(cloud_run, dict) else {}
    service = services.get(service_name, {}) if isinstance(services, dict) else {}
    secrets = service.get("secrets", {}) if isinstance(service, dict) else {}
    return set(secrets.keys()) if isinstance(secrets, dict) else set()


def _cloud_run_secret_binding(manifest: dict[str, Any], service_name: str, key: str) -> dict[str, Any]:
    cloud_run = _prod_manifest(manifest).get("cloud_run", {})
    services = cloud_run.get("services", {}) if isinstance(cloud_run, dict) else {}
    service = services.get(service_name, {}) if isinstance(services, dict) else {}
    secrets = service.get("secrets", {}) if isinstance(service, dict) else {}
    binding = secrets.get(key, {}) if isinstance(secrets, dict) else {}
    return binding if isinstance(binding, dict) else {}


def _csv_values(raw: object) -> list[str]:
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    if raw is None:
        return []
    return [item.strip() for item in str(raw).split(",") if item.strip()]


def _clients_json_entries(raw_clients: str) -> list[dict[str, Any]]:
    parsed = json.loads(raw_clients)
    if isinstance(parsed, dict):
        return [
            {"client_id": str(client_id), **config} for client_id, config in parsed.items() if isinstance(config, dict)
        ]
    if isinstance(parsed, list):
        return [entry for entry in parsed if isinstance(entry, dict)]
    return []


def _validate_live_env_consistency() -> list[str]:
    """Cross-check actual env values when the deploy/preflight environment provides them.

    The checked-in manifest can only verify secret bindings. When this script runs
    with real env values, ensure the aggregate JSON and Claude-specific fallback
    vars describe the same Claude OAuth client, so get_client() cannot silently
    prefer a stale JSON registration over the per-client deploy contract.
    """

    raw_clients = os.getenv("MCP_OAUTH_CLIENTS_JSON", "")
    if not raw_clients:
        return []

    errors: list[str] = []
    claude_client_id = os.getenv("MCP_OAUTH_CLAUDE_CLIENT_ID", "").strip()
    claude_client_name = os.getenv("MCP_OAUTH_CLAUDE_CLIENT_NAME", "").strip()
    claude_redirect_uris = _csv_values(os.getenv("MCP_OAUTH_CLAUDE_REDIRECT_URIS", ""))
    try:
        entries = _clients_json_entries(raw_clients)
    except json.JSONDecodeError as exc:
        return [f"MCP_OAUTH_CLIENTS_JSON is not valid JSON: {exc}"]

    if not claude_client_id:
        return []

    matching = next((entry for entry in entries if str(entry.get("client_id", "")).strip() == claude_client_id), None)
    if matching is None:
        errors.append("MCP_OAUTH_CLIENTS_JSON missing Claude client from MCP_OAUTH_CLAUDE_CLIENT_ID")
        return errors

    json_name = str(matching.get("name", "")).strip()
    if claude_client_name and json_name and json_name != claude_client_name:
        errors.append("MCP_OAUTH_CLIENTS_JSON Claude name differs from MCP_OAUTH_CLAUDE_CLIENT_NAME")

    json_redirect_uris = _csv_values(matching.get("allowed_redirect_uris") or matching.get("redirect_uris"))
    if claude_redirect_uris and json_redirect_uris and set(json_redirect_uris) != set(claude_redirect_uris):
        errors.append("MCP_OAUTH_CLIENTS_JSON Claude redirect URIs differ from MCP_OAUTH_CLAUDE_REDIRECT_URIS")

    return errors


def validate_mcp_oauth_deploy_contract() -> list[str]:
    errors: list[str] = []
    manifest = _load_yaml(RUNTIME_ENV)
    listen_values = _load_yaml(LISTEN_VALUES)
    secrets_values = _load_yaml(SECRETS_VALUES)

    listen_keys = _env_names_from_listen_values(listen_values)
    listen_config_maps = _config_map_names_from_listen_values(listen_values)
    secret_keys = _secret_keys_from_secrets_values(secrets_values)

    for key in MCP_OAUTH_CONFIG_KEYS:
        expected_config_map = "prod-omi-backend-config"
        if expected_config_map not in listen_config_maps:
            errors.append(f"backend-listen prod values missing ConfigMap {expected_config_map}")
            break
        binding = _runtime_env_binding(manifest, key)
        config_map = binding.get("config_map") if isinstance(binding, dict) else None
        if (
            not isinstance(config_map, dict)
            or config_map.get("name") != expected_config_map
            or config_map.get("key") != key
        ):
            errors.append(f"runtime_env.yaml prod gke/backend-listen must source {key} from ConfigMap")

    for key in MCP_OAUTH_SECRET_KEYS:
        if key not in listen_keys:
            errors.append(f"backend-listen prod values missing secret env {key}")
        if key not in secret_keys:
            errors.append(f"backend-secrets prod values missing secretKey {key}")

    for key in MCP_OAUTH_CLAUDE_CONFIG_KEYS:
        binding = _cloud_run_env_binding(manifest, "backend", key)
        if binding.get("env_var") != key:
            errors.append(f"runtime_env.yaml prod cloud_run/backend must render {key} from its GitHub variable")

    if "MCP_OAUTH_CLIENTS_JSON" not in _cloud_run_secret_keys(manifest, "backend"):
        errors.append("runtime_env.yaml prod cloud_run/backend missing secret MCP_OAUTH_CLIENTS_JSON")
    binding = _cloud_run_secret_binding(manifest, "backend", "MCP_OAUTH_CLIENTS_JSON")
    if binding and binding.get("secret") != "MCP_OAUTH_CLIENTS_JSON":
        errors.append("runtime_env.yaml prod cloud_run/backend must bind Secret Manager MCP_OAUTH_CLIENTS_JSON")

    errors.extend(_validate_live_env_consistency())
    return errors


def main() -> int:
    errors = validate_mcp_oauth_deploy_contract()
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
