import asyncio
import os
from unittest.mock import AsyncMock, patch
import pytest
from fastapi import HTTPException

os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")

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


def test_device_model_whitespace_stripped():
    assert fw._get_device_by_model_number("  Omi CV 1  ") == fw.DeviceModel.OMI_CV1
    assert fw._get_device_by_model_number("  Omi DevKit 2 \n") == fw.DeviceModel.OMI_DEVKIT_2
    assert fw._get_device_by_model_number(" Friend ") == fw.DeviceModel.OMI_DEVKIT_1


def test_device_model_invalid_type_handled():
    assert fw._get_device_by_model_number(None) is None
    assert fw._get_device_by_model_number(123) is None
    assert fw._get_device_by_model_number("") is None


def test_get_latest_version_fetch_exception_handled():
    with patch.object(fw, "get_omi_github_releases", AsyncMock(side_effect=RuntimeError("GitHub API timeout"))):
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(
                fw.get_latest_version(
                    device_model="Omi CV 1",
                    firmware_revision="1.0.0",
                    hardware_revision="hw1",
                    manufacturer_name="Omi",
                )
            )
        assert exc_info.value.status_code == 502
        assert exc_info.value.detail == "Failed to fetch firmware releases from repository"


def test_get_stable_version_fetch_exception_handled():
    with patch.object(fw, "get_omi_github_releases", AsyncMock(side_effect=RuntimeError("GitHub API rate limit"))):
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(fw.get_stable_version(device_model="Omi CV 1"))
        assert exc_info.value.status_code == 502
        assert exc_info.value.detail == "Failed to fetch firmware releases from repository"


def test_get_firmware_version_fetch_exception_handled():
    with patch.object(
        fw, "get_omi_github_releases", AsyncMock(side_effect=RuntimeError("GitHub API connection error"))
    ):
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(fw.get_firmware_version(device_model="Omi CV 1", version="3.0.15"))
        assert exc_info.value.status_code == 502
        assert exc_info.value.detail == "Failed to fetch firmware releases from repository"


def test_get_latest_version_whitespace_device_model_succeeds():
    releases = [_release("Omi_CV1_v3.0.15", "3.0.15", _ota("3.0.15"))]
    with patch.object(fw, "get_omi_github_releases", AsyncMock(return_value=releases)):
        res = asyncio.run(
            fw.get_latest_version(
                device_model="  Omi CV 1  ",
                firmware_revision="1.0.0",
                hardware_revision="hw1",
                manufacturer_name="Omi",
            )
        )
        assert res["version"] == "3.0.15"
