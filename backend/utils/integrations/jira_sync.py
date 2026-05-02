"""Jira → Omi action items sync.

Periodic read-only puller. Calls the Jira plugin's ``/tools/list_my_issues``
endpoint with ``open_only=True``, normalizes each task into the Omi action
item shape, and upserts via ``database.action_items.upsert_external_action_item``.

Design constraints (from project CLAUDE.md / project memory):
- All imports at the module top level (no in-function imports).
- ``utils/`` may import from ``database/`` only — never from ``routers/`` or
  ``main.py``.
- Two-way sync default OFF: this module only READS from Jira; nothing here
  writes back. Write-tool gating happens in the chat tool resolver.
- Iterate users via Redis SCAN — never load every user up front.
"""

import logging
import os
from datetime import datetime, timezone
from typing import Optional

import httpx

import database.action_items as action_items_db
from database.apps import get_app_by_id_db
from database.redis_db import is_app_enabled, r as redis_client
from utils.log_sanitizer import sanitize

logger = logging.getLogger(__name__)


JIRA_APP_ID = os.environ.get("NOOTO_JIRA_APP_ID", "nooto-jira")
JIRA_SOURCE_KEY = "jira"
_HTTP_TIMEOUT = 20.0
# Match the existing redis enabled-plugins keyspace — see database.redis_db.is_app_enabled.
_ENABLED_PLUGINS_KEY_PATTERN = "users:*:enabled_plugins"


def _resolve_plugin_base_url() -> Optional[str]:
    """Where to find the Jira plugin.

    Priority:
      1. ``NOOTO_JIRA_PLUGIN_URL`` env var (explicit override)
      2. ``app.external_integration.app_home_url`` from the registered app
         document in Firestore (this is what ``register_jira_app.py`` writes).
    Returns None if neither is configured — caller logs and bails.
    """
    env_url = os.environ.get("NOOTO_JIRA_PLUGIN_URL")
    if env_url:
        return env_url.rstrip("/")

    app_doc = get_app_by_id_db(JIRA_APP_ID)
    if not app_doc:
        return None
    ext = app_doc.get("external_integration") or {}
    base = (ext.get("app_home_url") or "").rstrip("/")
    return base or None


def _normalize_task_to_action_item(task: dict) -> dict:
    """Map a Jira plugin ``task`` payload to action-item write fields.

    The plugin's ``_normalize_jira_issue`` (see plugins/nooto-jira-app/routes/tools.py)
    already produces a stable cross-plugin shape with ``external_id``,
    ``title``, ``status_type``, ``due_at``, ``url``. We translate that into
    the action item document shape (``description``, ``due_at``, ``completed``).
    """
    description = (task.get("title") or "").strip() or (task.get("external_id") or "Untitled")
    completed = task.get("status_type") == "done"

    due_at = None
    raw_due = task.get("due_at")
    if isinstance(raw_due, str) and raw_due:
        try:
            # Jira returns ISO date-only strings (e.g. "2025-12-15"); accept both.
            due_at = datetime.fromisoformat(raw_due.replace("Z", "+00:00"))
            if due_at.tzinfo is None:
                due_at = due_at.replace(tzinfo=timezone.utc)
        except ValueError:
            due_at = None
    elif isinstance(raw_due, datetime):
        due_at = raw_due

    fields = {
        "description": description,
        "completed": completed,
        "due_at": due_at,
        # Keep transcript-only fields explicitly null so the unified feed
        # doesn't accidentally show a Jira item as belonging to a conversation.
        "conversation_id": None,
    }
    return fields


def _build_external_source(task: dict) -> dict:
    return {
        "source": JIRA_SOURCE_KEY,
        "external_id": task.get("external_id") or "",
        "url": task.get("url") or "",
    }


async def sync_user_jira_issues(uid: str, http_client: Optional[httpx.AsyncClient] = None) -> dict:
    """Pull open Jira issues for ``uid`` and upsert them as action items.

    Returns ``{"synced": N, "errors": K, "skipped": M}``.

    ``skipped`` covers tasks with no ``external_id`` (defensive — should never
    happen for real Jira issues but keeps the pipeline crash-free).
    """
    base_url = _resolve_plugin_base_url()
    if not base_url:
        logger.warning(
            "[JiraSync] No plugin URL configured (NOOTO_JIRA_PLUGIN_URL/app_home_url) — skipping uid=%s", uid
        )
        return {"synced": 0, "errors": 1, "skipped": 0}

    endpoint = f"{base_url}/tools/list_my_issues"
    payload = {"uid": uid, "open_only": True}

    owns_client = http_client is None
    client = http_client or httpx.AsyncClient(timeout=_HTTP_TIMEOUT)
    try:
        try:
            resp = await client.post(endpoint, json=payload)
        except httpx.RequestError as exc:
            logger.error("[JiraSync] Network error contacting plugin uid=%s err=%s", uid, sanitize(str(exc)))
            return {"synced": 0, "errors": 1, "skipped": 0}

        if resp.status_code != 200:
            # `resp.text` may contain Jira tokens / PII — sanitize before logging.
            logger.warning(
                "[JiraSync] Plugin returned %s for uid=%s body=%s",
                resp.status_code,
                uid,
                sanitize(resp.text[:500]),
            )
            return {"synced": 0, "errors": 1, "skipped": 0}

        body = resp.json() or {}
    finally:
        if owns_client:
            await client.aclose()

    if body.get("error"):
        logger.info("[JiraSync] Plugin reported error for uid=%s err=%s", uid, sanitize(str(body.get("error"))))
        return {"synced": 0, "errors": 1, "skipped": 0}

    data = body.get("data") or {}
    tasks = data.get("tasks") or []

    synced = 0
    errors = 0
    skipped = 0
    for task in tasks:
        ext_id = task.get("external_id")
        if not ext_id:
            skipped += 1
            continue
        external_source = _build_external_source(task)
        fields = _normalize_task_to_action_item(task)
        try:
            action_items_db.upsert_external_action_item(uid, external_source, fields)
            synced += 1
        except Exception as exc:  # pragma: no cover — defensive
            errors += 1
            logger.exception("[JiraSync] Upsert failed uid=%s ext_id=%s err=%s", uid, ext_id, sanitize(str(exc)))

    # Free the response body / list once we've consumed it (memory hygiene).
    tasks.clear()
    body.clear()

    logger.info("[JiraSync] uid=%s synced=%d errors=%d skipped=%d", uid, synced, errors, skipped)
    return {"synced": synced, "errors": errors, "skipped": skipped}


def _iter_uids_with_jira_enabled():
    """Yield uids that currently have the Jira app enabled.

    Uses Redis SCAN (cursor-based) so we don't materialize the full enabled-
    plugins keyspace into memory. ``is_app_enabled`` is the canonical check.
    """
    for raw_key in redis_client.scan_iter(_ENABLED_PLUGINS_KEY_PATTERN, count=500):
        try:
            key = raw_key.decode() if isinstance(raw_key, (bytes, bytearray)) else str(raw_key)
        except Exception:  # pragma: no cover — extremely defensive
            continue
        # key format: users:{uid}:enabled_plugins
        parts = key.split(":")
        if len(parts) < 3:
            continue
        uid = parts[1]
        if not uid:
            continue
        if is_app_enabled(uid, JIRA_APP_ID):
            yield uid


async def sync_all_users_jira() -> dict:
    """Run sync for every user with Jira enabled.

    Returns aggregate counts. Errors per-user are logged but do not abort the
    overall run.
    """
    total_users = 0
    total_synced = 0
    total_errors = 0

    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        for uid in _iter_uids_with_jira_enabled():
            total_users += 1
            try:
                result = await sync_user_jira_issues(uid, http_client=client)
            except Exception as exc:  # pragma: no cover — defensive
                logger.exception("[JiraSync] sync_user_jira_issues raised uid=%s err=%s", uid, sanitize(str(exc)))
                total_errors += 1
                continue
            total_synced += result.get("synced", 0)
            total_errors += result.get("errors", 0)

    summary = {"users": total_users, "synced": total_synced, "errors": total_errors}
    logger.info("[JiraSync] cron complete %s", summary)
    return summary
