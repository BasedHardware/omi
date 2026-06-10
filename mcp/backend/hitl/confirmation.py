"""
hitl/confirmation.py

confirmation_node is called via Send("confirmation_node", payload) from fanout.

Key design: instead of relying on the planner to pre-fill email/calendar fields
(which fails when the body depends on retrieved context), we call the LLM
*inside confirmation_node* to draft the fields using:
  - task.parameters  (whatever the planner already filled in)
  - payload["context"] (already fetched by the context layer before this runs)
  - user_query
  - user_prefs (extracted from conversation_history — global memory tier)

This means the modal is always pre-filled, even for queries like:
  "search my docs and email the summary to john@example.com"
  "check the club schedule and create a calendar event for the next meeting"

Flow:
  planning → context fetch → execute_tasks → fanout → confirmation_node
                                                            ↓
                                                 draft fields with LLM
                                                 (now includes user prefs)
                                                            ↓
                                                   interrupt(json_string)
                                                            ↓
                                                  [GRAPH FREEZES — modal shows]
                                                            ↓
                                                  user edits + approves/rejects
                                                            ↓
                                               inject edits → hitl_google_worker
"""
from __future__ import annotations
import json
import logging
import os
import re

from langgraph.types import interrupt
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Lightweight LLM just for field drafting — fast and cheap
_draft_llm = ChatGroq(
    model=os.getenv("WORKER_MODEL", "llama-3.1-8b-instant"),
    temperature=0.2,
    api_key=os.getenv("GROQ_API_KEY"),
)

WRITE_SIGNALS = {
    "send", "email", "mail", "reply", "forward", "draft",
    "delete", "trash", "remove", "mark as",
    "create", "schedule", "add event", "update", "modify",
    "cancel event", "reschedule", "write", "compose", "submit",
}
READ_SIGNALS = {
    "search", "list", "get", "read", "summarize", "summary",
    "fetch", "find", "show", "display", "retrieve", "check",
    "look up", "lookup", "view", "open", "count",
}
GOOGLE_WORKER_TYPES = {
    "gmail", "calendar", "google_workspace", "google_gmail", "google_calendar",
}


def _is_google_task(task: dict) -> bool:
    wt = (task.get("worker_type") or "").lower()
    gs = (task.get("google_service") or "").lower()
    return any(kw in wt or kw in gs for kw in GOOGLE_WORKER_TYPES)


def needs_confirmation(task: dict) -> bool:
    """Returns True if this task needs human approval before executing."""
    if not _is_google_task(task):
        return False

    wt = (task.get("worker_type") or "").lower()
    gs = (task.get("google_service") or "").lower()
    params = task.get("parameters") or {}

    if "gmail" in wt or gs == "gmail":
        if params.get("to") or params.get("body") or params.get("subject"):
            return True

    if "calendar" in wt or gs == "calendar":
        if params.get("summary") or params.get("title") or params.get("start"):
            return True

    combined = (
        (task.get("description") or "").lower() + " " +
        (task.get("title") or "").lower()
    )
    is_read  = any(sig in combined for sig in READ_SIGNALS)
    is_write = any(sig in combined for sig in WRITE_SIGNALS)
    if is_read and not is_write:
        return False
    return is_write


# ── Field drafting ─────────────────────────────────────────────────────────────

def _call_draft_llm(system: str, prompt: str) -> dict:
    """Shared LLM call + JSON parse for field drafting. Returns {} on failure."""
    try:
        response = _draft_llm.invoke([
            SystemMessage(content=system),
            HumanMessage(content=prompt),
        ])
        raw = (response.content or "").strip()
        # Strip markdown fences if model wraps the JSON
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw.strip())
    except Exception as exc:
        logger.warning(f"HITL: draft LLM call failed: {exc}")
        return {}


def _extract_user_prefs(conversation_history: list) -> str:
    """
    Pull the [User preferences: ...] line out of conversation_history
    (which is the output of session_memory.build_context()).
    Returns empty string if not present.
    """
    for line in (conversation_history or []):
        stripped = (line or "").strip()
        if stripped.startswith("[User preferences:"):
            return stripped
    return ""


def _draft_gmail_fields(
    task: dict,
    user_query: str,
    context: str,
    user_prefs: str = "",
) -> dict:
    """
    Draft to/subject/body.
    - If planner already filled all three, skip the LLM call entirely.
    - Otherwise call the LLM with task params + fetched context + user prefs.
    """
    params = task.get("parameters") or {}

    # Fast path: planner already did the work
    if params.get("to") and params.get("subject") and params.get("body"):
        return {
            "to":      params["to"],
            "subject": params["subject"],
            "body":    params["body"],
        }

    system = (
        "You are an email drafting assistant. "
        "Draft the email fields based on the user's request, any retrieved context, "
        "and the user's known preferences if provided. "
        "Return ONLY a raw JSON object with keys: to, subject, body. "
        "No markdown fences, no explanation."
    )
    prompt = "\n\n".join(filter(None, [
        user_prefs,                                                    # ← global memory
        f"User request: {user_query}",
        f"Planner params: {json.dumps(params)}" if params else "",
        f"Retrieved context:\n{context[:2000]}"  if context else "",
        "Draft the email. Return JSON only.",
    ]))

    drafted = _call_draft_llm(system, prompt)
    return {
        "to":      drafted.get("to",      params.get("to",      "")),
        "subject": drafted.get("subject", params.get("subject", "")),
        "body":    drafted.get("body",    params.get("body",    "")),
    }


def _is_valid_iso_datetime(dt_str: str) -> bool:
    """Basic validation for ISO 8601 datetime with timezone."""
    if not dt_str:
        return False
    pattern = r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}([+-]\d{2}:\d{2}|Z)$'
    return bool(re.match(pattern, dt_str))


def _parse_natural_datetime(text: str) -> str:
    """
    Parse natural language time expressions into ISO 8601 datetime.
    Handles: "tonight", "tomorrow", "next monday", "10pm", etc.
    """
    if not text or not isinstance(text, str):
        return ""

    text = text.lower().strip()
    now = datetime.now()
    today = now.date()

    time_mappings = {
        "tonight":         (today, 22, 0),
        "tonite":          (today, 22, 0),
        "this evening":    (today, 19, 0),
        "evening":         (today, 19, 0),
        "this morning":    (today, 9,  0),
        "morning":         (today, 9,  0),
        "this afternoon":  (today, 14, 0),
        "afternoon":       (today, 14, 0),
        "noon":            (today, 12, 0),
        "midnight":        (today, 0,  0),
        "mid-day":         (today, 12, 0),
        "midday":          (today, 12, 0),
        "tomorrow":                  (today + timedelta(days=1), 10, 0),
        "tmr":                       (today + timedelta(days=1), 10, 0),
        "tmrw":                      (today + timedelta(days=1), 10, 0),
        "tomorrow morning":          (today + timedelta(days=1), 9,  0),
        "tomorrow afternoon":        (today + timedelta(days=1), 14, 0),
        "tomorrow evening":          (today + timedelta(days=1), 19, 0),
        "tomorrow night":            (today + timedelta(days=1), 22, 0),
        "yesterday":       (today - timedelta(days=1), 10, 0),
        "yday":            (today - timedelta(days=1), 10, 0),
        "now":             (today, now.hour, now.minute),
        "right now":       (today, now.hour, now.minute),
        "immediately":     (today, now.hour, now.minute + 5),
        "asap":            (today, now.hour, now.minute + 5),
    }

    if text in time_mappings:
        date, hour, minute = time_mappings[text]
        dt = datetime.combine(date, datetime.min.time()).replace(hour=hour, minute=minute)
        return dt.strftime("%Y-%m-%dT%H:%M:%S+05:30")

    match = re.match(
        r'(tonight|tonite|tomorrow|tmr|tmrw|yesterday)\s+(?:at\s+)?'
        r'(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)?',
        text,
    )
    if match:
        day_word, hour_str, minute_str, ampm = match.groups()
        hour   = int(hour_str)
        minute = int(minute_str) if minute_str else 0
        if ampm:
            ampm = ampm.lower().replace('.', '')
            if ampm == 'pm' and hour < 12:
                hour += 12
            elif ampm == 'am' and hour == 12:
                hour = 0
        if day_word in ('tonight', 'tonite'):
            date = today
            if hour < 12:
                hour += 12
        elif day_word in ('tomorrow', 'tmr', 'tmrw'):
            date = today + timedelta(days=1)
        else:
            date = today - timedelta(days=1)
        dt = datetime.combine(date, datetime.min.time()).replace(hour=hour, minute=minute)
        return dt.strftime("%Y-%m-%dT%H:%M:%S+05:30")

    days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
    for i, day in enumerate(days):
        if re.search(rf'(?:next|this\s+)?{day}', text):
            target_weekday  = i
            current_weekday = today.weekday()
            if 'next' in text:
                days_ahead = (target_weekday - current_weekday) % 7 or 7
            else:
                days_ahead = (target_weekday - current_weekday) % 7
            target_date = today + timedelta(days=days_ahead)
            time_match = re.search(
                r'(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)?', text
            )
            if time_match:
                h_str, m_str, ap = time_match.groups()
                hour   = int(h_str)
                minute = int(m_str) if m_str else 0
                if ap:
                    ap = ap.lower().replace('.', '')
                    if ap == 'pm' and hour < 12:
                        hour += 12
                    elif ap == 'am' and hour == 12:
                        hour = 0
            else:
                hour, minute = 10, 0
            dt = datetime.combine(target_date, datetime.min.time()).replace(
                hour=hour, minute=minute
            )
            return dt.strftime("%Y-%m-%dT%H:%M:%S+05:30")

    time_match = re.match(r'^(\d{1,2})(?::(\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)?$', text)
    if time_match:
        h_str, m_str, ap = time_match.groups()
        hour   = int(h_str)
        minute = int(m_str) if m_str else 0
        if ap:
            ap = ap.lower().replace('.', '')
            if ap == 'pm' and hour < 12:
                hour += 12
            elif ap == 'am' and hour == 12:
                hour = 0
        target_dt = datetime.combine(today, datetime.min.time()).replace(
            hour=hour, minute=minute
        )
        if target_dt < now:
            target_dt += timedelta(days=1)
        return target_dt.strftime("%Y-%m-%dT%H:%M:%S+05:30")

    return ""


def _normalize_datetime(dt_str: str) -> str:
    """Replace placeholders and natural language with actual ISO 8601 dates."""
    if not dt_str:
        return ""

    parsed = _parse_natural_datetime(dt_str)
    if parsed and _is_valid_iso_datetime(parsed):
        return parsed

    today = datetime.now()
    replacements = {
        "<today>":     today.strftime("%Y-%m-%d"),
        "<tomorrow>":  (today + timedelta(days=1)).strftime("%Y-%m-%d"),
        "<yesterday>": (today - timedelta(days=1)).strftime("%Y-%m-%d"),
        "now":         today.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    result = dt_str
    for placeholder, value in replacements.items():
        result = result.replace(placeholder, value)

    match = re.match(r'<(\w+)>T(\d{2}):(\d{2}):(\d{2})', result)
    if match:
        day_word, hour, minute, second = match.groups()
        dl = day_word.lower()
        if dl in ("today", "now", "current", "tonight", "tonite"):
            date_part = today.strftime("%Y-%m-%d")
        elif dl in ("tomorrow", "tmr", "tmrw", "next day"):
            date_part = (today + timedelta(days=1)).strftime("%Y-%m-%d")
        else:
            date_part = (today - timedelta(days=1)).strftime("%Y-%m-%d")
        result = f"{date_part}T{hour}:{minute}:{second}+05:30"

    if result and "T" in result and "+" not in result and result.count("-") < 3 and "Z" not in result:
        result = result + "+05:30"

    return result


def _draft_calendar_fields(
    task: dict,
    user_query: str,
    context: str,
    user_prefs: str = "",
) -> dict:
    """
    Draft title/start/end/attendees/description.
    Falls back to parsing user query directly if LLM output is invalid.
    Now accepts user_prefs from global memory for better pre-filling.
    """
    params = task.get("parameters") or {}
    title  = params.get("summary") or params.get("title", "")

    # Fast path — validate the dates first
    if title and params.get("start") and params.get("end"):
        start = _normalize_datetime(params.get("start", ""))
        end   = _normalize_datetime(params.get("end", ""))
        if start and end and _is_valid_iso_datetime(start) and _is_valid_iso_datetime(end):
            return {
                "title":       title,
                "start":       start,
                "end":         end,
                "attendees":   params.get("attendees", ""),
                "description": params.get("description", ""),
            }

    tomorrow      = datetime.now() + timedelta(days=1)
    default_start = tomorrow.replace(hour=10, minute=0, second=0, microsecond=0)
    default_end   = default_start + timedelta(hours=1)
    default_start_str = default_start.strftime("%Y-%m-%dT%H:%M:%S+05:30")
    default_end_str   = default_end.strftime("%Y-%m-%dT%H:%M:%S+05:30")

    today_str    = datetime.now().strftime("%Y-%m-%d")
    tomorrow_str = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    now_time_str = datetime.now().strftime("%H:%M")

    system = f"""
You are a calendar event drafting assistant.
Draft the event fields based on the user's request.

CRITICAL: You MUST output REAL dates, NOT natural language.
- Today's date is: {today_str}
- Tomorrow's date is: {tomorrow_str}
- Current time is: {now_time_str}

Return ONLY a raw JSON object with keys: title, start, end, attendees, description.

DATETIME FORMAT (ABSOLUTELY REQUIRED):
- start and end MUST be actual ISO 8601 strings with timezone.
- Format: "YYYY-MM-DDThh:mm:ss+05:30"
- Example for today at 10pm: "{today_str}T22:00:00+05:30"
- Example for tomorrow at 9am: "{tomorrow_str}T09:00:00+05:30"
- NEVER output words like "tonight", "tomorrow", "now" as the datetime value.
- ALWAYS output the actual calculated date string.

If the user says "tonight at 10pm", output: "{today_str}T22:00:00+05:30"
If the user says "tomorrow at 2pm", output: "{tomorrow_str}T14:00:00+05:30"
If no time specified, default to tomorrow 10:00-11:00.

Use empty string "" for attendees and description if unknown.
No markdown fences, no explanation. Output ONLY valid JSON.
"""

    prompt = "\n\n".join(filter(None, [
        user_prefs,                                                    # ← global memory
        f"User request: {user_query}",
        f"Planner params: {json.dumps(params)}" if params else "",
        f"Retrieved context:\n{context[:2000]}"  if context else "",
        "Output the calendar event with REAL dates (no natural language words). Return JSON only.",
    ]))

    drafted = _call_draft_llm(system, prompt)

    start = _normalize_datetime(drafted.get("start", ""))
    end   = _normalize_datetime(drafted.get("end", ""))

    # Fallback: parse directly from user query
    if not _is_valid_iso_datetime(start) or not _is_valid_iso_datetime(end):
        logger.warning(
            f"LLM returned invalid dates: start='{start}', end='{end}'. "
            "Parsing from user query."
        )
        parsed_start = _parse_natural_datetime(user_query)
        if parsed_start:
            start = parsed_start
            start_dt = datetime.fromisoformat(start.replace('+05:30', ''))
            end = (start_dt + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S+05:30")

    if not _is_valid_iso_datetime(start):
        logger.warning(f"Invalid start '{start}', using default.")
        start = default_start_str
    if not _is_valid_iso_datetime(end):
        logger.warning(f"Invalid end '{end}', using default.")
        end = default_end_str

    return {
        "title":       drafted.get("title",       title or "Event"),
        "start":       start,
        "end":         end,
        "attendees":   drafted.get("attendees",   params.get("attendees",   "")),
        "description": drafted.get("description", params.get("description", "")),
    }


def _build_interrupt_payload(
    task: dict,
    user_query: str,
    context: str,
    user_prefs: str = "",
) -> dict:
    """
    Build the structured dict passed to interrupt().
    Frontend reads this directly — no regex parsing needed.
    user_prefs is injected from global memory (conversation_history prefix lines).
    """
    wt = (task.get("worker_type") or "").lower()
    gs = (task.get("google_service") or "").lower()

    if "gmail" in wt or gs == "gmail":
        fields = _draft_gmail_fields(task, user_query, context, user_prefs=user_prefs)
        return {
            "type": "gmail",
            "action": task.get("description", "Send email"),
            "user_query": user_query,
            **fields,
        }

    elif "calendar" in wt or gs == "calendar":
        fields = _draft_calendar_fields(task, user_query, context, user_prefs=user_prefs)
        return {
            "type": "calendar",
            "action": task.get("description", "Create calendar event"),
            "user_query": user_query,
            **fields,
        }

    else:
        return {
            "type": "google",
            "action": task.get("description", "Google action"),
            "user_query": user_query,
        }


# ── LangGraph node ────────────────────────────────────────────────────────────

def confirmation_node(payload: dict) -> dict:
    """
    Called via Send("confirmation_node", payload).
    payload keys: task, user_query, user_id, context (already fetched),
                  conversation_history (build_context() output — contains
                  [User preferences: ...] and [Summary: ...] lines)

    Steps:
      1. Read-only task → pass straight through (no interrupt).
      2. Write task → extract user prefs from history → draft fields with LLM
         → interrupt(json) → FREEZE.
      3. On resume → inject user-edited values → return approved payload.

    State updates returned:
      Approved:  {"hitl_approved_payload": [updated_payload]}
      Rejected:  {"results": [TaskResult(...)], "hitl_approved_payload": []}
      Read-only: {"hitl_approved_payload": [payload]}
    """
    from orchestration.wow_orchestration import TaskResult

    task_dict          = payload.get("task") or {}
    user_query         = payload.get("user_query") or ""
    context            = payload.get("context") or ""
    conversation_history = payload.get("conversation_history") or []

    # ── Extract global memory preferences line ────────────────────────
    user_prefs = _extract_user_prefs(conversation_history)
    if user_prefs:
        logger.info(f"HITL: injecting user prefs into draft: {user_prefs[:80]}")

    # ── 1. Read-only: pass straight to worker ────────────────────────
    if not needs_confirmation(task_dict):
        logger.info(f"HITL: task {task_dict.get('id')} is read-only, bypassing")
        return {"hitl_approved_payload": [payload]}

    # ── 2. Draft fields using LLM (context + prefs available here) ────
    logger.info(
        f"HITL: drafting fields for task {task_dict.get('id')} "
        f"— {task_dict.get('description')} "
        f"[context: {len(context)} chars, prefs: {len(user_prefs)} chars]"
    )

    interrupt_data = _build_interrupt_payload(
        task_dict, user_query, context, user_prefs=user_prefs
    )

    logger.info(
        f"HITL: pausing — type={interrupt_data.get('type')} "
        f"to={interrupt_data.get('to', 'N/A')} "
        f"title={interrupt_data.get('title', 'N/A')}"
    )

    # Frontend receives this JSON string, parses it, pre-fills the modal
    user_response: str = interrupt(json.dumps(interrupt_data))  # ← GRAPH FREEZES

    clean = (user_response or "").strip()

    # ── Reject: plain string ──────────────────────────────────────────
    if clean.lower() in {"reject", "cancel", "no", "n"}:
        logger.info(f"HITL: task {task_dict.get('id')} REJECTED (plain string)")
        return {
            "hitl_approved_payload": [],
            "results": [TaskResult(
                task_id=task_dict.get("id", 0),
                worker_type=task_dict.get("worker_type", "google"),
                success=False,
                output="❌ Action cancelled by user.",
                error="user_rejected",
            )],
        }

    # ── Parse JSON from modal ─────────────────────────────────────────
    try:
        data = json.loads(clean)
    except (json.JSONDecodeError, TypeError):
        logger.warning(f"HITL: unparseable resume response {clean!r} → reject")
        return {
            "hitl_approved_payload": [],
            "results": [TaskResult(
                task_id=task_dict.get("id", 0),
                worker_type=task_dict.get("worker_type", "google"),
                success=False,
                output="❌ Action cancelled (invalid response).",
                error="user_rejected",
            )],
        }

    if not data.get("approved"):
        logger.info(f"HITL: task {task_dict.get('id')} REJECTED via JSON")
        return {
            "hitl_approved_payload": [],
            "results": [TaskResult(
                task_id=task_dict.get("id", 0),
                worker_type=task_dict.get("worker_type", "google"),
                success=False,
                output="❌ Action cancelled by user.",
                error="user_rejected",
            )],
        }

    # ── 3. Approved — merge user edits over drafted values ────────────
    logger.info(f"HITL: task {task_dict.get('id')} APPROVED")

    params = dict(task_dict.get("parameters") or {})
    wt = (task_dict.get("worker_type") or "").lower()
    gs = (task_dict.get("google_service") or "").lower()

    if "gmail" in wt or gs == "gmail":
        params["to"]      = data.get("to",      interrupt_data.get("to",      ""))
        params["subject"] = data.get("subject", interrupt_data.get("subject", ""))
        params["body"]    = data.get("body",    interrupt_data.get("body",    ""))

        final_context = (
            f"CONFIRMED EMAIL TO SEND:\n"
            f"To: {params['to']}\n"
            f"Subject: {params['subject']}\n"
            f"Body:\n{params['body']}\n\n"
            f"Send this email exactly as specified using send_gmail_message tool."
        )
        updated_task = {**task_dict, "parameters": params}

    elif "calendar" in wt or gs == "calendar":
        # Populate both canonical key sets for maximum worker compatibility
        params["summary"]     = data.get("title",       interrupt_data.get("title",       ""))
        params["title"]       = params["summary"]
        params["start"]       = data.get("start",       interrupt_data.get("start",       ""))
        params["end"]         = data.get("end",         interrupt_data.get("end",         ""))
        params["start_time"]  = params["start"]
        params["end_time"]    = params["end"]
        params["attendees"]   = data.get("attendees",   interrupt_data.get("attendees",   ""))
        params["description"] = data.get("description", interrupt_data.get("description", ""))
        params["calendar_id"] = "primary"

        final_context = (
            f"CONFIRMED CALENDAR EVENT TO CREATE:\n"
            f"Title: {params['summary']}\n"
            f"Start: {params['start']}\n"
            f"End: {params['end']}\n"
            f"Attendees: {params['attendees']}\n"
            f"Description: {params['description']}\n\n"
            f"Create this event exactly as specified using the calendar create tool."
        )

        logger.info("=== HITL APPROVED CALENDAR PARAMS ===")
        logger.info(f"  summary: {params.get('summary')}")
        logger.info(f"  start: {params.get('start')}")
        logger.info(f"  end: {params.get('end')}")
        logger.info(f"  attendees: {params.get('attendees')}")
        logger.info(f"  description: {params.get('description')}")

        updated_task = {**task_dict, "parameters": params}
        logger.info(
            f"  Updated task parameters: "
            f"{json.dumps(updated_task.get('parameters', {}), default=str)}"
        )

    else:
        final_context = context
        updated_task  = task_dict

    updated_payload = {**payload, "task": updated_task, "context": final_context}

    logger.info("=== HITL FINAL PAYLOAD ===")
    logger.info(f"  Payload task type: {updated_payload['task'].get('worker_type')}")
    logger.info(
        f"  Payload task params: "
        f"{json.dumps(updated_payload['task'].get('parameters', {}), default=str)}"
    )
    return {"hitl_approved_payload": [updated_payload]}