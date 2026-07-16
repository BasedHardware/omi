#!/usr/bin/env python3
"""Keep the #9842 development WIF plan pilot development-only and read-only."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[2]
PILOT_DIR = ROOT / "infrastructure" / "opentofu" / "pilots" / "development-wif-plan"
PROBE_DIR = ROOT / "infrastructure" / "opentofu" / "probes" / "development-project-read"
BOOTSTRAP = PILOT_DIR / "main.tf"
BOOTSTRAP_VARIABLES = PILOT_DIR / "variables.tf"
PROBE = PROBE_DIR / "main.tf"
WORKFLOW = ROOT / ".github" / "workflows" / "opentofu-development-wif-pilot.yml"
VALIDATION_WORKFLOW = ROOT / ".github" / "workflows" / "opentofu-development-wif-pilot-validate.yml"

EXPECTED_PILOT_FILES = frozenset({"main.tf", "variables.tf"})
EXPECTED_PROBE_FILES = frozenset({"main.tf"})
EXPECTED_BOOTSTRAP_RESOURCES = frozenset(
    {
        "google_service_account.plan",
        "google_iam_workload_identity_pool.github",
        "google_iam_workload_identity_pool_provider.github",
        "google_service_account_iam_member.github_plan_impersonation",
        "google_project_iam_member.plan_project_browser",
    }
)
EXPECTED_PARTIAL_RECOVERY_RESOURCES = frozenset(
    {
        "google_service_account.plan",
        "google_project_iam_member.plan_project_browser",
    }
)
EXPECTED_PARTIAL_RECOVERY_CREATES = EXPECTED_BOOTSTRAP_RESOURCES - EXPECTED_PARTIAL_RECOVERY_RESOURCES
EXPECTED_PARTIAL_RECOVERY_ACTIONS = {
    **{address: ["no-op"] for address in EXPECTED_PARTIAL_RECOVERY_RESOURCES},
    **{address: ["create"] for address in EXPECTED_PARTIAL_RECOVERY_CREATES},
}
EXPECTED_PARTIAL_RECOVERY_VALUES = {
    "google_service_account.plan": {"account_id": "omi-tofu-plan-dev-9842"},
    "google_project_iam_member.plan_project_browser": {
        "project": "based-hardware-dev",
        "role": "roles/browser",
        "member": "serviceAccount:omi-tofu-plan-dev-9842@based-hardware-dev.iam.gserviceaccount.com",
    },
}
RESOURCE = re.compile(r'^\s*resource\s+"(?P<type>[^"]+)"\s+"(?P<name>[^"]+)"', re.MULTILINE)
DATA = re.compile(r'^\s*data\s+"(?P<type>[^"]+)"\s+"(?P<name>[^"]+)"', re.MULTILINE)
MODULE = re.compile(r'^\s*module\s+"(?P<name>[^"]+)"', re.MULTILINE)
PROVIDER = re.compile(r'^\s*provider\s+"(?P<name>[^"]+)"', re.MULTILINE)
PROVISIONER = re.compile(r'^\s*provisioner\s+"(?P<name>[^"]+)"', re.MULTILINE)
DISPLAY_NAME = re.compile(r'^\s*display_name\s*=\s*"(?P<value>[^"]*)"', re.MULTILINE)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def module_files(module_dir: Path) -> list[Path]:
    return sorted(path for path in module_dir.rglob("*.tf") if path.is_file())


def module_config_files(module_dir: Path) -> list[Path]:
    return sorted(
        path
        for path in module_dir.rglob("*")
        if path.is_file() and (path.name.endswith(".tf") or path.name.endswith(".tf.json"))
    )


def check_module_files(module_dir: Path, expected_names: frozenset[str], label: str) -> list[str]:
    names = {path.relative_to(module_dir).as_posix() for path in module_config_files(module_dir)}
    if names != expected_names:
        return [f"{label} files must be exactly {sorted(expected_names)}, found {sorted(names)}"]
    return []


def module_source(module_dir: Path) -> str:
    return "\n".join(read(path) for path in module_files(module_dir))


def resource_body(text: str, address: str) -> str | None:
    resource_type, name = address.split(".", maxsplit=1)
    match = re.search(
        rf'^\s*resource\s+"{re.escape(resource_type)}"\s+"{re.escape(name)}"\s*\{{(?P<body>.*?)(?=^\s*resource\s+|\Z)',
        text,
        re.MULTILINE | re.DOTALL,
    )
    return None if match is None else match.group("body")


def check_display_name_limit(text: str, address: str) -> list[str]:
    body = resource_body(text, address)
    if body is None:
        return []
    match = DISPLAY_NAME.search(body)
    if match is None:
        return [f"bootstrap {address} must declare a display_name"]
    if len(match.group("value")) > 32:
        return [f"bootstrap {address} display_name must not exceed 32 characters"]
    return []


def check_bootstrap(text: str) -> list[str]:
    errors: list[str] = []
    resources = {f"{match.group('type')}.{match.group('name')}" for match in RESOURCE.finditer(text)}
    if resources != EXPECTED_BOOTSTRAP_RESOURCES:
        errors.append(f"bootstrap resources must be exactly {sorted(EXPECTED_BOOTSTRAP_RESOURCES)}")
    if DATA.search(text):
        errors.append("bootstrap must not declare data sources")
    if MODULE.search(text):
        errors.append("bootstrap must not declare modules")
    if PROVISIONER.search(text):
        errors.append("bootstrap must not declare provisioners")
    providers = {match.group("name") for match in PROVIDER.finditer(text)}
    if providers != {"google"}:
        errors.append("bootstrap must declare exactly one google provider")
    for required in (
        'backend "gcs" {}',
        "project = var.project_id",
        "roles/iam.workloadIdentityUser",
        "roles/browser",
        "assertion.repository_id == '${var.github_repository_id}'",
        "assertion.repository_owner_id == '${var.github_repository_owner_id}'",
        "assertion.ref == 'refs/heads/main'",
        "assertion.workflow_ref == '${var.github_workflow_ref}'",
        "assertion.environment == 'development'",
        "https://token.actions.githubusercontent.com",
    ):
        if required not in text:
            errors.append(f"bootstrap is missing required pilot contract {required!r}")
    for forbidden in (
        "roles/owner",
        "roles/editor",
        "roles/viewer",
        "roles/iam.securityReviewer",
        "roles/secretmanager.viewer",
        "roles/secretmanager.secretAccessor",
        "roles/iam.serviceAccountTokenCreator",
        "google_cloud_run_",
        "google_container_",
        "google_secret_manager_secret_version",
        "secret_data",
        "secret_string",
    ):
        if forbidden in text:
            errors.append(f"bootstrap contains forbidden permission or release/secret-value reference {forbidden!r}")

    expected_blocks = {
        "google_service_account.plan": ("account_id   = var.plan_service_account_id",),
        "google_iam_workload_identity_pool.github": ("workload_identity_pool_id = var.workload_identity_pool_id",),
        "google_iam_workload_identity_pool_provider.github": (
            "workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id",
            'workload_identity_pool_provider_id = "github"',
            '"google.subject"                = "assertion.sub"',
            '"attribute.repository_id"       = "assertion.repository_id"',
            '"attribute.repository_owner_id" = "assertion.repository_owner_id"',
            '"attribute.workflow_ref"        = "assertion.workflow_ref"',
            '"attribute.environment"         = "assertion.environment"',
        ),
        "google_service_account_iam_member.github_plan_impersonation": (
            "service_account_id = google_service_account.plan.name",
            'role               = "roles/iam.workloadIdentityUser"',
            "attribute.repository_id/${var.github_repository_id}",
        ),
        "google_project_iam_member.plan_project_browser": (
            "project = var.project_id",
            'role    = "roles/browser"',
            "member  = \"serviceAccount:${google_service_account.plan.email}\"",
        ),
    }
    for address, required in expected_blocks.items():
        body = resource_body(text, address)
        if body is None:
            continue
        for expected in required:
            if expected not in body:
                errors.append(f"bootstrap {address} is missing required contract {expected!r}")
    for address in (
        "google_iam_workload_identity_pool.github",
        "google_iam_workload_identity_pool_provider.github",
    ):
        errors.extend(check_display_name_limit(text, address))
    return errors


def check_probe(text: str) -> list[str]:
    errors: list[str] = []
    if RESOURCE.search(text):
        errors.append("development probe must not declare resources")
    if MODULE.search(text):
        errors.append("development probe must not declare modules")
    if PROVISIONER.search(text):
        errors.append("development probe must not declare provisioners")
    if {match.group("name") for match in PROVIDER.finditer(text)} != {"google"}:
        errors.append("development probe must declare exactly one google provider")
    if len(re.findall(r'^\s*data\s+"google_project"\s+"development"', text, re.MULTILINE)) != 1:
        errors.append("development probe must contain exactly one google_project development data source")
    if len(list(DATA.finditer(text))) != 1:
        errors.append("development probe must not contain other data sources")
    for required in ('default     = "based-hardware-dev"', "project = var.project_id", "project_id = var.project_id"):
        if required not in text:
            errors.append(f"development probe is missing required contract {required!r}")
    if 'backend "gcs"' in text:
        errors.append("development probe must not use a remote backend")
    return errors


def check_bootstrap_variables(text: str) -> list[str]:
    errors: list[str] = []
    for required in (
        'default     = "based-hardware-dev"',
        'condition     = var.project_id == "based-hardware-dev"',
        'default     = "1031333818730"',
        'condition     = var.project_number == "1031333818730"',
        'default     = "776121034"',
        'condition     = var.github_repository_id == "776121034"',
        'default     = "162546372"',
        'condition     = var.github_repository_owner_id == "162546372"',
        'default     = "BasedHardware/omi/.github/workflows/opentofu-development-wif-pilot.yml@refs/heads/main"',
        'condition     = var.github_workflow_ref == "BasedHardware/omi/.github/workflows/opentofu-development-wif-pilot.yml@refs/heads/main"',
        'default     = "omi-opentofu-9842-dev"',
        'condition     = var.workload_identity_pool_id == "omi-opentofu-9842-dev"',
        'default     = "omi-tofu-plan-dev-9842"',
        'condition     = var.plan_service_account_id == "omi-tofu-plan-dev-9842"',
    ):
        if required not in text:
            errors.append(f"bootstrap variables are missing immutable pilot contract {required!r}")
    return errors


def check_plan(plan: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    changes = plan.get("resource_changes")
    if not isinstance(changes, list):
        return ["bootstrap plan resource_changes must be a list"]

    actual: dict[str, list[str]] = {}
    for change in changes:
        if not isinstance(change, dict):
            errors.append("bootstrap plan contains a malformed resource change")
            continue
        address = change.get("address")
        action = change.get("change", {}).get("actions") if isinstance(change.get("change"), dict) else None
        if (
            not isinstance(address, str)
            or not isinstance(action, list)
            or not all(isinstance(item, str) for item in action)
        ):
            errors.append("bootstrap plan contains a malformed address or action")
            continue
        if address in actual:
            errors.append(f"bootstrap plan contains duplicate change {address}")
        actual[address] = action

    if set(actual) != EXPECTED_BOOTSTRAP_RESOURCES:
        errors.append(f"bootstrap plan resources must be exactly {sorted(EXPECTED_BOOTSTRAP_RESOURCES)}")
    for address, actions in actual.items():
        if actions != ["create"]:
            errors.append(f"bootstrap plan {address} must have only a create action, found {actions}")
    return errors


def plan_root_resources(plan: dict[str, Any], section: str) -> tuple[dict[str, dict[str, Any]], list[str]]:
    errors: list[str] = []
    section_value = plan.get(section)
    if not isinstance(section_value, dict):
        return {}, [f"bootstrap recovery plan {section} must be an object"]
    values = section_value.get("values")
    if not isinstance(values, dict):
        return {}, [f"bootstrap recovery plan {section}.values must be an object"]
    root_module = values.get("root_module")
    if not isinstance(root_module, dict):
        return {}, [f"bootstrap recovery plan {section}.values.root_module must be an object"]
    resources = root_module.get("resources")
    if not isinstance(resources, list):
        return {}, [f"bootstrap recovery plan {section}.values.root_module.resources must be a list"]
    if root_module.get("child_modules"):
        errors.append(f"bootstrap recovery plan {section} must not contain child modules")

    actual: dict[str, dict[str, Any]] = {}
    for resource in resources:
        if not isinstance(resource, dict):
            errors.append(f"bootstrap recovery plan {section} contains a malformed resource")
            continue
        address = resource.get("address")
        if not isinstance(address, str):
            errors.append(f"bootstrap recovery plan {section} contains a resource without an address")
            continue
        if address in actual:
            errors.append(f"bootstrap recovery plan {section} contains duplicate resource {address}")
        actual[address] = resource
    return actual, errors


def check_partial_recovery_plan(plan: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    prior_resources, prior_errors = plan_root_resources(plan, "prior_state")
    errors.extend(prior_errors)
    if set(prior_resources) != EXPECTED_PARTIAL_RECOVERY_RESOURCES:
        errors.append(
            "bootstrap recovery prior state must contain exactly " f"{sorted(EXPECTED_PARTIAL_RECOVERY_RESOURCES)}"
        )
    for address, expected_values in EXPECTED_PARTIAL_RECOVERY_VALUES.items():
        values = prior_resources.get(address, {}).get("values")
        if not isinstance(values, dict):
            errors.append(f"bootstrap recovery prior state {address} must contain resource values")
            continue
        for key, expected in expected_values.items():
            if values.get(key) != expected:
                errors.append(f"bootstrap recovery prior state {address} must retain {key}={expected!r}")

    planned_resources, planned_errors = plan_root_resources(plan, "planned_values")
    errors.extend(planned_errors)
    if set(planned_resources) != EXPECTED_BOOTSTRAP_RESOURCES:
        errors.append(
            "bootstrap recovery planned values must contain exactly " f"{sorted(EXPECTED_BOOTSTRAP_RESOURCES)}"
        )

    changes = plan.get("resource_changes")
    if not isinstance(changes, list):
        return errors + ["bootstrap recovery plan resource_changes must be a list"]
    actual_actions: dict[str, list[str]] = {}
    for change in changes:
        if not isinstance(change, dict):
            errors.append("bootstrap recovery plan contains a malformed resource change")
            continue
        address = change.get("address")
        actions = change.get("change", {}).get("actions") if isinstance(change.get("change"), dict) else None
        if (
            not isinstance(address, str)
            or not isinstance(actions, list)
            or not all(isinstance(item, str) for item in actions)
        ):
            errors.append("bootstrap recovery plan contains a malformed address or action")
            continue
        if address in actual_actions:
            errors.append(f"bootstrap recovery plan contains duplicate change {address}")
        actual_actions[address] = actions
    if actual_actions != EXPECTED_PARTIAL_RECOVERY_ACTIONS:
        errors.append(
            "bootstrap recovery plan actions must be exactly "
            f"{EXPECTED_PARTIAL_RECOVERY_ACTIONS}, found {actual_actions}"
        )
    return errors


def check_workflow(text: str) -> list[str]:
    errors: list[str] = []
    for required in (
        "workflow_dispatch:",
        "environment: development",
        "contents: read",
        "id-token: write",
        "google-github-actions/auth@v2",
        "workload_identity_provider: projects/1031333818730/locations/global/workloadIdentityPools/omi-opentofu-9842-dev/providers/github",
        "service_account: omi-tofu-plan-dev-9842@based-hardware-dev.iam.gserviceaccount.com",
        "ref: main",
        "-backend=false",
        "-lock=false",
        "-refresh=false",
    ):
        if required not in text:
            errors.append(f"pilot workflow is missing required read-only development contract {required!r}")
    for forbidden in ("credentials_json", "gcloud", "tofu apply", "backend-config", "environment: prod"):
        if forbidden in text:
            errors.append(f"pilot workflow contains forbidden reference {forbidden!r}")
    return errors


def check_validation_workflow(text: str) -> list[str]:
    errors: list[str] = []
    for required in (
        "contents: read",
        "GOOGLE_OAUTH_ACCESS_TOKEN: offline-validation-only",
        "--prepare-offline-plan-module",
        "-backend=false",
        "-lock=false",
        "-refresh=false",
        "-out=",
        "--plan-json",
    ):
        if required not in text:
            errors.append(f"pilot validation workflow is missing required offline contract {required!r}")
    if not re.search(r"tofu\s+-chdir=[^\n]+\s+show\s+-json", text):
        errors.append("pilot validation workflow is missing required offline plan JSON rendering")
    token_values = re.findall(r"^\s*GOOGLE_OAUTH_ACCESS_TOKEN:\s*(?P<value>\S.*)$", text, re.MULTILINE)
    if token_values != ["offline-validation-only"]:
        errors.append("pilot validation workflow may contain only the invalid offline-validation-only token literal")
    for forbidden in (
        "credentials_json",
        "GOOGLE_APPLICATION_CREDENTIALS",
        "GOOGLE_CREDENTIALS",
        "google-github-actions/auth",
        "id-token: write",
        "workload_identity_provider",
        "gcloud",
        "tofu apply",
        "backend-config",
    ):
        if forbidden in text:
            errors.append(
                f"pilot validation workflow contains forbidden credential or mutation reference {forbidden!r}"
            )
    return errors


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    plan_group = parser.add_mutually_exclusive_group()
    plan_group.add_argument("--plan-json", type=Path)
    plan_group.add_argument("--partial-recovery-plan-json", type=Path)
    args = parser.parse_args(argv)

    bootstrap = module_source(PILOT_DIR)
    probe = module_source(PROBE_DIR)
    errors = (
        check_module_files(PILOT_DIR, EXPECTED_PILOT_FILES, "bootstrap")
        + check_bootstrap(bootstrap)
        + check_bootstrap_variables(read(BOOTSTRAP_VARIABLES))
        + check_module_files(PROBE_DIR, EXPECTED_PROBE_FILES, "development probe")
        + check_probe(probe)
        + check_workflow(read(WORKFLOW))
        + check_validation_workflow(read(VALIDATION_WORKFLOW))
    )
    plan_path = args.plan_json or args.partial_recovery_plan_json
    if plan_path is not None:
        try:
            plan = json.loads(read(plan_path))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"could not read bootstrap plan JSON {plan_path}: {exc}")
        else:
            if not isinstance(plan, dict):
                errors.append(f"bootstrap plan JSON {plan_path} must be an object")
            else:
                errors.extend(
                    check_partial_recovery_plan(plan)
                    if args.partial_recovery_plan_json is not None
                    else check_plan(plan)
                )

    if errors:
        print("Development WIF pilot check failed:", file=sys.stderr)
        print("\n".join(f"- {error}" for error in errors), file=sys.stderr)
        return 1
    print("Development WIF pilot check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
