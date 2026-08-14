"""Read-only, fail-closed evidence builder for an emergency Beta candidate."""

from __future__ import annotations

import asyncio
import hashlib
import json
from typing import Any

from desktop_release_manifest import validate_manifest
from utils.github_releases import extract_key_value_pairs
from utils.beta_candidate_evidence import (
    GitHubBetaCandidateReader,
    BetaCandidateAdmissionError,
    candidate_asset,
    candidate_asset_digest,
    candidate_asset_url,
    candidate_current_time,
    candidate_fail,
    candidate_github_object,
    candidate_is_fresh,
    candidate_read_github,
    candidate_release_assets,
    candidate_timestamp,
    TAG_RE,
)

EXPECTED_TEAM_ID = "9536L8KLMP"
REQUIRED_STRUCTURAL_SMOKE_CHECKS = frozenset(
    {
        "Launch + identity metadata is aligned",
        "Auth persistence prerequisites: signing identity and Keychain-compatible entitlements are sane",
        "Backend routing config matches the declared external backend",
        "Sparkle/update metadata and authoritative ZIP artifacts are present",
        "Native helper/runtime bundle integrity passed",
        "Local storage/database package surface is present",
        "Signed desktop artifact smoke completed",
    }
)
REQUIRED_BETA_BEHAVIORAL_SMOKE_CHECKS = frozenset(
    {
        "Signed app launches and remains alive",
        "Signed artifact Keychain write/read/delete canary passed",
        "Signed app relaunched for UserNotifications callback canary",
        "UserNotifications settings callback completion canary passed",
    }
)


def _smoke_evidence(
    payload: bytes,
    *,
    tag: str,
    source_sha: str,
    bundle_id: str,
    version: str,
    build: str,
    require_behavioral_checks: bool = False,
    expected_artifacts: dict[str, str] | None = None,
    label: str = "emergency target",
) -> None:
    try:
        smoke = json.loads(payload)
    except (TypeError, json.JSONDecodeError):
        candidate_fail(f"{label} signed-artifact smoke is invalid")
    if not isinstance(smoke, dict):
        candidate_fail(f"{label} signed-artifact smoke is invalid")
    required = {
        "ok": True,
        "release_tag": tag,
        "expected_channel": "beta",
        "bundle_id": bundle_id,
        "version": version,
        "build": build,
        "team_id": EXPECTED_TEAM_ID,
    }
    if any(smoke.get(key) != value for key, value in required.items()):
        candidate_fail(f"{label} signed-artifact smoke does not bind the target")
    checks = smoke.get("checks")
    if not isinstance(checks, list) or any(not isinstance(check, str) for check in checks):
        candidate_fail(f"{label} signed-artifact smoke is incomplete")
    required_checks = set(REQUIRED_STRUCTURAL_SMOKE_CHECKS)
    if require_behavioral_checks:
        required_checks.update(REQUIRED_BETA_BEHAVIORAL_SMOKE_CHECKS)
    if not required_checks.issubset(checks):
        candidate_fail(f"{label} signed-artifact smoke is incomplete")
    if smoke.get("source_sha") != source_sha:
        candidate_fail(f"{label} source identity is invalid")
    if require_behavioral_checks:
        callback = smoke.get("notification_callback_canary")
        expected_callback = {
            "schema": 1,
            "event": "user-notifications-settings-callback-completed",
            "bundle_id": bundle_id,
            "main_actor": True,
            "validated": True,
        }
        if not isinstance(callback, dict) or any(
            callback.get(key) != value for key, value in expected_callback.items()
        ):
            candidate_fail(f"{label} UserNotifications callback canary is invalid")
        if not isinstance(callback.get("authorization_status"), int):
            candidate_fail(f"{label} UserNotifications callback canary is incomplete")
    if expected_artifacts is not None:
        artifacts = smoke.get("artifacts")
        if not isinstance(artifacts, list):
            candidate_fail(f"{label} smoke has no artifact digest set")
        observed: dict[str, str] = {}
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                candidate_fail(f"{label} smoke artifact digest set is invalid")
            art_label, digest = artifact.get("label"), artifact.get("sha256")
            if art_label in expected_artifacts and isinstance(digest, str):
                observed[art_label] = f"sha256:{digest}"
        if observed != expected_artifacts:
            candidate_fail(f"{label} smoke does not bind the published artifacts")


async def build_signed_beta_manifest(tag: str, *, reader: Any | None = None, now: Any | None = None) -> dict[str, Any]:
    """Derive the normal Beta manifest directly from Codemagic signed-smoke evidence."""
    match = TAG_RE.fullmatch(tag)
    if match is None:
        candidate_fail("candidate tag identity is invalid")
    build_number = int(match.group("build"))
    current_time = candidate_current_time(now)
    source = reader or GitHubBetaCandidateReader()
    release = candidate_github_object(
        await candidate_read_github(source, "release", tag), "candidate release is invalid"
    )
    if release.get("tag_name") != tag or release.get("draft") is not False or release.get("prerelease") is not False:
        candidate_fail("candidate is not an immutable published release")
    metadata = extract_key_value_pairs(str(release.get("body") or ""))
    if metadata.get("channel") != "candidate" or str(metadata.get("isLive", "")).lower() != "false":
        candidate_fail("candidate release metadata is not non-live candidate state")
    published_at = release.get("published_at")
    if not candidate_is_fresh(candidate_timestamp(published_at), current_time):
        candidate_fail("candidate release is stale")
    actual_source = await candidate_read_github(source, "tag_sha", tag)
    if (
        not isinstance(actual_source, str)
        or await candidate_read_github(source, "is_merged_source", actual_source) is not True
    ):
        candidate_fail("candidate source identity is not merged main")

    assets = candidate_release_assets(release.get("assets"))
    names = (
        "Omi.zip",
        "omi.dmg",
        "Omi.Beta.zip",
        "omi-beta.dmg",
        "desktop-smoke-result.json",
        "desktop-smoke-result-beta.json",
    )
    selected = {name: candidate_asset(assets, name) for name in names}
    urls = {name: candidate_asset_url(asset, tag, name) for name, asset in selected.items()}
    digests = {name: candidate_asset_digest(asset) for name, asset in selected.items()}
    stable_smoke_bytes, beta_smoke_bytes = await asyncio.gather(
        candidate_read_github(source, "download", urls["desktop-smoke-result.json"]),
        candidate_read_github(source, "download", urls["desktop-smoke-result-beta.json"]),
    )
    if "sha256:" + hashlib.sha256(stable_smoke_bytes).hexdigest() != digests["desktop-smoke-result.json"]:
        candidate_fail("candidate stable signed-smoke digest does not match its immutable release asset")
    if "sha256:" + hashlib.sha256(beta_smoke_bytes).hexdigest() != digests["desktop-smoke-result-beta.json"]:
        candidate_fail("candidate signed-smoke digest does not match its immutable release asset")
    _smoke_evidence(
        stable_smoke_bytes,
        tag=tag,
        source_sha=actual_source,
        bundle_id="com.omi.computer-macos",
        version=match.group("version"),
        build=match.group("build"),
        label="candidate stable identity",
        expected_artifacts={
            "sparkle_zip": digests["Omi.zip"],
            "dmg": digests["omi.dmg"],
        },
    )
    _smoke_evidence(
        beta_smoke_bytes,
        tag=tag,
        source_sha=actual_source,
        bundle_id="com.omi.computer-macos.beta",
        version=match.group("version"),
        build=match.group("build"),
        require_behavioral_checks=True,
        label="candidate",
        expected_artifacts={
            "sparkle_zip": digests["Omi.Beta.zip"],
            "dmg": digests["omi-beta.dmg"],
        },
    )

    signature = metadata.get("edSignature", "").strip()
    if not signature or not metadata.get("betaEdSignature", "").strip():
        candidate_fail("candidate has no complete Sparkle signatures")
    try:
        return validate_manifest(
            {
                "schema_version": 1,
                "release_id": tag,
                "platform": "macos",
                "version": match.group("version"),
                "build_number": build_number,
                "app_source_sha": actual_source,
                "zip_url": urls["Omi.zip"],
                "zip_sha256": digests["Omi.zip"],
                "dmg_url": urls["omi.dmg"],
                "dmg_sha256": digests["omi.dmg"],
                "ed_signature": signature,
                # Manifest v1 retains the historical field names. False is
                # deliberate: normal Beta now trusts Codemagic signed smoke,
                # not the retired T2 qualification lane.
                "qualification_evidence_asset": "desktop-smoke-result-beta.json",
                "qualification_evidence_sha256": digests["desktop-smoke-result-beta.json"],
                "qualification_tier": "signed-smoke",
                "qualification_passed": False,
                "backend_mode": "app_only",
                "compatibility_contract": {
                    "schema_version": 1,
                    "app_release_id": tag,
                    "app_version": match.group("version"),
                    "app_build_number": build_number,
                    "backend_mode": "app_only",
                    "environment_contract_version": "desktop-backend-env-v1",
                },
                "environment_contract_version": "desktop-backend-env-v1",
                "created_at": published_at,
                "published_at": published_at,
                "changelog": metadata.get("changelog", []),
                "mandatory": str(metadata.get("mandatory", "false")).lower() in {"true", "1", "yes"},
            }
        )
    except ValueError as exc:
        raise BetaCandidateAdmissionError("candidate manifest is invalid") from exc


async def build_emergency_beta_manifest(
    tag: str, *, reader: Any | None = None, now: Any | None = None
) -> dict[str, Any]:
    """Derive a higher emergency candidate while preserving false normal T2 truth."""
    match = TAG_RE.fullmatch(tag)
    if match is None:
        candidate_fail("emergency target tag identity is invalid")
    build_number = int(match.group("build"))
    current_time = candidate_current_time(now)
    source = reader or GitHubBetaCandidateReader()
    release = candidate_github_object(
        await candidate_read_github(source, "release", tag), "emergency target release is invalid"
    )
    if release.get("tag_name") != tag or release.get("draft") is not False or release.get("prerelease") is not False:
        candidate_fail("emergency target is not an immutable published release")
    published_at = release.get("published_at")
    if not candidate_is_fresh(candidate_timestamp(published_at), current_time):
        candidate_fail("emergency target release is stale")
    actual_source = await candidate_read_github(source, "tag_sha", tag)
    if (
        not isinstance(actual_source, str)
        or await candidate_read_github(source, "is_merged_source", actual_source) is not True
    ):
        candidate_fail("emergency target source identity is not merged main")
    assets = candidate_release_assets(release.get("assets"))
    zip_asset, dmg_asset, smoke_asset = (
        candidate_asset(assets, "Omi.zip"),
        candidate_asset(assets, "omi.dmg"),
        candidate_asset(assets, "desktop-smoke-result.json"),
    )
    urls = {
        "Omi.zip": candidate_asset_url(zip_asset, tag, "Omi.zip"),
        "omi.dmg": candidate_asset_url(dmg_asset, tag, "omi.dmg"),
        "desktop-smoke-result.json": candidate_asset_url(smoke_asset, tag, "desktop-smoke-result.json"),
    }
    expected = {
        name: candidate_asset_digest(asset)
        for name, asset in (("Omi.zip", zip_asset), ("omi.dmg", dmg_asset), ("desktop-smoke-result.json", smoke_asset))
    }
    downloaded = {name: await candidate_read_github(source, "download", url) for name, url in urls.items()}
    actual = {name: "sha256:" + hashlib.sha256(content).hexdigest() for name, content in downloaded.items()}
    if actual != expected:
        candidate_fail("emergency target GitHub digests do not match immutable assets")
    _smoke_evidence(
        downloaded["desktop-smoke-result.json"],
        tag=tag,
        source_sha=actual_source,
        bundle_id="com.omi.computer-macos",
        version=match.group("version"),
        build=match.group("build"),
    )
    metadata = extract_key_value_pairs(str(release.get("body") or ""))
    signature = metadata.get("edSignature", "").strip()
    if not signature:
        candidate_fail("emergency target has no Sparkle signature")
    try:
        return validate_manifest(
            {
                "schema_version": 1,
                "release_id": tag,
                "platform": "macos",
                "version": match.group("version"),
                "build_number": build_number,
                "app_source_sha": actual_source,
                "zip_url": urls["Omi.zip"],
                "zip_sha256": actual["Omi.zip"],
                "dmg_url": urls["omi.dmg"],
                "dmg_sha256": actual["omi.dmg"],
                "ed_signature": signature,
                "qualification_evidence_asset": "desktop-smoke-result.json",
                "qualification_evidence_sha256": actual["desktop-smoke-result.json"],
                "qualification_tier": "emergency",
                "qualification_passed": False,
                "backend_mode": "app_only",
                "compatibility_contract": {
                    "schema_version": 1,
                    "app_release_id": tag,
                    "app_version": match.group("version"),
                    "app_build_number": build_number,
                    "backend_mode": "app_only",
                    "environment_contract_version": "desktop-backend-env-v1",
                },
                "environment_contract_version": "desktop-backend-env-v1",
                "created_at": published_at,
                "published_at": published_at,
                "changelog": [],
                "mandatory": False,
            }
        )
    except ValueError as exc:
        raise BetaCandidateAdmissionError("emergency target manifest is invalid") from exc
