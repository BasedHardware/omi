#!/usr/bin/env python3
"""Keep the #9842 development WIF plan pilot development-only and read-only."""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BOOTSTRAP = ROOT / "infrastructure" / "opentofu" / "pilots" / "development-wif-plan" / "main.tf"
BOOTSTRAP_VARIABLES = ROOT / "infrastructure" / "opentofu" / "pilots" / "development-wif-plan" / "variables.tf"
PROBE = ROOT / "infrastructure" / "opentofu" / "probes" / "development-project-read" / "main.tf"
WORKFLOW = ROOT / ".github" / "workflows" / "opentofu-development-wif-pilot.yml"

EXPECTED_BOOTSTRAP_RESOURCES = {
    "google_service_account.plan",
    "google_iam_workload_identity_pool.github",
    "google_iam_workload_identity_pool_provider.github",
    "google_service_account_iam_member.github_plan_impersonation",
    "google_project_iam_member.plan_project_browser",
}
RESOURCE = re.compile(r'^\s*resource\s+"(?P<type>[^"]+)"\s+"(?P<name>[^"]+)"', re.MULTILINE)


def resource_body(text: str, address: str) -> str | None:
    resource_type, name = address.split(".", maxsplit=1)
    match = re.search(
        rf'^\s*resource\s+"{re.escape(resource_type)}"\s+"{re.escape(name)}"\s*\{{(?P<body>.*?)(?=^\s*resource\s+|\Z)',
        text,
        re.MULTILINE | re.DOTALL,
    )
    return None if match is None else match.group("body")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def check_bootstrap(text: str) -> list[str]:
    errors: list[str] = []
    resources = {f"{match.group('type')}.{match.group('name')}" for match in RESOURCE.finditer(text)}
    if resources != EXPECTED_BOOTSTRAP_RESOURCES:
        errors.append(f"bootstrap resources must be exactly {sorted(EXPECTED_BOOTSTRAP_RESOURCES)}")
    if re.search(r"^\s*data\s+", text, re.MULTILINE):
        errors.append("bootstrap must not declare data sources")
    for required in (
        'backend "gcs" {}',
        'project = var.project_id',
        'roles/iam.workloadIdentityUser',
        'roles/browser',
        'assertion.ref == \'refs/heads/main\'',
        'https://token.actions.githubusercontent.com',
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
        "google_service_account.plan": ('account_id   = var.plan_service_account_id',),
        "google_iam_workload_identity_pool.github": ('workload_identity_pool_id = var.workload_identity_pool_id',),
        "google_iam_workload_identity_pool_provider.github": (
            "workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id",
            'workload_identity_pool_provider_id = "github"',
            '"google.subject"       = "assertion.sub"',
            '"attribute.repository" = "assertion.repository"',
            "attribute_condition = \"assertion.repository == '${var.github_repository}' && assertion.ref == 'refs/heads/main'\"",
        ),
        "google_service_account_iam_member.github_plan_impersonation": (
            "service_account_id = google_service_account.plan.name",
            'role               = "roles/iam.workloadIdentityUser"',
            "attribute.repository/${var.github_repository}",
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
    return errors


def check_probe(text: str) -> list[str]:
    errors: list[str] = []
    if re.search(r"^\s*resource\s+", text, re.MULTILINE):
        errors.append("development probe must not declare resources")
    if len(re.findall(r'^\s*data\s+"google_project"\s+"development"', text, re.MULTILINE)) != 1:
        errors.append("development probe must contain exactly one google_project development data source")
    for required in ('default     = "based-hardware-dev"', 'project = var.project_id', 'project_id = var.project_id'):
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
        'default     = "BasedHardware/omi"',
        'condition     = var.github_repository == "BasedHardware/omi"',
        'default     = "omi-opentofu-9842-dev"',
        'condition     = var.workload_identity_pool_id == "omi-opentofu-9842-dev"',
        'default     = "omi-tofu-plan-dev-9842"',
        'condition     = var.plan_service_account_id == "omi-tofu-plan-dev-9842"',
    ):
        if required not in text:
            errors.append(f"bootstrap variables are missing immutable pilot contract {required!r}")
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


def main() -> int:
    errors = (
        check_bootstrap(read(BOOTSTRAP))
        + check_bootstrap_variables(read(BOOTSTRAP_VARIABLES))
        + check_probe(read(PROBE))
        + check_workflow(read(WORKFLOW))
    )
    if errors:
        print("Development WIF pilot check failed:", file=sys.stderr)
        print("\n".join(f"- {error}" for error in errors), file=sys.stderr)
        return 1
    print("Development WIF pilot check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
