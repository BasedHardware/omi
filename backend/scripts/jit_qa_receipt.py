#!/usr/bin/env python3
"""Produce a content-free readiness candidate for the isolated JIT QA plane."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Mapping

SCHEMA_VERSION = "omi.jit.qa.cloud.v1"
PROJECT = "based-hardware-dev"
REGION = "us-central1"
AUTH_PROJECT = "based-hardware"
FIRESTORE_DATABASE = "jit-qa"
_REVISION_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_DIGEST_IMAGE_RE = re.compile(r"^gcr\.io/based-hardware-dev/[a-z0-9-]+@sha256:[0-9a-f]{64}$")


def require_sha(value: str, *, label: str) -> None:
    if not _SHA_RE.fullmatch(value):
        raise ValueError(f"{label} must be a full lowercase 40-character SHA")


def require_digest_image(value: str, *, label: str) -> None:
    if not _DIGEST_IMAGE_RE.fullmatch(value):
        raise ValueError(f"{label} must be a dev GCR image pinned by sha256 digest")


def _containers(resource: Mapping[str, Any], *, kind: str) -> list[Mapping[str, Any]]:
    paths = (
        (("spec", "template", "spec", "containers"), ("spec", "template", "containers"))
        if kind == "service"
        else (
            ("spec", "template", "spec", "template", "spec", "containers"),
            ("spec", "template", "spec", "template", "containers"),
            ("spec", "template", "template", "spec", "containers"),
            ("spec", "template", "template", "containers"),
        )
    )
    value: object = None
    for path in paths:
        candidate: object = resource
        for key in path:
            candidate = candidate.get(key) if isinstance(candidate, Mapping) else None
        if candidate is not None:
            value = candidate
            break
    if not isinstance(value, list) or len(value) != 1 or not isinstance(value[0], dict):
        raise ValueError(f"Cloud Run {kind} must have exactly one application container")
    return value


def _load(path: Path) -> Mapping[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain an object")
    return payload


def _revision(resource: Mapping[str, Any], *, label: str) -> str:
    status = resource.get("status")
    revision = status.get("latestReadyRevisionName") if isinstance(status, Mapping) else None
    if not isinstance(revision, str) or not _REVISION_RE.fullmatch(revision):
        raise ValueError(f"{label} has no exact ready revision")
    created = status.get("latestCreatedRevisionName") if isinstance(status, Mapping) else None
    if created is not None and created != revision:
        raise ValueError(f"{label} has a newer non-serving revision than the ready revision")
    traffic = status.get("traffic") if isinstance(status, Mapping) else None
    serving = (
        [
            item.get("revisionName")
            for item in traffic
            if isinstance(item, Mapping) and item.get("percent") == 100 and item.get("revisionName")
        ]
        if isinstance(traffic, list)
        else []
    )
    if serving != [revision]:
        raise ValueError(f"{label} does not have exactly one 100 percent serving revision")
    return revision


def _image(resource: Mapping[str, Any], *, kind: str, label: str) -> str:
    containers = _containers(resource, kind=kind)
    image = containers[0].get("image")
    if not isinstance(image, str):
        raise ValueError(f"{label} has no immutable image")
    require_digest_image(image, label=label)
    return image.rsplit("@", 1)[1]


def build_receipt(
    *,
    source_sha: str,
    python_resource: Mapping[str, Any],
    desktop_resource: Mapping[str, Any],
    gateway_resource: Mapping[str, Any],
    python_url: str,
    desktop_url: str,
    gateway_url: str,
    app_probe: bool,
    gateway_probe: bool,
) -> dict[str, Any]:
    require_sha(source_sha, label="source_sha")
    for value, label in ((python_url, "python_url"), (desktop_url, "desktop_url"), (gateway_url, "gateway_url")):
        if not value.startswith("https://"):
            raise ValueError(f"{label} must be an HTTPS Cloud Run URL")
    if not app_probe or not gateway_probe:
        raise ValueError("readiness requires successful app and gateway probes")
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "ready",
        # A human/root review must promote this candidate to an activation
        # receipt after independently checking the exact live resources.
        "reviewed": False,
        "project": PROJECT,
        "data_plane_project": PROJECT,
        "region": REGION,
        "auth_project": AUTH_PROJECT,
        "python_service": "backend-jit-qa",
        "desktop_service": "desktop-backend-jit-qa",
        "gateway_service": "llm-gateway-jit-qa",
        "exact_python_url": python_url,
        "exact_desktop_url": desktop_url,
        "exact_gateway_url": gateway_url,
        "full_source_sha": source_sha,
        "firestore_database_id": FIRESTORE_DATABASE,
        "python_revision": _revision(python_resource, label="python service"),
        "python_image_digest": _image(python_resource, kind="service", label="python image"),
        "desktop_revision": _revision(desktop_resource, label="desktop service"),
        "desktop_image_digest": _image(desktop_resource, kind="service", label="desktop image"),
        "gateway_revision": _revision(gateway_resource, label="gateway service"),
        "gateway_image_digest": _image(gateway_resource, kind="service", label="gateway image"),
        "dependency_vector": {
            "firestore": "based-hardware-dev",
            "redis": "jit-qa-redis:basic-1GiB",
            "gateway": "llm-gateway-jit-qa:service-token",
            "typesense": "typesense-jit-qa:api-key",
            "firebase_auth": "based-hardware:verify-only",
            "storage": "none",
            "pubsub": "none",
            "scheduler": "none",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--python-json", type=Path, required=True)
    parser.add_argument("--desktop-json", type=Path, required=True)
    parser.add_argument("--gateway-json", type=Path, required=True)
    parser.add_argument("--python-url", required=True)
    parser.add_argument("--desktop-url", required=True)
    parser.add_argument("--gateway-url", required=True)
    parser.add_argument("--app-probe", action="store_true")
    parser.add_argument("--gateway-probe", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    receipt = build_receipt(
        source_sha=args.source_sha,
        python_resource=_load(args.python_json),
        desktop_resource=_load(args.desktop_json),
        gateway_resource=_load(args.gateway_json),
        python_url=args.python_url,
        desktop_url=args.desktop_url,
        gateway_url=args.gateway_url,
        app_probe=args.app_probe,
        gateway_probe=args.gateway_probe,
    )
    args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("JIT QA readiness candidate written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
