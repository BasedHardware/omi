"""Validate the source/deploy contract for permanent conversation photos.

This is intentionally an offline validator: it reads a rendered binding and,
optionally, a ``gcloud storage buckets describe --format=json`` fixture. It
never creates or mutates a bucket.
"""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml


def _find_bindings(value: Any, env_name: str) -> list[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        bindings: list[Mapping[str, Any]] = []
        for key, child in value.items():
            if key == env_name and isinstance(child, Mapping):
                bindings.append(child)
            bindings.extend(_find_bindings(child, env_name))
        return bindings
    if isinstance(value, list):
        bindings = []
        for child in value:
            bindings.extend(_find_bindings(child, env_name))
        return bindings
    return []


def validate_bucket_contract(
    bucket_name: str | None = None,
    lifecycle_document: Mapping[str, Any] | None = None,
    contract: Mapping[str, Any] | None = None,
) -> list[str]:
    errors: list[str] = []
    name = (bucket_name or os.getenv("BUCKET_FRAME_REQUESTS", "")).strip()
    if not name:
        errors.append("BUCKET_FRAME_REQUESTS must bind the dedicated permanent bucket")
    if lifecycle_document is None:
        errors.append("live bucket describe document is required outside --source-only mode")
        return errors
    live_name = str(lifecycle_document.get("name") or "").strip()
    if live_name and name and live_name != name:
        errors.append(f"live bucket name {live_name!r} does not match binding {name!r}")
    rules = lifecycle_document.get("lifecycle", {}).get("rule", [])
    if not isinstance(rules, list):
        errors.append("bucket lifecycle.rule must be a list")
        return errors
    for index, rule in enumerate(rules):
        if isinstance(rule, Mapping) and isinstance(rule.get("condition"), Mapping):
            condition = rule["condition"]
            if any(
                key in condition
                for key in (
                    "age",
                    "createdBefore",
                    "customTimeBefore",
                    "daysSinceCustomTime",
                )
            ):
                errors.append(
                    f"bucket lifecycle rule {index} expires objects; permanent evidence requires no expiration"
                )
    if contract:
        allowed_locations = {str(value).upper() for value in contract.get("allowed_locations", [])}
        location = str(lifecycle_document.get("location") or "").upper()
        if not location or location not in allowed_locations:
            errors.append(f"bucket location {location or '<missing>'} is not allowed")
        iam = lifecycle_document.get("iamConfiguration", {})
        uniform = iam.get("uniformBucketLevelAccess", {}) if isinstance(iam, Mapping) else {}
        if contract.get("uniform_bucket_level_access") is True and uniform.get("enabled") is not True:
            errors.append("bucket must enable uniform bucket-level access")
        prevention = iam.get("publicAccessPrevention") if isinstance(iam, Mapping) else None
        if prevention != contract.get("public_access_prevention"):
            errors.append("bucket must enforce public access prevention")
        encryption = lifecycle_document.get("encryption")
        if encryption is not None and (
            not isinstance(encryption, Mapping) or not str(encryption.get("defaultKmsKeyName") or "").strip()
        ):
            errors.append("bucket encryption must be Google-managed or name a default KMS key")
    return errors


def validate_runtime_binding(runtime_document: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    for env_name in ("BUCKET_FRAME_REQUESTS", "BUCKET_FRAME_REQUESTS_TEMPORARY"):
        bindings = _find_bindings(runtime_document, env_name)
        if not bindings:
            errors.append(f"runtime manifest must bind {env_name}")
            continue
        for index, binding in enumerate(bindings):
            if binding.get("env_var") != env_name:
                errors.append(f"runtime {env_name} binding {index} must preserve the env var name")
            if not (str(binding.get("default") or binding.get("value") or "").strip() or binding.get("env_var")):
                errors.append(f"runtime {env_name} binding {index} has no value or env var")
    return errors


def validate_temporary_bucket_contract(
    bucket_name: str | None,
    lifecycle_document: Mapping[str, Any] | None,
    contract: Mapping[str, Any] | None,
) -> list[str]:
    errors: list[str] = []
    name = (bucket_name or os.getenv("BUCKET_FRAME_REQUESTS_TEMPORARY", "")).strip()
    if not name:
        errors.append("BUCKET_FRAME_REQUESTS_TEMPORARY must bind the dedicated temporary bucket")
    if lifecycle_document is None:
        errors.append("live temporary bucket describe document is required outside --source-only mode")
        return errors
    if str(lifecycle_document.get("name") or "").strip() != name:
        errors.append("live temporary bucket name does not match binding")
    temporary_contract = contract.get("temporary_lifecycle", {}) if contract else {}
    expected_age = int(temporary_contract.get("delete_age_days", 0) or 0)
    rules = lifecycle_document.get("lifecycle", {}).get("rule", [])
    if not isinstance(rules, list):
        errors.append("temporary bucket lifecycle.rule must be a list")
        rules = []
    has_delete = any(
        isinstance(rule, Mapping)
        and rule.get("action", {}).get("type") == "Delete"
        and rule.get("condition", {}).get("age") == expected_age
        for rule in rules
    )
    if expected_age < 1 or expected_age >= 7 or not has_delete:
        errors.append("temporary bucket must delete live objects with an age below seven days")
    soft_delete = lifecycle_document.get("softDeletePolicy", {})
    if int(soft_delete.get("retentionDurationSeconds", -1) or 0) != 0:
        errors.append("temporary bucket soft delete must be disabled")
    if contract:
        errors.extend(
            error.replace("bucket", "temporary bucket", 1)
            for error in validate_bucket_contract(name, {**lifecycle_document, "lifecycle": {"rule": []}}, contract)
            if "expires objects" not in error
        )
    return errors


def validate_contract_document(contract: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if contract.get("permanent_bucket_env_var") != "BUCKET_FRAME_REQUESTS":
        errors.append("bucket contract must name BUCKET_FRAME_REQUESTS")
    if contract.get("temporary_bucket_env_var") != "BUCKET_FRAME_REQUESTS_TEMPORARY":
        errors.append("bucket contract must name BUCKET_FRAME_REQUESTS_TEMPORARY")
    if contract.get("conversation_attachment_policy") != "conversation_lifetime":
        errors.append("bucket contract must preserve conversation-lifetime attachments")
    lifecycle = contract.get("lifecycle")
    if not isinstance(lifecycle, Mapping) or lifecycle.get("expires_objects") is not False:
        errors.append("bucket contract must explicitly disable object expiration")
    if not contract.get("allowed_locations"):
        errors.append("bucket contract must constrain location")
    if contract.get("uniform_bucket_level_access") is not True:
        errors.append("bucket contract must require uniform bucket-level access")
    if contract.get("public_access_prevention") != "enforced":
        errors.append("bucket contract must enforce public access prevention")
    temporary = contract.get("temporary_lifecycle")
    if not isinstance(temporary, Mapping) or not 1 <= int(temporary.get("delete_age_days", 0) or 0) < 7:
        errors.append("temporary bucket delete age must be below seven days")
    if not isinstance(temporary, Mapping) or temporary.get("soft_delete_retention_seconds") != 0:
        errors.append("temporary bucket soft delete must be disabled")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bucket", default=None)
    parser.add_argument("--lifecycle-json", type=Path, default=None)
    parser.add_argument("--temporary-bucket", default=None)
    parser.add_argument("--temporary-lifecycle-json", type=Path, default=None)
    parser.add_argument("--runtime-env", type=Path, default=None)
    parser.add_argument("--contract", type=Path, default=None)
    parser.add_argument("--source-only", action="store_true")
    args = parser.parse_args()
    errors: list[str] = []
    lifecycle = None
    if args.lifecycle_json:
        lifecycle = json.loads(args.lifecycle_json.read_text(encoding="utf-8"))
    temporary_lifecycle = None
    if args.temporary_lifecycle_json:
        temporary_lifecycle = json.loads(args.temporary_lifecycle_json.read_text(encoding="utf-8"))
    contract_document = None
    if args.runtime_env:
        try:
            runtime_document = yaml.safe_load(args.runtime_env.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            errors.append(f"could not read runtime env manifest: {exc}")
        else:
            if isinstance(runtime_document, Mapping):
                errors.extend(validate_runtime_binding(runtime_document))
            else:
                errors.append("runtime env manifest must be a mapping")
    if args.contract:
        try:
            contract = json.loads(args.contract.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"could not read bucket contract: {exc}")
        else:
            if isinstance(contract, Mapping):
                contract_document = contract
                errors.extend(validate_contract_document(contract))
            else:
                errors.append("bucket contract must be a JSON object")
    if args.source_only:
        if args.bucket or args.lifecycle_json or args.temporary_bucket or args.temporary_lifecycle_json:
            errors.append("--source-only cannot claim live bucket validation")
    else:
        errors.extend(validate_bucket_contract(args.bucket, lifecycle, contract_document))
        errors.extend(validate_temporary_bucket_contract(args.temporary_bucket, temporary_lifecycle, contract_document))
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("frame-request bucket contract passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
