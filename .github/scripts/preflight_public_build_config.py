#!/usr/bin/env python3
"""Resolve the reviewed public-build source from GitHub before a deploy builds."""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Iterable

from check_public_build_contract import (
    ROOT,
    Contract,
    Target,
    build_args,
    load_contract,
    parse_values_document,
    validate_values,
)


API_ROOT = "https://api.github.com"


class RemoteConfigMissing(RuntimeError):
    """The selected commit has no reviewed public-build configuration."""


class RemoteConfigUnavailable(RuntimeError):
    """The workflow token cannot read the authoritative GitHub source."""


def request_remote_values(
    *, repository: str, ref: str, config_path: str, token: str
) -> dict[str, dict[str, str]]:
    encoded_path = "/".join(urllib.parse.quote(segment, safe="") for segment in config_path.split("/"))
    encoded_ref = urllib.parse.quote(ref, safe="")
    request = urllib.request.Request(
        f"{API_ROOT}/repos/{repository}/contents/{encoded_path}?ref={encoded_ref}",
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
        if exc.code == 404:
            raise RemoteConfigMissing("reviewed public-build configuration is missing at the deployed ref") from exc
        raise RemoteConfigUnavailable(f"reviewed public-build configuration is unavailable (HTTP {exc.code})") from exc
    except urllib.error.URLError as exc:
        raise RemoteConfigUnavailable("reviewed public-build configuration is unavailable") from exc
    if (
        not isinstance(payload, dict)
        or payload.get("encoding") != "base64"
        or not isinstance(payload.get("content"), str)
    ):
        raise RemoteConfigUnavailable("reviewed public-build configuration metadata is invalid")
    try:
        content = base64.b64decode("".join(payload["content"].split()), validate=True).decode("utf-8")
        return parse_values_document(json.loads(content), source="remote reviewed public-build configuration")
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RemoteConfigUnavailable("reviewed public-build configuration content is invalid") from exc


def select_targets(contract: Contract, names: Iterable[str] | None, all_targets: bool) -> list[Target]:
    selected_names = sorted(contract.targets) if all_targets else list(names or [])
    if not selected_names:
        raise ValueError("specify --target or --all")
    unknown = sorted(set(selected_names) - contract.targets.keys())
    if unknown:
        raise ValueError(f"unknown public-build targets: {', '.join(unknown)}")
    return [contract.targets[name] for name in selected_names]


def write_github_output(path: Path, *, target: Target, values: dict[str, str]) -> None:
    arguments = build_args(target, values)
    with path.open("a", encoding="utf-8") as handle:
        handle.write("build_args<<OMI_PUBLIC_BUILD_ARGS\n")
        handle.write(f"{arguments}\n")
        handle.write("OMI_PUBLIC_BUILD_ARGS\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", required=True)
    parser.add_argument("--target", action="append")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY"))
    parser.add_argument("--ref", default=os.environ.get("GITHUB_SHA"))
    parser.add_argument("--token", default=os.environ.get("GITHUB_TOKEN"))
    parser.add_argument("--contract", type=Path, default=ROOT / "config" / "public-build-contract.json")
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args(argv)
    if args.github_output and args.all:
        print("public-build configuration preflight failed: --github-output requires one --target", file=sys.stderr)
        return 1
    if not args.repository or not args.ref or not args.token:
        print(
            "public-build configuration preflight failed: repository, ref, and read-only GitHub token are required",
            file=sys.stderr,
        )
        return 1
    try:
        contract = load_contract(args.contract)
        targets = select_targets(contract, args.target, args.all)
        values = request_remote_values(
            repository=args.repository,
            ref=args.ref,
            config_path=contract.config_path,
            token=args.token,
        )
        errors = validate_values(contract, values, targets, args.environment)
        if errors:
            raise ValueError("; ".join(errors))
        if args.github_output:
            write_github_output(args.github_output, target=targets[0], values=values[args.environment])
    except (OSError, ValueError, RemoteConfigMissing, RemoteConfigUnavailable, json.JSONDecodeError) as exc:
        print(f"public-build configuration preflight failed: {exc}", file=sys.stderr)
        return 1
    print(
        "public-build configuration preflight passed: "
        f"source=reviewed-ref, environment={args.environment}, targets={len(targets)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
