import os
import re
from typing import Optional, List, Dict
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom import minidom

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from routers.firmware import get_omi_github_releases, extract_key_value_pairs


router = APIRouter()


def _parse_desktop_version(tag_name: str) -> Optional[Dict[str, str]]:
    """
    Parse desktop version from tag name.
    Expected format: v1.0.77+464-desktop-cm or v1.0.77+464-macos-cm
    Returns dict with version info or None if invalid.
    """
    # Match pattern: v{major}.{minor}.{patch}+{build}-{platform}-cm
    pattern = r'^v?(\d+)\.(\d+)\.(\d+)\+(\d+)-(?:desktop|macos|windows|linux)-cm$'
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


def _calculate_short_version(major: str, minor: str, patch: str, build: str) -> int:
    """
    Calculate numeric short version for desktop_updater comparison.
    Format: major * 10000000 + minor * 100000 + patch * 1000 + build
    Example: 1.0.77+464 -> 10077464
    """
    try:
        return int(major) * 10000000 + int(minor) * 100000 + int(patch) * 1000 + int(build)
    except (ValueError, TypeError):
        return 0


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


def _get_gcs_bucket_url() -> str:
    """
    Get the GCS bucket URL for desktop updates.
    Can be configured via environment variable or use default.
    """
    return os.getenv('DESKTOP_UPDATES_GCS_BUCKET', 'https://storage.googleapis.com/omi_macos_updates')


@router.get("/v2/desktop/app-archive.json")
async def get_desktop_updates(platform: str = Query(default="macos", regex="^(macos|windows|linux)$")):
    """
    Desktop updater endpoint for macOS/Windows/Linux updates.
    Returns app-archive.json format expected by desktop_updater package.

    Fetches releases from GitHub with tag pattern: *-desktop-cm
    Returns versions hosted on Google Cloud Storage.

    Args:
        platform: Target platform (macos, windows, or linux)

    Returns:
        JSON object with appName, description, and items array
    """
    # Fetch GitHub releases with caching
    cache_key = "github_releases_desktop"
    releases = await get_omi_github_releases(cache_key)

    if not releases:
        raise HTTPException(status_code=404, detail="No releases found")

    # Filter for desktop releases
    desktop_releases = []
    for release in releases:
        # Skip drafts and unpublished releases
        if release.get("draft") or not release.get("published_at"):
            continue

        tag_name = release.get("tag_name", "")

        # Check if it's a desktop release
        if not tag_name.endswith("-desktop-cm") and not tag_name.endswith(f"-{platform}-cm"):
            continue

        # Parse version info
        version_info = _parse_desktop_version(tag_name)
        if not version_info:
            continue

        desktop_releases.append({"release": release, "version_info": version_info})

    if not desktop_releases:
        raise HTTPException(status_code=404, detail=f"No desktop releases found for platform: {platform}")

    # Sort by published date (newest first)
    desktop_releases.sort(key=lambda x: x["release"].get("published_at", ""), reverse=True)

    # Transform to desktop_updater format
    gcs_bucket_url = _get_gcs_bucket_url()
    items = []

    for entry in desktop_releases:
        release = entry["release"]
        version_info = entry["version_info"]

        # Extract metadata from release body
        kv = extract_key_value_pairs(release.get("body", ""))
        changelog = kv.get("changelog", [])
        mandatory = kv.get("mandatory", "false").lower() == "true"

        # Parse changes
        changes = _parse_changelog_to_changes(changelog, release.get("body", ""))

        # Calculate short version
        short_version = _calculate_short_version(
            version_info["major"], version_info["minor"], version_info["patch"], version_info["build"]
        )

        # Construct GCS URL for the release folder
        folder_name = f"{version_info['version']}-{platform}"
        url = f"{gcs_bucket_url}/{folder_name}/"

        items.append(
            {
                "version": version_info["version"],
                "shortVersion": short_version,
                "changes": changes,
                "date": release.get("published_at"),
                "mandatory": mandatory,
                "url": url,
                "platform": platform,
            }
        )

    return {"appName": "Omi", "description": "Omi AI Desktop Application", "items": items}


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

        # Release notes as HTML
        description = _format_changelog_html(release_item.get('changes', []))
        desc_elem = SubElement(item, 'description')
        desc_elem.text = f'<![CDATA[{description}]]>'

        SubElement(item, 'pubDate').text = release_item['date']

        # Download URL - point to GCS ZIP file
        gcs_base = release_item['url']  # e.g., https://storage.googleapis.com/omi_macos_updates/1.0.78+471-macos/
        download_url = f"{gcs_base}{version}-{platform}.zip"

        enclosure_attrs = {
            'url': download_url,
            'sparkle:version': str(release_item['shortVersion']),
            'sparkle:shortVersionString': version,
            'type': 'application/octet-stream',
        }

        # Add EdDSA signature if available
        ed_signature = release_item.get('edSignature', '').strip()
        if ed_signature:
            enclosure_attrs['sparkle:edSignature'] = ed_signature

        enclosure = SubElement(item, 'enclosure', enclosure_attrs)

        # Critical update (optional)
        if release_item.get('mandatory'):
            SubElement(item, 'sparkle:criticalUpdate')

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
        # Reuse existing release fetching logic
        cache_key = "github_releases_desktop"
        releases = await get_omi_github_releases(cache_key)

        if not releases:
            raise HTTPException(status_code=404, detail="No releases found")

        # Filter for desktop releases
        desktop_releases = []
        for release in releases:
            # Skip drafts and unpublished releases
            if release.get("draft") or not release.get("published_at"):
                continue

            tag_name = release.get("tag_name", "")

            # Check if it's a desktop release
            if not tag_name.endswith("-desktop-cm") and not tag_name.endswith(f"-{platform}-cm"):
                continue

            # Parse version info
            version_info = _parse_desktop_version(tag_name)
            if not version_info:
                continue

            desktop_releases.append({"release": release, "version_info": version_info})

        if not desktop_releases:
            raise HTTPException(status_code=404, detail=f"No desktop releases found for platform: {platform}")

        # Sort by published date (newest first)
        desktop_releases.sort(key=lambda x: x["release"].get("published_at", ""), reverse=True)

        # Transform to items format (reuse logic from get_desktop_updates)
        gcs_bucket_url = _get_gcs_bucket_url()
        items = []

        for entry in desktop_releases:
            release = entry["release"]
            version_info = entry["version_info"]

            # Extract metadata from release body
            kv = extract_key_value_pairs(release.get("body", ""))
            changelog = kv.get("changelog", [])
            mandatory = kv.get("mandatory", "false").lower() == "true"
            ed_signature = kv.get("edSignature", "")  # EdDSA signature for Sparkle

            # Parse changes
            changes = _parse_changelog_to_changes(changelog, release.get("body", ""))

            # Calculate short version
            short_version = _calculate_short_version(
                version_info["major"], version_info["minor"], version_info["patch"], version_info["build"]
            )

            # Construct GCS URL for the release folder
            folder_name = f"{version_info['version']}-{platform}"
            url = f"{gcs_bucket_url}/{folder_name}/"

            items.append(
                {
                    "version": version_info["version"],
                    "shortVersion": short_version,
                    "changes": changes,
                    "date": release.get("published_at"),
                    "mandatory": mandatory,
                    "url": url,
                    "platform": platform,
                    "edSignature": ed_signature,  # Include signature
                }
            )

        # Generate Sparkle XML
        xml_content = _generate_appcast_xml(items, platform)

        return Response(
            content=xml_content,
            media_type="application/xml",
            headers={"Cache-Control": "max-age=1800"},  # Cache for 30 minutes
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating appcast: {str(e)}")
