"""Jira write actions backing the Plan-screen direct dispatch.

Two helpers for the Plan view's per-row buttons (transition, snooze):

- ``transition_action_item(uid, action_item_id, to_status)`` — calls the
  Jira plugin's ``/tools/update_issue_status`` endpoint and mirrors the new
  status into the action item's ``external_source.metadata`` (status,
  status_type, status_changed_at) plus the ``completed`` flag when the
  resulting status_type maps to "done".
- ``snooze_action_item(uid, action_item_id, snooze_until)`` — calls the
  plugin's ``/tools/update_issue_due_date`` endpoint and updates the local
  ``due_at`` timestamp.

Design constraints (project CLAUDE.md):
- All imports at the module top level.
- Module hierarchy: ``utils/`` may import from ``database/``, never upward.
- Two-way-sync gating happens in the router layer (this module assumes the
  caller has already validated). Each helper returns the updated action item
  dict on success and raises typed exceptions for the router to translate
  to HTTP status codes.
- ``sanitize()`` plugin response bodies before logging.
"""

import logging
import os
from datetime import datetime, timezone
from typing import Optional

import httpx

import database.action_items as action_items_db
from database.apps import get_app_by_id_db
from utils.log_sanitizer import sanitize

logger = logging.getLogger(__name__)


JIRA_APP_ID = os.environ.get("NOOTO_JIRA_APP_ID", "nooto-jira")
JIRA_SOURCE_KEY = "jira"
_HTTP_TIMEOUT = 20.0

# Plugin emits the legacy chat-tool vocabulary — keep the action-item
# metadata aligned with the Plan-screen contract (Jira statusCategory key).
_STATUS_TYPE_TO_METADATA = {
    "todo": "todo",
    "in_progress": "indeterminate",
    "indeterminate": "indeterminate",
    "done": "done",
}


# ── Errors ─────────────────────────────────────────────────────────────────


class JiraActionError(Exception):
    """Base for any Jira write helper failure."""


class JiraActionNotFound(JiraActionError):
    """The referenced action item was not found, has no Jira link, or the
    integration is not configured."""


class JiraActionPluginError(JiraActionError):
    """The Jira plugin returned a non-success response (network / 5xx / error
    payload). Routers should map this to HTTP 502."""


# ── Plugin URL resolution (mirrors jira_sync) ──────────────────────────────


def _resolve_plugin_base_url() -> Optional[str]:
    """Identical resolution path to ``jira_sync._resolve_plugin_base_url``.

    Kept inline here rather than imported to avoid a utils ↔ utils cycle if
    jira_sync ever grows to import this module (Plan-view direct actions and
    the cron read path are independent surfaces).
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


def _get_jira_action_item(uid: str, action_item_id: str) -> dict:
    """Load the action item and assert it carries a Jira ``external_source``.

    Raises ``JiraActionNotFound`` if the item is missing or isn't linked to
    a Jira issue (the router converts this to HTTP 404).
    """
    item = action_items_db.get_action_item(uid, action_item_id)
    if not item:
        raise JiraActionNotFound(f"Action item not found: {action_item_id}")
    ext = item.get("external_source") or {}
    if not isinstance(ext, dict) or ext.get("source") != JIRA_SOURCE_KEY or not ext.get("external_id"):
        raise JiraActionNotFound(f"Action item {action_item_id} is not linked to a Jira issue")
    return item


async def _post_plugin(
    endpoint_path: str,
    payload: dict,
    *,
    http_client: Optional[httpx.AsyncClient] = None,
) -> dict:
    """POST to a plugin endpoint and return the parsed JSON body.

    Raises ``JiraActionNotFound`` when the plugin URL is unconfigured (no
    integration installed) and ``JiraActionPluginError`` for network errors,
    non-200 responses, or plugin-reported error payloads.
    """
    base_url = _resolve_plugin_base_url()
    if not base_url:
        raise JiraActionNotFound("Jira plugin URL not configured")

    url = f"{base_url}{endpoint_path}"
    owns_client = http_client is None
    client = http_client or httpx.AsyncClient(timeout=_HTTP_TIMEOUT)
    try:
        try:
            resp = await client.post(url, json=payload)
        except httpx.RequestError as exc:
            logger.error("[JiraActions] Network error calling plugin %s err=%s", endpoint_path, sanitize(str(exc)))
            raise JiraActionPluginError("Plugin network error") from exc

        if resp.status_code != 200:
            logger.warning(
                "[JiraActions] Plugin returned %s for %s body=%s",
                resp.status_code,
                endpoint_path,
                sanitize(resp.text[:500]),
            )
            raise JiraActionPluginError(f"Plugin HTTP {resp.status_code}")

        body = resp.json() or {}
    finally:
        if owns_client:
            await client.aclose()

    if body.get("error"):
        # `body.get('error')` may include a message constructed from a Jira
        # response — sanitize before logging.
        logger.info(
            "[JiraActions] Plugin reported error for %s err=%s", endpoint_path, sanitize(str(body.get("error")))
        )
        raise JiraActionPluginError(str(body.get("error")))

    return body


# ── Public helpers ─────────────────────────────────────────────────────────


async def transition_action_item(
    uid: str,
    action_item_id: str,
    to_status: str,
    *,
    http_client: Optional[httpx.AsyncClient] = None,
) -> dict:
    """Transition the linked Jira issue and refresh the action item.

    Returns the updated action item dict (post-write, freshly read).
    Raises ``JiraActionNotFound`` / ``JiraActionPluginError`` on failure.
    """
    if not (to_status or "").strip():
        raise JiraActionPluginError("to_status is required")

    item = _get_jira_action_item(uid, action_item_id)
    issue_key = item["external_source"]["external_id"]

    body = await _post_plugin(
        "/tools/update_issue_status",
        {"uid": uid, "issue_key": issue_key, "new_status": to_status},
        http_client=http_client,
    )

    # Plugin's response shape: {"result": "...", "data": {"issue_key": ..., "status": ...}}
    # On a not-found-status path it also returns 200 with `data.available` listing
    # the valid transitions. Treat that as a non-fatal mismatch — the router
    # surfaces it as 502 so the caller picks a different status.
    data = body.get("data") or {}
    if "available" in data and data.get("status") is None:
        raise JiraActionPluginError(f"Status '{to_status}' is not a valid transition")

    # Translate the requested status to a metadata-shaped status_type. We
    # don't know the Jira statusCategory locally, so we trust the plugin's
    # hint (currently only the requested status name is echoed back) and
    # fall back to "indeterminate" for in-flight transitions. For the
    # common-case "Done" name we lock it to "done" so the completed flag flips.
    new_status_name = data.get("status") or to_status
    inferred_status_type = _infer_status_type(new_status_name)

    now_iso = datetime.now(timezone.utc).isoformat()

    prior_external_source = item.get("external_source") or {}
    prior_metadata = prior_external_source.get("metadata") if isinstance(prior_external_source, dict) else None
    new_metadata = dict(prior_metadata or {})
    new_metadata["status"] = new_status_name
    new_metadata["status_type"] = inferred_status_type
    new_metadata["status_changed_at"] = now_iso

    new_external_source = dict(prior_external_source)
    new_external_source["metadata"] = new_metadata

    update_fields: dict = {"external_source": new_external_source}
    if inferred_status_type == "done":
        update_fields["completed"] = True
    elif inferred_status_type in ("todo", "indeterminate"):
        # Re-opening a previously-completed item: clear the completed flag.
        if item.get("completed"):
            update_fields["completed"] = False

    action_items_db.update_action_item(uid, action_item_id, update_fields)

    # Free the response payload — it's not used past this point.
    body.clear()

    refreshed = action_items_db.get_action_item(uid, action_item_id) or {}
    return refreshed


async def snooze_action_item(
    uid: str,
    action_item_id: str,
    snooze_until: datetime,
    *,
    http_client: Optional[httpx.AsyncClient] = None,
) -> dict:
    """Push the linked Jira issue's due date out and update local ``due_at``.

    ``snooze_until`` must be a ``datetime``. Jira's ``duedate`` is a
    date-only string (YYYY-MM-DD); we normalize to UTC and format the date
    component before forwarding to the plugin.

    Returns the updated action item dict.
    """
    if not isinstance(snooze_until, datetime):
        raise JiraActionPluginError("snooze_until must be a datetime")

    item = _get_jira_action_item(uid, action_item_id)
    issue_key = item["external_source"]["external_id"]

    snooze_utc = (
        snooze_until.astimezone(timezone.utc) if snooze_until.tzinfo else snooze_until.replace(tzinfo=timezone.utc)
    )
    due_date_str = snooze_utc.strftime("%Y-%m-%d")

    body = await _post_plugin(
        "/tools/update_issue_due_date",
        {"uid": uid, "issue_key": issue_key, "due_date": due_date_str},
        http_client=http_client,
    )

    action_items_db.update_action_item(uid, action_item_id, {"due_at": snooze_utc})

    body.clear()

    refreshed = action_items_db.get_action_item(uid, action_item_id) or {}
    return refreshed


def _infer_status_type(status_name: str) -> str:
    """Best-effort mapping from a free-form Jira status name to the canonical
    statusCategory key.

    The plugin's ``/tools/update_issue_status`` doesn't echo the
    statusCategory, only the status name — so we infer locally. Unknown
    names fall back to ``indeterminate`` (in-progress) so the Plan card
    still shows the user that the issue moved off the previous status.
    """
    lower = (status_name or "").strip().lower()
    if not lower:
        return "indeterminate"
    if lower in ("done", "closed", "resolved", "complete", "completed", "won't do", "wont do"):
        return "done"
    if lower in ("to do", "todo", "open", "backlog", "new"):
        return "todo"
    return "indeterminate"
