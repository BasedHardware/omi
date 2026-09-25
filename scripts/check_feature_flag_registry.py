#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

from feature_flag_registry import (
    ROOT, extract_code_reads, extract_deploy_declarations, load_registry, overdue, validate_registry,
)

AS_OF = re.compile(r"<!-- feature-flag-registry as-of: (\d{4}-\d{2}-\d{2}) -->")


def check(root: Path, *, check_render: bool = True) -> tuple[list[str], list[str]]:
    registry_path = root / "config/feature-flags.yaml"
    registry = load_registry(registry_path)
    errors = validate_registry(registry)
    if errors:
        return errors, []
    flags = {entry["key"]: entry for entry in registry["flags"]}
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
    for declared in extract_deploy_declarations(root):
        if declared.key not in known:
            errors.append(f"{declared.path}:{declared.line}: undeclared registry flag: {declared.key}")
        elif declared.key in retired:
            errors.append(f"{declared.path}:{declared.line}: retired name redeclared: {declared.key}")

    doc = root / "backend/docs/feature-flag-registry.md"
    warnings: list[str] = []
    if check_render:
        old = doc.read_text(encoding="utf-8") if doc.is_file() else ""
        match = AS_OF.search(old)
        if match is None:
            errors.append(f"{doc.relative_to(root)}: missing committed as-of header; regenerate with python3 scripts/render_feature_flag_registry.py --as-of 2026-09-24")
        else:
            as_of = date.fromisoformat(match[1])
            from render_feature_flag_registry import render

            fresh = render(root, registry, as_of)
            if old != fresh:
                errors.append(f"{doc.relative_to(root)}: rendered doc drift; regenerate with python3 scripts/render_feature_flag_registry.py --as-of {as_of.isoformat()}")
    for key in overdue(registry, date.today()):
        warnings.append(f"WARNING: overdue for a decision: {key}")
    return sorted(set(errors)), warnings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--skip-render", action="store_true")
    args = parser.parse_args()
    try:
        errors, warnings = check(args.root.resolve(), check_render=not args.skip_render)
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
