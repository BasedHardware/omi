#!/usr/bin/env python3
"""Verify that a Cloud Run image is the runnable child of an immutable build image."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

DIGEST_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")
INDEX_MEDIA_TYPES = {
    "application/vnd.docker.distribution.manifest.list.v2+json",
    "application/vnd.oci.image.index.v1+json",
}
IMAGE_MEDIA_TYPES = {
    "application/vnd.docker.distribution.manifest.v2+json",
    "application/vnd.oci.image.manifest.v1+json",
}
RUNTIME_OS = "linux"
RUNTIME_ARCHITECTURE = "amd64"
ATTESTATION_REFERENCE_TYPE = "attestation-manifest"


class LineageError(ValueError):
    """Raised when the runtime image cannot be proven from the build image."""


def _parse_immutable_image_reference(reference: str) -> tuple[str, str]:
    if reference != reference.strip() or any(character.isspace() for character in reference):
        raise LineageError("image reference must not contain whitespace")
    repository, separator, digest = reference.rpartition("@")
    if not separator or not repository or not DIGEST_PATTERN.fullmatch(digest):
        raise LineageError(f"image reference must use an exact sha256 digest: {reference!r}")
    if "@" in repository or ":" in repository.rsplit("/", 1)[-1]:
        raise LineageError(f"image reference must not include a mutable tag: {reference!r}")
    return repository, digest


def verify_lineage(
    *,
    build_image_reference: str,
    runtime_image_reference: str,
    manifest: dict[str, Any],
) -> dict[str, object]:
    build_repository, build_digest = _parse_immutable_image_reference(build_image_reference)
    runtime_repository, runtime_digest = _parse_immutable_image_reference(runtime_image_reference)
    if runtime_repository != build_repository:
        raise LineageError(
            f"runtime repository {runtime_repository!r} does not match build repository {build_repository!r}"
        )
    if manifest.get("schemaVersion") != 2:
        raise LineageError("build image manifest must use OCI/Docker schema version 2")

    media_type = manifest.get("mediaType")
    if media_type in INDEX_MEDIA_TYPES:
        descriptors = manifest.get("manifests")
        if not isinstance(descriptors, list) or not descriptors:
            raise LineageError("build image index has no manifest descriptors")
        runtime_descriptors = [
            descriptor
            for descriptor in descriptors
            if isinstance(descriptor, dict)
            and isinstance(descriptor.get("platform"), dict)
            and descriptor["platform"].get("architecture") == RUNTIME_ARCHITECTURE
            and descriptor["platform"].get("os") == RUNTIME_OS
        ]
        if len(runtime_descriptors) != 1:
            raise LineageError(
                "build image index must contain exactly one linux/amd64 runtime manifest "
                f"(found {len(runtime_descriptors)})"
            )
        runtime_descriptor = runtime_descriptors[0]
        annotations = runtime_descriptor.get("annotations")
        if annotations is not None and not isinstance(annotations, dict):
            raise LineageError("linux/amd64 runtime descriptor has malformed annotations")
        if annotations is not None and any(
            not isinstance(key, str) or not isinstance(value, str) for key, value in annotations.items()
        ):
            raise LineageError("linux/amd64 runtime descriptor annotations must be a string-to-string map")
        if annotations and annotations.get("vnd.docker.reference.type") == ATTESTATION_REFERENCE_TYPE:
            raise LineageError("linux/amd64 runtime descriptor is an attestation, not a runnable image")
        expected_runtime_digest = runtime_descriptor.get("digest")
        descriptor_media_type = runtime_descriptor.get("mediaType")
        if not isinstance(expected_runtime_digest, str) or not DIGEST_PATTERN.fullmatch(expected_runtime_digest):
            raise LineageError("linux/amd64 runtime descriptor has an invalid digest")
        if descriptor_media_type not in IMAGE_MEDIA_TYPES:
            raise LineageError(f"linux/amd64 runtime descriptor has unsupported media type {descriptor_media_type!r}")
        if runtime_digest != expected_runtime_digest:
            raise LineageError(
                f"Cloud Run resolved {runtime_digest}, but immutable build index {build_digest} "
                f"selects {expected_runtime_digest} for linux/amd64"
            )
        lineage_kind = "image-index-platform-child"
        descriptor_count = len(descriptors)
    elif media_type in IMAGE_MEDIA_TYPES:
        if runtime_digest != build_digest:
            raise LineageError(f"Cloud Run resolved {runtime_digest}, but the immutable build image is {build_digest}")
        expected_runtime_digest = build_digest
        descriptor_media_type = media_type
        lineage_kind = "direct-image-manifest"
        descriptor_count = 1
    else:
        raise LineageError(f"build image has unsupported media type {media_type!r}")

    return {
        "build_image": {
            "digest": build_digest,
            "media_type": media_type,
            "reference": build_image_reference,
        },
        "desktop_backend_oci_index_digest": build_digest,
        "desktop_backend_platform_digest": runtime_digest,
        "lineage": {
            "descriptor_count": descriptor_count,
            "kind": lineage_kind,
            "selected_manifest_digest": expected_runtime_digest,
            "selected_manifest_media_type": descriptor_media_type,
        },
        "runtime_image": {
            "architecture": RUNTIME_ARCHITECTURE,
            "digest": runtime_digest,
            "os": RUNTIME_OS,
            "reference": runtime_image_reference,
        },
        "schema_version": 1,
        "status": "passed",
    }


def _inspect_manifest(image_reference: str) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            ["docker", "buildx", "imagetools", "inspect", "--raw", image_reference],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except OSError as error:
        raise LineageError(f"could not inspect immutable build image: {error}") from error
    if completed.returncode != 0:
        detail = completed.stderr.strip().splitlines()
        suffix = f": {detail[-1]}" if detail else ""
        raise LineageError(f"could not inspect immutable build image{suffix}")
    try:
        manifest = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise LineageError("registry returned invalid build image manifest JSON") from error
    if not isinstance(manifest, dict):
        raise LineageError("registry returned a non-object build image manifest")
    return manifest


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--build-image-ref", required=True)
    parser.add_argument("--runtime-image-ref", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--evidence-path", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        evidence = verify_lineage(
            build_image_reference=args.build_image_ref,
            runtime_image_reference=args.runtime_image_ref,
            manifest=_inspect_manifest(args.build_image_ref),
        )
    except LineageError as error:
        print(f"desktop-backend image lineage verification failed: {error}", file=sys.stderr)
        return 1

    evidence["revision"] = args.revision
    evidence["source_sha"] = args.source_sha
    args.evidence_path.parent.mkdir(parents=True, exist_ok=True)
    args.evidence_path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(evidence["runtime_image"]["digest"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
