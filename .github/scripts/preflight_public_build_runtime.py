#!/usr/bin/env python3
"""Fail before a public build when its declared Cloud Run runtime is not deployable."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
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


def _sanitized_gcloud_diagnostic(error: subprocess.CalledProcessError) -> str:
    """Keep an actionable command failure without exposing credential-shaped text."""

    raw = "\n".join(part for part in (error.stderr, error.stdout) if part)
    compact = " ".join(raw.split())
    # gcloud normally omits credentials, but failures can include echoed input
    # from a proxy or wrapper. Do not turn a deployment error into a leak.
    compact = re.sub(r'(?i)(bearer\s+)[^\s,;"\']+', r"\1[REDACTED]", compact)
    for marker in ("access_token", "authorization", "password", "secret", "token"):
        compact = re.sub(
            rf'(?i)({marker}["\']?\s*[=:]\s*["\']?)' rf'(?:bearer\s+)?' rf'[^\s,;"\']+' rf'(["\']?)',
            r"\1[REDACTED]\2",
            compact,
        )
    return compact[:500] or "no diagnostic returned"


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


def _secret_reference(wrapper: str, value_source: Any) -> str | None:
    """Return a Secret Manager reference from one documented Cloud Run shape.

    Cloud Run v1 serializes secret refs as ``name``/``key`` under
    ``valueFrom``. Cloud Run v2 uses ``secret``/``version`` under
    ``valueSource``. The wrapper and nested shape must match exactly so the
    preflight never accepts an ambiguous source as a Secret Manager binding.
    """

    expected_fields = {
        "valueFrom": ("name", "key"),
        "valueSource": ("secret", "version"),
    }.get(wrapper)
    if expected_fields is None or not isinstance(value_source, Mapping) or set(value_source) != {"secretKeyRef"}:
        return None
    secret_ref = value_source["secretKeyRef"]
    if not isinstance(secret_ref, Mapping) or set(secret_ref) != set(expected_fields):
        return None
    secret, version = (secret_ref[field] for field in expected_fields)
    if not isinstance(secret, str) or not secret or not isinstance(version, str) or not version:
        return None
    return f"{secret}:{version}"


def _runtime_binding(raw_item: Mapping[str, Any]) -> RuntimeBinding:
    """Classify one Cloud Run environment entry without reading literal values."""

    source_wrappers = [wrapper for wrapper in ("valueFrom", "valueSource") if wrapper in raw_item]
    if not source_wrappers:
        return RuntimeBinding("literal")
    if len(source_wrappers) != 1 or "value" in raw_item:
        return RuntimeBinding("invalid")

    wrapper = source_wrappers[0]
    secret_reference = _secret_reference(wrapper, raw_item[wrapper])
    if secret_reference is None:
        return RuntimeBinding("invalid")
    return RuntimeBinding("secret", secret_reference)


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
            bindings[name] = _runtime_binding(raw_item)
    return bindings


def validate_current_bindings(target: Target, service: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    bindings = current_bindings(service)
    for name, actual in bindings.items():
        if actual.kind == "invalid":
            errors.append(f"{target.service}: runtime binding {name} has an ambiguous or malformed value source")
    for name, expected_reference in target.deployment.runtime_secrets.items():
        actual = bindings.get(name)
        if actual is None:
            continue
        if actual.kind == "invalid":
            continue
        if actual.kind != "secret":
            errors.append(
                f"{target.name}: runtime binding {name} is a literal; expected Secret Manager {expected_reference}"
            )
        elif actual.reference != expected_reference:
            errors.append(
                f"{target.name}: runtime binding {name} references {actual.reference}; expected {expected_reference}"
            )
    for name in target.deployment.preserve_runtime_secrets:
        actual = bindings.get(name)
        if actual is None:
            errors.append(
                f"{target.name}: preserved runtime secret {name} is absent; expected an enabled Secret Manager binding"
            )
        elif actual.kind == "invalid":
            continue
        elif actual.kind != "secret":
            errors.append(
                f"{target.name}: preserved runtime secret {name} is a literal; expected an enabled Secret Manager binding"
            )
    for name in target.deployment.runtime_env_vars:
        actual = bindings.get(name)
        if actual is not None and actual.kind == "invalid":
            continue
        if actual is not None and actual.kind != "literal":
            errors.append(f"{target.name}: runtime config {name} is a Secret Manager binding; expected a literal value")
    declared_or_removed = (
        set(target.deployment.runtime_secrets)
        | set(target.deployment.preserve_runtime_secrets)
        | set(target.deployment.runtime_env_vars)
        | set(target.deployment.remove_runtime_secrets)
    )
    for name, actual in bindings.items():
        if actual.kind == "secret" and name not in declared_or_removed:
            errors.append(f"{target.service}: secret binding {name} is missing from the deployment contract")
    return errors


def _gcloud_json_document(arguments: Sequence[str]) -> Any:
    try:
        completed = subprocess.run(
            ["gcloud", *arguments, "--format=json"],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        raw_message = f"{exc.stderr}\n{exc.stdout}".lower()
        if "permission denied" in raw_message or "permissiondenied" in raw_message:
            message, category = "permission denied", "permission_denied"
        elif "unauthenticated" in raw_message or "authentication" in raw_message:
            message, category = "authentication failed", "unauthenticated"
        else:
            message = f"gcloud command failed: {_sanitized_gcloud_diagnostic(exc)}"
            category = "unknown"
        raise RuntimePreflightError(message, category=category) from exc
    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimePreflightError("gcloud returned invalid JSON") from exc
    return result


def _gcloud_json(arguments: Sequence[str]) -> Mapping[str, Any]:
    result = _gcloud_json_document(arguments)
    if not isinstance(result, Mapping):
        raise RuntimePreflightError("gcloud returned an unexpected JSON document")
    return result


def _gcloud_access_token() -> str:
    """Return the current gcloud access token. Never log or print it."""

    try:
        completed = subprocess.run(
            ["gcloud", "auth", "print-access-token"],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        # stdout is the bearer token on success; never include it in diagnostics.
        raise RuntimePreflightError(
            "gcloud auth print-access-token failed",
            category="unauthenticated",
        ) from exc
    token = ""
    for line in completed.stdout.splitlines():
        if line.strip():
            token = line.strip()
    if not token:
        raise RuntimePreflightError(
            "gcloud auth print-access-token returned no token",
            category="unauthenticated",
        )
    return token


def _test_service_account_iam_permissions(
    *,
    service_account: str,
    project_id: str,
    permissions: Sequence[str],
) -> Mapping[str, Any]:
    """POST IAM testIamPermissions. Fake this in tests; never log the token."""

    token = _gcloud_access_token()
    quoted_project = urllib.parse.quote(project_id, safe=".-")
    quoted_account = urllib.parse.quote(service_account, safe=".-")
    url = (
        f"https://iam.googleapis.com/v1/projects/{quoted_project}"
        f"/serviceAccounts/{quoted_account}:testIamPermissions"
    )
    request = urllib.request.Request(
        url,
        data=json.dumps({"permissions": list(permissions)}).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        try:
            exc.close()
        except Exception:
            pass
        raise RuntimePreflightError(
            f"IAM testIamPermissions HTTP {exc.code}",
            category="unknown",
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimePreflightError("IAM testIamPermissions request failed", category="unknown") from exc
    try:
        result = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimePreflightError("IAM testIamPermissions returned invalid JSON") from exc
    if not isinstance(result, Mapping):
        raise RuntimePreflightError("IAM testIamPermissions returned an unexpected JSON document")
    return result


def _cloud_run_service_exists(*, target: Target, project_id: str) -> bool:
    """Use an authenticated, name-filtered list to classify a first create."""

    result = _gcloud_json_document(
        [
            "run",
            "services",
            "list",
            f"--project={project_id}",
            f"--region={target.deployment.region}",
            f"--filter=metadata.name={target.service}",
        ]
    )
    if not isinstance(result, list) or not all(isinstance(item, Mapping) for item in result):
        raise RuntimePreflightError("gcloud returned an unexpected Cloud Run service list")
    return bool(result)


def load_current_service(*, target: Target, project_id: str) -> Mapping[str, Any] | None:
    try:
        if not _cloud_run_service_exists(target=target, project_id=project_id):
            return None
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
        raise RuntimePreflightError(
            f"{target.name}: cannot inspect current Cloud Run service {target.service}: {exc}", category=exc.category
        ) from exc


def validate_secret_versions(*, target: Target, project_id: str) -> list[str]:
    return validate_secret_references(
        service_name=target.service,
        references=target.deployment.runtime_secrets,
        project_id=project_id,
    )


def validate_preserved_secret_versions(*, target: Target, service: Mapping[str, Any], project_id: str) -> list[str]:
    bindings = current_bindings(service)
    references = {
        name: binding.reference
        for name in target.deployment.preserve_runtime_secrets
        if (binding := bindings.get(name)) is not None and binding.kind == "secret" and binding.reference is not None
    }
    return validate_secret_references(service_name=target.service, references=references, project_id=project_id)


def validate_fallback_secret_versions(*, target: Target, project_id: str) -> list[str]:
    return validate_secret_references(
        service_name=target.service,
        references=target.deployment.fallback_runtime_secrets,
        project_id=project_id,
    )


def validate_secret_references(*, service_name: str, references: Mapping[str, str], project_id: str) -> list[str]:
    errors: list[str] = []
    results: dict[str, RuntimePreflightError | Mapping[str, Any]] = {}
    for binding_name, reference in sorted(references.items()):
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
                f"{service_name}: runtime binding {binding_name} requires Secret Manager version {reference}, "
                f"but it is unavailable ({result})"
            )
            continue
        if result.get("state") != "ENABLED":
            errors.append(
                f"{service_name}: runtime binding {binding_name} requires enabled Secret Manager version {reference}"
            )
    return errors


def validate_service_account(*, service_account: str, project_id: str) -> list[str]:
    """Prove a Cloud Run runtime identity exists and the deployer can act as it."""

    identity = service_account.strip()
    if not identity:
        return []
    try:
        _gcloud_json(["iam", "service-accounts", "describe", identity, f"--project={project_id}"])
    except RuntimePreflightError as exc:
        return [f"{identity}: Cloud Run runtime identity does not exist or cannot be described ({exc})"]
    try:
        result = _test_service_account_iam_permissions(
            service_account=identity,
            project_id=project_id,
            permissions=("iam.serviceAccounts.actAs",),
        )
    except RuntimePreflightError as exc:
        return [f"{identity}: cannot test iam.serviceAccounts.actAs ({exc})"]
    granted = result.get("permissions")
    if not isinstance(granted, list) or "iam.serviceAccounts.actAs" not in granted:
        return [f"{identity}: deployer is missing permission iam.serviceAccounts.actAs"]
    return []


def preflight_deployment_result(
    *, target: Target, project_id: str, service_account: str = ""
) -> tuple[list[str], dict[str, str], bool]:
    """Validate the runtime and report whether the Cloud Run service exists."""

    errors = validate_secret_versions(target=target, project_id=project_id)
    errors.extend(validate_service_account(service_account=service_account, project_id=project_id))
    fallback_runtime_secrets: dict[str, str] = {}
    service_exists = False
    try:
        service = load_current_service(target=target, project_id=project_id)
    except RuntimePreflightError as exc:
        errors.append(str(exc))
    else:
        if service is None:
            fallback_runtime_secrets = target.deployment.fallback_runtime_secrets
            errors.extend(validate_fallback_secret_versions(target=target, project_id=project_id))
        else:
            service_exists = True
            errors.extend(validate_current_bindings(target, service))
            errors.extend(validate_preserved_secret_versions(target=target, service=service, project_id=project_id))
    return errors, fallback_runtime_secrets, service_exists


def preflight_result(*, target: Target, project_id: str, service_account: str = "") -> tuple[list[str], dict[str, str]]:
    """Validate the runtime for callers that do not need deployment metadata."""

    errors, fallback_runtime_secrets, _service_exists = preflight_deployment_result(
        target=target, project_id=project_id, service_account=service_account
    )
    return errors, fallback_runtime_secrets


def preflight(*, target: Target, project_id: str, service_account: str = "") -> list[str]:
    return preflight_result(target=target, project_id=project_id, service_account=service_account)[0]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--service-account", default="")
    parser.add_argument("--contract", type=Path, default=ROOT / "config" / "public-build-contract.json")
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args(argv)
    try:
        contract = load_contract(args.contract)
        target = contract.targets[args.target]
    except (KeyError, OSError, ValueError) as exc:
        print(f"public-build runtime preflight failed: {exc}", file=sys.stderr)
        return 1

    errors, fallback_runtime_secrets, service_exists = preflight_deployment_result(
        target=target, project_id=args.project_id, service_account=args.service_account
    )
    if errors:
        print("public-build runtime preflight failed:", file=sys.stderr)
        print("\n".join(f"- {error}" for error in errors), file=sys.stderr)
        return 1
    if args.github_output is not None:
        fallback_lines = "\n".join(
            f"{name}={reference}" for name, reference in sorted(fallback_runtime_secrets.items())
        )
        with args.github_output.open("a", encoding="utf-8") as output:
            output.write(f"fallback_runtime_secrets<<EOF\n{fallback_lines}\nEOF\n")
            output.write(f"service_exists={'true' if service_exists else 'false'}\n")
    print(f"public-build runtime preflight passed: target={target.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
