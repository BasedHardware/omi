"""GET /v1/integrations/tasks — fan out to enabled plugins' list_my_issues
chat tools and return a merged task list for the unified Plan view.

Lives separate from the agentic chat path (utils/retrieval/agentic.py) — that
path uses Anthropic for tool dispatch which is wasteful for read-only retrieval.
Here we just POST to each plugin's tool endpoint over plain httpx.
"""

import asyncio
import logging
from typing import Optional

import httpx
from fastapi import APIRouter, Depends

from database.redis_db import get_enabled_apps
from models.aggregated_tasks import AggregatedTasksResponse, NormalizedTask
from utils.apps import get_available_app_by_id
from utils.other import endpoints as auth

router = APIRouter()
logger = logging.getLogger(__name__)


_PER_APP_TIMEOUT_S = 5.0
_MAX_TASKS = 200
# Tools whose responses we treat as "list of my open work items". The plugin
# contract is `data.tasks: [{external_id, title, status, status_type, …}]`.
_LIST_TOOL_NAME_SUFFIX = "list_my_issues"


def _find_list_tool(app: dict) -> Optional[dict]:
    """Pick the chat_tools entry to call for this app, if any."""
    for tool in app.get("chat_tools") or []:
        # `tool` is a ChatTool dict (see models/app.py:89). We accept any tool
        # whose name ends in `list_my_issues` so each plugin can keep its own
        # prefix (e.g. `jira_list_my_issues`, `linear_list_my_issues`).
        name = (tool.get("name") or "").lower()
        if name.endswith(_LIST_TOOL_NAME_SUFFIX) and tool.get("endpoint"):
            return tool
    return None


async def _fetch_app_tasks(
    client: httpx.AsyncClient, app: dict, uid: str
) -> tuple[list[dict], Optional[str]]:
    """Call one plugin's list_my_issues tool. Returns (raw_tasks, error_str)."""
    tool = _find_list_tool(app)
    if not tool:
        return [], None  # silently skip — app doesn't expose a list tool

    try:
        # `open_only` filters out Done/Cancelled tickets at the source so we
        # don't waste the limit budget on closed work. Plugins that don't yet
        # honor the flag (older deploys) just ignore it — they'll over-fetch
        # and the frontend's `t.completed` filter still hides closed rows.
        resp = await client.post(
            tool["endpoint"],
            json={"uid": uid, "limit": 50, "open_only": True},
            timeout=_PER_APP_TIMEOUT_S,
        )
    except (httpx.TimeoutException, httpx.RequestError) as e:
        logger.warning("[aggregated_tasks] %s timed out / network error: %s", app.get("id"), e)
        return [], f"network error: {e}"

    if resp.status_code != 200:
        return [], f"http {resp.status_code}"

    try:
        body = resp.json()
    except ValueError:
        return [], "non-JSON response"

    # Plugin error path — `ChatToolResponse(error=..., oauth_url=...)`.
    err = body.get("error")
    if err:
        return [], err

    data = body.get("data") or {}
    tasks = data.get("tasks") or []
    if not isinstance(tasks, list):
        return [], "data.tasks not a list"
    return tasks, None


@router.get("/v1/integrations/tasks", response_model=AggregatedTasksResponse, tags=["integrations"])
async def list_integration_tasks(uid: str = Depends(auth.get_current_user_uid)):
    """Aggregate `list_my_issues` results across the user's enabled apps.

    Returns:
        tasks: NormalizedTask[] — one entry per external task, sorted by
            (due_at nulls last, updated_at desc), capped at 200.
        errors: {app_id: human error} — present per app that failed; absent
            apps were healthy or had no list tool. Frontend can show a banner.
    """
    enabled_ids = get_enabled_apps(uid)
    if not enabled_ids:
        return AggregatedTasksResponse(tasks=[], errors={})

    apps = [get_available_app_by_id(app_id, uid) for app_id in enabled_ids]
    apps = [a for a in apps if a]

    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(
            *[_fetch_app_tasks(client, a, uid) for a in apps],
            return_exceptions=True,
        )

    merged: list[NormalizedTask] = []
    errors: dict[str, str] = {}
    for app, result in zip(apps, results):
        if isinstance(result, BaseException):
            errors[app["id"]] = f"{type(result).__name__}: {result}"
            continue
        raw_tasks, err = result
        if err:
            errors[app["id"]] = err
            continue
        for t in raw_tasks:
            try:
                merged.append(
                    NormalizedTask(
                        **t,
                        source_app_id=app["id"],
                        source_app_name=app.get("name") or app["id"],
                        source_app_image=app.get("image"),
                    )
                )
            except Exception as e:  # malformed plugin payload — drop, don't fail the whole call
                logger.warning("[aggregated_tasks] skipping malformed task from %s: %s", app["id"], e)

    # Sort: items with due dates first (ascending), undated last; within each
    # group, most recently updated first. Python's sort is stable, so two passes
    # give us the desired tiebreak.
    merged.sort(key=lambda t: t.updated_at or "", reverse=True)
    merged.sort(key=lambda t: (t.due_at is None, t.due_at or ""))
    return AggregatedTasksResponse(tasks=merged[:_MAX_TASKS], errors=errors)
