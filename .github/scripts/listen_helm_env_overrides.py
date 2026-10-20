#!/usr/bin/env python3
"""Resolve named backend-listen env overrides to helm --set-string argv.

Looks up each env var by name in the chart values ``env`` list and emits
``--set-string env[N].value=...`` so workflow_dispatch can override a few
literals without rewriting chart defaults on main.

Blank override values are skipped (chart defaults win). Unknown names or
secret/valueFrom entries fail closed. Override values are constrained to a
single-line safe literal alphabet and helm-special characters are escaped so
comma-separated model lists and newline injection cannot widen the argv.

``--private-values-file`` validates a values file rendered from a
protected-environment secret (top-level ``privateEnv`` map of NAME to string),
registers each value as a GitHub Actions log mask, and appends ``-f <file>`` to
the argv. Its error messages never contain a value. ``--redact-release-values``
filters ``helm get values`` output on stdin so privateEnv values never reach a
log.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys
from typing import Mapping

import yaml

# Single-line literals only. Newlines would split the argv file; other
# control/separator characters are rejected rather than trusted through helm.
_SAFE_OVERRIDE_VALUE = re.compile(r"^[A-Za-z0-9_.,+\-]+$")
_HELM_SET_ESCAPE_CHARS = ("\\", ",", "{", "}", "[", "]", ".", "=")

PRIVATE_ENV_KEY = "privateEnv"
_PRIVATE_ENV_NAME = re.compile(r"^[A-Z][A-Z0-9_]*$")
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")
# The chart derives this one from runtimeGcpProjectId; never let a private
# value replace it.
_CHART_OWNED_ENV = frozenset({"GOOGLE_CLOUD_PROJECT"})
REDACTED = "<redacted>"
# GitHub drops any job output that contains a masked string, and this job
# exports short-SHA image tags. Short flag values ("true", "live") are not
# identifiers, so only values at least this long are registered as masks.
MASK_MIN_LENGTH = 8


class _UniqueKeyLoader(yaml.SafeLoader):
    """SafeLoader that rejects duplicate mapping keys instead of keeping the last."""


def _construct_unique_mapping(loader: _UniqueKeyLoader, node: yaml.MappingNode, deep: bool = False):
    seen = set()
    for key_node, _ in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in seen:
            raise ValueError(f"private values repeat a key (line {key_node.start_mark.line + 1})")
        seen.add(key)
    return loader.construct_mapping(node, deep=deep)


_UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping)


def load_values(path: Path) -> dict:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    return loaded if isinstance(loaded, dict) else {}


def env_name_indices(values: Mapping) -> dict[str, int]:
    indices: dict[str, int] = {}
    for index, entry in enumerate(values.get("env") or []):
        if isinstance(entry, dict) and isinstance(entry.get("name"), str):
            indices[entry["name"]] = index
    return indices


def validate_override_value(name: str, value: str) -> str:
    if any(ch in value for ch in ("\n", "\r", "\0")):
        raise ValueError(f"env {name} override contains a disallowed control character")
    if not _SAFE_OVERRIDE_VALUE.fullmatch(value):
        raise ValueError(f"env {name} override has disallowed characters: {value!r}")
    return value


def helm_escape_set_string(value: str) -> str:
    """Escape characters helm still treats as --set/--set-string syntax."""
    escaped = value
    for ch in _HELM_SET_ESCAPE_CHARS:
        escaped = escaped.replace(ch, f"\\{ch}")
    return escaped


def applied_override_names(overrides: Mapping[str, str | None]) -> list[str]:
    return [name for name, value in overrides.items() if value is not None and str(value) not in ("", "chart-default")]


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
        # workflow_dispatch choice cannot ship literal "off"; accept disabled alias.
        if name == "OMI_LLM_GATEWAY_FEATURE_MODE" and value == "disabled":
            value = "off"
        if name not in indices:
            raise ValueError(f"env {name} not found in values env list")
        index = indices[name]
        entry = env_entries[index]
        if not isinstance(entry, dict) or "value" not in entry:
            raise ValueError(f"env {name} is not a literal value entry")
        safe_value = validate_override_value(name, value)
        argv.extend(
            [
                "--set-string",
                f"env[{index}].value={helm_escape_set_string(safe_value)}",
            ]
        )
    return argv


def load_private_env(path: Path) -> dict[str, str]:
    """Parse and validate a private values file. Messages never echo content."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        raise ValueError("private values file is unreadable or not UTF-8") from None
    try:
        documents = list(yaml.load_all(text, Loader=_UniqueKeyLoader))  # noqa: S506 - SafeLoader subclass
    except yaml.YAMLError as exc:
        # str(exc) quotes the offending line; report only its position.
        mark = getattr(exc, "problem_mark", None)
        where = f" (line {mark.line + 1})" if mark is not None else ""
        raise ValueError(f"private values do not parse as YAML{where}") from None
    if len(documents) != 1:
        raise ValueError("private values must be exactly one YAML document")
    loaded = documents[0]
    if not isinstance(loaded, dict) or set(loaded) != {PRIVATE_ENV_KEY}:
        raise ValueError(f"private values must be a mapping whose only top-level key is {PRIVATE_ENV_KEY}")
    private_env = loaded[PRIVATE_ENV_KEY]
    if private_env is None:
        return {}
    if not isinstance(private_env, dict):
        raise ValueError(f"{PRIVATE_ENV_KEY} must be a mapping of NAME to string")
    for name, value in private_env.items():
        if not isinstance(name, str) or not _PRIVATE_ENV_NAME.fullmatch(name):
            # The bad key itself is not printed: it may be a misplaced value.
            raise ValueError(f"{PRIVATE_ENV_KEY} has a key that does not match {_PRIVATE_ENV_NAME.pattern}")
        if not isinstance(value, str):
            raise ValueError(f"{PRIVATE_ENV_KEY}.{name} must be a quoted string")
        if _CONTROL_CHARS.search(value):
            raise ValueError(f"{PRIVATE_ENV_KEY}.{name} contains a control character")
    return dict(private_env)


def check_private_env_against_chart(
    private_env: Mapping[str, str],
    values: Mapping,
    overrides: Mapping[str, str | None],
) -> None:
    """Fail when a private name would silently shadow a chart-owned or overridden entry."""
    indices = env_name_indices(values)
    env_entries = values.get("env") or []
    overridden = set(applied_override_names(overrides))
    for name in private_env:
        if name in _CHART_OWNED_ENV:
            raise ValueError(f"{PRIVATE_ENV_KEY}.{name} is derived by the chart and cannot be overridden")
        if name in indices:
            entry = env_entries[indices[name]]
            if not isinstance(entry, dict) or "value" not in entry:
                raise ValueError(f"{PRIVATE_ENV_KEY}.{name} would replace a non-literal (valueFrom) env entry")
        if name in overridden:
            raise ValueError(f"{PRIVATE_ENV_KEY}.{name} conflicts with a workflow_dispatch override of the same env")


def github_mask_command(value: str) -> str:
    """Return the ::add-mask:: workflow command for value, escaped like @actions/core."""
    escaped = value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    return f"::add-mask::{escaped}"


def redact_release_values(text: str) -> str:
    """Return helm get values output with every privateEnv value replaced.

    Output without a privateEnv key passes through unchanged. Anything that
    cannot be parsed is withheld rather than printed.
    """
    if not text.strip():
        return text
    header = ""
    body = text
    first_line, sep, rest = text.partition("\n")
    if first_line.strip() == "USER-SUPPLIED VALUES:":
        header, body = first_line + sep, rest
    try:
        loaded = yaml.safe_load(body)
    except yaml.YAMLError:
        return "release values withheld: they could not be parsed for redaction\n"
    if loaded is None:
        return text
    if not isinstance(loaded, dict):
        return "release values withheld: they could not be parsed for redaction\n"
    if not loaded.get(PRIVATE_ENV_KEY):
        # Absent, null, or the values file's own privateEnv: {} carries nothing.
        return text
    private_env = loaded[PRIVATE_ENV_KEY]
    if isinstance(private_env, dict):
        loaded[PRIVATE_ENV_KEY] = {str(name): REDACTED for name in private_env}
    else:
        loaded[PRIVATE_ENV_KEY] = REDACTED
    return header + yaml.safe_dump(loaded, sort_keys=False, default_flow_style=False)


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
    parser.add_argument(
        "--private-values-file",
        type=Path,
        help="Validated privateEnv values file; masked and passed to helm as -f",
    )
    parser.add_argument(
        "--redact-release-values",
        action="store_true",
        help="Filter helm get values output from stdin to stdout, redacting privateEnv",
    )
    args = parser.parse_args(argv)

    if args.redact_release_values:
        sys.stdout.write(redact_release_values(sys.stdin.read()))
        return 0
    if args.values_file is None:
        parser.error("--values-file is required")

    try:
        overrides = parse_set_args(args.set)
        values = load_values(args.values_file)
        resolved = resolve_env_override_argv(values, overrides)
        private_env: dict[str, str] = {}
        if args.private_values_file is not None:
            private_env = load_private_env(args.private_values_file)
            check_private_env_against_chart(private_env, values, overrides)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.private_values_file is not None:
        # Register masks before anything downstream can render these values.
        for value in private_env.values():
            if len(value) >= MASK_MIN_LENGTH:
                print(github_mask_command(value), flush=True)
        resolved = resolved + ["-f", str(args.private_values_file)]

    if args.output_argv_file is not None:
        args.output_argv_file.write_text(
            ("\n".join(resolved) + ("\n" if resolved else "")),
            encoding="utf-8",
        )
    else:
        for token in resolved:
            print(token)

    applied_names = applied_override_names(overrides)
    if applied_names:
        print(
            f"listen helm env overrides: {len(applied_names)} ({', '.join(applied_names)})",
            file=sys.stderr,
        )
    else:
        print("listen helm env overrides: none (chart defaults win)", file=sys.stderr)
    if args.private_values_file is not None:
        print(
            # Count only: a key name is not guaranteed to be safe to print.
            f"listen private env: {len(private_env)} key(s)",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
