#!/usr/bin/env python3
"""Validate the project Cursor MCP configuration without registry access."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / ".cursor" / "mcp.json"

BANNED_PACKAGE_IDENTITIES = {
    "@modelcontextprotocol/server-browser",
    "@modelcontextprotocol/server-figma",
    "@modelcontextprotocol/server-github",
    "@modelcontextprotocol/server-notion",
}

# Which servers the config must define. Deliberately not a contract on *how* each
# one connects: 8b5715527b chose local npx packages over hosted endpoints, and this
# check exists to keep whatever is configured runnable and credential-safe, not to
# relitigate that choice.
REQUIRED_SERVERS = ("notion", "figma", "browser")
EXACT_NPM_SPEC = re.compile(
    r"^(?:@[^/@]+/[^/@]+|[^/@][^@]*)@\d+\.\d+\.\d+" r"(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$"
)
SENSITIVE_NAME = re.compile(r"(?:AUTHORIZATION|KEY|SECRET|TOKEN)", re.IGNORECASE)
ENV_REFERENCE = re.compile(r"^(?:Bearer )?\$\{env:[A-Za-z_][A-Za-z0-9_]*\}$")


def _npx_package(args: Any) -> str | None:
    if not isinstance(args, list) or not all(isinstance(arg, str) for arg in args):
        return None
    return next((arg for arg in args if not arg.startswith("-")), None)


def _credential_errors(server_name: str, field: str, values: Any) -> list[str]:
    if values is None:
        return []
    if not isinstance(values, dict):
        return [f"{server_name}.{field} must be an object"]

    errors: list[str] = []
    for key, value in values.items():
        if SENSITIVE_NAME.search(str(key)) and (not isinstance(value, str) or not ENV_REFERENCE.fullmatch(value)):
            errors.append(f"{server_name}.{field}.{key} must use a ${{env:NAME}} reference, not a committed value")
    return errors


def config_errors(config: Any) -> list[str]:
    if not isinstance(config, dict):
        return ["Cursor MCP config must be a JSON object"]

    servers = config.get("mcpServers")
    if not isinstance(servers, dict):
        return ["Cursor MCP config must define an mcpServers object"]

    errors: list[str] = []
    for required in REQUIRED_SERVERS:
        if required not in servers:
            errors.append(f"missing required MCP server: {required}")

    for name, server in servers.items():
        if not isinstance(server, dict):
            errors.append(f"{name} must be an object")
            continue

        has_command = "command" in server
        has_url = "url" in server
        if has_command == has_url:
            errors.append(f"{name} must define exactly one transport: command or url")

        if has_url:
            url = server.get("url")
            if not isinstance(url, str) or urlparse(url).scheme != "https":
                errors.append(f"{name}.url must use HTTPS")

        package = _npx_package(server.get("args")) if server.get("command") == "npx" else None
        if package in BANNED_PACKAGE_IDENTITIES:
            errors.append(f"{name} uses unsupported MCP package {package}")
        if server.get("command") == "npx" and (package is None or EXACT_NPM_SPEC.fullmatch(package) is None):
            errors.append(f"{name} must pin its npx package to an exact semantic version")

        errors.extend(_credential_errors(name, "env", server.get("env")))
        errors.extend(_credential_errors(name, "headers", server.get("headers")))

    browser = servers.get("browser")
    if isinstance(browser, dict):
        if browser.get("env"):
            errors.append("browser MCP must not receive repository credentials")

    return errors


def load_config(path: Path = CONFIG_PATH) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read {path}: {exc}") from exc


def main() -> int:
    try:
        config = load_config()
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 1

    errors = config_errors(config)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print("Cursor MCP config contract passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
