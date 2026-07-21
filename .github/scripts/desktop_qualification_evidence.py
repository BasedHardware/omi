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
ZIP_SIGNATURES = {"Omi.zip": "edSignature"}
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


def file_sha256(path: Path) -> str:
    return hashlib.file_digest(path.open("rb"), "sha256").hexdigest()


def build_evidence(
    release: dict[str, Any], release_tag: str, source_sha: str, files: dict[str, Path]
) -> dict[str, Any]:
    if release.get("tagName") != release_tag:
        _fail("release ID does not match requested tag")
    if not re.fullmatch(r"[0-9a-f]{40}", source_sha):
        _fail("source SHA is not an exact 40-character SHA")
    gate = files.pop("__candidate_gate__")
    candidate_gate = json.loads(gate.read_text(encoding="utf-8"))
    if candidate_gate.get("passed") is not True or candidate_gate.get("release_tag") != release_tag:
        _fail("was not created after the passing candidate gate")
    metadata = _metadata(str(release.get("body") or ""))
    artifacts: dict[str, dict[str, str]] = {}
    required = {"Omi.zip", "omi.dmg"}
    if set(files) != required:
        _fail("does not contain the exact qualified Omi.zip and omi.dmg")
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
    return {
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
    artifacts = evidence.get("artifacts")
    if not isinstance(artifacts, dict):
        _fail("does not contain artifacts")
    metadata = _metadata(str(release.get("body") or ""))
    expected_names = set(digests)
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
    parser.add_argument("--asset", action="append", default=[])
    args = parser.parse_args()
    release = json.loads(Path(args.release_json).read_text(encoding="utf-8"))
    files: dict[str, Path] = {}
    for raw in args.asset:
        name, sep, path = raw.partition("=")
        if not sep or name not in ARTIFACTS:
            raise SystemExit("--asset must be NAME=PATH for a required release artifact")
        files[name] = Path(path)
    if args.command == "build":
        if not args.candidate_gate:
            raise SystemExit("build requires --candidate-gate")
        files["__candidate_gate__"] = Path(args.candidate_gate)
        result = build_evidence(release, args.release_tag, args.source_sha, files)
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
