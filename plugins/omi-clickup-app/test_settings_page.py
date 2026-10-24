"""Hermetic production-handler tests for the settings page; framework, storage and ClickUp are doubles."""
import asyncio
import importlib.util
import os
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


os.environ.setdefault("CLICKUP_SETTINGS_SECRET", "test-clickup-settings-secret")


class Response:
    def __init__(self, content=None, status_code=200, **kwargs):
        self.content = content
        self.status_code = status_code
        self.cookies = {}
        self.headers = {}
        self.__dict__.update(kwargs)

    def set_cookie(self, key, value="", **kwargs):
        self.cookies[key] = {"value": value, **kwargs}
        self.headers["set-cookie"] = f"{key}={value}"


def module(name, **attributes):
    value = types.ModuleType(name)
    value.__dict__.update(attributes)
    return value


stubs = {
    "dotenv": module("dotenv", load_dotenv=lambda: None),
    "fastapi": module("fastapi", FastAPI=Framework, Request=Framework, Query=Framework, HTTPException=Exception),
    "fastapi.responses": module("fastapi.responses", HTMLResponse=Response, RedirectResponse=Response, JSONResponse=Response),
    "simple_storage": module("simple_storage", SimpleUserStorage=Mock(), SimpleSessionStorage=Mock()),
    "clickup_client": module("clickup_client", ClickUpClient=Mock),
    "task_detector": module("task_detector", TaskDetector=Mock),
    "omi_notifications": module("omi_notifications", notify_task_created=Mock(), notify_task_failed=Mock()),
}
spec = importlib.util.spec_from_file_location("clickup_main_under_test", Path(__file__).with_name("main.py"))
main = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, stubs):
    spec.loader.exec_module(main)


def user_with(lists, team_name="Acme", timezone="UTC"):
    return {
        "access_token": "token",
        "team_name": team_name,
        "selected_list": "l1",
        "available_lists": lists,
        "timezone": timezone,
    }


class SettingsPageTests(unittest.TestCase):
    def render(self, lists, uid="u1", team_name="Acme", timezone="UTC"):
        with patch.object(main.SimpleUserStorage, "get_user", return_value=user_with(lists, team_name=team_name, timezone=timezone)):
            return asyncio.run(main.root(uid=uid)).content

    def test_folder_lists_are_labelled_by_folder(self):
        page = self.render([
            {"id": "l1", "name": "Inbox", "space_name": "Engineering"},
            {"id": "l2", "name": "Bugs", "space_name": "Engineering", "folder_id": "f1", "folder_name": "Sprint 1"},
        ])

        self.assertIn('<option value="l1" selected>Inbox (Engineering)</option>', page)
        self.assertIn('<option value="l2" >Sprint 1 / Bugs (Engineering)</option>', page)

    def test_list_names_are_escaped_in_the_picker(self):
        # ClickUp names are user-controlled; a list, folder or space named with
        # markup must render as text in the option, not as markup.
        page = self.render([
            {
                "id": "l2",
                "name": "<script>Bugs</script>",
                "space_name": "Eng & Co",
                "folder_id": "f1",
                "folder_name": "<b>Sprint</b>",
            },
        ])

        self.assertIn(
            '<option value="l2" >&lt;b&gt;Sprint&lt;/b&gt; / &lt;script&gt;Bugs&lt;/script&gt; (Eng &amp; Co)</option>',
            page,
        )
        self.assertNotIn("<script>Bugs</script>", page)
        self.assertNotIn("<b>Sprint</b>", page)

    def test_team_name_and_timezone_are_escaped_on_settings_page(self):
        page = self.render(
            lists=[],
            team_name='<script>alert("team")</script>',
            timezone='<b>UTC+1</b>',
        )
        self.assertIn('&lt;script&gt;alert(&quot;team&quot;)&lt;/script&gt;', page)
        self.assertNotIn('<script>alert("team")</script>', page)
        self.assertIn('&lt;b&gt;UTC+1&lt;/b&gt;', page)
        self.assertNotIn('<span><b>UTC+1</b></span>', page)

    def test_uid_serialized_safely_in_script_and_unauthenticated_page(self):
        # Unauthenticated: uid is properly URL-encoded and attribute-escaped in connect link
        with patch.object(main.SimpleUserStorage, "get_user", return_value=None):
            unauth_page = asyncio.run(main.root(uid='user"123<script>')).content
            self.assertIn('href="/auth?uid=user%22123%3Cscript%3E"', unauth_page)
            self.assertNotIn('href="/auth?uid=user"123<script>"', unauth_page)

        # Authenticated: uid is safely serialized as JSON and encoded via encodeURIComponent
        auth_page = self.render([], uid='user"123<script>')
        self.assertIn('const CURRENT_UID = "user\\"123<script>";', auth_page)
        self.assertIn('const ENCODED_UID = encodeURIComponent(CURRENT_UID);', auth_page)
        self.assertIn("fetch('/update-list?uid=' + ENCODED_UID", auth_page)
        self.assertIn("fetch('/refresh-lists?uid=' + ENCODED_UID", auth_page)
        self.assertIn("fetch('/update-timezone?uid=' + ENCODED_UID", auth_page)
        self.assertIn("fetch('/logout?uid=' + ENCODED_UID", auth_page)

    def test_authenticated_page_escapes_script_element_terminator_in_uid(self):
        malicious_uid = "user</script><script>alert('xss')</script>"
        auth_page = self.render([], uid=malicious_uid)

        self.assertIn('const CURRENT_UID = "user<\\/script><script>alert(\'xss\')<\\/script>";', auth_page)
        self.assertNotIn('const CURRENT_UID = "user</script>', auth_page)
        self.assertNotIn('</script><script>alert', auth_page)

    def test_dev_interface_uid_escaped(self):
        test_page = asyncio.run(main.test_interface(uid='user" onfocus="alert(1)', dev="true")).content
        self.assertIn('value="user&quot; onfocus=&quot;alert(1)"', test_page)
        self.assertNotIn('value="user" onfocus="alert(1)"', test_page)

    def _req(self, cookies=None, scheme="https"):
        return types.SimpleNamespace(
            cookies=cookies or {},
            url=types.SimpleNamespace(scheme=scheme),
        )

    def _authed_req(self, uid):
        return self._req({main.COOKIE_NAME: main.session_value(uid)})

    def test_mutations_fail_closed_503_when_secret_unset(self):
        with patch.dict(os.environ, {"CLICKUP_SETTINGS_SECRET": ""}):
            for call in (
                lambda: asyncio.run(main.update_list(self._req(), uid="u1", list="L2")),
                lambda: asyncio.run(main.update_timezone(self._req(), uid="u1", timezone="UTC")),
                lambda: asyncio.run(main.refresh_lists(self._req(), uid="u1")),
                lambda: asyncio.run(main.logout(self._req(), uid="u1")),
            ):
                with self.assertRaises(main.HTTPException) as ctx:
                    call()
                self.assertEqual(ctx.exception.status_code, 503)

    def test_mutations_reject_missing_mismatched_and_tampered_cookies(self):
        bad_requests = [
            self._req(),
            self._authed_req("attacker"),
            self._req({main.COOKIE_NAME: "u1.deadbeef"}),
        ]
        for req in bad_requests:
            for call in (
                lambda r=req: asyncio.run(main.update_list(r, uid="u1", list="L2")),
                lambda r=req: asyncio.run(main.update_timezone(r, uid="u1", timezone="UTC")),
                lambda r=req: asyncio.run(main.refresh_lists(r, uid="u1")),
                lambda r=req: asyncio.run(main.logout(r, uid="u1")),
            ):
                with self.assertRaises(main.HTTPException) as ctx:
                    call()
                self.assertEqual(ctx.exception.status_code, 401)

    def test_oauth_callback_blocks_cross_workspace_rebind_without_session(self):
        main.oauth_states["st-hijack"] = "u1"
        with patch.object(
            main.SimpleUserStorage,
            "get_user",
            return_value={"access_token": "cu-victim", "team_id": "T-VICTIM", "team_name": "Victim"},
        ), patch.object(main.SimpleUserStorage, "save_user") as save_mock, patch.object(
            main.clickup_client, "exchange_code_for_token", return_value={"access_token": "cu-attacker"}
        ), patch.object(
            main.clickup_client, "get_authorized_user", return_value={"id": 9}
        ), patch.object(
            main.clickup_client,
            "get_workspaces",
            return_value=[{"id": "T-ATTACKER", "name": "Attacker"}],
        ), patch.object(
            main.clickup_client, "get_all_lists", return_value=[]
        ) as lists_mock:
            response = asyncio.run(main.auth_callback(self._req(), code="code-atk", state="st-hijack"))

        self.assertEqual(response.status_code, 403)
        self.assertIn("Already Connected", response.content)
        self.assertNotIn(main.COOKIE_NAME, response.cookies)
        save_mock.assert_not_called()
        lists_mock.assert_not_called()

    def test_oauth_callback_allows_same_workspace_reconnect_and_sets_cookie(self):
        main.oauth_states["st-recover"] = "u1"
        with patch.object(
            main.SimpleUserStorage,
            "get_user",
            return_value={"access_token": "cu-victim", "team_id": "T-VICTIM", "team_name": "Victim"},
        ), patch.object(main.SimpleUserStorage, "save_user") as save_mock, patch.object(
            main.clickup_client, "exchange_code_for_token", return_value={"access_token": "cu-victim-2"}
        ), patch.object(
            main.clickup_client, "get_authorized_user", return_value={"id": 1}
        ), patch.object(
            main.clickup_client,
            "get_workspaces",
            return_value=[{"id": "T-VICTIM", "name": "Victim"}],
        ), patch.object(
            main.clickup_client, "get_all_lists", return_value=[]
        ), patch.object(
            main.clickup_client, "get_workspace_members", return_value=[]
        ):
            response = asyncio.run(main.auth_callback(self._req(), code="code-rec", state="st-recover"))

        self.assertEqual(response.status_code, 200)
        self.assertIn(main.COOKIE_NAME, response.cookies)
        self.assertTrue(response.cookies[main.COOKIE_NAME]["httponly"])
        self.assertEqual(response.cookies[main.COOKIE_NAME]["samesite"], "lax")
        self.assertTrue(response.cookies[main.COOKIE_NAME]["secure"])
        save_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
