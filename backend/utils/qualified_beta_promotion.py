"""Server-owned admission of one qualified immutable macOS Beta candidate."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
import os
import re
from collections.abc import Awaitable
from typing import Any, NoReturn, TypeGuard
from urllib.parse import urlsplit
import zipfile
import zlib

from desktop_qualification_admission import validate_qualification_run
from desktop_qualification_evidence import verify_evidence
from desktop_release_manifest import validate_manifest
from utils.github_releases import extract_key_value_pairs
from utils.http_client import get_web_fetch_client

REPOSITORY = "BasedHardware/omi"
TAG_RE = re.compile(r"^v(?P<version>[0-9]+\.[0-9]+(?:\.[0-9]+)?)\+(?P<build>[1-9][0-9]*)-macos$")
SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
UTC_RFC3339_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?Z$")
# INV-BETA-1: the side-by-side Omi Beta app ships these two sanctioned assets on
# every macOS candidate. Any OTHER "omi beta"-ish asset name is still a retired
# identity and rejected. Kept in canonical form used by codemagic/updates.py.
SANCTIONED_BETA_ASSET_NAMES = ("Omi.Beta.zip", "omi-beta.dmg")
RETIRED_ASSET_NAMES = frozenset({"Omi Beta.zip", "Omi Beta.dmg"})
QUALIFICATION_WORKFLOW = "desktop_qualify_beta.yml"
QUALIFICATION_ARTIFACT_PREFIX = "desktop-qualification-evidence-"
QUALIFICATION_EVIDENCE_FILE = "qualification-evidence.json"
MAX_QUALIFICATION_ARTIFACT_BYTES = 1_048_576
MAX_QUALIFICATION_EVIDENCE_BYTES = 262_144
_EXACT_DATETIME_TYPE = datetime


class QualifiedBetaAdmissionError(ValueError):
    """A candidate failed server-side Beta admission without mutable effects."""


def _fail(message: str) -> NoReturn:
    raise QualifiedBetaAdmissionError(message)


def _timestamp(value: object) -> datetime:
    """Parse the sole accepted GitHub freshness timestamp representation."""
    if not isinstance(value, str) or not UTC_RFC3339_RE.fullmatch(value):
        _fail("candidate freshness is missing")
    try:
        parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except (OverflowError, ValueError):
        _fail("candidate freshness is invalid")
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        _fail("candidate freshness is invalid")
    return parsed.astimezone(timezone.utc)


def _current_time(value: object) -> datetime:
    """Use an aware UTC clock value so admission never subtracts naive datetimes."""
    if value is None:
        try:
            value = datetime.now(timezone.utc)
        except Exception:
            _fail("candidate admission clock is invalid")
    if type(value) is not _EXACT_DATETIME_TYPE:
        _fail("candidate admission clock is invalid")
    try:
        if value.tzinfo is None or value.utcoffset() is None:
            _fail("candidate admission clock is invalid")
        normalized = value.astimezone(timezone.utc)
    except Exception:
        _fail("candidate admission clock is invalid")
    if type(normalized) is not _EXACT_DATETIME_TYPE or normalized.tzinfo is not timezone.utc:
        _fail("candidate admission clock is invalid")
    return normalized


def _is_fresh(timestamp: datetime, now: datetime) -> bool:
    """Require every admission freshness timestamp to be present, current, and bounded."""
    try:
        age = now - timestamp
        maximum_age = timedelta(seconds=_max_age_seconds())
    except (OverflowError, TypeError):
        _fail("candidate freshness is invalid")
    return timedelta(0) <= age <= maximum_age


def _max_age_seconds() -> int:
    raw = os.getenv("QUALIFIED_BETA_MAX_AGE_SECONDS", "604800")
    try:
        value = int(raw)
    except ValueError:
        _fail("candidate freshness policy is unavailable")
    if value <= 0:
        _fail("candidate freshness policy is unavailable")
    return value


def _asset(assets: list[dict[str, Any]], name: str) -> dict[str, Any]:
    matches = [asset for asset in assets if asset.get("name") == name]
    if len(matches) != 1:
        _fail("candidate is missing a canonical asset")
    return matches[0]


def _github_object(value: object, message: str) -> dict[str, Any]:
    """Validate an untrusted GitHub JSON object before reading its fields."""
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        _fail(message)
    result: dict[str, Any] = {}
    for key, item in value.items():
        result[key] = item
    return result


def _github_objects(value: object, message: str) -> list[dict[str, Any]]:
    """Validate an untrusted GitHub JSON array of objects before consuming it."""
    if not isinstance(value, list):
        _fail(message)
    return [_github_object(item, message) for item in value]


def _is_exact_integer(value: object) -> TypeGuard[int]:
    return isinstance(value, int) and not isinstance(value, bool)


def _nonempty_string(value: object, message: str) -> str:
    if not isinstance(value, str) or not value:
        _fail(message)
    return value


def _release_assets(value: object) -> list[dict[str, Any]]:
    """Validate collection structure without applying canonical asset rules to unrelated assets."""
    assets = _github_objects(value, "candidate GitHub release assets are invalid")
    for asset in assets:
        _nonempty_string(asset.get("name"), "candidate GitHub release assets are invalid")
        _nonempty_string(asset.get("browser_download_url"), "candidate GitHub release assets are invalid")
        digest = asset.get("digest")
        if digest is not None and not isinstance(digest, str):
            _fail("candidate GitHub release assets are invalid")
    return assets


def _validate_qualification_run_member(run: dict[str, Any]) -> None:
    """Reject malformed run members while permitting documented nullable unrelated fields."""
    if not _is_exact_integer(run.get("id")) or run["id"] <= 0:
        _fail("candidate qualification run has no trusted identity")
    for field in ("status", "conclusion", "event", "path", "head_sha"):
        _nonempty_string(run.get(field), "candidate qualification runs are invalid")
    for field in ("head_branch", "name"):
        value = run.get(field)
        if value is not None and not isinstance(value, str):
            _fail("candidate qualification runs are invalid")
    for field in ("repository", "head_repository"):
        repository = _github_object(run.get(field), "candidate qualification runs are invalid")
        _nonempty_string(repository.get("full_name"), "candidate qualification runs are invalid")
    _timestamp(run.get("updated_at"))


def _validate_selected_qualification_run(run: dict[str, Any]) -> tuple[int, datetime]:
    """Apply exact identity and freshness requirements only after a run is trusted."""
    run_id = _trusted_run_id(run)
    for field in ("status", "conclusion", "event", "path", "head_branch", "head_sha", "name"):
        _nonempty_string(run.get(field), "candidate qualification runs are invalid")
    for field in ("repository", "head_repository"):
        repository = _github_object(run.get(field), "candidate qualification runs are invalid")
        _nonempty_string(repository.get("full_name"), "candidate qualification runs are invalid")
    return run_id, _timestamp(run.get("updated_at"))


def _qualification_runs(value: object) -> list[dict[str, Any]]:
    """Validate every run before trust selection can skip an invalid member."""
    runs = _github_objects(value, "candidate qualification runs are invalid")
    for run in runs:
        _validate_qualification_run_member(run)
    return runs


def _qualification_artifacts(value: object) -> list[dict[str, Any]]:
    """Validate collection structure without applying canonical artifact rules to unrelated entries."""
    artifacts = _github_objects(value, "candidate qualification artifacts are invalid")
    for artifact in artifacts:
        artifact_id = artifact.get("id")
        if not _is_exact_integer(artifact_id) or artifact_id <= 0:
            _fail("candidate qualification artifact is invalid")
        _nonempty_string(artifact.get("name"), "candidate qualification artifacts are invalid")
        if type(artifact.get("expired")) is not bool:
            _fail("candidate qualification artifact is invalid")
        size = artifact.get("size_in_bytes")
        if not _is_exact_integer(size) or size < 0:
            _fail("candidate qualification artifact is invalid")
        _nonempty_string(artifact.get("archive_download_url"), "candidate qualification artifacts are invalid")
    return artifacts


def _asset_url(asset: dict[str, Any], tag: str, name: str) -> str:
    url = asset.get("browser_download_url")
    expected = f"https://github.com/{REPOSITORY}/releases/download/{tag}/{name}"
    encoded = f"https://github.com/{REPOSITORY}/releases/download/{tag.replace('+', '%2B')}/{name}"
    if not isinstance(url, str) or url not in {expected, encoded}:
        _fail("candidate asset identity does not match its immutable release")
    return url


def _asset_digest(asset: dict[str, Any]) -> str:
    value = asset.get("digest")
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        _fail("candidate asset is missing its GitHub SHA-256 digest")
    return value


def _trusted_run_id(run: dict[str, Any]) -> int:
    run_id = run.get("id")
    if not _is_exact_integer(run_id) or run_id <= 0:
        _fail("candidate qualification run has no trusted identity")
    return run_id


def _select_qualification_run(runs: object, tag: str, source_sha: str, now: datetime) -> tuple[dict[str, Any], int]:
    """Choose the newest fully trusted retry without caller-selected run state."""
    acceptable: list[tuple[datetime, int, dict[str, Any]]] = []
    for run in _qualification_runs(runs):
        try:
            validate_qualification_run(run, REPOSITORY, tag, source_sha)
        except QualifiedBetaAdmissionError:
            raise
        except ValueError:
            continue
        run_id, completed_at = _validate_selected_qualification_run(run)
        if not _is_fresh(completed_at, now):
            continue
        acceptable.append((completed_at, run_id, run))
    if not acceptable:
        _fail("candidate has no fresh trusted qualification run")
    _, run_id, run = max(acceptable, key=lambda item: (item[0], item[1]))
    return run, run_id


def _qualification_artifact_id(artifacts: object, tag: str) -> int:
    expected_name = f"{QUALIFICATION_ARTIFACT_PREFIX}{tag}"
    matches = [artifact for artifact in _qualification_artifacts(artifacts) if artifact.get("name") == expected_name]
    if len(matches) != 1:
        _fail("candidate qualification artifact is missing or ambiguous")
    artifact = matches[0]
    if artifact.get("expired") is not False:
        _fail("candidate qualification artifact is expired")
    artifact_id = artifact.get("id")
    size = artifact.get("size_in_bytes")
    if (
        not _is_exact_integer(artifact_id)
        or artifact_id <= 0
        or not _is_exact_integer(size)
        or not 0 < size <= MAX_QUALIFICATION_ARTIFACT_BYTES
    ):
        _fail("candidate qualification artifact is invalid")
    expected_url = f"https://api.github.com/repos/{REPOSITORY}/actions/artifacts/{artifact_id}/zip"
    if artifact.get("archive_download_url") != expected_url:
        _fail("candidate qualification artifacts are invalid")
    return artifact_id


def _evidence_from_artifact(payload: object) -> bytes:
    if not isinstance(payload, bytes) or not payload or len(payload) > MAX_QUALIFICATION_ARTIFACT_BYTES:
        _fail("candidate qualification artifact download is invalid")
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            infos = archive.infolist()
            if len(infos) != 1:
                _fail("candidate qualification artifact has unexpected contents")
            info = infos[0]
            if (
                info.filename != QUALIFICATION_EVIDENCE_FILE
                or info.is_dir()
                or info.flag_bits & 0x1
                or info.file_size < 1
                or info.file_size > MAX_QUALIFICATION_EVIDENCE_BYTES
                or info.compress_size < 0
                or info.compress_size > MAX_QUALIFICATION_ARTIFACT_BYTES
            ):
                _fail("candidate qualification artifact has unsafe contents")
            evidence = archive.read(info)
    except (EOFError, OSError, RuntimeError, zipfile.BadZipFile, zipfile.LargeZipFile, zlib.error) as exc:
        raise QualifiedBetaAdmissionError("candidate qualification artifact is not a safe ZIP") from exc
    if len(evidence) != info.file_size or len(evidence) > MAX_QUALIFICATION_EVIDENCE_BYTES:
        _fail("candidate qualification artifact evidence is invalid")
    return evidence


async def _read_github(source: Any, method: str, *args: Any) -> Any:
    """Keep every read dependency fail-closed before the admission transaction."""
    try:
        dependency = getattr(source, method)
        result = dependency(*args)
        if not isinstance(result, Awaitable):
            _fail("candidate GitHub read dependency is unavailable")
        return await result
    except QualifiedBetaAdmissionError:
        raise
    except Exception as exc:
        raise QualifiedBetaAdmissionError("candidate GitHub read dependency is unavailable") from exc


def _release_for_contract(release: dict[str, Any], assets: list[dict[str, Any]]) -> dict[str, Any]:
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
                "url": asset.get("browser_download_url"),
                "digest": asset.get("digest"),
            }
            for asset in assets
        ],
    }


class GitHubQualifiedBetaReader:
    """Read-only public GitHub view used by the backend admission transaction."""

    def _headers(self) -> dict[str, str]:
        token = os.getenv("GITHUB_TOKEN")
        if not token:
            _fail("candidate GitHub read authorization is unavailable")
        return {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    async def _api(self, path: str) -> dict[str, Any]:
        response = await get_web_fetch_client().get(
            f"https://api.github.com/repos/{REPOSITORY}/{path}",
            headers=self._headers(),
        )
        if response.status_code != 200:
            _fail("candidate GitHub evidence is unavailable")
        value: object = response.json()
        return _github_object(value, "candidate GitHub evidence is invalid")

    async def release(self, tag: str) -> dict[str, Any]:
        return await self._api(f"releases/tags/{tag}")

    async def tag_sha(self, tag: str) -> str:
        ref = await self._api(f"git/ref/tags/{tag}")
        obj = _github_object(ref.get("object"), "candidate tag is invalid")
        object_type = obj.get("type")
        object_sha = obj.get("sha")
        if object_type not in {"commit", "tag"} or not isinstance(object_sha, str):
            _fail("candidate tag is invalid")
        if object_type == "commit":
            return object_sha
        tag_object = await self._api(f"git/tags/{object_sha}")
        nested = _github_object(tag_object.get("object"), "candidate tag is invalid")
        nested_type = nested.get("type")
        nested_sha = nested.get("sha")
        if nested_type != "commit" or not isinstance(nested_sha, str):
            _fail("candidate tag is invalid")
        return nested_sha

    async def is_merged_source(self, source_sha: str) -> bool:
        comparison = await self._api(f"compare/{source_sha}...main")
        # GitHub reports the HEAD (`main`) relative to the base (`source_sha`).
        # A candidate already merged into main therefore yields `ahead` (or
        # `identical`), while `behind` means the candidate is ahead of main.
        return comparison.get("status") in {"ahead", "identical"}

    async def runs(self) -> list[dict[str, Any]]:
        response = await self._api(
            f"actions/workflows/{QUALIFICATION_WORKFLOW}/runs?event=workflow_dispatch&status=completed&per_page=100"
        )
        runs = response.get("workflow_runs")
        return _github_objects(runs, "candidate qualification runs are invalid")

    async def artifacts(self, run_id: int) -> list[dict[str, Any]]:
        response = await self._api(f"actions/runs/{run_id}/artifacts?per_page=100")
        artifacts = response.get("artifacts")
        return _github_objects(artifacts, "candidate qualification artifacts are invalid")

    async def download(self, url: str) -> bytes:
        client = get_web_fetch_client()
        response = await client.get(url, headers=self._headers())
        if response.status_code in {301, 302, 303, 307, 308}:
            location = response.headers.get("location")
            if not isinstance(location, str):
                _fail("candidate GitHub asset is unavailable")
            redirect = urlsplit(location)
            if (
                redirect.scheme != "https"
                or redirect.hostname != "release-assets.githubusercontent.com"
                or redirect.port is not None
                or redirect.username is not None
                or redirect.password is not None
            ):
                _fail("candidate GitHub asset is unavailable")
            # Never forward the GitHub API credential to the signed asset URL.
            response = await client.get(location)
        if response.status_code != 200:
            _fail("candidate GitHub asset is unavailable")
        return response.content

    async def download_artifact(self, artifact_id: int) -> bytes:
        response = await get_web_fetch_client().get(
            f"https://api.github.com/repos/{REPOSITORY}/actions/artifacts/{artifact_id}/zip", headers=self._headers()
        )
        if response.status_code != 200:
            _fail("candidate qualification artifact is unavailable")
        return response.content


async def build_qualified_beta_manifest(
    tag: str, *, reader: Any | None = None, now: datetime | None = None
) -> dict[str, Any]:
    """Derive and verify a canonical manifest from GitHub, never caller claims."""
    match = TAG_RE.fullmatch(tag)
    if not match:
        _fail("candidate tag is invalid")
    current_time = _current_time(now)
    source = reader or GitHubQualifiedBetaReader()
    release = _github_object(await _read_github(source, "release", tag), "candidate GitHub evidence is invalid")
    if (
        release.get("tag_name") != tag
        or type(release.get("draft")) is not bool
        or type(release.get("prerelease")) is not bool
        or release["draft"] is not False
        or release["prerelease"] is not False
    ):
        _fail("candidate release is not an immutable published release")
    published_at = release.get("published_at")
    published = _timestamp(published_at)
    if not isinstance(release.get("body"), str):
        _fail("candidate release metadata is invalid")
    if not _is_fresh(published, current_time):
        _fail("candidate release is stale")

    assets = _release_assets(release.get("assets"))
    names = {asset.get("name") for asset in assets}
    # The sanctioned INV-BETA-1 pair is allowed; any other "omi beta" identity is
    # still retired and rejected.
    sanctioned_beta = set(SANCTIONED_BETA_ASSET_NAMES)
    disallowed_beta = {
        name for name in names if isinstance(name, str) and "omi beta" in name.lower() and name not in sanctioned_beta
    }
    if names & RETIRED_ASSET_NAMES or disallowed_beta:
        _fail("candidate contains a retired desktop identity")
    has_beta_identity = sanctioned_beta.issubset(names)
    zip_asset, dmg_asset = _asset(assets, "Omi.zip"), _asset(assets, "omi.dmg")
    evidence_name = f"qualification-evidence-{tag}.json"
    evidence_asset = _asset(assets, evidence_name)
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
    beta_assets: dict[str, dict[str, Any]] = {}
    if has_beta_identity:
        for beta_name in SANCTIONED_BETA_ASSET_NAMES:
            beta_asset = _asset(assets, beta_name)
            beta_assets[beta_name] = beta_asset
            expected_digests[beta_name] = _asset_digest(beta_asset)
    source_sha = await _read_github(source, "tag_sha", tag)
    if not isinstance(source_sha, str):
        _fail("candidate source is not a trusted merged source")
    merged_source = await _read_github(source, "is_merged_source", source_sha)
    if not re.fullmatch(r"[0-9a-f]{40}", source_sha) or merged_source is not True:
        _fail("candidate source is not a trusted merged source")
    _, run_id = _select_qualification_run(await _read_github(source, "runs"), tag, source_sha, current_time)
    artifact_id = _qualification_artifact_id(await _read_github(source, "artifacts", run_id), tag)
    trusted_evidence_bytes = _evidence_from_artifact(await _read_github(source, "download_artifact", artifact_id))
    try:
        evidence: object = json.loads(trusted_evidence_bytes)
    except (TypeError, json.JSONDecodeError):
        _fail("candidate trusted qualification evidence is invalid")
    evidence = _github_object(evidence, "candidate trusted qualification evidence does not bind its run")
    qualification_run_id = evidence.get("qualification_run_id")
    if not _is_exact_integer(qualification_run_id) or qualification_run_id != run_id:
        _fail("candidate trusted qualification evidence does not bind its run")
    if not _is_exact_integer(evidence.get("schema_version")) or evidence.get("schema_version") != 1:
        _fail("candidate trusted qualification evidence is invalid")
    download_targets = [("Omi.zip", zip_url), ("omi.dmg", dmg_url), (evidence_name, evidence_url)]
    for beta_name in SANCTIONED_BETA_ASSET_NAMES:
        if beta_name in beta_assets:
            download_targets.append((beta_name, _asset_url(beta_assets[beta_name], tag, beta_name)))
    downloaded: dict[str, bytes] = {}
    for name, url in download_targets:
        content = await _read_github(source, "download", url)
        if not isinstance(content, bytes):
            _fail("candidate GitHub asset is unavailable")
        downloaded[name] = content
    actual_digests = {name: "sha256:" + hashlib.sha256(content).hexdigest() for name, content in downloaded.items()}
    if actual_digests != expected_digests:
        _fail("candidate asset digest does not match GitHub release metadata")
    if downloaded[evidence_name] != trusted_evidence_bytes:
        _fail("candidate release qualification evidence differs from its trusted run artifact")
    contract_release = _release_for_contract(release, assets)
    # verify_evidence requires the digest set to equal the evidence's artifact set;
    # when the beta identity ships, its two assets are in the evidence too.
    verify_digests = {
        "Omi.zip": actual_digests["Omi.zip"].removeprefix("sha256:"),
        "omi.dmg": actual_digests["omi.dmg"].removeprefix("sha256:"),
    }
    for beta_name in SANCTIONED_BETA_ASSET_NAMES:
        if beta_name in beta_assets:
            verify_digests[beta_name] = actual_digests[beta_name].removeprefix("sha256:")
    try:
        verify_evidence(
            evidence,
            contract_release,
            tag,
            source_sha,
            verify_digests,
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


# Public read-only evidence helpers shared by the emergency Beta evidence
# builder. These aliases keep all GitHub parsing, digest, freshness, and
# fail-closed behavior owned by this module instead of duplicating it.
candidate_asset = _asset
candidate_asset_digest = _asset_digest
candidate_asset_url = _asset_url
candidate_current_time = _current_time
candidate_fail = _fail
candidate_github_object = _github_object
candidate_is_fresh = _is_fresh
candidate_read_github = _read_github
candidate_release_assets = _release_assets
candidate_timestamp = _timestamp
