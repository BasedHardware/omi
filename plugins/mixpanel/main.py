import os
import json
import base64
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from fastapi import FastAPI, Request, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

app = FastAPI(title="Omi Mixpanel Analytics", version="1.0.0")

MIXPANEL_API_BASE = "https://mixpanel.com/api"

# ---------------------------------------------------------------------------
# Storage helpers (Redis with JSON-file fallback for local dev)
# ---------------------------------------------------------------------------

_redis_client = None
_local_store = {}
_local_store_path = os.path.join(os.path.dirname(__file__), ".local_store.json")


def _get_redis():
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        return None
    try:
        import redis

        _redis_client = redis.Redis.from_url(redis_url, decode_responses=True)
        _redis_client.ping()
        return _redis_client
    except Exception:
        _redis_client = None
        return None


def _load_local():
    global _local_store
    if os.path.exists(_local_store_path):
        with open(_local_store_path, "r") as f:
            _local_store = json.load(f)


def _save_local():
    with open(_local_store_path, "w") as f:
        json.dump(_local_store, f)


def store_set(key: str, value: str):
    r = _get_redis()
    if r:
        r.set(key, value)
    else:
        _load_local()
        _local_store[key] = value
        _save_local()


def store_get(key: str) -> Optional[str]:
    r = _get_redis()
    if r:
        return r.get(key)
    _load_local()
    return _local_store.get(key)


def store_delete(key: str):
    r = _get_redis()
    if r:
        r.delete(key)
    else:
        _load_local()
        _local_store.pop(key, None)
        _save_local()


# ---------------------------------------------------------------------------
# Credentials helpers
# ---------------------------------------------------------------------------


def _creds_key(uid: str) -> str:
    return f"mixpanel:creds:{uid}"


def save_credentials(uid: str, project_id: str, sa_username: str, sa_secret: str):
    data = json.dumps({"project_id": project_id, "sa_username": sa_username, "sa_secret": sa_secret})
    store_set(_creds_key(uid), data)


def get_credentials(uid: str) -> Optional[dict]:
    raw = store_get(_creds_key(uid))
    if not raw:
        return None
    return json.loads(raw)


def delete_credentials(uid: str):
    store_delete(_creds_key(uid))


# ---------------------------------------------------------------------------
# Mixpanel API client
# ---------------------------------------------------------------------------


def _auth_header(sa_username: str, sa_secret: str) -> dict:
    token = base64.b64encode(f"{sa_username}:{sa_secret}".encode()).decode()
    return {"Authorization": f"Basic {token}", "Accept": "application/json"}


async def mixpanel_query(endpoint: str, params: dict, creds: dict) -> dict:
    headers = _auth_header(creds["sa_username"], creds["sa_secret"])
    params["project_id"] = creds["project_id"]
    url = f"{MIXPANEL_API_BASE}/{endpoint}"
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url, headers=headers, params=params)
        resp.raise_for_status()
        return resp.json()


# ---------------------------------------------------------------------------
# Fuzzy event name matching
# ---------------------------------------------------------------------------


async def _fetch_all_event_names(creds: dict) -> list[str]:
    """Fetch all event names from the Mixpanel project."""
    try:
        data = await mixpanel_query("query/events/top", {"limit": 500, "type": "general"}, creds)
        events = data.get("events", data) if isinstance(data, dict) else data
        if isinstance(events, dict):
            return list(events.keys())
        if isinstance(events, list):
            return [item.get("event", item.get("name", "")) if isinstance(item, dict) else str(item) for item in events]
    except Exception:
        pass
    return []


def _normalize(text: str) -> str:
    """Lowercase and strip special chars for comparison."""
    return text.lower().replace("_", " ").replace("-", " ").strip()


def _fuzzy_match(query: str, candidates: list[str]) -> tuple[Optional[str], list[str]]:
    """Find the best matching event name. Returns (best_match, top_candidates).

    Matching strategy (in priority order):
    1. Exact match (case-insensitive)
    2. Normalized exact match (underscores/hyphens treated as spaces)
    3. Query is a substring of candidate (or vice versa)
    4. All query words appear in the candidate
    5. Word overlap scoring
    """
    if not candidates:
        return None, []

    query_norm = _normalize(query)
    query_words = set(query_norm.split())

    # 1. Exact match
    for c in candidates:
        if c.lower() == query.lower():
            return c, [c]

    # 2. Normalized exact match
    for c in candidates:
        if _normalize(c) == query_norm:
            return c, [c]

    # 3 & 4 & 5. Score all candidates
    scored = []
    for c in candidates:
        c_norm = _normalize(c)
        c_words = set(c_norm.split())

        score = 0.0

        # Substring match (high score)
        if query_norm in c_norm:
            score += 10.0 + (len(query_norm) / max(len(c_norm), 1))
        elif c_norm in query_norm:
            score += 8.0 + (len(c_norm) / max(len(query_norm), 1))

        # All query words present in candidate
        if query_words and query_words.issubset(c_words):
            score += 7.0

        # Word overlap
        overlap = query_words & c_words
        if overlap:
            score += len(overlap) / max(len(query_words | c_words), 1) * 5.0

        # Partial word matching (query word is substring of candidate word or vice versa)
        partial_matches = 0
        for qw in query_words:
            for cw in c_words:
                if len(qw) >= 3 and (qw in cw or cw in qw):
                    partial_matches += 1
                    score += 1.0
                    break  # count each query word once

        # Majority of query words match (overlap + partial)
        total_matched = len(overlap) + partial_matches
        if query_words and total_matched >= len(query_words) * 0.5:
            score += 3.0

        if score > 0:
            scored.append((c, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    top = [c for c, _ in scored[:5]]

    # Auto-resolve if top score is strong enough OR significantly ahead of runner-up
    if scored:
        best_score = scored[0][1]
        runner_up = scored[1][1] if len(scored) > 1 else 0
        if best_score >= 4.0 or (best_score >= 2.5 and best_score >= runner_up * 1.5):
            return scored[0][0], top

    return None, top


async def _resolve_event_name(event: str, creds: dict) -> tuple[str, Optional[str]]:
    """Resolve a user-provided event name to an actual Mixpanel event.

    Returns (resolved_name, note). `note` is a message like "Matched 'X' to 'Y'"
    if the name was fuzzy-matched, or an error hint if no match was found.
    """
    all_events = await _fetch_all_event_names(creds)
    if not all_events:
        # Can't fetch events list, just use what the user gave us
        return event, None

    # Check exact match first (fast path)
    if event in all_events:
        return event, None

    best, top = _fuzzy_match(event, all_events)
    if best:
        if best.lower() == event.lower():
            return best, None
        return best, f'Matched "{event}" to **{best}**'

    # No good match — return the original but include suggestions
    if top:
        suggestions = ", ".join(f'"{e}"' for e in top[:5])
        return event, f'No exact event named "{event}" found. Similar events: {suggestions}'
    return event, f'No event named "{event}" found in your project.'


async def _resolve_events_list(events_str: str, creds: dict) -> tuple[list[str], list[str]]:
    """Resolve a comma-separated list of event names. Returns (resolved_list, notes)."""
    raw_events = [e.strip() for e in events_str.split(",") if e.strip()]
    resolved = []
    notes = []
    for e in raw_events:
        name, note = await _resolve_event_name(e, creds)
        resolved.append(name)
        if note:
            notes.append(note)
    return resolved, notes


# ---------------------------------------------------------------------------
# Response model
# ---------------------------------------------------------------------------


class ChatToolResponse(BaseModel):
    result: Optional[str] = None
    error: Optional[str] = None


def _default_dates() -> tuple[str, str]:
    today = datetime.now(timezone.utc).date()
    from_date = (today - timedelta(days=30)).isoformat()
    to_date = today.isoformat()
    return from_date, to_date


def _get_dates(body: dict) -> tuple[str, str]:
    """Get from_date and to_date from request body, falling back to defaults for None/empty values."""
    default_from, default_to = _default_dates()
    from_date = body.get("from_date") or default_from
    to_date = body.get("to_date") or default_to
    return from_date, to_date


# ---------------------------------------------------------------------------
# Tools manifest
# ---------------------------------------------------------------------------


@app.get("/.well-known/omi-tools.json")
async def tools_manifest():
    return {
        "tools": [
            {
                "name": "query_events",
                "description": (
                    "Use this tool when the user asks about how many times an event happened, event counts, "
                    "event trends over time, or wants to see event volume. Returns event counts broken down "
                    "by time unit (hour, day, week, month)."
                ),
                "endpoint": "/tools/query_events",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "event": {
                            "type": "string",
                            "description": "The event name to query — does not need to be exact, fuzzy matching will find the closest event (e.g. 'sign ups', 'purchases', 'starred filter')",
                        },
                        "from_date": {
                            "type": "string",
                            "description": "Start date in YYYY-MM-DD format. Defaults to 30 days ago.",
                        },
                        "to_date": {
                            "type": "string",
                            "description": "End date in YYYY-MM-DD format. Defaults to today.",
                        },
                        "unit": {
                            "type": "string",
                            "description": "Time unit for grouping: hour, day, week, or month. Defaults to day.",
                        },
                    },
                    "required": ["event"],
                },
                "auth_required": True,
                "status_message": "Querying Mixpanel events...",
            },
            {
                "name": "segmentation",
                "description": (
                    "Use this tool when the user wants to break down an event by a property, see how an event "
                    "distributes across property values, or analyze event data segmented by a dimension. "
                    "For example: 'show me sign ups by country' or 'break down purchases by plan type'."
                ),
                "endpoint": "/tools/segmentation",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "event": {
                            "type": "string",
                            "description": "The event name to segment — fuzzy matching will find the closest event",
                        },
                        "property": {
                            "type": "string",
                            "description": "The property to segment by (e.g. 'country', 'plan', '$browser')",
                        },
                        "from_date": {
                            "type": "string",
                            "description": "Start date in YYYY-MM-DD format. Defaults to 30 days ago.",
                        },
                        "to_date": {
                            "type": "string",
                            "description": "End date in YYYY-MM-DD format. Defaults to today.",
                        },
                        "seg_type": {
                            "type": "string",
                            "description": "Aggregation type: general (total), unique (unique users), or average. Defaults to general.",
                        },
                    },
                    "required": ["event", "property"],
                },
                "auth_required": True,
                "status_message": "Running Mixpanel segmentation...",
            },
            {
                "name": "funnel_analysis",
                "description": (
                    "Use this tool when the user asks about conversion rates, funnel drop-offs, or how users "
                    "progress through a sequence of steps. Provide a comma-separated list of event names "
                    "representing the funnel steps."
                ),
                "endpoint": "/tools/funnel_analysis",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "events": {
                            "type": "string",
                            "description": "Comma-separated event names in funnel order — fuzzy matching will find closest events (e.g. 'sign ups,onboarding,first purchase')",
                        },
                        "from_date": {
                            "type": "string",
                            "description": "Start date in YYYY-MM-DD format. Defaults to 30 days ago.",
                        },
                        "to_date": {
                            "type": "string",
                            "description": "End date in YYYY-MM-DD format. Defaults to today.",
                        },
                    },
                    "required": ["events"],
                },
                "auth_required": True,
                "status_message": "Analyzing Mixpanel funnel...",
            },
            {
                "name": "retention",
                "description": (
                    "Use this tool when the user asks about user retention, how many users come back after "
                    "a specific action, or return rates. Requires a born_event (initial action) and "
                    "return_event (the action that indicates the user returned)."
                ),
                "endpoint": "/tools/retention",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "born_event": {
                            "type": "string",
                            "description": "The initial event — fuzzy matching will find closest event (e.g. 'sign ups')",
                        },
                        "return_event": {
                            "type": "string",
                            "description": "The return event — fuzzy matching will find closest event (e.g. 'app open'). If omitted, same as born_event.",
                        },
                        "from_date": {
                            "type": "string",
                            "description": "Start date in YYYY-MM-DD format. Defaults to 30 days ago.",
                        },
                        "to_date": {
                            "type": "string",
                            "description": "End date in YYYY-MM-DD format. Defaults to today.",
                        },
                    },
                    "required": ["born_event"],
                },
                "auth_required": True,
                "status_message": "Analyzing Mixpanel retention...",
            },
            {
                "name": "query_profiles",
                "description": (
                    "Use this tool when the user asks about user profiles, wants to look up users by a property, "
                    "or wants to see user data. Searches Mixpanel user profiles (Engage) by a property filter."
                ),
                "endpoint": "/tools/query_profiles",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "filter_expression": {
                            "type": "string",
                            "description": (
                                'Mixpanel filter expression, e.g. \'properties["plan"] == "premium"\' '
                                'or \'properties["country"] == "US"\'. If omitted, returns recent profiles.'
                            ),
                        },
                        "limit": {"type": "integer", "description": "Max profiles to return (default 10, max 100)"},
                    },
                    "required": [],
                },
                "auth_required": True,
                "status_message": "Querying Mixpanel profiles...",
            },
            {
                "name": "top_events",
                "description": (
                    "Use this tool when the user asks what the most popular or top events are, wants an overview "
                    "of event volume, or asks 'what events are being tracked'. Returns the highest-volume events."
                ),
                "endpoint": "/tools/top_events",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "limit": {"type": "integer", "description": "Number of top events to return (default 10)"},
                    },
                    "required": [],
                },
                "auth_required": True,
                "status_message": "Fetching top Mixpanel events...",
            },
        ]
    }


# ---------------------------------------------------------------------------
# HTML template
# ---------------------------------------------------------------------------

_PAGE_STYLE = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&display=swap');
    :root {
        --mp-purple: #7856FF;
        --mp-purple-hover: #6644E0;
        --mp-dark: #1c1c1c;
        --mp-darker: #141414;
        --mp-card: #2a2a2a;
        --mp-muted: #a3a3a3;
        --mp-white: #ffffff;
        --mp-border: #3a3a3a;
        --omi-accent: #6366f1;
        --mp-red: #ef4444;
        --mp-green: #22c55e;
    }
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
        font-family: 'DM Sans', -apple-system, BlinkMacSystemFont, sans-serif;
        background: linear-gradient(145deg, #141414 0%, #1a0f2e 50%, #1c1c1c 100%);
        color: var(--mp-white);
        min-height: 100vh;
        display: flex;
        justify-content: center;
        padding: 40px 20px;
    }
    .container { max-width: 480px; width: 100%; }
    .logo-row {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 16px;
        margin-bottom: 24px;
    }
    .logo-icon {
        width: 56px; height: 56px;
        border-radius: 14px;
        display: flex; align-items: center; justify-content: center;
        font-size: 24px; font-weight: 700; color: white;
    }
    .logo-mp { background: linear-gradient(135deg, #7856FF, #A78BFA); }
    .logo-omi { background: linear-gradient(135deg, #6366f1, #8b5cf6); }
    .logo-plus { color: var(--mp-muted); font-size: 20px; font-weight: 500; }
    h1 {
        text-align: center;
        font-size: 28px; font-weight: 700;
        margin-bottom: 8px;
        background: linear-gradient(90deg, #ffffff, #7856FF);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
    }
    .subtitle { text-align: center; color: var(--mp-muted); margin-bottom: 32px; font-size: 15px; }
    .card {
        background: var(--mp-card);
        border-radius: 16px;
        padding: 28px;
        margin-bottom: 20px;
        box-shadow: 0 8px 32px rgba(0,0,0,0.3);
    }
    .feature-list { list-style: none; }
    .feature-list li {
        display: flex; align-items: flex-start; gap: 12px;
        padding: 12px 0;
        border-bottom: 1px solid var(--mp-border);
        font-size: 14px; color: var(--mp-muted);
    }
    .feature-list li:last-child { border-bottom: none; }
    .feature-icon { font-size: 18px; flex-shrink: 0; margin-top: 1px; }
    .feature-title { color: var(--mp-white); font-weight: 600; display: block; margin-bottom: 2px; }
    .btn {
        display: block; width: 100%;
        padding: 16px 32px;
        border: none; border-radius: 12px;
        font-family: inherit; font-size: 16px; font-weight: 600;
        cursor: pointer;
        transition: all 0.2s ease;
        text-align: center; text-decoration: none;
        color: white;
    }
    .btn:hover { transform: scale(1.02); }
    .btn-primary { background: linear-gradient(135deg, #7856FF, #6644E0); }
    .btn-primary:hover { background: linear-gradient(135deg, #6644E0, #5533CC); }
    .btn-danger {
        background: transparent; color: var(--mp-red);
        border: 1px solid rgba(239,68,68,0.3);
        font-size: 14px; padding: 12px;
    }
    .btn-danger:hover { background: rgba(239,68,68,0.1); }
    .form-group { margin-bottom: 20px; }
    .form-label {
        display: block; font-size: 13px; font-weight: 600;
        color: var(--mp-muted); margin-bottom: 8px; text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    .form-input {
        width: 100%; padding: 14px 16px;
        background: var(--mp-darker); border: 1px solid var(--mp-border);
        border-radius: 10px; color: var(--mp-white);
        font-family: inherit; font-size: 15px;
        transition: border-color 0.2s;
    }
    .form-input:focus { outline: none; border-color: var(--mp-purple); }
    .form-input::placeholder { color: #555; }
    .form-hint { font-size: 12px; color: #666; margin-top: 6px; }
    .banner {
        border-radius: 12px; padding: 16px 20px;
        margin-bottom: 20px; display: flex; align-items: center; gap: 12px;
        font-size: 14px; font-weight: 500;
    }
    .banner-success { background: linear-gradient(135deg, rgba(34,197,94,0.15), rgba(34,197,94,0.05)); color: var(--mp-green); }
    .banner-error { background: linear-gradient(135deg, rgba(239,68,68,0.15), rgba(239,68,68,0.05)); color: var(--mp-red); }
    .banner-icon { font-size: 20px; }
    .connected-info { text-align: center; padding: 8px 0; }
    .connected-info .project-id {
        display: inline-block;
        background: var(--mp-darker); border: 1px solid var(--mp-border);
        border-radius: 8px; padding: 6px 14px;
        font-size: 13px; color: var(--mp-muted); font-family: monospace;
        margin-top: 8px;
    }
    .examples-title { font-size: 13px; font-weight: 600; color: var(--mp-muted); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 14px; }
    .example-item {
        background: var(--mp-darker); border-radius: 10px;
        padding: 12px 16px; margin-bottom: 8px;
        font-size: 14px; color: var(--mp-muted);
        border-left: 3px solid var(--mp-purple);
    }
    .help-link {
        display: block; text-align: center;
        color: var(--mp-muted); font-size: 13px;
        margin-top: 16px; text-decoration: none;
    }
    .help-link:hover { color: var(--mp-white); }
</style>
"""


def _html_page(body: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Mixpanel for Omi</title>
    {_PAGE_STYLE}
</head>
<body>
    <div class="container">
        <div class="logo-row">
            <div class="logo-icon logo-mp">M</div>
            <span class="logo-plus">+</span>
            <div class="logo-icon logo-omi">omi</div>
        </div>
        <h1>Mixpanel for Omi</h1>
        {body}
    </div>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Setup flow
# ---------------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse)
async def root(uid: Optional[str] = Query(None)):
    if not uid:
        body = """
        <p class="subtitle">Connect your Mixpanel analytics to explore data through Omi chat.</p>
        <div class="card">
            <p style="color: var(--mp-muted); font-size: 14px; text-align: center;">
                Open this page from the Omi app to get started.
            </p>
        </div>"""
        return HTMLResponse(_html_page(body))

    creds = get_credentials(uid)
    if creds:
        body = f"""
        <p class="subtitle">Your analytics are ready to explore.</p>
        <div class="banner banner-success">
            <span class="banner-icon">&#10003;</span>
            Connected to Mixpanel
        </div>
        <div class="card">
            <div class="connected-info">
                <span style="color: var(--mp-muted); font-size: 14px;">Project ID</span>
                <br>
                <span class="project-id">{creds['project_id']}</span>
            </div>
        </div>
        <div class="card">
            <div class="examples-title">Try asking Omi</div>
            <div class="example-item">What are the top events this week?</div>
            <div class="example-item">Show me sign ups by country</div>
            <div class="example-item">What's the conversion from Sign Up to Purchase?</div>
            <div class="example-item">What's the retention for users who signed up?</div>
        </div>
        <a href="/disconnect?uid={uid}" class="btn btn-danger">Disconnect Mixpanel</a>"""
        return HTMLResponse(_html_page(body))

    body = f"""
    <p class="subtitle">Connect your Mixpanel account to explore analytics through Omi chat.</p>
    <div class="card">
        <ul class="feature-list">
            <li>
                <span class="feature-icon">&#128202;</span>
                <div><span class="feature-title">Event Analytics</span>Query event counts, trends, and top events</div>
            </li>
            <li>
                <span class="feature-icon">&#128269;</span>
                <div><span class="feature-title">Segmentation</span>Break down events by any property</div>
            </li>
            <li>
                <span class="feature-icon">&#128200;</span>
                <div><span class="feature-title">Funnels &amp; Retention</span>Analyze conversions and user return rates</div>
            </li>
            <li>
                <span class="feature-icon">&#128100;</span>
                <div><span class="feature-title">User Profiles</span>Search and explore user data</div>
            </li>
        </ul>
    </div>
    <div class="card">
        <form method="POST" action="/auth/mixpanel?uid={uid}">
            <div class="form-group">
                <label class="form-label" for="project_id">Project ID</label>
                <input class="form-input" type="text" id="project_id" name="project_id"
                       placeholder="e.g. 2195732" required>
                <div class="form-hint">Found in Mixpanel &rarr; Settings &rarr; Project Settings</div>
            </div>
            <div class="form-group">
                <label class="form-label" for="sa_username">Service Account Username</label>
                <input class="form-input" type="text" id="sa_username" name="sa_username"
                       placeholder="e.g. my-service-account.abc123.mp-service-account" required>
            </div>
            <div class="form-group">
                <label class="form-label" for="sa_secret">Service Account Secret</label>
                <input class="form-input" type="password" id="sa_secret" name="sa_secret"
                       placeholder="&#8226;&#8226;&#8226;&#8226;&#8226;&#8226;&#8226;&#8226;&#8226;&#8226;&#8226;&#8226;" required>
                <div class="form-hint">Create one in Mixpanel &rarr; Organization Settings &rarr; Service Accounts</div>
            </div>
            <button type="submit" class="btn btn-primary">Connect Mixpanel</button>
        </form>
    </div>"""
    return HTMLResponse(_html_page(body))


@app.get("/auth/mixpanel", response_class=HTMLResponse)
async def auth_mixpanel_redirect(uid: str = Query(...)):
    from fastapi.responses import RedirectResponse

    return RedirectResponse(url=f"/?uid={uid}")


@app.post("/auth/mixpanel", response_class=HTMLResponse)
async def auth_mixpanel(request: Request, uid: str = Query(...)):
    form = await request.form()
    project_id = form.get("project_id", "").strip()
    sa_username = form.get("sa_username", "").strip()
    sa_secret = form.get("sa_secret", "").strip()

    if not all([project_id, sa_username, sa_secret]):
        body = """
        <p class="subtitle">Something went wrong.</p>
        <div class="banner banner-error">
            <span class="banner-icon">&#9888;</span>
            All fields are required.
        </div>
        <a href="javascript:history.back()" class="btn btn-primary">Go Back</a>"""
        return HTMLResponse(_html_page(body), status_code=400)

    # Validate credentials by making a test API call
    try:
        headers = _auth_header(sa_username, sa_secret)
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{MIXPANEL_API_BASE}/query/events/top",
                headers=headers,
                params={"project_id": project_id, "limit": 1, "type": "general"},
            )
            if resp.status_code == 401 or resp.status_code == 403:
                body = f"""
                <p class="subtitle">Something went wrong.</p>
                <div class="banner banner-error">
                    <span class="banner-icon">&#9888;</span>
                    Invalid credentials. Check your Service Account username and secret.
                </div>
                <a href="/?uid={uid}" class="btn btn-primary">Try Again</a>"""
                return HTMLResponse(_html_page(body), status_code=401)
            resp.raise_for_status()
    except httpx.HTTPStatusError:
        body = f"""
        <p class="subtitle">Something went wrong.</p>
        <div class="banner banner-error">
            <span class="banner-icon">&#9888;</span>
            Could not connect to Mixpanel. Verify your Project ID and credentials.
        </div>
        <a href="/?uid={uid}" class="btn btn-primary">Try Again</a>"""
        return HTMLResponse(_html_page(body), status_code=400)

    save_credentials(uid, project_id, sa_username, sa_secret)
    from fastapi.responses import RedirectResponse

    return RedirectResponse(url=f"/?uid={uid}", status_code=303)


@app.get("/setup/mixpanel")
async def check_setup(uid: Optional[str] = Query(None)):
    if not uid:
        return {"is_setup_completed": False}
    creds = get_credentials(uid)
    return {"is_setup_completed": creds is not None}


@app.get("/disconnect", response_class=HTMLResponse)
async def disconnect(uid: str = Query(...)):
    delete_credentials(uid)
    from fastapi.responses import RedirectResponse

    return RedirectResponse(url=f"/?uid={uid}")


# ---------------------------------------------------------------------------
# Chat tool endpoints
# ---------------------------------------------------------------------------


def _require_creds(uid: Optional[str]) -> tuple[Optional[ChatToolResponse], Optional[dict]]:
    if not uid:
        return ChatToolResponse(error="User ID is required."), None
    creds = get_credentials(uid)
    if not creds:
        return ChatToolResponse(error="Please connect your Mixpanel account first in the app settings."), None
    return None, creds


@app.post("/tools/query_events", response_model=ChatToolResponse, tags=["chat_tools"])
async def tool_query_events(request: Request):
    body = await request.json()
    uid = body.get("uid")
    err, creds = _require_creds(uid)
    if err:
        return err

    event = body.get("event")
    if not event:
        return ChatToolResponse(error="Event name is required.")

    # Resolve fuzzy event name
    event, match_note = await _resolve_event_name(event, creds)

    from_date, to_date = _get_dates(body)
    unit = body.get("unit", "day")

    try:
        data = await mixpanel_query(
            "query/events",
            {"event": json.dumps([event]), "type": "general", "unit": unit, "from_date": from_date, "to_date": to_date},
            creds,
        )
    except httpx.HTTPStatusError as e:
        return ChatToolResponse(error=f"Mixpanel API error: {e.response.status_code}")
    except Exception as e:
        return ChatToolResponse(error=f"Failed to query Mixpanel: {str(e)}")

    # Format result
    values = data.get("data", {}).get("values", {})
    event_data = values.get(event, {})
    if not event_data:
        msg = f"No data found for event **{event}** from {from_date} to {to_date}."
        if match_note:
            msg = f"{match_note}\n\n{msg}"
        return ChatToolResponse(result=msg)

    total = sum(event_data.values())
    lines = []
    if match_note:
        lines.append(match_note)
        lines.append("")
    lines.extend(
        [
            f"**{event}** from {from_date} to {to_date}",
            f"**Total:** {total:,}",
            "",
            "| Date | Count |",
            "|------|-------|",
        ]
    )
    for date_str, count in sorted(event_data.items()):
        lines.append(f"| {date_str} | {count:,} |")

    return ChatToolResponse(result="\n".join(lines))


@app.post("/tools/segmentation", response_model=ChatToolResponse, tags=["chat_tools"])
async def tool_segmentation(request: Request):
    body = await request.json()
    uid = body.get("uid")
    err, creds = _require_creds(uid)
    if err:
        return err

    event = body.get("event")
    prop = body.get("property")
    if not event or not prop:
        return ChatToolResponse(error="Both event and property are required.")

    # Resolve fuzzy event name
    event, match_note = await _resolve_event_name(event, creds)

    from_date, to_date = _get_dates(body)
    seg_type = body.get("seg_type", "general")

    try:
        data = await mixpanel_query(
            "query/segmentation",
            {
                "event": event,
                "on": f'properties["{prop}"]',
                "type": seg_type,
                "from_date": from_date,
                "to_date": to_date,
            },
            creds,
        )
    except httpx.HTTPStatusError as e:
        return ChatToolResponse(error=f"Mixpanel API error: {e.response.status_code}")
    except Exception as e:
        return ChatToolResponse(error=f"Failed to query Mixpanel: {str(e)}")

    values = data.get("data", {}).get("values", {})
    if not values:
        msg = f"No segmentation data for **{event}** by **{prop}** from {from_date} to {to_date}."
        if match_note:
            msg = f"{match_note}\n\n{msg}"
        return ChatToolResponse(result=msg)

    # Aggregate totals per segment value
    totals = {}
    for segment_val, date_counts in values.items():
        totals[segment_val] = sum(date_counts.values()) if isinstance(date_counts, dict) else 0

    sorted_segments = sorted(totals.items(), key=lambda x: x[1], reverse=True)
    lines = []
    if match_note:
        lines.append(match_note)
        lines.append("")
    lines.extend(
        [
            f"**{event}** segmented by **{prop}** ({from_date} to {to_date})",
            "",
            f"| {prop} | Count |",
            "|------|-------|",
        ]
    )
    for seg_val, count in sorted_segments[:25]:
        display = seg_val if seg_val else "(empty)"
        lines.append(f"| {display} | {count:,} |")

    if len(sorted_segments) > 25:
        lines.append(f"\n*Showing top 25 of {len(sorted_segments)} values.*")

    return ChatToolResponse(result="\n".join(lines))


@app.post("/tools/funnel_analysis", response_model=ChatToolResponse, tags=["chat_tools"])
async def tool_funnel_analysis(request: Request):
    body = await request.json()
    uid = body.get("uid")
    err, creds = _require_creds(uid)
    if err:
        return err

    events_str = body.get("events")
    if not events_str:
        return ChatToolResponse(error="Events list is required (comma-separated).")

    event_list, match_notes = await _resolve_events_list(events_str, creds)
    if len(event_list) < 2:
        return ChatToolResponse(error="At least 2 events are required for funnel analysis.")

    from_date, to_date = _get_dates(body)

    # Simulate funnel by querying unique users for each event
    step_counts = []
    for event_name in event_list:
        try:
            data = await mixpanel_query(
                "query/events",
                {
                    "event": json.dumps([event_name]),
                    "type": "unique",
                    "unit": "month",
                    "from_date": from_date,
                    "to_date": to_date,
                },
                creds,
            )
            values = data.get("data", {}).get("values", {})
            event_data = values.get(event_name, {})
            total = sum(event_data.values()) if event_data else 0
            step_counts.append((event_name, total))
        except Exception:
            step_counts.append((event_name, 0))

    lines = []
    if match_notes:
        lines.extend(match_notes)
        lines.append("")
    lines.extend([f"**Funnel Analysis** ({from_date} to {to_date})", ""])
    lines.extend(["| Step | Event | Unique Users | Conversion |", "|------|-------|-------------|------------|"])

    first_count = step_counts[0][1] if step_counts else 0
    for i, (event_name, count) in enumerate(step_counts):
        if i == 0:
            pct = "100.0%"
        elif first_count > 0:
            pct = f"{(count / first_count * 100):.1f}%"
        else:
            pct = "N/A"
        lines.append(f"| {i + 1} | {event_name} | {count:,} | {pct} |")

    # Add step-over-step conversion
    if len(step_counts) > 1:
        lines.append("")
        lines.append("**Step-over-step conversion:**")
        for i in range(1, len(step_counts)):
            prev_name, prev_count = step_counts[i - 1]
            cur_name, cur_count = step_counts[i]
            if prev_count > 0:
                rate = cur_count / prev_count * 100
                lines.append(f"- {prev_name} -> {cur_name}: **{rate:.1f}%**")
            else:
                lines.append(f"- {prev_name} -> {cur_name}: N/A")

    return ChatToolResponse(result="\n".join(lines))


@app.post("/tools/retention", response_model=ChatToolResponse, tags=["chat_tools"])
async def tool_retention(request: Request):
    body = await request.json()
    uid = body.get("uid")
    err, creds = _require_creds(uid)
    if err:
        return err

    born_event = body.get("born_event")
    if not born_event:
        return ChatToolResponse(error="born_event is required.")

    # Resolve fuzzy event names
    born_event, born_note = await _resolve_event_name(born_event, creds)
    return_event = body.get("return_event", born_event)
    if body.get("return_event"):
        return_event, return_note = await _resolve_event_name(return_event, creds)
    else:
        return_note = None
    retention_notes = [n for n in [born_note, return_note] if n]

    from_date, to_date = _get_dates(body)

    try:
        data = await mixpanel_query(
            "query/retention",
            {
                "born_event": born_event,
                "event": return_event,
                "from_date": from_date,
                "to_date": to_date,
                "born_where": "true",
                "where": "true",
            },
            creds,
        )
    except httpx.HTTPStatusError as e:
        return ChatToolResponse(error=f"Mixpanel API error: {e.response.status_code}")
    except Exception as e:
        return ChatToolResponse(error=f"Failed to query Mixpanel: {str(e)}")

    results = data.get("results", {})
    if not results:
        msg = f"No retention data for **{born_event}** -> **{return_event}** from {from_date} to {to_date}."
        if retention_notes:
            msg = "\n".join(retention_notes) + f"\n\n{msg}"
        return ChatToolResponse(result=msg)

    lines = []
    if retention_notes:
        lines.extend(retention_notes)
        lines.append("")
    lines.extend(
        [
            f"**Retention: {born_event} -> {return_event}** ({from_date} to {to_date})",
            "",
            "| Day | Retained | Rate |",
            "|-----|----------|------|",
        ]
    )

    # Aggregate across cohorts
    day_totals = {}
    day_counts = {}
    for cohort_date, cohort_data in results.items():
        counts = cohort_data.get("counts", [])
        first = cohort_data.get("first", counts[0] if counts else 0)
        for day_idx, count in enumerate(counts):
            day_totals.setdefault(day_idx, 0)
            day_counts.setdefault(day_idx, 0)
            day_totals[day_idx] += count
            day_counts[day_idx] += first

    for day_idx in sorted(day_totals.keys())[:15]:
        retained = day_totals[day_idx]
        base = day_counts[day_idx]
        rate = f"{(retained / base * 100):.1f}%" if base > 0 else "N/A"
        label = "Day 0" if day_idx == 0 else f"Day {day_idx}"
        lines.append(f"| {label} | {retained:,} | {rate} |")

    if len(day_totals) > 15:
        lines.append(f"\n*Showing first 15 of {len(day_totals)} days.*")

    return ChatToolResponse(result="\n".join(lines))


@app.post("/tools/query_profiles", response_model=ChatToolResponse, tags=["chat_tools"])
async def tool_query_profiles(request: Request):
    body = await request.json()
    uid = body.get("uid")
    err, creds = _require_creds(uid)
    if err:
        return err

    filter_expr = body.get("filter_expression", "")
    limit = min(body.get("limit", 10), 100)

    params = {"page_size": limit}
    if filter_expr:
        params["where"] = filter_expr

    try:
        headers = _auth_header(creds["sa_username"], creds["sa_secret"])
        params["project_id"] = creds["project_id"]
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(f"{MIXPANEL_API_BASE}/query/engage", headers=headers, params=params)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as e:
        return ChatToolResponse(error=f"Mixpanel API error: {e.response.status_code}")
    except Exception as e:
        return ChatToolResponse(error=f"Failed to query Mixpanel: {str(e)}")

    results = data.get("results", [])
    total = data.get("total", len(results))

    if not results:
        filter_desc = f" matching `{filter_expr}`" if filter_expr else ""
        return ChatToolResponse(result=f"No profiles found{filter_desc}.")

    lines = [f"**User Profiles** (showing {len(results)} of {total:,} total)", ""]

    for profile in results:
        props = profile.get("$properties", {})
        distinct_id = profile.get("$distinct_id", "?")
        name = props.get("$name", props.get("$first_name", ""))
        email = props.get("$email", "")
        city = props.get("$city", "")
        last_seen = props.get("$last_seen", "")

        header_parts = [f"**{name}**" if name else f"ID: `{distinct_id}`"]
        if email:
            header_parts.append(f"({email})")
        lines.append(" ".join(header_parts))

        details = []
        if city:
            details.append(f"City: {city}")
        if last_seen:
            details.append(f"Last seen: {last_seen}")
        if details:
            lines.append("  " + " | ".join(details))
        lines.append("")

    return ChatToolResponse(result="\n".join(lines))


@app.post("/tools/top_events", response_model=ChatToolResponse, tags=["chat_tools"])
async def tool_top_events(request: Request):
    body = await request.json()
    uid = body.get("uid")
    err, creds = _require_creds(uid)
    if err:
        return err

    limit = body.get("limit", 10)

    try:
        data = await mixpanel_query("query/events/top", {"limit": limit, "type": "general"}, creds)
    except httpx.HTTPStatusError as e:
        return ChatToolResponse(error=f"Mixpanel API error: {e.response.status_code}")
    except Exception as e:
        return ChatToolResponse(error=f"Failed to query Mixpanel: {str(e)}")

    events = data.get("events", data) if isinstance(data, dict) else data

    if not events:
        return ChatToolResponse(result="No events found in your Mixpanel project.")

    lines = ["**Top Events**", "", "| # | Event | Count |", "|---|-------|-------|"]

    if isinstance(events, dict):
        sorted_events = sorted(
            events.items(), key=lambda x: x[1] if isinstance(x[1], (int, float)) else 0, reverse=True
        )
        for i, (name, count) in enumerate(sorted_events[:limit], 1):
            count_val = count if isinstance(count, (int, float)) else 0
            lines.append(f"| {i} | {name} | {count_val:,} |")
    elif isinstance(events, list):
        for i, item in enumerate(events[:limit], 1):
            if isinstance(item, dict):
                name = item.get("event", item.get("name", "?"))
                count = item.get("amount", item.get("count", 0))
                lines.append(f"| {i} | {name} | {count:,} |")
            else:
                lines.append(f"| {i} | {item} | - |")

    return ChatToolResponse(result="\n".join(lines))
