#!/usr/bin/env python3
"""Verify checked-in public-build wiring against its canonical contract."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONTRACT = ROOT / "config" / "public-build-contract.json"
DEFAULT_CLASSIFICATION = ROOT / "config" / "deployment-setting-classification.json"
NAME = re.compile(r"[A-Z][A-Z0-9_]*\Z")
ARG = re.compile(r"^\s*ARG\s+([A-Z][A-Z0-9_]*)\s*$", re.MULTILINE)
GUARD = re.compile(r'^\s*ENV\s+OMI_REQUIRED_PUBLIC_BUILD_INPUTS="([A-Z0-9_ ]*)"\s*$', re.MULTILINE)
WORKFLOW_BUILD_ARG = re.compile(
    r'^\s*(?:--build-arg\s+)?"?([A-Z][A-Z0-9_]*)=\$\{\{\s*vars\.([A-Z][A-Z0-9_]*)\s*}}"?',
    re.MULTILINE,
)
ALLOWED_SCOPES = frozenset({"organization", "repository", "environment"})


@dataclass(frozen=True)
class PublicInput:
    name: str
    scope: str


@dataclass(frozen=True)
class Target:
    name: str
    dockerfile: str
    workflow: str
    inputs: tuple[PublicInput, ...]


def _read_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def load_contract(path: Path) -> dict[str, Target]:
    raw = _read_json(path)
    if not isinstance(raw, dict) or not isinstance(raw.get("targets"), dict):
        raise ValueError(f"{path}: targets must be an object")

    targets: dict[str, Target] = {}
    for target_name, raw_target in raw["targets"].items():
        if not isinstance(target_name, str) or not target_name:
            raise ValueError(f"{path}: target names must be non-empty strings")
        if not isinstance(raw_target, dict):
            raise ValueError(f"{path}: target {target_name} must be an object")
        dockerfile = raw_target.get("dockerfile")
        workflow = raw_target.get("workflow")
        raw_inputs = raw_target.get("inputs")
        if not isinstance(dockerfile, str) or not dockerfile:
            raise ValueError(f"{path}: target {target_name} must declare dockerfile")
        if not isinstance(workflow, str) or not workflow:
            raise ValueError(f"{path}: target {target_name} must declare workflow")
        if not isinstance(raw_inputs, list) or not raw_inputs:
            raise ValueError(f"{path}: target {target_name} must declare non-empty inputs")

        inputs: list[PublicInput] = []
        for raw_input in raw_inputs:
            if not isinstance(raw_input, dict):
                raise ValueError(f"{path}: target {target_name} inputs must be objects")
            name = raw_input.get("name")
            scope = raw_input.get("scope")
            if not isinstance(name, str) or NAME.fullmatch(name) is None:
                raise ValueError(f"{path}: target {target_name} has invalid input name {name!r}")
            if scope not in ALLOWED_SCOPES:
                raise ValueError(f"{path}: target {target_name} input {name} has invalid scope {scope!r}")
            inputs.append(PublicInput(name=name, scope=scope))
        names = [item.name for item in inputs]
        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            raise ValueError(f"{path}: target {target_name} duplicates inputs: {', '.join(duplicates)}")
        targets[target_name] = Target(target_name, dockerfile, workflow, tuple(inputs))
    if not targets:
        raise ValueError(f"{path}: targets must not be empty")
    return targets


def public_build_names(classification_path: Path) -> set[str]:
    raw = _read_json(classification_path)
    try:
        names = raw["kinds"]["public_build"]
    except (KeyError, TypeError) as exc:
        raise ValueError(f"{classification_path}: kinds.public_build must be a list") from exc
    if not isinstance(names, list) or not all(isinstance(name, str) for name in names):
        raise ValueError(f"{classification_path}: kinds.public_build must be a list")
    return set(names)


def _required_names(target: Target) -> set[str]:
    return {item.name for item in target.inputs}


def _docker_public_args(text: str, classified_public: set[str]) -> set[str]:
    return {
        name
        for name in ARG.findall(text)
        if name.startswith("NEXT_PUBLIC_") or name in classified_public
    }


def _guarded_names(text: str) -> set[str]:
    match = GUARD.search(text)
    if match is None:
        return set()
    return set(match.group(1).split())


def _workflow_public_bindings(text: str, classified_public: set[str]) -> dict[str, str]:
    bindings: dict[str, str] = {}
    for argument, source in WORKFLOW_BUILD_ARG.findall(text):
        if argument.startswith("NEXT_PUBLIC_") or argument in classified_public:
            existing = bindings.get(argument)
            if existing is not None and existing != source:
                raise ValueError(f"workflow builds {argument} from multiple vars sources")
            bindings[argument] = source
    return bindings


def validate_target(root: Path, target: Target, classified_public: set[str]) -> list[str]:
    errors: list[str] = []
    required = _required_names(target)
    unclassified = sorted(required - classified_public)
    for name in unclassified:
        errors.append(f"{target.name}: required input {name} is not classified public_build")

    dockerfile_path = root / target.dockerfile
    if not dockerfile_path.is_file():
        return errors + [f"{target.name}: Dockerfile is missing: {target.dockerfile}"]
    dockerfile = dockerfile_path.read_text(encoding="utf-8")
    docker_args = _docker_public_args(dockerfile, classified_public)
    for name in sorted(required - docker_args):
        errors.append(f"{target.dockerfile}: required public ARG {name} is missing")
    for name in sorted(docker_args - required):
        errors.append(f"{target.dockerfile}: public ARG {name} is not declared by target {target.name}")

    guard_names = _guarded_names(dockerfile)
    if not guard_names:
        errors.append(f"{target.dockerfile}: missing OMI_REQUIRED_PUBLIC_BUILD_INPUTS guard")
    for name in sorted(required - guard_names):
        errors.append(f"{target.dockerfile}: empty-value guard omits {name}")
    for name in sorted(guard_names - required):
        errors.append(f"{target.dockerfile}: empty-value guard includes undeclared {name}")
    if guard_names and 'test -n "$value"' not in dockerfile:
        errors.append(f"{target.dockerfile}: public-build guard must reject empty values")

    workflow_path = root / target.workflow
    if not workflow_path.is_file():
        return errors + [f"{target.name}: workflow is missing: {target.workflow}"]
    try:
        bindings = _workflow_public_bindings(workflow_path.read_text(encoding="utf-8"), classified_public)
    except ValueError as exc:
        return errors + [f"{target.workflow}: {exc}"]
    for name in sorted(required - bindings.keys()):
        errors.append(f"{target.workflow}: required public build arg {name} is missing")
    for name in sorted(bindings.keys() - required):
        errors.append(f"{target.workflow}: public build arg {name} is not declared by target {target.name}")
    for name in sorted(required & bindings.keys()):
        if bindings[name] != name:
            errors.append(f"{target.workflow}: build arg {name} must use vars.{name}, not vars.{bindings[name]}")
    return errors


def validate(root: Path, targets: Iterable[Target], classified_public: set[str]) -> list[str]:
    errors: list[str] = []
    for target in targets:
        errors.extend(validate_target(root, target, classified_public))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--contract", type=Path)
    parser.add_argument("--classification", type=Path)
    parser.add_argument("--target", action="append")
    args = parser.parse_args()

    root = args.root.resolve()
    contract_path = (args.contract or root / DEFAULT_CONTRACT.relative_to(ROOT)).resolve()
    classification_path = (args.classification or root / DEFAULT_CLASSIFICATION.relative_to(ROOT)).resolve()
    try:
        targets = load_contract(contract_path)
        selected_names = args.target or sorted(targets)
        unknown = sorted(set(selected_names) - targets.keys())
        if unknown:
            raise ValueError(f"unknown public-build targets: {', '.join(unknown)}")
        errors = validate(root, (targets[name] for name in selected_names), public_build_names(classification_path))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"public-build contract check failed: {exc}", file=sys.stderr)
        return 1
    if errors:
        print("public-build contract check failed:", file=sys.stderr)
        print("\n".join(f"- {error}" for error in errors), file=sys.stderr)
        return 1
    print("public-build contract check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
