import re
import hashlib
from dataclasses import dataclass
from typing import Optional, Tuple, List, Dict

from fastapi import APIRouter, HTTPException, Request
from enum import Enum
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from config.app_channel import APP_CHANNEL_HEADER, APP_CHANNELS, app_channel
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


class FirmwareVersionResponse(BaseModel):
    version: str | None = None
    min_version: str | None = None
    min_app_version: str | None = None
    min_app_version_code: str | None = None
    zip_url: str | None = None
    draft: bool = False
    ota_update_steps: List[str] = Field(default_factory=list)
    is_legacy_secure_dfu: bool = True
    changelog: str | List[str] = ''


# Firmware release tag pattern — matches Omi_CV1_v3.0.15, Omi_DK2_v2.0.10, OmiGlass_v2.3.2, etc.
FIRMWARE_TAG_PATTERN = re.compile(
    r'^(?:Omi_CV1|Omi_DK2|OmiGlass|OpenGlass|Friend)_v[0-9]+(?:\.[0-9]+){1,2}$',
    re.IGNORECASE,
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
    if not version_str or not isinstance(version_str, str):
        return None

    cleaned = version_str.replace('\x00', '').strip()
    if not cleaned:
        return None

    normalized_version_str = cleaned.lower()
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


# Release audience keys. A release that names an audience goes to that audience
# whatever its rollout_percent, so it can be published at 0% and reach only
# testers:
#   allow_uid_sha256: comma-separated hex SHA-256 of Firebase uids. Hashes, not
#     uids, because release bodies are public.
#   channels: comma-separated X-Omi-App-Channel values, e.g. "beta" for TestFlight
#     and non-production builds. While set, nobody outside these channels or the
#     allowlist gets the release, so remove it to roll out to everyone.
# A malformed audience value fails closed.
AUDIENCE_UIDS_KEY = 'allow_uid_sha256'
AUDIENCE_CHANNELS_KEY = 'channels'
_UID_SHA256_PATTERN = re.compile(r'^[0-9a-f]{64}$')


@dataclass(frozen=True)
class ReleaseAudience:
    """Who is asking: the hashed uid when the request was authenticated, and the app channel."""

    uid_sha256: Optional[str] = None
    channel: str = 'unknown'


def _parse_list(raw) -> Optional[List[str]]:
    values = [v.strip().lower() for v in str(raw).split(',')]
    if not values or any(not v for v in values):
        return None
    return values


def _audience_match(kv: Dict, audience: Optional[ReleaseAudience]) -> Optional[bool]:
    """True/False for a valid audience policy, None when it is malformed."""
    matched = False
    if AUDIENCE_UIDS_KEY in kv:
        uids = _parse_list(kv[AUDIENCE_UIDS_KEY])
        if uids is None or not all(_UID_SHA256_PATTERN.match(u) for u in uids):
            return None
        matched = matched or bool(audience and audience.uid_sha256 in uids)
    if AUDIENCE_CHANNELS_KEY in kv:
        channels = _parse_list(kv[AUDIENCE_CHANNELS_KEY])
        if channels is None or not set(channels) <= APP_CHANNELS:
            return None
        matched = matched or bool(audience and audience.channel in channels)
    return matched


def _release_is_eligible(
    kv: Dict,
    device_id: Optional[str],
    *,
    ignore_rollout_percent: bool = False,
    audience: Optional[ReleaseAudience] = None,
) -> bool:
    """Stable nested cohorts. Missing policy preserves published-release behavior.

    Unidentified clients can receive legacy or 100% releases, never partial cohorts.
    Invalid explicit policies fail closed so a typo cannot expand a rollout.
    Explicit version requests ignore rollout_percent, but always honor blocked.
    """
    blocked = str(kv.get('blocked', 'false')).strip().lower()
    if blocked != 'false':
        return False
    if ignore_rollout_percent:
        return True
    if AUDIENCE_UIDS_KEY in kv or AUDIENCE_CHANNELS_KEY in kv:
        matched = _audience_match(kv, audience)
        if matched is None:
            return False
        if matched:
            return True
        if AUDIENCE_CHANNELS_KEY in kv:
            return False
    raw_percent = str(kv.get('rollout_percent', '100')).strip()
    if not re.fullmatch(r'[0-9]+', raw_percent):
        return False
    percent = int(raw_percent)
    if not 0 <= percent <= 100:
        return False
    if percent == 100:
        return True
    if percent == 0 or not device_id or not device_id.strip():
        return False
    # Hash only the identifier, not the release, so expanding the percentage
    # retains existing members and successive releases share the same cohort.
    bucket = int.from_bytes(hashlib.sha256(device_id.encode('utf-8')).digest()[:8], 'big') % 100
    return bucket < percent


def _find_candidate_releases(
    releases: List[Dict],
    release_prefix: str,
    current_firmware_tuple: Optional[Tuple[int, ...]] = None,
    device_id: Optional[str] = None,
    *,
    ignore_rollout_percent: bool = False,
    audience: Optional[ReleaseAudience] = None,
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
        if not _release_is_eligible(kv, device_id, ignore_rollout_percent=ignore_rollout_percent, audience=audience):
            continue

        release_firmware_version_str = kv.get("release_firmware_version")
        if not release_firmware_version_str:
            continue

        release_firmware_tuple = _parse_firmware_version(release_firmware_version_str)
        # Skip releases with unparseable release_firmware_version metadata.
        if release_firmware_tuple is None:
            continue

        if current_firmware_tuple is not None:
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


def _find_release_by_version(
    releases: List[Dict], release_prefix: str, target_firmware_tuple: Tuple[int, ...]
) -> Optional[Dict]:
    """Return the release whose release_firmware_version equals the target, or None.

    Reuses _find_candidate_releases (current=None) for the device-prefix / draft / prerelease / tag
    filtering, sorts newest-published first (matching get_stable/get_latest) so the result is
    deterministic if two releases ever advertise the same version, then matches the exact target. An
    unparseable stored version simply won't equal the (already-validated) target, so it is skipped.
    Ignores rollout_percent for support/reverts; blocked releases remain unavailable.
    """
    candidates = _find_candidate_releases(releases, release_prefix, ignore_rollout_percent=True)
    candidates.sort(key=lambda r: r.get("published_at", ""), reverse=True)
    for release in candidates:
        kv = extract_key_value_pairs(release.get("body"))
        if _parse_firmware_version(kv.get("release_firmware_version")) == target_firmware_tuple:
            return release
    return None


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
    is_legacy_dfu = str(is_legacy_dfu_str).strip().lower() != 'false'

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


async def _request_audience(request: Optional[Request], releases: List[Dict]) -> ReleaseAudience:
    """The caller's audience. The token is verified only when some release has a uid allowlist.

    An absent or invalid token just means no uid: the update check stays anonymous-safe.
    """
    if request is None:
        return ReleaseAudience()
    channel = app_channel(request.headers.get(APP_CHANNEL_HEADER))
    uid_sha256 = None
    if any(AUDIENCE_UIDS_KEY in extract_key_value_pairs(r.get("body")) for r in releases):
        uid = await run_in_threadpool(_verified_uid, request.headers.get("authorization"))
        if uid:
            uid_sha256 = hashlib.sha256(uid.encode("utf-8")).hexdigest()
    return ReleaseAudience(uid_sha256=uid_sha256, channel=channel)


def _verified_uid(authorization: Optional[str]) -> Optional[str]:
    parts = (authorization or "").split(" ")
    if len(parts) != 2 or not parts[1]:
        return None
    from utils.other.endpoints import verify_token

    try:
        return verify_token(parts[1])
    except Exception:  # an unverifiable token only drops the uid allowlist match
        logger.info("firmware audience: token not verified")
        return None


@router.get("/v2/firmware/latest", response_model=FirmwareVersionResponse)
async def get_latest_version(
    device_model: str,
    firmware_revision: str,
    hardware_revision: str,
    manufacturer_name: str,
    device_id: Optional[str] = None,
    request: Request = None,  # pyright: ignore[reportArgumentType]  # FastAPI injects Request; direct callers omit it
):
    """Return the newest eligible update using stable device rollout cohorts.

    device_id is the hex SHA-256 of the device's normalized DIS serial, never the
    raw serial. Omit it when no serial is available; unidentified clients cannot
    receive partial rollouts. Blocked releases are never offered. Releases with an
    audience (allow_uid_sha256, channels) also read the caller's token and app channel.
    """
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
    audience = await _request_audience(request, releases)
    candidates = _find_candidate_releases(
        releases, release_prefix, current_firmware_tuple, device_id, audience=audience
    )

    if not candidates:
        raise HTTPException(status_code=404, detail="No suitable firmware update found for your device version.")

    candidates.sort(key=lambda r: r.get("published_at", ""), reverse=True)
    return _extract_firmware_response(device, candidates[0])


@router.get("/v2/firmware/stable", response_model=FirmwareVersionResponse)
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


@router.get("/v2/firmware/version", response_model=FirmwareVersionResponse)
async def get_firmware_version(device_model: str, version: str):
    """Return the OTA metadata for a specific published firmware version of a device.

    Complements /v2/firmware/stable by making any individual published build addressable, e.g. to pin
    or roll a device back to a known-good earlier version, or for QA/support to flash a named build.
    Explicit requests ignore rollout_percent for support/reverts, but blocked releases return 404.
    """
    device = _get_device_by_model_number(device_model)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    target = _parse_firmware_version(version)
    if target is None:
        raise HTTPException(status_code=400, detail="Could not parse requested firmware version")

    releases = await get_omi_github_releases("github_releases_omi", tag_filter=FIRMWARE_TAG_PATTERN)
    if not releases:
        raise HTTPException(status_code=404, detail="No releases found for the repository")

    match = _find_release_by_version(releases, _get_release_prefix(device), target)
    if not match:
        raise HTTPException(status_code=404, detail="Requested firmware version not found for your device.")

    return _extract_firmware_response(device, match)
