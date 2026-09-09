"""Read-only TVMaze tools; transport and handlers use only the standard library."""

import json
import socket
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

API_BASE = "https://api.tvmaze.com"
MAX_RESPONSE_BYTES = 1024 * 1024
ATTRIBUTION = "Source: TVMaze (https://www.tvmaze.com), CC BY-SA. Schedules may change."


class ProviderError(Exception):
    """A bounded, user-readable provider failure."""


def _request(path, params):
    request = Request(
        f"{API_BASE}{path}?{urlencode(params)}",
        headers={"User-Agent": "Omi-TVmaze/1.0 (+https://github.com/BasedHardware/omi)", "Accept": "application/json"},
    )
    try:
        with urlopen(request, timeout=10) as response:
            body = response.read(MAX_RESPONSE_BYTES + 1)
        if len(body) > MAX_RESPONSE_BYTES:
            raise ProviderError("TVMaze returned an unexpectedly large response. Please try again later.")
        return json.loads(body)
    except HTTPError as exc:
        exc.close()
        if exc.code == 404:
            raise ProviderError("TVMaze could not find that show ID. Search for the show again.") from exc
        if exc.code == 429:
            raise ProviderError(
                "TVMaze is temporarily rate limiting requests. Please try again in a few seconds."
            ) from exc
        raise ProviderError("TVMaze is temporarily unavailable. Please try again later.") from exc
    except (URLError, socket.timeout, TimeoutError, OSError) as exc:
        raise ProviderError("Could not reach TVMaze. Please try again later.") from exc
    except (ValueError, UnicodeError) as exc:
        raise ProviderError("TVMaze returned an unreadable response. Please try again later.") from exc


def _positive_int(value, field, maximum=None):
    if isinstance(value, bool) or not isinstance(value, int) or value < 1 or (maximum and value > maximum):
        suffix = f" between 1 and {maximum}" if maximum else " greater than zero"
        raise ValueError(f"{field} must be an integer{suffix}.")
    return value


def _show_identity(show):
    if not isinstance(show, dict) or not isinstance(show.get("name"), str):
        raise ProviderError("TVMaze returned incomplete show information. Please try again later.")
    show_id = show.get("id")
    if isinstance(show_id, bool) or not isinstance(show_id, int) or show_id < 1:
        raise ProviderError("TVMaze returned incomplete show information. Please try again later.")
    return show_id, show["name"]


def _channel(show):
    channel = show.get("network") or show.get("webChannel") or {}
    if not isinstance(channel, dict):
        return "Channel not listed"
    country = channel.get("country") or {}
    country_name = country.get("name") if isinstance(country, dict) else None
    return str(channel.get("name") or "Channel not listed") + (f" ({country_name})" if country_name else "")


def search_tv_shows(payload):
    """Return distinct candidate IDs instead of guessing between same-name shows."""
    try:
        query = payload.get("query")
        if not isinstance(query, str) or not 1 <= len(query.strip()) <= 100:
            raise ValueError("query must contain 1 to 100 characters.")
        limit = _positive_int(payload.get("limit", 5), "limit", 10)
        data = _request("/search/shows", {"q": query.strip()})
        if not isinstance(data, list):
            raise ProviderError("TVMaze returned an unexpected search response. Please try again later.")
        if not data:
            return {"result": f"No matching shows found. Try another spelling.\n\n{ATTRIBUTION}"}
        lines = [f"Showing {min(limit, len(data))} of {len(data)} TVMaze matches; use the show ID for episode details."]
        for item in data[:limit]:
            show = item.get("show") if isinstance(item, dict) else None
            show_id, name = _show_identity(show)
            lines.append(
                f"\n{name} — ID {show_id}\n"
                f"Premiered: {show.get('premiered') or 'not listed'} | {_channel(show)}\n"
                f"Status: {show.get('status') or 'not listed'}\nhttps://www.tvmaze.com/shows/{show_id}"
            )
        return {"result": "\n".join(lines) + f"\n\n{ATTRIBUTION}"}
    except (ValueError, ProviderError) as exc:
        return {"error": str(exc)}


def get_tv_show(payload):
    """Retrieve metadata and the explicitly announced next episode, when present."""
    try:
        show_id = _positive_int(payload.get("show_id"), "show_id")
        data = _request(f"/shows/{show_id}", {"embed": "nextepisode"})
        returned_id, name = _show_identity(data)
        if returned_id != show_id:
            raise ProviderError("TVMaze returned a different show ID. Please try again later.")
        lines = [name, f"Status: {data.get('status') or 'not listed'} | {_channel(data)}"]
        embedded = data.get("_embedded") or {}
        if not isinstance(embedded, dict):
            raise ProviderError("TVMaze returned unexpected episode information. Please try again later.")
        episode = embedded.get("nextepisode")
        if episode is None:
            lines.append(
                "No next episode is currently listed by TVMaze. This does not by itself mean the show is cancelled."
            )
        elif not isinstance(episode, dict):
            raise ProviderError("TVMaze returned unexpected episode information. Please try again later.")
        else:
            season, number = episode.get("season"), episode.get("number")
            label = (
                f"Season {season}, episode {number}" if season is not None and number is not None else "Next episode"
            )
            lines.append(f"{label}: {episode.get('name') or 'title not announced'}")
            if episode.get("airstamp"):
                try:
                    timestamp = datetime.fromisoformat(episode["airstamp"].replace("Z", "+00:00"))
                    if timestamp.utcoffset() is None:
                        raise ValueError("No UTC offset")
                except (AttributeError, TypeError, ValueError) as exc:
                    raise ProviderError("TVMaze returned an invalid or timezone-free episode timestamp.") from exc
                lines.append(
                    f"Announced airtime (offset included, not converted to your timezone): {episode['airstamp']}"
                )
            elif episode.get("airdate"):
                lines.append(f"Announced airdate: {episode['airdate']}; exact timestamp not supplied.")
            else:
                lines.append("Airdate not announced.")
        lines.extend([f"https://www.tvmaze.com/shows/{show_id}", "", ATTRIBUTION])
        return {"result": "\n".join(lines)}
    except (ValueError, ProviderError) as exc:
        return {"error": str(exc)}


TOOLS = [
    {
        "name": "search_tv_shows",
        "description": "Find TV shows by name. Returns distinct show IDs, premiere dates and channels so same-name shows are not confused. Use before get_tv_show when the ID is unknown.",
        "endpoint": "/tools/search_tv_shows",
        "method": "POST",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "minLength": 1, "maxLength": 100, "description": "TV show name."},
                "limit": {"type": "integer", "minimum": 1, "maximum": 10, "default": 5},
            },
            "required": ["query"],
        },
        "auth_required": False,
        "status_message": "Searching TV shows...",
    },
    {
        "name": "get_tv_show",
        "description": "Get a specific TV show's status, channel and next announced episode from its TVMaze ID. An absent next episode is not evidence of cancellation. Air timestamps preserve their provider offset; they are not converted to the user's timezone.",
        "endpoint": "/tools/get_tv_show",
        "method": "POST",
        "parameters": {
            "type": "object",
            "properties": {
                "show_id": {"type": "integer", "minimum": 1, "description": "Exact ID returned by search_tv_shows."}
            },
            "required": ["show_id"],
        },
        "auth_required": False,
        "status_message": "Looking up the next episode...",
    },
]
