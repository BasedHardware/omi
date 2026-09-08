#!/usr/bin/env python3
"""Validate ChatGPT MCP OAuth review/submission config without printing secrets."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, cast

APPROVED_CLIENT_AUTH_METHODS = {
    "omi-chatgpt-prod": "none",
    "omi-mcp-public": "none",
}
REJECTED_CLIENT_IDS = {"omi"}
SECRET_FIELD_NAMES = {
    "access_token",
    "client_secret",
    "firebase_id_token",
    "id_token",
    "password",
    "refresh_token",
}


class ValidationError(Exception):
    pass


def _load_json(path: Path) -> Any:
    if not path.exists():
        raise ValidationError(f"{path}: file does not exist")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValidationError(f"{path}: invalid JSON: {exc}") from exc


def _find_dicts_with_key(value: Any, key: str) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    if isinstance(value, dict):
        data = cast(dict[str, Any], value)
        if key in data:
            matches.append(data)
        for child in data.values():
            matches.extend(_find_dicts_with_key(child, key))
    elif isinstance(value, list):
        items = cast(list[Any], value)
        for child in items:
            matches.extend(_find_dicts_with_key(child, key))
    return matches


def _find_secret_paths(value: Any, prefix: str = "$") -> list[str]:
    paths: list[str] = []
    if isinstance(value, dict):
        data = cast(dict[str, Any], value)
        for key, child in data.items():
            child_path = f"{prefix}.{key}"
            if key.lower() in SECRET_FIELD_NAMES and child not in (None, ""):
                paths.append(child_path)
            paths.extend(_find_secret_paths(child, child_path))
    elif isinstance(value, list):
        items = cast(list[Any], value)
        for index, child in enumerate(items):
            paths.extend(_find_secret_paths(child, f"{prefix}[{index}]"))
    return paths


def _extract_oauth_clients(payload: Any) -> list[dict[str, Any] | None]:
    clients: list[dict[str, Any] | None] = []
    for owner in _find_dicts_with_key(payload, "oauth_client"):
        oauth_client = owner.get("oauth_client")
        flow_requires_oauth = bool(
            owner.get("requires_oauth")
            or owner.get("oauth_required")
            or owner.get("authentication") == "oauth"
            or owner.get("auth_type") == "oauth"
            or owner.get("type") == "oauth"
            or owner.get("server_url")
        )
        if oauth_client is None and flow_requires_oauth:
            clients.append(None)
        elif isinstance(oauth_client, dict):
            clients.append(cast(dict[str, Any], oauth_client))
        elif oauth_client is not None:
            raise ValidationError("oauth_client must be an object when present")
    return clients


def validate_submission_config(payload: Any) -> list[str]:
    errors: list[str] = []
    oauth_clients = _extract_oauth_clients(payload)
    if not oauth_clients:
        errors.append("missing oauth_client object for MCP OAuth review config")

    for index, oauth_client in enumerate(oauth_clients, start=1):
        label = f"oauth_client[{index}]"
        if oauth_client is None:
            errors.append(f"{label} is null for a flow that requires OAuth")
            continue
        client_id = str(oauth_client.get("client_id") or "").strip()
        token_auth_method = str(oauth_client.get("token_endpoint_auth_method") or "").strip()
        if not client_id:
            errors.append(f"{label}.client_id is required")
        elif client_id in REJECTED_CLIENT_IDS:
            errors.append(f"{label}.client_id={client_id!r} is rejected; use omi-chatgpt-prod or omi-mcp-public")
        elif client_id not in APPROVED_CLIENT_AUTH_METHODS:
            errors.append(f"{label}.client_id={client_id!r} is not in the approved review client registry")
        expected_method = APPROVED_CLIENT_AUTH_METHODS.get(client_id)
        if not token_auth_method:
            errors.append(f"{label}.token_endpoint_auth_method is required")
        elif expected_method and token_auth_method != expected_method:
            errors.append(
                f"{label}.token_endpoint_auth_method={token_auth_method!r} does not match {client_id!r}: {expected_method!r}"
            )

    secret_paths = _find_secret_paths(payload)
    if secret_paths:
        errors.append("submission config contains raw secret fields: " + ", ".join(secret_paths))
    return errors


def _tool_names(value: Any) -> set[str]:
    names: set[str] = set()

    if isinstance(value, list):
        items = cast(list[Any], value)
        for tool in items:
            if isinstance(tool, dict):
                tool_data = cast(dict[str, Any], tool)
                if tool_data.get("name"):
                    names.add(str(tool_data["name"]))

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            node_data = cast(dict[str, Any], node)
            tools = node_data.get("tools")
            if isinstance(tools, list):
                tools_list = cast(list[Any], tools)
                for tool in tools_list:
                    if isinstance(tool, dict):
                        tool_data = cast(dict[str, Any], tool)
                        if tool_data.get("name"):
                            names.add(str(tool_data["name"]))
            for child in node_data.values():
                visit(child)
        elif isinstance(node, list):
            node_items = cast(list[Any], node)
            for child in node_items:
                visit(child)

    visit(value)
    return names


def validate_tool_metadata(submission_payload: Any, live_tools_payload: Any) -> list[str]:
    exported = _tool_names(submission_payload)
    live = _tool_names(live_tools_payload)
    errors: list[str] = []
    if not exported:
        errors.append("submission config does not include tool metadata to compare")
    if not live:
        errors.append("live tools/list payload does not include tools")
    missing = sorted(live - exported)
    stale = sorted(exported - live)
    if missing:
        errors.append("submission tool metadata is missing live tools: " + ", ".join(missing))
    if stale:
        errors.append("submission tool metadata includes stale tools: " + ", ".join(stale))
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("submission_json", type=Path, help="Generated ChatGPT review/submission JSON")
    parser.add_argument("--live-tools-json", type=Path, help="Captured MCP tools/list JSON for the selected scopes")
    args = parser.parse_args(argv)

    try:
        submission_payload = _load_json(args.submission_json)
        errors = validate_submission_config(submission_payload)
        if args.live_tools_json:
            errors.extend(validate_tool_metadata(submission_payload, _load_json(args.live_tools_json)))
    except ValidationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("MCP OAuth review config OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
