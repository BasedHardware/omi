"""/update-list, /update-timezone, /refresh-lists and /logout returned f"{e}" straight to the
caller on any unhandled exception -- an internal exception message can carry detail (a file
path, a downstream response fragment, a host) that has no reason to reach an HTTP response.
Every other exception handler in this file already logs only `type(e).__name__`
(see e.g. the OAuth callback and timeout-monitor handlers); these four were the exceptions.
Now they follow the same convention: log the real exception server-side, return a fixed,
generic message.
"""

import asyncio
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch


class Framework:
    def __init__(self, *args, **kwargs):
        pass

    def get(self, *args, **kwargs):
        return lambda function: function

    post = on_event = get


class Response:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def module(name, **attributes):
    value = types.ModuleType(name)
    value.__dict__.update(attributes)
    return value


stubs = {
    "dotenv": module("dotenv", load_dotenv=lambda: None),
    "fastapi": module("fastapi", FastAPI=Framework, Request=Framework, Query=Framework, HTTPException=Exception),
    "fastapi.responses": module(
        "fastapi.responses", HTMLResponse=Response, RedirectResponse=Response, JSONResponse=Response
    ),
    "simple_storage": module("simple_storage", SimpleUserStorage=Mock(), SimpleSessionStorage=Mock()),
    "clickup_client": module("clickup_client", ClickUpClient=Mock),
    "task_detector": module("task_detector", TaskDetector=Mock),
    "omi_notifications": module("omi_notifications", notify_task_created=Mock(), notify_task_failed=Mock()),
}
spec = importlib.util.spec_from_file_location("clickup_leak_under_test", Path(__file__).with_name("main.py"))
main = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, stubs):
    spec.loader.exec_module(main)


SENSITIVE_DETAIL = "psycopg2.OperationalError: could not connect to server at 10.0.4.12:5432, password authentication failed for user 'clickup_app'"


class ErrorMessagesDoNotLeakTests(unittest.TestCase):
    def assert_generic_and_silent(self, response, expected_message):
        self.assertFalse(response["success"])
        self.assertEqual(response["error"], expected_message)
        self.assertNotIn("10.0.4.12", response["error"])
        self.assertNotIn("password authentication", response["error"])

    def test_update_list_does_not_leak_the_storage_exception(self):
        with patch.object(main.SimpleUserStorage, "update_list_selection", side_effect=RuntimeError(SENSITIVE_DETAIL)):
            res = asyncio.run(main.update_list(uid="u1", list="l1"))
        self.assert_generic_and_silent(res, "Failed to update default list.")

    def test_update_timezone_does_not_leak_the_storage_exception(self):
        with patch.object(main.SimpleUserStorage, "update_timezone", side_effect=RuntimeError(SENSITIVE_DETAIL)):
            res = asyncio.run(main.update_timezone(uid="u1", timezone="America/Los_Angeles"))
        self.assert_generic_and_silent(res, "Failed to update timezone.")

    def test_refresh_lists_does_not_leak_the_clickup_client_exception(self):
        with patch.object(
            main.SimpleUserStorage, "get_user", return_value={"access_token": "tok", "team_id": "t1"}
        ), patch.object(main.clickup_client, "get_workspaces", side_effect=RuntimeError(SENSITIVE_DETAIL)):
            res = asyncio.run(main.refresh_lists(uid="u1"))
        self.assert_generic_and_silent(res, "Failed to refresh lists from ClickUp.")

    def test_logout_does_not_leak_the_storage_exception(self):
        broken_users = Mock()
        broken_users.__contains__ = Mock(side_effect=RuntimeError(SENSITIVE_DETAIL))
        with patch.dict(sys.modules, {"simple_storage": module("simple_storage", users=broken_users, sessions={}, save_users=Mock(), save_sessions=Mock())}):
            res = asyncio.run(main.logout(uid="u1"))
        self.assert_generic_and_silent(res, "Failed to log out.")


if __name__ == "__main__":
    unittest.main()
