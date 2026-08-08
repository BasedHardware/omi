#!/usr/bin/env python3
"""Render and validate immutable Agent VM release manifests.

This command is intentionally filesystem-only.  CI publishes the resulting
artifacts with ``gcloud storage cp -n`` and activates the small mutable pointer
only after the desktop backend serving gate succeeds.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

SHA256 = re.compile(r"^[0-9a-f]{64}$")
SOURCE_SHA = re.compile(r"^[0-9a-f]{40}$")
IMAGE_DIGEST = re.compile(r"^.+@sha256:[0-9a-f]{64}$")
SERVICE_ACCOUNT = re.compile(r"^[^@\s]+@[^@\s]+\.iam\.gserviceaccount\.com$")
PRODUCTION_MIGRATION_APPROVAL_POLICY = "state-preserving-v1"
PRODUCTION_MIGRATION_MIN_ADMISSION_SOAK_SECONDS = 10 * 60
PRODUCTION_MIGRATION_MIN_RETENTION_SECONDS = 7 * 24 * 60 * 60


def canonical_bytes(payload: Mapping[str, Any]) -> bytes:
    return (json.dumps(dict(payload), sort_keys=True, separators=(",", ":")) + "\n").encode()


def render_manifest(args: argparse.Namespace) -> dict[str, Any]:
    values = {
        "schemaVersion": 1,
        "environment": args.environment,
        "sourceSha": args.source_sha,
        "imageDigest": args.image_digest,
        "startupUri": args.startup_uri,
        "startupSha256": args.startup_sha256,
        "bootImage": args.boot_image,
        "serviceAccount": args.service_account,
        "rollout": {
            "phase": args.rollout_phase,
            "targetPercent": args.rollout_target_percent,
            "maxConcurrency": args.max_concurrency,
        },
    }
    # Replacement is deliberately a separately selected artifact, not an
    # automatic consequence of publishing a newer boot image. Production adds
    # a one-owner, seven-day-retention approval policy as a second fence.
    if args.boot_image_migration_allowed_uid:
        values["bootImageMigration"] = {
            "enabled": True,
            "allowedUids": sorted(set(args.boot_image_migration_allowed_uid)),
            "maxConcurrency": 1,
            "soakSeconds": args.boot_image_migration_soak_seconds,
            "retentionSeconds": (args.boot_image_migration_retention_seconds or args.boot_image_migration_soak_seconds),
            "drainRunning": args.boot_image_migration_drain_running,
            **(
                {"approvalPolicy": args.boot_image_migration_approval_policy}
                if args.boot_image_migration_approval_policy
                else {}
            ),
        }
    validate_manifest(values)
    values["manifestSha256"] = hashlib.sha256(canonical_bytes(values)).hexdigest()
    return values


def validate_manifest(payload: Mapping[str, Any]) -> None:
    required = ("environment", "sourceSha", "imageDigest", "startupUri", "startupSha256", "bootImage", "serviceAccount")
    missing = [key for key in required if not isinstance(payload.get(key), str) or not str(payload[key]).strip()]
    if missing:
        raise ValueError(f"missing release fields: {', '.join(missing)}")
    if payload.get("schemaVersion") != 1:
        raise ValueError("schemaVersion must be 1")
    if not SOURCE_SHA.fullmatch(str(payload["sourceSha"])):
        raise ValueError("sourceSha must be a lowercase 40-character SHA")
    if not IMAGE_DIGEST.fullmatch(str(payload["imageDigest"])):
        raise ValueError("imageDigest must be an immutable @sha256 image")
    if not (
        str(payload["startupUri"]).startswith("gs://")
        or str(payload["startupUri"]).startswith("https://storage.googleapis.com/")
    ):
        raise ValueError("startupUri must use gs:// or storage.googleapis.com")
    if not SHA256.fullmatch(str(payload["startupSha256"])):
        raise ValueError("startupSha256 must be a lowercase SHA-256 digest")
    if not SERVICE_ACCOUNT.fullmatch(str(payload["serviceAccount"])):
        raise ValueError("serviceAccount must be a Google service-account email")
    migration = payload.get("bootImageMigration")
    if migration is not None:
        if (
            not isinstance(migration, Mapping)
            or migration.get("enabled") is not True
            or not isinstance(migration.get("allowedUids"), list)
            or not migration["allowedUids"]
            or not all(isinstance(uid, str) and uid.strip() for uid in migration["allowedUids"])
            or migration.get("maxConcurrency") != 1
            or not isinstance(migration.get("soakSeconds"), int)
            or migration["soakSeconds"] < 60
            or not isinstance(migration.get("retentionSeconds", migration.get("soakSeconds")), int)
            or migration.get("retentionSeconds", migration.get("soakSeconds")) < migration["soakSeconds"]
            or not isinstance(migration.get("drainRunning", False), bool)
        ):
            raise ValueError("bootImageMigration must be an explicit allowlist with a safe soak")
        environment = payload.get("environment")
        allowed_uids = {uid.strip() for uid in migration["allowedUids"]}
        if environment == "production":
            if (
                migration.get("approvalPolicy") != PRODUCTION_MIGRATION_APPROVAL_POLICY
                or len(allowed_uids) != 1
                or migration["soakSeconds"] < PRODUCTION_MIGRATION_MIN_ADMISSION_SOAK_SECONDS
                or migration["retentionSeconds"] < PRODUCTION_MIGRATION_MIN_RETENTION_SECONDS
                or migration.get("drainRunning") is not True
            ):
                raise ValueError(
                    "production bootImageMigration requires one canary, fenced drain, approved policy, and seven-day retention"
                )
        elif environment != "development":
            raise ValueError("bootImageMigration requires an approved environment")
    if "manifestSha256" in payload:
        unsigned = dict(payload)
        declared = unsigned.pop("manifestSha256")
        if not isinstance(declared, str) or not SHA256.fullmatch(declared):
            raise ValueError("manifestSha256 must be a lowercase SHA-256 digest")
        if hashlib.sha256(canonical_bytes(unsigned)).hexdigest() != declared:
            raise ValueError("manifestSha256 does not match the manifest")


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("--output", type=Path, required=True)
    command.add_argument("--environment", required=True)
    command.add_argument("--source-sha", required=True)
    command.add_argument("--image-digest", required=True)
    command.add_argument("--startup-uri", required=True)
    command.add_argument("--startup-sha256", required=True)
    command.add_argument("--boot-image", required=True)
    command.add_argument("--service-account", required=True)
    command.add_argument("--rollout-target-percent", type=int, default=100)
    command.add_argument("--max-concurrency", type=int, default=5)
    command.add_argument("--rollout-phase", choices=("sentinel", "canary", "quarter", "remainder"), default="remainder")
    command.add_argument(
        "--boot-image-migration-allowed-uid",
        action="append",
        default=[],
        help="Explicit migration allowlist; production accepts exactly one canary owner.",
    )
    command.add_argument("--boot-image-migration-soak-seconds", type=int, default=600)
    command.add_argument("--boot-image-migration-retention-seconds", type=int)
    command.add_argument("--boot-image-migration-drain-running", action="store_true")
    command.add_argument("--boot-image-migration-approval-policy", default="")
    return command


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if not 0 <= args.rollout_target_percent <= 100:
        raise SystemExit("rollout target must be between 0 and 100")
    if not 1 <= args.max_concurrency <= 50:
        raise SystemExit("max concurrency must be between 1 and 50")
    if args.boot_image_migration_soak_seconds < 60:
        raise SystemExit("boot-image migration soak must be at least 60 seconds")
    payload = render_manifest(args)
    args.output.write_bytes(canonical_bytes(payload))
    print(json.dumps({"manifestSha256": payload["manifestSha256"], "sourceSha": args.source_sha}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
