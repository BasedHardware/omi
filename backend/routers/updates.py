import os
import re
from typing import Optional, List, Dict
from xml.sax.saxutils import escape as xml_escape

from fastapi import APIRouter, HTTPException, Header, Query
from fastapi.responses import RedirectResponse, Response, HTMLResponse

from routers.firmware import get_omi_github_releases, extract_key_value_pairs
from database.redis_db import delete_generic_cache

router = APIRouter()

VALID_CHANNELS = {"beta", "stable"}

_XML_ATTR_ENTITIES = {'"': '&quot;', "'": '&apos;'}


def _xml_attr(value: str) -> str:
    """Escape a string for use inside XML double-quoted attributes."""
    return xml_escape(value, _XML_ATTR_ENTITIES)


def _parse_desktop_version(tag_name: str) -> Optional[Dict[str, str]]:
    """
    Parse desktop version from tag name.
    Expected format: v1.0.77+464-desktop-cm or v1.0.77+464-macos-cm or v1.0.77+464-desktop-auto or v0.6.4+6004-macos
    Returns dict with version info or None if invalid.
    """
    # Match pattern: v{major}.{minor}.{patch}+{build}-{platform}[-{cm|auto}]
    pattern = r'^v?(\d+)\.(\d+)\.(\d+)\+(\d+)-(?:desktop|macos|windows|linux)(?:-(?:cm|auto))?$'
    match = re.match(pattern, tag_name, re.IGNORECASE)

    if not match:
        return None

    major, minor, patch, build = match.groups()

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


def _get_sparkle_zip_download_url(release: Dict) -> Optional[str]:
    """Get the Sparkle ZIP download URL from GitHub release assets."""
    for asset in release.get("assets", []):
        if asset.get("name", "") == "Omi.zip":
            return asset.get("browser_download_url")
    return None


def _get_dmg_download_url(release: Dict) -> Optional[str]:
    """Get the DMG installer download URL from GitHub release assets."""
    for asset in release.get("assets", []):
        if asset.get("name", "").endswith(".dmg"):
            return asset.get("browser_download_url")
    return None


async def _get_live_desktop_releases(platform: str) -> List[Dict]:
    """
    Fetch and filter live desktop releases for a given platform.
    Returns list of releases sorted by published date (newest first).
    Each entry includes release, version_info, metadata (KEY_VALUE_START fields),
    and channel (beta or stable).
    """
    cache_key = "github_releases_desktop"
    releases = await get_omi_github_releases(cache_key)

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
        .container {{ max-width: 480px; padding: 40px 24px; }}
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
async def get_desktop_appcast_xml(platform: str = Query(default="macos", pattern="^(macos|windows|linux)$")):
    """
    Sparkle appcast XML endpoint for desktop auto-updates.
    Returns a single feed with both beta and stable channel items.
    Sparkle clients filter by their configured allowed channels.
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
):
    """
    Redirect to the latest desktop release DMG installer.
    Stable resolves from the latest stable-tagged release.
    Beta always resolves from the newest desktop GitHub release, regardless of channel metadata.
    Defaults to stable channel (for macos.omi.me). Use channel=beta for QA.
    """
    desktop_releases = await _get_live_desktop_releases(platform)
    if not desktop_releases:
        raise HTTPException(status_code=404, detail=f"No live desktop releases found for platform: {platform}")

    if channel == "beta":
        # Beta downloads should always expose the newest GitHub desktop build,
        # even if the release-channel promotion metadata is stale.
        for entry in desktop_releases:
            dmg_url = _get_dmg_download_url(entry["release"])
            if dmg_url:
                version = entry["version_info"]["version"]
                return HTMLResponse(content=_download_landing_html(dmg_url, channel="beta", version=version))
        raise HTTPException(status_code=404, detail="No DMG installer found for latest beta release")

    # Find latest release matching the requested channel
    for entry in desktop_releases:
        if entry["channel"] != channel:
            continue
        dmg_url = _get_dmg_download_url(entry["release"])
        if dmg_url:
            version = entry["version_info"]["version"]
            return HTMLResponse(content=_download_landing_html(dmg_url, channel=channel, version=version))

    # Fallback: if no stable release, try beta (for fresh installs before first promotion)
    if channel == "stable":
        for entry in desktop_releases:
            dmg_url = _get_dmg_download_url(entry["release"])
            if dmg_url:
                version = entry["version_info"]["version"]
                return HTMLResponse(content=_download_landing_html(dmg_url, channel="stable", version=version))

    raise HTTPException(status_code=404, detail=f"No DMG installer found for channel: {channel}")


@router.get("/v2/desktop/download/beta")
async def download_beta_desktop_release(
    platform: str = Query(default="macos", pattern="^(macos|windows|linux)$"),
):
    """
    Redirect to the latest beta desktop release DMG installer.
    Convenience endpoint for macos.omi.me/beta (URL map can't add query params).
    """
    return await download_latest_desktop_release(platform=platform, channel="beta")


@router.post("/v2/desktop/clear-cache")
async def clear_desktop_cache(secret_key: str = Header(...)):
    """
    Clear the GitHub releases cache for desktop updates.
    This forces the next appcast.xml request to fetch fresh data from GitHub.
    """
    if secret_key != os.getenv('ADMIN_KEY'):
        raise HTTPException(status_code=403, detail='You are not authorized to perform this action')
    delete_generic_cache("github_releases_desktop")
    return {"success": True, "message": "Desktop releases cache cleared successfully"}
