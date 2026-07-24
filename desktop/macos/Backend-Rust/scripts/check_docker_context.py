#!/usr/bin/env python3
"""Check that Rust compile-time assets are present in the Docker build context.

This intentionally covers only literal ``include_str!`` and ``include_bytes!``
paths. Dynamic paths cannot be resolved without compiling the project, while
these literals are a cheap, high-signal contract between Rust sources and the
Dockerfile.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import shlex
import sys
from dataclasses import dataclass
from pathlib import Path

INCLUDE_PATTERN = re.compile(r'include_(?:str|bytes)!\s*\(\s*"([^"]+)"\s*\)')
INSTRUCTION_PATTERN = re.compile(r"^(?:COPY|ADD)\s+(.+)$", re.IGNORECASE)


@dataclass(frozen=True)
class DockerignoreRule:
    pattern: str
    negated: bool


def _logical_dockerfile_lines(dockerfile: Path) -> list[str]:
    """Return non-comment Dockerfile instructions with continuations joined."""

    instructions: list[str] = []
    current = ""

    for raw_line in dockerfile.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if line.endswith("\\"):
            current = f"{current} {line[:-1].rstrip()}".strip()
            continue

        instructions.append(f"{current} {line}".strip())
        current = ""

    if current:
        instructions.append(current)

    return instructions


def _copy_sources(dockerfile: Path) -> list[str]:
    """Extract local source operands from Dockerfile COPY and ADD instructions."""

    sources: list[str] = []
    for line in _logical_dockerfile_lines(dockerfile):
        match = INSTRUCTION_PATTERN.match(line)
        if not match:
            continue

        arguments = match.group(1).strip()
        if arguments.startswith("["):
            try:
                operands = json.loads(arguments)
            except json.JSONDecodeError:
                continue
            if (
                isinstance(operands, list)
                and len(operands) >= 2
                and all(isinstance(operand, str) for operand in operands)
            ):
                sources.extend(operands[:-1])
            continue

        try:
            operands = shlex.split(arguments)
        except ValueError:
            continue

        if any(operand == "--from" or operand.startswith("--from=") for operand in operands):
            continue

        local_operands = [operand for operand in operands if not operand.startswith("--")]
        if len(local_operands) >= 2:
            sources.extend(local_operands[:-1])

    return sources


def _dockerignore_rules(context: Path) -> list[DockerignoreRule]:
    dockerignore = context / ".dockerignore"
    if not dockerignore.exists():
        return []

    rules: list[DockerignoreRule] = []
    for raw_line in dockerignore.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        negated = line.startswith("!")
        pattern = line[1:] if negated else line
        pattern = pattern.lstrip("/")
        if pattern and pattern != ".":
            rules.append(DockerignoreRule(pattern=pattern, negated=negated))

    return rules


def _matches_dockerignore_pattern(relative_path: str, pattern: str) -> bool:
    """Approximate Docker ignore matching for a file and each of its parents."""

    normalized = pattern.rstrip("/")
    if not normalized:
        return False

    path = Path(relative_path)
    candidates = [path.as_posix()]
    candidates.extend(parent.as_posix() for parent in path.parents if parent.as_posix() != ".")

    if "/" not in normalized:
        return any(fnmatch.fnmatchcase(part, normalized) for part in path.parts)

    return any(fnmatch.fnmatchcase(candidate, normalized) for candidate in candidates)


def _is_ignored(relative_path: str, rules: list[DockerignoreRule]) -> bool:
    ignored = False
    for rule in rules:
        if _matches_dockerignore_pattern(relative_path, rule.pattern):
            ignored = not rule.negated
    return ignored


def _source_covers_asset(source: str, asset: str) -> bool:
    source = source.removeprefix("./").rstrip("/")
    if source in {"", "."}:
        return True

    if source.startswith(("http://", "https://", "git://")):
        return False

    if any(character in source for character in "*?["):
        return fnmatch.fnmatchcase(asset, source) or any(
            fnmatch.fnmatchcase(parent.as_posix(), source) for parent in Path(asset).parents
        )

    return asset == source or asset.startswith(f"{source}/")


def _compile_time_assets(context: Path, source_root: Path) -> tuple[set[Path], list[str]]:
    assets: set[Path] = set()
    errors: list[str] = []
    if not source_root.exists():
        return assets, [f"Rust source directory does not exist: {source_root}"]

    for source in source_root.rglob("*.rs"):
        source_text = source.read_text(encoding="utf-8")
        for include_path in INCLUDE_PATTERN.findall(source_text):
            asset = (source.parent / include_path).resolve()
            try:
                asset.relative_to(context)
            except ValueError:
                errors.append(
                    f"{source.relative_to(context)} includes {include_path!r}, which resolves outside the Docker context"
                )
                continue

            if not asset.is_file():
                errors.append(
                    f"{source.relative_to(context)} includes {include_path!r}, but {asset.relative_to(context)} does not exist"
                )
                continue

            assets.add(asset)

    return assets, errors


def validate_context(context: Path, dockerfile: Path, source_root: Path | None = None) -> list[str]:
    """Return each Docker context contract violation for the supplied paths."""

    context = context.resolve()
    dockerfile = dockerfile.resolve()
    source_root = (source_root or context / "src").resolve()
    if not dockerfile.is_file():
        return [f"Dockerfile does not exist: {dockerfile}"]

    assets, errors = _compile_time_assets(context, source_root)
    copy_sources = _copy_sources(dockerfile)
    dockerignore_rules = _dockerignore_rules(context)

    for asset in sorted(assets):
        relative_asset = asset.relative_to(context).as_posix()
        if _is_ignored(relative_asset, dockerignore_rules):
            errors.append(f"{relative_asset} is used by include_str!/include_bytes! but excluded by .dockerignore")
            continue

        if not any(_source_covers_asset(source, relative_asset) for source in copy_sources):
            errors.append(
                f"{relative_asset} is used by include_str!/include_bytes! but no local COPY/ADD source includes it"
            )

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    default_context = Path(__file__).resolve().parents[1]
    parser.add_argument("--context", type=Path, default=default_context, help="Docker build context directory")
    parser.add_argument("--dockerfile", type=Path, help="Dockerfile to validate (defaults to <context>/Dockerfile)")
    parser.add_argument("--source-root", type=Path, help="Rust source directory relative to the build context")
    args = parser.parse_args()

    context = args.context.resolve()
    dockerfile = (args.dockerfile or context / "Dockerfile").resolve()
    source_root = context / args.source_root if args.source_root else None
    errors = validate_context(context, dockerfile, source_root)
    if errors:
        print("Docker context contract failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    assets, _ = _compile_time_assets(context, source_root or context / "src")
    print(f"Docker context contract passed: {len(assets)} compile-time asset(s) covered.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
