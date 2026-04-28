"""Proactive flow routes — slice D owns this file.

Routes:
    POST /webhook                       live transcript → intent → autofile/suggest
    POST /memory_created                end-of-conversation → up to 3 candidates
    POST /tools/confirm_suggestion      confirm/dismiss persisted suggestions
    GET  /suggestions/{suggestion_id}   edit form (HTML; minimal redirect for v1)

Cost guardrails (per-session cooldown, per-user daily cap, per-conversation
guard, token caps) live here — see plan §D.
"""

import asyncio
import json
import logging
import os
import re
import time
import uuid
from datetime import datetime, timedelta, timezone as dt_timezone
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse

import db
import intent_detector
import jira_client
from models import (
    ConfirmSuggestionResponse,
    JiraIntent,
    JiraTicketCandidate,
    WebhookRequest,
)

router = APIRouter()
log = logging.getLogger("nooto-jira-app.proactive")


def _r():
    return db.get_redis()


# ── Tunables ──────────────────────────────────────────────────────────────


VERB_RE = re.compile(
    r"\b(create|file|make|log|add|fix|need|build|update|track|ticket|bug|task)\b",
    re.IGNORECASE,
)
SENTENCE_END_RE = re.compile(r"[.?!]\s*$")

BUF_TTL = 600
FLUSHED_TTL = 600
LAST_TTL = 60
LLM_COOLDOWN_SECONDS = 30
SUGGESTION_TTL = 86_400
MEMORY_GUARD_TTL = 3_600
DAILY_CAP_KEY_TTL = 90_000  # 25h, slightly more than a day for grace.
MIN_FLUSH_CHARS = 25
IDLE_FLUSH_SECONDS = 5
IDLE_TICK_SECONDS = 1
IDLE_NO_REDIS_BACKOFF_SECONDS = 2

# Set of "{uid}:{session_id}" tuples currently being buffered.
# Replaces a `scan_iter("jira:last:*")` keyspace scan in idle_flush_worker.
ACTIVE_SESSIONS_KEY = "jira:active_sessions"
ACTIVE_SESSIONS_TTL = 600


def _auto_threshold() -> float:
    return float(os.getenv("JIRA_AUTOFILE_CONFIDENCE_THRESHOLD", "0.85"))


def _suggest_threshold() -> float:
    return float(os.getenv("JIRA_SUGGEST_CONFIDENCE_THRESHOLD", "0.6"))


def _daily_cap() -> int:
    try:
        return int(os.getenv("JIRA_LLM_DAILY_CAP", "200"))
    except ValueError:
        return 200


def _base_url() -> str:
    return os.getenv("BASE_URL", "").rstrip("/")


def _omi_backend_url() -> str:
    return os.getenv("OMI_BACKEND_URL", "").rstrip("/")


# ── Helpers ───────────────────────────────────────────────────────────────


def _is_authed(uid: str) -> bool:
    try:
        return db.get_jira_tokens(uid) is not None
    except Exception:
        return False


def _iso_now() -> str:
    return datetime.now(dt_timezone.utc).isoformat()


def _iso_in_24h() -> str:
    return (datetime.now(dt_timezone.utc) + timedelta(hours=24)).isoformat()


def _parse_iso(s: str) -> datetime:
    return datetime.fromisoformat(s)


# ── Notifications ─────────────────────────────────────────────────────────


async def _post_notification(payload: dict[str, Any]) -> None:
    backend = _omi_backend_url()
    secret = os.getenv("OMI_APP_SECRET", "")
    if not backend:
        log.info("OMI_BACKEND_URL not set; skipping notification: %s", payload.get("type"))
        return
    url = f"{backend}/v1/integrations/notification"
    headers = {"Content-Type": "application/json"}
    if secret:
        headers["Authorization"] = f"Bearer {secret}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code >= 300:
                log.warning(
                    "Notification POST %s -> %s: %s",
                    payload.get("type"),
                    resp.status_code,
                    resp.text[:200],
                )
    except Exception as e:
        log.warning("Notification dispatch failed (%s): %s", payload.get("type"), e)


async def notify_suggestion(uid: str, candidate: JiraTicketCandidate) -> None:
    if db.within_quiet_hours(uid):
        log.info("Suppressing suggestion notification for uid=%s during quiet hours", uid)
        return
    base = _base_url()
    sid = candidate.suggestion_id
    confirm_url = f"{base}/tools/confirm_suggestion?suggestion_id={sid}&action=confirm" if base else ""
    dismiss_url = f"{base}/tools/confirm_suggestion?suggestion_id={sid}&action=dismiss" if base else ""
    edit_url = f"{base}/suggestions/{sid}" if base else ""
    payload = {
        "uid": uid,
        "type": "jira_suggestion",
        "suggestion_id": sid,
        "title": "Create Jira ticket?",
        "body": (candidate.summary or "")[:280],
        "subtitle": (f'Source: "{candidate.source_quote[:140]}"' if candidate.source_quote else ""),
        "actions": [
            {"label": "File it", "url": confirm_url},
            {"label": "Edit", "url": edit_url},
            {"label": "Dismiss", "url": dismiss_url},
        ],
        "expires_at": _iso_in_24h(),
    }
    await _post_notification(payload)


async def notify_ticket_created(
    uid: str,
    intent: JiraIntent,
    issue: dict[str, Any],
) -> None:
    if db.within_quiet_hours(uid):
        log.info("Suppressing ticket-created notification for uid=%s during quiet hours", uid)
        return
    issue_key = issue.get("key") or ""
    # Atlassian "self" is the API URL; for browse links we'd need the site URL.
    # Best effort — fall back to API self link.
    issue_url = issue.get("self") or ""
    payload = {
        "uid": uid,
        "type": "jira_ticket_created",
        "issue_key": issue_key,
        "title": f"Filed {issue_key}" if issue_key else "Filed Jira ticket",
        "body": (intent.summary or "")[:280],
        "subtitle": (intent.project_key or ""),
        "actions": ([{"label": "Open in Jira", "url": issue_url}] if issue_url else []),
        "expires_at": _iso_in_24h(),
    }
    await _post_notification(payload)


# ── Suggestion store ──────────────────────────────────────────────────────


def _persist_suggestion(uid: str, candidate: JiraTicketCandidate) -> bool:
    """Store the suggestion in Redis with a 24h TTL. Returns True on success."""
    r = _r()
    if not r:
        log.warning("No Redis available; cannot persist suggestion for uid=%s", uid)
        return False
    try:
        sid = candidate.suggestion_id
        key = f"jira:suggestion:{sid}"
        now = time.time()
        payload_json = json.dumps(candidate.model_dump())
        pipe = r.pipeline()
        pipe.hset(
            key,
            mapping={
                "uid": uid,
                "payload_json": payload_json,
                "created_at": str(now),
                "status": "pending",
            },
        )
        pipe.expire(key, SUGGESTION_TTL)
        pipe.zadd(f"jira:suggestions:{uid}", {sid: now})
        pipe.expire(f"jira:suggestions:{uid}", SUGGESTION_TTL)
        pipe.execute()
        return True
    except Exception as e:
        log.warning("persist_suggestion failed for uid=%s: %s", uid, e)
        return False


def _load_suggestion(suggestion_id: str) -> Optional[dict[str, str]]:
    r = _r()
    if not r:
        return None
    try:
        data = r.hgetall(f"jira:suggestion:{suggestion_id}")
        return data or None
    except Exception as e:
        log.warning("load_suggestion failed for %s: %s", suggestion_id, e)
        return None


def _set_suggestion_status(suggestion_id: str, status: str, **extra: str) -> None:
    r = _r()
    if not r:
        return
    try:
        mapping: dict[str, str] = {"status": status}
        mapping.update({k: str(v) for k, v in extra.items()})
        r.hset(f"jira:suggestion:{suggestion_id}", mapping=mapping)
    except Exception as e:
        log.warning("set_suggestion_status failed: %s", e)


# ── Cost guardrails ───────────────────────────────────────────────────────


def _check_and_increment_daily_cap(uid: str) -> bool:
    """Return False if the user has exceeded the daily LLM call cap."""
    r = _r()
    if not r:
        return True
    today = datetime.now(dt_timezone.utc).strftime("%Y%m%d")
    key = f"jira:llm_calls:{uid}:{today}"
    try:
        count = r.incr(key)
        if count == 1:
            r.expire(key, DAILY_CAP_KEY_TTL)
        if count > _daily_cap():
            log.info("Daily LLM cap reached for uid=%s (count=%s)", uid, count)
            return False
        return True
    except Exception as e:
        log.warning("daily cap check failed for uid=%s: %s", uid, e)
        return True


def _llm_cooldown_active(uid: str, session_id: str) -> bool:
    r = _r()
    if not r:
        return False
    try:
        return bool(r.exists(f"jira:llm_cooldown:{uid}:{session_id}"))
    except Exception:
        return False


def _set_llm_cooldown(uid: str, session_id: str) -> None:
    r = _r()
    if not r:
        return
    try:
        r.setex(f"jira:llm_cooldown:{uid}:{session_id}", LLM_COOLDOWN_SECONDS, "1")
    except Exception as e:
        log.warning("set_llm_cooldown failed: %s", e)


# ── Buffer helpers ────────────────────────────────────────────────────────


def _buf_key(uid: str, session_id: str) -> str:
    return f"jira:buf:{uid}:{session_id}"


def _flushed_key(uid: str, session_id: str) -> str:
    return f"jira:flushed:{uid}:{session_id}"


def _last_key(uid: str, session_id: str) -> str:
    return f"jira:last:{uid}:{session_id}"


def _segment_fingerprint(seg: dict[str, Any]) -> Optional[str]:
    start = seg.get("start")
    end = seg.get("end")
    if start is None or end is None:
        return None
    return f"{start}:{end}"


# ── Apply guardrail and dispatch ──────────────────────────────────────────


async def _apply_guardrail_and_dispatch(uid: str, intent: JiraIntent) -> None:
    if not intent.detected:
        log.info("intent.detected=false for uid=%s; dropping", uid)
        return

    auto_threshold = _auto_threshold()
    suggest_threshold = _suggest_threshold()

    if intent.confidence >= auto_threshold and db.is_autofile_enabled(uid) and intent.project_key:
        await _autofile_intent(uid, intent)
        return

    if intent.confidence >= suggest_threshold:
        candidate = JiraTicketCandidate(
            **intent.model_dump(),
            suggestion_id=uuid.uuid4().hex,
            source_quote="",
        )
        if _persist_suggestion(uid, candidate):
            await notify_suggestion(uid, candidate)
        return

    log.info(
        "intent below suggest threshold for uid=%s (conf=%.2f); dropping",
        uid,
        intent.confidence,
    )


async def _autofile_intent(uid: str, intent: JiraIntent) -> None:
    active = db.get_active_jira(uid)
    if active is None:
        log.warning("autofile aborted: no active jira context for uid=%s", uid)
        return
    token, cloudid, _, _ = active
    description_adf = jira_client.text_to_adf(intent.description or "")
    try:
        issue = jira_client.create_issue(
            cloudid,
            token,
            project_key=intent.project_key or "",
            summary=intent.summary,
            description_adf=description_adf,
            issue_type=intent.issue_type,
            priority=intent.priority,
        )
    except Exception as e:
        log.warning("autofile create_issue failed for uid=%s: %s", uid, e)
        return
    await notify_ticket_created(uid, intent, issue)


# ── flush + idle worker ───────────────────────────────────────────────────


async def flush_buffer(uid: str, session_id: str) -> None:
    r = _r()
    if not r:
        return

    buf_key = _buf_key(uid, session_id)
    last_key = _last_key(uid, session_id)
    flushed_key = _flushed_key(uid, session_id)

    # Atomic drain: LRANGE + DEL.
    try:
        pipe = r.pipeline()
        pipe.lrange(buf_key, 0, -1)
        pipe.delete(buf_key)
        pipe.delete(last_key)
        items, _, _ = pipe.execute()
    except Exception as e:
        log.warning("flush_buffer drain failed for %s/%s: %s", uid, session_id, e)
        return

    if not items:
        return

    segments: list[dict[str, Any]] = []
    for raw in items:
        try:
            seg = json.loads(raw)
            if isinstance(seg, dict):
                segments.append(seg)
        except Exception:
            continue

    if not segments:
        return

    # Mark these segments as flushed so the next /webhook tick won't re-add.
    try:
        fingerprints = [fp for fp in (_segment_fingerprint(s) for s in segments) if fp]
        if fingerprints:
            r.sadd(flushed_key, *fingerprints)
            r.expire(flushed_key, FLUSHED_TTL)
    except Exception as e:
        log.warning("flushed-set update failed for %s/%s: %s", uid, session_id, e)

    # Cooldown immediately so concurrent webhooks don't re-trigger us mid-flight.
    _set_llm_cooldown(uid, session_id)

    full_text = " ".join((s.get("text") or "").strip() for s in segments).strip()
    if len(full_text) < MIN_FLUSH_CHARS:
        log.info("flush skipped: text too short (%d chars) for %s/%s", len(full_text), uid, session_id)
        return
    if not VERB_RE.search(full_text):
        log.info("flush skipped: no verb-ish token for %s/%s", uid, session_id)
        return

    if not _check_and_increment_daily_cap(uid):
        return

    active = db.get_active_jira(uid)
    if active is None:
        log.info("flush skipped: no active jira context for uid=%s", uid)
        return
    token, cloudid, _, _ = active

    try:
        projects, current_user = await asyncio.gather(
            asyncio.to_thread(jira_client.list_projects, cloudid, token, _cache_uid=uid),
            asyncio.to_thread(jira_client.current_user, cloudid, token, _cache_uid=uid),
        )
    except Exception as e:
        log.warning("Jira metadata fetch failed for uid=%s: %s", uid, e)
        return

    intent = await intent_detector.detect_jira_intent(segments, projects, current_user)
    await _apply_guardrail_and_dispatch(uid, intent)


async def idle_flush_worker() -> None:
    """Iterate the small `jira:active_sessions` set instead of scanning the keyspace.

    Each /webhook tick adds `{uid}:{session_id}` to that set; this worker reads
    only that set and flushes any session that has been idle past the threshold.
    """
    log.info("Starting jira idle_flush_worker")
    while True:
        try:
            r = _r()
            if r is None:
                await asyncio.sleep(IDLE_NO_REDIS_BACKOFF_SECONDS)
                continue
            now = time.time()
            try:
                members = list(r.smembers(ACTIVE_SESSIONS_KEY))
            except Exception:
                members = []
            stale: list[str] = []
            ready: list[tuple[str, str]] = []
            for member in members:
                # Member shape: "{uid}:{session_id}" — uid has no colons.
                if ":" not in member:
                    stale.append(member)
                    continue
                uid, _, session_id = member.partition(":")
                try:
                    raw = r.get(_last_key(uid, session_id))
                except Exception:
                    raw = None
                if not raw:
                    stale.append(member)
                    continue
                try:
                    last = float(_parse_iso(raw).timestamp())
                except Exception:
                    stale.append(member)
                    continue
                if now - last < IDLE_FLUSH_SECONDS:
                    continue
                ready.append((uid, session_id))
                stale.append(member)
            if stale:
                try:
                    r.srem(ACTIVE_SESSIONS_KEY, *stale)
                except Exception:
                    pass
            if ready:
                await asyncio.gather(*(flush_buffer(uid, sid) for uid, sid in ready))
        except Exception as e:
            log.exception("idle_flush_worker tick failed: %s", e)
        await asyncio.sleep(IDLE_TICK_SECONDS)


# ── Routes ────────────────────────────────────────────────────────────────


@router.post("/webhook")
async def webhook(
    request: Request,
    payload: WebhookRequest,
    uid: str = Query("", description="OMI user id"),
    session_id: str = Query("", description="Session id"),
):
    # Canonicalize identifiers (query params win, then body).
    effective_uid = uid or payload.uid or ""
    effective_session = session_id or payload.session_id or ""
    if not effective_uid:
        return {"status": "ok"}
    if not effective_session:
        effective_session = f"omi_session_{effective_uid}"

    if not _is_authed(effective_uid):
        return {"status": "ok"}

    if not db.is_enabled(effective_uid):
        return {"status": "ok"}

    # Skip when a flush already ran in the last 30s.
    if _llm_cooldown_active(effective_uid, effective_session):
        return {"status": "ok"}

    r = _r()
    if not r:
        # Without Redis we can't buffer; nothing to do but stay silent.
        return {"status": "ok"}

    segments = [s.model_dump() for s in payload.segments or []]
    if not segments:
        return {"status": "ok"}

    buf_key = _buf_key(effective_uid, effective_session)
    flushed_key = _flushed_key(effective_uid, effective_session)
    last_key = _last_key(effective_uid, effective_session)

    appended = 0
    try:
        for seg in segments:
            fp = _segment_fingerprint(seg)
            if fp and r.sismember(flushed_key, fp):
                continue
            r.rpush(buf_key, json.dumps(seg))
            appended += 1
        if appended:
            r.expire(buf_key, BUF_TTL)
        r.set(last_key, _iso_now(), ex=LAST_TTL)
        # Track the active session so idle_flush_worker doesn't have to scan.
        r.sadd(ACTIVE_SESSIONS_KEY, f"{effective_uid}:{effective_session}")
        r.expire(ACTIVE_SESSIONS_KEY, ACTIVE_SESSIONS_TTL)
    except Exception as e:
        log.warning("webhook buffer write failed for %s/%s: %s", effective_uid, effective_session, e)
        return {"status": "ok"}

    # Early-flush trigger when the speaker just hit a clear sentence boundary.
    try:
        buf_len = r.llen(buf_key)
    except Exception:
        buf_len = 0
    last_text = ""
    for seg in reversed(segments):
        if (seg.get("text") or "").strip():
            last_text = seg["text"].strip()
            break
    if buf_len >= 3 and last_text and SENTENCE_END_RE.search(last_text):
        await flush_buffer(effective_uid, effective_session)

    return {"status": "ok"}


@router.post("/memory_created")
async def memory_created(
    request: Request,
    uid: str = Query("", description="OMI user id"),
):
    body: dict[str, Any]
    try:
        body = await request.json()
    except Exception:
        return {"status": "ok"}
    if not isinstance(body, dict):
        return {"status": "ok"}

    effective_uid = uid or body.get("uid") or ""
    if not effective_uid:
        return {"status": "ok"}

    if not _is_authed(effective_uid):
        return {"status": "ok"}
    if not db.is_enabled(effective_uid):
        return {"status": "ok"}

    structured = body.get("structured") or {}
    action_items = structured.get("action_items") or []
    overview = structured.get("overview") or ""
    if not action_items and len(overview) < 100:
        return {"status": "ok", "suggestions_created": 0}

    conversation_id = body.get("id") or body.get("conversation_id") or ""
    r = _r()
    if r and conversation_id:
        try:
            # SETNX with EX semantics → set returns False when key already exists.
            ok = r.set(
                f"jira:memory_cooldown:{effective_uid}:{conversation_id}",
                "1",
                ex=MEMORY_GUARD_TTL,
                nx=True,
            )
            if not ok:
                return {"status": "ok", "suggestions_created": 0}
        except Exception as e:
            log.warning("memory cooldown SETNX failed for uid=%s: %s", effective_uid, e)

    # Daily cap — count this LLM call too.
    if not _check_and_increment_daily_cap(effective_uid):
        return {"status": "ok", "suggestions_created": 0}

    active = db.get_active_jira(effective_uid)
    if active is None:
        return {"status": "ok", "suggestions_created": 0}
    token, cloudid, _, _ = active

    try:
        projects, current_user = await asyncio.gather(
            asyncio.to_thread(jira_client.list_projects, cloudid, token, _cache_uid=effective_uid),
            asyncio.to_thread(jira_client.current_user, cloudid, token, _cache_uid=effective_uid),
        )
    except Exception as e:
        log.warning("Jira metadata fetch failed in memory_created: %s", e)
        return {"status": "ok", "suggestions_created": 0}

    candidates = await intent_detector.suggest_tickets_from_memory(body, projects, current_user)
    threshold = _suggest_threshold()
    suggestions_created = 0
    for c in candidates[:3]:
        if c.confidence < threshold:
            continue
        if not c.suggestion_id:
            c = c.model_copy(update={"suggestion_id": uuid.uuid4().hex})
        if _persist_suggestion(effective_uid, c):
            await notify_suggestion(effective_uid, c)
            suggestions_created += 1
    return {"status": "ok", "suggestions_created": suggestions_created}


@router.post("/tools/confirm_suggestion", response_model=ConfirmSuggestionResponse)
async def confirm_suggestion(
    suggestion_id: str = Query(...),
    action: str = Query(..., regex="^(confirm|dismiss)$"),
):
    data = _load_suggestion(suggestion_id)
    if not data:
        return ConfirmSuggestionResponse(status="expired", message="Suggestion expired or unknown.")

    current_status = data.get("status", "pending")
    if current_status == "filed":
        return ConfirmSuggestionResponse(
            status="already_filed",
            issue_key=data.get("issue_key"),
            message="Already filed.",
        )
    if current_status == "dismissed":
        return ConfirmSuggestionResponse(status="already_dismissed", message="Already dismissed.")

    if action == "dismiss":
        _set_suggestion_status(suggestion_id, "dismissed")
        return ConfirmSuggestionResponse(status="dismissed")

    uid = data.get("uid") or ""
    payload_json = data.get("payload_json") or "{}"
    try:
        payload = json.loads(payload_json)
    except Exception:
        return ConfirmSuggestionResponse(status="error", message="Corrupt suggestion payload.")

    if not uid:
        return ConfirmSuggestionResponse(status="error", message="Suggestion missing uid.")

    active = db.get_active_jira(uid)
    if active is None:
        base = _base_url()
        oauth_url = f"{base}/auth/jira?uid={uid}" if base else ""
        return ConfirmSuggestionResponse(
            status="error",
            message=f"Jira auth required. Reconnect at {oauth_url}" if oauth_url else "Jira auth required.",
        )
    token, cloudid, _, _ = active

    project_key = payload.get("project_key")
    summary = payload.get("summary") or ""
    description = payload.get("description") or ""
    issue_type = payload.get("issue_type") or "Task"
    priority = payload.get("priority")
    if not project_key or not summary:
        return ConfirmSuggestionResponse(
            status="error",
            message="Suggestion missing project_key or summary; cannot file.",
        )

    try:
        issue = jira_client.create_issue(
            cloudid,
            token,
            project_key=project_key,
            summary=summary,
            description_adf=jira_client.text_to_adf(description),
            issue_type=issue_type,
            priority=priority,
        )
    except jira_client.JiraAuthError:
        base = _base_url()
        oauth_url = f"{base}/auth/jira?uid={uid}" if base else ""
        return ConfirmSuggestionResponse(
            status="error",
            message=(
                f"Jira authorization expired. Reconnect at {oauth_url}" if oauth_url else "Jira authorization expired."
            ),
        )
    except Exception as e:
        log.warning("confirm_suggestion create_issue failed: %s", e)
        return ConfirmSuggestionResponse(status="error", message=f"Failed to create issue: {e}")

    issue_key = issue.get("key") or ""
    _set_suggestion_status(suggestion_id, "filed", issue_key=issue_key)
    return ConfirmSuggestionResponse(
        status="filed",
        issue_key=issue_key,
        message=f"Filed {issue_key}" if issue_key else "Filed.",
    )


@router.get("/suggestions/{suggestion_id}", response_class=HTMLResponse)
async def get_suggestion(suggestion_id: str):
    """Minimal HTML view of a pending suggestion. Full edit form deferred."""
    data = _load_suggestion(suggestion_id)
    if not data:
        return HTMLResponse(
            "<h1>Suggestion expired</h1><p>This suggestion is no longer available.</p>",
            status_code=404,
        )
    try:
        payload = json.loads(data.get("payload_json") or "{}")
    except Exception:
        payload = {}
    base = _base_url()
    confirm_url = f"{base}/tools/confirm_suggestion?suggestion_id={suggestion_id}&action=confirm"
    dismiss_url = f"{base}/tools/confirm_suggestion?suggestion_id={suggestion_id}&action=dismiss"
    summary = (payload.get("summary") or "").replace("<", "&lt;").replace(">", "&gt;")
    description = (payload.get("description") or "").replace("<", "&lt;").replace(">", "&gt;")
    project_key = (payload.get("project_key") or "").replace("<", "&lt;").replace(">", "&gt;")
    status = data.get("status", "pending")
    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Jira suggestion</title>
<style>
body{{font-family:-apple-system,Inter,sans-serif;background:#0D0D0D;color:#fff;padding:24px;max-width:560px;margin:0 auto}}
.card{{background:#171717;border:1px solid #2A2A2A;border-radius:16px;padding:24px;margin-top:16px}}
h1{{font-size:20px;margin-bottom:12px}}
.meta{{color:#9B9B9B;font-size:13px;margin-bottom:8px}}
.btn{{display:inline-block;padding:10px 18px;border-radius:10px;text-decoration:none;color:#fff;font-weight:600;margin-right:8px}}
.btn.primary{{background:#2684FF}}
.btn.secondary{{background:#1F1F1F;border:1px solid #2A2A2A}}
.status{{display:inline-block;padding:4px 10px;border-radius:8px;background:#1F1F1F;font-size:12px}}
</style></head>
<body>
<h1>Jira suggestion</h1>
<div class="card">
  <div class="meta">Status: <span class="status">{status}</span></div>
  <div class="meta">Project: <strong>{project_key or 'N/A'}</strong></div>
  <h2 style="font-size:16px;margin:8px 0">{summary or '(no summary)'}</h2>
  <pre style="white-space:pre-wrap;color:#9B9B9B;font-family:inherit">{description}</pre>
  <form method="post" action="{confirm_url}" style="display:inline">
    <button type="submit" class="btn primary">File it</button>
  </form>
  <form method="post" action="{dismiss_url}" style="display:inline">
    <button type="submit" class="btn secondary">Dismiss</button>
  </form>
</div>
</body></html>"""
    return HTMLResponse(html)
