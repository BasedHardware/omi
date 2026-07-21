from html import escape as html_escape
import hmac
import hashlib
import json
import logging
import os
import random
import re
from typing import Any, Optional, List, Dict, Literal
from xml.sax.saxutils import escape as xml_escape

from fastapi import APIRouter, HTTPException, Header, Query
from fastapi.responses import RedirectResponse, Response, HTMLResponse
from pydantic import BaseModel, ConfigDict, Field

from database.desktop_previews import delist_preview, get_current_preview, get_preview_manifest, publish_preview
from database.desktop_update_channels import (
    get_release_manifest,
    promote_channel,
    register_release_manifest,
)
from database.desktop_update_policy import default_desktop_update_policy, get_desktop_update_policy
from database.redis_db import delete_generic_cache
from utils.desktop_update_resolver import live_cache_key, resolve_pointer_release
from utils.executors import db_executor, run_blocking
from utils.github_releases import get_omi_github_releases, extract_key_value_pairs
from utils.metrics import (
    DESKTOP_UPDATE_FEED_VALID,
    DESKTOP_UPDATE_POINTER_MISMATCH_TOTAL,
    DESKTOP_UPDATE_RESOLUTION_TOTAL,
)
from utils.observability.fallback import record_fallback

router = APIRouter()
logger = logging.getLogger(__name__)


class DesktopUpdatePolicyResponse(BaseModel):
    """Server-controlled desktop update banner policy."""

    id: str = Field(description='Policy document identifier.')
    active: bool = Field(description='Whether the update banner is active.')
    severity: str = Field(description='Banner severity (none|banner|required).')
    maximum_build_number: Optional[int] = Field(default=None, description='Max build unaffected by this policy.')
    latest_build_number: Optional[int] = Field(default=None, description='Latest available build number.')
    title: Optional[str] = Field(default=None, description='Banner title.')
    message: Optional[str] = Field(default=None, description='Banner message body.')
    cta_text: str = Field(default='Download latest', description='Call-to-action button text.')
    download_url: str = Field(description='Download URL for the latest release.')
    can_dismiss: bool = Field(default=True, description='Whether the user can dismiss the banner.')
    platforms: Optional[List[str]] = Field(
        default=None, description='Platforms this policy applies to (empty/None = all).'
    )


class ClearCacheResponse(BaseModel):
    """Ack for clearing the desktop releases cache."""

    success: bool = Field(description='Whether the cache was cleared.')
    message: str = Field(description='Human-readable confirmation.')


class DesktopReleaseManifestRequest(BaseModel):
    release_id: str
    platform: str = Field(pattern="^(macos|windows|linux)$")
    version: str
    build_number: int = Field(gt=0)
    zip_url: str
    dmg_url: Optional[str] = None
    beta_zip_url: Optional[str] = None
    beta_dmg_url: Optional[str] = None
    ed_signature: str
    beta_ed_signature: Optional[str] = None
    published_at: str
    changelog: List[str] = Field(default_factory=list)
    mandatory: bool = False
    source_sha: str
    zip_sha256: Optional[str] = None
    dmg_sha256: Optional[str] = None
    beta_zip_sha256: Optional[str] = None
    beta_dmg_sha256: Optional[str] = None
    qualification: Dict[str, Any] = Field(default_factory=dict)


class DesktopChannelPromotionRequest(BaseModel):
    platform: str = Field(pattern="^(macos|windows|linux)$")
    channel: str = Field(pattern="^(beta|stable)$")
    release_id: str
    expected_generation: Optional[int] = Field(default=None, ge=0)
    expected_current_release_id: Optional[str] = None
    operation: Literal["promote", "repoint"] = "promote"


class QualifiedMacOSBetaPromotionRequest(BaseModel):
    """The sole request shape accepted by automatic macOS Beta promotion."""

    model_config = ConfigDict(extra='forbid')

    manifest: DesktopReleaseManifestRequest
    expected_generation: Optional[int] = Field(default=None, ge=0)


class DesktopPreviewPublishRequest(BaseModel):
    """Immutable metadata for a signed desktop preview artifact."""

    slug: str
    source_sha: str
    dmg_url: str
    dmg_sha256: str
    app_name: str
    bundle_id: str
    url_scheme: str
    built_at: str
    signer: str
    notarization: str
    notes: Optional[str] = None
    backend_url: Optional[str] = None
    expected_generation: Optional[int] = Field(default=None, ge=0)


class DesktopPreviewDelistRequest(BaseModel):
    """Compare-and-delete request for a mutable preview landing-page pointer."""

    expected_generation: int = Field(ge=0)


VALID_CHANNELS = {"beta", "stable"}


def _has_beta_promotion_authorization(secret_key: str) -> bool:
    """Match the dedicated automatic-promotion capability without widening admin auth."""
    token = os.getenv("BETA_PROMOTION_TOKEN", "")
    return bool(token) and hmac.compare_digest(secret_key, token)


def _has_admin_authorization(secret_key: str) -> bool:
    """Match the existing admin key with a constant-time comparison."""
    admin_key = os.getenv("ADMIN_KEY")
    return admin_key is not None and hmac.compare_digest(secret_key, admin_key)


DESKTOP_RELEASE_TAG_PATTERN = re.compile(
    r'^v?\d+\.\d+(?:\.\d+)?\+\d+-(?:desktop|macos|windows|linux)(?:-(?:cm|auto))?$',
    re.IGNORECASE,
)

_XML_ATTR_ENTITIES = {'"': '&quot;', "'": '&apos;'}


def _xml_attr(value: str) -> str:
    """Escape a string for use inside XML double-quoted attributes."""
    return xml_escape(value, _XML_ATTR_ENTITIES)


def _parse_desktop_version(tag_name: str) -> Optional[Dict[str, str]]:
    """
    Parse desktop version from tag name.
    Expected format: v1.0.77+464-desktop-cm or v1.0.77+464-macos-cm or v1.0.77+464-desktop-auto or v0.6.4+6004-macos
    The patch component is optional (newer tags use 2-component versions, e.g. v11.0+11000-macos);
    it defaults to "0" when absent.
    Returns dict with version info or None if invalid.
    """
    # Match pattern: v{major}.{minor}[.{patch}]+{build}-{platform}[-{cm|auto}]
    pattern = r'^v?(\d+)\.(\d+)(?:\.(\d+))?\+(\d+)-(?:desktop|macos|windows|linux)(?:-(?:cm|auto))?$'
    match = re.match(pattern, tag_name, re.IGNORECASE)

    if not match:
        return None

    major, minor, patch, build = match.groups()
    patch = patch if patch is not None else '0'

    return {
        'major': major,
        'minor': minor,
        'patch': patch,
        'build': build,
        'version': f"{major}.{minor}.{patch}+{build}",
        'tag_name': tag_name,
    }


def _parse_changelog_to_changes(changelog: List[str], release_body: str) -> List[Dict[str, str]]:
    """
    Parse changelog into desktop_updater changes format.

    Args:
        changelog: List of changelog items from KEY_VALUE_START section
        release_body: Full release body for fallback parsing

    Returns:
        List of change objects with type and message
    """
    changes = []

    # First try to use the structured changelog from KEY_VALUE section
    if changelog:
        for item in changelog:
            item = item.strip()
            if not item:
                continue

            # Try to detect type from keywords
            change_type = "feature"
            item_lower = item.lower()
            if any(word in item_lower for word in ["fix", "fixed", "bug", "issue"]):
                change_type = "fix"
            elif any(word in item_lower for word in ["improve", "performance", "optimization"]):
                change_type = "improvement"
            elif any(word in item_lower for word in ["breaking", "deprecated"]):
                change_type = "breaking"

            changes.append({"type": change_type, "message": item})

    # If no structured changelog, try to parse "What's Changed" section
    if not changes and release_body:
        lines = release_body.split('\n')
        in_changes_section = False

        for line in lines:
            line = line.strip()

            # Detect "What's Changed" section
            if "what's changed" in line.lower():
                in_changes_section = True
                continue

            # Stop at next section or HTML comment
            if in_changes_section and (line.startswith('##') or line.startswith('<!--')):
                break

            # Parse bullet points
            if in_changes_section and line.startswith('*'):
                message = line.lstrip('*').strip()
                if message and not message.startswith('http'):  # Skip PR links
                    # Detect change type
                    change_type = "feature"
                    message_lower = message.lower()
                    if any(word in message_lower for word in ["fix", "fixed", "bug"]):
                        change_type = "fix"
                    elif any(word in message_lower for word in ["improve", "performance"]):
                        change_type = "improvement"

                    changes.append({"type": change_type, "message": message})

    # Default fallback
    if not changes:
        changes.append({"type": "feature", "message": "New version available"})

    return changes


# Assets for the separately-installable "Omi Beta" identity (side-by-side with
# stable). Releases older than the dual-identity pipeline simply lack them.
BETA_IDENTITY_SPARKLE_ASSET = "Omi.Beta.zip"
BETA_IDENTITY_DMG_ASSET = "omi-beta.dmg"


def _get_asset_download_url(release: Dict, names: set) -> Optional[str]:
    for asset in release.get("assets", []):
        if asset.get("name", "") in names:
            return asset.get("browser_download_url")
    return None


def _get_sparkle_zip_download_url(release: Dict) -> Optional[str]:
    """Get the Sparkle ZIP download URL from GitHub release assets."""
    return _get_asset_download_url(release, {"Omi.zip"})


def _get_dmg_download_url(release: Dict) -> Optional[str]:
    """Stable-identity DMG installer URL from GitHub release assets.

    Beta-identity assets are excluded by exact name so their presence can never
    change which installer stable users receive.
    """
    for asset in release.get("assets", []):
        name = asset.get("name", "")
        if name.endswith(".dmg") and name != BETA_IDENTITY_DMG_ASSET:
            return asset.get("browser_download_url")
    return None


async def _find_desktop_release_by_tag(tag_name: str) -> Optional[Dict]:
    """Raw GitHub release by tag, without the isLive filter.

    Pointer entries fabricate their asset list from the registered manifest, so
    beta-identity asset lookups need the underlying release; the pointer itself
    already authorizes liveness.
    """
    if not tag_name:
        return None
    releases = await get_omi_github_releases("github_releases_desktop", tag_filter=DESKTOP_RELEASE_TAG_PATTERN)
    for release in releases or []:
        if release.get("tag_name") == tag_name:
            return release
    return None


async def _resolve_beta_identity_dmg(entry: Dict) -> Optional[str]:
    """Beta-identity DMG URL for this entry's release, or None when it predates
    the dual-identity pipeline."""
    return _get_asset_download_url(entry["release"], {BETA_IDENTITY_DMG_ASSET})


async def _resolve_beta_identity_enclosure(entry: Dict) -> Optional[tuple]:
    """(download_url, ed_signature) of the Omi Beta artifact for this entry's release.

    Returns None when the release predates the dual-identity pipeline (no beta
    asset or no beta signature) — the item is then omitted from the beta feed
    rather than served with a stable-identity artifact.
    """
    release = entry["release"]
    metadata = entry.get("metadata") or {}
    url = _get_asset_download_url(release, {BETA_IDENTITY_SPARKLE_ASSET})
    signature = (metadata.get("betaEdSignature") or "").strip()
    if not url or not signature:
        return None
    return url, signature


async def _get_legacy_live_desktop_releases(platform: str) -> List[Dict]:
    """
    Fetch and filter live desktop releases for a given platform.
    Returns list of releases sorted by published date (newest first).
    Each entry includes release, version_info, metadata (KEY_VALUE_START fields),
    and channel (beta or stable).
    """
    cache_key = "github_releases_desktop"
    # Paginate the legacy fallback so a stable release cannot silently vanish
    # when it rolls off GitHub's first 100 releases (root cause of #9079).
    releases = await get_omi_github_releases(cache_key, tag_filter=DESKTOP_RELEASE_TAG_PATTERN)

    if not releases:
        return []

    desktop_releases = []
    for release in releases:
        if release.get("draft") or not release.get("published_at"):
            continue

        tag_name = release.get("tag_name", "")

        if not (
            tag_name.endswith("-desktop-cm")
            or tag_name.endswith(f"-{platform}-cm")
            or tag_name.endswith("-desktop-auto")
            or tag_name.endswith(f"-{platform}")
        ):
            continue

        version_info = _parse_desktop_version(tag_name)
        if not version_info:
            continue

        kv = extract_key_value_pairs(release.get("body", ""))
        is_live = kv.get("isLive", "false").lower() == "true"
        if not is_live:
            continue

        channel = kv.get("channel", "beta").lower()
        if channel not in VALID_CHANNELS:
            channel = "beta"

        desktop_releases.append(
            {
                "release": release,
                "version_info": version_info,
                "metadata": kv,
                "channel": channel,
            }
        )

    desktop_releases.sort(key=lambda x: x["release"].get("published_at", ""), reverse=True)
    return desktop_releases


def _pointer_release_to_entry(release: Dict[str, Any], channel: str, source: str) -> Dict[str, Any]:
    manifest = release["manifest"]
    assets = [{"name": "Omi.zip", "browser_download_url": manifest["zip_url"]}]
    if manifest.get("dmg_url"):
        assets.append({"name": "Omi.dmg", "browser_download_url": manifest["dmg_url"]})
    if manifest.get("beta_zip_url"):
        assets.append({"name": "Omi.Beta.zip", "browser_download_url": manifest["beta_zip_url"]})
    if manifest.get("beta_dmg_url"):
        assets.append({"name": "omi-beta.dmg", "browser_download_url": manifest["beta_dmg_url"]})
    return {
        "channel": channel,
        "source": source,
        "release": {
            "tag_name": manifest["release_id"],
            "published_at": manifest["published_at"],
            "body": "",
            "assets": assets,
        },
        "version_info": {
            "version": manifest["version"],
            "build": str(manifest["build_number"]),
            "tag_name": manifest["release_id"],
        },
        "metadata": {
            "edSignature": manifest["ed_signature"],
            "betaEdSignature": manifest["beta_ed_signature"],
            "betaZipSha256": manifest.get("beta_zip_sha256"),
            "betaDmgSha256": manifest.get("beta_dmg_sha256"),
            "changelog": manifest.get("changelog", []),
            "mandatory": "true" if manifest.get("mandatory") else "false",
            "sourceSha": manifest["source_sha"],
        },
    }


def _reconciliation_sample_rate() -> float:
    try:
        return min(1.0, max(0.0, float(os.getenv("DESKTOP_UPDATE_RECONCILE_SAMPLE_RATE", "0.01"))))
    except ValueError:
        return 0.01


def _newest_release_by_channel(entries: List[Dict]) -> Dict[str, Dict]:
    newest: Dict[str, Dict] = {}
    for entry in entries:
        channel = entry["channel"]
        current = newest.get(channel)
        if current is None or entry["release"].get("published_at", "") > current["release"].get("published_at", ""):
            newest[channel] = entry
    return newest


def _record_pointer_mismatches(platform: str, pointer_entries: List[Dict], legacy_entries: List[Dict]) -> None:
    legacy_by_channel = _newest_release_by_channel(legacy_entries)
    for pointer in pointer_entries:
        channel = pointer["channel"]
        legacy = legacy_by_channel.get(channel)
        if legacy is None:
            DESKTOP_UPDATE_POINTER_MISMATCH_TOTAL.labels(platform=platform, channel=channel, field="missing").inc()
            continue
        comparisons = {
            "build": (pointer["version_info"]["build"], legacy["version_info"]["build"]),
            "zip_url": (
                _get_sparkle_zip_download_url(pointer["release"]),
                _get_sparkle_zip_download_url(legacy["release"]),
            ),
            "dmg_url": (_get_dmg_download_url(pointer["release"]), _get_dmg_download_url(legacy["release"])),
        }
        for field, (pointer_value, legacy_value) in comparisons.items():
            if pointer_value != legacy_value:
                DESKTOP_UPDATE_POINTER_MISMATCH_TOTAL.labels(platform=platform, channel=channel, field=field).inc()
                logger.warning(
                    "desktop_update_pointer_mismatch platform=%s channel=%s field=%s",
                    platform,
                    channel,
                    field,
                )


async def _get_live_desktop_releases(platform: str) -> List[Dict]:
    """Resolve explicit pointers first, then exact-channel legacy releases.

    A validated pointer LKG is used before the legacy GitHub scan. Stable never
    falls through to beta. Set DESKTOP_UPDATE_POINTERS_MODE=legacy as a kill
    switch while the dual-path rollout is being observed.
    """
    if os.getenv("DESKTOP_UPDATE_POINTERS_MODE", "primary").lower() == "legacy":
        releases = await _get_legacy_live_desktop_releases(platform)
        record_fallback(
            component='other',
            from_mode='desktop_update_pointer',
            to_mode='desktop_update_legacy',
            reason='policy',
            outcome='degraded',
            log=logger,
        )
        for entry in releases:
            DESKTOP_UPDATE_RESOLUTION_TOTAL.labels(
                platform=platform, channel=entry["channel"], source="legacy_forced"
            ).inc()
            DESKTOP_UPDATE_FEED_VALID.labels(platform=platform, channel=entry["channel"]).set(1)
        return releases

    pointer_entries: List[Dict] = []
    missing: Dict[str, str] = {}
    for channel in ("stable", "beta"):
        release, source, reason = await run_blocking(db_executor, resolve_pointer_release, platform, channel)
        if release is None:
            missing[channel] = reason or "pointer_missing"
            continue
        pointer_entries.append(_pointer_release_to_entry(release, channel, source))

    legacy_entries: List[Dict] = []
    should_reconcile = bool(pointer_entries) and random.random() < _reconciliation_sample_rate()
    if missing or should_reconcile:
        legacy_entries = await _get_legacy_live_desktop_releases(platform)

    if should_reconcile:
        _record_pointer_mismatches(platform, pointer_entries, legacy_entries)

    resolved = list(pointer_entries)
    legacy_by_channel = _newest_release_by_channel(legacy_entries)
    for channel, reason in missing.items():
        legacy = legacy_by_channel.get(channel)
        if legacy is None:
            continue
        legacy = {**legacy, "source": "legacy_fallback"}
        resolved.append(legacy)
        record_fallback(
            component='other',
            from_mode='desktop_update_pointer_lkg',
            to_mode='desktop_update_legacy',
            reason='config_incomplete' if reason == 'pointer_missing' else 'other',
            outcome='recovered',
            log=logger,
        )
        DESKTOP_UPDATE_RESOLUTION_TOTAL.labels(platform=platform, channel=channel, source="legacy_fallback").inc()
        DESKTOP_UPDATE_FEED_VALID.labels(platform=platform, channel=channel).set(1)

    resolved.sort(key=lambda entry: entry["release"].get("published_at", ""), reverse=True)
    return resolved


def _download_landing_html(dmg_url: str, channel: str = "stable", version: str = "") -> str:
    """Generate an HTML landing page that auto-triggers DMG download."""
    channel_label = "Beta " if channel == "beta" else ""
    version_display = f"v{version}" if version else ""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Download Omi {channel_label}for macOS</title>
    <meta http-equiv="refresh" content="2;url={dmg_url}">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
               background: #0a0a0a; color: #fff; display: flex; align-items: center;
               justify-content: center; min-height: 100vh; text-align: center; }}
        .container {{ max-width: 960px; padding: 40px 24px; }}
        h1 {{ font-size: 28px; font-weight: 600; margin-bottom: 12px; }}
        .version {{ color: #555; font-size: 14px; margin-bottom: 24px; }}
        .subtitle {{ color: #888; font-size: 16px; margin-bottom: 32px; }}
        .status {{ width: 40px; height: 40px; margin: 0 auto 24px; position: relative; }}
        .spinner {{ width: 40px; height: 40px; border: 3px solid #333; border-top-color: #fff;
                    border-radius: 50%; animation: spin 0.8s linear infinite; }}
        .checkmark {{ display: none; font-size: 36px; color: #4ade80; }}
        .done .spinner {{ display: none; }}
        .done .checkmark {{ display: block; }}
        .done .subtitle {{ color: #4ade80; }}
        @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
        .download-link {{ color: #6C8FFF; text-decoration: none; font-size: 15px; }}
        .download-link:hover {{ text-decoration: underline; }}
        .video-container {{ margin-top: 32px; border-radius: 12px; overflow: hidden;
                            background: #151515; display: none; }}
        .video-container video {{ width: 100%; display: block; }}
        .video-label {{ color: #888; font-size: 13px; padding: 12px 16px; text-align: center; }}
        .steps {{ color: #888; font-size: 13px; margin-top: 20px; line-height: 1.8; text-align: left;
                  background: #151515; border-radius: 12px; padding: 20px 24px; }}
        .steps b {{ color: #ccc; }}
        .discord {{ margin-top: 24px; font-size: 14px; color: #888; }}
        .discord a {{ color: #5865F2; text-decoration: none; }}
        .discord a:hover {{ text-decoration: underline; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Downloading Omi {channel_label}for macOS</h1>
        <p class="version">{version_display}</p>
        <p class="subtitle" id="status-text">Your download should start automatically&hellip;</p>
        <div class="status" id="status-icon">
            <div class="spinner"></div>
            <div class="checkmark">&#10003;</div>
        </div>
        <p><a class="download-link" href="{dmg_url}">Click here if the download doesn&rsquo;t start</a></p>
        <div class="video-container" id="demo-video">
            <video autoplay muted loop playsinline>
                <source src="https://storage.googleapis.com/omi_macos_updates/omi-demo.mp4" type="video/mp4">
            </video>
            <p class="video-label">See how Omi works</p>
        </div>
        <div class="steps">
            <b>Installation steps:</b><br>
            1. Open the downloaded .dmg file<br>
            2. Drag Omi to your Applications folder<br>
            3. Launch Omi from Applications
        </div>
        <p class="discord">Need help? Join our <a href="https://discord.com/invite/8MP3b9ymvx">Discord community</a></p>
    </div>
    <script>
        setTimeout(function() {{
            window.location.href = "{dmg_url}";
            document.getElementById("status-icon").classList.add("done");
            document.getElementById("status-text").textContent = "Download started!";
            document.getElementById("demo-video").style.display = "block";
        }}, 2000);
    </script>
</body>
</html>"""


def _preview_download_landing_html(manifest: Dict[str, Any]) -> str:
    """Render a public preview landing page from already-validated metadata.

    The registry still treats notes and app identity as untrusted text because
    they originate with a CI payload. Escape every dynamic HTML value rather
    than relying on the publisher's credentials as an XSS boundary.
    """
    app_name = html_escape(str(manifest["app_name"]), quote=True)
    slug = html_escape(str(manifest["slug"]), quote=True)
    source_sha = html_escape(str(manifest["source_sha"]), quote=True)
    built_at = html_escape(str(manifest["built_at"]), quote=True)
    notes = html_escape(str(manifest.get("notes") or ""), quote=True)
    dmg_url = html_escape(str(manifest["dmg_url"]), quote=True)
    notes_html = f'<p class="notes">{notes}</p>' if notes else ""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta http-equiv="refresh" content="2;url={dmg_url}">
    <title>Download {app_name} for macOS</title>
    <style>
        * {{ box-sizing: border-box; }}
        body {{ margin: 0; min-height: 100vh; display: grid; place-items: center; background: #0a0a0a;
               color: #f5f5f5; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
        main {{ width: min(620px, calc(100% - 48px)); padding: 40px; border: 1px solid #2a2a2a; border-radius: 16px;
               background: #121212; text-align: center; }}
        h1 {{ margin: 0 0 12px; font-size: 28px; }}
        p {{ color: #b6b6b6; line-height: 1.5; }}
        code {{ display: block; overflow-wrap: anywhere; padding: 12px; border-radius: 8px; background: #1c1c1c;
               color: #e8e8e8; font-size: 13px; }}
        a {{ color: #ffffff; }}
        .notes {{ white-space: pre-wrap; }}
        .meta {{ margin-top: 24px; text-align: left; font-size: 13px; color: #909090; }}
    </style>
</head>
<body>
    <main>
        <h1>Downloading {app_name}</h1>
        <p>Your macOS preview download should start automatically.</p>
        <p><a href="{dmg_url}">Download the preview DMG</a></p>
        {notes_html}
        <div class="meta">
            <p>Preview branch: <strong>{slug}</strong></p>
            <p>Approved source commit:</p>
            <code>{source_sha}</code>
            <p>Build time: {built_at}</p>
        </div>
    </main>
</body>
</html>"""


def _format_changelog_html(changes: List[Dict[str, str]]) -> str:
    """Format changelog as HTML for Sparkle appcast"""
    if not changes:
        return "<p>Bug fixes and improvements</p>"

    html = "<ul>"
    for change in changes:
        change_type = change.get('type', 'improvement')
        message = change.get('message', '')
        icon = {'feature': '&#10024;', 'fix': '&#128027;', 'improvement': '&#9889;', 'breaking': '&#9888;'}.get(
            change_type, '&#8226;'
        )
        html += f"<li>{icon} {xml_escape(message)}</li>"

    html += "</ul>"
    return html


def _generate_appcast_xml(items: List[Dict], platform: str) -> str:
    """
    Generate Sparkle 2.0 appcast XML with channel support.
    Stable items get no <sparkle:channel> tag (Sparkle default).
    Beta items get <sparkle:channel>beta</sparkle:channel>.
    """
    lines = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<rss version="2.0" xmlns:sparkle="http://www.andymatuschak.org/xml-namespaces/sparkle">',
        '  <channel>',
        '    <title>Omi Desktop Updates</title>',
        '    <description>Omi AI Desktop Application</description>',
        '    <language>en</language>',
    ]

    for release_item in items:
        version = release_item['version']
        short_version = release_item['shortVersion']
        changes_html = _format_changelog_html(release_item.get('changes', []))
        pub_date = release_item.get('date', '')
        url = release_item.get('url', '')
        ed_signature = release_item.get('edSignature', '').strip()
        channel = release_item.get('channel', 'beta')

        if not url:
            continue

        # Escape CDATA-unsafe sequences in changelog HTML
        safe_html = changes_html.replace(']]>', ']]]]><![CDATA[>')

        lines.append('    <item>')
        lines.append(f'      <title>Omi {xml_escape(version)}</title>')
        lines.append(f'      <sparkle:version>{xml_escape(short_version)}</sparkle:version>')
        lines.append(f'      <sparkle:shortVersionString>{xml_escape(version)}</sparkle:shortVersionString>')
        lines.append(f'      <description><![CDATA[{safe_html}]]></description>')
        lines.append(f'      <pubDate>{xml_escape(pub_date)}</pubDate>')

        enclosure = f'      <enclosure url="{_xml_attr(url)}" type="application/octet-stream" sparkle:os="{_xml_attr(platform)}"'
        if ed_signature:
            enclosure += f' sparkle:edSignature="{_xml_attr(ed_signature)}"'
        enclosure += ' />'
        lines.append(enclosure)

        # Stable = no channel tag (Sparkle default). Beta = explicit tag.
        if channel == "beta":
            lines.append('      <sparkle:channel>beta</sparkle:channel>')

        if release_item.get('mandatory'):
            lines.append('      <sparkle:criticalUpdate />')

        lines.append('    </item>')

    lines.append('  </channel>')
    lines.append('</rss>')
    return '\n'.join(lines)


@router.get("/v2/desktop/appcast.xml")
async def get_desktop_appcast_xml(
    platform: str = Query(default="macos", pattern="^(macos|windows|linux)$"),
    identity: str = Query(default="stable", pattern="^(stable|beta)$"),
):
    """
    Sparkle appcast XML endpoint for desktop auto-updates.
    Returns a single feed with both beta and stable channel items.
    Sparkle clients filter by their configured allowed channels.

    identity=beta is requested only by the separately-installable "Omi Beta" app
    (its SUFeedURL carries the parameter): it gets beta-channel items only, with
    beta-identity enclosures, so Sparkle can never replace it with a
    stable-identity bundle. Legacy stable-identity installs on the beta channel
    keep the default feed and their current update behavior.
    """
    try:
        desktop_releases = await _get_live_desktop_releases(platform)

        if not desktop_releases:
            raise HTTPException(status_code=404, detail=f"No desktop releases found for platform: {platform}")

        # Deduplicate: latest release per channel
        seen_channels = set()
        items = []

        for entry in desktop_releases:
            channel = entry["channel"]
            if identity == "beta" and channel != "beta":
                continue
            if channel in seen_channels:
                continue
            seen_channels.add(channel)

            release = entry["release"]
            version_info = entry["version_info"]
            kv = entry["metadata"]

            changelog = kv.get("changelog", [])
            mandatory = kv.get("mandatory", "false").lower() == "true"
            ed_signature = kv.get("edSignature", "")

            changes = _parse_changelog_to_changes(changelog, release.get("body", ""))
            if identity == "beta":
                beta_enclosure = await _resolve_beta_identity_enclosure(entry)
                if beta_enclosure is None:
                    seen_channels.discard(channel)
                    continue
                download_url, ed_signature = beta_enclosure
            else:
                download_url = _get_sparkle_zip_download_url(release)

            if not download_url:
                seen_channels.discard(channel)
                continue

            items.append(
                {
                    "version": version_info["version"],
                    "shortVersion": version_info["build"],
                    "changes": changes,
                    "date": release.get("published_at"),
                    "mandatory": mandatory,
                    "url": download_url,
                    "platform": platform,
                    "edSignature": ed_signature,
                    "channel": channel,
                }
            )

        xml_content = _generate_appcast_xml(items, platform)

        return Response(
            content=xml_content,
            media_type="application/xml",
            headers={"Cache-Control": "max-age=300"},
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating appcast: {str(e)}")


@router.get("/v2/desktop/download/latest")
async def download_latest_desktop_release(
    platform: str = Query(default="macos", pattern="^(macos|windows|linux)$"),
    channel: str = Query(default="stable", pattern="^(beta|stable)$"),
    identity: str = Query(default="stable", pattern="^(stable|beta)$"),
):
    """
    Redirect to the latest desktop release DMG installer.
    Both channels resolve only from their explicit channel pointer or the same
    channel in the legacy release metadata.
    Defaults to stable channel (for macos.omi.me). Use channel=beta for QA.
    identity=beta serves the separately-installable "Omi Beta" DMG, which runs
    side-by-side with stable.
    """
    if identity == "beta":
        channel = "beta"
    desktop_releases = await _get_live_desktop_releases(platform)
    if not desktop_releases:
        raise HTTPException(status_code=404, detail=f"No live desktop releases found for platform: {platform}")

    # Find latest release matching the requested channel
    for entry in desktop_releases:
        if entry["channel"] != channel:
            continue
        if identity == "beta":
            dmg_url = await _resolve_beta_identity_dmg(entry)
        else:
            dmg_url = _get_dmg_download_url(entry["release"])
        if dmg_url:
            version = entry["version_info"]["version"]
            return HTMLResponse(content=_download_landing_html(dmg_url, channel=channel, version=version))

    raise HTTPException(status_code=404, detail=f"No DMG installer found for channel: {channel}")


@router.get("/v2/desktop/download/beta")
async def download_beta_desktop_release(
    platform: str = Query(default="macos", pattern="^(macos|windows|linux)$"),
):
    """
    Redirect to the latest beta desktop release DMG installer.
    Convenience endpoint for macos.omi.me/beta (URL map can't add query params).

    Serves the side-by-side "Omi Beta" app. Until the first release that ships
    beta-identity artifacts is live, it falls back to the stable-identity DMG so
    the public link keeps working. (Sparkle self-updates stay strict: only this
    human install landing may fall back.)
    """
    try:
        return await download_latest_desktop_release(platform=platform, channel="beta", identity="beta")
    except HTTPException as e:
        if e.status_code != 404:
            raise
    record_fallback(
        component='other',
        from_mode='desktop_download_beta_identity',
        to_mode='desktop_download_stable_identity',
        reason='config_incomplete',
        outcome='degraded',
        log=logger,
    )
    return await download_latest_desktop_release(platform=platform, channel="beta", identity="stable")


def _preview_landing_response(result: Dict[str, Any]) -> HTMLResponse:
    return HTMLResponse(
        content=_preview_download_landing_html(result["manifest"]),
        headers={"Cache-Control": "no-store"},
    )


@router.get("/v2/desktop/previews/{slug}")
async def download_current_desktop_preview(slug: str):
    """Serve a public landing page for the current approved preview of one slug."""
    try:
        preview = await run_blocking(db_executor, get_current_preview, slug)
    except ValueError:
        raise HTTPException(status_code=404, detail="Preview not found") from None
    if preview is None:
        raise HTTPException(status_code=404, detail="Preview not found")
    return _preview_landing_response(preview)


@router.get("/v2/desktop/previews/{slug}/{source_sha}")
async def download_immutable_desktop_preview(slug: str, source_sha: str):
    """Serve a public landing page for one immutable approved preview artifact."""
    try:
        manifest = await run_blocking(db_executor, get_preview_manifest, slug, source_sha)
    except ValueError:
        raise HTTPException(status_code=404, detail="Preview not found") from None
    if manifest is None:
        raise HTTPException(status_code=404, detail="Preview not found")
    return _preview_landing_response({"manifest": manifest})


def _has_preview_publish_authorization(secret_key: str) -> bool:
    """Require a preview-only secret and fail closed when it is not configured."""
    preview_key = os.getenv("DESKTOP_PREVIEW_PUBLISH_KEY")
    return bool(preview_key) and hmac.compare_digest(secret_key, preview_key)


@router.post("/v2/desktop/previews/publish", status_code=201)
async def publish_desktop_preview(request: DesktopPreviewPublishRequest, secret_key: str = Header(...)):
    """Register a preview artifact without touching normal desktop release state."""
    if not _has_preview_publish_authorization(secret_key):
        raise HTTPException(status_code=403, detail="You are not authorized to publish desktop previews")
    try:
        result = await run_blocking(
            db_executor,
            publish_preview,
            request.model_dump(exclude={"expected_generation"}),
            expected_generation=request.expected_generation,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"success": True, **result}


@router.delete("/v2/desktop/previews/{slug}")
async def delist_desktop_preview(
    slug: str,
    request: DesktopPreviewDelistRequest,
    secret_key: str = Header(...),
):
    """Remove only a slug's mutable landing-page pointer, retaining immutable artifacts."""
    if not _has_preview_publish_authorization(secret_key):
        raise HTTPException(status_code=403, detail="You are not authorized to delist desktop previews")
    try:
        result = await run_blocking(
            db_executor,
            delist_preview,
            slug,
            expected_generation=request.expected_generation,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"success": True, **result}


@router.get("/v2/desktop/update-policy", response_model=DesktopUpdatePolicyResponse)
def get_desktop_update_policy_endpoint(
    platform: str = Query(default="macos", pattern="^(macos|windows|linux)$"),
    current_build: Optional[int] = Query(default=None, ge=0),
):
    """
    Server-controlled desktop update banner policy.

    Defaults to inactive when the Firestore document is missing. Configure
    ``desktop_update_policy/current`` to show a dismissible banner or a required
    manual-update prompt to future desktop clients.
    """
    try:
        return get_desktop_update_policy(current_build=current_build, platform=platform)
    except Exception as exc:
        # The policy only accelerates manual recovery; clients still have the
        # Sparkle appcast and stable manual download path when Firestore is unavailable.
        logger.warning("desktop_update_policy_unavailable error_type=%s", type(exc).__name__)
        record_fallback(
            component="other",
            from_mode="desktop_update_policy",
            to_mode="desktop_update_appcast",
            reason="other",
            outcome="recovered",
            log=logger,
        )
        return default_desktop_update_policy()


@router.post("/v2/desktop/clear-cache", response_model=ClearCacheResponse)
def clear_desktop_cache(secret_key: str = Header(...)):
    """
    Clear the GitHub releases cache for desktop updates.
    This forces the next appcast.xml request to fetch fresh data from GitHub.
    Last-known-good entries are deliberately preserved for incident recovery.
    """
    if not _has_admin_authorization(secret_key):
        raise HTTPException(status_code=403, detail='You are not authorized to perform this action')
    delete_generic_cache("github_releases_desktop")
    for platform in ("macos", "windows", "linux"):
        for channel in VALID_CHANNELS:
            delete_generic_cache(live_cache_key(platform, channel))
    return {"success": True, "message": "Desktop releases cache cleared successfully"}


@router.post("/v2/desktop/releases", status_code=201)
async def register_desktop_release(request: DesktopReleaseManifestRequest, secret_key: str = Header(...)):
    """Register an immutable release manifest without making it user-visible."""
    if not _has_admin_authorization(secret_key):
        raise HTTPException(status_code=403, detail='You are not authorized to perform this action')
    try:
        manifest = await run_blocking(db_executor, register_release_manifest, request.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"success": True, "manifest": manifest}


@router.post("/v2/desktop/channels/promote-qualified-beta")
async def promote_qualified_macos_beta(
    request: QualifiedMacOSBetaPromotionRequest,
    secret_key: str = Header(...),
):
    """Register and advance one passed-T2 macOS Beta candidate with one dedicated capability."""
    if not _has_beta_promotion_authorization(secret_key):
        raise HTTPException(status_code=403, detail='You are not authorized to perform this action')

    manifest_data = request.manifest.model_dump()
    if manifest_data["platform"] != "macos":
        raise HTTPException(status_code=422, detail="automatic beta promotion requires a macos manifest")
    qualification = manifest_data["qualification"]
    if qualification.get("passed") is not True or str(qualification.get("tier", "")).upper() != "T2":
        raise HTTPException(
            status_code=422, detail="automatic beta promotion requires passed T2 qualification evidence"
        )

    try:
        manifest = await run_blocking(db_executor, register_release_manifest, manifest_data)
        pointer = await run_blocking(
            db_executor,
            promote_channel,
            "macos",
            "beta",
            manifest["release_id"],
            expected_generation=request.expected_generation,
            expected_current_release_id=None,
            operation="promote",
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    await run_blocking(db_executor, delete_generic_cache, live_cache_key("macos", "beta"))
    return {"success": True, "manifest": manifest, "pointer": pointer}


@router.get("/v2/desktop/releases/{release_id}")
async def get_desktop_release_manifest(release_id: str, secret_key: str = Header(...)):
    """Return the retained manifest used for a pointer transition, not GitHub metadata."""
    if not _has_admin_authorization(secret_key):
        raise HTTPException(status_code=403, detail='You are not authorized to perform this action')
    manifest = await run_blocking(db_executor, get_release_manifest, release_id)
    if manifest is None:
        raise HTTPException(status_code=404, detail='desktop release manifest not found')
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {"success": True, "manifest": manifest, "manifest_sha256": hashlib.sha256(canonical).hexdigest()}


@router.post("/v2/desktop/channels/promote")
async def promote_desktop_channel(request: DesktopChannelPromotionRequest, secret_key: str = Header(...)):
    """Atomically advance or repoint one explicit qualified channel pointer."""
    if not _has_admin_authorization(secret_key):
        raise HTTPException(status_code=403, detail='You are not authorized to perform this action')
    try:
        pointer = await run_blocking(
            db_executor,
            promote_channel,
            request.platform,
            request.channel,
            request.release_id,
            expected_generation=request.expected_generation,
            expected_current_release_id=request.expected_current_release_id,
            operation=request.operation,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await run_blocking(
        db_executor,
        delete_generic_cache,
        live_cache_key(request.platform, request.channel),
    )
    return {"success": True, "pointer": pointer}
