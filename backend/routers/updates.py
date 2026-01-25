import os
import re
from typing import Optional, List, Dict
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom import minidom

from fastapi import APIRouter, HTTPException, Header, Query
from fastapi.responses import Response

from routers.firmware import get_omi_github_releases, extract_key_value_pairs
from database.redis_db import delete_generic_cache

router = APIRouter()


def _parse_desktop_version(tag_name: str) -> Optional[Dict[str, str]]:
    """
    Parse desktop version from tag name.
    Expected format: v1.0.77+464-desktop-cm or v1.0.77+464-macos-cm or v1.0.77+464-desktop-auto
    Returns dict with version info or None if invalid.
    """
    # Match pattern: v{major}.{minor}.{patch}+{build}-{platform}-{cm|auto}
    pattern = r'^v?(\d+)\.(\d+)\.(\d+)\+(\d+)-(?:desktop|macos|windows|linux)-(?:cm|auto)$'
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


def _get_sparkle_zip_download_url(release: Dict, version: str, platform: str) -> Optional[str]:
    """
    Get the Sparkle ZIP download URL from GitHub release assets.

    Args:
        release: GitHub release object
        version: Version string (e.g., "1.0.78+474")
        platform: Platform name (macos, windows, linux)

    Returns:
        Download URL for the Sparkle ZIP file, or None if not found
    """
    assets = release.get("assets", [])

    # Look for the Sparkle ZIP file: Omi.zip
    expected_filename = f"Omi.zip"

    for asset in assets:
        asset_name = asset.get("name", "")
        if asset_name == expected_filename:
            return asset.get("browser_download_url")

    # Fallback: look for any zip file that matches the pattern
    for asset in assets:
        asset_name = asset.get("name", "")
        if asset_name.endswith(f"Omi.zip"):
            return asset.get("browser_download_url")

    return None


async def _get_live_desktop_releases(platform: str) -> List[Dict]:
    """
    Fetch and filter live desktop releases for a given platform.
    Returns list of releases sorted by published date (newest first).

    Args:
        platform: Target platform (macos, windows, or linux)

    Returns:
        List of dicts containing release and version_info
    """
    # Fetch releases from GitHub
    cache_key = "github_releases_desktop"
    releases = await get_omi_github_releases(cache_key)

    if not releases:
        return []

    # Filter for desktop releases
    desktop_releases = []
    for release in releases:
        # Skip drafts and unpublished releases
        if release.get("draft") or not release.get("published_at"):
            continue

        tag_name = release.get("tag_name", "")

        # Check if it's a desktop release (-desktop-cm, -{platform}-cm, or -desktop-auto)
        if not (
            tag_name.endswith("-desktop-cm")
            or tag_name.endswith(f"-{platform}-cm")
            or tag_name.endswith("-desktop-auto")
        ):
            continue

        # Parse version info
        version_info = _parse_desktop_version(tag_name)
        if not version_info:
            continue

        # Check if release is live (only include live releases)
        kv = extract_key_value_pairs(release.get("body", ""))
        is_live = kv.get("isLive", "false").lower() == "true"
        if not is_live:
            continue

        desktop_releases.append({"release": release, "version_info": version_info, "metadata": kv})

    # Sort by published date (newest first)
    desktop_releases.sort(key=lambda x: x["release"].get("published_at", ""), reverse=True)

    return desktop_releases


def _format_changelog_html(changes: List[Dict[str, str]]) -> str:
    """Format changelog as HTML for Sparkle appcast"""
    if not changes:
        return "<p>Bug fixes and improvements</p>"

    html = "<ul>"
    for change in changes:
        change_type = change.get('type', 'improvement')
        message = change.get('message', '')

        icon = {'feature': '✨', 'fix': '🐛', 'improvement': '⚡', 'breaking': '⚠️'}.get(change_type, '•')

        html += f"<li>{icon} {message}</li>"

    html += "</ul>"
    return html


def _generate_appcast_xml(items: List[Dict], platform: str) -> str:
    """Generate Sparkle 2.0 appcast XML"""
    rss = Element('rss', {'version': '2.0', 'xmlns:sparkle': 'http://www.andymatuschak.org/xml-namespaces/sparkle'})

    channel = SubElement(rss, 'channel')
    SubElement(channel, 'title').text = 'Omi Desktop Updates'
    SubElement(channel, 'description').text = 'Omi AI Desktop Application'
    SubElement(channel, 'language').text = 'en'

    # Add each release
    for release_item in items:
        item = SubElement(channel, 'item')

        version = release_item['version']
        SubElement(item, 'title').text = f"Omi {version}"

        # For macOS, version fields go at item level (not in enclosure)
        SubElement(item, '{http://www.andymatuschak.org/xml-namespaces/sparkle}version').text = str(
            release_item['shortVersion']
        )
        SubElement(item, '{http://www.andymatuschak.org/xml-namespaces/sparkle}shortVersionString').text = version

        # Release notes as HTML (CDATA will be added during serialization)
        description = _format_changelog_html(release_item.get('changes', []))
        desc_elem = SubElement(item, 'description')
        desc_elem.text = description

        SubElement(item, 'pubDate').text = release_item['date']

        # Get download URL from release item
        url = release_item.get('url')
        if not url:
            continue

        # Enclosure with signature and OS
        enclosure_attrs = {
            'url': url,
            'type': 'application/octet-stream',
            '{http://www.andymatuschak.org/xml-namespaces/sparkle}os': platform,
        }

        # Add EdDSA signature if available
        ed_signature = release_item.get('edSignature', '').strip()
        if ed_signature:
            enclosure_attrs['{http://www.andymatuschak.org/xml-namespaces/sparkle}edSignature'] = ed_signature

        enclosure = SubElement(item, 'enclosure', enclosure_attrs)

        # Critical update (optional)
        if release_item.get('mandatory'):
            SubElement(item, '{http://www.andymatuschak.org/xml-namespaces/sparkle}criticalUpdate')

    # Pretty print
    xml_str = tostring(rss, encoding='unicode')
    dom = minidom.parseString(xml_str)
    return dom.toprettyxml(indent='  ')


@router.get("/v2/desktop/appcast.xml")
async def get_desktop_appcast_xml(platform: str = Query(default="macos", regex="^(macos|windows|linux)$")):
    """
    Sparkle appcast XML endpoint for auto_updater package.
    Returns Sparkle 2.0 compatible XML feed for macOS/Windows/Linux updates.

    Args:
        platform: Target platform (macos, windows, or linux)

    Returns:
        XML appcast feed
    """
    try:
        # Get live desktop releases using shared helper
        desktop_releases = await _get_live_desktop_releases(platform)

        if not desktop_releases:
            raise HTTPException(status_code=404, detail=f"No desktop releases found for platform: {platform}")

        # Transform to items format
        items = []

        for entry in desktop_releases:
            release = entry["release"]
            version_info = entry["version_info"]
            kv = entry["metadata"]

            changelog = kv.get("changelog", [])
            mandatory = kv.get("mandatory", "false").lower() == "true"
            ed_signature = kv.get("edSignature", "")  # EdDSA signature for Sparkle

            # Parse changes
            changes = _parse_changelog_to_changes(changelog, release.get("body", ""))

            # Use build number directly for sparkle:version
            short_version = version_info["build"]

            # Get Sparkle ZIP download URL from GitHub release assets
            download_url = _get_sparkle_zip_download_url(release, version_info["version"], platform)

            # Skip if no download URL found
            if not download_url:
                continue

            items.append(
                {
                    "version": version_info["version"],
                    "shortVersion": short_version,
                    "changes": changes,
                    "date": release.get("published_at"),
                    "mandatory": mandatory,
                    "url": download_url,
                    "platform": platform,
                    "edSignature": ed_signature,
                }
            )

        # Generate Sparkle XML
        xml_content = _generate_appcast_xml(items, platform)

        return Response(
            content=xml_content,
            media_type="application/xml",
            headers={"Cache-Control": "max-age=300"},  # Cache for 5 minutes
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating appcast: {str(e)}")


@router.get("/v2/desktop/download/latest")
async def download_latest_desktop_release(platform: str = Query(default="macos", regex="^(macos|windows|linux)$")):
    """
    Get the download URL for the latest desktop release installer.
    Redirects to the GitHub release asset download URL.

    Args:
        platform: Target platform (macos, windows, or linux)

    Returns:
        Redirect to the installer download URL (DMG for macOS, EXE for Windows, AppImage for Linux)
    """
    try:
        # Get live desktop releases using shared helper
        desktop_releases = await _get_live_desktop_releases(platform)

        if not desktop_releases:
            raise HTTPException(status_code=404, detail=f"No live desktop releases found for platform: {platform}")

        # Get the latest release (first in the sorted list)
        latest_entry = desktop_releases[0]
        latest_release = latest_entry["release"]

        # Find the installer asset in the release
        assets = latest_release.get("assets", [])

        # Look for platform-specific installer files
        extension_map = {"macos": ".dmg", "windows": ".exe", "linux": ".AppImage"}
        target_extension = extension_map.get(platform, ".dmg")

        installer_asset = None
        for asset in assets:
            asset_name = asset.get("name", "").lower()
            if asset_name.endswith(target_extension):
                installer_asset = asset
                break

        if not installer_asset:
            raise HTTPException(status_code=404, detail=f"No {target_extension} installer found in the latest release")

        # Get the download URL from the asset
        download_url = installer_asset.get("browser_download_url")
        if not download_url:
            raise HTTPException(status_code=404, detail="Download URL not found")

        # Redirect to the GitHub asset download URL
        from fastapi.responses import RedirectResponse

        return RedirectResponse(url=download_url, status_code=302)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching latest release: {str(e)}")


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
