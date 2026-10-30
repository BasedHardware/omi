"""Tests verifying defensive parameter guards and exception handling in gmail_tools.py.

Hermetic isolated unit test suite covering:
1. parse_gmail_message handles None, malformed message dicts, and non-dict payloads.
2. parse_gmail_message defensively handles malformed headers (None entries, missing name/value).
3. parse_gmail_message defensively handles malformed parts (None entries, missing body, corrupt base64 data).
4. parse_gmail_message decodes plain text and HTML fallback correctly.
5. get_gmail_messages_tool coerces and bounds max_results safely.
6. get_gmail_messages_tool defensively processes label and rewrites UNREAD search queries.

Uses memory_import_isolation snapshot_sys_modules and restore_sys_modules.
"""

import asyncio
import base64
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import AsyncMock, MagicMock

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent

try:
    from tests.unit.memory_import_isolation import (
        AutoMockModule,
        restore_sys_modules,
        snapshot_sys_modules,
    )
except ImportError:
    class AutoMockModule(types.ModuleType):
        def __getattr__(self, name: str):
            if name.startswith("__") and name.endswith("__"):
                raise AttributeError(name)
            mock = MagicMock()
            setattr(self, name, mock)
            return mock

    def snapshot_sys_modules(names):
        return {name: sys.modules.get(name) for name in names}

    def restore_sys_modules(saved):
        for name, original in saved.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


_SYS_MODULE_NAMES = [
    "langchain_core",
    "langchain_core.tools",
    "langchain_core.runnables",
    "utils",
    "utils.executors",
    "utils.model_text",
    "utils.user_clock",
    "utils.retrieval",
    "utils.retrieval.tools",
    "utils.retrieval.tools.integration_base",
    "utils.retrieval.tools.google_utils",
    "utils.retrieval.tools._gmail_tools_guards_test",
]

_SYS_MODULES_SNAPSHOT = snapshot_sys_modules(_SYS_MODULE_NAMES)


def _pkg(name: str):
    mod = types.ModuleType(name)
    mod.__path__ = []
    sys.modules[name] = mod
    if "." in name:
        parent_name, attr_name = name.rsplit(".", 1)
        parent = sys.modules.get(parent_name)
        if isinstance(parent, types.ModuleType):
            setattr(parent, attr_name, mod)
    return mod


def _mod(name: str):
    mod = AutoMockModule(name)
    sys.modules[name] = mod
    if "." in name:
        parent_name, attr_name = name.rsplit(".", 1)
        parent = sys.modules.get(parent_name)
        if isinstance(parent, types.ModuleType):
            setattr(parent, attr_name, mod)
    return mod


def _load(module_name: str, rel_path: str):
    spec = importlib.util.spec_from_file_location(module_name, str(BACKEND_DIR / rel_path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


def _tool_decorator(fn=None, **kwargs):
    if fn is not None and callable(fn):
        fn.func = fn
        return fn

    def dec(func):
        func.func = func
        return func

    return dec


# Install hermetic stubs
_pkg("langchain_core")
_lc_tools = _mod("langchain_core.tools")
_lc_tools.tool = _tool_decorator

_lc_runnables = _mod("langchain_core.runnables")
_lc_runnables.RunnableConfig = dict

_pkg("utils")
_executors = _mod("utils.executors")
_executors.db_executor = MagicMock()
_executors.run_blocking = AsyncMock(return_value=("test_user_42", MagicMock(), "fake_access_token", None))

_model_text = _mod("utils.model_text")
_model_text.DisplayClock = MagicMock
_model_text.UNTRUSTED_LEGEND = "[UNTRUSTED CONTENT]"
_model_text.count_header = lambda count, word, prefix="": f"{prefix}{count} {word}"
_model_text.format_instant = lambda d, user_clock=None: str(d)
_model_text.truncation_note = lambda *a, **k: ""
_model_text.untrusted_block = lambda content, **k: f"<<<{content}>>>"

_uclock = _mod("utils.user_clock")
_uclock.clock_for_config = lambda *a, **k: None

_pkg("utils.retrieval")
_pkg("utils.retrieval.tools")

_int_base = _mod("utils.retrieval.tools.integration_base")


def _ensure_capped(val, cap, msg=""):
    return min(val, cap)


_int_base.ensure_capped = _ensure_capped
_int_base.prepare_access = MagicMock(return_value=(
    {"configurable": {"user_id": "test_user_42"}},
    "test_user_42",
    None,
))

# Capture call params in retry_on_auth_async
_last_fetch_params = {}


_captured_calls = []


async def _fake_retry_on_auth_async(coro_fn, *args, **kwargs):
    fn_args = args[0] if args and isinstance(args[0], dict) else kwargs
    _captured_calls.append(fn_args)
    return [], None


_int_base.retry_on_auth_async = _fake_retry_on_auth_async

_gutils = _mod("utils.retrieval.tools.google_utils")
_gutils.GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
_gutils.google_integration_has_scope = MagicMock(return_value=True)

# Load module under test
gt = _load(
    "utils.retrieval.tools._gmail_tools_guards_test",
    "utils/retrieval/tools/gmail_tools.py",
)


def tearDownModule():
    restore_sys_modules(_SYS_MODULES_SNAPSHOT)


class TestGmailToolsGuards(unittest.TestCase):
    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.config = {"configurable": {"user_id": "test_user_42"}}

    def tearDown(self):
        self.loop.close()

    # 1. parse_gmail_message handles None, malformed message dicts, and non-dict payloads
    def test_parse_gmail_message_resilience(self):
        # None message
        res_none = gt.parse_gmail_message(None)
        self.assertIsInstance(res_none, dict)
        self.assertEqual(res_none.get("subject"), "(No subject)")
        self.assertEqual(res_none.get("body"), "")

        # String message
        res_str = gt.parse_gmail_message("not_a_dict")
        self.assertIsInstance(res_str, dict)

        # Message with non-dict payload
        res_bad_payload = gt.parse_gmail_message({"payload": "invalid_payload"})
        self.assertEqual(res_bad_payload.get("subject"), "(No subject)")

    # 2. parse_gmail_message defensively handles malformed headers
    def test_parse_gmail_message_headers_defense(self):
        headers = [
            None,
            "not_a_dict",
            {"name": None, "value": "some_value"},
            {"name": "Subject", "value": None},
            {"name": "Subject", "value": "Weekly Project Update"},
            {"name": "From", "value": "team@example.com"},
            {"name": "Date", "value": "invalid_date_string"},
        ]
        msg = {
            "id": "msg-001",
            "snippet": "Here is the weekly update...",
            "payload": {"headers": headers},
        }
        res = gt.parse_gmail_message(msg)
        self.assertEqual(res.get("subject"), "Weekly Project Update")
        self.assertEqual(res.get("from"), "team@example.com")
        self.assertEqual(res.get("snippet"), "Here is the weekly update...")

    # 3. parse_gmail_message defensively handles malformed parts and decodes plain text
    def test_parse_gmail_message_parts_and_decoding(self):
        encoded_text = base64.urlsafe_b64encode(b"Meeting scheduled for 3pm.").decode("utf-8")
        parts = [
            None,
            "string_part",
            {"mimeType": "application/pdf"},
            {"mimeType": "text/plain", "body": None},
            {"mimeType": "text/plain", "body": {"data": encoded_text}},
        ]
        msg = {
            "payload": {
                "parts": parts,
                "headers": [{"name": "Subject", "value": "Meeting"}],
            }
        }
        res = gt.parse_gmail_message(msg)
        self.assertEqual(res.get("body"), "Meeting scheduled for 3pm.")

    # 4. parse_gmail_message falls back to HTML if plain text missing
    def test_parse_gmail_message_html_fallback(self):
        encoded_html = base64.urlsafe_b64encode(b"<div><strong>Invoice Paid</strong></div>").decode("utf-8")
        parts = [
            {"mimeType": "text/html", "body": {"data": encoded_html}},
        ]
        msg = {
            "payload": {
                "parts": parts,
                "headers": [{"name": "Subject", "value": "Receipt"}],
            }
        }
        res = gt.parse_gmail_message(msg)
        self.assertIn("Invoice Paid", res.get("body"))

    # 5. get_gmail_messages_tool coerces and bounds max_results safely
    def test_get_gmail_messages_tool_max_results_coercion(self):
        async def run():
            # String integer "25"
            await gt.get_gmail_messages_tool.func(max_results="25", config=self.config)
            self.assertEqual(_captured_calls[-1].get("max_results"), 25)

            # Capped to 50 when out of bounds
            await gt.get_gmail_messages_tool.func(max_results=500, config=self.config)
            self.assertEqual(_captured_calls[-1].get("max_results"), 50)

            # Negative bounded to 1
            await gt.get_gmail_messages_tool.func(max_results=-5, config=self.config)
            self.assertEqual(_captured_calls[-1].get("max_results"), 1)

            # Invalid string falls back to 10
            await gt.get_gmail_messages_tool.func(max_results="invalid", config=self.config)
            self.assertEqual(_captured_calls[-1].get("max_results"), 10)

        self.loop.run_until_complete(run())

    # 6. get_gmail_messages_tool handles label and UNREAD search operator
    def test_get_gmail_messages_tool_label_handling(self):
        async def run():
            # label="UNREAD" converts to query
            await gt.get_gmail_messages_tool.func(label="UNREAD", config=self.config)
            self.assertEqual(_captured_calls[-1].get("query"), "is:unread")
            self.assertIsNone(_captured_calls[-1].get("label_ids"))

            # label="unread" with existing query
            await gt.get_gmail_messages_tool.func(query="from:alice", label="unread", config=self.config)
            self.assertEqual(_captured_calls[-1].get("query"), "from:alice is:unread")

            # Standard label like INBOX
            await gt.get_gmail_messages_tool.func(label="inbox", config=self.config)
            self.assertEqual(_captured_calls[-1].get("label_ids"), ["INBOX"])

            # Non-string label handled gracefully
            await gt.get_gmail_messages_tool.func(label=123, config=self.config)
            self.assertIsNone(_captured_calls[-1].get("label_ids"))

        self.loop.run_until_complete(run())


if __name__ == "__main__":
    unittest.main()
