from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import httpx

from models import (
    LaunchDetailsRequest,
    SearchLaunchesRequest,
    UpcomingLaunchesRequest,
    normalize_utc_datetime,
)


BASE_URL = "https://ll.thespacedevs.com/2.3.0"
SOURCE_URL = "https://thespacedevs.com/llapi"
MAX_RESPONSE_BYTES = 5 * 1024 * 1024
MAX_SUMMARY_CHARS = 900


class LaunchLibraryError(Exception):
    """A safe, user-facing Launch Library provider or payload error."""


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _clean_text(value: Any, limit: int = 180) -> str:
    if not isinstance(value, str):
        return ""
    text = " ".join(value.split())
    if len(text) > limit:
        return text[: limit - 3].rstrip() + "..."
    return text


def _format_datetime(value: Any) -> str:
    text = _clean_text(value, 40)
    if not text:
        return "not announced"
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return text
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    parsed = parsed.astimezone(timezone.utc)
    return parsed.strftime("%Y-%m-%d %H:%M UTC")


async def _get_json(
    client: httpx.AsyncClient,
    path: str,
    params: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    try:
        response = await client.get(f"{BASE_URL}{path}", params=params)
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        if status == 404:
            raise LaunchLibraryError("Launch Library 2 launch not found") from exc
        if status == 429:
            raise LaunchLibraryError(
                "Launch Library 2 rate limit reached. Its public free tier "
                "allows 15 requests per hour; try again later."
            ) from exc
        raise LaunchLibraryError(f"Launch Library 2 returned HTTP {status}") from exc
    except httpx.RequestError as exc:
        raise LaunchLibraryError(
            f"Launch Library 2 request failed: {type(exc).__name__}"
        ) from exc

    if len(response.content) > MAX_RESPONSE_BYTES:
        raise LaunchLibraryError("Launch Library 2 response exceeded the size limit")

    try:
        payload = response.json()
    except ValueError as exc:
        raise LaunchLibraryError("Launch Library 2 returned malformed JSON") from exc

    if not isinstance(payload, dict):
        raise LaunchLibraryError(
            "Launch Library 2 returned an unexpected response shape"
        )
    return payload


def _upcoming_params(request: UpcomingLaunchesRequest) -> dict[str, Any]:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    params: dict[str, Any] = {
        "mode": "detailed",
        "limit": request.limit,
        "ordering": "net",
        "net__gt": now.isoformat().replace("+00:00", "Z"),
        "net__lte": (now + timedelta(days=request.days))
        .isoformat()
        .replace("+00:00", "Z"),
    }
    if request.provider:
        params["lsp__name"] = request.provider
    if request.rocket:
        params["rocket__configuration__full_name__icontains"] = request.rocket
    return params


def _search_params(request: SearchLaunchesRequest) -> dict[str, Any]:
    params: dict[str, Any] = {
        "mode": "detailed",
        "limit": request.limit,
        "ordering": "net",
    }
    if request.query:
        params["search"] = request.query
    if request.provider:
        params["lsp__name"] = request.provider
    if request.rocket:
        params["rocket__configuration__full_name__icontains"] = request.rocket
    if request.start_date:
        params["net__gte"] = normalize_utc_datetime(request.start_date)
    if request.end_date:
        params["net__lte"] = normalize_utc_datetime(
            request.end_date,
            end_of_day=len(request.end_date.strip()) == 10,
        )
    return params


def _format_location(pad_value: Any) -> str:
    pad = _as_dict(pad_value)
    location = _as_dict(pad.get("location"))
    location_name = _clean_text(location.get("name"), 140)
    pad_name = _clean_text(pad.get("name"), 100)
    if location_name and pad_name:
        return f"{location_name} - {pad_name}"
    return location_name or pad_name or "location not listed"


def _format_launch_row(value: Any) -> str:
    launch = _as_dict(value)
    status = _as_dict(launch.get("status"))
    provider = _as_dict(launch.get("launch_service_provider"))
    rocket = _as_dict(_as_dict(launch.get("rocket")).get("configuration"))
    mission = _as_dict(launch.get("mission"))

    lines = [
        f"- {_clean_text(launch.get('name'), 180) or 'Unnamed launch'}",
        (
            f"  NET: {_format_datetime(launch.get('net'))}"
            f" | Status: {_clean_text(status.get('name'), 80) or 'unknown'}"
        ),
    ]
    provider_name = _clean_text(provider.get("name"), 120)
    rocket_name = _clean_text(
        rocket.get("full_name") or rocket.get("name"),
        140,
    )
    mission_name = _clean_text(mission.get("name"), 120)
    if provider_name:
        lines.append(f"  Provider: {provider_name}")
    if rocket_name:
        lines.append(f"  Rocket: {rocket_name}")
    if mission_name:
        lines.append(f"  Mission: {mission_name}")
    lines.append(f"  Pad: {_format_location(launch.get('pad'))}")
    return "\n".join(lines)


def _format_launch_details(value: Any) -> str:
    launch = _as_dict(value)
    status = _as_dict(launch.get("status"))
    provider = _as_dict(launch.get("launch_service_provider"))
    rocket = _as_dict(_as_dict(launch.get("rocket")).get("configuration"))
    mission = _as_dict(launch.get("mission"))
    orbit = _as_dict(mission.get("orbit"))

    launch_id = _clean_text(launch.get("id"), 40) or "unknown"
    description = _clean_text(mission.get("description"), MAX_SUMMARY_CHARS)
    lines = [
        f"{_clean_text(launch.get('name'), 220) or 'Unnamed launch'}",
        f"Status: {_clean_text(status.get('name'), 100) or 'unknown'}",
        f"NET: {_format_datetime(launch.get('net'))}",
        (
            "Window: "
            f"{_format_datetime(launch.get('window_start'))} to "
            f"{_format_datetime(launch.get('window_end'))}"
        ),
        ("Provider: " f"{_clean_text(provider.get('name'), 140) or 'not listed'}"),
        (
            "Rocket: "
            f"{_clean_text(rocket.get('full_name') or rocket.get('name'), 160) or 'not listed'}"
        ),
        f"Mission: {_clean_text(mission.get('name'), 160) or 'not listed'}",
        f"Mission type: {_clean_text(mission.get('type'), 100) or 'unknown'}",
        f"Orbit: {_clean_text(orbit.get('name'), 100) or 'not listed'}",
        f"Pad: {_format_location(launch.get('pad'))}",
        f"Last updated: {_format_datetime(launch.get('last_updated'))}",
    ]
    if description:
        lines.append(f"Description: {description}")
    if launch.get("webcast_live") is True:
        lines.append("Webcast: live now")
    lines.append(f"Launch Library ID: {launch_id}")
    lines.append(f"Source: {SOURCE_URL}")
    return "\n".join(lines)


def _results(payload: dict[str, Any]) -> list[Any]:
    results = payload.get("results")
    if results is not None and not isinstance(results, list):
        raise LaunchLibraryError(
            "Launch Library 2 returned an unexpected results payload"
        )
    return _as_list(results)


async def get_upcoming_launches(
    client: httpx.AsyncClient,
    request: UpcomingLaunchesRequest,
) -> str:
    payload = await _get_json(client, "/launches/", _upcoming_params(request))
    launches = _results(payload)
    if not launches:
        return (
            "No upcoming Launch Library 2 launches matched the request. "
            "Try a wider date range or remove the provider or rocket filter. "
            f"Source: {SOURCE_URL}"
        )

    total = payload.get("count")
    if not isinstance(total, int):
        total = len(launches)
    lines = [
        f"Found {total} upcoming launches; showing {len(launches)}.",
        *(_format_launch_row(item) for item in launches),
        ("Source: Launch Library 2 by The Space Devs. " "Launch schedules can change."),
    ]
    return "\n".join(lines)


async def search_launches(
    client: httpx.AsyncClient,
    request: SearchLaunchesRequest,
) -> str:
    payload = await _get_json(client, "/launches/", _search_params(request))
    launches = _results(payload)
    if not launches:
        return (
            "No Launch Library 2 launches matched the search. " f"Source: {SOURCE_URL}"
        )

    total = payload.get("count")
    if not isinstance(total, int):
        total = len(launches)
    lines = [
        f"Found {total} matching launches; showing {len(launches)}.",
        *(_format_launch_row(item) for item in launches),
        "Source: Launch Library 2 by The Space Devs.",
    ]
    return "\n".join(lines)


async def get_launch(
    client: httpx.AsyncClient,
    request: LaunchDetailsRequest,
) -> str:
    payload = await _get_json(
        client,
        f"/launches/{request.launch_id}/",
        {"mode": "detailed"},
    )
    if not payload.get("id"):
        raise LaunchLibraryError("Launch Library 2 returned no launch data")
    return _format_launch_details(payload)
