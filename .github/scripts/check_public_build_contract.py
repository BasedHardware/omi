#!/usr/bin/env python3
"""Verify browser-build deploy wiring against the canonical checked-in contract."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONTRACT = ROOT / "config" / "public-build-contract.json"
DEFAULT_VALUES = ROOT / "config" / "public-build-values.json"
DEFAULT_CLASSIFICATION = ROOT / "config" / "deployment-setting-classification.json"
NAME = re.compile(r"[A-Z][A-Z0-9_]*\Z")
SECRET_REFERENCE = re.compile(r"[A-Za-z0-9_-]+:(?:latest|[1-9][0-9]*)\Z")
ARG = re.compile(r"^\s*ARG\s+([A-Z][A-Z0-9_]*)\s*$", re.MULTILINE)
GUARD = re.compile(r'^\s*ENV\s+OMI_REQUIRED_PUBLIC_BUILD_INPUTS="([A-Z0-9_ ]*)"\s*$', re.MULTILINE)
REVISION_IDENTITY_ARGS = frozenset({"NEXT_PUBLIC_OMI_BUILD_SHA"})
WEB_WORKFLOWS = frozenset(
    {
        ".github/workflows/gcp_admin.yml",
        ".github/workflows/gcp_app.yml",
        ".github/workflows/gcp_frontend.yml",
        ".github/workflows/gcp_personas.yml",
    }
)
DEPLOY_ACTION = "uses: ./.github/actions/deploy-public-build"
PREPARE_ACTION = "uses: ./.github/actions/prepare-public-build"
PROMOTION_ACTION = "uses: ./.github/actions/public-build-candidate-promotion"
DEPLOY_ACTION_PATH = ".github/actions/deploy-public-build/action.yml"
PREPARE_ACTION_PATH = ".github/actions/prepare-public-build/action.yml"
PROMOTION_ACTION_PATH = ".github/actions/public-build-candidate-promotion/action.yml"
JIT_PREFLIGHT_WORKFLOW_PATH = ".github/workflows/public-build-config-preflight.yml"
MANUAL_ENVIRONMENT_INPUT = """workflow_dispatch:
    inputs:
      environment:
        description: 'Environment to deploy to'
        required: false
        default: 'prod'
        type: choice
        options: [development, prod]"""
DEPLOY_ENVIRONMENT_EXPRESSION = (
    "github.event_name == 'workflow_dispatch' && github.event.inputs.environment || "
    "(github.ref == 'refs/heads/development' && 'development') || 'prod'"
)
CONCURRENCY_ENVIRONMENT_EXPRESSION = (
    "github.event_name == 'workflow_dispatch' && github.event.inputs.environment || "
    "github.ref == 'refs/heads/development' && 'development' || "
    "github.ref == 'refs/heads/main' && 'prod' || format('nondeploy-{0}', github.run_id)"
)


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
    # environment -> absolute HTTPS URL served by the load balancer in front of
    # the service. Required for any environment whose ingress hides the tagged
    # candidate URL from CI; see acceptance_route().
    public_urls: dict[str, str] = field(default_factory=dict)


# Cloud Run ingress values under which the tagged run.app candidate URL answers
# to CI. Every other value (internal, internal-and-cloud-load-balancing) makes
# the tagged URL 404 for CI regardless of authentication.
OPEN_INGRESS = frozenset({"", "all"})


@dataclass(frozen=True)
class AcceptanceRoute:
    route: str  # "candidate_url" or "public_url"
    public_url: str = ""


def _parse_public_urls(raw: Any, *, target_name: str, environments: Iterable[str]) -> dict[str, str]:
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        raise ValueError(f"target {target_name} candidate public_urls must be an object")
    known = set(environments)
    public_urls: dict[str, str] = {}
    for environment, url in raw.items():
        if environment not in known:
            raise ValueError(f"target {target_name} candidate public_urls names unknown environment {environment!r}")
        if not isinstance(url, str) or not url.startswith("https://") or url != url.strip() or url.endswith("/"):
            raise ValueError(
                f"target {target_name} candidate public_urls[{environment!r}] must be an absolute HTTPS URL without a trailing slash"
            )
        public_urls[environment] = url
    return public_urls


def acceptance_route(target: Target, *, environment: str, ingress: str) -> AcceptanceRoute:
    """Decide how CI can observe a candidate for browser acceptance.

    Open ingress: smoke the no-traffic candidate through its tagged URL before
    promotion. Restricted ingress: the tagged URL is unreachable, so the
    candidate can only be observed through the declared public URL after it
    holds traffic; the promotion action smokes it there and rolls back on
    failure. Restricted ingress without a declared public URL is refused here
    with its real cause instead of surfacing later as a canary that never
    became ready.
    """

    normalized = ingress.strip()
    if normalized in OPEN_INGRESS:
        return AcceptanceRoute(route="candidate_url")
    public_url = target.candidate_acceptance.public_urls.get(environment, "")
    if not public_url:
        raise ValueError(
            f"target {target.name}: ingress {normalized!r} hides the tagged candidate URL from CI and "
            f"candidate_acceptance.public_urls declares no {environment!r} URL to smoke after promotion"
        )
    return AcceptanceRoute(route="public_url", public_url=public_url)


def serving_revision(service_document: Mapping[str, Any]) -> str:
    """Return the revision holding the largest traffic share, or "" when none does."""

    status = service_document.get("status")
    traffic = status.get("traffic") if isinstance(status, Mapping) else None
    best_name, best_percent = "", 0
    for entry in traffic or ():
        if not isinstance(entry, Mapping):
            continue
        name = entry.get("revisionName")
        percent = entry.get("percent")
        if isinstance(name, str) and name and isinstance(percent, int) and percent > best_percent:
            best_name, best_percent = name, percent
    return best_name


@dataclass(frozen=True)
class Deployment:
    region: str
    build_context: str
    platforms: tuple[str, ...]
    flags_by_environment: dict[str, tuple[str, ...]]
    runtime_secrets: dict[str, str]
    preserve_runtime_secrets: tuple[str, ...]
    fallback_runtime_secrets: dict[str, str]
    runtime_env_vars: dict[str, str]
    remove_runtime_secrets: tuple[str, ...]
    remove_runtime_env_vars: tuple[str, ...]

    def flags_for(self, environment: str) -> tuple[str, ...]:
        """Return the gcloud flags that apply to one declared environment."""

        return self.flags_by_environment.get(environment, ())


@dataclass(frozen=True)
class Target:
    name: str
    service: str
    dockerfile: str
    workflow: str
    gateway_required: bool
    deployment: Deployment
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


def _parse_flag_list(raw_flags: Any, *, target_name: str, where: str) -> tuple[str, ...]:
    if not isinstance(raw_flags, list) or not all(
        isinstance(flag, str) and flag.startswith("--") and "\n" not in flag and "\r" not in flag for flag in raw_flags
    ):
        raise ValueError(f"target {target_name} {where} must be safe gcloud flags")
    return tuple(raw_flags)


def _parse_flags(raw_flags: Any, *, target_name: str, environments: tuple[str, ...]) -> dict[str, tuple[str, ...]]:
    """Accept a shared flag list or an object keyed by declared environment."""

    if isinstance(raw_flags, list):
        flags = _parse_flag_list(raw_flags, target_name=target_name, where="deployment flags")
        return {environment: flags for environment in environments}
    if isinstance(raw_flags, Mapping):
        unknown = sorted(str(environment) for environment in raw_flags if environment not in environments)
        if unknown:
            raise ValueError(f"target {target_name} deployment flags names unknown environment {unknown[0]!r}")
        parsed = {environment: () for environment in environments}
        for environment, env_flags in raw_flags.items():
            if not isinstance(environment, str) or not environment:
                raise ValueError(f"target {target_name} deployment flags must be keyed by environment name")
            parsed[environment] = _parse_flag_list(
                env_flags, target_name=target_name, where=f"deployment flags[{environment!r}]"
            )
        return parsed
    raise ValueError(f"target {target_name} deployment flags must be a list or an object keyed by environment")


def _parse_env_name_list(raw_names: Any, *, target_name: str, field: str) -> tuple[str, ...]:
    if not isinstance(raw_names, list) or not all(isinstance(name, str) and NAME.fullmatch(name) for name in raw_names):
        raise ValueError(f"target {target_name} deployment {field} must be environment names")
    if len(set(raw_names)) != len(raw_names):
        raise ValueError(f"target {target_name} deployment {field} must be unique")
    return tuple(raw_names)


def _parse_deployment(raw_deployment: Any, *, target_name: str, environments: tuple[str, ...]) -> Deployment:
    if not isinstance(raw_deployment, Mapping):
        raise ValueError(f"target {target_name} must declare deployment")
    region = _require_string(raw_deployment.get("region"), field=f"target {target_name} deployment region")
    build_context = _require_string(
        raw_deployment.get("build_context"), field=f"target {target_name} deployment build_context"
    )
    raw_platforms = raw_deployment.get("platforms")
    if (
        not isinstance(raw_platforms, list)
        or not raw_platforms
        or not all(isinstance(platform, str) and platform for platform in raw_platforms)
    ):
        raise ValueError(f"target {target_name} deployment platforms must be non-empty strings")
    flags_by_environment = _parse_flags(raw_deployment.get("flags"), target_name=target_name, environments=environments)
    raw_runtime_secrets = raw_deployment.get("runtime_secrets")
    if not isinstance(raw_runtime_secrets, Mapping) or not all(
        isinstance(name, str)
        and NAME.fullmatch(name)
        and isinstance(reference, str)
        and SECRET_REFERENCE.fullmatch(reference)
        for name, reference in raw_runtime_secrets.items()
    ):
        raise ValueError(
            f"target {target_name} deployment runtime_secrets must map environment names to secret:version"
        )

    raw_preserve_runtime_secrets = raw_deployment.get("preserve_runtime_secrets", [])
    if not isinstance(raw_preserve_runtime_secrets, list) or not all(
        isinstance(name, str) and NAME.fullmatch(name) for name in raw_preserve_runtime_secrets
    ):
        raise ValueError(f"target {target_name} deployment preserve_runtime_secrets must be environment names")
    if len(set(raw_preserve_runtime_secrets)) != len(raw_preserve_runtime_secrets):
        raise ValueError(f"target {target_name} deployment preserve_runtime_secrets must be unique")

    raw_fallback_runtime_secrets = raw_deployment.get("fallback_runtime_secrets", {})
    if not isinstance(raw_fallback_runtime_secrets, Mapping) or not all(
        isinstance(name, str)
        and NAME.fullmatch(name)
        and isinstance(reference, str)
        and SECRET_REFERENCE.fullmatch(reference)
        for name, reference in raw_fallback_runtime_secrets.items()
    ):
        raise ValueError(
            f"target {target_name} deployment fallback_runtime_secrets must map environment names to secret:version"
        )
    if set(raw_fallback_runtime_secrets) != set(raw_preserve_runtime_secrets):
        raise ValueError(
            f"target {target_name} deployment fallback_runtime_secrets must declare exactly the preserved runtime secrets"
        )

    raw_runtime_env_vars = raw_deployment.get("runtime_env_vars", {})
    if not isinstance(raw_runtime_env_vars, Mapping) or not all(
        isinstance(name, str)
        and NAME.fullmatch(name)
        and isinstance(value, str)
        and value
        and value == value.strip()
        and not any(character in value for character in ("\\", ",", "\n", "\r", "\x00", "\u2028", "\u2029"))
        for name, value in raw_runtime_env_vars.items()
    ):
        raise ValueError(
            f"target {target_name} deployment runtime_env_vars must map environment names to non-empty deploy-safe values"
        )

    raw_remove_runtime_secrets = _parse_env_name_list(
        raw_deployment.get("remove_runtime_secrets", []),
        target_name=target_name,
        field="remove_runtime_secrets",
    )
    raw_remove_runtime_env_vars = _parse_env_name_list(
        raw_deployment.get("remove_runtime_env_vars", []),
        target_name=target_name,
        field="remove_runtime_env_vars",
    )
    # preserve_runtime_secrets are retained by the merge update strategies, so a
    # removal emitted for the same runtime name would strip the preserved
    # binding (env-var names and secret bindings share one runtime namespace).
    # fallback_runtime_secrets is validated to mirror preserve_runtime_secrets.
    env_var_removal_overlaps = set(raw_remove_runtime_env_vars) & (
        set(raw_runtime_secrets)
        | set(raw_runtime_env_vars)
        | set(raw_preserve_runtime_secrets)
        | set(raw_fallback_runtime_secrets)
    )
    if env_var_removal_overlaps:
        raise ValueError(
            f"target {target_name} deployment remove_runtime_env_vars cannot overlap runtime_secrets, "
            f"runtime_env_vars, preserve_runtime_secrets, or fallback_runtime_secrets: "
            f"{', '.join(sorted(env_var_removal_overlaps))}"
        )

    binding_groups = {
        "runtime_secrets": set(raw_runtime_secrets),
        "preserve_runtime_secrets": set(raw_preserve_runtime_secrets),
        "runtime_env_vars": set(raw_runtime_env_vars),
        "remove_runtime_secrets": set(raw_remove_runtime_secrets),
    }
    fallback_overlaps = set(raw_fallback_runtime_secrets) & (
        set(raw_runtime_secrets) | set(raw_runtime_env_vars) | set(raw_remove_runtime_secrets)
    )
    if fallback_overlaps:
        raise ValueError(
            f"target {target_name} deployment runtime binding groups cannot overlap: fallback_runtime_secrets and other "
            f"runtime bindings: "
            f"{', '.join(sorted(fallback_overlaps))}"
        )
    group_names = tuple(binding_groups)
    overlaps = [
        f"{left} and {right}: {', '.join(sorted(binding_groups[left] & binding_groups[right]))}"
        for index, left in enumerate(group_names)
        for right in group_names[index + 1 :]
        if binding_groups[left] & binding_groups[right]
    ]
    if overlaps:
        raise ValueError(
            f"target {target_name} deployment runtime binding groups cannot overlap: {'; '.join(overlaps)}"
        )
    return Deployment(
        region=region,
        build_context=build_context,
        platforms=tuple(raw_platforms),
        flags_by_environment=flags_by_environment,
        runtime_secrets=dict(raw_runtime_secrets),
        preserve_runtime_secrets=tuple(raw_preserve_runtime_secrets),
        fallback_runtime_secrets=dict(raw_fallback_runtime_secrets),
        runtime_env_vars=dict(raw_runtime_env_vars),
        remove_runtime_secrets=raw_remove_runtime_secrets,
        remove_runtime_env_vars=raw_remove_runtime_env_vars,
    )


def load_contract(path: Path) -> Contract:
    raw = _read_json(path)
    if not isinstance(raw, Mapping) or raw.get("schema_version") != 4:
        raise ValueError(f"{path}: unsupported public-build contract schema")
    configuration = raw.get("configuration")
    if not isinstance(configuration, Mapping) or configuration.get("source") != "repository_config":
        raise ValueError(f"{path}: configuration source must be repository_config")
    config_path = _require_string(configuration.get("path"), field=f"{path}: configuration path")
    raw_environments = configuration.get("environments")
    if (
        not isinstance(raw_environments, list)
        or not raw_environments
        or not all(isinstance(environment, str) and environment for environment in raw_environments)
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
        if "{sha}" in command and "--expect-sha" not in command:
            raise ValueError(f"{path}: target {target_name} candidate command uses {{sha}} without --expect-sha")
        gateway_required = raw_target.get("gateway_required", False)
        if not isinstance(gateway_required, bool):
            raise ValueError(f"target {target_name} gateway_required must be boolean")
        targets[target_name] = Target(
            name=target_name,
            service=_require_string(raw_target.get("service"), field=f"target {target_name} service"),
            dockerfile=_require_string(raw_target.get("dockerfile"), field=f"target {target_name} dockerfile"),
            workflow=_require_string(raw_target.get("workflow"), field=f"target {target_name} workflow"),
            gateway_required=gateway_required,
            deployment=_parse_deployment(
                raw_target.get("deployment"), target_name=target_name, environments=environments
            ),
            canary_component=_require_string(
                raw_target.get("canary_component"), field=f"target {target_name} canary_component"
            ),
            inputs=inputs,
            candidate_acceptance=CandidateAcceptance(
                command=tuple(command),
                marker=_require_string(acceptance.get("marker"), field="candidate marker"),
                public_urls=_parse_public_urls(
                    acceptance.get("public_urls"), target_name=target_name, environments=environments
                ),
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


def render_acceptance_command(
    command: Sequence[str],
    *,
    base_url: str,
    sha: str = "",
) -> tuple[str, ...]:
    """Replace {base_url} and {sha} in a candidate_acceptance.command template.

    Targets that omit {sha} are unchanged even when a sha is supplied. A template
    that declares {sha} requires a non-empty sha so the rendered argv cannot drop
    the revision identity the smoke is supposed to assert.
    """
    if "{sha}" in command and not sha:
        raise ValueError("candidate command requires {sha}")
    return tuple(part.replace("{base_url}", base_url).replace("{sha}", sha) for part in command)


def deployment_setting_names(classification_path: Path) -> dict[str, set[str]]:
    raw = _read_json(classification_path)
    try:
        kinds = raw["kinds"]
    except (KeyError, TypeError) as exc:
        raise ValueError(f"{classification_path}: kinds must be an object") from exc
    if not isinstance(kinds, Mapping):
        raise ValueError(f"{classification_path}: kinds must be an object")
    names_by_kind: dict[str, set[str]] = {}
    for kind in ("config", "public_build"):
        names = kinds.get(kind)
        if not isinstance(names, list) or not all(isinstance(name, str) for name in names):
            raise ValueError(f"{classification_path}: kinds.{kind} must be a list")
        names_by_kind[kind] = set(names)
    return names_by_kind


def public_build_names(classification_path: Path) -> set[str]:
    return deployment_setting_names(classification_path)["public_build"]


def _docker_public_args(text: str, classified_public: set[str]) -> set[str]:
    return {
        name
        for name in ARG.findall(text)
        if (name.startswith("NEXT_PUBLIC_") or name in classified_public) and name not in REVISION_IDENTITY_ARGS
    }


def _guarded_names(text: str) -> set[str]:
    match = GUARD.search(text)
    return set() if match is None else set(match.group(1).split())


def resolved_deploy_environment(*, event_name: str, ref: str, requested_environment: str | None = None) -> str:
    """Model the workflow expression used by every browser-build deploy target."""
    if event_name == "workflow_dispatch":
        if requested_environment not in {"development", "prod"}:
            raise ValueError("workflow_dispatch must select development or prod")
        return requested_environment
    return "development" if ref == "refs/heads/development" else "prod"


def validate_manual_environment_dispatch(workflow_path: str, workflow: str) -> list[str]:
    """Keep exact-head manual deployments bound to their selected environment."""
    errors: list[str] = []
    if MANUAL_ENVIRONMENT_INPUT not in workflow:
        errors.append(f"{workflow_path}: must expose the shared environment workflow_dispatch choice")
    expected_environment = f"environment: ${{{{ {DEPLOY_ENVIRONMENT_EXPRESSION} }}}}"
    if workflow.count(expected_environment) < 2:
        errors.append(
            f"{workflow_path}: job and deploy action must select environment from workflow_dispatch before ref"
        )
    if CONCURRENCY_ENVIRONMENT_EXPRESSION not in workflow:
        errors.append(f"{workflow_path}: concurrency must select environment from workflow_dispatch before ref")
    return errors


def validate_target(
    root: Path,
    target: Target,
    classified_public: set[str],
    classified_runtime_config: set[str] | None = None,
) -> list[str]:
    errors: list[str] = []
    names = all_names(target)
    unclassified = sorted(names - classified_public)
    errors.extend(f"{target.name}: input {name} is not classified public_build" for name in unclassified)
    runtime_config_names = set(target.deployment.runtime_env_vars)
    runtime_config_classification = classified_runtime_config or set()
    errors.extend(
        f"{target.name}: runtime env {name} is not classified config"
        for name in sorted(runtime_config_names - runtime_config_classification)
    )
    for item in target.inputs:
        if item.source != "repository_config":
            errors.append(f"{target.name}: input {item.name} must use repository_config")
        if item.allowed_scopes != ("repository",):
            errors.append(f"{target.name}: input {item.name} must allow only repository scope")

    dockerfile_path = root / target.dockerfile
    if not dockerfile_path.is_file():
        return errors + [f"{target.name}: Dockerfile is missing: {target.dockerfile}"]
    build_context_path = root / target.deployment.build_context
    if not build_context_path.is_dir():
        errors.append(f"{target.name}: Docker build context is missing: {target.deployment.build_context}")
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
    errors.extend(f"{target.dockerfile}: empty-value guard omits {name}" for name in sorted(required - guard_names))
    errors.extend(
        f"{target.dockerfile}: empty-value guard includes undeclared {name}" for name in sorted(guard_names - required)
    )
    if guard_names and 'test -n "$value"' not in dockerfile:
        errors.append(f"{target.dockerfile}: public-build guard must reject empty values")
    if "{sha}" in target.candidate_acceptance.command:
        dockerfile_args = set(ARG.findall(dockerfile))
        if "NEXT_PUBLIC_OMI_BUILD_SHA" not in dockerfile_args:
            errors.append(f"{target.dockerfile}: missing revision-identity ARG NEXT_PUBLIC_OMI_BUILD_SHA")

    workflow_path = root / target.workflow
    if not workflow_path.is_file():
        return errors + [f"{target.name}: workflow is missing: {target.workflow}"]
    workflow = workflow_path.read_text(encoding="utf-8")
    errors.extend(validate_manual_environment_dispatch(target.workflow, workflow))
    if DEPLOY_ACTION not in workflow:
        errors.append(f"{target.workflow}: missing centralized public-build deployment {DEPLOY_ACTION!r}")
    if target.gateway_required:
        if "runtime_env_vars: OMI_LLM_GATEWAY_URL=${{ vars.OMI_LLM_GATEWAY_URL }}" not in workflow:
            errors.append(
                f"{target.workflow}: gateway-required target must source OMI_LLM_GATEWAY_URL from GitHub environment vars"
            )
        if "require_gateway_url: true" not in workflow:
            errors.append(f"{target.workflow}: gateway-required target must reject an empty OMI_LLM_GATEWAY_URL")
    for name in sorted(names):
        if f"vars.{name}" in workflow:
            errors.append(f"{target.workflow}: input {name} bypasses repository_config via GitHub vars")
    for marker in (
        PREPARE_ACTION,
        PROMOTION_ACTION,
        "docker/build-push-action@",
        "google-github-actions/deploy-cloudrun@",
        "gcloud auth configure-docker",
        "docker build",
        "docker push",
        "gcloud run deploy",
        "no_traffic: true",
        "--revision-suffix=",
        "--tag=",
        "gcloud run services update-traffic",
    ):
        if marker not in workflow:
            continue
        errors.append(f"{target.workflow}: bypasses centralized public-build deployment via {marker!r}")
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
        if "{sha}" in target.candidate_acceptance.command and "data-omi-public-build-sha" not in canary:
            errors.append(f"{target.canary_component}: must expose data-omi-public-build-sha")
    return errors


def validate_shared_actions(root: Path) -> list[str]:
    errors: list[str] = []
    deploy_path = root / DEPLOY_ACTION_PATH
    if not deploy_path.is_file():
        errors.append(f"centralized public-build deployment action is missing: {DEPLOY_ACTION_PATH}")
    else:
        deploy = deploy_path.read_text(encoding="utf-8")
        required_markers = (
            "config/public-build-contract.json",
            ".deployment.runtime_secrets",
            "fallback_runtime_secrets",
            ".deployment.runtime_env_vars",
            ".deployment.remove_runtime_secrets",
            ".deployment.remove_runtime_env_vars",
            "($flags[$env] // [])",
            "--service-account",
            PREPARE_ACTION,
            "google-github-actions/auth@",
            "preflight_public_build_runtime.py",
            "--github-output",
            "steps.runtime-preflight.outputs.fallback_runtime_secrets",
            "service_exists",
            "Fail closed for a production first create",
            "refusing to create a public Cloud Run service outside development",
            "docker/build-push-action@",
            "google-github-actions/deploy-cloudrun@",
            "no_traffic: ${{ steps.runtime-preflight.outputs.service_exists == 'true' }}",
            "--revision-suffix=",
            "--tag=",
            "inputs.environment == 'development' && '--allow-unauthenticated' || ''",
            "--remove-secrets=",
            "--remove-env-vars=",
            "require_gateway_url",
            "OMI_LLM_GATEWAY_URL must be a non-empty HTTP(S) URL",
            "env_vars_update_strategy: merge",
            "secrets_update_strategy: merge",
            "NEXT_PUBLIC_OMI_BUILD_SHA",
            "steps.candidate.outputs.sha",
            PROMOTION_ACTION,
        )
        for marker in required_markers:
            if marker not in deploy:
                errors.append(f"{DEPLOY_ACTION_PATH}: missing centralized deployment marker {marker!r}")
        build_index = deploy.find("docker/build-push-action@")
        runtime_preflight_index = deploy.find("preflight_public_build_runtime.py")
        promotion_index = deploy.find(PROMOTION_ACTION)
        if runtime_preflight_index == -1 or build_index == -1 or runtime_preflight_index > build_index:
            errors.append(f"{DEPLOY_ACTION_PATH}: runtime preflight must run before image build")
        if promotion_index == -1 or build_index == -1 or promotion_index < build_index:
            errors.append(f"{DEPLOY_ACTION_PATH}: candidate promotion must follow image build")

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
        "public_build_acceptance_route.py",
        "run.googleapis.com/ingress",
        "resolve_cloud_run_tagged_url.py",
        "smoke_public_build_browser.py",
        "--expect-sha",
        "status.latestCreatedRevisionName",
        "previous_serving_revision",
        "gcloud run services update-traffic",
        "--to-revisions=",
    )
    for marker in required_markers:
        if marker not in promotion:
            errors.append(f"{PROMOTION_ACTION_PATH}: missing candidate-promotion marker {marker!r}")
    route_index = promotion.find("public_build_acceptance_route.py")
    smoke_index = promotion.find("smoke_public_build_browser.py")
    promotion_index = promotion.find("gcloud run services update-traffic")
    if route_index == -1 or smoke_index == -1 or route_index > smoke_index:
        errors.append(f"{PROMOTION_ACTION_PATH}: acceptance route must be resolved before browser acceptance")
    if smoke_index == -1 or promotion_index == -1 or smoke_index > promotion_index:
        errors.append(f"{PROMOTION_ACTION_PATH}: browser acceptance must run before traffic promotion")
    rollback_index = promotion.rfind("--to-revisions=")
    if rollback_index == -1 or rollback_index <= promotion_index:
        errors.append(f"{PROMOTION_ACTION_PATH}: public-URL acceptance must roll traffic back on failure")
    return errors


def validate_jit_preflight_workflow(root: Path) -> list[str]:
    workflow_path = root / JIT_PREFLIGHT_WORKFLOW_PATH
    if not workflow_path.is_file():
        return [f"JIT public-build preflight workflow is missing: {JIT_PREFLIGHT_WORKFLOW_PATH}"]
    workflow = workflow_path.read_text(encoding="utf-8")
    errors: list[str] = []
    if "pull_request:" not in workflow:
        errors.append(f"{JIT_PREFLIGHT_WORKFLOW_PATH}: must validate public-build changes in pull requests")
    if "workflow_dispatch:" not in workflow:
        errors.append(f"{JIT_PREFLIGHT_WORKFLOW_PATH}: must support explicit JIT validation")
    if "schedule:" in workflow:
        errors.append(f"{JIT_PREFLIGHT_WORKFLOW_PATH}: must not schedule drift checks; validation is JIT only")
    return errors


def validate(root: Path, contract: Contract, classified_settings: Mapping[str, set[str]]) -> list[str]:
    errors: list[str] = []
    workflows = {target.workflow for target in contract.targets.values()}
    if workflows != WEB_WORKFLOWS:
        errors.append("contract must cover exactly the four browser deploy workflows")
    for target in contract.targets.values():
        errors.extend(
            validate_target(
                root,
                target,
                classified_settings["public_build"],
                classified_settings["config"],
            )
        )
    errors.extend(validate_shared_actions(root))
    errors.extend(validate_jit_preflight_workflow(root))
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
        errors = validate(root, contract, deployment_setting_names(classification_path))
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
