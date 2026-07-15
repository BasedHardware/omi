#!/usr/bin/env python3
"""Verify browser-build deploy wiring against the canonical checked-in contract."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONTRACT = ROOT / "config" / "public-build-contract.json"
DEFAULT_VALUES = ROOT / "config" / "public-build-values.json"
DEFAULT_CLASSIFICATION = ROOT / "config" / "deployment-setting-classification.json"
NAME = re.compile(r"[A-Z][A-Z0-9_]*\Z")
ARG = re.compile(r"^\s*ARG\s+([A-Z][A-Z0-9_]*)\s*$", re.MULTILINE)
GUARD = re.compile(r'^\s*ENV\s+OMI_REQUIRED_PUBLIC_BUILD_INPUTS="([A-Z0-9_ ]*)"\s*$', re.MULTILINE)
WEB_WORKFLOWS = frozenset(
    {
        ".github/workflows/gcp_admin.yml",
        ".github/workflows/gcp_app.yml",
        ".github/workflows/gcp_frontend.yml",
        ".github/workflows/gcp_personas.yml",
    }
)
PREPARE_ACTION = "uses: ./.github/actions/prepare-public-build"
PROMOTION_ACTION = "uses: ./.github/actions/public-build-candidate-promotion"
PREPARE_ACTION_PATH = ".github/actions/prepare-public-build/action.yml"
PROMOTION_ACTION_PATH = ".github/actions/public-build-candidate-promotion/action.yml"


@dataclass(frozen=True)
class PublicInput:
    name: str
    required: bool
    source: str
    allowed_scopes: tuple[str, ...]


@dataclass(frozen=True)
class CandidateAcceptance:
    command: tuple[str, ...]
    marker: str


@dataclass(frozen=True)
class Target:
    name: str
    service: str
    dockerfile: str
    workflow: str
    canary_component: str
    inputs: tuple[PublicInput, ...]
    candidate_acceptance: CandidateAcceptance
    traffic_promotion: str


@dataclass(frozen=True)
class Contract:
    config_path: str
    environments: tuple[str, ...]
    targets: dict[str, Target]


def _read_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _require_string(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _parse_input(raw_input: Any, *, target_name: str) -> PublicInput:
    if not isinstance(raw_input, Mapping):
        raise ValueError(f"target {target_name} inputs must be objects")
    name = _require_string(raw_input.get("name"), field=f"target {target_name} input name")
    if NAME.fullmatch(name) is None:
        raise ValueError(f"target {target_name} has invalid input name {name!r}")
    required = raw_input.get("required")
    if not isinstance(required, bool):
        raise ValueError(f"target {target_name} input {name} must declare required")
    source = _require_string(raw_input.get("source"), field=f"target {target_name} input {name} source")
    raw_scopes = raw_input.get("allowed_scopes")
    if not isinstance(raw_scopes, list) or not raw_scopes or not all(isinstance(scope, str) for scope in raw_scopes):
        raise ValueError(f"target {target_name} input {name} must declare allowed_scopes")
    return PublicInput(name=name, required=required, source=source, allowed_scopes=tuple(raw_scopes))


def load_contract(path: Path) -> Contract:
    raw = _read_json(path)
    if not isinstance(raw, Mapping) or raw.get("schema_version") != 2:
        raise ValueError(f"{path}: unsupported public-build contract schema")
    configuration = raw.get("configuration")
    if not isinstance(configuration, Mapping) or configuration.get("source") != "repository_config":
        raise ValueError(f"{path}: configuration source must be repository_config")
    config_path = _require_string(configuration.get("path"), field=f"{path}: configuration path")
    raw_environments = configuration.get("environments")
    if not isinstance(raw_environments, list) or not raw_environments or not all(
        isinstance(environment, str) and environment for environment in raw_environments
    ):
        raise ValueError(f"{path}: configuration environments must be non-empty strings")
    environments = tuple(raw_environments)
    if len(set(environments)) != len(environments):
        raise ValueError(f"{path}: configuration environments must be unique")

    raw_targets = raw.get("targets")
    if not isinstance(raw_targets, Mapping) or not raw_targets:
        raise ValueError(f"{path}: targets must be a non-empty object")
    targets: dict[str, Target] = {}
    for target_name, raw_target in raw_targets.items():
        if not isinstance(target_name, str) or not target_name or not isinstance(raw_target, Mapping):
            raise ValueError(f"{path}: targets must map names to objects")
        raw_inputs = raw_target.get("inputs")
        if not isinstance(raw_inputs, list) or not raw_inputs:
            raise ValueError(f"{path}: target {target_name} must declare inputs")
        inputs = tuple(_parse_input(item, target_name=target_name) for item in raw_inputs)
        names = [item.name for item in inputs]
        if len(set(names)) != len(names):
            raise ValueError(f"{path}: target {target_name} duplicates inputs")
        acceptance = raw_target.get("candidate_acceptance")
        if not isinstance(acceptance, Mapping):
            raise ValueError(f"{path}: target {target_name} must declare candidate_acceptance")
        command = acceptance.get("command")
        if not isinstance(command, list) or not command or not all(isinstance(part, str) and part for part in command):
            raise ValueError(f"{path}: target {target_name} candidate command is invalid")
        if "{base_url}" not in command:
            raise ValueError(f"{path}: target {target_name} candidate command must use {{base_url}}")
        targets[target_name] = Target(
            name=target_name,
            service=_require_string(raw_target.get("service"), field=f"target {target_name} service"),
            dockerfile=_require_string(raw_target.get("dockerfile"), field=f"target {target_name} dockerfile"),
            workflow=_require_string(raw_target.get("workflow"), field=f"target {target_name} workflow"),
            canary_component=_require_string(
                raw_target.get("canary_component"), field=f"target {target_name} canary_component"
            ),
            inputs=inputs,
            candidate_acceptance=CandidateAcceptance(
                command=tuple(command), marker=_require_string(acceptance.get("marker"), field="candidate marker")
            ),
            traffic_promotion=_require_string(
                raw_target.get("traffic_promotion"), field=f"target {target_name} traffic_promotion"
            ),
        )
    return Contract(config_path=config_path, environments=environments, targets=targets)


def parse_values_document(raw: Any, *, source: str) -> dict[str, dict[str, str]]:
    if not isinstance(raw, Mapping) or raw.get("schema_version") != 1:
        raise ValueError(f"{source}: unsupported public-build values schema")
    raw_environments = raw.get("environments")
    if not isinstance(raw_environments, Mapping) or not raw_environments:
        raise ValueError(f"{source}: environments must be a non-empty object")
    values: dict[str, dict[str, str]] = {}
    for environment, raw_environment in raw_environments.items():
        if not isinstance(environment, str) or not isinstance(raw_environment, Mapping):
            raise ValueError(f"{source}: invalid environment entry")
        raw_values = raw_environment.get("values")
        if not isinstance(raw_values, Mapping):
            raise ValueError(f"{source}: environment {environment} must declare values")
        if not all(isinstance(name, str) and isinstance(value, str) for name, value in raw_values.items()):
            raise ValueError(f"{source}: environment {environment} values must be string pairs")
        values[environment] = dict(raw_values)
    return values


def load_values(path: Path) -> dict[str, dict[str, str]]:
    return parse_values_document(_read_json(path), source=str(path))


def required_names(target: Target) -> set[str]:
    return {item.name for item in target.inputs if item.required}


def all_names(target: Target) -> set[str]:
    return {item.name for item in target.inputs}


def validate_values(
    contract: Contract,
    values: dict[str, dict[str, str]],
    targets: Iterable[Target],
    environment: str,
) -> list[str]:
    errors: list[str] = []
    if environment not in contract.environments:
        return [f"contract does not declare environment {environment}"]
    environment_values = values.get(environment)
    if environment_values is None:
        return [f"configuration is missing environment {environment}"]
    for target in targets:
        for item in target.inputs:
            value = environment_values.get(item.name)
            if item.required and (not isinstance(value, str) or not value.strip()):
                errors.append(f"{target.name}: required input {item.name} is missing or empty in {environment}")
            elif isinstance(value, str) and any(character in value for character in ("\n", "\r", "\x00")):
                errors.append(f"{target.name}: input {item.name} is unsafe for Docker build arguments")
    return errors


def build_args(target: Target, values: Mapping[str, str]) -> str:
    return "\n".join(f"{item.name}={values[item.name]}" for item in target.inputs if item.name in values)


def public_build_names(classification_path: Path) -> set[str]:
    raw = _read_json(classification_path)
    try:
        names = raw["kinds"]["public_build"]
    except (KeyError, TypeError) as exc:
        raise ValueError(f"{classification_path}: kinds.public_build must be a list") from exc
    if not isinstance(names, list) or not all(isinstance(name, str) for name in names):
        raise ValueError(f"{classification_path}: kinds.public_build must be a list")
    return set(names)


def _docker_public_args(text: str, classified_public: set[str]) -> set[str]:
    return {name for name in ARG.findall(text) if name.startswith("NEXT_PUBLIC_") or name in classified_public}


def _guarded_names(text: str) -> set[str]:
    match = GUARD.search(text)
    return set() if match is None else set(match.group(1).split())


def validate_target(root: Path, target: Target, classified_public: set[str]) -> list[str]:
    errors: list[str] = []
    names = all_names(target)
    unclassified = sorted(names - classified_public)
    errors.extend(f"{target.name}: input {name} is not classified public_build" for name in unclassified)
    for item in target.inputs:
        if item.source != "repository_config":
            errors.append(f"{target.name}: input {item.name} must use repository_config")
        if item.allowed_scopes != ("repository",):
            errors.append(f"{target.name}: input {item.name} must allow only repository scope")

    dockerfile_path = root / target.dockerfile
    if not dockerfile_path.is_file():
        return errors + [f"{target.name}: Dockerfile is missing: {target.dockerfile}"]
    dockerfile = dockerfile_path.read_text(encoding="utf-8")
    docker_args = _docker_public_args(dockerfile, classified_public)
    errors.extend(f"{target.dockerfile}: required public ARG {name} is missing" for name in sorted(names - docker_args))
    errors.extend(
        f"{target.dockerfile}: public ARG {name} is not declared by target {target.name}"
        for name in sorted(docker_args - names)
    )
    guard_names = _guarded_names(dockerfile)
    if not guard_names:
        errors.append(f"{target.dockerfile}: missing OMI_REQUIRED_PUBLIC_BUILD_INPUTS guard")
    required = required_names(target)
    errors.extend(
        f"{target.dockerfile}: empty-value guard omits {name}" for name in sorted(required - guard_names)
    )
    errors.extend(
        f"{target.dockerfile}: empty-value guard includes undeclared {name}" for name in sorted(guard_names - required)
    )
    if guard_names and 'test -n "$value"' not in dockerfile:
        errors.append(f"{target.dockerfile}: public-build guard must reject empty values")

    workflow_path = root / target.workflow
    if not workflow_path.is_file():
        return errors + [f"{target.name}: workflow is missing: {target.workflow}"]
    workflow = workflow_path.read_text(encoding="utf-8")
    for marker in (PREPARE_ACTION, "id: public-build", "build-args: ${{ steps.public-build.outputs.build_args }}"):
        if marker not in workflow:
            errors.append(f"{target.workflow}: missing shared public-build preparation {marker!r}")
    for name in sorted(names):
        if f"vars.{name}" in workflow:
            errors.append(f"{target.workflow}: input {name} bypasses repository_config via GitHub vars")
    for marker in ("no_traffic: true", "--revision-suffix=", "--tag=", PROMOTION_ACTION):
        if marker not in workflow:
            errors.append(f"{target.workflow}: missing candidate promotion marker {marker!r}")
    if "revision_traffic:" in workflow or "LATEST=100" in workflow:
        errors.append(f"{target.workflow}: must not promote direct traffic during candidate deployment")
    if target.candidate_acceptance.command[1] != ".github/scripts/smoke_public_build_browser.py":
        errors.append(f"{target.name}: candidate acceptance must use the shared browser smoke")
    if target.traffic_promotion != "candidate_after_browser_acceptance":
        errors.append(f"{target.name}: traffic promotion must follow browser acceptance")

    canary_path = root / target.canary_component
    if not canary_path.is_file():
        errors.append(f"{target.name}: client canary is missing: {target.canary_component}")
    else:
        canary = canary_path.read_text(encoding="utf-8")
        if "data-omi-public-build-canary" not in canary or target.name not in canary:
            errors.append(f"{target.canary_component}: must expose {target.name} browser canary")
    return errors


def validate_shared_actions(root: Path) -> list[str]:
    errors: list[str] = []
    prepare_path = root / PREPARE_ACTION_PATH
    if not prepare_path.is_file():
        errors.append(f"shared public-build preparation action is missing: {PREPARE_ACTION_PATH}")
    else:
        prepare = prepare_path.read_text(encoding="utf-8")
        for marker in ("preflight_public_build_config.py", "--github-output", "GITHUB_TOKEN: ${{ github.token }}"):
            if marker not in prepare:
                errors.append(f"{PREPARE_ACTION_PATH}: missing reviewed-source preflight marker {marker!r}")

    promotion_path = root / PROMOTION_ACTION_PATH
    if not promotion_path.is_file():
        errors.append(f"shared public-build candidate promotion action is missing: {PROMOTION_ACTION_PATH}")
        return errors
    promotion = promotion_path.read_text(encoding="utf-8")
    required_markers = (
        "resolve_cloud_run_tagged_url.py",
        "smoke_public_build_browser.py",
        "status.latestCreatedRevisionName",
        "gcloud run services update-traffic",
        "--to-revisions=",
    )
    for marker in required_markers:
        if marker not in promotion:
            errors.append(f"{PROMOTION_ACTION_PATH}: missing candidate-promotion marker {marker!r}")
    smoke_index = promotion.find("smoke_public_build_browser.py")
    promotion_index = promotion.find("gcloud run services update-traffic")
    if smoke_index == -1 or promotion_index == -1 or smoke_index > promotion_index:
        errors.append(f"{PROMOTION_ACTION_PATH}: browser acceptance must run before traffic promotion")
    return errors


def validate(root: Path, contract: Contract, classified_public: set[str]) -> list[str]:
    errors: list[str] = []
    workflows = {target.workflow for target in contract.targets.values()}
    if workflows != WEB_WORKFLOWS:
        errors.append("contract must cover exactly the four browser deploy workflows")
    for target in contract.targets.values():
        errors.extend(validate_target(root, target, classified_public))
    errors.extend(validate_shared_actions(root))
    values_path = root / contract.config_path
    try:
        values = load_values(values_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return errors + [f"public-build values check failed: {exc}"]
    for environment in contract.environments:
        errors.extend(validate_values(contract, values, contract.targets.values(), environment))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--contract", type=Path)
    parser.add_argument("--classification", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    contract_path = (args.contract or root / DEFAULT_CONTRACT.relative_to(ROOT)).resolve()
    classification_path = (args.classification or root / DEFAULT_CLASSIFICATION.relative_to(ROOT)).resolve()
    try:
        contract = load_contract(contract_path)
        errors = validate(root, contract, public_build_names(classification_path))
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
