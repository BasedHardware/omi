"""Chat tool routes — slice C owns this file.

Each route resolves an active-Jira context via `db.get_active_jira(uid)` (one
Redis fetch covering tokens + refresh + cloudid + site_url), then dispatches to
`jira_client`. Errors map to ChatToolResponse{error,oauth_url}.

Routes:
    POST /tools/create_issue
    POST /tools/list_my_issues
    POST /tools/search_issues
    POST /tools/get_issue
    POST /tools/update_issue_status
    POST /tools/add_comment
    POST /tools/list_projects
"""

import logging
import os
import re
from typing import Any, Optional

import httpx
from fastapi import APIRouter

import db
import jira_client
from jira_client import JiraAuthError, JiraNotFound, JiraRateLimit
from models import (
    ChatToolResponse,
    JiraAddCommentRequest,
    JiraCreateIssueRequest,
    JiraGetIssueRequest,
    JiraListMyIssuesRequest,
    JiraListProjectsRequest,
    JiraSearchIssuesRequest,
    JiraUpdateStatusRequest,
)

router = APIRouter()
log = logging.getLogger("nooto-jira-app.tools")

_ISSUE_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]+-\d+$")
_DEFAULT_FIELDS = [
    "summary",
    "status",
    "assignee",
    "priority",
    "issuetype",
    "updated",
    "duedate",
    # Pulled into list_my_issues so the desktop chat / Plan view can show a
    # short snippet under the title without a follow-up `get_issue` call.
    "description",
]
_DETAIL_FIELDS = _DEFAULT_FIELDS + ["reporter"]

# Jira's three statusCategory keys → our 4-bucket status_type. Anything
# unknown (custom workflow) falls back to "todo" so it still shows.
_STATUS_CATEGORY_MAP = {
    "new": "todo",
    "indeterminate": "in_progress",
    "done": "done",
}


def _normalize_jira_issue(it: dict, site_url: str) -> dict:
    """Reduce a raw Jira REST issue to the cross-plugin task shape consumed
    by the unified Plan view aggregator. Keep this in sync with the
    `IntegrationTask` shape in the Linear plugin and the backend's
    `NormalizedTask` model."""
    key = it.get("key", "") or ""
    f = (it.get("fields") or {}) or {}
    status = f.get("status") or {}
    category = (status.get("statusCategory") or {}).get("key")
    project = key.split("-")[0] if "-" in key else None
    assignee = (f.get("assignee") or {}).get("displayName")
    priority = (f.get("priority") or {}).get("name")
    # Jira stores description as ADF (Atlassian Document Format) — flatten
    # to plain text and cap so chat pills / cards aren't dominated by long
    # bodies. Caller can hit `get_issue` for the full thing when needed.
    description = _adf_to_text(f.get("description"))
    if description and len(description) > 240:
        description = description[:239].rstrip() + "…"
    return {
        "external_id": key,
        "title": (f.get("summary") or "") or key,
        "description": description or None,
        "status": status.get("name") or "Unknown",
        "status_type": _STATUS_CATEGORY_MAP.get(category, "todo"),
        "due_at": f.get("duedate"),
        "priority": priority,
        "url": f"{site_url}/browse/{key}" if site_url and key else "",
        "project": project,
        "assignee": assignee,
        "updated_at": f.get("updated"),
    }


# ── Auth gate ──────────────────────────────────────────────────────────────


def _oauth_url(uid: str) -> str:
    """Absolute when BASE_URL is set, relative path otherwise — chat layer handles both."""
    base = os.getenv("BASE_URL", "").rstrip("/")
    return f"{base}/auth/jira?uid={uid}"


def _resolve_active(uid: str) -> tuple[str, str, str] | ChatToolResponse:
    """Return (access_token, cloudid, site_url) or a populated error response.

    Single Redis lookup on the happy path, courtesy of `db.get_active_jira`.
    """
    active = db.get_active_jira(uid)
    if active is None:
        msg = "Connect Jira first." if not db.get_jira_tokens(uid) else "Jira session expired. Reconnect."
        return ChatToolResponse(error=msg, oauth_url=_oauth_url(uid))
    token, cloudid, site_url, _ = active
    return token, cloudid, site_url


def _validate_issue_key(key: str) -> bool:
    return bool(key and _ISSUE_KEY_RE.match(key))


def _truncate(s: str, n: int = 80) -> str:
    s = s or ""
    return s if len(s) <= n else s[: n - 1] + "…"


def _adf_to_text(doc: Optional[dict[str, Any]]) -> str:
    """Flatten ADF doc.content[].content[].text into plain lines."""
    if not doc or not isinstance(doc, dict):
        return ""
    lines: list[str] = []
    for block in doc.get("content", []) or []:
        chunks: list[str] = []
        for inline in block.get("content", []) or []:
            t = inline.get("text")
            if isinstance(t, str):
                chunks.append(t)
        lines.append("".join(chunks))
    return "\n".join(lines).strip()


# ── Routes ─────────────────────────────────────────────────────────────────


@router.post("/tools/create_issue", response_model=ChatToolResponse)
async def tool_create_issue(req: JiraCreateIssueRequest) -> ChatToolResponse:
    active = _resolve_active(req.uid)
    if isinstance(active, ChatToolResponse):
        return active
    token, cloudid, site_url = active

    project_key = req.project_key
    if not project_key:
        return ChatToolResponse(error="No project specified. Provide `project_key` (e.g. 'PROJ').")

    description_adf = jira_client.text_to_adf(req.description or "")

    try:
        result = jira_client.create_issue(
            cloudid,
            token,
            project_key=project_key,
            summary=req.summary,
            description_adf=description_adf,
            issue_type=req.issue_type or "Task",
            priority=req.priority,
        )
    except JiraAuthError:
        return ChatToolResponse(error="Jira auth failed.", oauth_url=_oauth_url(req.uid))
    except JiraNotFound:
        return ChatToolResponse(error=f"Project '{project_key}' not found.")
    except JiraRateLimit:
        return ChatToolResponse(error="Jira is rate-limiting; try again shortly.")
    except httpx.HTTPStatusError as e:
        log.warning("create_issue failed: %s", e)
        return ChatToolResponse(error=f"Failed to create issue: {e.response.status_code}")
    except Exception as e:  # pragma: no cover
        log.exception("create_issue unexpected error")
        return ChatToolResponse(error=f"Failed to create issue: {e}")

    issue_key = result.get("key", "")
    url = f"{site_url}/browse/{issue_key}" if site_url and issue_key else ""
    summary_line = f"Created **{issue_key}**: {req.summary}"
    text = f"{summary_line}\n{url}" if url else summary_line
    return ChatToolResponse(result=text, data=result)


@router.post("/tools/list_my_issues", response_model=ChatToolResponse)
async def tool_list_my_issues(req: JiraListMyIssuesRequest) -> ChatToolResponse:
    active = _resolve_active(req.uid)
    if isinstance(active, ChatToolResponse):
        return active
    token, cloudid, site_url = active

    jql_parts = ["assignee = currentUser()"]
    if req.status:
        safe_status = (req.status or "").replace('"', '\\"').strip()
        if safe_status:
            jql_parts.append(f'status = "{safe_status}"')
    elif req.open_only:
        # `statusCategory` is the standard JQL field for grouping workflows
        # across projects (To Do / In Progress / Done). Excluding Done filters
        # Resolved/Closed/Won't Do uniformly, regardless of custom status names.
        jql_parts.append("statusCategory != Done")
    jql = " AND ".join(jql_parts) + " ORDER BY updated DESC"
    limit = max(1, min(int(req.limit or 10), 50))

    try:
        result = jira_client.search_jql(cloudid, token, jql=jql, fields=_DEFAULT_FIELDS, max_results=limit)
    except JiraAuthError:
        return ChatToolResponse(error="Jira auth failed.", oauth_url=_oauth_url(req.uid))
    except JiraNotFound:
        return ChatToolResponse(error="Jira returned 404 for that query.")
    except JiraRateLimit:
        return ChatToolResponse(error="Jira is rate-limiting; try again shortly.")
    except httpx.HTTPStatusError as e:
        log.warning("list_my_issues failed: %s", e)
        return ChatToolResponse(error=f"Failed to list issues: {e.response.status_code}")
    except Exception as e:  # pragma: no cover
        log.exception("list_my_issues unexpected error")
        return ChatToolResponse(error=f"Failed to list issues: {e}")

    issues = result.get("issues", []) or []
    if not issues:
        suffix = f" with status '{req.status}'" if req.status else ""
        return ChatToolResponse(
            result=f"No issues assigned to you{suffix}.",
            data={"tasks": [], "raw": result},
        )

    tasks = [_normalize_jira_issue(it, site_url) for it in issues[:limit]]
    lines = [
        f"- **{t['external_id']}** [{t['status']}] {_truncate(t['title'], 80)}"
        for t in tasks
    ]
    # `tasks` is the cross-plugin shape consumed by the Plan-view aggregator;
    # `raw` is preserved so the chat agent can still read the full Jira payload.
    return ChatToolResponse(
        result="\n".join(lines),
        data={"tasks": tasks, "raw": result},
    )


@router.post("/tools/search_issues", response_model=ChatToolResponse)
async def tool_search_issues(req: JiraSearchIssuesRequest) -> ChatToolResponse:
    active = _resolve_active(req.uid)
    if isinstance(active, ChatToolResponse):
        return active
    token, cloudid, _ = active

    safe_q = jira_client.jql_escape(req.query or "")
    if not safe_q:
        return ChatToolResponse(error="Search query is empty after sanitization.")

    jql_parts = [f'text ~ "{safe_q}"']
    if req.project_key:
        # Validate project key shape (uppercase letters/digits/underscores).
        if re.match(r"^[A-Z][A-Z0-9_]+$", req.project_key):
            jql_parts.append(f"project = {req.project_key}")
    jql = " AND ".join(jql_parts) + " ORDER BY updated DESC"
    limit = max(1, min(int(req.limit or 10), 50))

    try:
        result = jira_client.search_jql(cloudid, token, jql=jql, fields=_DEFAULT_FIELDS, max_results=limit)
    except JiraAuthError:
        return ChatToolResponse(error="Jira auth failed.", oauth_url=_oauth_url(req.uid))
    except JiraNotFound:
        return ChatToolResponse(error="Project not found.")
    except JiraRateLimit:
        return ChatToolResponse(error="Jira is rate-limiting; try again shortly.")
    except httpx.HTTPStatusError as e:
        log.warning("search_issues failed: %s", e)
        return ChatToolResponse(error=f"Failed to search: {e.response.status_code}")
    except Exception as e:  # pragma: no cover
        log.exception("search_issues unexpected error")
        return ChatToolResponse(error=f"Failed to search: {e}")

    issues = result.get("issues", []) or []
    if not issues:
        return ChatToolResponse(result=f"No issues match '{req.query}'.", data=result)

    lines: list[str] = []
    for it in issues[:limit]:
        key = it.get("key", "")
        f = it.get("fields", {}) or {}
        status_name = ((f.get("status") or {}).get("name")) or "Unknown"
        summary = _truncate((f.get("summary") or ""), 80)
        lines.append(f"- **{key}** [{status_name}] {summary}")

    return ChatToolResponse(result="\n".join(lines), data=result)


@router.post("/tools/get_issue", response_model=ChatToolResponse)
async def tool_get_issue(req: JiraGetIssueRequest) -> ChatToolResponse:
    if not _validate_issue_key(req.issue_key):
        return ChatToolResponse(error=f"Invalid issue key: {req.issue_key!r}.")

    active = _resolve_active(req.uid)
    if isinstance(active, ChatToolResponse):
        return active
    token, cloudid, _ = active

    try:
        result = jira_client.get_issue(cloudid, token, key=req.issue_key, fields=_DETAIL_FIELDS)
    except JiraAuthError:
        return ChatToolResponse(error="Jira auth failed.", oauth_url=_oauth_url(req.uid))
    except JiraNotFound:
        return ChatToolResponse(error=f"Issue {req.issue_key} not found.")
    except JiraRateLimit:
        return ChatToolResponse(error="Jira is rate-limiting; try again shortly.")
    except httpx.HTTPStatusError as e:
        log.warning("get_issue failed: %s", e)
        return ChatToolResponse(error=f"Failed to fetch issue: {e.response.status_code}")
    except Exception as e:  # pragma: no cover
        log.exception("get_issue unexpected error")
        return ChatToolResponse(error=f"Failed to fetch issue: {e}")

    f = result.get("fields", {}) or {}
    summary = (f.get("summary") or "").strip()
    status_name = ((f.get("status") or {}).get("name")) or "Unknown"
    priority_name = ((f.get("priority") or {}).get("name")) or "None"
    assignee = f.get("assignee") or {}
    assignee_name = assignee.get("displayName") or "Unassigned"
    description_text = _adf_to_text(f.get("description"))

    header = f"**{req.issue_key}** — {summary}"
    meta = f"Status: {status_name} | Priority: {priority_name} | Assignee: {assignee_name}"
    body = f"{header}\n{meta}"
    if description_text:
        body += f"\n\n{description_text}"

    return ChatToolResponse(result=body, data=result)


@router.post("/tools/update_issue_status", response_model=ChatToolResponse)
async def tool_update_issue_status(req: JiraUpdateStatusRequest) -> ChatToolResponse:
    if not _validate_issue_key(req.issue_key):
        return ChatToolResponse(error=f"Invalid issue key: {req.issue_key!r}.")

    active = _resolve_active(req.uid)
    if isinstance(active, ChatToolResponse):
        return active
    token, cloudid, _ = active

    try:
        ok, available = jira_client.transition_to_named_status(cloudid, token, req.issue_key, req.new_status)
    except JiraAuthError:
        return ChatToolResponse(error="Jira auth failed.", oauth_url=_oauth_url(req.uid))
    except JiraNotFound:
        return ChatToolResponse(error=f"Issue {req.issue_key} not found.")
    except JiraRateLimit:
        return ChatToolResponse(error="Jira is rate-limiting; try again shortly.")
    except httpx.HTTPStatusError as e:
        log.warning("update_issue_status failed: %s", e)
        return ChatToolResponse(error=f"Failed to transition: {e.response.status_code}")
    except Exception as e:  # pragma: no cover
        log.exception("update_issue_status unexpected error")
        return ChatToolResponse(error=f"Failed to transition: {e}")

    if ok:
        return ChatToolResponse(
            result=f"Moved **{req.issue_key}** to **{req.new_status}**.",
            data={"issue_key": req.issue_key, "status": req.new_status},
        )

    avail_str = ", ".join(available) if available else "(none)"
    return ChatToolResponse(
        result=f"Could not find status '{req.new_status}'. Available: {avail_str}",
        data={"issue_key": req.issue_key, "available": available},
    )


@router.post("/tools/add_comment", response_model=ChatToolResponse)
async def tool_add_comment(req: JiraAddCommentRequest) -> ChatToolResponse:
    if not _validate_issue_key(req.issue_key):
        return ChatToolResponse(error=f"Invalid issue key: {req.issue_key!r}.")
    if not (req.comment or "").strip():
        return ChatToolResponse(error="Comment body is empty.")

    active = _resolve_active(req.uid)
    if isinstance(active, ChatToolResponse):
        return active
    token, cloudid, _ = active

    body_adf = jira_client.text_to_adf(req.comment)

    try:
        result = jira_client.add_comment(cloudid, token, key=req.issue_key, body_adf=body_adf)
    except JiraAuthError:
        return ChatToolResponse(error="Jira auth failed.", oauth_url=_oauth_url(req.uid))
    except JiraNotFound:
        return ChatToolResponse(error=f"Issue {req.issue_key} not found.")
    except JiraRateLimit:
        return ChatToolResponse(error="Jira is rate-limiting; try again shortly.")
    except httpx.HTTPStatusError as e:
        log.warning("add_comment failed: %s", e)
        return ChatToolResponse(error=f"Failed to add comment: {e.response.status_code}")
    except Exception as e:  # pragma: no cover
        log.exception("add_comment unexpected error")
        return ChatToolResponse(error=f"Failed to add comment: {e}")

    return ChatToolResponse(result=f"Added comment to **{req.issue_key}**.", data=result)


@router.post("/tools/list_projects", response_model=ChatToolResponse)
async def tool_list_projects(req: JiraListProjectsRequest) -> ChatToolResponse:
    active = _resolve_active(req.uid)
    if isinstance(active, ChatToolResponse):
        return active
    token, cloudid, _ = active

    try:
        # Cache only when no `query` was passed (cache layer respects this).
        projects = jira_client.list_projects(cloudid, token, query=req.query, _cache_uid=req.uid)
    except JiraAuthError:
        return ChatToolResponse(error="Jira auth failed.", oauth_url=_oauth_url(req.uid))
    except JiraRateLimit:
        return ChatToolResponse(error="Jira is rate-limiting; try again shortly.")
    except httpx.HTTPStatusError as e:
        log.warning("list_projects failed: %s", e)
        return ChatToolResponse(error=f"Failed to list projects: {e.response.status_code}")
    except Exception as e:  # pragma: no cover
        log.exception("list_projects unexpected error")
        return ChatToolResponse(error=f"Failed to list projects: {e}")

    if not projects:
        suffix = f" matching '{req.query}'" if req.query else ""
        return ChatToolResponse(result=f"No projects found{suffix}.", data={"values": projects})

    lines = [f"- **{p.get('key', '')}** — {p.get('name', '')}" for p in projects]
    return ChatToolResponse(result="\n".join(lines), data={"values": projects})
