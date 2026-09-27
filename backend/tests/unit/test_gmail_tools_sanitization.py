import asyncio
import importlib.util
import pathlib
import sys
import types
from unittest.mock import MagicMock, patch

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

# Passthrough @tool decorator so the tool stays a plain callable.
sys.modules["langchain_core.tools"].tool = lambda func=None, **kw: (func if func is not None else (lambda f: f))
sys.modules["langchain_core.runnables"].RunnableConfig = dict

# Stub google_utils
google_utils = sys.modules["utils.retrieval.tools.google_utils"]
google_utils.GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
google_utils.google_integration_has_scope = lambda integration, scope: True
google_utils.google_api_request = MagicMock()
google_utils.refresh_google_token = MagicMock()

# Stub executors
executors = sys.modules["utils.executors"]
executors.db_executor = MagicMock()


async def _fake_run_blocking(executor, fn, *args, **kwargs):
    return fn(*args, **kwargs)


executors.run_blocking = _fake_run_blocking

# Stub integration_base
int_base = sys.modules["utils.retrieval.tools.integration_base"]
int_base.ensure_capped = lambda val, cap, msg: min(val, cap)
int_base.prepare_access = MagicMock()
int_base.retry_on_auth_async = MagicMock()


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


def test_gmail_tools_sanitizes_run_blocking_exception():
    with patch.object(gmail_tools, "run_blocking", side_effect=RuntimeError("threadpool_deadlock_secret_path_0xdead")):
        res = asyncio.run(gmail_tools.get_gmail_messages_tool())
        assert res == "Unexpected error fetching Gmail messages."
        assert "threadpool_deadlock_secret_path_0xdead" not in res


def test_gmail_tools_sanitizes_connection_error():
    fake_grant = ("uid1", None, None, "Error checking Gmail connection: /etc/secrets/google_oauth.json file not found")
    with patch.object(gmail_tools, "run_blocking", return_value=fake_grant):
        res = asyncio.run(gmail_tools.get_gmail_messages_tool())
        assert res == "Error checking Gmail connection."
        assert "/etc/secrets" not in res


def test_gmail_tools_sanitizes_api_exception():
    fake_grant = ("uid1", {"connected": True}, "test_token_secret_xyz", None)
    with (
        patch.object(gmail_tools, "run_blocking", return_value=fake_grant),
        patch.object(
            gmail_tools,
            "retry_on_auth_async",
            side_effect=RuntimeError("oauth token test_token_secret_xyz invalid ssl"),
        ),
    ):
        res = asyncio.run(gmail_tools.get_gmail_messages_tool())
        assert res == "Unexpected error fetching Gmail messages."
        assert "test_token_secret_xyz" not in res


if __name__ == "__main__":
    test_gmail_tools_sanitizes_run_blocking_exception()
    test_gmail_tools_sanitizes_connection_error()
    test_gmail_tools_sanitizes_api_exception()
    print("All Gmail tools sanitization unit tests passed successfully!")
