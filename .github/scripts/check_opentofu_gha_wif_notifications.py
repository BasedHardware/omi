#!/usr/bin/env python3
"""Keep the notifications-job development WIF slice narrow."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SLICE = ROOT / "infrastructure" / "opentofu" / "slices" / "gha-wif-notifications"
MAIN = SLICE / "main.tf"
VARS = SLICE / "variables.tf"

EXPECTED_TF = frozenset({"main.tf", "variables.tf"})
EXPECTED_RESOURCES = frozenset(
    {
        "google_service_account.deploy",
        "google_iam_workload_identity_pool.github",
        "google_iam_workload_identity_pool_provider.github",
        "google_service_account_iam_member.github_deploy_impersonation",
        "google_artifact_registry_repository_iam_member.gcr_writer",
        "google_cloud_run_v2_job_iam_member.notifications_job_developer",
        "google_service_account_iam_member.notifications_job_runtime_act_as",
        "google_project_iam_member.gke_viewer",
        "google_project_iam_member.compute_network_viewer",
        "google_project_iam_member.run_developer",
        "google_project_iam_member.compute_network_user",
        "google_secret_manager_secret_iam_member.gateway_token",
    }
)
FORBIDDEN = (
    "roles/owner",
    "roles/editor",
    "roles/viewer",
    "roles/run.admin",
    "roles/storage.admin",
    "roles/iam.securityReviewer",
    "omi-opentofu-9842-dev",
    "omi-tofu-plan-dev-9842",
    "based-hardware-dev.svc.id.goog",
    'project_id" {',
)
RESOURCE = re.compile(r'^\s*resource\s+"(?P<type>[^"]+)"\s+"(?P<name>[^"]+)"', re.MULTILINE)
DISPLAY = re.compile(r'^\s*display_name\s*=\s*"(?P<value>[^"]*)"', re.MULTILINE)
DATA = re.compile(r'^\s*data\s+"', re.MULTILINE)
MODULE = re.compile(r'^\s*module\s+"', re.MULTILINE)


def main() -> int:
    errors: list[str] = []
    tf_names = {p.name for p in SLICE.glob("*.tf")}
    if tf_names != EXPECTED_TF:
        errors.append(f"tf files must be {sorted(EXPECTED_TF)}, found {sorted(tf_names)}")
    text = MAIN.read_text(encoding="utf-8") + "\n" + VARS.read_text(encoding="utf-8")
    found = {f"{m.group('type')}.{m.group('name')}" for m in RESOURCE.finditer(text)}
    if found != EXPECTED_RESOURCES:
        errors.append(f"resources must be {sorted(EXPECTED_RESOURCES)}, found {sorted(found)}")
    if DATA.search(text):
        errors.append("no data sources")
    if MODULE.search(text):
        errors.append("no modules")
    for match in DISPLAY.finditer(text):
        value = match.group("value")
        if len(value) > 32:
            errors.append(f"display_name over 32 chars: {value!r}")
    lowered = text
    for token in FORBIDDEN:
        if token in lowered and token != 'project_id" {':
            errors.append(f"forbidden token {token}")
    if "based-hardware\"" in text and "based-hardware-dev" not in text.replace("based-hardware-dev", ""):
        pass
    if '"based-hardware"' in text:
        errors.append("must not mention production project based-hardware")
    if "gcp_notifications_job.yml@refs/heads/main" not in text:
        errors.append("workflow_ref must pin gcp_notifications_job.yml on main")
    if "credentials_json" in text:
        errors.append("module must not reference credentials_json")
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print("gha-wif-notifications OpenTofu slice OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
