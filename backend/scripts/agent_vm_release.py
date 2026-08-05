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
    return command


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if not 0 <= args.rollout_target_percent <= 100:
        raise SystemExit("rollout target must be between 0 and 100")
    if not 1 <= args.max_concurrency <= 50:
        raise SystemExit("max concurrency must be between 1 and 50")
    payload = render_manifest(args)
    args.output.write_bytes(canonical_bytes(payload))
    print(json.dumps({"manifestSha256": payload["manifestSha256"], "sourceSha": args.source_sha}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
