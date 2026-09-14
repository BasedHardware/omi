from pathlib import Path
import importlib.util
import sys
import types
import unittest
from unittest.mock import patch

# clickup_client.py imports requests and dotenv at load time. The suite never
# performs real I/O (requests.get is patched per test), so stub both modules
# during the import — the same pattern as the sibling plugin suites — and this
# file runs on a stdlib-only interpreter. The stubs stay bound inside the
# loaded module, so patching clickup_client.requests still intercepts.
_requests = types.ModuleType("requests")
_requests.get = _requests.post = None
_dotenv = types.ModuleType("dotenv")
_dotenv.load_dotenv = lambda *args, **kwargs: None

MODULE_PATH = Path(__file__).with_name("clickup_client.py")
spec = importlib.util.spec_from_file_location("clickup_client", MODULE_PATH)
clickup_client = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, {"requests": _requests, "dotenv": _dotenv}):
    spec.loader.exec_module(clickup_client)

API = "https://api.clickup.com/api/v2"


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = str(payload)

    def json(self):
        return self._payload


def route(responses):
    """Answer requests.get by URL; get_all_lists makes a variable number of calls."""
    def get(url, headers=None, params=None):
        return responses[url]
    return get


# The shapes below are ClickUp API v2's: /space/{id}/list embeds a `folder`
# object on each list, and /space/{id}/folder embeds each folder's `lists`.
SPACES = {"spaces": [{"id": "s1", "name": "Engineering", "private": False, "color": None}]}
FOLDERLESS = {"lists": [{"id": "l1", "name": "Inbox", "folder": {"id": None, "name": "hidden", "hidden": True}}]}
FOLDER_WITH_LISTS = {"folders": [{"id": "f1", "name": "Sprint 1", "lists": [{"id": "l2", "name": "Bugs"}]}]}
FOLDER_WITHOUT_LISTS = {"folders": [{"id": "f1", "name": "Sprint 1"}]}


class ClickUpClientTests(unittest.TestCase):
    def test_get_all_lists_includes_lists_inside_folders(self):
        client = clickup_client.ClickUpClient()
        responses = {
            f"{API}/team/t1/space": FakeResponse(SPACES),
            f"{API}/space/s1/list": FakeResponse(FOLDERLESS),
            f"{API}/space/s1/folder": FakeResponse(FOLDER_WITH_LISTS),
        }

        with patch.object(clickup_client.requests, "get", side_effect=route(responses)) as get:
            lists = client.get_all_lists("token", "t1")

        self.assertEqual(
            [(lst["id"], lst["name"], lst.get("folder_name")) for lst in lists],
            [("l1", "Inbox", None), ("l2", "Bugs", "Sprint 1")],
        )
        # `name` stays the bare list name: task_detector matches what the user
        # said against it, and nobody says "Sprint 1 / Bugs" out loud.
        self.assertEqual(
            lists[1],
            {
                "id": "l2",
                "name": "Bugs",
                "space_id": "s1",
                "space_name": "Engineering",
                "folder_id": "f1",
                "folder_name": "Sprint 1",
            },
        )
        requested = [call.args[0] for call in get.call_args_list]
        self.assertIn(f"{API}/space/s1/folder", requested)
        self.assertNotIn(f"{API}/folder/f1/list", requested, "embedded folder lists must not be re-fetched")
        folder_call = get.call_args_list[requested.index(f"{API}/space/s1/folder")]
        self.assertEqual(folder_call.kwargs["params"], {"archived": "false"})
        self.assertEqual(folder_call.kwargs["headers"], {"Authorization": "token"})

    def test_get_all_lists_fetches_folder_lists_when_not_embedded(self):
        client = clickup_client.ClickUpClient()
        responses = {
            f"{API}/team/t1/space": FakeResponse(SPACES),
            f"{API}/space/s1/list": FakeResponse(FOLDERLESS),
            f"{API}/space/s1/folder": FakeResponse(FOLDER_WITHOUT_LISTS),
            f"{API}/folder/f1/list": FakeResponse({"lists": [{"id": "l2", "name": "Bugs"}]}),
        }

        with patch.object(clickup_client.requests, "get", side_effect=route(responses)) as get:
            lists = client.get_all_lists("token", "t1")

        self.assertEqual(
            [(lst["id"], lst["name"], lst.get("folder_name")) for lst in lists],
            [("l1", "Inbox", None), ("l2", "Bugs", "Sprint 1")],
        )
        self.assertEqual(lists[1]["folder_id"], "f1")
        self.assertIn(f"{API}/folder/f1/list", [call.args[0] for call in get.call_args_list])

    def test_get_all_lists_discards_partial_results_when_folder_request_fails(self):
        # A folderless-only answer after a failed folder request would look
        # like a workspace with no folders — the exact bug, now intermittent.
        client = clickup_client.ClickUpClient()
        responses = {
            f"{API}/team/t1/space": FakeResponse(SPACES),
            f"{API}/space/s1/list": FakeResponse(FOLDERLESS),
            f"{API}/space/s1/folder": FakeResponse({"err": "boom"}, status_code=500),
        }

        with patch.object(clickup_client.requests, "get", side_effect=route(responses)), patch.object(
            clickup_client, "print"
        ) as log:
            self.assertEqual(client.get_all_lists("token", "t1"), [])

        self.assertIn("500", log.call_args.args[0])

    def test_get_all_lists_discards_partial_results_when_folder_lists_request_fails(self):
        client = clickup_client.ClickUpClient()
        responses = {
            f"{API}/team/t1/space": FakeResponse(SPACES),
            f"{API}/space/s1/list": FakeResponse(FOLDERLESS),
            f"{API}/space/s1/folder": FakeResponse(FOLDER_WITHOUT_LISTS),
            f"{API}/folder/f1/list": FakeResponse({"err": "boom"}, status_code=500),
        }

        with patch.object(clickup_client.requests, "get", side_effect=route(responses)), patch.object(
            clickup_client, "print"
        ):
            self.assertEqual(client.get_all_lists("token", "t1"), [])

    def test_get_all_lists_keeps_folderless_lists_when_space_has_no_folders(self):
        client = clickup_client.ClickUpClient()
        responses = {
            f"{API}/team/t1/space": FakeResponse(SPACES),
            f"{API}/space/s1/list": FakeResponse(FOLDERLESS),
            f"{API}/space/s1/folder": FakeResponse({"folders": []}),
        }

        with patch.object(clickup_client.requests, "get", side_effect=route(responses)):
            lists = client.get_all_lists("token", "t1")

        self.assertEqual([(lst["id"], lst["space_name"]) for lst in lists], [("l1", "Engineering")])


if __name__ == "__main__":
    unittest.main()
