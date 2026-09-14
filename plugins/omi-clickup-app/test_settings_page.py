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


if __name__ == "__main__":
    unittest.main()
