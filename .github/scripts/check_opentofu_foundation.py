#!/usr/bin/env python3
"""Enforce the no-mutation OpenTofu foundation boundary for issue #9842."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODULE_DIR = ROOT / "infrastructure" / "opentofu" / "foundation"
DEFAULT_WORKFLOW_PATH = ROOT / ".github" / "workflows" / "opentofu-foundation-validate.yml"

RESOURCE_BLOCK = re.compile(r'^\s*resource\s+"(?P<type>[^"]+)"\s+"[^"]+"', re.MULTILINE)
DATA_BLOCK = re.compile(r'^\s*data\s+"(?P<type>[^"]+)"\s+"[^"]+"', re.MULTILINE)
GCS_BACKEND = re.compile(r'backend\s+"gcs"\s*\{\s*\}', re.DOTALL)
GCS_BACKEND_BLOCK = re.compile(r'^\s*backend\s+"gcs"\s*\{\s*\}\s*$', re.MULTILINE)

ALLOWED_RESOURCE_TYPES = frozenset(
    {
        "google_iam_workload_identity_pool",
        "google_iam_workload_identity_pool_provider",
        "google_project_iam_member",
        "google_secret_manager_secret",
        "google_secret_manager_secret_iam_member",
        "google_service_account",
        "google_service_account_iam_member",
        "google_storage_bucket",
        "google_storage_bucket_iam_member",
    }
)

FORBIDDEN_REFERENCES = (
    re.compile(r"\bgoogle_artifact_registry_"),
    re.compile(r"\bgoogle_cloud_run_"),
    re.compile(r"\bgoogle_container_"),
    re.compile(r"\bgoogle_secret_manager_secret_version\b"),
    re.compile(r"\bsecret_data\s*="),
    re.compile(r"\bsecret_string\s*="),
)

FORBIDDEN_WORKFLOW_REFERENCES = (
    re.compile(r"\bcredentials_json\b"),
    re.compile(r"\bgcloud\b"),
    re.compile(r"\bgoogle-github-actions/auth\b"),
    re.compile(r"\bid-token\s*:\s*"),
    re.compile(r"\btofu\b[^\n]*\bapply\b"),
    re.compile(r"\bworkload_identity_provider\b"),
)

REQUIRED_WORKFLOW_REFERENCES = (
    "contents: read",
    "-backend=false",
    "--prepare-offline-plan-module",
    "-refresh=false",
)


def module_files(module_dir: Path) -> list[Path]:
    return sorted(path for path in module_dir.rglob("*.tf") if path.is_file())


def check_module(module_dir: Path) -> list[str]:
    errors: list[str] = []
    files = module_files(module_dir)
    if not files:
        return [f"{module_dir}: no OpenTofu files found"]

    source = "\n".join(path.read_text(encoding="utf-8") for path in files)
    if not GCS_BACKEND.search(source):
        errors.append("foundation module must declare an empty gcs backend block")
    if 'required_providers' not in source or 'hashicorp/google' not in source:
        errors.append("foundation module must pin the hashicorp/google provider")

    for path in files:
        text = path.read_text(encoding="utf-8")
        for match in RESOURCE_BLOCK.finditer(text):
            resource_type = match.group("type")
            if resource_type not in ALLOWED_RESOURCE_TYPES:
                errors.append(f"{path}: resource type {resource_type} is outside the foundation boundary")
        for match in DATA_BLOCK.finditer(text):
            errors.append(f"{path}: data source {match.group('type')} is outside the foundation boundary")
        for pattern in FORBIDDEN_REFERENCES:
            if pattern.search(text):
                errors.append(f"{path}: forbidden release or secret-value reference {pattern.pattern!r}")

    return errors


def prepare_offline_plan_module(module_dir: Path, destination: Path) -> None:
    """Copy the module with its GCS backend removed for an offline empty-plan check."""
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(module_dir, destination)

    removed_backends = 0
    for path in module_files(destination):
        text = path.read_text(encoding="utf-8")
        updated, count = GCS_BACKEND_BLOCK.subn("", text)
        if count:
            path.write_text(updated, encoding="utf-8")
            removed_backends += count

    if removed_backends != 1:
        raise ValueError(f"expected one gcs backend block in {module_dir}, found {removed_backends}")


def check_workflow_text(text: str) -> list[str]:
    errors: list[str] = []
    for pattern in FORBIDDEN_WORKFLOW_REFERENCES:
        if pattern.search(text):
            errors.append(f"validation workflow contains forbidden cloud mutation or credential reference {pattern.pattern!r}")
    for reference in REQUIRED_WORKFLOW_REFERENCES:
        if reference not in text:
            errors.append(f"validation workflow is missing required no-mutation reference {reference!r}")
    return errors


def check_workflow(workflow_path: Path) -> list[str]:
    try:
        return check_workflow_text(workflow_path.read_text(encoding="utf-8"))
    except OSError as exc:
        return [f"could not read validation workflow {workflow_path}: {exc}"]


def check_plan(plan: dict[str, Any], *, require_empty: bool) -> list[str]:
    errors: list[str] = []
    changes = plan.get("resource_changes", [])
    if not isinstance(changes, list):
        return ["plan resource_changes must be a list"]

    for change in changes:
        if not isinstance(change, dict):
            errors.append("plan contains a malformed resource change")
            continue
        resource_type = change.get("type")
        address = change.get("address", "<unknown>")
        if resource_type not in ALLOWED_RESOURCE_TYPES:
            errors.append(f"plan resource {address} ({resource_type}) is outside the foundation boundary")
        if require_empty:
            errors.append(f"initial no-mutation slice must have an empty plan; found {address}")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--module-dir", type=Path, default=DEFAULT_MODULE_DIR)
    parser.add_argument("--plan-json", type=Path)
    parser.add_argument("--prepare-offline-plan-module", type=Path)
    parser.add_argument("--workflow-path", type=Path, default=DEFAULT_WORKFLOW_PATH)
    args = parser.parse_args()

    errors = check_module(args.module_dir)
    errors.extend(check_workflow(args.workflow_path))
    if args.prepare_offline_plan_module is not None and not errors:
        try:
            prepare_offline_plan_module(args.module_dir, args.prepare_offline_plan_module)
        except (OSError, ValueError) as exc:
            errors.append(f"could not prepare offline plan module: {exc}")
    if args.plan_json is not None:
        try:
            plan = json.loads(args.plan_json.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"could not read plan JSON {args.plan_json}: {exc}")
        else:
            if not isinstance(plan, dict):
                errors.append(f"plan JSON {args.plan_json} must be an object")
            else:
                errors.extend(check_plan(plan, require_empty=True))

    if errors:
        print("OpenTofu foundation boundary check failed:", file=sys.stderr)
        print("\n".join(f"- {error}" for error in errors), file=sys.stderr)
        return 1

    print("OpenTofu foundation boundary check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
