import re
from typing import Optional, Tuple, List, Dict

from fastapi import APIRouter, HTTPException
from enum import Enum
import ast

from utils.github_releases import get_omi_github_releases, extract_key_value_pairs
import logging

logger = logging.getLogger(__name__)


class DeviceModel(int, Enum):
    OMI_DEVKIT_1 = 1
    OMI_DEVKIT_2 = 2
    OPEN_GLASS = 3
    OMI_CV1 = 4
    OMI_GLASS = 5


router = APIRouter()

# Firmware release tag pattern — matches Omi_CV1_v3.0.15, Omi_DK2_v2.0.10, OmiGlass_v2.3.2, etc.
FIRMWARE_TAG_PATTERN = re.compile(
    r'^(?:Omi_CV1|Omi_DK2|OmiGlass|OpenGlass|Friend)_v[0-9]+(?:\.[0-9]+){1,2}$', re.IGNORECASE
)


# Device Model Number
# - DK2: Omi DevKit 2
# - DK1: Friend | Friend DevKit 1
# - OpenGlass: OpenGlass
# - Omi_CV1: Omi CV 1
# - OMI_GLASS: OMI Glass
def _get_device_by_model_number(device_model: str):
    if device_model in ['Omi DevKit 2']:
        return DeviceModel.OMI_DEVKIT_2
    if device_model in ['Friend DevKit 1', 'Friend']:
        return DeviceModel.OMI_DEVKIT_1
    if device_model in ['OpenGlass']:
        return DeviceModel.OPEN_GLASS
    if device_model in ['Omi CV 1']:
        return DeviceModel.OMI_CV1
    if device_model in ['OMI Glass', 'OmiGlass']:
        return DeviceModel.OMI_GLASS
    # TODO: remove
    if device_model in ['OMI_shell']:
        return DeviceModel.OMI_CV1
    if device_model in ['nrf5340']:
        return DeviceModel.OMI_CV1

    return None


def _parse_firmware_version(version_str: Optional[str]) -> Optional[Tuple[int, ...]]:
    """
    Parses a firmware version string (e.g., "v1.2.3" or "1.2.3") into a tuple of integers.
    Returns None for empty/invalid/unparsable strings. Callers MUST treat None as
    "version unknown" — not as (0, 0, 0) — otherwise an empty current_firmware
    matches every legacy release and surfaces a stale upgrade prompt to users
    whose actual firmware is current.
    """
    if not version_str:
        return None

    normalized_version_str = version_str.lower()
    if normalized_version_str.startswith('v'):
        normalized_version_str = normalized_version_str[1:]

    parts = normalized_version_str.split('.')

    version_tuple = []
    for part in parts:
        try:
            version_tuple.append(int(part))
        except ValueError:
            return None

    # Pad with zeros if less than 3 parts for consistent comparison (e.g., 1.2 -> 1.2.0)
    while len(version_tuple) < 3:
        version_tuple.append(0)

    return tuple(version_tuple)


def _get_release_prefix(device: DeviceModel) -> str:
    """Map device model to GitHub release tag prefix."""
    if device == DeviceModel.OMI_DEVKIT_2:
        return "Omi_DK2"
    elif device == DeviceModel.OPEN_GLASS:
        return "OpenGlass"
    elif device == DeviceModel.OMI_CV1:
        return "Omi_CV1"
    elif device == DeviceModel.OMI_GLASS:
        return "OmiGlass"
    return "Friend"


def _find_candidate_releases(
    releases: List[Dict], release_prefix: str, current_firmware_tuple: Optional[Tuple[int, ...]] = None
) -> List[Dict]:
    """Filter releases matching the device prefix.

    When current_firmware_tuple is provided, only returns releases newer than
    the current version that meet minimum firmware requirements (update flow).
    When None, returns all valid releases (stable/rollback flow).
    """
    candidates = []
    for release in releases:
        tag_name = release.get("tag_name", "")

        if (
            release.get("draft")
            or release.get("prerelease")
            or not release.get("published_at")
            or not release.get("tag_name")
        ):
            continue

        regex_pattern = f"^{release_prefix}_v[0-9]+(?:\\.[0-9]+){{1,2}}$"
        if not re.match(regex_pattern, tag_name, re.IGNORECASE):
            continue

        kv = extract_key_value_pairs(release.get("body"))

        release_firmware_version_str = kv.get("release_firmware_version")
        if not release_firmware_version_str:
            continue

        if current_firmware_tuple is not None:
            release_firmware_tuple = _parse_firmware_version(release_firmware_version_str)
            # Skip releases with unparseable release_firmware_version metadata.
            if release_firmware_tuple is None:
                continue

            # Condition A: Release must be strictly newer than current version
            if not (release_firmware_tuple > current_firmware_tuple):
                continue

            # Condition B: Device must meet minimum firmware requirement
            minimum_firmware_required_str = kv.get("minimum_firmware_required")
            if minimum_firmware_required_str:
                min_req_tuple = _parse_firmware_version(minimum_firmware_required_str)
                # Treat unparseable min_req as no requirement — same as missing key.
                if min_req_tuple is not None and not (current_firmware_tuple >= min_req_tuple):
                    continue

        candidates.append(release)

    return candidates


def _extract_firmware_response(device: DeviceModel, release: Dict) -> Dict:
    """Extract firmware details and download asset from a GitHub release."""
    kv = extract_key_value_pairs(release.get("body"))

    assets = release.get("assets", [])
    asset = None
    if device == DeviceModel.OMI_GLASS:
        for a in assets:
            asset_name = a.get("name")
            if isinstance(asset_name, str) and asset_name.endswith(".bin"):
                asset = a
                break
        if not asset:
            raise HTTPException(status_code=500, detail="No firmware .bin file found in the selected release")
    else:
        for a in assets:
            asset_name = a.get("name")
            if isinstance(asset_name, str) and "ota" in asset_name.lower() and asset_name.endswith(".zip"):
                asset = a
                break
        if not asset:
            raise HTTPException(status_code=500, detail="No OTA zip found in the selected release")

    if not asset.get("browser_download_url"):
        raise HTTPException(status_code=500, detail="Essential release information (download URL) missing")

    ota_steps = kv.get('ota_update_steps', [])
    is_legacy_dfu_str = kv.get('is_legacy_secure_dfu', 'True')
    try:
        is_legacy_dfu = ast.literal_eval(is_legacy_dfu_str.capitalize())
    except (ValueError, SyntaxError):
        is_legacy_dfu = True

    return {
        "version": kv.get("release_firmware_version"),
        "min_version": kv.get("minimum_firmware_required"),
        "min_app_version": kv.get("minimum_app_version"),
        "min_app_version_code": kv.get("minimum_app_version_code"),
        "zip_url": asset.get("browser_download_url"),
        "draft": False,
        "ota_update_steps": ota_steps,
        "is_legacy_secure_dfu": is_legacy_dfu,
        "changelog": kv.get("changelog", ""),
    }


@router.get("/v2/firmware/latest")
async def get_latest_version(device_model: str, firmware_revision: str, hardware_revision: str, manufacturer_name: str):
    device = _get_device_by_model_number(device_model)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    # Refuse to recommend an upgrade when we can't trust the current version.
    # A missing/garbled firmware_revision used to be silently treated as 0.0.0,
    # which made every legacy release look "newer" and surfaced stale upgrade
    # prompts to users whose actual firmware was current. Fail loud instead.
    current_firmware_tuple = _parse_firmware_version(firmware_revision)
    if current_firmware_tuple is None:
        raise HTTPException(
            status_code=400,
            detail="Could not determine current firmware version",
        )

    releases = await get_omi_github_releases("github_releases_omi", tag_filter=FIRMWARE_TAG_PATTERN)
    if not releases:
        raise HTTPException(status_code=404, detail="No releases found for the repository")

    release_prefix = _get_release_prefix(device)
    candidates = _find_candidate_releases(releases, release_prefix, current_firmware_tuple)

    if not candidates:
        raise HTTPException(status_code=404, detail="No suitable firmware update found for your device version.")

    candidates.sort(key=lambda r: r.get("published_at", ""), reverse=True)
    return _extract_firmware_response(device, candidates[0])


@router.get("/v2/firmware/stable")
async def get_stable_version(device_model: str):
    """Return the latest stable firmware for a device, regardless of current version.

    Used for rolling back to the official stable firmware after flashing custom firmware.
    """
    device = _get_device_by_model_number(device_model)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    releases = await get_omi_github_releases("github_releases_omi", tag_filter=FIRMWARE_TAG_PATTERN)
    if not releases:
        raise HTTPException(status_code=404, detail="No releases found for the repository")

    release_prefix = _get_release_prefix(device)
    candidates = _find_candidate_releases(releases, release_prefix)

    if not candidates:
        raise HTTPException(status_code=404, detail="No stable firmware found for your device.")

    candidates.sort(key=lambda r: r.get("published_at", ""), reverse=True)
    return _extract_firmware_response(device, candidates[0])
