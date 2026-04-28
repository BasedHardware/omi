"""GET /v1/integrations/goals — fan out to enabled plugins' `list_releases`
chat tools and return a merged goal list for the unified Plan view.

Mirrors `aggregated_tasks.py` but for releases/milestones — Jira ships its
versions, Linear can ship cycles, GitHub releases, etc. Each plugin is
expected to return `data.goals: [{external_id, title, ...}]`.
"""

import asyncio
import logging
from typing import Optional

import httpx
from fastapi import APIRouter, Depends

from database.redis_db import get_enabled_apps
from models.aggregated_tasks import AggregatedGoalsResponse, NormalizedGoal
from utils.apps import get_available_app_by_id
from utils.other import endpoints as auth

router = APIRouter()
logger = logging.getLogger(__name__)


_PER_APP_TIMEOUT_S = 7.0  # slightly longer than tasks — list_releases fans
                          # out across projects on the plugin side
_MAX_GOALS = 200
_LIST_TOOL_NAME_SUFFIX = "list_releases"


def _find_list_tool(app: dict) -> Optional[dict]:
    for tool in app.get("chat_tools") or []:
        name = (tool.get("name") or "").lower()
        if name.endswith(_LIST_TOOL_NAME_SUFFIX) and tool.get("endpoint"):
            return tool
    return None


async def _fetch_app_goals(
    client: httpx.AsyncClient, app: dict, uid: str
) -> tuple[list[dict], Optional[str]]:
    tool = _find_list_tool(app)
    if not tool:
        return [], None

    try:
        resp = await client.post(
            tool["endpoint"],
            json={"uid": uid, "limit": 50},
            timeout=_PER_APP_TIMEOUT_S,
        )
    except (httpx.TimeoutException, httpx.RequestError) as e:
        logger.warning("[aggregated_goals] %s timed out / network error: %s", app.get("id"), e)
        return [], f"network error: {e}"

    if resp.status_code != 200:
        return [], f"http {resp.status_code}"

    try:
        body = resp.json()
    except ValueError:
        return [], "non-JSON response"

    err = body.get("error")
    if err:
        return [], err

    data = body.get("data") or {}
    goals = data.get("goals") or []
    if not isinstance(goals, list):
        return [], "data.goals not a list"
    return goals, None


@router.get("/v1/integrations/goals", response_model=AggregatedGoalsResponse, tags=["integrations"])
async def list_integration_goals(uid: str = Depends(auth.get_current_user_uid)):
    """Aggregate `list_releases` results across the user's enabled apps.

    Returns:
        goals: NormalizedGoal[] — one entry per external release/milestone,
            sorted by due_at (nulls last), capped at 200.
        errors: {app_id: human error}.
    """
    enabled_ids = get_enabled_apps(uid)
    if not enabled_ids:
        return AggregatedGoalsResponse(goals=[], errors={})

    apps = [get_available_app_by_id(app_id, uid) for app_id in enabled_ids]
    apps = [a for a in apps if a]

    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(
            *[_fetch_app_goals(client, a, uid) for a in apps],
            return_exceptions=True,
        )

    merged: list[NormalizedGoal] = []
    errors: dict[str, str] = {}
    for app, result in zip(apps, results):
        if isinstance(result, BaseException):
            errors[app["id"]] = f"{type(result).__name__}: {result}"
            continue
        raw_goals, err = result
        if err:
            errors[app["id"]] = err
            continue
        for g in raw_goals:
            try:
                merged.append(
                    NormalizedGoal(
                        **g,
                        source_app_id=app["id"],
                        source_app_name=app.get("name") or app["id"],
                        source_app_image=app.get("image"),
                    )
                )
            except Exception as e:
                logger.warning("[aggregated_goals] skipping malformed goal from %s: %s", app["id"], e)

    # Sort by due date ascending, undated last.
    merged.sort(key=lambda g: (g.due_at is None, g.due_at or ""))
    return AggregatedGoalsResponse(goals=merged[:_MAX_GOALS], errors=errors)
