"""Public iNaturalist tool behavior and bounded HTTP access; stdlib only."""

import asyncio
from collections import OrderedDict, deque
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from http.client import HTTPException
import json
import math
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener


API_ORIGIN = "https://api.inaturalist.org/v1"
MAX_RESPONSE_BYTES = 1_048_576
CONTEXT_FIELDS = {"uid", "app_id", "tool_name", "geolocation"}


class ToolError(Exception):
    """A public, non-sensitive diagnostic suitable for the Omi tool response."""


def integer(description, minimum=1, maximum=2_147_483_647, default=None):
    schema = {"type": "integer", "description": description, "minimum": minimum, "maximum": maximum}
    if default is not None:
        schema["default"] = default
    return schema


QUERY = {
    "type": "string",
    "minLength": 1,
    "maxLength": 100,
    "description": "Name to search; ambiguous matches remain separate.",
}
LIMIT = integer("Maximum results to return.", maximum=10, default=5)
TOOL_SPECS = {
    "search_inaturalist_taxa": (
        "Search common or scientific names. Return matching taxon IDs and ranks; use an exact ID for details.",
        {"query": QUERY, "limit": LIMIT},
        ["query"],
    ),
    "get_inaturalist_taxon": (
        "Look up an exact iNaturalist taxon ID, its rank and taxonomy. Does not identify a photo or confirm edibility.",
        {"taxon_id": integer("Taxon ID returned by search.")},
        ["taxon_id"],
    ),
    "search_inaturalist_places": (
        "Find iNaturalist place IDs by name; choose the intended full place name before requesting observed taxa.",
        {"query": QUERY, "limit": LIMIT},
        ["query"],
    ),
    "get_inaturalist_observed_taxa": (
        "List taxa reported in research-grade community observations for a place, optionally by taxon or calendar month across all years. Counts are reports, not animal abundance or current presence.",
        {
            "place_id": integer("Place ID returned by place search."),
            "taxon_id": integer("Optional taxon ID to restrict the group, such as birds or plants."),
            "month": integer("Optional calendar month, across all years.", maximum=12),
            "limit": LIMIT,
        },
        ["place_id"],
    ),
}


def manifest():
    return {
        "schema_version": "1.0",
        "name": "iNaturalist Wildlife Lookup",
        "description": "Public taxonomy and regional community observation summaries.",
        "tools": [
            {
                "name": name,
                "description": description,
                "endpoint": f"/tools/{name}",
                "method": "POST",
                "auth_required": False,
                "parameters": {"type": "object", "properties": properties, "required": required},
            }
            for name, (description, properties, required) in TOOL_SPECS.items()
        ],
    }


def validate(name, payload):
    """Validate the same parameter definitions advertised in the manifest."""
    if not isinstance(payload, dict):
        raise ToolError("Tool input must be a JSON object.")
    _, properties, required = TOOL_SPECS[name]
    if payload.keys() - properties.keys() - CONTEXT_FIELDS:
        raise ToolError("Unexpected tool parameter. Check the tool manifest.")
    values = {}
    for key, schema in properties.items():
        value = payload.get(key)
        if value is None:
            if key in required:
                raise ToolError(f"{key} is required and cannot be null.")
            # Omi's schema adapter gives omitted optional arguments None defaults.
            value = schema.get("default")
            if value is None:
                continue
        if schema["type"] == "string":
            if not isinstance(value, str):
                raise ToolError(f"{key} must be text.")
            value = value.strip()
            if not schema["minLength"] <= len(value) <= schema["maxLength"]:
                raise ToolError(f"{key} must contain 1 to 100 non-padding characters.")
            if any(ord(char) < 32 or ord(char) == 127 for char in value):
                raise ToolError(f"{key} cannot contain control characters.")
        elif type(value) is not int or not schema["minimum"] <= value <= schema["maximum"]:
            raise ToolError(f"{key} must be an integer between {schema['minimum']} and {schema['maximum']}.")
        values[key] = value
    return values


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def public_get(path, params):
    """Only called with internally selected paths and validated query parameters."""
    request = Request(
        f"{API_ORIGIN}{path}?{urlencode(params)}",
        headers={"Accept": "application/json", "User-Agent": "Omi-iNaturalist-Integration/1.0"},
    )
    try:
        with build_opener(NoRedirect).open(request, timeout=15) as response:
            body = response.read(MAX_RESPONSE_BYTES + 1)
            if len(body) > MAX_RESPONSE_BYTES:
                raise ToolError("iNaturalist returned too much data. Try a narrower request.")
            return response.status, dict(response.headers), body
    except HTTPError as exc:
        headers = dict(exc.headers)
        exc.close()
        return exc.code, headers, b""
    except (TimeoutError, URLError, OSError, HTTPException):
        raise ToolError("iNaturalist could not be reached. Try again later.") from None


async def fetch_public(path, params):
    return await asyncio.to_thread(public_get, path, params)


def text(value, fallback="Unknown"):
    if not isinstance(value, str) or not value.strip():
        return fallback
    return " ".join(value.split())[:240]


def positive_id(value):
    if type(value) is not int or value < 1:
        raise ToolError("iNaturalist returned an invalid record. Try again later.")
    return value


def taxon_line(taxon):
    if not isinstance(taxon, dict):
        raise ToolError("iNaturalist returned an invalid taxon record. Try again later.")
    taxon_id = positive_id(taxon.get("id"))
    return (
        f"{text(taxon.get('preferred_common_name'), 'No common name supplied')} "
        f"({text(taxon.get('name'))}); rank: {text(taxon.get('rank'))}; "
        f"ID: {taxon_id}; https://www.inaturalist.org/taxa/{taxon_id}"
    )


class INaturalistTools:
    """One shared instance per process owns the cache and upstream rate budget."""

    def __init__(self, fetch=fetch_public, clock=time.monotonic, wall_clock=time.time, sleep=asyncio.sleep):
        self.fetch = fetch
        self.clock = clock
        self.wall_clock = wall_clock
        self.sleep = sleep
        self.lock = asyncio.Lock()
        self.cache = OrderedDict()
        self.in_flight = {}
        self.requests = deque()
        self.next_request = 0.0
        self.cooldown_until = 0.0

    async def request(self, path, params):
        async with self.lock:
            now = self.clock()
            if now < self.cooldown_until:
                raise ToolError(
                    f"iNaturalist request budget is cooling down. Try again in {math.ceil(self.cooldown_until - now)} seconds."
                )
            if now < self.next_request:
                await self.sleep(self.next_request - now)
                now = self.clock()
            # Another in-flight response may have requested a cooldown while we waited.
            if now < self.cooldown_until:
                raise ToolError(
                    f"iNaturalist request budget is cooling down. Try again in {math.ceil(self.cooldown_until - now)} seconds."
                )
            while self.requests and now - self.requests[0] >= 86400:
                self.requests.popleft()
            if len(self.requests) >= 10000:
                raise ToolError("This integration's daily iNaturalist request budget is exhausted. Try again tomorrow.")
            self.requests.append(now)
            self.next_request = now + 1.0
        status, headers, body = await self.fetch(path, params)
        if status == 429:
            retry_after = next((v for k, v in headers.items() if k.lower() == "retry-after"), "60")
            try:
                delay = float(retry_after)
                if not math.isfinite(delay):
                    raise ValueError
            except (TypeError, ValueError):
                try:
                    delay = parsedate_to_datetime(retry_after).timestamp() - self.wall_clock()
                except (TypeError, ValueError, OverflowError):
                    delay = 60.0
            self.cooldown_until = max(self.cooldown_until, self.clock() + max(1.0, delay))
            raise ToolError("iNaturalist rate limit reached. No retry was sent; try again later.")
        if status == 404:
            raise ToolError("No iNaturalist record was found for that ID.")
        if status != 200:
            raise ToolError("iNaturalist is temporarily unavailable. Try again later.")
        try:
            data = json.loads(body)
            rows = data["results"]
            if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
                raise ValueError
        except (ValueError, KeyError, TypeError):
            raise ToolError("iNaturalist returned an unexpected response. Try again later.") from None
        fetched = datetime.fromtimestamp(self.wall_clock(), timezone.utc).isoformat(timespec="seconds")
        return rows, fetched

    async def run(self, name, payload):
        try:
            values = validate(name, payload)
        except ToolError as exc:
            return {"error": str(exc)}
        key = (name, tuple(sorted(values.items())))
        cached = self.cache.get(key)
        if cached and self.clock() - cached[0] < 300:
            self.cache.move_to_end(key)
            return {"result": cached[1]}
        task = self.in_flight.get(key)
        if task is None:
            if len(self.in_flight) >= 64:
                return {"error": "This integration is busy. Try again later."}
            task = asyncio.create_task(self._run_and_cache(name, values, key))
            self.in_flight[key] = task
            task.add_done_callback(lambda done: self._finish_request(key, done))
        # A caller disconnecting must not cancel work another caller is awaiting.
        return await asyncio.shield(task)

    def _finish_request(self, key, task):
        if self.in_flight.get(key) is task:
            self.in_flight.pop(key)
        if not task.cancelled():
            # Retrieve unexpected failures even if all callers disconnected.
            task.exception()

    async def _run_and_cache(self, name, values, key):
        response = await self._run(name, values)
        if "result" in response:
            # Commit only after endpoint-specific validation and formatting succeed.
            self.cache[key] = (self.clock(), response["result"])
            self.cache.move_to_end(key)
            while len(self.cache) > 64:
                self.cache.popitem(last=False)
        return response

    async def _run(self, name, values):
        try:
            limit = values.get("limit", 1)
            if name == "get_inaturalist_taxon":
                rows, fetched = await self.request(f"/taxa/{values['taxon_id']}", {})
                if not rows:
                    raise ToolError("No iNaturalist record was found for that ID.")
                taxon = rows[0]
                if taxon.get("id") != values["taxon_id"]:
                    raise ToolError("iNaturalist returned a different taxon. Try again later.")
                lines = [taxon_line(taxon)]
                ancestors = taxon.get("ancestors") or []
                if not isinstance(ancestors, list) or any(not isinstance(item, dict) for item in ancestors):
                    raise ToolError("iNaturalist returned an unexpected taxonomy. Try again later.")
                lines.append(
                    "Taxonomy: " + (" > ".join(text(item.get("name")) for item in ancestors[:20]) or "Not supplied")
                )
            elif name == "get_inaturalist_observed_taxa":
                params = {key: value for key, value in values.items() if key != "limit"}
                params.update({"quality_grade": "research", "per_page": limit, "page": 1})
                rows, fetched = await self.request("/observations/species_counts", params)
                query = urlencode({key: value for key, value in params.items() if key not in {"page", "per_page"}})
                lines = [
                    f"Research-grade community observations for place ID {values['place_id']}.",
                    "Counts are submitted observations, not population size, a complete species list, or current presence.",
                ]
                if "month" in values:
                    lines.append(f"Calendar month {values['month']}, across all years.")
                for row in rows[:limit]:
                    count = row.get("count")
                    if type(count) is not int or count < 0:
                        raise ToolError("iNaturalist returned an invalid observation count. Try again later.")
                    lines.append(f"- {taxon_line(row.get('taxon'))}; observations: {count}")
                if not rows:
                    lines.append("No matching observations were returned; this does not establish absence.")
                lines.append(f"Source: https://www.inaturalist.org/observations?{query}")
            else:
                path = "/taxa" if name == "search_inaturalist_taxa" else "/places/autocomplete"
                params = {"q": values["query"]}
                if path == "/taxa":
                    params["per_page"] = limit
                rows, fetched = await self.request(path, params)
                lines = [
                    (
                        "Matching taxa (names may be ambiguous):"
                        if path == "/taxa"
                        else "Matching places (choose a full place name):"
                    )
                ]
                for row in rows[:limit]:
                    if path == "/taxa":
                        lines.append("- " + taxon_line(row))
                    else:
                        place_id = positive_id(row.get("id"))
                        lines.append(
                            f"- {text(row.get('display_name'), text(row.get('name')))}; ID: {place_id}; https://www.inaturalist.org/places/{place_id}"
                        )
                if not rows:
                    lines.append("No matches found.")
            lines.append(f"Public iNaturalist data fetched at {fetched}; responses may be cached for five minutes.")
            return {"result": "\n".join(lines)}
        except ToolError as exc:
            return {"error": str(exc)}
