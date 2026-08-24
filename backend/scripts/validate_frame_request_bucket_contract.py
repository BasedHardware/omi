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


def _find_bindings(value: Any) -> list[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        bindings: list[Mapping[str, Any]] = []
        for key, child in value.items():
            if key == "BUCKET_FRAME_REQUESTS" and isinstance(child, Mapping):
                bindings.append(child)
            bindings.extend(_find_bindings(child))
        return bindings
    if isinstance(value, list):
        bindings = []
        for child in value:
            bindings.extend(_find_bindings(child))
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
    bindings = _find_bindings(runtime_document)
    if not bindings:
        return ["runtime manifest must bind BUCKET_FRAME_REQUESTS"]
    errors: list[str] = []
    for index, binding in enumerate(bindings):
        if binding.get("env_var") != "BUCKET_FRAME_REQUESTS":
            errors.append(f"runtime BUCKET_FRAME_REQUESTS binding {index} must preserve the env var name")
        if not (str(binding.get("default") or binding.get("value") or "").strip() or binding.get("env_var")):
            errors.append(f"runtime BUCKET_FRAME_REQUESTS binding {index} has no value or env var")
    return errors


def validate_contract_document(contract: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if contract.get("bucket_env_var") != "BUCKET_FRAME_REQUESTS":
        errors.append("bucket contract must name BUCKET_FRAME_REQUESTS")
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
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bucket", default=None)
    parser.add_argument("--lifecycle-json", type=Path, default=None)
    parser.add_argument("--runtime-env", type=Path, default=None)
    parser.add_argument("--contract", type=Path, default=None)
    parser.add_argument("--source-only", action="store_true")
    args = parser.parse_args()
    errors: list[str] = []
    lifecycle = None
    if args.lifecycle_json:
        lifecycle = json.loads(args.lifecycle_json.read_text(encoding="utf-8"))
    contract_document = None
    if args.runtime_env:
        try:
            import yaml

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
        if args.bucket or args.lifecycle_json:
            errors.append("--source-only cannot claim live bucket validation")
    else:
        errors.extend(validate_bucket_contract(args.bucket, lifecycle, contract_document))
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("frame-request bucket contract passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
