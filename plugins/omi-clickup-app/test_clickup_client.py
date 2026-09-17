from pathlib import Path
import importlib.util
import sys
import types
import unittest
import asyncio
from unittest.mock import patch, MagicMock

# Stub dependencies for standard library hermetic testing
_requests = types.ModuleType("requests")
_requests.get = _requests.post = None
_dotenv = types.ModuleType("dotenv")
_dotenv.load_dotenv = lambda *args, **kwargs: None
_openai = types.ModuleType("openai")
_openai.AsyncOpenAI = MagicMock

MODULE_DIR = Path(__file__).parent
spec_client = importlib.util.spec_from_file_location("clickup_client", MODULE_DIR / "clickup_client.py")
clickup_client = importlib.util.module_from_spec(spec_client)

spec_storage = importlib.util.spec_from_file_location("simple_storage", MODULE_DIR / "simple_storage.py")
simple_storage = importlib.util.module_from_spec(spec_storage)

spec_detector = importlib.util.spec_from_file_location("task_detector", MODULE_DIR / "task_detector.py")
task_detector = importlib.util.module_from_spec(spec_detector)

with patch.dict(sys.modules, {"requests": _requests, "dotenv": _dotenv, "openai": _openai}):
    with patch("builtins.print"):
        spec_client.loader.exec_module(clickup_client)
        spec_storage.loader.exec_module(simple_storage)
        spec_detector.loader.exec_module(task_detector)

API = "https://api.clickup.com/api/v2"


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = str(payload)

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


def route(responses):
    """Answer requests.get by URL."""
    def get(url, headers=None, params=None):
        return responses[url]
    return get


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
        self.assertNotIn(f"{API}/folder/f1/list", requested)
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

    def test_safe_json_guards_against_html_errors_and_non_dicts(self):
        client = clickup_client.ClickUpClient()
        # Invalid JSON / HTML
        resp_html = FakeResponse(ValueError("Expecting value: line 1 column 1 (char 0)"))
        self.assertEqual(client._safe_json(resp_html), {})
        self.assertEqual(client._safe_json(None), {})

        # Non-dict list JSON
        resp_list = FakeResponse([1, 2, 3])
        self.assertEqual(client._safe_json(resp_list), {"data": [1, 2, 3]})

    def test_get_authorized_user_handles_malformed_and_gateway_errors(self):
        client = clickup_client.ClickUpClient()
        with patch.object(clickup_client.requests, "get", return_value=FakeResponse("Bad Gateway", status_code=502)):
            self.assertEqual(client.get_authorized_user("tok"), {})

        # User is None or non-dict
        with patch.object(clickup_client.requests, "get", return_value=FakeResponse({"user": None}, status_code=200)):
            self.assertEqual(client.get_authorized_user("tok"), {"id": None, "username": None, "email": None})

    def test_get_workspaces_guards_none_and_malformed_teams(self):
        client = clickup_client.ClickUpClient()
        # Malformed teams list
        with patch.object(clickup_client.requests, "get", return_value=FakeResponse({"teams": None}, status_code=200)):
            self.assertEqual(client.get_workspaces("tok"), [])

        # Non-dict elements inside teams
        with patch.object(clickup_client.requests, "get", return_value=FakeResponse({"teams": ["bad", {"id": "1", "name": "Team"}]}, status_code=200)):
            res = client.get_workspaces("tok")
            self.assertEqual(len(res), 1)
            self.assertEqual(res[0]["id"], "1")

    def test_get_spaces_and_lists_guards_none_collections(self):
        client = clickup_client.ClickUpClient()
        with patch.object(clickup_client.requests, "get", return_value=FakeResponse({"spaces": None}, status_code=200)):
            self.assertEqual(client.get_spaces("tok", "t1"), [])

        with patch.object(clickup_client.requests, "get", return_value=FakeResponse({"lists": None}, status_code=200)):
            self.assertEqual(client.get_lists("tok", "s1"), [])

    def test_get_workspace_members_guards_none_and_malformed_users(self):
        client = clickup_client.ClickUpClient()
        with patch.object(clickup_client.requests, "get", return_value=FakeResponse({"team": {"members": [None, {"user": None}, {"user": {"id": 12, "username": "Alice"}}]}}, status_code=200)):
            members = client.get_workspace_members("tok", "t1")
            self.assertEqual(len(members), 1)
            self.assertEqual(members[0]["username"], "Alice")

    def test_create_task_assignee_coercion(self):
        client = clickup_client.ClickUpClient()
        captured_data = {}

        def mock_post(url, headers=None, json=None):
            nonlocal captured_data
            captured_data = json
            return FakeResponse({"id": "t123", "name": json.get("name"), "status": {"status": "open"}})

        with patch.object(clickup_client.requests, "post", side_effect=mock_post):
            # Mix of numeric strings, ints, invalid strings, None
            res = asyncio.run(client.create_task(
                access_token="tok",
                list_id="l1",
                name="Fix issue",
                assignees=["1001", 1002, "invalid_me", None, ""]
            ))

        self.assertTrue(res["success"])
        self.assertEqual(captured_data.get("assignees"), [1001, 1002])

    def test_create_task_due_date_and_status_variants(self):
        client = clickup_client.ClickUpClient()
        captured_data = {}

        def mock_post(url, headers=None, json=None):
            nonlocal captured_data
            captured_data = json
            return FakeResponse({"id": "t123", "name": json.get("name"), "status": "in progress"})

        with patch.object(clickup_client.requests, "post", side_effect=mock_post):
            # Test timestamp int
            res = asyncio.run(client.create_task(
                access_token="tok",
                list_id="l1",
                name="Check server",
                due_date=1729000000000,
                status="in progress"
            ))

        self.assertTrue(res["success"])
        self.assertEqual(res["status"], "in progress")
        self.assertEqual(captured_data.get("due_date"), 1729000000000)
        self.assertTrue(captured_data.get("due_date_time"))

        # Test ISO date string without time
        with patch.object(clickup_client.requests, "post", side_effect=mock_post):
            asyncio.run(client.create_task(
                access_token="tok",
                list_id="l1",
                name="Check report",
                due_date="2026-10-15"
            ))
        self.assertFalse(captured_data.get("due_date_time"))


class StorageLifecycleTests(unittest.TestCase):
    def setUp(self):
        simple_storage.sessions.clear()

    def test_session_lifecycle_and_eviction(self):
        # Create session
        sess = simple_storage.SimpleSessionStorage.get_or_create_session("sess_1", "u1")
        self.assertIn("sess_1", simple_storage.sessions)
        self.assertEqual(sess["task_mode"], "idle")

        # Update session
        simple_storage.SimpleSessionStorage.update_session("sess_1", task_mode="recording", accumulated_text="hello")
        self.assertEqual(simple_storage.sessions["sess_1"]["task_mode"], "recording")

        # Explicit delete
        self.assertTrue(simple_storage.SimpleSessionStorage.delete_session("sess_1"))
        self.assertNotIn("sess_1", simple_storage.sessions)

    def test_cleanup_old_sessions(self):
        from datetime import datetime, timezone, timedelta
        now = datetime.now(timezone.utc)

        # Fresh session
        simple_storage.sessions["fresh"] = {
            "session_id": "fresh",
            "last_segment_at": now.isoformat(),
            "task_mode": "idle"
        }
        # Old session (> 1h)
        old_time = (now - timedelta(seconds=4000)).isoformat()
        simple_storage.sessions["expired"] = {
            "session_id": "expired",
            "last_segment_at": old_time,
            "task_mode": "idle"
        }

        evicted = simple_storage.SimpleSessionStorage.cleanup_old_sessions(max_age_seconds=3600)
        self.assertEqual(evicted, 1)
        self.assertIn("fresh", simple_storage.sessions)
        self.assertNotIn("expired", simple_storage.sessions)


class TaskDetectorTests(unittest.TestCase):
    def test_trigger_detection_and_content_extraction(self):
        detector = task_detector.TaskDetector
        text = "hey please create clickup task fix the payment gateway by 5pm"
        self.assertTrue(detector.detect_trigger(text))
        extracted = detector.extract_task_content(text)
        self.assertEqual(extracted, "fix the payment gateway by 5pm")

        no_trigger = "just speaking casually about tasks"
        self.assertFalse(detector.detect_trigger(no_trigger))
        self.assertIsNone(detector.extract_task_content(no_trigger))

    def test_ai_match_list_fallback_when_openai_none(self):
        detector = task_detector.TaskDetector
        available = [{"id": "1", "name": "Sprint Tasks"}, {"id": "2", "name": "Bugs"}]
        with patch.object(task_detector, "get_openai_client", return_value=None):
            matched = asyncio.run(detector.ai_match_list("bugs", available))
            self.assertEqual(matched["id"], "2")
            none_match = asyncio.run(detector.ai_match_list("unknown_list", available))
            self.assertIsNone(none_match)


if __name__ == "__main__":
    unittest.main()
