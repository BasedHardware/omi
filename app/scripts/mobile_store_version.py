#!/usr/bin/env python3
"""Parse mobile store version lookups without conflating empty and failed reads."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import re
import sys
from typing import Any, Mapping

from mobile_release_identity import MAX_BUILD_NUMBER

VERSION_RE = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
BUILD_RE = re.compile(r"^[1-9][0-9]*$")
PROVIDERS = frozenset({"testflight", "app_store", "play"})


class StoreLookupError(ValueError):
    """A store command failed or returned an invalid successful response."""


@dataclass(frozen=True)
class StoreSnapshot:
    provider: str
    status: str
    version: str | None = None
    build_number: int | None = None

    @classmethod
    def empty(cls, provider: str) -> "StoreSnapshot":
        return cls(provider=provider, status="empty")

    @classmethod
    def available(cls, provider: str, version: str | None, build_number: int) -> "StoreSnapshot":
        return cls(provider=provider, status="available", version=version, build_number=build_number)


@dataclass(frozen=True)
class ReleasePlan:
    platform: str
    version: str
    build_number: int


def _require_build(value: object, label: str) -> int:
    if isinstance(value, bool):
        raise StoreLookupError(f"{label} must be a positive integer")
    if isinstance(value, int):
        build = value
    elif isinstance(value, str) and BUILD_RE.fullmatch(value):
        build = int(value)
    else:
        raise StoreLookupError(f"{label} must be a positive integer")
    if build <= 0:
        raise StoreLookupError(f"{label} must be a positive integer")
    if build > MAX_BUILD_NUMBER:
        raise StoreLookupError(f"{label} must be <= {MAX_BUILD_NUMBER}")
    return build


def _require_version(value: object, label: str) -> str:
    if not isinstance(value, str) or not VERSION_RE.fullmatch(value):
        raise StoreLookupError(f"{label} must be a strict major.minor.patch version")
    return value


def _require_success(returncode: int, provider: str) -> None:
    if returncode != 0:
        raise StoreLookupError(f"{provider} lookup failed with exit code {returncode}")


def parse_app_store_output(raw: str, *, provider: str, returncode: int = 0) -> StoreSnapshot:
    """Parse app-store-connect JSON output.

    Blank output, JSON ``null``, and an empty list are explicit empty-history
    results.  Every other malformed or partial response is an error.
    """
    if provider not in {"testflight", "app_store"}:
        raise StoreLookupError("app-store provider must be testflight or app_store")
    _require_success(returncode, provider)
    if not raw.strip():
        return StoreSnapshot.empty(provider)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        raise StoreLookupError(f"{provider} returned invalid JSON") from error
    if payload is None or payload == []:
        return StoreSnapshot.empty(provider)
    if not isinstance(payload, dict):
        raise StoreLookupError(f"{provider} returned a non-object result")
    # Codemagic's app-store lookup includes an opaque buildId alongside the
    # version/build number. It is provider metadata, not a second version
    # source, so accept it while keeping the numeric fields strict.
    if set(payload) - {"version", "buildNumber", "buildId"} or "version" not in payload or "buildNumber" not in payload:
        raise StoreLookupError(f"{provider} returned an incomplete result")
    version = _require_version(payload["version"], f"{provider}.version")
    build = _require_build(payload["buildNumber"], f"{provider}.buildNumber")
    return StoreSnapshot.available(provider, version, build)


def parse_play_output(raw: str, *, returncode: int = 0) -> StoreSnapshot:
    """Parse google-play's plain latest-build output."""
    provider = "play"
    _require_success(returncode, provider)
    value = raw.strip()
    if not value:
        return StoreSnapshot.empty(provider)
    return StoreSnapshot.available(provider, None, _require_build(value, "play.build_number"))


def _parse_pubspec_version(value: str) -> tuple[str, int]:
    try:
        version, build = value.split("+", 1)
    except ValueError as error:
        raise StoreLookupError("pubspec version must use version+build form") from error
    return _require_version(version, "pubspec.version"), _require_build(build, "pubspec.build_number")


def _bump_patch(version: str) -> str:
    major, minor, patch = (int(part) for part in version.split("."))
    return f"{major}.{minor}.{patch + 1}"


def resolve_next_release(
    platform: str,
    pubspec_version: str,
    snapshots: Mapping[str, StoreSnapshot],
) -> ReleasePlan:
    """Choose the next release from already-parsed, successful store reads."""
    if platform not in {"ios", "android"}:
        raise StoreLookupError("platform must be exactly ios or android")
    expected = frozenset({"testflight", "app_store"}) if platform == "ios" else PROVIDERS
    if set(snapshots) != expected:
        missing = sorted(expected - set(snapshots))
        extra = sorted(set(snapshots) - expected)
        detail = []
        if missing:
            detail.append("missing " + ", ".join(missing))
        if extra:
            detail.append("unknown " + ", ".join(extra))
        raise StoreLookupError("store snapshot set is invalid: " + "; ".join(detail))
    version, pubspec_build = _parse_pubspec_version(pubspec_version)

    available = [snapshot for snapshot in snapshots.values() if snapshot.status == "available"]
    invalid_status = [snapshot.provider for snapshot in snapshots.values() if snapshot.status not in {"empty", "available"}]
    if invalid_status:
        raise StoreLookupError("invalid store status: " + ", ".join(sorted(invalid_status)))
    if not available:
        return ReleasePlan(platform=platform, version=version, build_number=pubspec_build)

    builds = [snapshot.build_number for snapshot in available]
    assert all(build is not None for build in builds)
    # Once a store has history, it is authoritative. The pubspec build only
    # seeds a genuinely empty history and must not force a jump over the store.
    next_build = max(build for build in builds if build is not None) + 1
    if next_build > MAX_BUILD_NUMBER:
        raise StoreLookupError(f"next build number must be <= {MAX_BUILD_NUMBER}")
    testflight = snapshots["testflight"]
    app_store = snapshots["app_store"]
    if testflight.status == "available" and app_store.status == "available":
        assert testflight.version is not None and app_store.version is not None
        next_version = testflight.version if tuple(map(int, testflight.version.split("."))) > tuple(map(int, app_store.version.split("."))) else _bump_patch(app_store.version)
    elif testflight.status == "available":
        assert testflight.version is not None
        next_version = testflight.version
    elif app_store.status == "available":
        assert app_store.version is not None
        next_version = _bump_patch(app_store.version)
    else:
        next_version = version
    return ReleasePlan(platform=platform, version=next_version, build_number=next_build)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", required=True, choices=("ios", "android"))
    parser.add_argument("--pubspec-version", required=True)
    parser.add_argument("--input", required=True, help="JSON file or - on stdin")
    return parser


def _read_input(path: str) -> dict[str, Any]:
    raw = Path(path).read_text(encoding="utf-8") if path != "-" else sys.stdin.read()
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as error:
        raise StoreLookupError("input must be valid JSON") from error
    if not isinstance(value, dict):
        raise StoreLookupError("input must be a JSON object")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        inputs = _read_input(args.input)
        snapshots: dict[str, StoreSnapshot] = {
            "testflight": parse_app_store_output(
                str(inputs["testflight"]["stdout"]),
                provider="testflight",
                returncode=int(inputs["testflight"].get("exit_code", 0)),
            ),
            "app_store": parse_app_store_output(
                str(inputs["app_store"]["stdout"]),
                provider="app_store",
                returncode=int(inputs["app_store"].get("exit_code", 0)),
            ),
        }
        if args.platform == "android":
            snapshots["play"] = parse_play_output(
                str(inputs["play"]["stdout"]),
                returncode=int(inputs["play"].get("exit_code", 0)),
            )
        plan = resolve_next_release(args.platform, args.pubspec_version, snapshots)
    except (KeyError, TypeError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps({"platform": plan.platform, "version": plan.version, "build_number": plan.build_number}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
