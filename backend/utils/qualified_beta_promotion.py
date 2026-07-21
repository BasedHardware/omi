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
RETIRED_ASSET_NAMES = frozenset({"Omi.Beta.zip", "omi-beta.dmg", "Omi Beta.zip", "Omi Beta.dmg"})
QUALIFICATION_WORKFLOW = "desktop_qualify_beta.yml"
QUALIFICATION_ARTIFACT_PREFIX = "desktop-qualification-evidence-"
QUALIFICATION_EVIDENCE_FILE = "qualification-evidence.json"
MAX_QUALIFICATION_ARTIFACT_BYTES = 1_048_576
MAX_QUALIFICATION_EVIDENCE_BYTES = 262_144


class QualifiedBetaAdmissionError(ValueError):
    """A candidate failed server-side Beta admission without mutable effects."""


def _fail(message: str) -> NoReturn:
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


def _asset_url(asset: dict[str, Any], tag: str, name: str) -> str:
    url = asset.get("browser_download_url") or asset.get("url")
    expected = f"https://github.com/{REPOSITORY}/releases/download/{tag}/{name}"
    if not isinstance(url, str) or url != expected:
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
    for run in _github_objects(runs, "candidate qualification runs are invalid"):
        try:
            validate_qualification_run(run, REPOSITORY, tag, source_sha)
            run_id = _trusted_run_id(run)
            completed_at = _timestamp(run.get("updated_at"))
        except (ValueError, QualifiedBetaAdmissionError):
            continue
        if now - completed_at > timedelta(seconds=_max_age_seconds()):
            continue
        acceptable.append((completed_at, run_id, run))
    if not acceptable:
        _fail("candidate has no fresh trusted qualification run")
    _, run_id, run = max(acceptable, key=lambda item: (item[0], item[1]))
    return run, run_id


def _qualification_artifact_id(artifacts: object, tag: str) -> int:
    expected_name = f"{QUALIFICATION_ARTIFACT_PREFIX}{tag}"
    matches = [
        artifact
        for artifact in _github_objects(artifacts, "candidate qualification artifacts are invalid")
        if artifact.get("name") == expected_name
    ]
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
                "url": asset.get("browser_download_url") or asset.get("url"),
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
        return comparison.get("status") in {"behind", "identical"}

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
        response = await get_web_fetch_client().get(url, headers=self._headers())
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
    source = reader or GitHubQualifiedBetaReader()
    release = _github_object(await _read_github(source, "release", tag), "candidate GitHub evidence is invalid")
    if release.get("tag_name") != tag or release.get("draft") or release.get("prerelease"):
        _fail("candidate release is not an immutable published release")
    published_at = release.get("published_at")
    published = _timestamp(published_at)
    if (now or datetime.now(timezone.utc)) - published > timedelta(seconds=_max_age_seconds()):
        _fail("candidate release is stale")

    assets = _github_objects(release.get("assets"), "candidate GitHub release assets are invalid")
    names = {asset.get("name") for asset in assets}
    if names & RETIRED_ASSET_NAMES or any(isinstance(name, str) and "omi beta" in name.lower() for name in names):
        _fail("candidate contains a retired desktop identity")
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
    source_sha = await _read_github(source, "tag_sha", tag)
    if not isinstance(source_sha, str):
        _fail("candidate source is not a trusted merged source")
    if not re.fullmatch(r"[0-9a-f]{40}", source_sha) or not await _read_github(source, "is_merged_source", source_sha):
        _fail("candidate source is not a trusted merged source")
    current_time = now or datetime.now(timezone.utc)
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
    downloaded: dict[str, bytes] = {}
    for name, url in (("Omi.zip", zip_url), ("omi.dmg", dmg_url), (evidence_name, evidence_url)):
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
