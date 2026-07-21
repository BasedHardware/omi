#!/usr/bin/env python3
"""Validate and digest the immutable Omi desktop release manifest v1.

This module is intentionally stdlib-only so candidate, beta, and stable
workflows can use the exact same contract on clean runners. The detached
manifest digest is SHA-256 over UTF-8 JSON with sorted keys, no insignificant
whitespace, and non-ASCII characters preserved. A detached digest avoids the
self-referential ambiguity of embedding a manifest hash inside the manifest.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import hmac
import json
from pathlib import Path
import re
from typing import Any, NoReturn
from urllib.parse import unquote, urlparse

SCHEMA_VERSION = 1
PLATFORM = "macos"
BACKEND_MODES = frozenset({"app_only", "backend_required"})
SIGNATURE_PREFIX = "hmac-sha256:"
SIGNING_CONTEXT = b"omi-desktop-release-manifest-v1\0"
TOP_LEVEL_FIELDS = frozenset(
    {
        "schema_version",
        "release_id",
        "platform",
        "version",
        "build_number",
        "app_source_sha",
        "zip_url",
        "zip_sha256",
        "dmg_url",
        "dmg_sha256",
        "ed_signature",
        "beta_zip_url",
        "beta_zip_sha256",
        "beta_dmg_url",
        "beta_dmg_sha256",
        "beta_ed_signature",
        "qualification_evidence_asset",
        "qualification_evidence_sha256",
        "qualification_tier",
        "qualification_passed",
        "backend_mode",
        "desktop_backend_source_sha",
        "desktop_backend_oci_index_digest",
        "desktop_backend_platform_digest",
        "compatibility_contract",
        "environment_contract_version",
        "created_at",
    }
)
REQUIRED_FIELDS = frozenset(
    TOP_LEVEL_FIELDS
    - {
        "desktop_backend_source_sha",
        "desktop_backend_oci_index_digest",
        "desktop_backend_platform_digest",
    }
)
BACKEND_FIELDS = frozenset(
    {
        "desktop_backend_source_sha",
        "desktop_backend_oci_index_digest",
        "desktop_backend_platform_digest",
    }
)
COMPATIBILITY_BASE_FIELDS = frozenset(
    {
        "schema_version",
        "app_release_id",
        "app_version",
        "app_build_number",
        "backend_mode",
        "environment_contract_version",
    }
)
TAG_RE = re.compile(r"^v(?P<version>[0-9]+\.[0-9]+(?:\.[0-9]+)?)\+(?P<build>[1-9][0-9]*)-macos$")
SOURCE_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
EVIDENCE_ASSET_RE = re.compile(r"^qualification-evidence-[^/]+\.json$")
ENVIRONMENT_CONTRACT_RE = re.compile(r"^desktop-backend-env-v[1-9]\d*$")


class ManifestError(ValueError):
    """The release manifest violates the immutable v1 contract."""


def _fail(message: str) -> NoReturn:
    raise ManifestError(message)


def _require_exact_fields(data: dict[str, Any], required: frozenset[str], allowed: frozenset[str], label: str) -> None:
    missing = sorted(required - data.keys())
    unknown = sorted(data.keys() - allowed)
    if missing:
        _fail(f"{label} is missing required field(s): {', '.join(missing)}")
    if unknown:
        _fail(f"{label} has unknown field(s): {', '.join(unknown)}")


def _require_string(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        _fail(f"{key} must be a non-empty string")
    if value != value.strip():
        _fail(f"{key} must not have surrounding whitespace")
    return value


def _require_int(data: dict[str, Any], key: str) -> int:
    value = data.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        _fail(f"{key} must be a positive integer")
    return value


def _require_source_sha(data: dict[str, Any], key: str) -> str:
    value = _require_string(data, key)
    if not SOURCE_SHA_RE.fullmatch(value):
        _fail(f"{key} must be a lowercase 40-character Git SHA")
    return value


def _require_sha256(data: dict[str, Any], key: str) -> str:
    value = _require_string(data, key)
    if not SHA256_RE.fullmatch(value):
        _fail(f"{key} must use sha256:<64 lowercase hex> form")
    return value


def _require_release_asset_url(data: dict[str, Any], key: str, *, release_id: str, asset_name: str) -> str:
    value = _require_string(data, key)
    parsed = urlparse(value)
    if (
        parsed.scheme != "https"
        or parsed.netloc != "github.com"
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        _fail(f"{key} must be a clean github.com release asset URL")
    expected_prefix = "/BasedHardware/omi/releases/download/"
    if not parsed.path.startswith(expected_prefix):
        _fail(f"{key} must reference the BasedHardware/omi release")
    suffix = parsed.path.removeprefix(expected_prefix)
    try:
        encoded_tag, actual_asset = suffix.rsplit("/", 1)
    except ValueError:
        _fail(f"{key} must include a release tag and asset name")
    if unquote(encoded_tag) != release_id or actual_asset != asset_name:
        _fail(f"{key} must reference {asset_name} on release {release_id}")
    return value


def _require_timestamp(data: dict[str, Any], key: str) -> str:
    value = _require_string(data, key)
    if not value.endswith("Z"):
        _fail(f"{key} must be an RFC 3339 UTC timestamp ending in Z")
    try:
        parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError as exc:
        raise ManifestError(f"{key} must be an RFC 3339 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        _fail(f"{key} must be UTC")
    return value


def _validate_compatibility(manifest: dict[str, Any]) -> None:
    raw = manifest.get("compatibility_contract")
    if not isinstance(raw, dict):
        _fail("compatibility_contract must be an object")
    contract = raw
    mode = manifest["backend_mode"]
    allowed = COMPATIBILITY_BASE_FIELDS | (BACKEND_FIELDS if mode == "backend_required" else frozenset())
    _require_exact_fields(contract, allowed, allowed, "compatibility_contract")

    if contract.get("schema_version") != SCHEMA_VERSION:
        _fail("compatibility_contract.schema_version must be 1")
    exact_matches = {
        "app_release_id": manifest["release_id"],
        "app_version": manifest["version"],
        "app_build_number": manifest["build_number"],
        "backend_mode": mode,
        "environment_contract_version": manifest["environment_contract_version"],
    }
    if mode == "backend_required":
        exact_matches.update({field: manifest[field] for field in BACKEND_FIELDS})
    for field, expected in exact_matches.items():
        if contract.get(field) != expected:
            _fail(f"compatibility_contract.{field} must exactly match {field}")


def validate_manifest(value: object) -> dict[str, Any]:
    """Validate one v1 manifest and return it unchanged when valid."""
    if not isinstance(value, dict):
        _fail("manifest must be a JSON object")
    manifest = value
    _require_exact_fields(manifest, REQUIRED_FIELDS, TOP_LEVEL_FIELDS, "manifest")

    if manifest.get("schema_version") != SCHEMA_VERSION:
        _fail("schema_version must be 1")
    if manifest.get("platform") != PLATFORM:
        _fail("platform must be macos")

    release_id = _require_string(manifest, "release_id")
    match = TAG_RE.fullmatch(release_id)
    if not match:
        _fail("release_id must use v<version>+<build>-macos form")
    version = _require_string(manifest, "version")
    build_number = _require_int(manifest, "build_number")
    if version != match.group("version"):
        _fail("version must match release_id")
    if build_number != int(match.group("build")):
        _fail("build_number must match release_id")

    _require_source_sha(manifest, "app_source_sha")
    _require_release_asset_url(manifest, "zip_url", release_id=release_id, asset_name="Omi.zip")
    _require_sha256(manifest, "zip_sha256")
    _require_release_asset_url(manifest, "dmg_url", release_id=release_id, asset_name="omi.dmg")
    _require_sha256(manifest, "dmg_sha256")
    _require_string(manifest, "ed_signature")
    _require_release_asset_url(manifest, "beta_zip_url", release_id=release_id, asset_name="Omi.Beta.zip")
    _require_sha256(manifest, "beta_zip_sha256")
    _require_release_asset_url(manifest, "beta_dmg_url", release_id=release_id, asset_name="omi-beta.dmg")
    _require_sha256(manifest, "beta_dmg_sha256")
    _require_string(manifest, "beta_ed_signature")

    evidence_asset = _require_string(manifest, "qualification_evidence_asset")
    if not EVIDENCE_ASSET_RE.fullmatch(evidence_asset):
        _fail("qualification_evidence_asset must be a qualification-evidence-*.json asset name")
    _require_sha256(manifest, "qualification_evidence_sha256")
    if manifest.get("qualification_tier") != "T2" or manifest.get("qualification_passed") is not True:
        _fail("qualification must be passed at tier T2")

    mode = manifest.get("backend_mode")
    if mode not in BACKEND_MODES:
        _fail("backend_mode must be app_only or backend_required")
    present_backend_fields = BACKEND_FIELDS & manifest.keys()
    if mode == "app_only" and present_backend_fields:
        _fail(f"app_only manifest must omit backend field(s): {', '.join(sorted(present_backend_fields))}")
    if mode == "backend_required":
        missing_backend_fields = BACKEND_FIELDS - manifest.keys()
        if missing_backend_fields:
            _fail(f"backend_required manifest is missing field(s): {', '.join(sorted(missing_backend_fields))}")
        _require_source_sha(manifest, "desktop_backend_source_sha")
        if manifest["desktop_backend_source_sha"] != manifest["app_source_sha"]:
            _fail("desktop backend and app must come from the same source SHA")
        _require_sha256(manifest, "desktop_backend_oci_index_digest")
        _require_sha256(manifest, "desktop_backend_platform_digest")
        if manifest["desktop_backend_oci_index_digest"] == manifest["desktop_backend_platform_digest"]:
            _fail("OCI index and platform-child digests must identify distinct objects")

    environment_contract = _require_string(manifest, "environment_contract_version")
    if not ENVIRONMENT_CONTRACT_RE.fullmatch(environment_contract):
        _fail("environment_contract_version must use desktop-backend-env-vN form")
    _require_timestamp(manifest, "created_at")
    _validate_compatibility(manifest)
    return manifest


def canonical_bytes(manifest: object) -> bytes:
    """Return the deterministic bytes covered by the detached manifest digest."""
    validated = validate_manifest(manifest)
    return json.dumps(validated, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def manifest_digest(manifest: object) -> str:
    return f"sha256:{hashlib.sha256(canonical_bytes(manifest)).hexdigest()}"


def _require_signing_key(signing_key: bytes) -> None:
    if len(signing_key) < 32:
        _fail("manifest signing key must contain at least 32 bytes")


def manifest_signature(manifest: object, signing_key: bytes) -> str:
    """Sign canonical bytes with a separately controlled HMAC trust anchor."""
    _require_signing_key(signing_key)
    signature = hmac.new(signing_key, SIGNING_CONTEXT + canonical_bytes(manifest), hashlib.sha256).hexdigest()
    return f"{SIGNATURE_PREFIX}{signature}"


def verify_manifest_signature(manifest: object, signature: str, signing_key: bytes) -> None:
    _require_signing_key(signing_key)
    expected = manifest_signature(manifest, signing_key)
    if not hmac.compare_digest(expected, signature):
        _fail("manifest signature mismatch")


def require_digest_match(expected: str, actual: str, *, label: str) -> None:
    if not SHA256_RE.fullmatch(expected) or not SHA256_RE.fullmatch(actual):
        _fail(f"{label} digest must use sha256:<64 lowercase hex> form")
    if not hmac.compare_digest(expected, actual):
        _fail(f"{label} digest mismatch: expected {expected}, got {actual}")


def verify_manifest_digest(manifest: object, expected_digest: str) -> None:
    require_digest_match(expected_digest, manifest_digest(manifest), label="manifest")


def verify_manifest_integrity(
    manifest: object,
    expected_digest: str,
    signature: str,
    signing_key: bytes,
) -> None:
    """Verify both public drift detection and the independent trust anchor."""
    verify_manifest_digest(manifest, expected_digest)
    verify_manifest_signature(manifest, signature, signing_key)


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def verify_artifact(path: Path, expected_digest: str, *, label: str) -> None:
    require_digest_match(expected_digest, file_digest(path), label=label)


def _load_manifest(path: Path) -> object:
    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                _fail(f"manifest JSON contains duplicate key: {key}")
            result[key] = value
        return result

    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=reject_duplicate_keys)


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser("validate")
    validate.add_argument("manifest", type=Path)
    digest = subparsers.add_parser("digest")
    digest.add_argument("manifest", type=Path)
    verify = subparsers.add_parser("verify")
    verify.add_argument("manifest", type=Path)
    verify.add_argument("--digest", required=True)
    verify.add_argument("--signature", required=True)
    verify.add_argument("--signing-key-file", required=True, type=Path)
    sign = subparsers.add_parser("sign")
    sign.add_argument("manifest", type=Path)
    sign.add_argument("--signing-key-file", required=True, type=Path)
    args = parser.parse_args()

    try:
        manifest = _load_manifest(args.manifest)
        if args.command == "validate":
            validate_manifest(manifest)
            print(f"desktop release manifest v{SCHEMA_VERSION} valid: {args.manifest}")
        elif args.command == "digest":
            print(manifest_digest(manifest))
        elif args.command == "verify":
            verify_manifest_integrity(
                manifest,
                args.digest,
                args.signature,
                args.signing_key_file.read_bytes(),
            )
            print(f"desktop release manifest integrity verified: {args.manifest}")
        else:
            print(manifest_signature(manifest, args.signing_key_file.read_bytes()))
    except (ManifestError, json.JSONDecodeError, OSError) as exc:
        raise SystemExit(f"FAIL: {exc}") from exc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
