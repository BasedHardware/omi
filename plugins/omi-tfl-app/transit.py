"""TfL's public, read-only API exposed through Omi's chat-tool contract."""

import json
import re
import threading
import time
from collections import deque
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

API_ROOT = "https://api.tfl.gov.uk"
ATTRIBUTION = (
    "Powered by TfL Open Data. https://tfl.gov.uk/\n"
    "Contains OS data © Crown copyright and database rights 2016. "
    "Geomni UK Map data © and database rights [2019]."
)
MAX_RESPONSE_BYTES = 1_000_000
MODES = ("tube", "bus", "dlr", "overground", "elizabeth-line", "tram", "river-bus", "national-rail")


class ToolError(Exception):
    """A safe error that may be shown in an Omi conversation."""


class TfLClient:
    """Bound requests to the anonymous quota, including concurrent tool calls."""

    def __init__(self, opener=urlopen, clock=time.monotonic):
        self.opener = opener
        self.clock = clock
        self.requests = deque()
        self.lock = threading.Lock()

    def get(self, path, params=None):
        with self.lock:
            now = self.clock()
            while self.requests and now - self.requests[0] >= 60:
                self.requests.popleft()
            if len(self.requests) >= 40:
                raise ToolError("The transit request limit was reached. Please try again in a minute.")
            self.requests.append(now)
        url = API_ROOT + path
        if params:
            url += "?" + urlencode(params)
        request = Request(url, headers={"Accept": "application/json", "User-Agent": "OmiTfLIntegration/1.0"})
        try:
            with self.opener(request, timeout=10) as response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise ToolError("TfL returned too much data. Please try a more specific stop or line.")
            return json.loads(raw)
        except HTTPError as exc:
            exc.close()
            if exc.code == 429:
                raise ToolError("TfL's request limit was reached. Please try again later.") from exc
            if exc.code == 404:
                raise ToolError("TfL could not find that stop or line. Search for its exact ID first.") from exc
            raise ToolError(f"TfL is unavailable (HTTP {exc.code}). Please try again later.") from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise ToolError("TfL could not be reached. Please try again later.") from exc
        except (ValueError, UnicodeError) as exc:
            raise ToolError("TfL returned an invalid response. Please try again later.") from exc


def text(value, label, maximum=200):
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum:
        raise ToolError(f"{label} must be non-empty text of at most {maximum} characters.")
    return value.strip()


def identifier(value, label):
    value = text(value, label, 64)
    if not re.fullmatch(r"[A-Za-z0-9-]+", value):
        raise ToolError(f"{label} must be an exact TfL ID containing only letters, digits or hyphens.")
    return value


def limit_value(value):
    if type(value) is not int or not 1 <= value <= 10:
        raise ToolError("limit must be an integer between 1 and 10.")
    return value


def records(payload):
    if not isinstance(payload, list) or any(not isinstance(item, dict) for item in payload):
        raise ToolError("TfL returned an unexpected response format.")
    return payload


def timestamp(value):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("missing timezone")
        return parsed.astimezone(timezone.utc)
    except (AttributeError, TypeError, ValueError) as exc:
        raise ToolError("TfL returned an invalid prediction timestamp.") from exc


def line_status(payload, client, now):
    ids = payload.get("line_ids", [])
    if not isinstance(ids, list) or len(ids) > 10:
        raise ToolError("line_ids must be a list of at most 10 exact TfL line IDs.")
    ids = list(dict.fromkeys(identifier(item, "line ID").lower() for item in ids))
    path = f"/Line/{','.join(ids)}/Status" if ids else "/Line/Mode/tube/Status"
    lines = records(client.get(path))
    if not lines:
        raise ToolError("TfL returned no line status data; service status is unknown.")
    output = ["TfL line status:" if ids else "London Underground line status:"]
    returned_ids = set()
    for line in lines:
        returned_ids.add(identifier(line.get("id"), "TfL line ID").lower())
        name = text(line.get("name"), "TfL line name")
        statuses = records(line.get("lineStatuses"))
        if not statuses:
            output.append(f"- {name}: status not supplied by TfL.")
        for status in statuses:
            description = text(status.get("statusSeverityDescription"), "TfL status")
            reason = status.get("reason")
            detail = f" — {text(reason, 'TfL disruption detail', 12000)}" if reason else ""
            output.append(f"- {name}: {description}{detail}")
    missing = [item for item in ids if item not in returned_ids]
    if missing:
        output.append(f"No status returned for: {', '.join(missing)}. Those lines' status is unknown.")
    return output


def find_stops(payload, client, now):
    query = text(payload.get("query"), "query", 80)
    if len(query) < 2:
        raise ToolError("query must contain at least two characters.")
    limit = limit_value(payload.get("limit", 5))
    params = {"query": query, "maxResults": limit, "includeHubs": "false"}
    mode = payload.get("mode")
    if mode is not None:
        if mode not in MODES:
            raise ToolError(f"mode must be one of: {', '.join(MODES)}.")
        params["modes"] = mode
    result = client.get("/StopPoint/Search", params)
    if not isinstance(result, dict):
        raise ToolError("TfL returned an unexpected stop-search response.")
    stops = records(result.get("matches"))
    if not stops:
        return ["No matching TfL stops were found. Try a station name or a bus stop code."]
    output = ["Matching TfL stops (choose the exact ID for arrivals):"]
    for stop in stops[:limit]:
        stop_id = identifier(stop.get("id"), "TfL stop ID")
        name = text(stop.get("name"), "TfL stop name")
        modes = stop.get("modes", [])
        if not isinstance(modes, list):
            raise ToolError("TfL returned invalid transport modes.")
        modes = ", ".join(text(item, "TfL mode", 50) for item in modes)
        output.append(f"- {name} | ID: {stop_id}" + (f" | {modes}" if modes else ""))
    total = result.get("total", len(stops))
    if type(total) is not int or total < 0:
        raise ToolError("TfL returned an invalid stop count.")
    if len(stops) > limit or total > limit:
        output.append("Only the first matches are shown. Refine the query or mode if the stop is ambiguous.")
    return output


def get_arrivals(payload, client, now):
    stop_id = identifier(payload.get("stop_id"), "stop_id")
    limit = limit_value(payload.get("limit", 5))
    predictions = records(client.get(f"/StopPoint/{stop_id}/Arrivals"))
    upcoming = []
    for prediction in predictions:
        if prediction.get("operationType") == 2:
            continue
        if "timeToLive" in prediction and timestamp(prediction["timeToLive"]) <= now:
            continue
        expected = timestamp(prediction.get("expectedArrival"))
        reported = timestamp(prediction.get("timestamp"))
        if expected >= now:
            upcoming.append((expected, reported, prediction))
    upcoming.sort(key=lambda item: item[0])
    if not upcoming:
        return [
            f"TfL has no upcoming arrival predictions for {stop_id}. This does not establish whether service is running."
        ]
    output = [f"Arrival predictions for {stop_id} (UTC; predictions may change):"]
    for expected, reported, prediction in upcoming[:limit]:
        name = text(prediction.get("lineName"), "TfL line name")
        destination = prediction.get("destinationName") or prediction.get("towards") or "destination not supplied"
        platform = prediction.get("platformName") or "platform not supplied"
        output.append(
            f"- {name} towards {text(destination, 'TfL destination')}: "
            f"{expected.isoformat()} | {text(platform, 'TfL platform')} | "
            f"prediction reported {reported.isoformat()}"
        )
    return output


TOOLS = {"get_line_status": line_status, "find_stops": find_stops, "get_arrivals": get_arrivals}


def execute(tool_name, payload, client, now=None):
    try:
        if tool_name not in TOOLS:
            raise ToolError("Unknown transit tool.")
        if not isinstance(payload, dict):
            raise ToolError("Tool parameters must be a JSON object.")
        now = now or datetime.now(timezone.utc)
        output = TOOLS[tool_name](payload, client, now)
        output.extend([f"Retrieved: {now.isoformat()} (UTC).", ATTRIBUTION])
        return {"result": "\n".join(output)}
    except ToolError as exc:
        return {"error": str(exc)}
