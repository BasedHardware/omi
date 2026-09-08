"""Bounded OSV API reads and summaries; no package execution or scanning."""

import asyncio
import json
import re
from typing import Any
from urllib.parse import quote, urlsplit

import httpx

from models import QueryPackageRequest

MAX_RESPONSE_BYTES = 2_000_000
MAX_RESULT_CHARS = 20_000
ADVISORY_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")


class OSVError(Exception):
    """A public, non-sensitive error suitable for a chat tool response."""

    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


async def fetch_osv(client: httpx.AsyncClient, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    """Read one OSV page with a deadline and byte limit; never follow redirects."""
    try:
        async with asyncio.timeout(15):
            async with client.stream("POST" if body is not None else "GET", path, json=body) as response:
                if response.status_code == 404:
                    raise OSVError(
                        "OSV did not find this advisory or endpoint. Check the identifier; no safety conclusion can be drawn.",
                        404,
                    )
                if response.status_code == 400:
                    raise OSVError(
                        "OSV rejected the lookup. Check the ecosystem, exact package name/version, or advisory ID.",
                        400,
                    )
                if response.status_code == 429:
                    raise OSVError("OSV is rate limiting requests. Try again later; the lookup was not completed.", 429)
                if response.status_code != 200:
                    raise OSVError("OSV is unavailable or returned an unexpected status. The lookup was not completed.")
                chunks = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(chunks) + len(chunk) > MAX_RESPONSE_BYTES:
                        raise OSVError(
                            "OSV's response exceeded the lookup size limit. No complete result is available."
                        )
                    chunks.extend(chunk)
        data = json.loads(chunks)
    except (TimeoutError, httpx.TimeoutException) as exc:
        raise OSVError("OSV timed out. Try again later; the lookup was not completed.", 504) from exc
    except httpx.HTTPError as exc:
        raise OSVError("Could not reach OSV. Try again later; the lookup was not completed.") from exc
    except (ValueError, UnicodeError) as exc:
        raise OSVError("OSV returned an invalid response. The lookup was not completed.") from exc
    if not isinstance(data, dict) or "error" in data:
        raise OSVError("OSV returned an invalid response. The lookup was not completed.")
    return data


def text(value: object, length: int = 200) -> str:
    if not isinstance(value, str):
        return ""
    value = " ".join(value.split())
    return value if len(value) <= length else value[: length - 1] + "…"


def bounded_result(value: str) -> str:
    suffix = "\n[Output truncated. Follow the OSV source links for complete records.]"
    return value if len(value) <= MAX_RESULT_CHARS else value[: MAX_RESULT_CHARS - len(suffix)] + suffix


def advisory_id(record: object) -> str:
    if not isinstance(record, dict) or not isinstance(record.get("id"), str) or not ADVISORY_ID.fullmatch(record["id"]):
        raise OSVError("OSV returned an invalid advisory record. No complete result is available.")
    return record["id"]


def same_package(affected: dict[str, Any], query: QueryPackageRequest) -> bool:
    package = affected.get("package")
    if not isinstance(package, dict) or package.get("ecosystem") != query.ecosystem:
        return False
    name = package.get("name")
    if not isinstance(name, str):
        return False
    if query.ecosystem == "PyPI":
        return re.sub(r"[-_.]+", "-", name).casefold() == re.sub(r"[-_.]+", "-", query.package_name).casefold()
    if query.ecosystem == "NuGet":
        return name.casefold() == query.package_name.casefold()
    return name == query.package_name


def affected_summary(affected: dict[str, Any]) -> list[str]:
    package = affected.get("package")
    if not isinstance(package, dict):
        return []
    lines = [f"Package: {text(package.get('ecosystem'), 40)} / {text(package.get('name'), 200)}"]
    ranges = affected.get("ranges", [])
    if not isinstance(ranges, list):
        ranges = []
    fixes: list[str] = []
    for affected_range in ranges:
        if not isinstance(affected_range, dict):
            continue
        events = affected_range.get("events", [])
        if not isinstance(events, list):
            continue
        for event in events:
            if isinstance(event, dict) and isinstance(event.get("fixed"), str) and event["fixed"] not in fixes:
                fixes.append(event["fixed"])
    if fixes:
        shown = ", ".join(text(value, 80) for value in fixes[:6])
        lines.append(f"Reported fixed markers: {shown}" + (" (more in source)" if len(fixes) > 6 else ""))
    else:
        lines.append(
            "No fixed marker reported for this package; consult the advisory. This does not mean no fix exists."
        )
    for affected_range in ranges[:2]:
        if not isinstance(affected_range, dict) or not isinstance(affected_range.get("events"), list):
            continue
        event_text = []
        for event in affected_range["events"][:4]:
            if not isinstance(event, dict):
                continue
            for key in ("introduced", "fixed", "last_affected", "limit"):
                if isinstance(event.get(key), str):
                    value = (
                        "beginning of history" if key == "introduced" and event[key] == "0" else text(event[key], 80)
                    )
                    event_text.append(f"{key}: {value}")
        if event_text:
            suffix = " (more events in source)" if len(affected_range["events"]) > 4 else ""
            lines.append(f"Range ({text(affected_range.get('type'), 24)}): " + "; ".join(event_text) + suffix)
    if len(ranges) > 2:
        lines.append("More affected ranges are available in the source.")
    return lines


def format_advisory(record: dict[str, Any], query: QueryPackageRequest | None = None) -> str:
    identifier = advisory_id(record)
    title = text(record.get("summary")) or text(record.get("details")) or "No summary supplied"
    lines = [f"{identifier} — {title}"]
    if record.get("withdrawn"):
        lines.append(f"WITHDRAWN: {text(record['withdrawn'], 80)}. Do not treat this as an active advisory.")
    aliases = record.get("aliases", [])
    if isinstance(aliases, list) and aliases:
        lines.append(
            "Aliases: "
            + ", ".join(text(alias, 100) for alias in aliases[:4])
            + (" (more in source)" if len(aliases) > 4 else "")
        )
    affected = record.get("affected", [])
    if not isinstance(affected, list):
        raise OSVError("OSV returned invalid affected-package data. No complete result is available.")
    selected = [
        entry for entry in affected if isinstance(entry, dict) and (query is None or same_package(entry, query))
    ]
    for entry in selected[:2]:
        lines.extend(affected_summary(entry))
    if len(selected) > 2:
        lines.append("More affected packages are available in the source.")
    if not selected:
        lines.append("No affected-package range was supplied for this lookup; consult the source for fix information.")
    lines.append(f"OSV source: https://osv.dev/vulnerability/{quote(identifier, safe='')}")
    if query is None:
        references = record.get("references", [])
        if isinstance(references, list):
            count = 0
            for reference in references:
                url = reference.get("url") if isinstance(reference, dict) else None
                if not isinstance(url, str) or len(url) > 300:
                    continue
                try:
                    parsed = urlsplit(url)
                except ValueError:
                    continue
                if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
                    continue
                lines.append(f"Reference: {url}")
                count += 1
                if count == 3:
                    break
    return "\n".join(lines)


def format_query(data: dict[str, Any], query: QueryPackageRequest) -> str:
    if "vulns" not in data and any(key != "next_page_token" for key in data):
        raise OSVError("OSV returned an invalid query response. The lookup was not completed.")
    records = data.get("vulns", [])
    if not isinstance(records, list):
        raise OSVError("OSV returned an invalid advisory list. No complete result is available.")
    for record in records:
        advisory_id(record)
    more_pages = bool(data.get("next_page_token"))
    if not records:
        if more_pages:
            return "OSV returned an empty page but indicates more pages. This lookup is incomplete; no safety conclusion can be drawn."
        return (
            f"OSV returned no matching advisory records for {query.ecosystem} / {query.package_name} {query.version}. "
            "OSV does not distinguish an unknown package/version from one with no indexed advisories. "
            "This is not a confirmation that the package exists or is vulnerability-free."
        )
    lines = [
        f"OSV lookup: {query.ecosystem} / {query.package_name} {query.version}",
        f"Received {len(records)} advisory record(s) on this page; showing {min(len(records), query.limit)}. "
        "Records can share CVE/GHSA aliases; this is not a count of unique vulnerabilities.",
        "Fixed markers can belong to different release branches (or be commits for GIT ranges); verify the affected ranges before upgrading.",
    ]
    if more_pages:
        lines.append("OSV reports additional pages that were not fetched. This result is incomplete.")
    lines.extend(format_advisory(record, query) for record in records[: query.limit])
    if len(records) > query.limit:
        lines.append("Additional records were omitted by the requested display limit.")
    return bounded_result("\n\n".join(lines))
