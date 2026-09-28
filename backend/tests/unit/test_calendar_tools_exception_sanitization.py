import os
from unittest.mock import AsyncMock, patch

import pytest

os.environ.setdefault("ENCRYPTION_SECRET", "0123456789abcdef0123456789abcdef")

from utils.retrieval.tools import calendar_tools
from utils.retrieval.tools.google_utils import GoogleAPIError


@pytest.fixture
def mock_prepare_access():
    async def _mock_run_blocking(executor, fn, *args, **kwargs):
        if fn == calendar_tools.prepare_access:
            return ("uid-123", {"connected": True}, "mock-token", None)
        return await fn(*args, **kwargs)

    with patch.object(calendar_tools, "run_blocking", side_effect=_mock_run_blocking):
        yield


@pytest.mark.asyncio
async def test_delete_by_id_unexpected_error_sanitized(mock_prepare_access, caplog):
    sensitive_err = "Sensitive internal database timeout at internal-db.cluster:5432"
    with (
        patch.object(
            calendar_tools,
            "delete_google_calendar_event",
            side_effect=Exception(sensitive_err),
        ),
        caplog.at_level("ERROR"),
    ):
        res = await calendar_tools.delete_calendar_event_tool.coroutine(
            event_id="evt_123"
        )

    assert "internal-db.cluster" not in res
    assert (
        res
        == "An unexpected error occurred while deleting the calendar event. Please try again later."
    )
    assert sensitive_err in caplog.text


@pytest.mark.asyncio
async def test_delete_by_id_retry_error_sanitized(mock_prepare_access, caplog):
    sensitive_retry_err = "OAuth2 refresh failed with token AIzaSySecret123"
    api_err = GoogleAPIError(status_code=401, message="Unauthorized")

    with (
        patch.object(
            calendar_tools,
            "delete_google_calendar_event",
            side_effect=[api_err, Exception(sensitive_retry_err)],
        ),
        patch.object(
            calendar_tools,
            "refresh_google_token",
            new=AsyncMock(return_value="new-token"),
        ),
        caplog.at_level("ERROR"),
    ):
        res = await calendar_tools.delete_calendar_event_tool.coroutine(
            event_id="evt_123"
        )

    assert "AIzaSySecret123" not in res
    assert (
        res
        == "An unexpected error occurred while deleting the calendar event. Please try again later."
    )
    assert sensitive_retry_err in caplog.text


@pytest.mark.asyncio
async def test_delete_events_by_search_item_failure_sanitized(
    mock_prepare_access, caplog
):
    sensitive_item_err = "S3 NoSuchKey exception: secret-bucket-id-999"
    matching = [{"id": "ev1", "summary": "Executive Strategy"}]

    with (
        patch.object(
            calendar_tools,
            "get_google_calendar_events",
            new=AsyncMock(return_value=matching),
        ),
        patch.object(
            calendar_tools,
            "delete_google_calendar_event",
            side_effect=Exception(sensitive_item_err),
        ),
        caplog.at_level("ERROR"),
    ):
        res = await calendar_tools.delete_calendar_event_tool.coroutine(
            event_title="Executive",
            start_date="2026-09-28T10:00:00Z",
        )

    assert "secret-bucket-id-999" not in res
    assert "Failed to delete event" in res
    assert sensitive_item_err in caplog.text


@pytest.mark.asyncio
async def test_delete_events_by_search_retry_item_failure_sanitized(
    mock_prepare_access, caplog
):
    sensitive_retry_item_err = "Internal socket error: 10.100.0.4:8080"
    api_err = GoogleAPIError(status_code=401, message="Unauthorized")

    matching = [{"id": "ev2", "summary": "Board Meeting"}]

    with (
        patch.object(
            calendar_tools,
            "get_google_calendar_events",
            side_effect=[api_err, matching],
        ),
        patch.object(
            calendar_tools,
            "refresh_google_token",
            new=AsyncMock(return_value="new-token"),
        ),
        patch.object(
            calendar_tools,
            "delete_google_calendar_event",
            side_effect=Exception(sensitive_retry_item_err),
        ),
        caplog.at_level("ERROR"),
    ):
        res = await calendar_tools.delete_calendar_event_tool.coroutine(
            event_title="Board",
            start_date="2026-09-28T10:00:00Z",
        )

    assert "10.100.0.4" not in res
    assert "Failed to delete event" in res
    assert sensitive_retry_item_err in caplog.text


@pytest.mark.asyncio
async def test_delete_events_retry_block_exception_sanitized(
    mock_prepare_access, caplog
):
    sensitive_retry_block_err = "Google API quota crash token=topsecrettoken"
    api_err = GoogleAPIError(status_code=401, message="Unauthorized")

    with (
        patch.object(
            calendar_tools,
            "get_google_calendar_events",
            side_effect=[api_err, Exception(sensitive_retry_block_err)],
        ),
        patch.object(
            calendar_tools,
            "refresh_google_token",
            new=AsyncMock(return_value="new-token"),
        ),
        caplog.at_level("ERROR"),
    ):
        res = await calendar_tools.delete_calendar_event_tool.coroutine(
            event_title="Any",
            start_date="2026-09-28T10:00:00Z",
        )

    assert "topsecrettoken" not in res
    assert (
        res
        == "An unexpected error occurred while deleting calendar events. Please try again later."
    )
    assert sensitive_retry_block_err in caplog.text


@pytest.mark.asyncio
async def test_delete_events_search_exception_sanitized(mock_prepare_access, caplog):
    sensitive_search_err = "Query parse error with credentials creds=user:password123"

    with (
        patch.object(
            calendar_tools,
            "get_google_calendar_events",
            side_effect=Exception(sensitive_search_err),
        ),
        caplog.at_level("ERROR"),
    ):
        res = await calendar_tools.delete_calendar_event_tool.coroutine(
            event_title="Review",
            start_date="2026-09-28T10:00:00Z",
        )

    assert "password123" not in res
    assert res == "An unexpected error occurred while searching for calendar events."
    assert sensitive_search_err in caplog.text


@pytest.mark.asyncio
async def test_delete_events_outer_exception_sanitized(mock_prepare_access, caplog):
    sensitive_outer_err = "Fatal memory leak in event loop heap_addr=0xdeadbeef"

    with (
        patch.object(
            calendar_tools,
            "parse_iso_with_tz",
            side_effect=Exception(sensitive_outer_err),
        ),
        caplog.at_level("ERROR"),
    ):
        res = await calendar_tools.delete_calendar_event_tool.coroutine(
            event_title="Review",
            start_date="2026-09-28T10:00:00Z",
        )

    assert "0xdeadbeef" not in res
    assert (
        res
        == "An unexpected error occurred while deleting calendar events. Please try again later."
    )
    assert sensitive_outer_err in caplog.text


@pytest.mark.asyncio
async def test_update_event_search_exception_sanitized(mock_prepare_access, caplog):
    sensitive_search_err = "Internal ElasticSearch failure cluster_key=es_prod_key_777"

    with (
        patch.object(
            calendar_tools,
            "get_google_calendar_events",
            side_effect=Exception(sensitive_search_err),
        ),
        caplog.at_level("ERROR"),
    ):
        res = await calendar_tools.update_calendar_event_tool.coroutine(
            event_title="Sync",
            title="Updated Title",
        )

    assert "es_prod_key_777" not in res
    assert res == "An unexpected error occurred while searching for the calendar event."
    assert sensitive_search_err in caplog.text


@pytest.mark.asyncio
async def test_update_event_get_event_retry_exception_sanitized(
    mock_prepare_access, caplog
):
    sensitive_retry_err = "TLS certificate validation failed: cert=privkey.pem"
    api_err = GoogleAPIError(status_code=401, message="Unauthorized")

    with (
        patch.object(
            calendar_tools,
            "get_google_calendar_event",
            side_effect=[api_err, Exception(sensitive_retry_err)],
        ),
        patch.object(
            calendar_tools,
            "refresh_google_token",
            new=AsyncMock(return_value="new-token"),
        ),
        caplog.at_level("ERROR"),
    ):
        res = await calendar_tools.update_calendar_event_tool.coroutine(
            event_id="evt_555",
            title="Updated Title",
        )

    assert "privkey.pem" not in res
    assert res == "An unexpected error occurred while retrieving the calendar event."
    assert sensitive_retry_err in caplog.text


@pytest.mark.asyncio
async def test_update_event_get_event_unexpected_exception_sanitized(
    mock_prepare_access, caplog
):
    sensitive_err = "Connection reset by peer host=192.168.1.100"

    with (
        patch.object(
            calendar_tools,
            "get_google_calendar_event",
            side_effect=Exception(sensitive_err),
        ),
        caplog.at_level("ERROR"),
    ):
        res = await calendar_tools.update_calendar_event_tool.coroutine(
            event_id="evt_555",
            title="Updated Title",
        )

    assert "192.168.1.100" not in res
    assert res == "An unexpected error occurred while retrieving the calendar event."
    assert sensitive_err in caplog.text


@pytest.mark.asyncio
async def test_update_event_update_retry_exception_sanitized(
    mock_prepare_access, caplog
):
    sensitive_retry_err = "Update failed on endpoint with auth=bearer_token_999"
    api_err = GoogleAPIError(status_code=401, message="Unauthorized")

    with (
        patch.object(
            calendar_tools,
            "get_google_calendar_event",
            new=AsyncMock(return_value={"id": "evt_555", "summary": "Old Title"}),
        ),
        patch.object(
            calendar_tools,
            "update_google_calendar_event",
            side_effect=[api_err, Exception(sensitive_retry_err)],
        ),
        patch.object(
            calendar_tools,
            "refresh_google_token",
            new=AsyncMock(return_value="new-token"),
        ),
        caplog.at_level("ERROR"),
    ):
        res = await calendar_tools.update_calendar_event_tool.coroutine(
            event_id="evt_555",
            title="Updated Title",
        )

    assert "bearer_token_999" not in res
    assert (
        res
        == "An unexpected error occurred while updating the calendar event. Please try again later."
    )
    assert sensitive_retry_err in caplog.text


@pytest.mark.asyncio
async def test_update_event_outer_exception_sanitized(mock_prepare_access, caplog):
    sensitive_outer_err = (
        "Critical crash during payload serialization: secret_env=MY_SECRET"
    )

    with (
        patch.object(
            calendar_tools,
            "get_google_calendar_event",
            new=AsyncMock(return_value={"id": "evt_555", "summary": "Old Title"}),
        ),
        patch.object(
            calendar_tools,
            "update_google_calendar_event",
            side_effect=Exception(sensitive_outer_err),
        ),
        caplog.at_level("ERROR"),
    ):
        res = await calendar_tools.update_calendar_event_tool.coroutine(
            event_id="evt_555",
            title="Updated Title",
        )

    assert "MY_SECRET" not in res
    assert (
        res
        == "An unexpected error occurred while updating the calendar event. Please try again later."
    )
    assert sensitive_outer_err in caplog.text
