import os
import json
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from fastapi import FastAPI, Request, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from openai import OpenAI
from pydantic import BaseModel

app = FastAPI(title="Omi Habitify", version="1.0.0")

HABITIFY_API_BASE = "https://api.habitify.me"

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
    return f"habitify:api_key:{uid}"


def save_credentials(uid: str, api_key: str):
    data = json.dumps({"api_key": api_key})
    store_set(_creds_key(uid), data)


def get_credentials(uid: str) -> Optional[dict]:
    raw = store_get(_creds_key(uid))
    if not raw:
        return None
    return json.loads(raw)


def delete_credentials(uid: str):
    store_delete(_creds_key(uid))


# ---------------------------------------------------------------------------
# Habitify API client
# ---------------------------------------------------------------------------


async def habitify_request(method: str, path: str, api_key: str, params: dict = None, json_body: dict = None) -> dict:
    headers = {"Authorization": api_key, "Accept": "application/json"}
    url = f"{HABITIFY_API_BASE}{path}"
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.request(method, url, headers=headers, params=params, json=json_body)
        resp.raise_for_status()
        return resp.json()


# ---------------------------------------------------------------------------
# OpenAI-powered habit name matching
# ---------------------------------------------------------------------------

_openai_client = None


def _get_openai():
    global _openai_client
    if _openai_client is not None:
        return _openai_client
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    _openai_client = OpenAI(api_key=api_key)
    return _openai_client


def _simple_match(query: str, habits: list[dict]) -> Optional[dict]:
    """Case-insensitive substring fallback when OpenAI is unavailable."""
    q = query.lower().strip()
    for h in habits:
        if h["name"].lower() == q:
            return h
    for h in habits:
        if q in h["name"].lower() or h["name"].lower() in q:
            return h
    return None


async def _resolve_habit(habit_name: str, api_key: str) -> tuple[Optional[dict], Optional[str]]:
    """Resolve a user-provided habit name to an actual Habitify habit.

    Returns (habit_object, note_if_fuzzy_matched). habit_object is None if no match found.
    """
    data = await habitify_request("GET", "/habits", api_key)
    habits = data.get("data", [])
    if not habits:
        return None, "You don't have any habits in Habitify yet."

    # Exact match first
    for h in habits:
        if h["name"].lower() == habit_name.lower():
            return h, None

    # Try OpenAI matching
    oai = _get_openai()
    if oai:
        habit_names = [h["name"] for h in habits]
        try:
            resp = oai.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a habit name matcher. Given a list of habit names and a user query, "
                            "return the EXACT habit name from the list that best matches the query. "
                            "Return ONLY the exact name string, nothing else. "
                            "If no habit matches at all, return the word NULL."
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"Habit names: {json.dumps(habit_names)}\n\nUser query: {habit_name}",
                    },
                ],
                temperature=0,
                max_tokens=100,
            )
            matched_name = resp.choices[0].message.content.strip()
            if matched_name and matched_name != "NULL":
                for h in habits:
                    if h["name"] == matched_name:
                        note = (
                            None
                            if matched_name.lower() == habit_name.lower()
                            else f'Matched "{habit_name}" to **{matched_name}**'
                        )
                        return h, note
        except Exception:
            pass

    # Fallback to simple substring matching
    match = _simple_match(habit_name, habits)
    if match:
        note = None if match["name"].lower() == habit_name.lower() else f'Matched "{habit_name}" to **{match["name"]}**'
        return match, note

    return None, f'No habit matching "{habit_name}" found. Your habits: {", ".join(h["name"] for h in habits[:10])}'


# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------


def _default_target_date() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def _default_date_range() -> tuple[str, str]:
    today = datetime.now(timezone.utc)
    from_date = (today - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    to_date = today.strftime("%Y-%m-%dT%H:%M:%S+00:00")
    return from_date, to_date


# ---------------------------------------------------------------------------
# Response model
# ---------------------------------------------------------------------------


class ChatToolResponse(BaseModel):
    result: Optional[str] = None
    error: Optional[str] = None


def _require_creds(uid: Optional[str]) -> tuple[Optional[ChatToolResponse], Optional[dict]]:
    if not uid:
        return ChatToolResponse(error="User ID is required."), None
    creds = get_credentials(uid)
    if not creds:
        return ChatToolResponse(error="Please connect your Habitify account first in the app settings."), None
    return None, creds


# ---------------------------------------------------------------------------
# Tools manifest
# ---------------------------------------------------------------------------


@app.get("/.well-known/omi-tools.json")
async def tools_manifest():
    return {
        "tools": [
            {
                "name": "list_habits",
                "description": (
                    "Use this tool when the user asks about their habits, wants to see "
                    "what habits they're tracking, or needs a list of habits. Returns all "
                    "habits with their names, areas, goals, and schedule info."
                ),
                "endpoint": "/tools/list_habits",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "area_name": {
                            "type": "string",
                            "description": "Optional area/category name to filter habits by (e.g. 'Health', 'Work'). If omitted, returns all habits.",
                        },
                    },
                    "required": [],
                },
                "auth_required": True,
                "status_message": "Fetching your habits...",
            },
            {
                "name": "get_habit_status",
                "description": (
                    "Use this tool when the user asks about the status of a specific habit "
                    "for a given day - whether it's completed, in progress, skipped, or has no data. "
                    "Also returns progress toward the goal if applicable."
                ),
                "endpoint": "/tools/get_habit_status",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "habit_name": {
                            "type": "string",
                            "description": "The name of the habit to check (fuzzy matching will find the closest habit)",
                        },
                        "target_date": {
                            "type": "string",
                            "description": "Date in ISO format (YYYY-MM-DDThh:mm:ss+hh:mm). Defaults to today.",
                        },
                    },
                    "required": ["habit_name"],
                },
                "auth_required": True,
                "status_message": "Checking habit status...",
            },
            {
                "name": "complete_habit",
                "description": (
                    "Use this tool when the user wants to mark a habit as completed, log progress "
                    "toward a goal-based habit, or record that they did a habit. For simple habits, "
                    "it marks them complete. For goal-based habits (e.g. 'drink 8 glasses of water'), "
                    "provide the value to log."
                ),
                "endpoint": "/tools/complete_habit",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "habit_name": {
                            "type": "string",
                            "description": "The name of the habit to complete or log progress for (fuzzy matching applied)",
                        },
                        "value": {
                            "type": "number",
                            "description": "For goal-based habits, the value to log (e.g. 30 for 30 minutes). Omit for simple completion habits.",
                        },
                        "target_date": {
                            "type": "string",
                            "description": "Date to log for, in ISO format. Defaults to today.",
                        },
                    },
                    "required": ["habit_name"],
                },
                "auth_required": True,
                "status_message": "Logging habit completion...",
            },
            {
                "name": "get_habit_logs",
                "description": (
                    "Use this tool when the user asks about their habit history, past completions, "
                    "or wants to see logs for a specific habit over a time range. Returns the log "
                    "entries with dates and values."
                ),
                "endpoint": "/tools/get_habit_logs",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "habit_name": {
                            "type": "string",
                            "description": "The name of the habit to get logs for (fuzzy matching applied)",
                        },
                        "from_date": {
                            "type": "string",
                            "description": "Start date in ISO format. Defaults to 7 days ago.",
                        },
                        "to_date": {
                            "type": "string",
                            "description": "End date in ISO format. Defaults to today.",
                        },
                    },
                    "required": ["habit_name"],
                },
                "auth_required": True,
                "status_message": "Fetching habit logs...",
            },
            {
                "name": "daily_summary",
                "description": (
                    "Use this tool when the user asks for an overview of their day, wants to know "
                    "their overall habit progress, or asks how they're doing. Returns the status of "
                    "all active habits for a specific day, including completion rate."
                ),
                "endpoint": "/tools/daily_summary",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "target_date": {
                            "type": "string",
                            "description": "Date in ISO format. Defaults to today.",
                        },
                    },
                    "required": [],
                },
                "auth_required": True,
                "status_message": "Building your daily summary...",
            },
            {
                "name": "add_note",
                "description": (
                    "Use this tool when the user wants to add a text note or journal entry to "
                    "a specific habit. Notes help track qualitative observations alongside "
                    "habit completions."
                ),
                "endpoint": "/tools/add_note",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "habit_name": {
                            "type": "string",
                            "description": "The name of the habit to add a note to (fuzzy matching applied)",
                        },
                        "content": {
                            "type": "string",
                            "description": "The text content of the note",
                        },
                        "target_date": {
                            "type": "string",
                            "description": "Date for the note in ISO format. Defaults to today.",
                        },
                    },
                    "required": ["habit_name", "content"],
                },
                "auth_required": True,
                "status_message": "Adding note to habit...",
            },
            {
                "name": "log_mood",
                "description": (
                    "Use this tool when the user wants to log or record their mood for the day. "
                    "Mood values are: terrible (1), bad (2), okay (3), good (4), excellent (5). "
                    "The tool will map natural language descriptions to the appropriate value."
                ),
                "endpoint": "/tools/log_mood",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "mood_value": {
                            "type": "integer",
                            "description": "Mood value: 1 (terrible), 2 (bad), 3 (okay), 4 (good), 5 (excellent)",
                        },
                        "target_date": {
                            "type": "string",
                            "description": "Date in ISO format (YYYY-MM-DDThh:mm:ss+hh:mm). Defaults to now.",
                        },
                    },
                    "required": ["mood_value"],
                },
                "auth_required": True,
                "status_message": "Logging your mood...",
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
        --hb-green: #4CAF50;
        --hb-green-hover: #43A047;
        --hb-dark: #1c1c1c;
        --hb-darker: #141414;
        --hb-card: #2a2a2a;
        --hb-muted: #a3a3a3;
        --hb-white: #ffffff;
        --hb-border: #3a3a3a;
        --omi-accent: #6366f1;
        --hb-red: #ef4444;
        --hb-green-success: #22c55e;
    }
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
        font-family: 'DM Sans', -apple-system, BlinkMacSystemFont, sans-serif;
        background: linear-gradient(145deg, #141414 0%, #0f2e1a 50%, #1c1c1c 100%);
        color: var(--hb-white);
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
    .logo-hb { background: linear-gradient(135deg, #4CAF50, #81C784); }
    .logo-omi { background: linear-gradient(135deg, #6366f1, #8b5cf6); }
    .logo-plus { color: var(--hb-muted); font-size: 20px; font-weight: 500; }
    h1 {
        text-align: center;
        font-size: 28px; font-weight: 700;
        margin-bottom: 8px;
        background: linear-gradient(90deg, #ffffff, #4CAF50);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
    }
    .subtitle { text-align: center; color: var(--hb-muted); margin-bottom: 32px; font-size: 15px; }
    .card {
        background: var(--hb-card);
        border-radius: 16px;
        padding: 28px;
        margin-bottom: 20px;
        box-shadow: 0 8px 32px rgba(0,0,0,0.3);
    }
    .feature-list { list-style: none; }
    .feature-list li {
        display: flex; align-items: flex-start; gap: 12px;
        padding: 12px 0;
        border-bottom: 1px solid var(--hb-border);
        font-size: 14px; color: var(--hb-muted);
    }
    .feature-list li:last-child { border-bottom: none; }
    .feature-icon { font-size: 18px; flex-shrink: 0; margin-top: 1px; }
    .feature-title { color: var(--hb-white); font-weight: 600; display: block; margin-bottom: 2px; }
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
    .btn-primary { background: linear-gradient(135deg, #4CAF50, #43A047); }
    .btn-primary:hover { background: linear-gradient(135deg, #43A047, #388E3C); }
    .btn-danger {
        background: transparent; color: var(--hb-red);
        border: 1px solid rgba(239,68,68,0.3);
        font-size: 14px; padding: 12px;
    }
    .btn-danger:hover { background: rgba(239,68,68,0.1); }
    .form-group { margin-bottom: 20px; }
    .form-label {
        display: block; font-size: 13px; font-weight: 600;
        color: var(--hb-muted); margin-bottom: 8px; text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    .form-input {
        width: 100%; padding: 14px 16px;
        background: var(--hb-darker); border: 1px solid var(--hb-border);
        border-radius: 10px; color: var(--hb-white);
        font-family: inherit; font-size: 15px;
        transition: border-color 0.2s;
    }
    .form-input:focus { outline: none; border-color: var(--hb-green); }
    .form-input::placeholder { color: #555; }
    .form-hint { font-size: 12px; color: #666; margin-top: 6px; }
    .banner {
        border-radius: 12px; padding: 16px 20px;
        margin-bottom: 20px; display: flex; align-items: center; gap: 12px;
        font-size: 14px; font-weight: 500;
    }
    .banner-success { background: linear-gradient(135deg, rgba(34,197,94,0.15), rgba(34,197,94,0.05)); color: var(--hb-green-success); }
    .banner-error { background: linear-gradient(135deg, rgba(239,68,68,0.15), rgba(239,68,68,0.05)); color: var(--hb-red); }
    .banner-icon { font-size: 20px; }
    .examples-title { font-size: 13px; font-weight: 600; color: var(--hb-muted); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 14px; }
    .example-item {
        background: var(--hb-darker); border-radius: 10px;
        padding: 12px 16px; margin-bottom: 8px;
        font-size: 14px; color: var(--hb-muted);
        border-left: 3px solid var(--hb-green);
    }
</style>
"""


def _html_page(body: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Habitify for Omi</title>
    {_PAGE_STYLE}
</head>
<body>
    <div class="container">
        <div class="logo-row">
            <div class="logo-icon logo-hb">H</div>
            <span class="logo-plus">+</span>
            <div class="logo-icon logo-omi">omi</div>
        </div>
        <h1>Habitify for Omi</h1>
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
        <p class="subtitle">Track and manage your habits through Omi chat.</p>
        <div class="card">
            <p style="color: var(--hb-muted); font-size: 14px; text-align: center;">
                Open this page from the Omi app to get started.
            </p>
        </div>"""
        return HTMLResponse(_html_page(body))

    creds = get_credentials(uid)
    if creds:
        body = f"""
        <p class="subtitle">Your habits are ready to manage.</p>
        <div class="banner banner-success">
            <span class="banner-icon">&#10003;</span>
            Connected to Habitify
        </div>
        <div class="card">
            <div class="examples-title">Try asking Omi</div>
            <div class="example-item">How am I doing today?</div>
            <div class="example-item">Mark meditation as done</div>
            <div class="example-item">Show my exercise logs this week</div>
            <div class="example-item">Log my mood as good</div>
            <div class="example-item">Add a note to my reading habit: finished chapter 5</div>
        </div>
        <a href="/disconnect?uid={uid}" class="btn btn-danger">Disconnect Habitify</a>"""
        return HTMLResponse(_html_page(body))

    body = f"""
    <p class="subtitle">Connect your Habitify account to manage habits through Omi chat.</p>
    <div class="card">
        <ul class="feature-list">
            <li>
                <span class="feature-icon">&#9989;</span>
                <div><span class="feature-title">Track Habits</span>Mark habits complete or log progress with your voice</div>
            </li>
            <li>
                <span class="feature-icon">&#128202;</span>
                <div><span class="feature-title">Daily Summary</span>Get an overview of your habit progress for any day</div>
            </li>
            <li>
                <span class="feature-icon">&#128203;</span>
                <div><span class="feature-title">Habit Logs</span>Review your habit history and streaks</div>
            </li>
            <li>
                <span class="feature-icon">&#128578;</span>
                <div><span class="feature-title">Mood Tracking</span>Log your mood and add notes to habits</div>
            </li>
        </ul>
    </div>
    <div class="card">
        <form method="POST" action="/auth/habitify?uid={uid}">
            <div class="form-group">
                <label class="form-label" for="api_key">Habitify API Key</label>
                <input class="form-input" type="password" id="api_key" name="api_key"
                       placeholder="&#8226;&#8226;&#8226;&#8226;&#8226;&#8226;&#8226;&#8226;&#8226;&#8226;&#8226;&#8226;" required>
                <div class="form-hint">Found in Habitify &rarr; Settings &rarr; API Credential</div>
            </div>
            <button type="submit" class="btn btn-primary">Connect Habitify</button>
        </form>
    </div>"""
    return HTMLResponse(_html_page(body))


@app.get("/auth/habitify", response_class=HTMLResponse)
async def auth_habitify_redirect(uid: str = Query(...)):
    return RedirectResponse(url=f"/?uid={uid}")


@app.post("/auth/habitify", response_class=HTMLResponse)
async def auth_habitify(request: Request, uid: str = Query(...)):
    form = await request.form()
    api_key = form.get("api_key", "").strip()

    if not api_key:
        body = """
        <p class="subtitle">Something went wrong.</p>
        <div class="banner banner-error">
            <span class="banner-icon">&#9888;</span>
            API key is required.
        </div>
        <a href="javascript:history.back()" class="btn btn-primary">Go Back</a>"""
        return HTMLResponse(_html_page(body), status_code=400)

    # Validate credentials by making a test API call
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{HABITIFY_API_BASE}/habits",
                headers={"Authorization": api_key, "Accept": "application/json"},
            )
            if resp.status_code in (401, 403):
                body = f"""
                <p class="subtitle">Something went wrong.</p>
                <div class="banner banner-error">
                    <span class="banner-icon">&#9888;</span>
                    Invalid API key. Check your Habitify API credential.
                </div>
                <a href="/?uid={uid}" class="btn btn-primary">Try Again</a>"""
                return HTMLResponse(_html_page(body), status_code=401)
            resp.raise_for_status()
    except httpx.HTTPStatusError:
        body = f"""
        <p class="subtitle">Something went wrong.</p>
        <div class="banner banner-error">
            <span class="banner-icon">&#9888;</span>
            Could not connect to Habitify. Please verify your API key.
        </div>
        <a href="/?uid={uid}" class="btn btn-primary">Try Again</a>"""
        return HTMLResponse(_html_page(body), status_code=400)

    save_credentials(uid, api_key)
    return RedirectResponse(url=f"/?uid={uid}", status_code=303)


@app.get("/setup/habitify")
async def check_setup(uid: Optional[str] = Query(None)):
    if not uid:
        return {"is_setup_completed": False}
    creds = get_credentials(uid)
    return {"is_setup_completed": creds is not None}


@app.get("/disconnect", response_class=HTMLResponse)
async def disconnect(uid: str = Query(...)):
    delete_credentials(uid)
    return RedirectResponse(url=f"/?uid={uid}")


# ---------------------------------------------------------------------------
# Chat tool endpoints
# ---------------------------------------------------------------------------


@app.post("/tools/list_habits", response_model=ChatToolResponse, tags=["chat_tools"])
async def tool_list_habits(request: Request):
    body = await request.json()
    uid = body.get("uid")
    err, creds = _require_creds(uid)
    if err:
        return err

    api_key = creds["api_key"]
    area_name = body.get("area_name")

    try:
        data = await habitify_request("GET", "/habits", api_key)
        habits = data.get("data", [])
    except httpx.HTTPStatusError as e:
        return ChatToolResponse(error=f"Habitify API error: {e.response.status_code}")
    except Exception as e:
        return ChatToolResponse(error=f"Failed to fetch habits: {str(e)}")

    if not habits:
        return ChatToolResponse(result="You don't have any habits in Habitify yet.")

    # Fetch areas for name mapping
    area_map = {}
    try:
        areas_data = await habitify_request("GET", "/areas", api_key)
        for area in areas_data.get("data", []):
            area_map[area["id"]] = area["name"]
    except Exception:
        pass

    # Filter by area if specified
    if area_name:
        area_name_lower = area_name.lower()
        habits = [h for h in habits if area_map.get(h.get("area", {}).get("id", ""), "").lower() == area_name_lower]
        if not habits:
            available = ", ".join(sorted(set(area_map.values()))) if area_map else "none"
            return ChatToolResponse(result=f'No habits found in area "{area_name}". Available areas: {available}')

    # Filter out archived by default
    active_habits = [h for h in habits if not h.get("is_archived", False)]

    lines = [f"**Your Habits** ({len(active_habits)} active)", ""]
    lines.extend(["| Habit | Area | Goal |", "|-------|------|------|"])

    for h in active_habits:
        name = h.get("name", "?")
        area_id = h.get("area", {}).get("id", "") if isinstance(h.get("area"), dict) else ""
        area = area_map.get(area_id, "-")
        goal = h.get("goal")
        if goal and goal.get("value"):
            goal_str = f'{goal["value"]} {goal.get("unit_type", "")}/{goal.get("periodicity", "day")}'
        else:
            goal_str = "Simple"
        lines.append(f"| {name} | {area} | {goal_str} |")

    archived = [h for h in habits if h.get("is_archived", False)]
    if archived:
        lines.append(f"\n*{len(archived)} archived habit(s) not shown.*")

    return ChatToolResponse(result="\n".join(lines))


@app.post("/tools/get_habit_status", response_model=ChatToolResponse, tags=["chat_tools"])
async def tool_get_habit_status(request: Request):
    body = await request.json()
    uid = body.get("uid")
    err, creds = _require_creds(uid)
    if err:
        return err

    api_key = creds["api_key"]
    habit_name = body.get("habit_name")
    if not habit_name:
        return ChatToolResponse(error="Habit name is required.")

    target_date = body.get("target_date") or _default_target_date()

    habit, note = await _resolve_habit(habit_name, api_key)
    if not habit:
        return ChatToolResponse(error=note or f'Could not find habit "{habit_name}".')

    try:
        status_data = await habitify_request(
            "GET", f'/status/{habit["id"]}', api_key, params={"target_date": target_date}
        )
        status_info = status_data.get("data", {})
    except httpx.HTTPStatusError as e:
        return ChatToolResponse(error=f"Habitify API error: {e.response.status_code}")
    except Exception as e:
        return ChatToolResponse(error=f"Failed to get status: {str(e)}")

    status = status_info.get("status", "none")
    progress = status_info.get("progress")

    lines = []
    if note:
        lines.append(note)
        lines.append("")

    status_display = {"completed": "Completed", "in_progress": "In Progress", "skipped": "Skipped", "none": "Not Done"}
    lines.append(f'**{habit["name"]}** - {status_display.get(status, status)}')

    if progress:
        current = progress.get("current_value", 0)
        target = progress.get("target_value", 0)
        unit = progress.get("unit_type", "")
        if target > 0:
            pct = min(100, (current / target) * 100)
            lines.append(f"Progress: {current}/{target} {unit} ({pct:.0f}%)")
        else:
            lines.append(f"Progress: {current} {unit}")

    return ChatToolResponse(result="\n".join(lines))


@app.post("/tools/complete_habit", response_model=ChatToolResponse, tags=["chat_tools"])
async def tool_complete_habit(request: Request):
    body = await request.json()
    uid = body.get("uid")
    err, creds = _require_creds(uid)
    if err:
        return err

    api_key = creds["api_key"]
    habit_name = body.get("habit_name")
    if not habit_name:
        return ChatToolResponse(error="Habit name is required.")

    value = body.get("value")
    target_date = body.get("target_date") or _default_target_date()

    habit, note = await _resolve_habit(habit_name, api_key)
    if not habit:
        return ChatToolResponse(error=note or f'Could not find habit "{habit_name}".')

    goal = habit.get("goal")
    lines = []
    if note:
        lines.append(note)
        lines.append("")

    try:
        if goal and goal.get("value"):
            # Goal-based habit: log progress
            log_value = value if value is not None else goal.get("value", 1)
            unit_type = goal.get("unit_type", "")
            await habitify_request(
                "POST",
                f'/logs/{habit["id"]}',
                api_key,
                json_body={"unit_type": unit_type, "value": log_value, "target_date": target_date},
            )
            lines.append(f'Logged **{log_value} {unit_type}** for **{habit["name"]}**.')
        else:
            # Simple habit: mark as completed
            await habitify_request(
                "PUT",
                f'/status/{habit["id"]}',
                api_key,
                json_body={"status": "completed", "target_date": target_date},
            )
            lines.append(f'Marked **{habit["name"]}** as completed.')
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 402:
            return ChatToolResponse(error="You've reached the Habitify free plan limit. Please upgrade to log more.")
        return ChatToolResponse(error=f"Habitify API error: {e.response.status_code}")
    except Exception as e:
        return ChatToolResponse(error=f"Failed to complete habit: {str(e)}")

    return ChatToolResponse(result="\n".join(lines))


@app.post("/tools/get_habit_logs", response_model=ChatToolResponse, tags=["chat_tools"])
async def tool_get_habit_logs(request: Request):
    body = await request.json()
    uid = body.get("uid")
    err, creds = _require_creds(uid)
    if err:
        return err

    api_key = creds["api_key"]
    habit_name = body.get("habit_name")
    if not habit_name:
        return ChatToolResponse(error="Habit name is required.")

    default_from, default_to = _default_date_range()
    from_date = body.get("from_date") or default_from
    to_date = body.get("to_date") or default_to

    habit, note = await _resolve_habit(habit_name, api_key)
    if not habit:
        return ChatToolResponse(error=note or f'Could not find habit "{habit_name}".')

    try:
        logs_data = await habitify_request(
            "GET", f'/logs/{habit["id"]}', api_key, params={"from": from_date, "to": to_date}
        )
        logs = logs_data.get("data", [])
    except httpx.HTTPStatusError as e:
        return ChatToolResponse(error=f"Habitify API error: {e.response.status_code}")
    except Exception as e:
        return ChatToolResponse(error=f"Failed to fetch logs: {str(e)}")

    lines = []
    if note:
        lines.append(note)
        lines.append("")

    if not logs:
        lines.append(f'No logs found for **{habit["name"]}** in the selected period.')
        return ChatToolResponse(result="\n".join(lines))

    lines.append(f'**{habit["name"]}** Logs ({len(logs)} entries)')
    lines.append("")
    lines.extend(["| Date | Value | Unit |", "|------|-------|------|"])

    for log in logs:
        created = log.get("created_date", "?")
        if isinstance(created, str) and "T" in created:
            created = created.split("T")[0]
        val = log.get("value", "-")
        unit = log.get("unit_type", "-")
        lines.append(f"| {created} | {val} | {unit} |")

    return ChatToolResponse(result="\n".join(lines))


@app.post("/tools/daily_summary", response_model=ChatToolResponse, tags=["chat_tools"])
async def tool_daily_summary(request: Request):
    body = await request.json()
    uid = body.get("uid")
    err, creds = _require_creds(uid)
    if err:
        return err

    api_key = creds["api_key"]
    target_date = body.get("target_date") or _default_target_date()

    try:
        data = await habitify_request("GET", "/habits", api_key)
        habits = data.get("data", [])
    except httpx.HTTPStatusError as e:
        return ChatToolResponse(error=f"Habitify API error: {e.response.status_code}")
    except Exception as e:
        return ChatToolResponse(error=f"Failed to fetch habits: {str(e)}")

    active_habits = [h for h in habits if not h.get("is_archived", False)]
    if not active_habits:
        return ChatToolResponse(result="You don't have any active habits in Habitify.")

    # Fetch statuses concurrently
    async def _get_status(habit: dict) -> tuple[dict, dict]:
        try:
            status_data = await habitify_request(
                "GET", f'/status/{habit["id"]}', api_key, params={"target_date": target_date}
            )
            return habit, status_data.get("data", {})
        except Exception:
            return habit, {}

    results = await asyncio.gather(*[_get_status(h) for h in active_habits[:50]])

    completed = 0
    total = len(results)
    lines = []
    lines.extend(["| Habit | Status | Progress |", "|-------|--------|----------|"])

    for habit, status_info in results:
        status = status_info.get("status", "none")
        if status == "completed":
            completed += 1

        status_display = {"completed": "Done", "in_progress": "In Progress", "skipped": "Skipped", "none": "-"}
        progress = status_info.get("progress")
        if progress and progress.get("target_value"):
            current = progress.get("current_value", 0)
            target = progress.get("target_value", 0)
            unit = progress.get("unit_type", "")
            prog_str = f"{current}/{target} {unit}"
        else:
            prog_str = "-"

        lines.append(f'| {habit["name"]} | {status_display.get(status, status)} | {prog_str} |')

    pct = (completed / total * 100) if total > 0 else 0
    header = [
        f"**Daily Summary** ({target_date.split('T')[0] if 'T' in target_date else target_date})",
        f"**Completion: {completed}/{total} habits ({pct:.0f}%)**",
        "",
    ]

    return ChatToolResponse(result="\n".join(header + lines))


@app.post("/tools/add_note", response_model=ChatToolResponse, tags=["chat_tools"])
async def tool_add_note(request: Request):
    body = await request.json()
    uid = body.get("uid")
    err, creds = _require_creds(uid)
    if err:
        return err

    api_key = creds["api_key"]
    habit_name = body.get("habit_name")
    content = body.get("content")
    if not habit_name:
        return ChatToolResponse(error="Habit name is required.")
    if not content:
        return ChatToolResponse(error="Note content is required.")

    target_date = body.get("target_date") or _default_target_date()

    habit, note = await _resolve_habit(habit_name, api_key)
    if not habit:
        return ChatToolResponse(error=note or f'Could not find habit "{habit_name}".')

    lines = []
    if note:
        lines.append(note)
        lines.append("")

    try:
        await habitify_request(
            "POST",
            f'/notes/{habit["id"]}',
            api_key,
            json_body={"content": content, "created": target_date},
        )
        lines.append(f'Note added to **{habit["name"]}**: "{content}"')
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 402:
            return ChatToolResponse(error="You've reached the Habitify free plan limit for notes. Please upgrade.")
        return ChatToolResponse(error=f"Habitify API error: {e.response.status_code}")
    except Exception as e:
        return ChatToolResponse(error=f"Failed to add note: {str(e)}")

    return ChatToolResponse(result="\n".join(lines))


@app.post("/tools/log_mood", response_model=ChatToolResponse, tags=["chat_tools"])
async def tool_log_mood(request: Request):
    body = await request.json()
    uid = body.get("uid")
    err, creds = _require_creds(uid)
    if err:
        return err

    api_key = creds["api_key"]
    mood_value = body.get("mood_value")
    if mood_value is None:
        return ChatToolResponse(error="Mood value is required (1-5).")

    mood_value = int(mood_value)
    if mood_value < 1 or mood_value > 5:
        return ChatToolResponse(error="Mood value must be between 1 (terrible) and 5 (excellent).")

    target_date = body.get("target_date") or _default_target_date()

    mood_labels = {1: "Terrible", 2: "Bad", 3: "Okay", 4: "Good", 5: "Excellent"}

    try:
        await habitify_request(
            "POST",
            "/moods",
            api_key,
            json_body={"value": str(mood_value), "created_at": target_date},
        )
        return ChatToolResponse(result=f'Mood logged as **{mood_labels[mood_value]}** ({mood_value}/5).')
    except httpx.HTTPStatusError as e:
        return ChatToolResponse(error=f"Habitify API error: {e.response.status_code}")
    except Exception as e:
        return ChatToolResponse(error=f"Failed to log mood: {str(e)}")
