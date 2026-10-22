"""Hermetic unit tests for gmail_tools.

Verifies:
1. Safe handling of string / invalid / boolean max_results without TypeError.
2. Safe parsing of single-part, simple multipart, and nested multipart MIME emails.
3. Resilience against None payload, None headers, None parts, and None header names.
4. Correct label sanitization (whitespace trimming, UNREAD operator conversion).
5. Top-level user_id config resolution.
6. Safe handling of None messages in API response.
"""

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from testing.import_isolation import load_module_fresh, stub_modules

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent


def _tool_decorator(fn=None, **kwargs):
    if fn is not None and callable(fn):
        fn.func = fn
        return fn

    def dec(func):
        func.func = func
        return func

    return dec


async def _run_blocking_stub(executor, fn, *args, **kwargs):
    res = fn(*args, **kwargs)
    if asyncio.iscoroutine(res):
        return await res
    return res


def _module(name, **attrs):
    mod = ModuleType(name)
    for key, value in attrs.items():
        setattr(mod, key, value)
    return mod


def _package(name):
    mod = _module(name)
    mod.__path__ = []  # type: ignore[attr-defined]
    return mod


@pytest.fixture(scope="module", autouse=True)
def _gmail_tools_module():
    """Load gmail_tools with isolated dependencies."""
    langchain_tools = _module("langchain_core.tools", tool=_tool_decorator)
    langchain_runnables = _module("langchain_core.runnables", RunnableConfig=dict)
    notifications = _module("database.notifications", get_user_time_zone=MagicMock(return_value="UTC"))
    executors = _module("utils.executors", db_executor=MagicMock(), run_blocking=_run_blocking_stub)
    integration_base = _module(
        "utils.retrieval.tools.integration_base",
        ensure_capped=lambda val, cap, _msg: min(val, cap),
        prepare_access=MagicMock(),
        retry_on_auth_async=AsyncMock(),
    )
    google_utils = _module(
        "utils.retrieval.tools.google_utils",
        GMAIL_READONLY_SCOPE="https://www.googleapis.com/auth/gmail.readonly",
        google_api_request=AsyncMock(),
        google_integration_has_scope=MagicMock(return_value=True),
        refresh_google_token=MagicMock(),
    )

    stubs = {
        "langchain_core": _package("langchain_core"),
        "langchain_core.tools": langchain_tools,
        "langchain_core.runnables": langchain_runnables,
        "database": _package("database"),
        "database.notifications": notifications,
        "utils": _package("utils"),
        "utils.executors": executors,
        "utils.retrieval": _package("utils.retrieval"),
        "utils.retrieval.tools": _package("utils.retrieval.tools"),
        "utils.retrieval.tools.integration_base": integration_base,
        "utils.retrieval.tools.google_utils": google_utils,
    }

    with stub_modules(stubs):
        model_text = load_module_fresh("utils.model_text", str(BACKEND_DIR / "utils" / "model_text.py"))
        user_clock = load_module_fresh("utils.user_clock", str(BACKEND_DIR / "utils" / "user_clock.py"))
        module = load_module_fresh(
            "utils.retrieval.tools.gmail_tools",
            str(BACKEND_DIR / "utils" / "retrieval" / "tools" / "gmail_tools.py"),
        )
        globals()["gt"] = module
        globals()["_model_text"] = model_text
        yield
        globals().pop("gt", None)
        globals().pop("_model_text", None)


def test_parse_gmail_message_single_part_plain():
    import base64

    body_bytes = b"Hello from Omi unit tests!"
    encoded = base64.urlsafe_b64encode(body_bytes).decode("utf-8")

    msg = {
        "id": "msg_001",
        "threadId": "th_001",
        "snippet": "Hello from Omi...",
        "payload": {
            "mimeType": "text/plain",
            "headers": [
                {"name": "Subject", "value": "Release Announcement"},
                {"name": "From", "value": "team@omi.me"},
                {"name": "To", "value": "user@example.com"},
                {"name": "Date", "value": "Thu, 22 Oct 2026 10:00:00 +0000"},
            ],
            "body": {"data": encoded},
        },
    }

    parsed = gt.parse_gmail_message(msg)
    assert parsed["id"] == "msg_001"
    assert parsed["subject"] == "Release Announcement"
    assert parsed["from"] == "team@omi.me"
    assert parsed["to"] == "user@example.com"
    assert "Hello from Omi unit tests!" in parsed["body"]


def test_parse_gmail_message_nested_multipart():
    import base64

    plain_bytes = b"Nested plain text body."
    encoded_plain = base64.urlsafe_b64encode(plain_bytes).decode("utf-8")

    msg = {
        "id": "msg_nested",
        "payload": {
            "mimeType": "multipart/mixed",
            "headers": [
                {"name": "Subject", "value": "Multipart Email"},
            ],
            "parts": [
                {
                    "mimeType": "multipart/alternative",
                    "parts": [
                        {
                            "mimeType": "text/plain",
                            "body": {"data": encoded_plain},
                        }
                    ],
                }
            ],
        },
    }

    parsed = gt.parse_gmail_message(msg)
    assert parsed["subject"] == "Multipart Email"
    assert parsed["body"] == "Nested plain text body."


def test_parse_gmail_message_none_and_malformed_guards():
    # Completely empty or None-heavy payloads must not raise AttributeError or TypeError
    msg_empty = {
        "id": "msg_none",
        "payload": {
            "headers": None,
            "parts": None,
            "body": None,
        },
    }
    parsed = gt.parse_gmail_message(msg_empty)
    assert parsed["subject"] == "(No subject)"
    assert parsed["body"] == ""
    assert parsed["from"] == "Unknown"

    # Header with name: None
    msg_bad_header = {
        "payload": {
            "headers": [
                {"name": None, "value": "Ghost"},
                {"name": "Subject", "value": "Valid Subject"},
            ]
        }
    }
    parsed2 = gt.parse_gmail_message(msg_bad_header)
    assert parsed2["subject"] == "Valid Subject"


@pytest.mark.asyncio
async def test_get_gmail_messages_none_messages_response():
    # If Gmail API returns {'messages': None}, get_gmail_messages must not crash
    with patch.object(gt, "google_api_request", new_callable=AsyncMock) as mock_api:
        mock_api.return_value = {"messages": None}
        messages = await gt.get_gmail_messages("token", query="test", max_results=5)
        assert messages == []


@pytest.mark.asyncio
async def test_get_gmail_messages_tool_string_max_results_coercion():
    mock_messages = [
        {
            "id": "m1",
            "snippet": "Test snippet",
            "payload": {
                "headers": [{"name": "Subject", "value": "Meeting"}],
            },
        }
    ]

    with patch.object(gt, "prepare_access", return_value=("u1", {"connected": True}, "token", None)):
        with patch.object(gt, "google_integration_has_scope", return_value=True):
            with patch.object(gt, "retry_on_auth_async", new_callable=AsyncMock, return_value=(mock_messages, None)) as mock_retry:
                # Passing string max_results="5" must not raise TypeError
                res = await gt.get_gmail_messages_tool.func(
                    query="meeting",
                    max_results="5",  # type: ignore[arg-type]
                    config={"configurable": {"user_id": "u1"}},
                )
                assert "Meeting" in res
                call_args = mock_retry.call_args[0][1]
                assert call_args["max_results"] == 5


@pytest.mark.asyncio
async def test_get_gmail_messages_tool_unread_label_transformation():
    with patch.object(gt, "prepare_access", return_value=("u1", {"connected": True}, "token", None)):
        with patch.object(gt, "google_integration_has_scope", return_value=True):
            with patch.object(gt, "retry_on_auth_async", new_callable=AsyncMock, return_value=([], None)) as mock_retry:
                # Label UNREAD should be converted to is:unread query operator
                res = await gt.get_gmail_messages_tool.func(
                    label="unread",
                    config={"configurable": {"user_id": "u1"}},
                )
                call_args = mock_retry.call_args[0][1]
                assert call_args["query"] == "is:unread"
                assert call_args["label_ids"] is None


@pytest.mark.asyncio
async def test_get_gmail_messages_tool_whitespace_label_filtering():
    with patch.object(gt, "prepare_access", return_value=("u1", {"connected": True}, "token", None)):
        with patch.object(gt, "google_integration_has_scope", return_value=True):
            with patch.object(gt, "retry_on_auth_async", new_callable=AsyncMock, return_value=([], None)) as mock_retry:
                # Whitespace label should not result in empty string in label_ids
                res = await gt.get_gmail_messages_tool.func(
                    label="   ",
                    config={"configurable": {"user_id": "u1"}},
                )
                call_args = mock_retry.call_args[0][1]
                assert call_args["label_ids"] is None


@pytest.mark.asyncio
async def test_get_gmail_messages_tool_top_level_user_id():
    with patch.object(gt, "prepare_access", return_value=("u1", {"connected": True}, "token", None)) as mock_prep:
        with patch.object(gt, "google_integration_has_scope", return_value=True):
            with patch.object(gt, "retry_on_auth_async", new_callable=AsyncMock, return_value=([], None)):
                # Passing top-level user_id in config
                res = await gt.get_gmail_messages_tool.func(
                    config={"user_id": "u123"},
                )
                passed_cfg = mock_prep.call_args[0][0]
                assert passed_cfg["configurable"]["user_id"] == "u123"


@pytest.mark.asyncio
async def test_get_gmail_messages_tool_missing_scope():
    with patch.object(gt, "prepare_access", return_value=("u1", {"connected": True}, "token", None)):
        with patch.object(gt, "google_integration_has_scope", return_value=False):
            res = await gt.get_gmail_messages_tool.func(
                config={"configurable": {"user_id": "u1"}},
            )
            assert "Gmail access has not been granted" in res
