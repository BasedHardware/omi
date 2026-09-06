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
FIRESTORE_DATABASE_ID = "jit-qa"

BACKEND_SERVICE = "backend-jit-qa"
DESKTOP_BACKEND_SERVICE = "desktop-backend-jit-qa"
LEDGER_DRAIN_JOB = "knowledge-ledger-drain-qa-job"
DAILY_SWEEP_JOB = "daily-memory-sweep-qa-job"
LLM_GATEWAY_SERVICE = "llm-gateway-jit-qa"

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
DEFAULT_GATEWAY_URL = "https://llm-gateway-jit-qa.invalid"
DEFAULT_REDIS_HOST = "10.0.0.10"

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
    # Rollout admission is a real PostHog control-plane read.  Keep the
    # project key as an individually approved dev secret; never copy the
    # normal customer-data secret bundle into this plane.
    "POSTHOG_PROJECT_API_KEY": "POSTHOG_PROJECT_API_KEY:latest",
    "REDIS_DB_PASSWORD": "jit-qa-redis-password:latest",
    "OMI_LLM_GATEWAY_SERVICE_TOKEN": "jit-qa-gateway-token:latest",
}
_GATEWAY_SECRET_BINDINGS = {
    "OPENAI_API_KEY": "OPENAI_API_KEY:latest",
    "ANTHROPIC_API_KEY": "ANTHROPIC_API_KEY:latest",
    "PERPLEXITY_API_KEY": "PERPLEXITY_API_KEY:latest",
    "OMI_LLM_GATEWAY_SERVICE_TOKEN": "jit-qa-gateway-token:latest",
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
    expected = {"backend", "desktop", "gateway", "drain", "sweep"}
    if images is None or set(images) != expected:
        raise JITQAContractError(f"exactly these QA images are required: {sorted(expected)}")
    for name, image in images.items():
        require_digest_image(image, label=f"{name} image")


def validate_environment(environment: Mapping[str, str], *, profile: str) -> None:
    """Reject credential selectors and non-QA runtime identity values."""

    for name in _FORBIDDEN_CREDENTIAL_ENV:
        if environment.get(name, "").strip():
            raise JITQAContractError(f"{name} is forbidden on the isolated QA plane")
    expected = {
        "GOOGLE_CLOUD_PROJECT": PROJECT_ID,
        "OMI_FIRESTORE_DATA_PLANE_PROJECT": PROJECT_ID,
        "FIRESTORE_DATABASE_ID": FIRESTORE_DATABASE_ID,
        "FIREBASE_AUTH_PROJECT_ID": AUTH_PROJECT_ID,
        "OMI_ENV_STAGE": "dev",
    }
    for name, value in expected.items():
        if environment.get(name) != value:
            raise JITQAContractError(f"{name} must be {value}")
    try:
        expected_profile = resource_environment(profile)[0]
    except JITQAContractError:
        raise
    if profile == "drain":
        if environment.get("KNOWLEDGE_LEDGER_DRAIN_UID_ALLOWLIST") != QA_UID:
            raise JITQAContractError("ledger drain allowlist must contain only the QA UID")
    elif environment.get("KNOWLEDGE_LEDGER_DRAIN_UID_ALLOWLIST"):
        raise JITQAContractError("ledger drain allowlist is only valid on the drain profile")
    if expected_profile.get("KNOWLEDGE_LEDGER_DRAIN_UID_ALLOWLIST") != environment.get(
        "KNOWLEDGE_LEDGER_DRAIN_UID_ALLOWLIST"
    ):
        raise JITQAContractError(f"environment does not match the {profile} QA profile")


def validate_qa_http_environment(environment: Mapping[str, str], *, gateway_url: str, redis_host: str) -> None:
    """Require the isolated HTTP service to use the QA auth, gateway and cache."""

    expected = {
        "OMI_JIT_QA_AUTH_ONLY": "true",
        "OMI_JIT_QA_UID_ALLOWLIST": QA_UID,
        "OMI_LLM_GATEWAY_FEATURE_MODE": "gateway",
        "OMI_LLM_CHAT_AGENT_ROUTE": "gateway",
        "OMI_LLM_GATEWAY_ALLOW_DIRECT_MODEL_EXCEPTION": "false",
        "OMI_LLM_GATEWAY_URL": gateway_url,
        "REDIS_DB_HOST": redis_host,
        "REDIS_DB_PORT": "6379",
    }
    for name, value in expected.items():
        if environment.get(name) != value:
            raise JITQAContractError(f"{name} must be the isolated QA value")


def validate_execution(*, run_once: str, confirmation: str, kill_switch: str = "false") -> None:
    """Admit one explicit bounded execution without opening a persistent gate."""

    if run_once != "true":
        raise JITQAContractError("one-shot execution was not explicitly requested")
    if confirmation != RUN_ONCE_CONFIRMATION:
        raise JITQAContractError(f"one-shot execution requires confirmation {RUN_ONCE_CONFIRMATION!r}")
    if kill_switch != "false":
        raise JITQAContractError("one-shot execution requires the sweep kill switch to remain false")


def _containers(resource: Mapping[str, Any], *, kind: str) -> list[Mapping[str, Any]]:
    if kind == "service":
        paths = (("spec", "template", "spec", "containers"), ("spec", "template", "containers"))
    elif kind == "job":
        paths = (
            ("spec", "template", "spec", "template", "spec", "containers"),
            ("spec", "template", "spec", "template", "containers"),
            ("spec", "template", "template", "spec", "containers"),
            ("spec", "template", "template", "containers"),
        )
    else:
        raise JITQAContractError(f"unknown Cloud Run resource kind {kind!r}")
    value: object = None
    for path in paths:
        candidate: object = resource
        for key in path:
            if not isinstance(candidate, Mapping):
                candidate = None
                break
            candidate = candidate.get(key)
        if candidate is not None:
            value = candidate
            break
    if value is None:
        raise JITQAContractError(f"Cloud Run {kind} has no supported v1/v2 container contract")
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
    gateway_url: str | None = None,
    redis_host: str | None = None,
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
    if kind == "service" and gateway_url is not None and redis_host is not None:
        actual_environment = {
            str(entry["name"]): str(entry.get("value", ""))
            for entry in container.get("env", [])
            if isinstance(entry, dict) and "name" in entry and "value" in entry
        }
        validate_qa_http_environment(actual_environment, gateway_url=gateway_url, redis_host=redis_host)

    spec = resource.get("spec")
    if not isinstance(spec, Mapping):
        raise JITQAContractError("Cloud Run resource has no v2 spec")
    if kind == "service":
        templates = [spec.get("template")]
    else:
        outer = spec.get("template")
        templates = []
        if isinstance(outer, Mapping):
            templates.extend(
                [outer.get("spec", {}).get("template") if isinstance(outer.get("spec"), Mapping) else None]
            )
            templates.extend([outer.get("template")])
    templates = [template for template in templates if isinstance(template, Mapping)]
    if not templates:
        raise JITQAContractError("Cloud Run resource has no v2 service template")
    service_account = None
    for template in templates:
        service_account = template.get("serviceAccountName", template.get("serviceAccount"))
        if service_account is None and isinstance(template.get("spec"), Mapping):
            service_spec = template["spec"]
            service_account = service_spec.get("serviceAccountName", service_spec.get("serviceAccount"))
        if service_account is not None:
            break
    if service_account != expected_service_account:
        raise JITQAContractError("Cloud Run resource uses an unexpected runtime service account")


def resource_environment(
    profile: str,
    *,
    gateway_url: str = DEFAULT_GATEWAY_URL,
    redis_host: str = DEFAULT_REDIS_HOST,
) -> tuple[dict[str, str], dict[str, str]]:
    """Return the exact literal and Secret Manager bindings for a QA profile."""

    identity = {
        "OMI_ENV_STAGE": "dev",
        "GOOGLE_CLOUD_PROJECT": PROJECT_ID,
        "OMI_FIRESTORE_DATA_PLANE_PROJECT": PROJECT_ID,
        "FIRESTORE_DATABASE_ID": FIRESTORE_DATABASE_ID,
        "FIREBASE_AUTH_PROJECT_ID": AUTH_PROJECT_ID,
    }
    if profile in {"backend", "desktop"}:
        return (
            {
                **identity,
                "MEMORY_ENABLED": "on",
                "MEMORY_BELIEF_MODEL_ENABLED": "true",
                "OMI_JIT_QA_AUTH_ONLY": "true",
                "OMI_JIT_QA_UID_ALLOWLIST": QA_UID,
                "OMI_LLM_GATEWAY_FEATURE_MODE": "gateway",
                "OMI_LLM_CHAT_AGENT_ROUTE": "gateway",
                "OMI_LLM_GATEWAY_ALLOW_DIRECT_MODEL_EXCEPTION": "false",
                "OMI_LLM_GATEWAY_URL": gateway_url,
                "REDIS_DB_HOST": redis_host,
                "REDIS_DB_PORT": "6379",
            },
            dict(_ALLOWED_SECRET_BINDINGS),
        )
    if profile == "gateway":
        return (
            {
                **identity,
                "OMI_JIT_QA_AUTH_ONLY": "true",
                "OMI_JIT_QA_UID_ALLOWLIST": QA_UID,
                "OMI_LLM_GATEWAY_PROD": "false",
                "LLM_GATEWAY_ALLOWED_CALLERS": "backend,desktop",
                "OMI_LLM_GATEWAY_BUILD_IDENTITY": "jit-qa",
            },
            {
                **_GATEWAY_SECRET_BINDINGS,
            },
        )
    if profile == "drain":
        return (
            {
                **identity,
                "MEMORY_ENABLED": "on",
                "KNOWLEDGE_LEDGER_DRAIN_ENABLED": "false",
                "KNOWLEDGE_LEDGER_DRAIN_UID_ALLOWLIST": QA_UID,
                "OMI_JIT_QA_AUTH_ONLY": "true",
                "OMI_JIT_QA_UID_ALLOWLIST": QA_UID,
            },
            {
                "ENCRYPTION_SECRET": _ALLOWED_SECRET_BINDINGS["ENCRYPTION_SECRET"],
                "POSTHOG_PROJECT_API_KEY": _ALLOWED_SECRET_BINDINGS["POSTHOG_PROJECT_API_KEY"],
            },
        )
    if profile == "sweep":
        return (
            {
                **identity,
                "MEMORY_ENABLED": "on",
                "MEMORY_DAILY_MEMORY_SWEEP_ENABLED": "false",
                "MEMORY_DAILY_MEMORY_SWEEP_KILL_SWITCH": "false",
                "MEMORY_DAILY_MEMORY_SWEEP_MODEL_ENABLED": "false",
                "MEMORY_DAILY_MEMORY_SWEEP_MODEL_NAME": "disabled",
                "MEMORY_DAILY_MEMORY_SWEEP_MAX_MODEL_CANDIDATES": "8",
                "MEMORY_DAILY_MEMORY_SWEEP_MAX_MODEL_COST_USD": "0",
                "MEMORY_DAILY_MEMORY_SWEEP_COHORT_ENABLED": "false",
                "MEMORY_DAILY_MEMORY_SWEEP_COHORT_FLAG": "",
                "OMI_JIT_QA_AUTH_ONLY": "true",
                "OMI_JIT_QA_UID_ALLOWLIST": QA_UID,
                "OMI_LLM_GATEWAY_FEATURE_MODE": "gateway",
                "OMI_LLM_CHAT_AGENT_ROUTE": "gateway",
                "OMI_LLM_GATEWAY_ALLOW_DIRECT_MODEL_EXCEPTION": "false",
                "OMI_LLM_GATEWAY_URL": gateway_url,
                "REDIS_DB_HOST": redis_host,
                "REDIS_DB_PORT": "6379",
            },
            {
                "ENCRYPTION_SECRET": _ALLOWED_SECRET_BINDINGS["ENCRYPTION_SECRET"],
                "POSTHOG_PROJECT_API_KEY": _ALLOWED_SECRET_BINDINGS["POSTHOG_PROJECT_API_KEY"],
                "REDIS_DB_PASSWORD": _ALLOWED_SECRET_BINDINGS["REDIS_DB_PASSWORD"],
                "OMI_LLM_GATEWAY_SERVICE_TOKEN": _ALLOWED_SECRET_BINDINGS["OMI_LLM_GATEWAY_SERVICE_TOKEN"],
            },
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
    parser.add_argument("--profile", choices=("backend", "desktop", "gateway", "drain", "sweep"))
    parser.add_argument("--expected-image")
    parser.add_argument("--expected-name")
    parser.add_argument("--gateway-url", default=DEFAULT_GATEWAY_URL)
    parser.add_argument("--redis-host", default=DEFAULT_REDIS_HOST)
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
                images=images,
            )
        elif args.command == "environment":
            if args.environment_json is None:
                raise JITQAContractError("--environment-json is required")
            environment = json.loads(args.environment_json.read_text(encoding="utf-8"))
            if not isinstance(environment, dict):
                raise JITQAContractError("environment JSON must be an object")
            if args.profile is None:
                raise JITQAContractError("environment validation requires --profile")
            validate_environment(environment, profile=args.profile)
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
            expected_environment, expected_secret_bindings = resource_environment(
                args.profile, gateway_url=args.gateway_url, redis_host=args.redis_host
            )
            validate_cloud_run_resource(
                resource,
                kind=args.kind,
                expected_image=args.expected_image,
                expected_environment=expected_environment,
                expected_secret_bindings=expected_secret_bindings,
                expected_name=args.expected_name,
                gateway_url=args.gateway_url if args.profile in {"backend", "desktop"} else None,
                redis_host=args.redis_host if args.profile in {"backend", "desktop"} else None,
            )
    except (JITQAContractError, OSError, json.JSONDecodeError) as exc:
        print(f"JIT QA contract failed: {exc}", file=sys.stderr)
        return 1
    print("JIT QA contract passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
