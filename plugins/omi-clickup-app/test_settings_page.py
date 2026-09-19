"""Hermetic production-handler tests for the settings page; framework, storage and ClickUp are doubles."""
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


def user_with(lists):
    return {"access_token": "token", "team_name": "Acme", "selected_list": "l1", "available_lists": lists}


class SettingsPageTests(unittest.TestCase):
    def render(self, lists):
        with patch.object(main.SimpleUserStorage, "get_user", return_value=user_with(lists)):
            return asyncio.run(main.root(uid="u1")).content

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


class ReflectedValueEscapingTests(unittest.TestCase):
    """#14888: workspace name / timezone / uid are reflected into HTML and JS."""

    PAYLOAD = "<script>alert(1)</script>"

    def render_settings(self, uid="u1", team_name="Acme", timezone="UTC"):
        user = {
            "access_token": "token",
            "team_name": team_name,
            "timezone": timezone,
            "selected_list": "",
            "available_lists": [],
        }
        with patch.object(main.SimpleUserStorage, "get_user", return_value=user):
            return asyncio.run(main.root(uid=uid)).content

    def test_workspace_name_is_escaped_in_the_settings_page(self):
        page = self.render_settings(team_name=f"{self.PAYLOAD} & Co")

        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt; &amp; Co", page)
        self.assertNotIn(self.PAYLOAD, page)

    def test_timezone_is_escaped_in_the_settings_page(self):
        page = self.render_settings(timezone='"><img src=x onerror=alert(1)>')

        self.assertIn("&quot;&gt;&lt;img src=x onerror=alert(1)&gt;", page)
        self.assertNotIn('"><img src=x', page)

    def test_uid_is_safely_serialized_for_the_inline_script_block(self):
        uid = 'u1"><script>alert(1)</script>'
        page = self.render_settings(uid=uid)

        # json.dumps plus \u00XX escaping: the payload cannot close the tag.
        self.assertIn(
            'const CURRENT_UID = "u1\\"\\u003e\\u003cscript\\u003ealert(1)\\u003c/script\\u003e";',
            page,
        )
        self.assertIn("const ENCODED_UID = encodeURIComponent(CURRENT_UID);", page)
        self.assertNotIn('u1"><script>', page)
        self.assertNotIn("uid={uid}", page)

    def test_unauthenticated_auth_link_percent_encodes_the_uid(self):
        with patch.object(main.SimpleUserStorage, "get_user", return_value=None):
            page = asyncio.run(main.root(uid="u'\"<x")).content

        self.assertIn('href="/auth?uid=u%27%22%3Cx"', page)
        self.assertNotIn("href=\"/auth?uid=u'\"", page)

    def test_callback_escapes_workspace_name_and_encodes_uid(self):
        uid = 'u1"><script>alert(1)</script>'
        main.oauth_states["state-14888"] = uid
        main.clickup_client.exchange_code_for_token.return_value = {"access_token": "t"}
        main.clickup_client.get_authorized_user.return_value = {}
        main.clickup_client.get_workspaces.return_value = [{"id": "1", "name": f"{self.PAYLOAD}&Co"}]
        main.clickup_client.get_all_lists.return_value = []
        main.clickup_client.get_workspace_members.return_value = []
        try:
            page = asyncio.run(main.auth_callback(request=None, code="c", state="state-14888")).content
        finally:
            main.oauth_states.pop("state-14888", None)

        self.assertIn(
            "Your ClickUp workspace <strong>&lt;script&gt;alert(1)&lt;/script&gt;&amp;Co</strong>",
            page,
        )
        self.assertNotIn(self.PAYLOAD, page)
        self.assertIn('href="/?uid=u1%22%3E%3Cscript%3Ealert%281%29%3C%2Fscript%3E"', page)

    def test_test_interface_escapes_the_uid_attribute(self):
        page = asyncio.run(
            main.test_interface(uid='" onfocus=alert(1) autofocus x="', dev="true")
        ).content

        self.assertIn('value="&quot; onfocus=alert(1) autofocus x=&quot;"', page)
        self.assertNotIn('value="" onfocus=alert(1)', page)
        self.assertIn("encodeURIComponent(uid)", page)


if __name__ == "__main__":
    unittest.main()
