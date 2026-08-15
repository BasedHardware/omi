"""Fail-closed GitHub evidence primitives for immutable macOS Beta candidates."""

from __future__ import annotations

from collections.abc import Awaitable
from datetime import datetime, timedelta, timezone
import os
import re
from typing import Any, NoReturn
from urllib.parse import urlsplit

from utils.http_client import get_web_fetch_client

REPOSITORY = "BasedHardware/omi"
TAG_RE = re.compile(r"^v(?P<version>[0-9]+\.[0-9]+\.[0-9]+)\+(?P<build>[1-9][0-9]*)-macos$")
SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
UTC_RFC3339_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?Z$")
_EXACT_DATETIME_TYPE = datetime


class BetaCandidateAdmissionError(ValueError):
    """A candidate failed server-side Beta admission without mutable effects."""


def _fail(message: str) -> NoReturn:
    raise BetaCandidateAdmissionError(message)


def _timestamp(value: object) -> datetime:
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
    try:
        age = now - timestamp
        maximum_age = timedelta(seconds=_max_age_seconds())
    except (OverflowError, TypeError):
        _fail("candidate freshness is invalid")
    return timedelta(0) <= age <= maximum_age


def _max_age_seconds() -> int:
    raw = os.getenv("BETA_CANDIDATE_MAX_AGE_SECONDS", "604800")
    try:
        value = int(raw)
    except ValueError:
        _fail("candidate freshness policy is unavailable")
    if value <= 0:
        _fail("candidate freshness policy is unavailable")
    return value


def _github_object(value: object, message: str) -> dict[str, Any]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        _fail(message)
    return dict(value)


def _github_objects(value: object, message: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        _fail(message)
    return [_github_object(item, message) for item in value]


def _nonempty_string(value: object, message: str) -> str:
    if not isinstance(value, str) or not value:
        _fail(message)
    return value


def _release_assets(value: object) -> list[dict[str, Any]]:
    assets = _github_objects(value, "candidate GitHub release assets are invalid")
    for asset in assets:
        _nonempty_string(asset.get("name"), "candidate GitHub release assets are invalid")
        _nonempty_string(asset.get("browser_download_url"), "candidate GitHub release assets are invalid")
        if asset.get("digest") is not None and not isinstance(asset.get("digest"), str):
            _fail("candidate GitHub release assets are invalid")
    return assets


def _asset(assets: list[dict[str, Any]], name: str) -> dict[str, Any]:
    matches = [asset for asset in assets if asset.get("name") == name]
    if len(matches) != 1:
        _fail("candidate is missing a canonical asset")
    return matches[0]


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


async def _read_github(source: Any, method: str, *args: Any) -> Any:
    try:
        dependency = getattr(source, method)
        result = dependency(*args)
        if not isinstance(result, Awaitable):
            _fail("candidate GitHub read dependency is unavailable")
        return await result
    except BetaCandidateAdmissionError:
        raise
    except Exception as exc:
        raise BetaCandidateAdmissionError("candidate GitHub read dependency is unavailable") from exc


class GitHubBetaCandidateReader:
    """Read-only public GitHub view used before the Beta admission transaction."""

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
            f"https://api.github.com/repos/{REPOSITORY}/{path}", headers=self._headers()
        )
        if response.status_code != 200:
            _fail("candidate GitHub evidence is unavailable")
        return _github_object(response.json(), "candidate GitHub evidence is invalid")

    async def release(self, tag: str) -> dict[str, Any]:
        return await self._api(f"releases/tags/{tag}")

    async def tag_sha(self, tag: str) -> str:
        ref = await self._api(f"git/ref/tags/{tag}")
        obj = _github_object(ref.get("object"), "candidate tag is invalid")
        object_type, object_sha = obj.get("type"), obj.get("sha")
        if object_type not in {"commit", "tag"} or not isinstance(object_sha, str):
            _fail("candidate tag is invalid")
        if object_type == "commit":
            return object_sha
        tag_object = await self._api(f"git/tags/{object_sha}")
        nested = _github_object(tag_object.get("object"), "candidate tag is invalid")
        if nested.get("type") != "commit" or not isinstance(nested.get("sha"), str):
            _fail("candidate tag is invalid")
        return nested["sha"]

    async def is_merged_source(self, source_sha: str) -> bool:
        comparison = await self._api(f"compare/{source_sha}...main")
        return comparison.get("status") in {"ahead", "identical"}

    async def download(self, url: str) -> bytes:
        client = get_web_fetch_client()
        response = await client.get(url, headers=self._headers())
        if response.status_code in {301, 302, 303, 307, 308}:
            location = response.headers.get("location")
            redirect = urlsplit(location) if isinstance(location, str) else None
            if (
                redirect is None
                or redirect.scheme != "https"
                or redirect.hostname != "release-assets.githubusercontent.com"
                or redirect.port is not None
                or redirect.username is not None
                or redirect.password is not None
            ):
                _fail("candidate GitHub asset is unavailable")
            response = await client.get(location)
        if response.status_code != 200:
            _fail("candidate GitHub asset is unavailable")
        return response.content


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
