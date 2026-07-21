"""Server-owned admission of one qualified immutable macOS Beta candidate."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
import re
from typing import Any

from desktop_qualification_admission import validate_qualification_run
from desktop_qualification_evidence import verify_evidence
from desktop_release_manifest import validate_manifest
from utils.github_releases import extract_key_value_pairs
from utils.http_client import get_web_fetch_client

REPOSITORY = "BasedHardware/omi"
TAG_RE = re.compile(r"^v(?P<version>[0-9]+\.[0-9]+(?:\.[0-9]+)?)\+(?P<build>[1-9][0-9]*)-macos$")
SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
RETIRED_ASSET_NAMES = frozenset({"Omi.Beta.zip", "omi-beta.dmg", "Omi Beta.zip", "Omi Beta.dmg"})


class QualifiedBetaAdmissionError(ValueError):
    """A candidate failed server-side Beta admission without mutable effects."""


def _fail(message: str) -> None:
    raise QualifiedBetaAdmissionError(message)


def _timestamp(value: object) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        _fail("candidate freshness is missing")
    try:
        return datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError:
        _fail("candidate freshness is invalid")


def _max_age_seconds() -> int:
    raw = os.getenv("QUALIFIED_BETA_MAX_AGE_SECONDS", "604800")
    try:
        value = int(raw)
    except ValueError:
        _fail("candidate freshness policy is unavailable")
    if value <= 0:
        _fail("candidate freshness policy is unavailable")
    return value


def _asset(release: dict[str, Any], name: str) -> dict[str, Any]:
    matches = [asset for asset in release.get("assets", []) if asset.get("name") == name]
    if len(matches) != 1:
        _fail("candidate is missing a canonical asset")
    return matches[0]


def _asset_url(asset: dict[str, Any], tag: str, name: str) -> str:
    url = asset.get("browser_download_url") or asset.get("url")
    expected = f"https://github.com/{REPOSITORY}/releases/download/{tag}/{name}"
    if url != expected:
        _fail("candidate asset identity does not match its immutable release")
    return url


def _asset_digest(asset: dict[str, Any]) -> str:
    value = asset.get("digest")
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        _fail("candidate asset is missing its GitHub SHA-256 digest")
    return value


def _release_for_contract(release: dict[str, Any]) -> dict[str, Any]:
    """Adapt GitHub REST names to the existing canonical evidence owner."""
    return {
        "tagName": release.get("tag_name"),
        "body": release.get("body"),
        "isDraft": release.get("draft"),
        "isPrerelease": release.get("prerelease"),
        "publishedAt": release.get("published_at"),
        "assets": [
            {
                "name": asset.get("name"),
                "url": asset.get("browser_download_url") or asset.get("url"),
                "digest": asset.get("digest"),
            }
            for asset in release.get("assets", [])
        ],
    }


class GitHubQualifiedBetaReader:
    """Read-only public GitHub view used by the backend admission transaction."""

    async def _api(self, path: str) -> dict[str, Any]:
        response = await get_web_fetch_client().get(
            f"https://api.github.com/repos/{REPOSITORY}/{path}",
            headers={"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"},
        )
        if response.status_code != 200:
            _fail("candidate GitHub evidence is unavailable")
        value: object = response.json()
        if not isinstance(value, dict):
            _fail("candidate GitHub evidence is invalid")
        return value

    async def release(self, tag: str) -> dict[str, Any]:
        return await self._api(f"releases/tags/{tag}")

    async def tag_sha(self, tag: str) -> str:
        ref = await self._api(f"git/ref/tags/{tag}")
        obj = ref.get("object")
        if not isinstance(obj, dict) or obj.get("type") not in {"commit", "tag"} or not isinstance(obj.get("sha"), str):
            _fail("candidate tag is invalid")
        if obj["type"] == "commit":
            return obj["sha"]
        tag_object = await self._api(f"git/tags/{obj['sha']}")
        nested = tag_object.get("object")
        if not isinstance(nested, dict) or nested.get("type") != "commit" or not isinstance(nested.get("sha"), str):
            _fail("candidate tag is invalid")
        return nested["sha"]

    async def is_merged_source(self, source_sha: str) -> bool:
        comparison = await self._api(f"compare/{source_sha}...main")
        return comparison.get("status") in {"behind", "identical"}

    async def run(self, run_id: int) -> dict[str, Any]:
        return await self._api(f"actions/runs/{run_id}")

    async def download(self, url: str) -> bytes:
        response = await get_web_fetch_client().get(url)
        if response.status_code != 200:
            _fail("candidate GitHub asset is unavailable")
        return response.content


async def build_qualified_beta_manifest(
    tag: str, *, reader: Any | None = None, now: datetime | None = None
) -> dict[str, Any]:
    """Derive and verify a canonical manifest from GitHub, never caller claims."""
    match = TAG_RE.fullmatch(tag)
    if not match:
        _fail("candidate tag is invalid")
    source = reader or GitHubQualifiedBetaReader()
    release = await source.release(tag)
    if release.get("tag_name") != tag or release.get("draft") or release.get("prerelease"):
        _fail("candidate release is not an immutable published release")
    published_at = release.get("published_at")
    published = _timestamp(published_at)
    if (now or datetime.now(timezone.utc)) - published > timedelta(seconds=_max_age_seconds()):
        _fail("candidate release is stale")

    names = {asset.get("name") for asset in release.get("assets", [])}
    if names & RETIRED_ASSET_NAMES or any(isinstance(name, str) and "omi beta" in name.lower() for name in names):
        _fail("candidate contains a retired desktop identity")
    zip_asset, dmg_asset = _asset(release, "Omi.zip"), _asset(release, "omi.dmg")
    evidence_name = f"qualification-evidence-{tag}.json"
    evidence_asset = _asset(release, evidence_name)
    zip_url, dmg_url, evidence_url = (
        _asset_url(zip_asset, tag, "Omi.zip"),
        _asset_url(dmg_asset, tag, "omi.dmg"),
        _asset_url(evidence_asset, tag, evidence_name),
    )
    expected_digests = {
        "Omi.zip": _asset_digest(zip_asset),
        "omi.dmg": _asset_digest(dmg_asset),
        evidence_name: _asset_digest(evidence_asset),
    }
    source_sha = await source.tag_sha(tag)
    if not re.fullmatch(r"[0-9a-f]{40}", source_sha) or not await source.is_merged_source(source_sha):
        _fail("candidate source is not a trusted merged source")
    downloaded = {
        "Omi.zip": await source.download(zip_url),
        "omi.dmg": await source.download(dmg_url),
        evidence_name: await source.download(evidence_url),
    }
    actual_digests = {name: "sha256:" + hashlib.sha256(content).hexdigest() for name, content in downloaded.items()}
    if actual_digests != expected_digests:
        _fail("candidate asset digest does not match GitHub release metadata")
    try:
        evidence = json.loads(downloaded[evidence_name])
    except (TypeError, json.JSONDecodeError):
        _fail("candidate qualification evidence is invalid")
    if not isinstance(evidence, dict):
        _fail("candidate qualification evidence is invalid")
    run_id = evidence.get("qualification_run_id")
    if not isinstance(run_id, int) or run_id <= 0:
        _fail("candidate qualification evidence has no trusted run identity")
    run = await source.run(run_id)
    try:
        validate_qualification_run(run, REPOSITORY, tag, source_sha)
    except ValueError as exc:
        raise QualifiedBetaAdmissionError("candidate qualification run is not trusted") from exc
    run_time = _timestamp(run.get("updated_at"))
    if (now or datetime.now(timezone.utc)) - run_time > timedelta(seconds=_max_age_seconds()):
        _fail("candidate qualification is stale")
    contract_release = _release_for_contract(release)
    try:
        verify_evidence(
            evidence,
            contract_release,
            tag,
            source_sha,
            {
                "Omi.zip": actual_digests["Omi.zip"].removeprefix("sha256:"),
                "omi.dmg": actual_digests["omi.dmg"].removeprefix("sha256:"),
            },
        )
    except ValueError as exc:
        raise QualifiedBetaAdmissionError("candidate qualification evidence does not bind this release") from exc
    metadata = extract_key_value_pairs(str(release.get("body") or ""))
    signature = metadata.get("edSignature", "").strip()
    if not signature:
        _fail("candidate release has no Sparkle signature")
    manifest = {
        "schema_version": 1,
        "release_id": tag,
        "platform": "macos",
        "version": match.group("version"),
        "build_number": int(match.group("build")),
        "app_source_sha": source_sha,
        "zip_url": zip_url,
        "zip_sha256": actual_digests["Omi.zip"],
        "dmg_url": dmg_url,
        "dmg_sha256": actual_digests["omi.dmg"],
        "ed_signature": signature,
        "qualification_evidence_asset": evidence_name,
        "qualification_evidence_sha256": actual_digests[evidence_name],
        "qualification_tier": "T2",
        "qualification_passed": True,
        "backend_mode": "app_only",
        "compatibility_contract": {
            "schema_version": 1,
            "app_release_id": tag,
            "app_version": match.group("version"),
            "app_build_number": int(match.group("build")),
            "backend_mode": "app_only",
            "environment_contract_version": "desktop-backend-env-v1",
        },
        "environment_contract_version": "desktop-backend-env-v1",
        "created_at": published_at,
        "published_at": published_at,
        "changelog": metadata.get("changelog", []),
        "mandatory": str(metadata.get("mandatory", "false")).lower() in {"true", "1", "yes"},
    }
    try:
        return validate_manifest(manifest)
    except ValueError as exc:
        raise QualifiedBetaAdmissionError("candidate manifest does not satisfy the canonical contract") from exc
