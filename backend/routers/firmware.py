import os
import re

import httpx
from fastapi import APIRouter, HTTPException
from enum import Enum

class DeviceModel(int, Enum):
    OMI_DEVKIT_1 = 1
    OMI_DEVKIT_2 = 2
    OPEN_GLASS = 3


router = APIRouter()


# Device Model Number
# - DK2: Omi DevKit 2
# - DK1: Friend | Friend DevKit 1
# - OpenGlass: OpenGlass
def _get_device_by_model_number(device_model: str):
    if device_model in ['Omi DevKit 2']:
        return DeviceModel.OMI_DEVKIT_2
    if device_model in ['Friend DevKit 1', 'Friend']:
        return DeviceModel.OMI_DEVKIT_1
    if device_model in ['OpenGlass']:
        return DeviceModel.OPEN_GLASS

    return None

@router.get("/v2/firmware/latest")
async def get_latest_version(device_model: str, firmware_revision: str, hardware_revision: str, manufacturer_name: str):
    device = _get_device_by_model_number(device_model)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    async with httpx.AsyncClient() as client:
        url = "https://api.github.com/repos/basedhardware/omi/releases?per_page=100"
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Authorization": f"Bearer {os.getenv('GITHUB_TOKEN')}",
        }
        response = await client.get(url, headers=headers)
        if response.status_code != 200:
            raise HTTPException(status_code=response.status_code, detail="Failed to fetch latest release")
        releases = response.json()
        latest_release = None

        # Release tags
        # - Omi_DK2_v2.0.5
        # - Friend_v1.0.4
        # - OpenGlass_v1.0.4
        release_prefix = "Friend"
        if DeviceModel.OMI_DEVKIT_2:
            release_prefix = "Omi_DK2"
        if DeviceModel.OPEN_GLASS:
            release_prefix = "OpenGlass"
        for release in releases:
            if release.get("draft") or not release.get("published_at") or not release.get("tag_name"):
                continue
            if not bool(re.match(f"{release_prefix}_v\d+.\d+.\d+", release.get("tag_name"), re.IGNORECASE)):
                continue
            if not latest_release or release.get("published_at") > latest_release.get("published_at"):
                latest_release = release

        if not latest_release:
            raise HTTPException(status_code=404, detail="No latest release found for the device")
        release_data = latest_release

        # Extract key:value from body
        # <!-- KEY_VALUE_START
        # release_firmware_version:v2.0.5
        # minimum_firmware_required:v2.0.0
        # minimum_app_version:1.0.48
        # minimum_app_version_code:181
        # KEY_VALUE_END -->
        kv = extract_key_value_pairs(release_data.get("body"))
        assets = release_data.get("assets")
        asset = None
        for a in assets:
            if "ota" in a.get("name", "").lower():
                asset = a
                break
        if not asset:
            raise HTTPException(status_code=500, detail="No OTA zip found in the release")

        return {
            "version": kv.get("release_firmware_version"),
            "min_version": kv.get("minimum_firmware_required"),
            "min_app_version": kv.get("minimum_app_version"),
            "min_app_version_code": kv.get("minimum_app_version_code"),
            "zip_url": asset.get("browser_download_url"),
        }


@router.get("/v1/firmware/latest")
async def get_latest_version_v1(device: int):
    # if device = 1 : Friend
    # if device = 2 : OpenGlass
    if device != 1 and device != 2:
        raise HTTPException(status_code=404, detail="Device not found")
    async with httpx.AsyncClient() as client:
        url = "https://api.github.com/repos/basedhardware/omi/releases"
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Authorization": f"Bearer {os.getenv('GITHUB_TOKEN')}",
        }
        response = await client.get(url, headers=headers)
        if response.status_code != 200:
            raise HTTPException(status_code=response.status_code, detail="Failed to fetch latest release")
        releases = response.json()
        latest_release = None
        device_type = "friend" if device == 1 else "openglass"
        for release in releases:
            if (
                release.get("published_at")
                and release.get("tag_name")
                and (device_type in release.get("tag_name", "").lower() or device_type in release.get("name", "").lower())
                and "firmware" in release.get("tag_name", "").lower()
                and not release.get("draft")
            ):
                if not latest_release:
                    latest_release = release
                else:
                    if release.get("published_at") > latest_release.get("published_at"):
                        latest_release = release
        if not latest_release:
            raise HTTPException(status_code=404, detail="No latest release found for the device")
        release_data = latest_release
        kv = extract_key_value_pairs(release_data.get("body"))
        assets = release_data.get("assets")
        asset = None
        for a in assets:
            if "ota" in a.get("name", "").lower():
                asset = a
                break
        if not asset:
            raise HTTPException(status_code=500, detail="No OTA zip found in the release")
        return {
            "version": kv.get("release_firmware_version"),
            "min_version": kv.get("minimum_firmware_required"),
            "min_app_version": kv.get("minimum_app_version"),
            "min_app_version_code": kv.get("minimum_app_version_code"),
            "device_type": kv.get("device_type"),
            "id": release_data.get("id"),
            "tag_name": release_data.get("tag_name"),
            "published_at": release_data.get("published_at"),
            "draft": release_data.get("draft"),
            "prerelease": release_data.get("prerelease"),
            "zip_url": asset.get("browser_download_url"),
            "zip_name": asset.get("name"),
            "zip_size": asset.get("size"),
            "release_name": release_data.get("name"),
        }


def extract_key_value_pairs(markdown_content):
    key_value_pattern = re.compile(r'<!-- KEY_VALUE_START\s*(.*?)\s*KEY_VALUE_END -->', re.DOTALL)
    key_value_match = key_value_pattern.search(markdown_content)

    if not key_value_match:
        return {}

    key_value_string = key_value_match.group(1)
    lines = key_value_string.split('\n')
    key_value_map = {}

    for line in lines:
        key_value = line.split(':')
        if len(key_value) == 2:
            key = key_value[0].strip()
            value = key_value[1].strip()
            key_value_map[key] = value

    return key_value_map
