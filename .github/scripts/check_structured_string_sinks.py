#!/usr/bin/env python3
"""Validate the repository's finite registry of structured-string workflow sinks.

This is deliberately not a general shell or workflow linter. Each check is
activated by an explicit registry entry that names one real sink, its grammar,
and the historical fixture that proves the check can fail.
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Iterator

import yaml

SCHEMA_VERSION = 1
SUPPORTED_KINDS = {"action-delimited-map", "script-split-argv", "script-interpreter"}
GITHUB_EXPRESSION_RE = re.compile(r"\$\{\{.*?}}")


@dataclass(frozen=True)
class Violation:
    entry_id: str
    path: str
    message: str

    def render(self) -> str:
        return f"{self.path}: [{self.entry_id}] {self.message}"


def repository_root(explicit: str | None = None) -> Path:
    return Path(explicit).resolve() if explicit else Path(__file__).resolve().parents[2]


def registry_directory(root: Path, explicit: str | None = None) -> Path:
    return Path(explicit).resolve() if explicit else root / ".github" / "structured-string-sinks"


def _safe_relative_path(raw: object, *, field: str) -> str:
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"{field} must be a non-empty repository-relative path")
    relative = raw.strip()
    path = PurePosixPath(relative)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"{field} must be a safe repository-relative path: {relative!r}")
    return relative


def _non_empty_string(raw: object, *, field: str) -> str:
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return raw.strip()


def _string_list(raw: object, *, field: str) -> list[str]:
    if not isinstance(raw, list) or not raw:
        raise ValueError(f"{field} must be a non-empty list")
    values = [_non_empty_string(value, field=f"{field}[]") for value in raw]
    if len(values) != len(set(values)):
        raise ValueError(f"{field} must not contain duplicates")
    return values


def _delimiter_list(raw: object, *, field: str) -> list[str]:
    if not isinstance(raw, list) or not raw or not all(isinstance(value, str) and value for value in raw):
        raise ValueError(f"{field} must be a non-empty list of non-empty delimiters")
    if len(raw) != len(set(raw)):
        raise ValueError(f"{field} must not contain duplicates")
    return list(raw)


def validate_entry(entry: object, *, source: Path, root: Path) -> dict[str, Any]:
    if not isinstance(entry, dict):
        raise ValueError(f"{source}: registry document must be a JSON object")
    if entry.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"{source}: schema_version must be {SCHEMA_VERSION}")

    entry_id = _non_empty_string(entry.get("id"), field=f"{source}: id")
    kind = _non_empty_string(entry.get("kind"), field=f"{source}: kind")
    if kind not in SUPPORTED_KINDS:
        raise ValueError(f"{source}: {entry_id}: unsupported kind {kind!r}")
    _non_empty_string(entry.get("failure_class"), field=f"{source}: failure_class")
    _non_empty_string(entry.get("safe_encoding"), field=f"{source}: safe_encoding")

    evidence_prs = entry.get("evidence_prs")
    if (
        not isinstance(evidence_prs, list)
        or not evidence_prs
        or not all(isinstance(number, int) and number > 0 for number in evidence_prs)
    ):
        raise ValueError(f"{source}: {entry_id}: evidence_prs must contain positive PR numbers")

    scope = entry.get("scope")
    if not isinstance(scope, dict):
        raise ValueError(f"{source}: {entry_id}: scope must be an object")
    _string_list(scope.get("globs"), field=f"{source}: {entry_id}: scope.globs")

    fixtures = entry.get("fixtures")
    if not isinstance(fixtures, dict):
        raise ValueError(f"{source}: {entry_id}: fixtures must be an object")
    for outcome in ("passing", "failing"):
        relative = _safe_relative_path(fixtures.get(outcome), field=f"{source}: {entry_id}: fixtures.{outcome}")
        if not (root / relative).is_file():
            raise ValueError(f"{source}: {entry_id}: missing {outcome} fixture {relative}")

    if "allowlist" in entry:
        raise ValueError(
            f"{source}: {entry_id}: bare allowlist is forbidden; name an owner and reason on the exact exemption"
        )

    if kind == "action-delimited-map":
        selector = entry.get("selector")
        grammar = entry.get("grammar")
        dynamic_values = entry.get("dynamic_values")
        if not isinstance(selector, dict) or not isinstance(grammar, dict):
            raise ValueError(f"{source}: {entry_id}: action entry requires selector and grammar objects")
        _non_empty_string(selector.get("uses"), field=f"{source}: {entry_id}: selector.uses")
        _non_empty_string(selector.get("input"), field=f"{source}: {entry_id}: selector.input")
        _non_empty_string(
            grammar.get("assignment_delimiter"), field=f"{source}: {entry_id}: grammar.assignment_delimiter"
        )
        _delimiter_list(grammar.get("pair_delimiters"), field=f"{source}: {entry_id}: grammar.pair_delimiters")
        escape = _non_empty_string(grammar.get("escape"), field=f"{source}: {entry_id}: grammar.escape")
        if len(escape) != 1:
            raise ValueError(f"{source}: {entry_id}: grammar.escape must be one character")
        if not isinstance(dynamic_values, dict):
            raise ValueError(f"{source}: {entry_id}: dynamic_values must name its policy owner and reason")
        _non_empty_string(dynamic_values.get("owner"), field=f"{source}: {entry_id}: dynamic_values.owner")
        reason = _non_empty_string(dynamic_values.get("reason"), field=f"{source}: {entry_id}: dynamic_values.reason")
        if len(reason) < 20:
            raise ValueError(f"{source}: {entry_id}: dynamic_values.reason must explain the safety boundary")
    else:
        command = _non_empty_string(entry.get("command"), field=f"{source}: {entry_id}: command")
        if "/" in command:
            raise ValueError(f"{source}: {entry_id}: command must be a basename, not a path")
        if kind == "script-split-argv":
            _string_list(entry.get("split_options"), field=f"{source}: {entry_id}: split_options")
        if kind == "script-interpreter":
            _string_list(entry.get("interpreters"), field=f"{source}: {entry_id}: interpreters")

    return entry


def load_registry(root: Path, directory: Path | None = None) -> list[dict[str, Any]]:
    registry_dir = directory or registry_directory(root)
    paths = sorted(registry_dir.glob("*.json"))
    if not paths:
        raise ValueError(f"no structured-string sink entries found in {registry_dir}")
    entries: list[dict[str, Any]] = []
    ids: set[str] = set()
    for path in paths:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(f"{path}: cannot load registry entry: {error}") from error
        entry = validate_entry(raw, source=path, root=root)
        entry_id = str(entry["id"])
        if entry_id in ids:
            raise ValueError(f"{path}: duplicate registry id {entry_id!r}")
        ids.add(entry_id)
        entries.append(entry)
    return entries


def _iter_mappings(value: object) -> Iterator[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _iter_mappings(child)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_mappings(child)


def _load_yaml(path: Path) -> object:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise ValueError(f"{path}: cannot parse YAML: {error}") from error


def _display_path(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _contains_unescaped(text: str, delimiter: str, escape: str) -> bool:
    start = 0
    while True:
        index = text.find(delimiter, start)
        if index < 0:
            return False
        escapes = 0
        cursor = index - 1
        while cursor >= 0 and text[cursor] == escape:
            escapes += 1
            cursor -= 1
        if escapes % 2 == 0:
            return True
        start = index + len(delimiter)


def _check_action_delimited_map(entry: dict[str, Any], path: Path, document: object, root: Path) -> list[Violation]:
    selector = entry["selector"]
    grammar = entry["grammar"]
    assignment = str(grammar["assignment_delimiter"])
    escape = str(grammar["escape"])
    value_delimiters = [delimiter for delimiter in grammar["pair_delimiters"] if delimiter != "\n"]
    violations: list[Violation] = []
    display = _display_path(path, root)

    for mapping in _iter_mappings(document):
        if mapping.get("uses") != selector["uses"]:
            continue
        inputs = mapping.get("with")
        if not isinstance(inputs, dict) or selector["input"] not in inputs:
            continue
        raw = inputs[selector["input"]]
        if not isinstance(raw, str):
            violations.append(
                Violation(
                    str(entry["id"]),
                    display,
                    f"{selector['uses']} input {selector['input']} must be a string",
                )
            )
            continue
        for line_number, raw_line in enumerate(raw.splitlines(), start=1):
            line = raw_line.strip()
            if not line or GITHUB_EXPRESSION_RE.fullmatch(line):
                continue
            if assignment not in line:
                violations.append(
                    Violation(
                        str(entry["id"]),
                        display,
                        f"{selector['input']} entry {line_number} is neither a dynamic producer nor a {assignment!r} assignment",
                    )
                )
                continue
            name, value = line.split(assignment, 1)
            literal_value = GITHUB_EXPRESSION_RE.sub("", value)
            for delimiter in value_delimiters:
                if _contains_unescaped(literal_value, str(delimiter), escape):
                    violations.append(
                        Violation(
                            str(entry["id"]),
                            display,
                            f"{selector['input']} assignment {name.strip()!r} contains unescaped {delimiter!r}; {entry['safe_encoding']}",
                        )
                    )
    return violations


def _logical_shell_commands(run: str) -> Iterator[list[str]]:
    masked = GITHUB_EXPRESSION_RE.sub("__GITHUB_EXPRESSION__", run)
    pending = ""
    for raw_line in masked.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        pending = f"{pending} {stripped}".strip()
        if pending.endswith("\\"):
            pending = pending[:-1].rstrip()
            continue
        try:
            yield shlex.split(pending, posix=True)
        except ValueError:
            # Shell syntax outside a registered command is not this check's
            # responsibility. If the registered basename is visible, fail
            # closed with a diagnostic instead of silently skipping it.
            if ".sh" in pending:
                yield ["__UNPARSEABLE__", pending]
        pending = ""
    if pending:
        try:
            yield shlex.split(pending, posix=True)
        except ValueError:
            if ".sh" in pending:
                yield ["__UNPARSEABLE__", pending]


def _command_basename(token: str) -> str:
    return token.rstrip(";,|").rsplit("/", 1)[-1]


def _registered_invocations(document: object, command: str) -> Iterator[tuple[list[str], int]]:
    for mapping in _iter_mappings(document):
        run = mapping.get("run")
        if not isinstance(run, str) or command not in run:
            continue
        for tokens in _logical_shell_commands(run):
            if tokens and tokens[0] == "__UNPARSEABLE__" and command in tokens[1]:
                yield tokens, 0
                continue
            for index, token in enumerate(tokens):
                if _command_basename(token) == command:
                    yield tokens, index


def _check_script_split_argv(entry: dict[str, Any], path: Path, document: object, root: Path) -> list[Violation]:
    display = _display_path(path, root)
    violations: list[Violation] = []
    for tokens, command_index in _registered_invocations(document, str(entry["command"])):
        if tokens and tokens[0] == "__UNPARSEABLE__":
            violations.append(Violation(str(entry["id"]), display, f"could not parse registered command: {tokens[1]}"))
            continue
        arguments = tokens[command_index + 1 :]
        for option in entry["split_options"]:
            joined = f"{option}="
            if any(argument.startswith(joined) for argument in arguments):
                violations.append(
                    Violation(
                        str(entry["id"]),
                        display,
                        f"{entry['command']} received joined argument {joined}<value>; {entry['safe_encoding']}",
                    )
                )
    return violations


def _check_script_interpreter(entry: dict[str, Any], path: Path, document: object, root: Path) -> list[Violation]:
    display = _display_path(path, root)
    allowed = set(entry["interpreters"])
    violations: list[Violation] = []
    for tokens, command_index in _registered_invocations(document, str(entry["command"])):
        if tokens and tokens[0] == "__UNPARSEABLE__":
            violations.append(Violation(str(entry["id"]), display, f"could not parse registered command: {tokens[1]}"))
            continue
        interpreter = tokens[command_index - 1] if command_index > 0 else ""
        if interpreter not in allowed:
            violations.append(
                Violation(
                    str(entry["id"]),
                    display,
                    f"{entry['command']} is invoked without an explicit {sorted(allowed)} interpreter; {entry['safe_encoding']}",
                )
            )
    return violations


def check_entry_paths(entry: dict[str, Any], paths: Iterable[Path], root: Path) -> list[Violation]:
    violations: list[Violation] = []
    for path in sorted(set(paths)):
        document = _load_yaml(path)
        if entry["kind"] == "action-delimited-map":
            violations.extend(_check_action_delimited_map(entry, path, document, root))
        elif entry["kind"] == "script-split-argv":
            violations.extend(_check_script_split_argv(entry, path, document, root))
        elif entry["kind"] == "script-interpreter":
            violations.extend(_check_script_interpreter(entry, path, document, root))
    return violations


def entry_paths(entry: dict[str, Any], root: Path) -> list[Path]:
    paths: set[Path] = set()
    for pattern in entry["scope"]["globs"]:
        paths.update(path for path in root.glob(pattern) if path.is_file())
    if not paths:
        raise ValueError(f"{entry['id']}: scope matched no files")
    return sorted(paths)


def count_entry_matches(entry: dict[str, Any], paths: Iterable[Path]) -> int:
    matches = 0
    for path in sorted(set(paths)):
        document = _load_yaml(path)
        if entry["kind"] == "action-delimited-map":
            selector = entry["selector"]
            matches += sum(
                1
                for mapping in _iter_mappings(document)
                if mapping.get("uses") == selector["uses"]
                and isinstance(mapping.get("with"), dict)
                and selector["input"] in mapping["with"]
            )
        else:
            matches += sum(1 for _ in _registered_invocations(document, str(entry["command"])))
    return matches


def check_repository(root: Path, entries: Iterable[dict[str, Any]]) -> list[Violation]:
    violations: list[Violation] = []
    for entry in entries:
        paths = entry_paths(entry, root)
        if count_entry_matches(entry, paths) == 0:
            raise ValueError(f"{entry['id']}: registered scope matched files but no sink invocation")
        violations.extend(check_entry_paths(entry, paths, root))
    return violations


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", help="repository root (defaults to this script's repository)")
    parser.add_argument("--registry-dir", help="registry directory (defaults to .github/structured-string-sinks)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    root = repository_root(args.root)
    try:
        entries = load_registry(root, registry_directory(root, args.registry_dir))
        violations = check_repository(root, entries)
    except ValueError as error:
        print(f"structured-string sink registry error: {error}", file=sys.stderr)
        return 2
    if violations:
        for violation in violations:
            print(violation.render(), file=sys.stderr)
        print(f"FAIL: {len(violations)} structured-string sink violation(s)", file=sys.stderr)
        return 1
    print(f"OK: {len(entries)} registered structured-string sinks are grammar-safe.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
