"""Hermetic regression tests for the ClickUp client's list discovery.

The production module imports ``dotenv`` and ``requests``; both are stubbed
so the suite runs on the standard library alone. All HTTP is faked through
``requests.get`` — no network or credentials.

Regression for #13130: ``get_all_lists`` used only the "folderless lists"
endpoint, so a workspace whose lists all live inside folders appeared to
have no selectable lists.
"""

import sys
import types
import unittest
from unittest.mock import MagicMock, patch

sys.modules.setdefault("dotenv", types.SimpleNamespace(load_dotenv=lambda *a, **k: None))
sys.modules.setdefault("requests", types.SimpleNamespace(get=None, post=None))

import clickup_client


def _response(payload, status=200):
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = payload
    return resp


def _router(fixtures):
    """Map URL suffixes to canned payloads; record every request URL."""
    calls = []

    def fake_get(url, headers=None, params=None, **kwargs):
        calls.append(url)
        for suffix, payload in fixtures.items():
            if url.endswith(suffix):
                body, status = payload if isinstance(payload, tuple) else (payload, 200)
                return _response(body, status)
        raise AssertionError(f"Unexpected URL not covered by fixtures: {url}")

    return fake_get, calls


class GetAllListsTests(unittest.TestCase):
    def setUp(self):
        self.client = clickup_client.ClickUpClient()

    def _run(self, fixtures):
        fake_get, calls = _router(fixtures)
        with patch("clickup_client.requests.get", side_effect=fake_get):
            result = self.client.get_all_lists("token", "team-1")
        return result, calls

    def test_folder_contained_lists_are_returned(self):
        fixtures = {
            "/team/team-1/space": {"spaces": [{"id": "space-1", "name": "Ops"}]},
            "/space/space-1/list": {"lists": []},
            "/space/space-1/folder": {"folders": [{"id": "fold-1", "name": "Projects"}]},
            "/folder/fold-1/list": {"lists": [{"id": "list-9", "name": "Sprint"}]},
        }
        result, calls = self._run(fixtures)

        self.assertEqual(len(result), 1)
        entry = result[0]
        self.assertEqual(entry["id"], "list-9")
        self.assertEqual(entry["space_id"], "space-1")
        self.assertEqual(entry["space_name"], "Ops")
        self.assertEqual(entry["folder_id"], "fold-1")
        self.assertEqual(entry["folder_name"], "Projects")
        self.assertEqual(entry["identity"], "Sprint (Projects)")
        self.assertTrue(any("/folder/fold-1/list" in url for url in calls))

    def test_folderless_and_foldered_lists_coexist(self):
        fixtures = {
            "/team/team-1/space": {"spaces": [{"id": "space-1", "name": "Ops"}]},
            "/space/space-1/list": {"lists": [{"id": "list-a", "name": "Inbox"}]},
            "/space/space-1/folder": {"folders": [{"id": "fold-1", "name": "Projects"}]},
            "/folder/fold-1/list": {"lists": [{"id": "list-b", "name": "Sprint"}]},
        }
        result, _ = self._run(fixtures)

        self.assertEqual({lst["id"] for lst in result}, {"list-a", "list-b"})

    def test_space_without_folders_still_lists_folderless(self):
        fixtures = {
            "/team/team-1/space": {"spaces": [{"id": "space-1", "name": "Ops"}]},
            "/space/space-1/list": {"lists": [{"id": "list-a", "name": "Inbox"}]},
            "/space/space-1/folder": {"folders": []},
        }
        result, _ = self._run(fixtures)

        self.assertEqual([lst["id"] for lst in result], ["list-a"])

    def test_failed_folder_list_request_drops_only_that_folder(self):
        fixtures = {
            "/team/team-1/space": {"spaces": [{"id": "space-1", "name": "Ops"}]},
            "/space/space-1/list": {"lists": [{"id": "list-a", "name": "Inbox"}]},
            "/space/space-1/folder": {
                "folders": [{"id": "fold-bad", "name": "Broken"}, {"id": "fold-ok", "name": "Fine"}]
            },
            "/folder/fold-bad/list": ({"err": "denied"}, 403),
            "/folder/fold-ok/list": {"lists": [{"id": "list-b", "name": "Sprint"}]},
        }
        result, _ = self._run(fixtures)

        self.assertEqual({lst["id"] for lst in result}, {"list-a", "list-b"})

    def test_duplicate_list_names_in_two_folders_keep_distinct_identities(self):
        fixtures = {
            "/team/team-1/space": {"spaces": [{"id": "space-1", "name": "Ops"}]},
            "/space/space-1/list": {"lists": []},
            "/space/space-1/folder": {
                "folders": [
                    {"id": "fold-a", "name": "Projects"},
                    {"id": "fold-b", "name": "Archive"},
                ]
            },
            "/folder/fold-a/list": {"lists": [{"id": "list-1", "name": "Sprint"}]},
            "/folder/fold-b/list": {"lists": [{"id": "list-2", "name": "Sprint"}]},
        }
        result, _ = self._run(fixtures)
        by_ident = {
            clickup_client.ClickUpClient.list_identity(lst): lst["id"] for lst in result
        }
        self.assertEqual(by_ident["Sprint (Projects)"], "list-1")
        self.assertEqual(by_ident["Sprint (Archive)"], "list-2")
        self.assertEqual(
            clickup_client.ClickUpClient.resolve_list(result, "Sprint (Projects)")["id"],
            "list-1",
        )
        self.assertIsNone(clickup_client.ClickUpClient.resolve_list(result, "Sprint"))

    def test_unique_bare_list_name_still_resolves(self):
        lists = [
            {"id": "list-a", "name": "Inbox", "space_name": "Ops"},
            {"id": "list-b", "name": "Sprint", "folder_name": "Projects", "space_name": "Ops"},
        ]
        hit = clickup_client.ClickUpClient.resolve_list(lists, "Inbox")
        self.assertEqual(hit["id"], "list-a")
        self.assertEqual(
            clickup_client.ClickUpClient.list_identity(lists[0]),
            "Inbox (Ops)",
        )

    def test_unknown_fixture_url_is_not_an_empty_200(self):
        fake_get, _ = _router({"/known": {"ok": True}})
        with self.assertRaises(AssertionError):
            fake_get("https://api.clickup.com/api/v2/space/x/unknown")


if __name__ == "__main__":
    unittest.main()
