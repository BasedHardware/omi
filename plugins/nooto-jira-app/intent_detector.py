"""GPT-4o intent extraction for proactive flows.

Slice D owns this file. Both functions call the OpenAI client with
`model="gpt-4o"`, `response_format={"type":"json_object"}`, `temperature=0.2`.

System prompts mirror plan §D. Both prompts:
    - inject today's date, timezone, current user, available projects
    - require strict JSON output matching the Pydantic schema
    - default assignee to current user; due_date conversion to YYYY-MM-DD

Cost guardrails (cooldowns, daily caps) live in routes/proactive.py — this
module does not enforce them.
"""

import json
import logging
import os
import uuid
from datetime import datetime, timezone as dt_timezone
from typing import Any, Optional

from openai import AsyncOpenAI
from rapidfuzz import fuzz

from models import JiraIntent, JiraTicketCandidate

log = logging.getLogger("nooto-jira-app.intent_detector")

_client: Optional[AsyncOpenAI] = None


def _openai_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY", ""))
    return _client


def _format_projects(projects: list[dict[str, Any]]) -> str:
    """Render projects as `KEY — Name` per line."""
    lines: list[str] = []
    for p in projects or []:
        key = p.get("key") or ""
        name = p.get("name") or ""
        if key:
            lines.append(f"{key} — {name}")
    return "\n".join(lines) if lines else "(none available)"


def _live_system_prompt(
    today: str,
    tz: str,
    user_name: str,
    user_account_id: str,
    projects_block: str,
) -> str:
    return f"""You are a Jira ticket intent detector for a real-time voice assistant.
CURRENT CONTEXT: today={today}, tz={tz}, current_user={user_name}/{user_account_id}.

Available projects (KEY — Name):
{projects_block}

Issue types: Task | Bug | Story | Epic.

Decide whether the speaker is asking to FILE a ticket RIGHT NOW. Be conservative.
Casual mentions ("the auth thing is broken") are NOT intents.

PROJECT MATCHING: exact key > exact name > fuzzy. If unsure between two, lower
confidence to <=0.7. If no project, project_key=null and confidence <=0.6.

ASSIGNEE: default to current user ({user_account_id}). Only different if the
speaker explicitly names a teammate verifiably on the project; else null and
mention the name in description.

DUE DATE: convert relative ("tomorrow", "next sprint") to YYYY-MM-DD; null if
past or unspecified.

CONFIDENCE:
  0.85+ : explicit trigger phrase + clear summary + identifiable project.
  0.6-0.85: clear intent but ambiguous.
  <0.6  : any doubt -> detected:false.

Output JSON only matching this schema (all keys required, use null where noted):
{{
  "detected": bool,
  "confidence": float,
  "project_key": string | null,
  "issue_type": "Task" | "Bug" | "Story" | "Epic",
  "summary": string,
  "description": string,
  "priority": "Highest" | "High" | "Medium" | "Low" | "Lowest",
  "due_date": "YYYY-MM-DD" | null,
  "assignee_account_id": string | null,
  "reasoning": string
}}
"""


def _memory_system_prompt(
    today: str,
    tz: str,
    user_name: str,
    user_account_id: str,
    projects_block: str,
) -> str:
    return f"""You are a Jira ticket suggester. Propose UP TO 3 tickets the user
would likely file from a finished conversation. Quality over quantity — prefer
returning 0 over weak suggestions.

CURRENT CONTEXT: today={today}, tz={tz}, current_user={user_name}/{user_account_id}.

Available projects (KEY — Name):
{projects_block}

Issue types: Task | Bug | Story | Epic.

INPUT: structured.title, overview, action_items[].description, action_items[].due_at,
events, transcript_tail (last ~6k tokens).

RULES:
- Each suggestion = ONE concrete deliverable.
- Strongly prefer items in action_items (pre-vetted commitments).
- source_quote MUST be a verbatim excerpt <=200 chars taken from transcript_tail
  or action_items[].description.
- Project resolution same as live flow; OMIT a suggestion if no project fits
  (don't guess).
- Issue type: Bug=defect, Story=user-facing, Epic=multi-week, else Task.
- Confidence >= 0.6 to emit; otherwise drop.
- assignee_account_id defaults to {user_account_id}.
- DUE DATE: convert relative dates to YYYY-MM-DD; null if past or unspecified.

Output JSON only:
{{
  "suggestions": [
    {{
      "detected": true,
      "confidence": float,
      "project_key": string | null,
      "issue_type": "Task" | "Bug" | "Story" | "Epic",
      "summary": string,
      "description": string,
      "priority": "Highest" | "High" | "Medium" | "Low" | "Lowest",
      "due_date": "YYYY-MM-DD" | null,
      "assignee_account_id": string | null,
      "reasoning": string,
      "source_quote": string
    }}
  ]
}}

If you find nothing worth filing, return {{"suggestions": []}}.
"""


def _user_name(current_user: dict[str, Any]) -> str:
    return (
        current_user.get("displayName")
        or current_user.get("display_name")
        or current_user.get("name")
        or current_user.get("emailAddress")
        or "unknown"
    )


def _user_account_id(current_user: dict[str, Any]) -> str:
    return current_user.get("accountId") or current_user.get("account_id") or ""


async def detect_jira_intent(
    segments: list[dict[str, Any]],
    projects: list[dict[str, Any]],
    current_user: dict[str, Any],
    *,
    timezone: str = "UTC",
) -> JiraIntent:
    """Classify whether a live transcript snippet asks to file a Jira ticket NOW."""
    today = datetime.now(dt_timezone.utc).date().isoformat()
    user_name = _user_name(current_user)
    account_id = _user_account_id(current_user)
    projects_block = _format_projects(projects)

    # Cap input — last 30 segments, last 6000 chars of joined text.
    tail = (segments or [])[-30:]
    joined = " ".join((s.get("text") or "").strip() for s in tail if (s.get("text") or "").strip())
    if len(joined) > 6000:
        joined = joined[-6000:]

    if not joined:
        return JiraIntent(detected=False, reasoning="empty input")

    system_prompt = _live_system_prompt(today, timezone, user_name, account_id, projects_block)
    user_payload = f"Live transcript snippet (latest):\n\n{joined}"

    try:
        client = _openai_client()
        response = await client.chat.completions.create(
            model="gpt-4o",
            response_format={"type": "json_object"},
            temperature=0.2,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_payload},
            ],
        )
        raw = response.choices[0].message.content or "{}"
        data = json.loads(raw)
        # Default assignee to current user when null and we have an account id.
        if not data.get("assignee_account_id") and account_id:
            data["assignee_account_id"] = account_id
        return JiraIntent(**data)
    except Exception as e:
        log.warning("detect_jira_intent failed: %s", e)
        return JiraIntent(detected=False, reasoning=str(e))


async def suggest_tickets_from_memory(
    memory: dict[str, Any],
    projects: list[dict[str, Any]],
    current_user: dict[str, Any],
    *,
    timezone: str = "UTC",
) -> list[JiraTicketCandidate]:
    """Return up to 3 ticket candidates for a finished conversation."""
    today = datetime.now(dt_timezone.utc).date().isoformat()
    user_name = _user_name(current_user)
    account_id = _user_account_id(current_user)
    projects_block = _format_projects(projects)

    structured = (memory or {}).get("structured") or {}
    transcript_segments = (memory or {}).get("transcript_segments") or []
    transcript_text = " ".join(
        (s.get("text") or "").strip() for s in transcript_segments if isinstance(s, dict)
    ).strip()
    # Trim to last ~6000 tokens via char proxy (last 24000 chars).
    if len(transcript_text) > 24000:
        transcript_text = transcript_text[-24000:]

    payload = {
        "title": structured.get("title") or "",
        "overview": structured.get("overview") or "",
        "action_items": structured.get("action_items") or [],
        "events": structured.get("events") or [],
        "transcript_tail": transcript_text,
    }

    system_prompt = _memory_system_prompt(today, timezone, user_name, account_id, projects_block)
    user_payload = json.dumps(payload, ensure_ascii=False)

    try:
        client = _openai_client()
        response = await client.chat.completions.create(
            model="gpt-4o",
            response_format={"type": "json_object"},
            temperature=0.2,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_payload},
            ],
        )
        raw = response.choices[0].message.content or "{}"
        data = json.loads(raw)
        suggestions = data.get("suggestions") or []
        results: list[JiraTicketCandidate] = []
        for item in suggestions[:3]:
            if not isinstance(item, dict):
                continue
            if not item.get("assignee_account_id") and account_id:
                item["assignee_account_id"] = account_id
            item.setdefault("suggestion_id", uuid.uuid4().hex)
            item.setdefault("source_quote", "")
            try:
                results.append(JiraTicketCandidate(**item))
            except Exception as ve:
                log.warning("Skipping invalid suggestion candidate: %s", ve)
        return results
    except Exception as e:
        log.warning("suggest_tickets_from_memory failed: %s", e)
        return []


def resolve_project(
    spoken: str,
    projects: list[dict[str, Any]],
) -> tuple[Optional[dict[str, Any]], float]:
    """Exact key > exact name > rapidfuzz token_set_ratio >=80 > LLM disambiguator.

    Returns (project, confidence). (None, 0.0) means no fit — caller must
    route to suggestion path rather than auto-file.
    """
    if not spoken or not projects:
        return None, 0.0

    s_lower = spoken.strip().lower()
    if not s_lower:
        return None, 0.0

    # 1. Exact key match (case-insensitive).
    for p in projects:
        key = (p.get("key") or "").lower()
        if key and key == s_lower:
            return p, 1.0

    # 2. Exact name match.
    for p in projects:
        name = (p.get("name") or "").lower()
        if name and name == s_lower:
            return p, 0.95

    # 3. rapidfuzz token_set_ratio >= 80.
    best: Optional[dict[str, Any]] = None
    best_ratio = 0.0
    for p in projects:
        name = p.get("name") or ""
        if not name:
            continue
        ratio = float(fuzz.token_set_ratio(spoken, name))
        if ratio > best_ratio:
            best_ratio = ratio
            best = p
    if best is not None and best_ratio >= 80.0:
        return best, best_ratio / 100.0

    # 4. TODO: LLM disambiguator when multiple within 5 points (skipped for v1).

    # 5. Fail open.
    return None, 0.0
