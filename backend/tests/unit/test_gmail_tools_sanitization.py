import asyncio
import importlib.util
import pathlib
import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

BACKEND_DIR = pathlib.Path(__file__).resolve().parent.parent.parent


def _register(name: str):
    if name in sys.modules:
        return sys.modules[name]
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    if "." in name:
        parent_name, attr = name.rsplit(".", 1)
        setattr(_register(parent_name), attr, mod)
    return mod


for _name in [
    "langchain_core",
    "langchain_core.tools",
    "langchain_core.runnables",
    "utils",
    "utils.executors",
    "utils.retrieval",
    "utils.retrieval.tools",
    "utils.retrieval.tools.integration_base",
    "utils.retrieval.tools.google_utils",
]:
    _register(_name)

# Passthrough @tool decorator so tools remain plain callables
sys.modules["langchain_core.tools"].tool = lambda func=None, **kw: (func if func is not None else (lambda f: f))
sys.modules["langchain_core.runnables"].RunnableConfig = dict


# Stub utils.executors
async def _dummy_run_blocking(executor, func, *args, **kwargs):
    return func(*args, **kwargs)


sys.modules["utils.executors"].db_executor = MagicMock()
sys.modules["utils.executors"].run_blocking = _dummy_run_blocking

# Stub integration_base
sys.modules["utils.retrieval.tools.integration_base"].ensure_capped = lambda val, cap, msg: min(val, cap)
sys.modules["utils.retrieval.tools.integration_base"].prepare_access = MagicMock(
    return_value=("uid_123", {"connected": True}, "token_abc", None)
)
sys.modules["utils.retrieval.tools.integration_base"].retry_on_auth_async = AsyncMock(return_value=([], None))

# Stub google_utils
sys.modules["utils.retrieval.tools.google_utils"].GMAIL_READONLY_SCOPE = (
    "https://www.googleapis.com/auth/gmail.readonly"
)
sys.modules["utils.retrieval.tools.google_utils"].google_api_request = AsyncMock()
sys.modules["utils.retrieval.tools.google_utils"].google_integration_has_scope = MagicMock(return_value=True)
sys.modules["utils.retrieval.tools.google_utils"].refresh_google_token = AsyncMock()


def _load_module_from_file(module_name: str, file_path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(module_name, str(file_path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


gmail_tools = _load_module_from_file(
    "utils.retrieval.tools.gmail_tools",
    BACKEND_DIR / "utils" / "retrieval" / "tools" / "gmail_tools.py",
)


def test_get_gmail_messages_tool_sanitizes_fetch_exception():
    secret_leak = "internal_auth_token_secret_xyz123_at_10.0.0.5"
    with patch.object(
        gmail_tools,
        "prepare_access",
        return_value=("uid_123", {"connected": True}, "token_abc", None),
    ), patch.object(
        gmail_tools,
        "google_integration_has_scope",
        return_value=True,
    ), patch.object(
        gmail_tools,
        "retry_on_auth_async",
        new=AsyncMock(side_effect=RuntimeError(secret_leak)),
    ):
        result = asyncio.run(gmail_tools.get_gmail_messages_tool())
        assert result == "Unexpected error fetching Gmail messages."
        assert secret_leak not in result


def test_get_gmail_messages_tool_sanitizes_prepare_access_exception():
    secret_leak = "db_connection_failed_pg_user_root_pass_secret"
    with patch.object(
        gmail_tools,
        "prepare_access",
        side_effect=RuntimeError(secret_leak),
    ):
        result = asyncio.run(gmail_tools.get_gmail_messages_tool())
        assert result == "Unexpected error fetching Gmail messages."
        assert secret_leak not in result


def test_get_gmail_messages_tool_safe_on_missing_integration_or_token():
    # When uid or integration or token is None without access_err, it returns safe connection message
    with patch.object(
        gmail_tools,
        "prepare_access",
        return_value=(None, None, None, None),
    ):
        result = asyncio.run(gmail_tools.get_gmail_messages_tool())
        assert result == "Gmail is not connected. Please connect your Google account from settings to view your emails."

    # When token is None
    with patch.object(
        gmail_tools,
        "prepare_access",
        return_value=("uid_123", {"connected": True}, None, None),
    ):
        result = asyncio.run(gmail_tools.get_gmail_messages_tool())
        assert result == "Gmail is not connected. Please connect your Google account from settings to view your emails."


def test_get_gmail_messages_tool_returns_access_error():
    with patch.object(
        gmail_tools,
        "prepare_access",
        return_value=(None, None, None, "Config missing user_id"),
    ):
        result = asyncio.run(gmail_tools.get_gmail_messages_tool())
        assert result == "Config missing user_id"


def test_get_gmail_messages_tool_scope_check():
    with patch.object(
        gmail_tools,
        "prepare_access",
        return_value=("uid_123", {"connected": True}, "token_abc", None),
    ), patch.object(
        gmail_tools,
        "google_integration_has_scope",
        return_value=False,
    ):
        result = asyncio.run(gmail_tools.get_gmail_messages_tool())
        assert "Gmail access has not been granted for this Google account" in result


def test_get_gmail_messages_tool_success_formatting():
    fake_msg = {
        "id": "msg_001",
        "threadId": "th_001",
        "payload": {
            "headers": [
                {"name": "Subject", "value": "Team Meeting"},
                {"name": "From", "value": "alice@example.com"},
                {"name": "To", "value": "bob@example.com"},
                {"name": "Date", "value": "Wed, 23 Sep 2026 12:00:00 +0000"},
            ],
            "mimeType": "text/plain",
            "body": {"data": "SGVsbG8gV29ybGQ="},  # base64 "Hello World"
        },
        "snippet": "Hello World snippet",
    }

    with patch.object(
        gmail_tools,
        "prepare_access",
        return_value=("uid_123", {"connected": True}, "token_abc", None),
    ), patch.object(
        gmail_tools,
        "google_integration_has_scope",
        return_value=True,
    ), patch.object(
        gmail_tools,
        "retry_on_auth_async",
        new=AsyncMock(return_value=([fake_msg], None)),
    ):
        result = asyncio.run(gmail_tools.get_gmail_messages_tool())
        assert "Gmail Messages (1 found):" in result
        assert "1. Team Meeting" in result
        assert "From: alice@example.com" in result
        assert "To: bob@example.com" in result
        assert "Preview: Hello World snippet" in result


def test_get_gmail_messages_tool_no_messages_found():
    with patch.object(
        gmail_tools,
        "prepare_access",
        return_value=("uid_123", {"connected": True}, "token_abc", None),
    ), patch.object(
        gmail_tools,
        "google_integration_has_scope",
        return_value=True,
    ), patch.object(
        gmail_tools,
        "retry_on_auth_async",
        new=AsyncMock(return_value=([], None)),
    ):
        result = asyncio.run(gmail_tools.get_gmail_messages_tool(query="quarterly budget", label="INBOX"))
        assert result == "No emails found matching 'quarterly budget' in INBOX."


def test_parse_gmail_message_multipart_fallback():
    import base64

    # HTML only in multipart
    fake_multipart = {
        "id": "msg_002",
        "threadId": "th_002",
        "payload": {
            "headers": [
                {"name": "Subject", "value": "Newsletter"},
                {"name": "From", "value": "news@example.com"},
                {"name": "To", "value": "reader@example.com"},
                {"name": "Date", "value": "invalid-date-format"},
            ],
            "parts": [
                {
                    "mimeType": "text/html",
                    "body": {"data": base64.urlsafe_b64encode(b"<b>News content</b>").decode("utf-8")},
                }
            ],
        },
        "snippet": "News snippet",
    }

    parsed = gmail_tools.parse_gmail_message(fake_multipart)
    assert parsed["id"] == "msg_002"
    assert parsed["subject"] == "Newsletter"
    assert parsed["from"] == "news@example.com"
    assert parsed["body"] == "<b>News content</b>"
    assert parsed["date"] == "invalid-date-format"


if __name__ == "__main__":
    test_get_gmail_messages_tool_sanitizes_fetch_exception()
    test_get_gmail_messages_tool_sanitizes_prepare_access_exception()
    test_get_gmail_messages_tool_safe_on_missing_integration_or_token()
    test_get_gmail_messages_tool_returns_access_error()
    test_get_gmail_messages_tool_scope_check()
    test_get_gmail_messages_tool_success_formatting()
    test_get_gmail_messages_tool_no_messages_found()
    test_parse_gmail_message_multipart_fallback()
    print("All 8 unit tests passed successfully!")
