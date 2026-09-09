"""Offline provider-contract regression for issue #13130; no real credentials."""
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch


class ListDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.http = types.ModuleType("requests")
        self.http.get = Mock(side_effect=self.get)
        dotenv = types.ModuleType("dotenv")
        dotenv.load_dotenv = lambda: None
        spec = importlib.util.spec_from_file_location("clickup_under_test", Path(__file__).with_name("clickup_client.py"))
        self.module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"requests": self.http, "dotenv": dotenv}):
            spec.loader.exec_module(self.module)
        with patch.dict("os.environ", {}, clear=True):
            self.client = self.module.ClickUpClient()
        self.routes = {
            "/team/team/space": {"spaces": [{"id": "s", "name": "Space"}]},
            "/space/s/list": {"lists": []},
            "/space/s/folder": {"folders": [{"id": "f", "name": "Folder"}]},
            "/folder/f/list": {"lists": [{"id": "nested", "name": "Nested"}]},
        }
        self.calls = []

    def get(self, url, headers, params):
        path = url.removeprefix("https://api.clickup.com/api/v2")
        self.calls.append(path)
        self.assertEqual(headers, {"Authorization": "fixture"})
        self.assertEqual(params, {"archived": "false"})
        data = self.routes[path]
        if isinstance(data, Exception):
            raise data
        return types.SimpleNamespace(status_code=503 if data is None else 200, json=lambda: data)

    def test_folder_only_workspace(self):
        self.assertEqual(self.client.get_all_lists("fixture", "team"), [
            {"id": "nested", "name": "Nested", "space_id": "s", "space_name": "Space", "folder_id": "f"}
        ])
        self.assertEqual(self.calls, ["/team/team/space", "/space/s/list", "/space/s/folder", "/folder/f/list"])

    def test_mixed_lists_multiple_spaces_and_empty_folder(self):
        self.routes["/space/s/list"] = {"lists": [{"id": "loose", "name": "Loose"}]}
        self.routes["/space/s/folder"]["folders"].append({"id": "empty"})
        self.routes["/folder/empty/list"] = {"lists": []}
        self.routes["/team/team/space"]["spaces"].append({"id": "other", "name": "Other"})
        self.routes["/space/other/list"] = {"lists": [{"id": "other-list", "name": "Other List"}]}
        self.routes["/space/other/folder"] = {"folders": []}
        result = self.client.get_all_lists("fixture", "team")
        self.assertEqual([x["id"] for x in result], ["loose", "nested", "other-list"])
        self.assertIsNone(result[0]["folder_id"])
        self.assertEqual(result[-1]["space_name"], "Other")

    def test_failed_folder_does_not_hide_other_lists(self):
        for failure in (None, RuntimeError("offline transport failure")):
            with self.subTest(failure=failure):
                self.routes["/space/s/list"] = {"lists": [{"id": "loose", "name": "Loose"}]}
                self.routes["/space/s/folder"]["folders"] = [{"id": "bad"}, {"id": "f"}]
                self.routes["/folder/bad/list"] = failure
                self.assertEqual([x["id"] for x in self.client.get_all_lists("fixture", "team")], ["loose", "nested"])

    def test_folder_enumeration_failure_preserves_folderless(self):
        self.routes["/space/s/list"] = {"lists": [{"id": "loose", "name": "Loose"}]}
        self.routes["/space/s/folder"] = None
        self.assertEqual([x["id"] for x in self.client.get_all_lists("fixture", "team")], ["loose"])

    def test_empty_workspace(self):
        self.routes["/team/team/space"] = {"spaces": []}
        self.assertEqual(self.client.get_all_lists("fixture", "team"), [])
        self.assertEqual(self.calls, ["/team/team/space"])


if __name__ == "__main__":
    unittest.main()
