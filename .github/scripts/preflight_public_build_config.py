#!/usr/bin/env python3
"""Fail closed when GitHub's effective public build configuration drifts."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any, Iterable

from check_public_build_contract import ROOT, Target, load_contract


API_ROOT = "https://api.github.com"
SCOPES_IN_PRECEDENCE = ("environment", "repository", "organization")
JsonRequest = Callable[[str, str], dict[str, Any]]


def request_json(url: str, token: str) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "omi-public-build-preflight",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:  # noqa: S310 - fixed GitHub API root
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"GitHub metadata request failed with HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError("GitHub metadata request failed") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("GitHub metadata response was not an object")
    return payload


def list_variables(url: str, token: str, requester: JsonRequest = request_json) -> dict[str, str]:
    variables: dict[str, str] = {}
    page = 1
    total_count: int | None = None
    while total_count is None or len(variables) < total_count:
        separator = "&" if "?" in url else "?"
        payload = requester(f"{url}{separator}per_page=100&page={page}", token)
        raw_variables = payload.get("variables")
        total_count = payload.get("total_count")
        if not isinstance(raw_variables, list) or not isinstance(total_count, int):
            raise RuntimeError("GitHub metadata response did not contain variables")
        for item in raw_variables:
            if (
                not isinstance(item, dict)
                or not isinstance(item.get("name"), str)
                or not isinstance(item.get("value"), str)
            ):
                raise RuntimeError("GitHub metadata response contained an invalid variable")
            variables[item["name"]] = item["value"]
        if not raw_variables and len(variables) < total_count:
            raise RuntimeError("GitHub metadata pagination ended unexpectedly")
        page += 1
    return variables


def inventories(
    repository: str, environment: str, token: str, requester: JsonRequest = request_json
) -> dict[str, dict[str, str]]:
    encoded_environment = urllib.parse.quote(environment, safe="")
    base = f"{API_ROOT}/repos/{repository}"
    return {
        "organization": list_variables(f"{base}/actions/organization-variables", token, requester),
        "repository": list_variables(f"{base}/actions/variables", token, requester),
        "environment": list_variables(f"{base}/environments/{encoded_environment}/variables", token, requester),
    }


def validate_target(target: Target, scope_variables: dict[str, dict[str, str]]) -> list[str]:
    errors: list[str] = []
    for item in target.inputs:
        resolved_scope = next((scope for scope in SCOPES_IN_PRECEDENCE if item.name in scope_variables[scope]), None)
        if resolved_scope is None:
            errors.append(f"{target.name}: required {item.name} is missing")
            continue
        if resolved_scope != item.scope:
            errors.append(f"{target.name}: {item.name} resolves from {resolved_scope}, expected {item.scope}")
            continue
        if not scope_variables[resolved_scope][item.name].strip():
            errors.append(f"{target.name}: required {item.name} is empty in {resolved_scope}")
    return errors


def select_targets(targets: dict[str, Target], names: Iterable[str] | None, all_targets: bool) -> list[Target]:
    selected_names = sorted(targets) if all_targets else list(names or [])
    if not selected_names:
        raise ValueError("specify --target or --all")
    unknown = sorted(set(selected_names) - targets.keys())
    if unknown:
        raise ValueError(f"unknown public-build targets: {', '.join(unknown)}")
    return [targets[name] for name in selected_names]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", required=True)
    parser.add_argument("--target", action="append")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY"))
    parser.add_argument("--token", default=os.environ.get("GITHUB_TOKEN"))
    parser.add_argument("--contract", type=Path, default=ROOT / "config" / "public-build-contract.json")
    args = parser.parse_args()

    if not args.repository or not args.token:
        print("public-build configuration preflight failed: repository and GitHub token are required", file=sys.stderr)
        return 1
    try:
        targets = select_targets(load_contract(args.contract), args.target, args.all)
        scope_variables = inventories(args.repository, args.environment, args.token)
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"public-build configuration preflight failed: {exc}", file=sys.stderr)
        return 1

    errors = [error for target in targets for error in validate_target(target, scope_variables)]
    if errors:
        print("public-build configuration preflight failed:", file=sys.stderr)
        print("\n".join(f"- {error}" for error in errors), file=sys.stderr)
        return 1
    print(f"public-build configuration preflight passed: environment={args.environment}, targets={len(targets)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
