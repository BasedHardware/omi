"""Catalog-driven release selection and Sparkle feeds for public micro-apps.

The catalog is intentionally the only product-specific surface in this module.  A
new micro-app should add one entry with its release tag and asset conventions;
the provider, channel filtering, and XML generation remain shared.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import format_datetime, parsedate_to_datetime
from html import escape
import re
from typing import Any

from utils.github_releases import extract_key_value_pairs, get_omi_github_releases

SPARKLE_NAMESPACE = "http://www.andymatuschak.org/xml-namespaces/sparkle"
MICRO_APP_FEED_CACHE_CONTROL = "public, max-age=300"
_VERSION_PATTERN = re.compile(r"^(?P<core>\d+\.\d+(?:\.\d+)?)(?P<qualifier>[-+][0-9A-Za-z.-]+)?$")
_BUILD_PATTERN = re.compile(r"^\d+(?:\.\d+)*$")
_XML_INVALID_CHARACTERS = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F\uD800-\uDFFF\uFFFE\uFFFF]")


@dataclass(frozen=True)
class MicroAppConfig:
    """Release identity and presentation metadata for one public micro-app."""

    app_id: str
    title: str
    description: str
    repository: str
    github_cache_key: str
    tag_prefix: str
    asset_pattern: re.Pattern[str]
    minimum_system_version: str
    release_notes_fallback: str = "Bug fixes and improvements."

    @property
    def tag_pattern(self) -> re.Pattern[str]:
        return re.compile(rf"^{re.escape(self.tag_prefix)}\d+\.\d+(?:\.\d+)?(?:[-+][0-9A-Za-z.-]+)?$")


CONTEXT_FOR_CLAUDE = MicroAppConfig(
    app_id="context-for-claude",
    title="Context for Claude",
    description="Updates for Context for Claude.",
    repository="BasedHardware/omi",
    github_cache_key="github_releases_micro_app_context_for_claude",
    tag_prefix="context-for-claude-v",
    asset_pattern=re.compile(r"^ContextForClaude[^/]*\.zip$"),
    minimum_system_version="14.4",
    release_notes_fallback="Bug fixes and improvements.",
)

# Adding another product should be a single catalog entry.  In particular, do
# not broaden this registry with the Omi Desktop identity: desktop appcasts
# have a separate route and must never be a fallback for a micro-app feed.
MICRO_APP_CATALOG: Mapping[str, MicroAppConfig] = {
    CONTEXT_FOR_CLAUDE.app_id: CONTEXT_FOR_CLAUDE,
}

MicroAppRelease = Mapping[str, Any]
MicroAppReleaseProvider = Callable[[MicroAppConfig], Awaitable[Sequence[MicroAppRelease] | None]]


class UnknownMicroAppError(ValueError):
    """Raised when a request names no registered public micro-app."""


class MicroAppReleaseProviderError(RuntimeError):
    """Raised when the upstream release provider cannot return a snapshot."""


def get_micro_app_config(app_id: str) -> MicroAppConfig:
    """Return the registered config, or fail closed for an unknown app ID."""
    config = MICRO_APP_CATALOG.get(app_id)
    if config is None:
        raise UnknownMicroAppError(app_id)
    return config


async def fetch_micro_app_releases(config: MicroAppConfig) -> Sequence[MicroAppRelease] | None:
    """Fetch releases using the existing cached GitHub repository utility.

    The utility currently targets the Omi repository, which is also where the
    micro-app release tags live.  The tag filter is repeated during transform
    so an accidental provider broadening cannot leak another product's release.
    """
    return await get_omi_github_releases(config.github_cache_key, tag_filter=config.tag_pattern)


def _xml_safe(value: Any) -> str:
    """Remove XML 1.0-invalid characters before escaping a value."""
    text = "" if value is None else str(value)
    return _XML_INVALID_CHARACTERS.sub("", text)


def _metadata(release: MicroAppRelease) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    direct_metadata = release.get("metadata")
    if isinstance(direct_metadata, Mapping):
        metadata.update(direct_metadata)
    body = release.get("body")
    if isinstance(body, str):
        metadata.update(extract_key_value_pairs(body))
    for key in ("build", "build_number", "sparkleVersion", "sparkle_version", "channel"):
        if key in release and release.get(key) is not None:
            metadata[key] = release[key]
    return metadata


def _tag_version(config: MicroAppConfig, release: MicroAppRelease) -> str | None:
    tag_name = release.get("tag_name")
    if not isinstance(tag_name, str) or config.tag_pattern.fullmatch(tag_name) is None:
        return None
    version = tag_name[len(config.tag_prefix) :]
    return version if _VERSION_PATTERN.fullmatch(version) else None


def _is_truthy(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes"}
    return bool(value)


def _is_beta_release(config: MicroAppConfig, release: MicroAppRelease, metadata: Mapping[str, Any]) -> bool:
    version = _tag_version(config, release) or ""
    version_match = _VERSION_PATTERN.fullmatch(version)
    release_channel = str(metadata.get("channel", release.get("channel", ""))).strip().lower()
    qualifier = (version_match.group("qualifier") or "") if version_match else ""
    return (
        _is_truthy(release.get("prerelease")) or release_channel in {"beta", "prerelease"} or qualifier.startswith("-")
    )


def _release_signature(release: MicroAppRelease, metadata: Mapping[str, Any]) -> str:
    for key in ("edSignature", "ed_signature", "signature"):
        value = release.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    for key in ("edSignature", "ed_signature", "signature"):
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _release_asset(config: MicroAppConfig, release: MicroAppRelease) -> tuple[str, str] | None:
    assets = release.get("assets")
    if not isinstance(assets, Sequence) or isinstance(assets, (str, bytes, bytearray)):
        return None
    for asset in assets:
        if not isinstance(asset, Mapping):
            continue
        name = asset.get("name")
        url = asset.get("browser_download_url")
        if not isinstance(name, str) or config.asset_pattern.fullmatch(name) is None:
            continue
        if not isinstance(url, str) or not url.strip() or not url.startswith("https://"):
            continue
        return name, url.strip()
    return None


def _release_version_and_build(
    config: MicroAppConfig, release: MicroAppRelease, metadata: Mapping[str, Any]
) -> tuple[str, str] | None:
    version = _tag_version(config, release)
    if version is None:
        return None
    match = _VERSION_PATTERN.fullmatch(version)
    if match is None:
        return None

    build = ""
    for key in ("build", "build_number", "sparkleVersion", "sparkle_version"):
        value = metadata.get(key, release.get(key))
        if value is not None and str(value).strip():
            build = str(value).strip()
            break
    if not build:
        qualifier = match.group("qualifier") or ""
        if qualifier.startswith("+") and qualifier[1:].isdigit():
            build = qualifier[1:]
        else:
            # A tag without an explicit build still has a valid numeric
            # CFBundleVersion.  Beta identity is isolated by the feed/channel,
            # so its numeric build may share the stable core version.
            build = match.group("core")
    if not _BUILD_PATTERN.fullmatch(build):
        return None
    return version, build


def _format_pub_date(value: Any) -> str:
    """Normalize GitHub ISO timestamps to RSS/RFC 2822 when possible."""
    raw = _xml_safe(value).strip()
    if not raw:
        return ""
    parsed: datetime | None = None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = parsedate_to_datetime(raw)
        except (TypeError, ValueError):
            pass
    if parsed is None:
        return raw
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return format_datetime(parsed.astimezone(timezone.utc), usegmt=True)


def _release_notes_html(config: MicroAppConfig, release: MicroAppRelease) -> str:
    notes = release.get("release_notes")
    if not isinstance(notes, str) or not notes.strip():
        notes = release.get("body")
    if not isinstance(notes, str) or not notes.strip():
        notes = config.release_notes_fallback
    escaped_notes = escape(_xml_safe(notes.strip()), quote=False).replace("\r\n", "\n").replace("\n", "<br />")
    return f"<p>{escaped_notes}</p>"


def _release_title(config: MicroAppConfig, release: MicroAppRelease, version: str) -> str:
    release_name = release.get("name") or release.get("title")
    if isinstance(release_name, str) and release_name.strip() and release_name.strip() != release.get("tag_name"):
        return release_name.strip()
    return f"{config.title} {version}"


def _as_cdata(value: str) -> str:
    return value.replace("]]>", "]]]]><![CDATA[>")


def generate_micro_app_appcast(config: MicroAppConfig, items: Sequence[Mapping[str, Any]]) -> str:
    """Render a Sparkle 2 appcast; an empty item list is a valid empty feed."""
    lines = [
        '<?xml version="1.0" encoding="utf-8"?>',
        f'<rss version="2.0" xmlns:sparkle="{SPARKLE_NAMESPACE}">',
        "  <channel>",
        f"    <title>{escape(_xml_safe(config.title))} Updates</title>",
        f"    <description>{escape(_xml_safe(config.description))}</description>",
        "    <language>en</language>",
    ]
    for item in items:
        title = escape(_xml_safe(item.get("title", "")))
        version = escape(_xml_safe(item.get("version", "")))
        build = escape(_xml_safe(item.get("build", "")))
        notes = _as_cdata(str(item.get("notes_html", "")))
        pub_date = escape(_xml_safe(item.get("pub_date", "")))
        url = escape(_xml_safe(item.get("url", "")), quote=True)
        signature = escape(_xml_safe(item.get("ed_signature", "")), quote=True)
        release_notes_url = item.get("release_notes_url")

        lines.extend(
            [
                "    <item>",
                f"      <title>{title}</title>",
                f"      <sparkle:version>{build}</sparkle:version>",
                f"      <sparkle:shortVersionString>{version}</sparkle:shortVersionString>",
                f"      <description><![CDATA[{notes}]]></description>",
                f"      <pubDate>{pub_date}</pubDate>",
                f'      <enclosure url="{url}" type="application/octet-stream" sparkle:os="macos" sparkle:edSignature="{signature}" sparkle:minimumSystemVersion="{escape(_xml_safe(config.minimum_system_version), quote=True)}" />',
            ]
        )
        if isinstance(release_notes_url, str) and release_notes_url.strip():
            lines.append(
                f"      <sparkle:releaseNotesLink>{escape(_xml_safe(release_notes_url.strip()))}</sparkle:releaseNotesLink>"
            )
        if item.get("channel") == "beta":
            lines.append("      <sparkle:channel>beta</sparkle:channel>")
        lines.append("    </item>")
    lines.extend(["  </channel>", "</rss>"])
    return "\n".join(lines)


def _release_to_item(config: MicroAppConfig, release: MicroAppRelease, channel: str) -> dict[str, Any] | None:
    if _tag_version(config, release) is None:
        return None
    if _is_truthy(release.get("draft")):
        return None

    metadata = _metadata(release)
    is_beta = _is_beta_release(config, release, metadata)
    if channel == "stable" and is_beta:
        return None
    if channel == "beta" and not is_beta:
        return None

    asset = _release_asset(config, release)
    signature = _release_signature(release, metadata)
    version_and_build = _release_version_and_build(config, release, metadata)
    published_at = release.get("published_at") or release.get("created_at")
    if asset is None or not signature or version_and_build is None or not published_at:
        return None

    version, build = version_and_build
    release_notes_url = release.get("html_url") or release.get("release_notes_url")
    return {
        "title": _release_title(config, release, version),
        "version": version,
        "build": build,
        "notes_html": _release_notes_html(config, release),
        "pub_date": _format_pub_date(published_at),
        "url": asset[1],
        "ed_signature": signature,
        "release_notes_url": release_notes_url,
        "channel": channel,
        "published_at_sort": _xml_safe(published_at),
    }


async def build_micro_app_appcast(
    app_id: str,
    channel: str,
    provider: MicroAppReleaseProvider | None = None,
) -> str:
    """Fetch, filter, and render one app's channel feed.

    No eligible release is intentionally represented by HTTP callers as a
    valid empty RSS feed.  Sparkle can then treat a newly registered product or
    a release missing its signed artifact as "no update" rather than as an
    outage.  Provider exceptions are distinct and become a 503 at the router.
    """
    if channel not in {"stable", "beta"}:
        raise ValueError("channel must be stable or beta")
    config = get_micro_app_config(app_id)
    release_provider = provider or fetch_micro_app_releases
    try:
        releases = await release_provider(config)
    except Exception as exc:
        raise MicroAppReleaseProviderError from exc

    items: list[dict[str, Any]] = []
    seen_tags: set[str] = set()
    for release in releases or []:
        tag_name = release.get("tag_name")
        if isinstance(tag_name, str) and tag_name in seen_tags:
            continue
        item = _release_to_item(config, release, channel)
        if item is None:
            continue
        if isinstance(tag_name, str):
            seen_tags.add(tag_name)
        items.append(item)

    items.sort(key=lambda item: item.get("published_at_sort", ""), reverse=True)
    return generate_micro_app_appcast(config, items)
