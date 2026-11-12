#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from feature_flag_parser_defaults import parser_defaults
from feature_flag_registry import (
    REVIEW_GRACE_DAYS,
    RAMP_REQUIRED_FROM,
    ROOT,
    _ramp_applies_to,
    duplicate_declaration_sources,
    due_dates,
    extract_action_declarations,
    extract_code_reads,
    extract_deploy_declarations,
    load_registry,
    ramp_due,
    validate_registry,
)

AS_OF = re.compile(r"<!-- feature-flag-registry as-of: (\d{4}-\d{2}-\d{2}) -->")

# Only new rollout rows are gated; existing rows still contribute to the count.
MAX_UNRAMPED_PER_OWNER = 5
ACCOUNT_OWNERS = {"dazheng"}
# Keys use owner_tokens(); exceptions require an ISO expires date and reason.
OWNER_BACKLOG_EXCEPTIONS: dict[str, dict[str, str]] = {}


def normalize_owner(owner: str) -> str:
    """Ignore parenthetical annotations, case and whitespace runs."""
    while re.search(r"\([^()]*\)", owner):
        owner = re.sub(r"\([^()]*\)", " ", owner)
    return " ".join(owner.lower().split())


def owner_tokens(owner: str) -> tuple[str, ...]:
    """Split shared owners into distinct normalized lanes, preserving multiword names."""
    return tuple(dict.fromkeys(
        token.strip()
        for token in re.split(r"[/,&+|]|\s+and\s+", normalize_owner(owner))
        if token.strip()
    ))


def owner_backlog(registry: dict[str, Any], as_of: date | None = None) -> Counter[str]:
    """Count each debt row once per distinct normalized lane token, including shared owners."""
    current_date = as_of or datetime.now(timezone.utc).date()
    return Counter(
        owner
        for entry in registry.get("flags", [])
        if entry.get("lifecycle") == "rollout"
        and entry.get("decision") in {"pending", "undecided"}
        and isinstance(entry.get("owner"), str)
        and ("ramp" not in entry or ramp_due(entry) + timedelta(days=REVIEW_GRACE_DAYS) < current_date)
        for owner in owner_tokens(entry["owner"])
    )


def load_base_registry(root: Path) -> dict[str, Any]:
    # Hooks can export a different repository selection to child Git commands.
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    base = subprocess.run(
        ["git", "merge-base", "HEAD", "origin/main"],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    ).stdout.strip()
    content = subprocess.run(
        ["git", "show", f"{base}:config/feature-flags.yaml"],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    ).stdout
    with tempfile.TemporaryDirectory(prefix="omi-flag-base-") as directory:
        path = Path(directory) / "feature-flags.yaml"
        path.write_text(content, encoding="utf-8")
        return load_registry(path)


def check_diff_rules(base: dict[str, Any], registry: dict[str, Any], errors: list[str]) -> None:
    base_flags = {entry["key"]: entry for entry in base["flags"]}
    for entry in registry["flags"]:
        key = entry["key"]
        if key not in base_flags:
            if ACCOUNT_OWNERS.intersection(owner_tokens(entry["owner"])):
                errors.append(f"{key}: owner names an account; name the owning lane or area")
            continue
        old = base_flags[key]
        if "extension" in old and old["extension"]["until"] != entry.get("extension", {}).get("until"):
            errors.append(f"{key}: second extension refused: ramp or retire")
        if old.get("ramp", {}).get("done_by") and "ramp" not in entry and _ramp_applies_to(entry):
            errors.append(f"{key}: ramp deadline removed; keep the plan, ramp, or retire")
        for previous, current in (
            (old.get("review_by"), entry.get("review_by")),
            (old.get("ramp", {}).get("done_by"), entry.get("ramp", {}).get("done_by")),
        ):
            if previous and current and date.fromisoformat(current) > date.fromisoformat(previous):
                errors.append(f"{key}: due date moved later without an extension; add extension: instead")


def check_owner_backlog(
    base: dict[str, Any], registry: dict[str, Any], current_date: date, errors: list[str], warnings: list[str]
) -> None:
    base_keys = {entry["key"] for entry in base["flags"]}
    counts = owner_backlog(base, current_date)
    added_debt = owner_backlog(
        {"flags": [entry for entry in registry["flags"] if entry["key"] not in base_keys]}, current_date
    )
    for entry in registry["flags"]:
        if entry["key"] in base_keys or entry["lifecycle"] != "rollout":
            continue
        for owner in owner_tokens(entry["owner"]):
            if counts[owner] < MAX_UNRAMPED_PER_OWNER and counts[owner] + added_debt[owner] <= MAX_UNRAMPED_PER_OWNER:
                continue
            message = (
                f"{entry['key']}: owner={owner} had {counts[owner]} unramped flags at merge-base "
                f"(cap {MAX_UNRAMPED_PER_OWNER}); ramp or retire before adding"
            )
            if counts[owner] < MAX_UNRAMPED_PER_OWNER:
                message = (
                    f"{entry['key']}: owner={owner} would have {counts[owner] + added_debt[owner]} unramped flags "
                    f"after this diff (cap {MAX_UNRAMPED_PER_OWNER}); ramp or retire before adding"
                )
            exception = OWNER_BACKLOG_EXCEPTIONS.get(owner)
            if exception is None:
                errors.append(message)
                continue
            try:
                expires = date.fromisoformat(exception["expires"])
                reason = exception["reason"].strip()
                if not reason:
                    raise ValueError("empty reason")
            except (KeyError, TypeError, ValueError, AttributeError):
                errors.append(f"owner_backlog_exceptions[{owner}] requires an ISO expires date and nonempty reason")
                continue
            if current_date > expires:
                errors.append(f"owner backlog exception expired {expires}: {message}")
            else:
                warnings.append(f"WARNING: owner backlog exception expires {expires}: {message} ({reason})")


def check(root: Path, *, check_render: bool = True, as_of: date | None = None) -> tuple[list[str], list[str]]:
    current_date = as_of or datetime.now(timezone.utc).date()
    registry_path = root / "config/feature-flags.yaml"
    registry = load_registry(registry_path)
    errors = validate_registry(registry, root=root, as_of=current_date)
    if errors:
        return errors, []
    for owner, count in sorted(owner_backlog(registry, current_date).items()):
        print(f"FLAG_OWNER_BACKLOG owner={owner} unramped={count}")
    warnings: list[str] = []
    diff_errors: list[str] = []
    diff_warnings: list[str] = []
    try:
        base = load_base_registry(root)
        check_diff_rules(base, registry, diff_errors)
        check_owner_backlog(base, registry, current_date, diff_errors, diff_warnings)
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError) as error:
        warnings.append(
            "WARNING: registry diff rules and owner backlog gate skipped: "
            f"cannot load registry at merge-base with origin/main: {error}"
        )
    else:
        errors.extend(diff_errors)
        warnings.extend(diff_warnings)
    flags = {entry["key"]: entry for entry in registry["flags"]}
    for key, expected in parser_defaults(root).items():
        if key in flags and flags[key]["fail"] != expected:
            errors.append(f"{key}: fail must be {expected} for the shared boolean parser; regenerate the registry")
    grandfathered = sum(
        1
        for entry in registry["flags"]
        if _ramp_applies_to(entry) and date.fromisoformat(entry["created"]) < RAMP_REQUIRED_FROM and "ramp" not in entry
    )
    if grandfathered:
        warnings.append(
            f"WARNING: {grandfathered} grandfathered pending/undecided rollout rows lack ramp "
            f"(created before {RAMP_REQUIRED_FROM.isoformat()})"
        )
    else:
        warnings.append(f"Grandfathered pending/undecided rollout rows without ramp: 0 (cutoff {RAMP_REQUIRED_FROM})")
    alias_to_key = {alias: entry["key"] for entry in registry["flags"] for alias in entry.get("aliases", [])}
    ignored = {entry["key"] for entry in registry["ignore"]}
    retired = {entry["key"] for entry in registry["retired"]}
    known = set(flags) | set(alias_to_key) | ignored | retired
    reads = extract_code_reads(root, known)
    present = {read.key for read in reads}
    for read in reads:
        if read.key in retired:
            errors.append(f"{read.path}:{read.line}: retired name reintroduced: {read.key}")
        elif read.key not in known:
            errors.append(f"{read.path}:{read.line}: unregistered feature flag: {read.key}")
    for key in sorted(set(flags) | set(alias_to_key)):
        if key not in present:
            errors.append(f"stale registry entry: delete it or restore the read: {key}")
    declarations = extract_deploy_declarations(root) + extract_action_declarations(root)
    for declared in declarations:
        if declared.key not in known:
            errors.append(f"{declared.path}:{declared.line}: undeclared registry flag: {declared.key}")
        elif declared.key in retired:
            errors.append(f"{declared.path}:{declared.line}: retired name redeclared: {declared.key}")

    duplicate_sources = duplicate_declaration_sources(declarations)
    for (key, _platform, workload, environment), sources in duplicate_sources.items():
        errors.append(
            f"duplicate declaration: {key} for {workload}/{environment} appears in {', '.join(sources)}: keep one source, "
            "or declare it in the manifest gke section that validates this chart"
        )

    doc = root / "backend/docs/feature-flag-registry.md"
    if check_render:
        old = doc.read_text(encoding="utf-8") if doc.is_file() else ""
        match = AS_OF.search(old)
        if match is None:
            errors.append(
                f"{doc.relative_to(root)}: missing committed as-of header; regenerate with python3 scripts/render_feature_flag_registry.py --as-of 2026-09-24"
            )
        else:
            as_of = date.fromisoformat(match[1])
            from render_feature_flag_registry import render

            fresh = render(root, registry, as_of)
            if old != fresh:
                errors.append(
                    f"{doc.relative_to(root)}: rendered doc drift; regenerate with python3 scripts/render_feature_flag_registry.py --as-of {as_of.isoformat()}"
                )
    in_grace_rows: set[str] = set()
    beyond_grace_rows: set[str] = set()
    dark_over_14d = 0
    for key, entry in sorted(flags.items()):
        owner = entry["owner"]
        if entry["lifecycle"] == "rollout" and entry["decision"] in {"keep", "with_legacy"}:
            warnings.append(f"{key}: rollout row decided keep; relabel config_switch or ops_kill")
        if (
            _ramp_applies_to(entry)
            and entry["fail"] == "closed"
            and date.fromisoformat(entry["created"]) + timedelta(days=14) < current_date
        ):
            dark_over_14d += 1
        for kind, due in due_dates(entry):
            breaks = due + timedelta(days=REVIEW_GRACE_DAYS + 1)
            if current_date < breaks <= current_date + timedelta(days=3):
                print(f"FLAG_DUE_SOON key={key} owner={owner} kind={kind} due={due} breaks={breaks}")
            if due < current_date < breaks:
                in_grace_rows.add(key)
                warnings.append(
                    f"WARNING: {kind} passed but remains within the {REVIEW_GRACE_DAYS}-day grace: "
                    f"{key} (due {due}, owner {owner})"
                )
            elif current_date >= breaks:
                beyond_grace_rows.add(key)
                if entry["decision"] in {"graduate", "ship", "kill", "kill_after_readout"} and (
                    key in present or any(alias in present for alias in entry.get("aliases", []))
                ):
                    errors.append(
                        f"{key} decided {entry['decision']} but code still reads it (due {due}): retire the code path"
                    )
                else:
                    field = "due" if kind == "review" else "done_by"
                    errors.append(
                        f"{kind} overdue beyond the {REVIEW_GRACE_DAYS}-day grace: {key} "
                        f"({field} {due}, owner {owner}): ramp, retire, or add one extension"
                    )
    print(f"FLAG_OVERDUE_COUNT n={len(in_grace_rows - beyond_grace_rows)}")
    print(f"FLAG_DARK_OVER_14D n={dark_over_14d}")
    return sorted(set(errors)), warnings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--skip-render", action="store_true")
    parser.add_argument("--as-of", type=date.fromisoformat, help="YYYY-MM-DD; defaults to today")
    args = parser.parse_args()
    try:
        errors, warnings = check(args.root.resolve(), check_render=not args.skip_render, as_of=args.as_of)
        sys.stdout.flush()
    except (OSError, ValueError, SyntaxError) as error:
        print(f"feature-flag registry: {error}", file=sys.stderr)
        return 1
    for warning in warnings:
        print(warning, file=sys.stderr)
    for error in errors:
        print(error, file=sys.stderr)
    if errors:
        return 1
    print("feature-flag registry: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
