#!/usr/bin/env python3
"""Fail before a public build when its declared Cloud Run runtime is not deployable."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from check_public_build_contract import ROOT, Target, load_contract


@dataclass(frozen=True)
class RuntimeBinding:
    kind: str
    reference: str | None = None


class RuntimePreflightError(Exception):
    """The live Cloud Run or Secret Manager runtime contract cannot be verified."""

    def __init__(self, message: str, *, category: str = "unknown") -> None:
        super().__init__(message)
        self.category = category


def split_secret_reference(reference: str) -> tuple[str, str]:
    secret, version = reference.rsplit(":", maxsplit=1)
    return secret, version


def _containers(service: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    template = service.get("template")
    if isinstance(template, Mapping) and isinstance(template.get("containers"), list):
        return [container for container in template["containers"] if isinstance(container, Mapping)]
    spec = service.get("spec")
    if isinstance(spec, Mapping):
        template = spec.get("template")
        if isinstance(template, Mapping):
            template_spec = template.get("spec")
            if isinstance(template_spec, Mapping) and isinstance(template_spec.get("containers"), list):
                return [container for container in template_spec["containers"] if isinstance(container, Mapping)]
    return []


def current_bindings(service: Mapping[str, Any]) -> dict[str, RuntimeBinding]:
    """Extract Cloud Run env bindings without ever reading their values."""

    bindings: dict[str, RuntimeBinding] = {}
    for container in _containers(service):
        environment = container.get("env")
        if not isinstance(environment, list):
            continue
        for raw_item in environment:
            if not isinstance(raw_item, Mapping) or not isinstance(raw_item.get("name"), str):
                continue
            name = raw_item["name"]
            value_source = raw_item.get("valueSource")
            if not isinstance(value_source, Mapping):
                value_source = raw_item.get("valueFrom")
            secret_ref = value_source.get("secretKeyRef") if isinstance(value_source, Mapping) else None
            if isinstance(secret_ref, Mapping) and isinstance(secret_ref.get("name"), str) and isinstance(
                secret_ref.get("key"), str
            ):
                bindings[name] = RuntimeBinding("secret", f"{secret_ref['name']}:{secret_ref['key']}")
            else:
                bindings[name] = RuntimeBinding("literal")
    return bindings


def validate_current_bindings(target: Target, service: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    bindings = current_bindings(service)
    for name, expected_reference in target.deployment.runtime_secrets.items():
        actual = bindings.get(name)
        if actual is None:
            continue
        if actual.kind != "secret":
            errors.append(
                f"{target.name}: runtime binding {name} is a literal; expected Secret Manager {expected_reference}"
            )
        elif actual.reference != expected_reference:
            errors.append(
                f"{target.name}: runtime binding {name} references {actual.reference}; expected {expected_reference}"
            )
    declared_or_removed = set(target.deployment.runtime_secrets) | set(target.deployment.remove_runtime_secrets)
    for name, actual in bindings.items():
        if actual.kind == "secret" and name not in declared_or_removed:
            errors.append(f"{target.service}: secret binding {name} is missing from the deployment contract")
    return errors


def _gcloud_json(arguments: Sequence[str]) -> Mapping[str, Any]:
    try:
        completed = subprocess.run(
            ["gcloud", *arguments, "--format=json"],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        raw_message = f"{exc.stderr}\n{exc.stdout}".lower()
        if "not found" in raw_message or "does not exist" in raw_message or "not_found" in raw_message:
            message, category = "resource not found", "not_found"
        elif "permission denied" in raw_message or "permissiondenied" in raw_message:
            message, category = "permission denied", "permission_denied"
        elif "unauthenticated" in raw_message or "authentication" in raw_message:
            message, category = "authentication failed", "unauthenticated"
        else:
            message, category = "gcloud command failed", "unknown"
        raise RuntimePreflightError(message, category=category) from exc
    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimePreflightError("gcloud returned invalid JSON") from exc
    if not isinstance(result, Mapping):
        raise RuntimePreflightError("gcloud returned an unexpected JSON document")
    return result


def _is_missing_service(error: RuntimePreflightError) -> bool:
    return error.category == "not_found"


def load_current_service(*, target: Target, project_id: str) -> Mapping[str, Any] | None:
    try:
        return _gcloud_json(
            [
                "run",
                "services",
                "describe",
                target.service,
                f"--project={project_id}",
                f"--region={target.deployment.region}",
            ]
        )
    except RuntimePreflightError as exc:
        if _is_missing_service(exc):
            return None
        raise RuntimePreflightError(
            f"{target.name}: cannot read current Cloud Run service {target.service}: {exc}"
        ) from exc


def validate_secret_versions(*, target: Target, project_id: str) -> list[str]:
    errors: list[str] = []
    results: dict[str, RuntimePreflightError | Mapping[str, Any]] = {}
    for binding_name, reference in sorted(target.deployment.runtime_secrets.items()):
        secret, version = split_secret_reference(reference)
        result = results.get(reference)
        if result is None:
            try:
                result = _gcloud_json(
                    [
                        "secrets",
                        "versions",
                        "describe",
                        version,
                        f"--secret={secret}",
                        f"--project={project_id}",
                    ]
                )
            except RuntimePreflightError as exc:
                result = exc
            results[reference] = result
        if isinstance(result, RuntimePreflightError):
            errors.append(
                f"{target.service}: runtime binding {binding_name} requires Secret Manager version {reference}, "
                f"but it is unavailable ({result})"
            )
            continue
        if result.get("state") != "ENABLED":
            errors.append(
                f"{target.service}: runtime binding {binding_name} requires enabled Secret Manager version {reference}"
            )
    return errors


def preflight(*, target: Target, project_id: str) -> list[str]:
    errors = validate_secret_versions(target=target, project_id=project_id)
    try:
        service = load_current_service(target=target, project_id=project_id)
    except RuntimePreflightError as exc:
        errors.append(str(exc))
    else:
        if service is not None:
            errors.extend(validate_current_bindings(target, service))
    return errors


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--contract", type=Path, default=ROOT / "config" / "public-build-contract.json")
    args = parser.parse_args(argv)
    try:
        contract = load_contract(args.contract)
        target = contract.targets[args.target]
    except (KeyError, OSError, ValueError) as exc:
        print(f"public-build runtime preflight failed: {exc}", file=sys.stderr)
        return 1

    errors = preflight(target=target, project_id=args.project_id)
    if errors:
        print("public-build runtime preflight failed:", file=sys.stderr)
        print("\n".join(f"- {error}" for error in errors), file=sys.stderr)
        return 1
    print(f"public-build runtime preflight passed: target={target.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
