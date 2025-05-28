import os
import re
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException
from enum import Enum
import ast

from database.redis_db import get_generic_cache, set_generic_cache


class DeviceModel(int, Enum):
    OMI_DEVKIT_1 = 1
    OMI_DEVKIT_2 = 2
    OPEN_GLASS = 3
    OMI_CV1 = 4


router = APIRouter()


# Device Model Number
# - DK2: Omi DevKit 2
# - DK1: Friend | Friend DevKit 1
# - OpenGlass: OpenGlass
# - Omi_CV1: Omi CV 1
def _get_device_by_model_number(device_model: str):
    if device_model in ['Omi DevKit 2']:
        return DeviceModel.OMI_DEVKIT_2
    if device_model in ['Friend DevKit 1', 'Friend']:
        return DeviceModel.OMI_DEVKIT_1
    if device_model in ['OpenGlass']:
        return DeviceModel.OPEN_GLASS
    if device_model in ['Omi CV 1']:
        return DeviceModel.OMI_CV1
    # TODO: remove
    if device_model in ['OMI_shell']:
        return DeviceModel.OMI_CV1
    if device_model in ['nrf5340']:
        return DeviceModel.OMI_CV1

    return None


async def get_omi_github_releases(cache_key: str) -> Optional[list]:
    """Fetch releases from GitHub API with caching"""

    # Check cache first
    cached_releases = get_generic_cache(cache_key)
    if cached_releases:
        return cached_releases

    # Make GitHub API request if not cached
    async with httpx.AsyncClient() as client:
        url = "https://api.github.com/repos/BasedHardware/omi/releases?per_page=100"
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Authorization": f"Bearer {os.getenv('GITHUB_TOKEN')}",
        }
        response = await client.get(url, headers=headers)
        if response.status_code != 200:
            raise HTTPException(status_code=response.status_code, detail="Failed to fetch latest release")
        releases = response.json()
        # Cache successful response for 30 minutes
        set_generic_cache(cache_key, releases, ttl=1800)
        return releases


@router.get("/v2/firmware/latest")
async def get_latest_version(device_model: str, firmware_revision: str, hardware_revision: str, manufacturer_name: str):
    device = _get_device_by_model_number(device_model)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    cache_key = "github_releases_omi"
    releases = await get_omi_github_releases(cache_key)
    latest_release = None

    # Release tags
    # - Omi_DK2_v2.0.5
    # - Friend_v1.0.4
    # - OpenGlass_v1.0.4
    # - Omi_CV1_v1.0.0
    release_prefix = "Friend"
    if device == DeviceModel.OMI_DEVKIT_2:
        release_prefix = "Omi_DK2"
    if device == DeviceModel.OPEN_GLASS:
        release_prefix = "OpenGlass"
    if device == DeviceModel.OMI_CV1:
        release_prefix = "Omi_CV1"
    for release in releases:
        if release.get("draft") or not release.get("published_at") or not release.get("tag_name"):
            continue
        if not bool(re.match(f"{release_prefix}_v[0-9]+.[0-9]+.[0-9]+", release.get("tag_name"), re.IGNORECASE)):
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
        if "ota" in a.get("name", "").lower() and a.get("name", "").endswith(".zip"):
            asset = a
            break
    if not asset:
        raise HTTPException(status_code=500, detail="No OTA zip found in the release")

    # Safely get values with defaults
    version = kv.get("release_firmware_version")
    min_version = kv.get("minimum_firmware_required")
    min_app_version = kv.get("minimum_app_version")
    min_app_version_code = kv.get("minimum_app_version_code")
    changelog_text = kv.get("changelog", "")
    ota_steps = kv.get('ota_update_steps', [])
    is_legacy_dfu_str = kv.get('is_legacy_secure_dfu', 'True')

    # Attempt to parse boolean, default to True on error
    try:
        is_legacy_dfu = ast.literal_eval(is_legacy_dfu_str.capitalize())
    except (ValueError, SyntaxError):
        is_legacy_dfu = True

    # Basic validation (optional but recommended)
    if not all([version, asset.get("browser_download_url")]):
        raise HTTPException(status_code=500, detail="Essential release information missing")

    return {
        "version": version,
        "min_version": min_version,
        "min_app_version": min_app_version,
        "min_app_version_code": min_app_version_code,
        "zip_url": asset.get("browser_download_url"),
        "draft": False,
        "ota_update_steps": ota_steps,
        "is_legacy_secure_dfu": is_legacy_dfu,
        "changelog": changelog_text,
    }


def extract_key_value_pairs(markdown_content):
    if not markdown_content:
        return {}

    key_value_pattern = re.compile(r'<!-- KEY_VALUE_START\s*(.*?)\s*KEY_VALUE_END -->', re.DOTALL)
    key_value_match = key_value_pattern.search(markdown_content)

    if not key_value_match:
        return {}

    key_value_string = key_value_match.group(1).strip()
    lines = key_value_string.split('\n')
    key_value_map = {}

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Use split with maxsplit=1 to handle values containing colons
        parts = line.split(':', 1)
        if len(parts) == 2:
            key = parts[0].strip()
            value = parts[1].strip()

            if key == 'ota_update_steps':
                # Split by comma, filter empty strings
                key_value_map[key] = [step.strip() for step in value.split(',') if step.strip()]
            elif key == 'changelog':
                # Split by pipe, filter empty strings
                key_value_map[key] = [item.strip() for item in value.split('|') if item.strip()]
            else:
                key_value_map[key] = value

    return key_value_map
