#!/usr/bin/env python3
"""Prove production serves the Windows electron-updater feed resolver.

Windows clients since #10610 call ``/v2/desktop/update-feed/windows`` before every
update check and fail closed when that route is missing. Shipping another
Windows build while production still 404s the route (OpenAPI/route absence, not
an empty channel) permanently breaks auto-update for that cohort.

This probe is the release-lane guard for that contract. It validates the same
trust boundary the desktop client enforces: GitHub origin, Windows release
directory path, and stable-channel non-fallthrough.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable

DEFAULT_API_BASE = "https://api.omi.me"
DEFAULT_TIMEOUT_SECONDS = 20
CHANNELS = ("beta", "stable")
WINDOWS_FEED_PATH = re.compile(
    r"^/BasedHardware/omi/releases/download/v?\d+\.\d+(?:\.\d+)?(?:\+\d+)?-windows/$"
)
Fetcher = Callable[[str], tuple[int, object]]


class ProbeError(RuntimeError):
    """Production Windows update-feed probe failed."""


def _require_object(payload: object, *, stage: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ProbeError(f"{stage}: expected a JSON object, got {type(payload).__name__}")
    return payload


def validate_feed_response(payload: object, *, requested_channel: str) -> dict[str, str]:
    """Validate one successful update-feed JSON body against the client contract."""
    if requested_channel not in CHANNELS:
        raise ProbeError(f"requested channel must be beta or stable, got {requested_channel!r}")

    response = _require_object(payload, stage="update-feed")
    if response.get("requested_channel") != requested_channel:
        raise ProbeError(
            "update-feed: requested_channel mismatch "
            f"(expected {requested_channel!r}, got {response.get('requested_channel')!r})"
        )

    served = response.get("served_channel")
    if served not in CHANNELS:
        raise ProbeError(f"update-feed: invalid served_channel {served!r}")
    if requested_channel == "stable" and served != "stable":
        raise ProbeError("update-feed: stable must never fall through to beta")

    version = response.get("version")
    if not isinstance(version, str) or not version.strip():
        raise ProbeError(f"update-feed: missing version, got {version!r}")

    feed_url = response.get("feed_url")
    if not isinstance(feed_url, str):
        raise ProbeError(f"update-feed: missing feed_url, got {feed_url!r}")

    try:
        parsed = urllib.parse.urlparse(feed_url)
    except ValueError as exc:
        raise ProbeError(f"update-feed: invalid feed_url {feed_url!r}") from exc

    if (
        parsed.scheme != "https"
        or parsed.netloc != "github.com"
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or not WINDOWS_FEED_PATH.fullmatch(parsed.path)
    ):
        raise ProbeError(f"update-feed: untrusted feed_url {feed_url!r}")

    return {
        "requested_channel": requested_channel,
        "served_channel": served,
        "version": version,
        "feed_url": feed_url,
    }


def classify_http_failure(status: int, payload: object) -> str:
    """Turn a non-2xx response into a deploy-actionable error message."""
    detail = None
    if isinstance(payload, dict):
        raw = payload.get("detail")
        if isinstance(raw, str):
            detail = raw

    if status == 404 and detail in (None, "Not Found"):
        return (
            "production is missing /v2/desktop/update-feed/windows "
            "(deploy backend commit that includes #10610 before cutting a Windows release)"
        )
    if status == 404:
        return f"update-feed returned 404: {detail}"
    if detail:
        return f"update-feed returned HTTP {status}: {detail}"
    return f"update-feed returned HTTP {status}"


def _default_fetch(url: str, *, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> tuple[int, object]:
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "omi-windows-update-feed-probe"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed api.omi.me root
            body = response.read()
            status = int(getattr(response, "status", 200) or 200)
    except urllib.error.HTTPError as exc:
        body = exc.read()
        status = int(exc.code)
    except urllib.error.URLError as exc:
        raise ProbeError(f"update-feed request failed: {exc.reason}") from exc

    if not body:
        return status, None
    try:
        return status, json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProbeError(f"update-feed returned non-JSON body (HTTP {status})") from exc


def probe_channel(
    api_base: str,
    channel: str,
    *,
    fetch: Fetcher | None = None,
) -> dict[str, str]:
    base = api_base.rstrip("/")
    url = f"{base}/v2/desktop/update-feed/windows?channel={urllib.parse.quote(channel)}"
    fetcher = fetch or _default_fetch
    status, payload = fetcher(url)
    if status != 200:
        raise ProbeError(classify_http_failure(status, payload))
    return validate_feed_response(payload, requested_channel=channel)


def probe(
    api_base: str = DEFAULT_API_BASE,
    *,
    channels: tuple[str, ...] = ("beta",),
    fetch: Fetcher | None = None,
) -> list[dict[str, str]]:
    if not channels:
        raise ProbeError("at least one channel is required")
    results: list[dict[str, str]] = []
    for channel in channels:
        results.append(probe_channel(api_base, channel, fetch=fetch))
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--api-base",
        default=DEFAULT_API_BASE,
        help=f"Backend origin (default: {DEFAULT_API_BASE})",
    )
    parser.add_argument(
        "--channel",
        action="append",
        choices=list(CHANNELS),
        dest="channels",
        help="Channel to probe (repeatable). Default: beta only — the auto-cut release channel.",
    )
    args = parser.parse_args(argv)
    channels = tuple(args.channels) if args.channels else ("beta",)
    try:
        results = probe(args.api_base, channels=channels)
    except ProbeError as exc:
        print(f"Windows update-feed probe FAILED: {exc}", file=sys.stderr)
        return 1

    for result in results:
        print(
            "Windows update-feed probe OK: "
            f"requested={result['requested_channel']} "
            f"served={result['served_channel']} "
            f"version={result['version']} "
            f"feed_url={result['feed_url']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
