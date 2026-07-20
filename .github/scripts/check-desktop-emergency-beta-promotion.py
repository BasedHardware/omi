#!/usr/bin/env python3
"""Fail-closed verifier for the beta-only emergency forward-promotion lane."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

from desktop_release_metadata import fail, parse_metadata

TAG_RE = re.compile(r"^v\d+\.\d+(?:\.\d+)?\+\d+-macos$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
OPERATOR_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")
APPROVAL_RE = re.compile(
    r"^Emergency beta promotion approval:\s*(?P<tag>\S+)\s+(?P<sha>[0-9a-f]{40})\s+(?P<expires>\S+)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
REQUIRED_SMOKE_CHECKS = {
    "Launch + identity metadata is aligned",
    "Signed desktop artifact smoke completed",
    "Signed artifact Keychain write/read/delete canary passed",
}


def load_json(path: str) -> dict | list:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def https_url(value: str, field: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc:
        fail(f"{field} must be an https URL")
    return value


def sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def release_asset(release: dict, names: set[str]) -> dict:
    for asset in release.get("assets", []):
        if asset.get("name") in names:
            return asset
    fail(f"release is missing asset: {', '.join(sorted(names))}")


def smoke_artifact(smoke: dict, label: str) -> dict:
    for artifact in smoke.get("artifacts", []):
        if artifact.get("label") == label:
            return artifact
    fail(f"signed smoke evidence is missing {label!r}")


def release_digest(asset: dict) -> str:
    digest = str(asset.get("digest") or "").removeprefix("sha256:").lower()
    if not SHA256_RE.fullmatch(digest):
        fail(f"release asset {asset.get('name')!r} has no SHA-256 digest")
    return digest


def parse_expiry(value: str, *, now: datetime) -> datetime:
    try:
        expires_at = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        fail(f"expires_at must be ISO-8601: {exc}")
    if expires_at.tzinfo is None:
        fail("expires_at must include a timezone")
    expires_at = expires_at.astimezone(timezone.utc)
    if expires_at <= now or expires_at - now > timedelta(hours=4):
        fail("expires_at must be in the next four hours")
    return expires_at


def emergency_operation_id(release_tag: str, source_sha: str, incident_id: str) -> str:
    """Derive the durable operation identity shared by retries and reconciliation."""
    binding = f"macos-beta-emergency-forward-promotion:{release_tag}:{source_sha.lower()}:{incident_id.strip()}"
    return hashlib.sha256(binding.encode("utf-8")).hexdigest()


def approval_identities(comments: list[dict], tag: str, source_sha: str, expires_at: str) -> list[str]:
    approvers: list[str] = []
    for comment in comments:
        match = APPROVAL_RE.search(str(comment.get("body") or ""))
        if not match:
            continue
        if (match.group("tag"), match.group("sha").lower(), match.group("expires")) != (tag, source_sha, expires_at):
            continue
        if str(comment.get("author_association") or "").upper() not in {"MEMBER", "OWNER"}:
            continue
        login = str((comment.get("user") or {}).get("login") or "").strip()
        if login and login.lower() not in {item.lower() for item in approvers}:
            approvers.append(login)
    if len(approvers) != 2:
        fail("incident requires exactly two distinct MEMBER/OWNER approval comments bound to this candidate")
    return approvers


def incident_is_open(incident: dict, incident_id: str) -> bool:
    """Accept GitHub's documented state spelling regardless of casing."""
    return (
        str(incident.get("state") or "").strip().lower() == "open"
        and str(incident.get("number")) == str(incident_id)
    )


def validate(args: argparse.Namespace) -> dict:
    if args.confirm != "emergency-promote-beta":
        fail("confirm must equal emergency-promote-beta")
    if not TAG_RE.fullmatch(args.release_tag):
        fail("release_tag must be an exact macOS release tag")
    if not re.fullmatch(r"[0-9a-f]{40}", args.source_sha, re.IGNORECASE):
        fail("source_sha must be a 40-character SHA")
    if not args.reason.strip():
        fail("an emergency rationale is required")
    operator = args.operator.strip().lstrip("@")
    if not OPERATOR_RE.fullmatch(operator):
        fail("operator must be the GitHub login that started the protected workflow")
    now = datetime.now(timezone.utc) if args.now is None else datetime.fromisoformat(args.now.replace("Z", "+00:00"))
    expiry = parse_expiry(args.expires_at, now=now)
    incident_id = args.incident_id.strip()
    if not incident_id:
        fail("incident_id is required")
    behavioral_url = https_url(args.behavioral_evidence_url, "behavioral_evidence_url")
    behavioral_digest = sha256_file(args.behavioral_evidence_file)

    release = load_json(args.release_json)
    smoke = load_json(args.smoke_json)
    check_runs = load_json(args.source_check_json)
    incident = load_json(args.incident_json)
    comments = load_json(args.incident_comments_json)
    if not isinstance(release, dict) or not isinstance(smoke, dict) or not isinstance(check_runs, dict):
        fail("release, smoke, and source-check inputs must be JSON objects")
    if not isinstance(incident, dict) or not isinstance(comments, list):
        fail("incident inputs have an invalid shape")
    if release.get("tagName") != args.release_tag or release.get("isDraft") or release.get("isPrerelease") or not release.get("publishedAt"):
        fail("release must be an exact published non-prerelease GitHub release")
    metadata = parse_metadata(str(release.get("body") or ""))
    if metadata.get("channel") != "candidate" or metadata.get("isLive", "").lower() not in {"false", "0", "no"}:
        fail("emergency promotion accepts only a non-live candidate release")
    if metadata.get("emergencyPromotion", "").lower() in {"true", "1", "yes"}:
        fail("candidate already carries emergency promotion metadata")
    if smoke.get("ok") is not True or smoke.get("release_tag") != args.release_tag:
        fail("signed smoke evidence does not match the requested release")
    if not REQUIRED_SMOKE_CHECKS.issubset(set(smoke.get("checks") or [])):
        fail("signed smoke evidence is missing required checks")
    zip_asset = release_asset(release, {"Omi.zip"})
    dmg_asset = release_asset(release, {"Omi.dmg", "omi.dmg"})
    zip_digest, dmg_digest = release_digest(zip_asset), release_digest(dmg_asset)
    if sha256_file(args.zip_file) != zip_digest or sha256_file(args.dmg_file) != dmg_digest:
        fail("recomputed ZIP/DMG digest does not match the published asset")
    if smoke_artifact(smoke, "sparkle_zip").get("sha256") != zip_digest:
        fail("signed smoke ZIP digest does not match the published asset")
    if smoke_artifact(smoke, "dmg").get("sha256") != dmg_digest:
        fail("signed smoke DMG digest does not match the published asset")
    source_gate = next(
        (
            item
            for item in check_runs.get("check_runs", [])
            if item.get("name") == "Desktop Swift Build & Tests"
            and item.get("status") == "completed"
            and item.get("conclusion") == "success"
        ),
        None,
    )
    if source_gate is None:
        fail("normal Desktop Swift Build & Tests source gate did not pass for the immutable source SHA")
    if not incident_is_open(incident, incident_id):
        fail("incident must exist and remain open")
    approvers = approval_identities(comments, args.release_tag, args.source_sha.lower(), args.expires_at)
    signed_smoke_asset = release_asset(release, {"desktop-smoke-result.json"})
    signed_smoke_url = https_url(str(signed_smoke_asset.get("url") or ""), "signed smoke URL")
    signed_smoke_digest = release_digest(signed_smoke_asset)
    source_gate_url = https_url(str(source_gate.get("html_url") or ""), "source gate URL")
    return {
        "emergencyPromotion": True,
        "release_tag": args.release_tag,
        "source_sha": args.source_sha.lower(),
        "incident_id": incident_id,
        "reason": args.reason.strip(),
        "operator": operator,
        "expires_at": expiry.isoformat().replace("+00:00", "Z"),
        "operation_id": emergency_operation_id(args.release_tag, args.source_sha, incident_id),
        "approvers": approvers,
        "evidence": {
            "signed_smoke_url": signed_smoke_url,
            "signed_smoke_sha256": signed_smoke_digest,
            "behavioral_url": behavioral_url,
            "behavioral_sha256": behavioral_digest,
            "source_gate_url": source_gate_url,
            "zip_sha256": zip_digest,
            "dmg_sha256": dmg_digest,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release-json", required=True)
    parser.add_argument("--smoke-json", required=True)
    parser.add_argument("--source-check-json", required=True)
    parser.add_argument("--incident-json", required=True)
    parser.add_argument("--incident-comments-json", required=True)
    parser.add_argument("--zip-file", required=True)
    parser.add_argument("--dmg-file", required=True)
    parser.add_argument("--behavioral-evidence-file", required=True)
    parser.add_argument("--behavioral-evidence-url", required=True)
    parser.add_argument("--release-tag", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--incident-id", required=True)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--operator", required=True)
    parser.add_argument("--expires-at", required=True)
    parser.add_argument("--confirm", required=True)
    parser.add_argument("--now")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = validate(args)
    Path(args.output).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"emergency beta promotion evidence verified: {args.release_tag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
