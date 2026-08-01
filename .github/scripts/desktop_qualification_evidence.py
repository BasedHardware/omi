#!/usr/bin/env python3
"""Build and verify immutable trusted desktop qualification evidence.

The evidence is uploaded as a GitHub Actions artifact by the trusted
qualification run.  Its run ID is the authority boundary: promotion verifies
that run came from this workflow on main and then compares freshly downloaded
release bytes with this document.  GitHub release bodies/assets are never the
qualification authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from typing import Any

ARTIFACTS = ("Omi.zip", "omi.dmg")
# INV-BETA-1: releases that ship the side-by-side Omi Beta identity carry two
# additional qualified artifacts; older single-identity releases remain valid.
BETA_ARTIFACTS = ("Omi.Beta.zip", "omi-beta.dmg")
ZIP_SIGNATURES = {"Omi.zip": "edSignature", "Omi.Beta.zip": "betaEdSignature"}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _fail(message: str) -> None:
    raise ValueError(f"qualification evidence {message}")


def _metadata(body: str) -> dict[str, str]:
    match = re.search(r"KEY_VALUE_START\s*(.*?)\s*KEY_VALUE_END", body, re.DOTALL)
    if not match:
        return {}
    return {
        key.strip(): value.strip()
        for key, value in (line.split(":", 1) for line in match.group(1).splitlines() if ":" in line)
    }


def _asset(release: dict[str, Any], name: str) -> dict[str, Any]:
    matches = [item for item in release.get("assets", []) if item.get("name") == name]
    if len(matches) != 1:
        _fail(f"requires exactly one {name} asset")
    return matches[0]


def _url(asset: dict[str, Any]) -> str:
    value = asset.get("url") or asset.get("browser_download_url")
    if not isinstance(value, str) or not value.startswith("https://"):
        _fail("contains an invalid asset URL")
    return value


def _expected_artifact_names(release: dict[str, Any]) -> set[str]:
    """Return the only valid artifact topology for this immutable release."""
    release_names = {asset.get("name") for asset in release.get("assets", []) if isinstance(asset, dict)}
    beta_names = set(BETA_ARTIFACTS)
    beta_present = release_names & beta_names
    if beta_present and beta_present != beta_names:
        _fail("contains an incomplete Omi Beta artifact pair")
    expected = set(ARTIFACTS) | beta_present
    for name in expected:
        _asset(release, name)
    return expected


def file_sha256(path: Path) -> str:
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def _beta_uid_continuity(path: Path) -> dict[str, object]:
    try:
        proof = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("qualification evidence has unreadable Beta UID-continuity proof") from error
    expected = {
        "schema_version": 1,
        "status": "passed",
        "firebase_auth": {
            "project": "based-hardware",
            "release_probe_uid": "omi-release-probe",
            "token_claims": "production_project_verified",
        },
        "development_serving_reads": {
            "python": {
                "url": "https://api.omiapi.com/",
                "production_authority_url": "https://api.omi.me/",
                "operation": "production_sentinel_development_read_cleanup",
                "status": "passed",
            },
            "desktop_backend": {
                "url": "https://desktop-backend-dt5lrfkkoa-uc.a.run.app/",
                "operation": "authenticated_proxy_authority_read",
                "status": "passed",
            },
        },
        "redaction": {"customer_content_printed": False, "tokens_printed": False},
    }
    if proof != expected:
        _fail("contains an invalid Beta UID-continuity proof")
    return proof


def build_evidence(
    release: dict[str, Any],
    release_tag: str,
    source_sha: str,
    files: dict[str, Path],
    qualification_run_id: int | None = None,
    beta_uid_continuity_path: Path | None = None,
) -> dict[str, Any]:
    if release.get("tagName") != release_tag:
        _fail("release ID does not match requested tag")
    if not re.fullmatch(r"[0-9a-f]{40}", source_sha):
        _fail("source SHA is not an exact 40-character SHA")
    files = dict(files)
    gate = files.pop("__candidate_gate__")
    candidate_gate = json.loads(gate.read_text(encoding="utf-8"))
    if (
        candidate_gate.get("passed") is not True
        or candidate_gate.get("release_tag") != release_tag
        or candidate_gate.get("source_sha") != source_sha
    ):
        _fail("was not created after the passing candidate gate")
    metadata = _metadata(str(release.get("body") or ""))
    artifacts: dict[str, dict[str, str]] = {}
    expected_names = _expected_artifact_names(release)
    if set(files) != expected_names:
        _fail("does not contain the exact qualified Omi.zip and omi.dmg (plus both beta artifacts when present)")
    for name, path in files.items():
        if not path.is_file():
            _fail(f"is missing downloaded {name}")
        asset = _asset(release, name)
        digest = file_sha256(path)
        published = str(asset.get("digest") or "").removeprefix("sha256:")
        if published and published != digest:
            _fail(f"{name} differs from its published candidate digest")
        item = {"url": _url(asset), "sha256": digest}
        signature_key = ZIP_SIGNATURES.get(name)
        if signature_key:
            signature = metadata.get(signature_key, "")
            if not signature:
                _fail(f"is missing {signature_key}")
            item["signature"] = signature
        artifacts[name] = item
    evidence = {
        "schema_version": 1,
        "release_id": release_tag,
        "source_sha": source_sha,
        "source_qualification": {
            "passed": True,
            "tier": "T2",
            "subject": "source-built named-bundle",
            "fault_evidence": "trusted qualification runner",
        },
        "signed_artifact_verification": {
            "passed": True,
            "subject": "exact signed ZIP/DMG bytes",
            "checks": ["sha256", "Sparkle signature", "notarization", "signed smoke"],
        },
        "artifacts": artifacts,
    }
    if qualification_run_id is not None:
        if qualification_run_id <= 0:
            _fail("has an invalid qualification run identity")
        evidence["qualification_run_id"] = qualification_run_id
    if "Omi.Beta.zip" in artifacts:
        if beta_uid_continuity_path is None:
            _fail("requires Beta UID-continuity proof when Beta artifacts are qualified")
        evidence["beta_uid_continuity"] = _beta_uid_continuity(beta_uid_continuity_path)
    return evidence


def verify_evidence(
    evidence: dict[str, Any], release: dict[str, Any], release_tag: str, source_sha: str, digests: dict[str, str]
) -> None:
    if (
        evidence.get("schema_version") != 1
        or evidence.get("release_id") != release_tag
        or evidence.get("source_sha") != source_sha
    ):
        _fail("release ID or source SHA does not match the trusted run")
    source_qualification = evidence.get("source_qualification")
    signed_artifacts = evidence.get("signed_artifact_verification")
    if (
        not isinstance(source_qualification, dict)
        or source_qualification.get("passed") is not True
        or source_qualification.get("tier") != "T2"
    ):
        _fail("does not prove source-built named-bundle T2 qualification")
    if not isinstance(signed_artifacts, dict) or signed_artifacts.get("passed") is not True:
        _fail("does not prove exact signed artifact verification")
    if signed_artifacts.get("subject") != "exact signed ZIP/DMG bytes":
        _fail("must not claim signed production bytes ran T2")
    expected_names = _expected_artifact_names(release)
    if set(digests) != expected_names:
        _fail("artifact set differs from the immutable release topology")
    if "Omi.Beta.zip" in expected_names:
        continuity = evidence.get("beta_uid_continuity")
        if not isinstance(continuity, dict):
            _fail("does not prove Beta UID continuity")
        expected_continuity = {
            "schema_version": 1,
            "status": "passed",
            "firebase_auth": {
                "project": "based-hardware",
                "release_probe_uid": "omi-release-probe",
                "token_claims": "production_project_verified",
            },
            "development_serving_reads": {
                "python": {
                    "url": "https://api.omiapi.com/",
                    "production_authority_url": "https://api.omi.me/",
                    "operation": "production_sentinel_development_read_cleanup",
                    "status": "passed",
                },
                "desktop_backend": {
                    "url": "https://desktop-backend-dt5lrfkkoa-uc.a.run.app/",
                    "operation": "authenticated_proxy_authority_read",
                    "status": "passed",
                },
            },
            "redaction": {"customer_content_printed": False, "tokens_printed": False},
        }
        if continuity != expected_continuity:
            _fail("contains invalid Beta UID continuity")
    artifacts = evidence.get("artifacts")
    if not isinstance(artifacts, dict):
        _fail("does not contain artifacts")
    metadata = _metadata(str(release.get("body") or ""))
    if set(artifacts) != expected_names:
        _fail("artifact set differs from the downloaded release")
    for name, actual_sha in digests.items():
        item = artifacts.get(name)
        if not isinstance(item, dict) or item.get("sha256") != actual_sha or not SHA256_RE.fullmatch(actual_sha):
            _fail(f"{name} hash differs from trusted evidence")
        if item.get("url") != _url(_asset(release, name)):
            _fail(f"{name} URL differs from trusted evidence")
        signature_key = ZIP_SIGNATURES.get(name)
        if signature_key and item.get("signature") != metadata.get(signature_key):
            _fail(f"{name} signature differs from trusted evidence")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("build", "verify"))
    parser.add_argument("--release-json", required=True)
    parser.add_argument("--release-tag", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--candidate-gate")
    parser.add_argument("--qualification-run-id", type=int)
    parser.add_argument("--beta-uid-continuity-evidence")
    parser.add_argument("--asset", action="append", default=[])
    args = parser.parse_args()
    release = json.loads(Path(args.release_json).read_text(encoding="utf-8"))
    files: dict[str, Path] = {}
    for raw in args.asset:
        name, sep, path = raw.partition("=")
        if not sep or name not in (*ARTIFACTS, *BETA_ARTIFACTS):
            raise SystemExit("--asset must be NAME=PATH for a qualified release artifact")
        files[name] = Path(path)
    if args.command == "build":
        if not args.candidate_gate:
            raise SystemExit("build requires --candidate-gate")
        files["__candidate_gate__"] = Path(args.candidate_gate)
        result = build_evidence(
            release,
            args.release_tag,
            args.source_sha,
            files,
            args.qualification_run_id,
            Path(args.beta_uid_continuity_evidence) if args.beta_uid_continuity_evidence else None,
        )
        Path(args.evidence).write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    else:
        evidence = json.loads(Path(args.evidence).read_text(encoding="utf-8"))
        verify_evidence(
            evidence,
            release,
            args.release_tag,
            args.source_sha,
            {name: file_sha256(path) for name, path in files.items()},
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
