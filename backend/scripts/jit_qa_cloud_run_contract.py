#!/usr/bin/env python3
"""Fail-closed contract for the isolated JIT QA Cloud Run plane.

The normal development services use a mounted customer-data service account and
therefore point at the shared customer Firestore project.  This contract is
intentionally independent of ``runtime_env.yaml``: the QA resources use bare
development ADC, distinct Cloud Run names, and a deliberately small explicit
environment.  The workflow may deploy these resources, but it must never
mutate Firebase Auth or reuse customer-data credentials.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Mapping

PROJECT_ID = "based-hardware-dev"
REGION = "us-central1"
AUTH_PROJECT_ID = "based-hardware"

BACKEND_SERVICE = "backend-jit-qa"
DESKTOP_BACKEND_SERVICE = "desktop-backend-jit-qa"
LEDGER_DRAIN_JOB = "knowledge-ledger-drain-qa-job"
DAILY_SWEEP_JOB = "daily-memory-sweep-qa-job"

# This is the existing named-app identity that can authenticate through the
# normal Firebase Auth project.  The cloud plane owns only this UID and uses
# the dev Firestore data plane, so no customer account is ever migrated by this
# workflow.  It must never be paired with the shared ``based-hardware`` data
# plane.
QA_UID = "vi7SA9ckQCe4ccobWNxlbdcNdC23"
RUN_ONCE_CONFIRMATION = "RUN_ONCE"

BACKEND_DOCKERFILE = "backend/Dockerfile"
DESKTOP_BACKEND_DOCKERFILE = "backend/Dockerfile.desktop_backend"
LEDGER_DRAIN_DOCKERFILE = "backend/modal/Dockerfile.knowledge_ledger_drain_job"
DAILY_SWEEP_DOCKERFILE = "backend/modal/Dockerfile.daily_memory_sweep_job"

_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_DIGEST_IMAGE_RE = re.compile(r"^gcr\.io/based-hardware-dev/[a-z0-9-]+@sha256:[0-9a-f]{64}$")
_FORBIDDEN_CREDENTIAL_ENV = frozenset(
    {
        "SERVICE_ACCOUNT_JSON",
        "GOOGLE_APPLICATION_CREDENTIALS",
        "FIREBASE_AUTH_CREDENTIALS_PATH",
    }
)
_ALLOWED_SECRET_BINDINGS = {
    # Cloud Run Secret Manager refs are ``secret-name:version``.  These are
    # the development project's individual secrets; the similarly named
    # Kubernetes ``dev-omi-backend-secrets`` bundle must never be copied into
    # this plane.
    "ENCRYPTION_SECRET": "ENCRYPTION_SECRET:latest",
    "OPENAI_API_KEY": "OPENAI_API_KEY:latest",
}
RUNTIME_SERVICE_ACCOUNT = "jit-qa-runtime@based-hardware-dev.iam.gserviceaccount.com"


class JITQAContractError(ValueError):
    """The proposed QA execution crosses an isolation or rollout boundary."""


def require_sha(value: str, *, label: str) -> None:
    if not _SHA_RE.fullmatch(value):
        raise JITQAContractError(f"{label} must be a full lowercase 40-character SHA")


def require_digest_image(value: str, *, label: str) -> None:
    if not _DIGEST_IMAGE_RE.fullmatch(value):
        raise JITQAContractError(f"{label} must be a dev GCR image pinned by sha256 digest")


def validate_static_configuration(
    *,
    project: str,
    region: str,
    auth_project: str,
    uid: str,
    drain_enabled: str,
    sweep_enabled: str,
    sweep_kill_switch: str,
    run_once: str,
    confirmation: str,
    images: Mapping[str, str] | None = None,
) -> None:
    """Validate workflow inputs and the safe deployment baseline.

    ``drain_enabled`` and ``sweep_enabled`` describe the deployed baseline.  A
    one-shot execution is separately admitted by ``validate_execution`` and
    uses Cloud Run's execution override rather than changing the resource.
    """

    if project != PROJECT_ID:
        raise JITQAContractError(f"QA project must be {PROJECT_ID}")
    if region != REGION:
        raise JITQAContractError(f"QA region must be {REGION}")
    if auth_project != AUTH_PROJECT_ID:
        raise JITQAContractError(f"QA auth project must be {AUTH_PROJECT_ID}")
    if uid != QA_UID:
        raise JITQAContractError("QA UID must be the existing JIT QA identity")
    if drain_enabled != "false":
        raise JITQAContractError("ledger drain must deploy with its gate false")
    if sweep_enabled != "false":
        raise JITQAContractError("daily sweep must deploy with its gate false")
    if sweep_kill_switch != "false":
        raise JITQAContractError("daily sweep kill switch must deploy false")
    if run_once not in {"true", "false"}:
        raise JITQAContractError("run_once must be true or false")
    if run_once == "false" and confirmation:
        raise JITQAContractError("execution confirmation is only valid with run_once=true")
    if images is not None:
        expected = {"backend", "desktop", "drain", "sweep"}
        if set(images) != expected:
            raise JITQAContractError(f"exactly these QA images are required: {sorted(expected)}")
        for name, image in images.items():
            require_digest_image(image, label=f"{name} image")


def validate_environment(environment: Mapping[str, str]) -> None:
    """Reject credential selectors and non-QA runtime identity values."""

    for name in _FORBIDDEN_CREDENTIAL_ENV:
        if environment.get(name, "").strip():
            raise JITQAContractError(f"{name} is forbidden on the isolated QA plane")
    expected = {
        "GOOGLE_CLOUD_PROJECT": PROJECT_ID,
        "OMI_FIRESTORE_DATA_PLANE_PROJECT": PROJECT_ID,
        "FIREBASE_AUTH_PROJECT_ID": AUTH_PROJECT_ID,
        "OMI_ENV_STAGE": "dev",
    }
    for name, value in expected.items():
        if environment.get(name) != value:
            raise JITQAContractError(f"{name} must be {value}")
    if environment.get("KNOWLEDGE_LEDGER_DRAIN_UID_ALLOWLIST") != QA_UID:
        raise JITQAContractError("ledger drain allowlist must contain only the QA UID")


def validate_execution(*, run_once: str, confirmation: str, kill_switch: str = "false") -> None:
    """Admit one explicit bounded execution without opening a persistent gate."""

    if run_once != "true":
        raise JITQAContractError("one-shot execution was not explicitly requested")
    if confirmation != RUN_ONCE_CONFIRMATION:
        raise JITQAContractError(f"one-shot execution requires confirmation {RUN_ONCE_CONFIRMATION!r}")
    if kill_switch != "false":
        raise JITQAContractError("one-shot execution requires the sweep kill switch to remain false")


def _containers(resource: Mapping[str, Any], *, kind: str) -> list[Mapping[str, Any]]:
    try:
        if kind == "service":
            template = resource["spec"]["template"]
            if not isinstance(template, Mapping):
                raise TypeError
            service_template = template.get("spec", template)
            value = service_template["containers"]
        elif kind == "job":
            template = resource["spec"]["template"]
            if not isinstance(template, Mapping):
                raise TypeError
            job_template = template.get("template", template)
            value = job_template["containers"]
        else:
            raise JITQAContractError(f"unknown Cloud Run resource kind {kind!r}")
    except (KeyError, TypeError) as exc:
        raise JITQAContractError(f"Cloud Run {kind} has no v2 container contract") from exc
    if not isinstance(value, list) or len(value) != 1 or not isinstance(value[0], dict):
        raise JITQAContractError(f"Cloud Run {kind} must have exactly one application container")
    return value


def validate_cloud_run_resource(
    resource: Mapping[str, Any],
    *,
    kind: str,
    expected_image: str,
    expected_environment: Mapping[str, str],
    expected_secret_bindings: Mapping[str, str] | None = None,
    expected_name: str | None = None,
    expected_service_account: str = RUNTIME_SERVICE_ACCOUNT,
) -> None:
    """Validate a post-deploy Cloud Run describe result without printing secrets."""

    require_digest_image(expected_image, label="expected image")
    if expected_name is not None:
        metadata = resource.get("metadata")
        if not isinstance(metadata, Mapping) or metadata.get("name") != expected_name:
            raise JITQAContractError("Cloud Run resource name does not match the admitted QA name")
    container = _containers(resource, kind=kind)[0]
    if container.get("image") != expected_image:
        raise JITQAContractError("Cloud Run resource image does not match the admitted digest")
    expected_secret_bindings = dict(expected_secret_bindings or {})
    expected_names = set(expected_environment) | set(expected_secret_bindings)
    seen_names: set[str] = set()
    for entry in container.get("env", []):
        if not isinstance(entry, dict):
            raise JITQAContractError("Cloud Run environment entry is malformed")
        name = entry.get("name")
        if not isinstance(name, str) or not name or name in seen_names:
            raise JITQAContractError("Cloud Run environment names must be unique and non-empty")
        seen_names.add(name)
        if name in _FORBIDDEN_CREDENTIAL_ENV:
            raise JITQAContractError(f"Cloud Run resource retains forbidden credential env {name}")
        wrappers = [wrapper for wrapper in ("valueFrom", "valueSource") if wrapper in entry]
        if len(wrappers) > 1 or (wrappers and "value" in entry):
            raise JITQAContractError(f"Cloud Run resource has an ambiguous binding for {name}")
        if wrappers:
            wrapper = wrappers[0]
            if name not in expected_secret_bindings:
                raise JITQAContractError(f"Cloud Run resource has an unapproved secret binding for {name}")
            value_source = entry.get(wrapper)
            if not isinstance(value_source, Mapping) or set(value_source) != {"secretKeyRef"}:
                raise JITQAContractError(f"Cloud Run resource has an invalid secret binding for {name}")
            secret_ref = value_source.get("secretKeyRef")
            if not isinstance(secret_ref, Mapping):
                raise JITQAContractError(f"Cloud Run resource has an invalid secret binding for {name}")
            if wrapper == "valueFrom":
                actual_binding = f"{secret_ref.get('name', '')}:{secret_ref.get('key', '')}"
                if set(secret_ref) != {"name", "key"}:
                    raise JITQAContractError(f"Cloud Run resource has an invalid secret binding for {name}")
            else:
                actual_binding = f"{secret_ref.get('secret', '')}:{secret_ref.get('version', '')}"
                if set(secret_ref) != {"secret", "version"}:
                    raise JITQAContractError(f"Cloud Run resource has an invalid secret binding for {name}")
            if actual_binding != expected_secret_bindings[name]:
                raise JITQAContractError(f"Cloud Run resource has an unexpected secret binding for {name}")
        elif name in expected_environment:
            if set(entry) != {"name", "value"} or entry.get("value") != expected_environment[name]:
                raise JITQAContractError(f"Cloud Run resource has an unexpected value for {name}")
        else:
            # A replacement env update is intentional: silently retaining a
            # queue/cache/customer binding would break the isolation proof.
            raise JITQAContractError(f"Cloud Run resource has an unapproved environment entry for {name}")
    missing = expected_names - seen_names
    if missing:
        raise JITQAContractError(f"Cloud Run resource is missing required environment entries: {sorted(missing)}")

    spec = resource.get("spec")
    if not isinstance(spec, Mapping):
        raise JITQAContractError("Cloud Run resource has no v2 spec")
    if kind == "service":
        template = spec.get("template")
    else:
        template = spec.get("template", {}).get("template") if isinstance(spec.get("template"), Mapping) else None
    if not isinstance(template, Mapping):
        raise JITQAContractError("Cloud Run resource has no v2 service template")
    service_account = template.get("serviceAccountName", template.get("serviceAccount"))
    if service_account is None and isinstance(template.get("spec"), Mapping):
        service_spec = template["spec"]
        service_account = service_spec.get("serviceAccountName", service_spec.get("serviceAccount"))
    if service_account != expected_service_account:
        raise JITQAContractError("Cloud Run resource uses an unexpected runtime service account")


def resource_environment(profile: str) -> tuple[dict[str, str], dict[str, str]]:
    """Return the exact literal and Secret Manager bindings for a QA profile."""

    identity = {
        "OMI_ENV_STAGE": "dev",
        "GOOGLE_CLOUD_PROJECT": PROJECT_ID,
        "OMI_FIRESTORE_DATA_PLANE_PROJECT": PROJECT_ID,
        "FIREBASE_AUTH_PROJECT_ID": AUTH_PROJECT_ID,
    }
    if profile in {"backend", "desktop"}:
        return (
            {
                **identity,
                "MEMORY_ENABLED": "on",
                "MEMORY_BELIEF_MODEL_ENABLED": "true",
                # The gateway/companion plane is admitted separately.  Direct
                # mode keeps this service isolated if that plane is absent.
                "OMI_LLM_GATEWAY_FEATURE_MODE": "direct",
                "OMI_LLM_CHAT_AGENT_ROUTE": "direct",
            },
            dict(_ALLOWED_SECRET_BINDINGS),
        )
    if profile == "drain":
        return (
            {
                **identity,
                "KNOWLEDGE_LEDGER_DRAIN_ENABLED": "false",
                "KNOWLEDGE_LEDGER_DRAIN_UID_ALLOWLIST": QA_UID,
            },
            {"ENCRYPTION_SECRET": _ALLOWED_SECRET_BINDINGS["ENCRYPTION_SECRET"]},
        )
    if profile == "sweep":
        return (
            {
                **identity,
                "MEMORY_DAILY_MEMORY_SWEEP_ENABLED": "false",
                "MEMORY_DAILY_MEMORY_SWEEP_KILL_SWITCH": "false",
                "MEMORY_DAILY_MEMORY_SWEEP_MODEL_ENABLED": "false",
                "MEMORY_DAILY_MEMORY_SWEEP_MODEL_NAME": "disabled",
                "MEMORY_DAILY_MEMORY_SWEEP_MAX_MODEL_CANDIDATES": "8",
                "MEMORY_DAILY_MEMORY_SWEEP_MAX_MODEL_COST_USD": "0",
                "MEMORY_DAILY_MEMORY_SWEEP_COHORT_ENABLED": "false",
                "MEMORY_DAILY_MEMORY_SWEEP_COHORT_FLAG": "",
            },
            dict(_ALLOWED_SECRET_BINDINGS),
        )
    raise JITQAContractError(f"unknown QA resource profile {profile!r}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate", "environment", "execution", "resource"))
    parser.add_argument("--project", default=PROJECT_ID)
    parser.add_argument("--region", default=REGION)
    parser.add_argument("--auth-project", default=AUTH_PROJECT_ID)
    parser.add_argument("--uid", default=QA_UID)
    parser.add_argument("--drain-enabled", default="false")
    parser.add_argument("--sweep-enabled", default="false")
    parser.add_argument("--sweep-kill-switch", default="false")
    parser.add_argument("--run-once", default="false", choices=("true", "false"))
    parser.add_argument("--confirmation", default="")
    parser.add_argument("--image", action="append", default=[], metavar="NAME=IMAGE")
    parser.add_argument("--environment-json", type=Path)
    parser.add_argument("--resource-json", type=Path)
    parser.add_argument("--kind", choices=("service", "job"))
    parser.add_argument("--profile", choices=("backend", "desktop", "drain", "sweep"))
    parser.add_argument("--expected-image")
    parser.add_argument("--expected-name")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        if args.command == "validate":
            images: dict[str, str] = {}
            for item in args.image:
                name, separator, image = item.partition("=")
                if not separator or not name:
                    raise JITQAContractError("--image must be NAME=IMAGE")
                images[name] = image
            validate_static_configuration(
                project=args.project,
                region=args.region,
                auth_project=args.auth_project,
                uid=args.uid,
                drain_enabled=args.drain_enabled,
                sweep_enabled=args.sweep_enabled,
                sweep_kill_switch=args.sweep_kill_switch,
                run_once=args.run_once,
                confirmation=args.confirmation,
                images=images or None,
            )
        elif args.command == "environment":
            if args.environment_json is None:
                raise JITQAContractError("--environment-json is required")
            environment = json.loads(args.environment_json.read_text(encoding="utf-8"))
            if not isinstance(environment, dict):
                raise JITQAContractError("environment JSON must be an object")
            validate_environment(environment)
        elif args.command == "execution":
            validate_execution(
                run_once=args.run_once,
                confirmation=args.confirmation,
                kill_switch=args.sweep_kill_switch,
            )
        else:
            if args.resource_json is None or args.kind is None or args.expected_image is None:
                raise JITQAContractError("resource validation requires --resource-json, --kind, and --expected-image")
            resource = json.loads(args.resource_json.read_text(encoding="utf-8"))
            if not isinstance(resource, dict):
                raise JITQAContractError("Cloud Run resource JSON must be an object")
            if args.profile is None:
                raise JITQAContractError("resource validation requires --profile")
            expected_environment, expected_secret_bindings = resource_environment(args.profile)
            validate_cloud_run_resource(
                resource,
                kind=args.kind,
                expected_image=args.expected_image,
                expected_environment=expected_environment,
                expected_secret_bindings=expected_secret_bindings,
                expected_name=args.expected_name,
            )
    except (JITQAContractError, OSError, json.JSONDecodeError) as exc:
        print(f"JIT QA contract failed: {exc}", file=sys.stderr)
        return 1
    print("JIT QA contract passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
