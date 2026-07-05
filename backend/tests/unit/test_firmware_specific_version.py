"""GET /v2/firmware/version: OTA metadata for one specific published firmware version of a device.

/v2/firmware/stable only returns the latest stable build, so there was no way to address an exact
earlier version. This adds that, so a device can be pinned or rolled back to a known-good build, or
QA/support can flash a named version. It reuses the existing hardened helpers (_find_candidate_releases
applies the same draft/prerelease/tag/parseable validation) and mirrors get_stable_version.

Test isolation: routers.firmware imports cleanly; the async handler is driven via asyncio.run with
get_omi_github_releases patched (no network), and extract_key_value_pairs stays real to parse fixtures.
"""

import os

os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

import routers.firmware as fw


def _release(tag, version, assets, draft=False, prerelease=False, published_at="2026-01-01T00:00:00Z"):
    body = f"<!-- KEY_VALUE_START\nrelease_firmware_version: {version}\nKEY_VALUE_END -->"
    return {
        "tag_name": tag,
        "body": body,
        "assets": assets,
        "draft": draft,
        "prerelease": prerelease,
        "published_at": published_at,
    }


def _ota(version="3.0.15"):
    return [{"name": f"Omi_CV1_OTA_v{version}.zip", "browser_download_url": "https://x/ota.zip"}]


def _bin(version="2.3.2"):
    return [{"name": f"omiglass_v{version}.bin", "browser_download_url": "https://x/fw.bin"}]


def _call(**kw):
    params = {"device_model": "Omi CV 1", "version": "3.0.15"}
    params.update(kw)
    return asyncio.run(fw.get_firmware_version(**params))


def test_exact_match_non_glass_returns_ota_zip():
    releases = [_release("Omi_CV1_v3.0.15", "3.0.15", _ota("3.0.15"))]
    with patch.object(fw, "get_omi_github_releases", AsyncMock(return_value=releases)):
        result = _call(version="3.0.15")
    assert result["version"] == "3.0.15"
    assert result["zip_url"] == "https://x/ota.zip"


def test_exact_match_glass_returns_bin():
    releases = [_release("OmiGlass_v2.3.2", "2.3.2", _bin("2.3.2"))]
    with patch.object(fw, "get_omi_github_releases", AsyncMock(return_value=releases)):
        result = _call(device_model="OmiGlass", version="2.3.2")
    assert result["version"] == "2.3.2"
    assert result["zip_url"] == "https://x/fw.bin"


def test_version_normalization_accepts_v_prefix():
    releases = [_release("Omi_CV1_v3.0.15", "3.0.15", _ota("3.0.15"))]
    with patch.object(fw, "get_omi_github_releases", AsyncMock(return_value=releases)):
        assert _call(version="v3.0.15")["version"] == "3.0.15"
        assert _call(version="3.0.15")["version"] == "3.0.15"


def test_picks_the_requested_version_not_the_newest():
    releases = [
        _release("Omi_CV1_v3.0.15", "3.0.15", _ota("3.0.15"), published_at="2026-03-01T00:00:00Z"),
        _release("Omi_CV1_v3.0.10", "3.0.10", _ota("3.0.10"), published_at="2026-01-01T00:00:00Z"),
    ]
    with patch.object(fw, "get_omi_github_releases", AsyncMock(return_value=releases)):
        assert _call(version="3.0.10")["version"] == "3.0.10"


def test_not_found_is_404():
    releases = [_release("Omi_CV1_v3.0.15", "3.0.15", _ota("3.0.15"))]
    with patch.object(fw, "get_omi_github_releases", AsyncMock(return_value=releases)):
        with pytest.raises(HTTPException) as ei:
            _call(version="9.9.9")
    assert ei.value.status_code == 404


def test_unparseable_version_is_400_before_fetch():
    m = AsyncMock(return_value=[])
    with patch.object(fw, "get_omi_github_releases", m):
        with pytest.raises(HTTPException) as ei:
            _call(version="abc")
    assert ei.value.status_code == 400
    m.assert_not_called()  # 400 short-circuits before any release fetch


def test_unknown_device_is_404_before_fetch():
    m = AsyncMock(return_value=[])
    with patch.object(fw, "get_omi_github_releases", m):
        with pytest.raises(HTTPException) as ei:
            _call(device_model="Nonexistent", version="3.0.15")
    assert ei.value.status_code == 404
    m.assert_not_called()


def test_empty_releases_is_404():
    with patch.object(fw, "get_omi_github_releases", AsyncMock(return_value=[])):
        with pytest.raises(HTTPException) as ei:
            _call(version="3.0.15")
    assert ei.value.status_code == 404


def test_draft_and_prerelease_excluded():
    releases = [
        _release("Omi_CV1_v3.0.15", "3.0.15", _ota("3.0.15"), draft=True),
        _release("Omi_CV1_v3.0.16", "3.0.16", _ota("3.0.16"), prerelease=True),
    ]
    with patch.object(fw, "get_omi_github_releases", AsyncMock(return_value=releases)):
        for v in ("3.0.15", "3.0.16"):
            with pytest.raises(HTTPException) as ei:
                _call(version=v)
            assert ei.value.status_code == 404


def test_helper_finds_exact_match():
    releases = [
        _release("Omi_CV1_v3.0.15", "3.0.15", _ota("3.0.15")),
        _release("Omi_CV1_v3.0.10", "3.0.10", _ota("3.0.10")),
    ]
    assert fw._find_release_by_version(releases, "Omi_CV1", (3, 0, 10))["tag_name"] == "Omi_CV1_v3.0.10"
    assert fw._find_release_by_version(releases, "Omi_CV1", (9, 9, 9)) is None


def test_duplicate_version_returns_newest_published_deterministically():
    older = _release(
        "Omi_CV1_v3.0.15",
        "3.0.15",
        [{"name": "Omi_CV1_OTA_v3.0.15.zip", "browser_download_url": "https://x/OLD.zip"}],
        published_at="2026-01-01T00:00:00Z",
    )
    newer = _release(
        "Omi_CV1_v3.0.15",
        "3.0.15",
        [{"name": "Omi_CV1_OTA_v3.0.15.zip", "browser_download_url": "https://x/NEW.zip"}],
        published_at="2026-03-01T00:00:00Z",
    )
    # Raw list order older-first; the newest-published must win regardless.
    with patch.object(fw, "get_omi_github_releases", AsyncMock(return_value=[older, newer])):
        assert _call(version="3.0.15")["zip_url"] == "https://x/NEW.zip"
