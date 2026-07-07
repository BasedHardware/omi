#!/usr/bin/env python3
"""Validate prod MCP OAuth env wiring for backend-listen deploys."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
RUNTIME_ENV = BACKEND / "deploy" / "runtime_env.yaml"
LISTEN_VALUES = BACKEND / "charts" / "backend-listen" / "prod_omi_backend_listen_values.yaml"
SECRETS_VALUES = BACKEND / "charts" / "backend-secrets" / "prod_omi_backend_secrets_values.yaml"

REQUIRED_MCP_OAUTH_KEYS = (
    "MCP_AUTHORIZATION_SERVER_URL",
    "MCP_RESOURCE_URL",
    "MCP_OAUTH_CHATGPT_CLIENT_ID",
    "MCP_OAUTH_CHATGPT_CLIENT_SECRET",
    "MCP_OAUTH_CHATGPT_REDIRECT_URIS",
    "MCP_OAUTH_PUBLIC_CLIENT_ID",
    "MCP_OAUTH_PUBLIC_REDIRECT_URIS",
    "MCP_OAUTH_CLAUDE_CLIENT_ID",
    "MCP_OAUTH_CLAUDE_CLIENT_NAME",
    "MCP_OAUTH_CLAUDE_REDIRECT_URIS",
    "MCP_OAUTH_CLIENTS_JSON",
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


def _secret_keys_from_secrets_values(values: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    external_secret = values.get("externalSecret", {})
    entries = external_secret.get("secretKeys", []) if isinstance(external_secret, dict) else []
    for entry in entries or []:
        if isinstance(entry, dict) and entry.get("secretKey"):
            keys.add(str(entry["secretKey"]))
    return keys


def _runtime_env_keys(manifest: dict[str, Any]) -> set[str]:
    prod = manifest.get("environments", {}).get("prod", {})
    gke = prod.get("gke", {}).get("backend-listen", {})
    env = gke.get("env", {})
    return set(env.keys()) if isinstance(env, dict) else set()


def validate_mcp_oauth_deploy_contract() -> list[str]:
    errors: list[str] = []
    manifest = _load_yaml(RUNTIME_ENV)
    listen_values = _load_yaml(LISTEN_VALUES)
    secrets_values = _load_yaml(SECRETS_VALUES)

    runtime_keys = _runtime_env_keys(manifest)
    listen_keys = _env_names_from_listen_values(listen_values)
    secret_keys = _secret_keys_from_secrets_values(secrets_values)

    for key in REQUIRED_MCP_OAUTH_KEYS:
        if key not in listen_keys:
            errors.append(f"backend-listen prod values missing env {key}")
        if key not in secret_keys:
            errors.append(f"backend-secrets prod values missing secretKey {key}")

    for key in (
        "MCP_OAUTH_CLAUDE_CLIENT_ID",
        "MCP_OAUTH_CLAUDE_CLIENT_NAME",
        "MCP_OAUTH_CLAUDE_REDIRECT_URIS",
        "MCP_OAUTH_CLIENTS_JSON",
    ):
        if key not in runtime_keys:
            errors.append(f"runtime_env.yaml prod gke/backend-listen missing env {key}")

    return errors


def main() -> int:
    errors = validate_mcp_oauth_deploy_contract()
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
