"""Read-only, fail-closed evidence builder for an emergency Beta candidate."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from desktop_release_manifest import validate_manifest
from utils.github_releases import extract_key_value_pairs
from utils.qualified_beta_promotion import (
    GitHubQualifiedBetaReader,
    QualifiedBetaAdmissionError,
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


def _smoke_evidence(payload: bytes, *, tag: str, source_sha: str) -> None:
    try:
        smoke = json.loads(payload)
    except (TypeError, json.JSONDecodeError):
        candidate_fail("emergency target signed-artifact smoke is invalid")
    if not isinstance(smoke, dict):
        candidate_fail("emergency target signed-artifact smoke is invalid")
    required = {"ok": True, "release_tag": tag, "expected_channel": "beta", "bundle_id": "com.omi.computer-macos"}
    if any(smoke.get(key) != value for key, value in required.items()):
        candidate_fail("emergency target signed-artifact smoke does not bind the target")
    checks = smoke.get("checks")
    if not isinstance(checks, list) or "Signed desktop artifact smoke completed" not in checks:
        candidate_fail("emergency target signed-artifact smoke is incomplete")
    # The source SHA is independently bound by the signed immutable tag; no
    # caller-provided artifact URL or byte stream ever enters this path.
    if len(source_sha) != 40:
        candidate_fail("emergency target source identity is invalid")


async def build_emergency_beta_manifest(
    tag: str, *, reader: Any | None = None, now: Any | None = None
) -> dict[str, Any]:
    """Derive a higher emergency candidate while preserving false normal T2 truth."""
    match = TAG_RE.fullmatch(tag)
    if match is None:
        candidate_fail("emergency target tag identity is invalid")
    build_number = int(match.group("build"))
    current_time = candidate_current_time(now)
    source = reader or GitHubQualifiedBetaReader()
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
    _smoke_evidence(downloaded["desktop-smoke-result.json"], tag=tag, source_sha=actual_source)
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
        raise QualifiedBetaAdmissionError("emergency target manifest is invalid") from exc
