#!/usr/bin/env python3
"""Resolve named backend-listen env overrides to helm --set-string argv.

Looks up each env var by name in the chart values ``env`` list and emits
``--set-string env[N].value=...`` so workflow_dispatch can override a few
literals without rewriting chart defaults on main.

Blank override values are skipped (chart defaults win). Unknown names or
secret/valueFrom entries fail closed.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Mapping

import yaml


def load_values(path: Path) -> dict:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    return loaded if isinstance(loaded, dict) else {}


def env_name_indices(values: Mapping) -> dict[str, int]:
    indices: dict[str, int] = {}
    for index, entry in enumerate(values.get("env") or []):
        if isinstance(entry, dict) and isinstance(entry.get("name"), str):
            indices[entry["name"]] = index
    return indices


def resolve_env_override_argv(
    values: Mapping,
    overrides: Mapping[str, str | None],
) -> list[str]:
    """Return helm argv fragments for non-empty named env overrides."""
    indices = env_name_indices(values)
    env_entries = values.get("env") or []
    argv: list[str] = []

    for name, raw_value in overrides.items():
        if raw_value is None:
            continue
        value = str(raw_value)
        # workflow_dispatch choice inputs cannot be empty (actionlint); the
        # chart-default sentinel means "leave the values file alone", same as "".
        if value in ("", "chart-default"):
            continue
        if name not in indices:
            raise ValueError(f"env {name} not found in values env list")
        index = indices[name]
        entry = env_entries[index]
        if not isinstance(entry, dict) or "value" not in entry:
            raise ValueError(f"env {name} is not a literal value entry")
        argv.extend(["--set-string", f"env[{index}].value={value}"])
    return argv


def parse_set_args(items: list[str]) -> dict[str, str]:
    overrides: dict[str, str] = {}
    for item in items:
        if "=" not in item:
            raise ValueError(f"override must be NAME=VALUE, got {item!r}")
        name, value = item.split("=", 1)
        if not name:
            raise ValueError(f"override name is empty in {item!r}")
        overrides[name] = value
    return overrides


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--values-file",
        required=True,
        type=Path,
        help="backend-listen values YAML whose env list is the lookup source",
    )
    parser.add_argument(
        "--set",
        action="append",
        default=[],
        metavar="NAME=VALUE",
        help="Named env override; blank VALUE is ignored (repeatable)",
    )
    parser.add_argument(
        "--output-argv-file",
        type=Path,
        help="Write one argv token per line (empty file when no overrides)",
    )
    args = parser.parse_args(argv)

    try:
        overrides = parse_set_args(args.set)
        resolved = resolve_env_override_argv(load_values(args.values_file), overrides)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.output_argv_file is not None:
        args.output_argv_file.write_text(
            ("\n".join(resolved) + ("\n" if resolved else "")),
            encoding="utf-8",
        )
    else:
        for token in resolved:
            print(token)

    if resolved:
        applied_names = [name for name, value in overrides.items() if value not in ("", "chart-default")]
        print(
            f"listen helm env overrides: {len(resolved) // 2} ({', '.join(applied_names)})",
            file=sys.stderr,
        )
    else:
        print("listen helm env overrides: none (chart defaults win)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
