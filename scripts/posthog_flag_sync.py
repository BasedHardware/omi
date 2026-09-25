#!/usr/bin/env python3
"""Read-only PostHog feature-flag diff against config/feature-flags.yaml.

Default mode prints a diff and never writes. ``--apply-missing-kills`` creates
only missing ``role: kill`` rows as active with one 0% rollout group, printing
every intended write before any request. It never modifies or deletes an
existing row and never creates enable/exposure/payload rows.

Needs ``POSTHOG_PERSONAL_API_KEY``; ``POSTHOG_HOST`` defaults to
https://us.posthog.com and ``POSTHOG_PROJECT_ID`` to 302298.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".github/scripts"))
sys.path.insert(0, str(ROOT / "scripts"))
from run_checks import _parse_yaml_subset
from feature_flag_registry import validate_registry

REGISTRY_PATH = "config/feature-flags.yaml"
DEFAULT_HOST = "https://us.posthog.com"
DEFAULT_PROJECT = "302298"
PAGE_LIMIT = 100

Json = dict[str, Any]
Transport = Callable[[urllib.request.Request], Json]


class SyncError(RuntimeError):
    """Input or API-contract failure; raised before any write and never carries secrets."""


def _default_transport(request: urllib.request.Request) -> Json:
    with urllib.request.urlopen(request) as response:
        return json.loads(response.read())


def _validate_target(host: str, project: str) -> None:
    parsed = urllib.parse.urlsplit(host.rstrip("/"))
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path
        or parsed.query
        or parsed.fragment
    ):
        raise SyncError("POSTHOG_HOST must be a bare HTTPS origin such as https://us.posthog.com")
    if not project.isdecimal():
        raise SyncError("POSTHOG_PROJECT_ID must be decimal digits")


def _flags_url(host: str, project: str, offset: int) -> str:
    return f"{host.rstrip('/')}/api/projects/{project}/feature_flags/?limit={PAGE_LIMIT}&offset={offset}"


def list_feature_flags(
    host: str,
    project: str,
    token: str,
    *,
    transport: Transport | None = None,
) -> list[Json]:
    """Fetch every feature-flag row, advancing offset; never follow `next` URLs."""
    _validate_target(host, project)
    transport = transport or _default_transport
    rows: list[Json] = []
    offset = 0
    while True:
        request = urllib.request.Request(
            _flags_url(host, project, offset),
            headers={"Authorization": f"Bearer {token}"},
        )
        payload = transport(request)
        page = payload.get("results") or []
        rows.extend(page)
        if payload.get("next") is None:
            return rows
        if not page:
            raise SyncError("feature_flags page returned empty results with a non-null next cursor")
        offset += len(page)


def is_armed_kill(row: Json) -> bool:
    """Active with exactly one filters.groups item: properties [] and 0% rollout."""
    if row.get("active") is not True:
        return False
    filters = row.get("filters")
    if not isinstance(filters, dict):
        return False
    groups = filters.get("groups")
    if not isinstance(groups, list) or len(groups) != 1:
        return False
    group = groups[0]
    if not isinstance(group, dict):
        return False
    return group.get("properties") == [] and group.get("rollout_percentage") == 0


def kill_row_body(key: str) -> Json:
    return {
        "key": key,
        "name": key,
        "active": True,
        "filters": {"groups": [{"properties": [], "rollout_percentage": 0}]},
    }


@dataclass
class SyncDiff:
    expected_missing: list[str] = field(default_factory=list)
    present_unregistered: list[str] = field(default_factory=list)
    present_decision_kill: list[str] = field(default_factory=list)
    malformed_kills: list[str] = field(default_factory=list)
    unarmed_or_unknown: list[str] = field(default_factory=list)
    retired_present: list[str] = field(default_factory=list)
    unexpected_present: list[str] = field(default_factory=list)

    def report(self) -> list[str]:
        lines = [f"expected but missing: {', '.join(self.expected_missing) or 'none'}"]
        lines.append(f"present unregistered: {', '.join(self.present_unregistered) or 'none'}")
        lines.append(f"present with decision kill: {', '.join(self.present_decision_kill) or 'none'}")
        lines.append(
            "kill rows not active-with-one-0%-group: " + (", ".join(self.malformed_kills) or "none")
        )
        lines.append(
            "kill rows unarmed or unknown (absent reads unknown): "
            + (", ".join(self.unarmed_or_unknown) or "none")
        )
        lines.append(
            "retired rows still present (delete candidates, read-only): "
            + (", ".join(self.retired_present) or "none")
        )
        lines.append(f"expected-absent yet present: {', '.join(self.unexpected_present) or 'none'}")
        return lines


def diff_rows(registry: dict[str, list[Json]], rows: list[Json]) -> SyncDiff:
    flags = {entry["key"]: entry for entry in registry.get("flags", [])}
    retired = {entry["key"] for entry in registry.get("retired", [])}
    present = {row.get("key"): row for row in rows if row.get("key")}

    diff = SyncDiff()
    for key, entry in sorted(flags.items()):
        posthog = entry.get("posthog") or {}
        if entry.get("kind") != "posthog":
            continue
        row = present.get(key)
        expected_kill = posthog.get("row") == "expected" and posthog.get("role") == "kill"
        if posthog.get("row") == "expected" and row is None:
            diff.expected_missing.append(key)
            if expected_kill:
                diff.unarmed_or_unknown.append(key)
        elif posthog.get("row") == "absent" and row is not None:
            diff.unexpected_present.append(key)
        if row is not None:
            if entry.get("decision") == "kill":
                diff.present_decision_kill.append(key)
            if expected_kill and not is_armed_kill(row):
                diff.malformed_kills.append(key)
                diff.unarmed_or_unknown.append(key)
    for key, row in sorted(present.items()):
        if key in retired:
            diff.retired_present.append(key)
        elif key not in flags:
            diff.present_unregistered.append(key)
    return diff


def missing_kill_keys(registry: dict[str, list[Json]], rows: list[Json]) -> list[str]:
    present = {row.get("key") for row in rows if row.get("key")}
    return sorted(
        entry["key"]
        for entry in registry.get("flags", [])
        if entry.get("kind") == "posthog"
        and (entry.get("posthog") or {}).get("row") == "expected"
        and (entry.get("posthog") or {}).get("role") == "kill"
        and entry["key"] not in present
    )


def create_kill_row(
    host: str,
    project: str,
    token: str,
    key: str,
    *,
    transport: Transport | None = None,
) -> Json:
    transport = transport or _default_transport
    _validate_target(host, project)
    request = urllib.request.Request(
        f"{host.rstrip('/')}/api/projects/{project}/feature_flags/",
        data=json.dumps(kill_row_body(key)).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    return transport(request)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument(
        "--apply-missing-kills",
        action="store_true",
        help="create only missing role:kill rows as active with one 0%% group; prints all writes first",
    )
    args = parser.parse_args()

    token = os.environ.get("POSTHOG_PERSONAL_API_KEY")
    if not token:
        print("posthog-flag-sync: POSTHOG_PERSONAL_API_KEY is required", file=sys.stderr)
        return 2
    host = os.environ.get("POSTHOG_HOST", DEFAULT_HOST)
    project = os.environ.get("POSTHOG_PROJECT_ID", DEFAULT_PROJECT)

    try:
        _validate_target(host, project)
    except SyncError as exc:
        print(f"posthog-flag-sync: {exc}", file=sys.stderr)
        return 2

    registry = _parse_yaml_subset(args.root.resolve() / REGISTRY_PATH)
    schema_errors = validate_registry(registry)
    if schema_errors:
        for error in schema_errors:
            print(f"posthog-flag-sync: registry: {error}", file=sys.stderr)
        return 2

    rows = list_feature_flags(host, project, token)
    diff = diff_rows(registry, rows)
    for line in diff.report():
        print(line)

    if not args.apply_missing_kills:
        return 0

    creates = missing_kill_keys(registry, rows)
    if not creates:
        print("no missing kill rows; nothing to write")
        return 0
    print("planned writes:")
    for key in creates:
        print(f"  POST {_flags_url(host, project, 0).split('?')[0]} {json.dumps(kill_row_body(key), sort_keys=True)}")
    for key in creates:
        create_kill_row(host, project, token, key)
        print(f"  created {key}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
