from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

import database.notifications as notifications_db
from utils import task_integrations_ops as ops

TODAY_2359_LOS_ANGELES = datetime(2026, 9, 21, 6, 59, tzinfo=timezone.utc)
TODAY_0200_KOLKATA = datetime(2026, 9, 19, 20, 30, tzinfo=timezone.utc)


def _response(json_data):
    response = MagicMock(spec=httpx.Response)
    response.status_code = 200
    response.json.return_value = json_data
    return response


@pytest.fixture
def user_zone(monkeypatch):
    def set_zone(name):
        monkeypatch.setattr(notifications_db, "resolve_user_timezone", lambda uid: name)

    return set_zone


async def _create(app_key, integration, due_date):
    client = AsyncMock(spec=httpx.AsyncClient)
    client.post.return_value = _response({"id": "ext-1", "data": {"gid": "ext-1"}})
    result = await ops.create_task_internal(
        uid="uid-1",
        app_key=app_key,
        integration=integration,
        title="Send the invoice",
        due_date=due_date,
        client=client,
    )
    assert result["success"] is True
    return client.post.call_args.kwargs["json"]


@pytest.mark.asyncio
async def test_todoist_due_day_is_the_users_local_day(user_zone):
    user_zone("America/Los_Angeles")
    body = await _create("todoist", {"connected": True, "access_token": "tok"}, TODAY_2359_LOS_ANGELES)
    assert body["due_string"] == "2026-09-20"


@pytest.mark.asyncio
async def test_todoist_due_day_east_of_utc(user_zone):
    user_zone("Asia/Kolkata")
    body = await _create("todoist", {"connected": True, "access_token": "tok"}, TODAY_0200_KOLKATA)
    assert body["due_string"] == "2026-09-20"


@pytest.mark.asyncio
async def test_asana_due_day_is_the_users_local_day(user_zone):
    user_zone("America/Los_Angeles")
    integration = {
        "connected": True,
        "access_token": "tok",
        "workspace_gid": "ws",
        "expires_at": "2099-01-01T00:00:00+00:00",
    }
    body = await _create("asana", integration, TODAY_2359_LOS_ANGELES)
    assert body["data"]["due_on"] == "2026-09-20"


@pytest.mark.asyncio
async def test_google_tasks_due_day_is_the_users_local_day(user_zone):
    user_zone("America/Los_Angeles")
    integration = {
        "connected": True,
        "access_token": "tok",
        "default_list_id": "list-1",
        "expires_at": "2099-01-01T00:00:00+00:00",
    }
    body = await _create("google_tasks", integration, TODAY_2359_LOS_ANGELES)
    assert body["due"] == "2026-09-20T00:00:00.000Z"


@pytest.mark.asyncio
async def test_clickup_keeps_the_exact_instant(user_zone):
    user_zone("America/Los_Angeles")
    body = await _create("clickup", {"connected": True, "access_token": "tok", "list_id": "l"}, TODAY_2359_LOS_ANGELES)
    assert body["due_date"] == int(TODAY_2359_LOS_ANGELES.timestamp() * 1000)
