from pathlib import Path
import asyncio
from datetime import datetime, timezone, timedelta
import importlib.util
import sys
import types
import unittest
from unittest.mock import patch, MagicMock

# clickup_client.py imports requests and dotenv at load time. The suite never
# performs real I/O (requests.get is patched per test), so stub both modules
# during the import — the same pattern as the sibling plugin suites — and this
# file runs on a stdlib-only interpreter. The stubs stay bound inside the
# loaded module, so patching clickup_client.requests still intercepts.
_requests = types.ModuleType("requests")
_requests.get = _requests.post = None
_requests.Response = object
_requests.RequestException = Exception
_dotenv = types.ModuleType("dotenv")
_dotenv.load_dotenv = lambda *args, **kwargs: None

MODULE_PATH = Path(__file__).with_name("clickup_client.py")
spec = importlib.util.spec_from_file_location("clickup_client", MODULE_PATH)
clickup_client = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, {"requests": _requests, "dotenv": _dotenv}):
    spec.loader.exec_module(clickup_client)

# Import simple_storage
storage_path = Path(__file__).with_name("simple_storage.py")
storage_spec = importlib.util.spec_from_file_location("simple_storage", storage_path)
simple_storage = importlib.util.module_from_spec(storage_spec)
storage_spec.loader.exec_module(simple_storage)

# Import task_detector
detector_path = Path(__file__).with_name("task_detector.py")
detector_spec = importlib.util.spec_from_file_location("task_detector", detector_path)
task_detector_mod = importlib.util.module_from_spec(detector_spec)
with patch.dict(sys.modules, {"dotenv": _dotenv}):
    detector_spec.loader.exec_module(task_detector_mod)

# Import main (with fastapi stubs)
class _Framework:
    def __init__(self, *args, **kwargs): pass
    def get(self, *args, **kwargs): return lambda fn: fn
    post = on_event = get

_fastapi = types.ModuleType("fastapi")
_fastapi.FastAPI = _Framework
_fastapi.Request = _Framework
_fastapi.Query = _Framework
_fastapi.HTTPException = Exception
_fastapi_resp = types.ModuleType("fastapi.responses")
_fastapi_resp.HTMLResponse = _fastapi_resp.RedirectResponse = _fastapi_resp.JSONResponse = lambda *a, **kw: None

_omi_notif = types.ModuleType("omi_notifications")
_omi_notif.notify_task_created = _omi_notif.notify_task_failed = lambda *a, **kw: None

main_path = Path(__file__).with_name("main.py")
main_spec = importlib.util.spec_from_file_location("main", main_path)
main_mod = importlib.util.module_from_spec(main_spec)
with patch.dict(sys.modules, {
    "requests": _requests,
    "dotenv": _dotenv,
    "fastapi": _fastapi,
    "fastapi.responses": _fastapi_resp,
    "omi_notifications": _omi_notif,
}):
    main_spec.loader.exec_module(main_mod)

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


class SafeJsonTests(unittest.TestCase):
    def test_safe_json_returns_dict_on_valid_payload(self):
        resp = FakeResponse({"key": "value"})
        self.assertEqual(clickup_client._safe_json(resp), {"key": "value"})

    def test_safe_json_returns_empty_dict_on_non_dict_payload(self):
        resp_list = FakeResponse([1, 2, 3])
        self.assertEqual(clickup_client._safe_json(resp_list), {"data": [1, 2, 3]})
        resp_str = FakeResponse("just a string")
        self.assertEqual(clickup_client._safe_json(resp_str), {})

    def test_safe_json_returns_empty_dict_on_json_decode_error(self):
        resp_err = FakeResponse(ValueError("Bad JSON"))
        self.assertEqual(clickup_client._safe_json(resp_err), {})


class ClickUpClientEndpointTests(unittest.TestCase):
    def setUp(self):
        self.client = clickup_client.ClickUpClient()

    def test_get_spaces_handles_empty_none_and_non_dict_elements(self):
        with patch.object(clickup_client.requests, "get", return_value=FakeResponse({"spaces": None})):
            self.assertEqual(self.client.get_spaces("token", "t1"), [])

        payload = {"spaces": [{"id": "s1", "name": "Dev"}, "not-a-dict", None]}
        with patch.object(clickup_client.requests, "get", return_value=FakeResponse(payload)):
            spaces = self.client.get_spaces("token", "t1")
            self.assertEqual(len(spaces), 1)
            self.assertEqual(spaces[0]["id"], "s1")

    def test_get_spaces_returns_empty_on_error_status(self):
        with patch.object(clickup_client.requests, "get", return_value=FakeResponse({}, status_code=500)):
            self.assertEqual(self.client.get_spaces("token", "t1"), [])

    def test_get_lists_handles_none_and_non_dict_elements(self):
        with patch.object(clickup_client.requests, "get", return_value=FakeResponse({"lists": None})):
            self.assertEqual(self.client.get_lists("token", "s1"), [])

        payload = {"lists": [{"id": "l1", "name": "Backlog"}, 12345]}
        with patch.object(clickup_client.requests, "get", return_value=FakeResponse(payload)):
            lists = self.client.get_lists("token", "s1")
            self.assertEqual(len(lists), 1)
            self.assertEqual(lists[0]["name"], "Backlog")

    def test_get_lists_returns_empty_on_error_status(self):
        with patch.object(clickup_client.requests, "get", return_value=FakeResponse({}, status_code=404)):
            self.assertEqual(self.client.get_lists("token", "s1"), [])

    def test_get_folders_handles_none_and_non_dict_elements(self):
        with patch.object(clickup_client.requests, "get", return_value=FakeResponse({"folders": None})):
            self.assertEqual(self.client.get_folders("token", "s1"), [])

        payload = {"folders": [{"id": "f1", "name": "Sprint 1"}, "ignore_me"]}
        with patch.object(clickup_client.requests, "get", return_value=FakeResponse(payload)):
            folders = self.client.get_folders("token", "s1")
            self.assertEqual(len(folders), 1)
            self.assertEqual(folders[0]["id"], "f1")

    def test_get_folders_raises_on_error_status(self):
        with patch.object(clickup_client.requests, "get", return_value=FakeResponse({}, status_code=503)):
            with self.assertRaises(Exception):
                self.client.get_folders("token", "s1")

    def test_get_folder_lists_raises_on_error_status(self):
        with patch.object(clickup_client.requests, "get", return_value=FakeResponse({}, status_code=500)):
            with self.assertRaises(Exception):
                self.client.get_folder_lists("token", "f1")

    def test_get_workspace_members_safely_extracts_members(self):
        payload = {
            "team": {
                "members": [
                    {"user": {"id": 101, "username": "alice", "email": "alice@example.com"}},
                    {"user": None},
                    "not_a_dict_member",
                    {"user": {"id": 102, "username": "bob"}}
                ]
            }
        }
        with patch.object(clickup_client.requests, "get", return_value=FakeResponse(payload)):
            members = self.client.get_workspace_members("token", "t1")
            self.assertEqual(len(members), 2)
            self.assertEqual(members[0]["id"], 101)
            self.assertEqual(members[0]["username"], "alice")
            self.assertEqual(members[1]["id"], 102)

    def test_get_workspace_members_returns_empty_on_error_status(self):
        with patch.object(clickup_client.requests, "get", return_value=FakeResponse({}, status_code=403)):
            self.assertEqual(self.client.get_workspace_members("token", "t1"), [])

    def test_exchange_code_for_token_success_and_failure(self):
        with patch.object(clickup_client.requests, "post", return_value=FakeResponse({"access_token": "tok123"})):
            res = self.client.exchange_code_for_token("code1")
            self.assertEqual(res.get("access_token"), "tok123")

        with patch.object(clickup_client.requests, "post", return_value=FakeResponse({}, status_code=400)):
            with self.assertRaises(Exception):
                self.client.exchange_code_for_token("bad_code")

    def test_get_authorized_user_success_and_failure(self):
        with patch.object(clickup_client.requests, "get", return_value=FakeResponse({"user": {"id": 1, "username": "user1"}})):
            user = self.client.get_authorized_user("token")
            self.assertEqual(user.get("username"), "user1")

        with patch.object(clickup_client.requests, "get", return_value=FakeResponse({}, status_code=401)):
            user = self.client.get_authorized_user("bad_token")
            self.assertEqual(user, {})

    def test_get_workspaces_success_and_failure(self):
        with patch.object(clickup_client.requests, "get", return_value=FakeResponse({"teams": [{"id": "t1", "name": "Team 1"}]})):
            teams = self.client.get_workspaces("token")
            self.assertEqual(len(teams), 1)
            self.assertEqual(teams[0]["id"], "t1")

        with patch.object(clickup_client.requests, "get", return_value=FakeResponse({}, status_code=500)):
            self.assertEqual(self.client.get_workspaces("token"), [])


class CreateTaskTests(unittest.TestCase):
    def setUp(self):
        self.client = clickup_client.ClickUpClient()

    def test_create_task_coerces_numeric_string_assignees_to_integers(self):
        captured_data = {}

        def fake_post(url, headers=None, json=None):
            captured_data.update(json)
            return FakeResponse({
                "id": "task_1",
                "name": json.get("name"),
                "url": "https://app.clickup.com/t/task_1",
                "status": {"status": "to do"}
            })

        with patch.object(clickup_client.requests, "post", side_effect=fake_post):
            result = asyncio.run(self.client.create_task(
                access_token="tok",
                list_id="l1",
                name="New Task",
                assignees=["100", "200"]
            ))

        self.assertTrue(result.get("success"))
        self.assertEqual(captured_data.get("assignees"), [100, 200])

    def test_create_task_ignores_non_numeric_assignees_without_raising(self):
        captured_data = {}

        def fake_post(url, headers=None, json=None):
            captured_data.update(json)
            return FakeResponse({
                "id": "task_2",
                "name": json.get("name"),
                "url": "https://app.clickup.com/t/task_2",
                "status": "open"
            })

        with patch.object(clickup_client.requests, "post", side_effect=fake_post):
            result = asyncio.run(self.client.create_task(
                access_token="tok",
                list_id="l1",
                name="Safe Assignee Task",
                assignees=["admin", "me", "300", None]
            ))

        self.assertTrue(result.get("success"))
        self.assertEqual(captured_data.get("assignees"), [300])

    def test_create_task_accepts_integer_and_numeric_string_due_dates(self):
        captured_data = {}

        def fake_post(url, headers=None, json=None):
            captured_data.update(json)
            return FakeResponse({
                "id": "task_3",
                "name": json.get("name"),
                "status": "to do"
            })

        with patch.object(clickup_client.requests, "post", side_effect=fake_post):
            result = asyncio.run(self.client.create_task(
                access_token="tok",
                list_id="l1",
                name="Due Date Millis",
                due_date=1730000000000
            ))

        self.assertTrue(result.get("success"))
        self.assertEqual(captured_data.get("due_date"), 1730000000000)

    def test_create_task_parses_iso_due_dates(self):
        captured_data = {}

        def fake_post(url, headers=None, json=None):
            captured_data.update(json)
            return FakeResponse({
                "id": "task_4",
                "name": json.get("name"),
                "status": "to do"
            })

        with patch.object(clickup_client.requests, "post", side_effect=fake_post):
            # ISO with time
            asyncio.run(self.client.create_task(
                access_token="tok",
                list_id="l1",
                name="Due Date ISO Time",
                due_date="2025-10-31T18:00:00"
            ))
            self.assertTrue(captured_data.get("due_date_time"))
            self.assertIsInstance(captured_data.get("due_date"), int)

            # ISO date-only
            asyncio.run(self.client.create_task(
                access_token="tok",
                list_id="l1",
                name="Due Date ISO Date Only",
                due_date="2025-10-31"
            ))
            self.assertFalse(captured_data.get("due_date_time"))

    def test_create_task_extracts_status_as_dict_or_string(self):
        # Case 1: Status is dict
        with patch.object(clickup_client.requests, "post", return_value=FakeResponse({
            "id": "t1", "name": "T1", "status": {"status": "in progress"}
        })):
            res1 = asyncio.run(self.client.create_task("tok", "l1", "T1"))
            self.assertEqual(res1.get("status"), "in progress")

        # Case 2: Status is string
        with patch.object(clickup_client.requests, "post", return_value=FakeResponse({
            "id": "t2", "name": "T2", "status": "completed"
        })):
            res2 = asyncio.run(self.client.create_task("tok", "l1", "T2"))
            self.assertEqual(res2.get("status"), "completed")

        # Case 3: Status is None
        with patch.object(clickup_client.requests, "post", return_value=FakeResponse({
            "id": "t3", "name": "T3", "status": None
        })):
            res3 = asyncio.run(self.client.create_task("tok", "l1", "T3"))
            self.assertIsNone(res3.get("status"))

    def test_create_task_handles_http_failure_cleanly(self):
        with patch.object(clickup_client.requests, "post", return_value=FakeResponse({"err": "Quota exceeded"}, status_code=429)):
            res = asyncio.run(self.client.create_task("tok", "l1", "Rate Limited Task"))
            self.assertFalse(res.get("success"))
            self.assertIn("error", res)


class SimpleSessionStorageTests(unittest.TestCase):
    def setUp(self):
        simple_storage.sessions.clear()

    def test_get_or_create_session_initializes_expected_keys(self):
        sess = simple_storage.SimpleSessionStorage.get_or_create_session("s_100", "user_1")
        self.assertEqual(sess["session_id"], "s_100")
        self.assertEqual(sess["uid"], "user_1")
        self.assertEqual(sess["task_mode"], "idle")
        self.assertEqual(sess["segments_count"], 0)
        self.assertEqual(sess["accumulated_text"], "")
        self.assertIn("created_at", sess)

    def test_update_session_updates_fields_and_timestamp(self):
        simple_storage.SimpleSessionStorage.get_or_create_session("s_101", "user_1")
        simple_storage.SimpleSessionStorage.update_session("s_101", task_mode="recording", segments_count=3)
        sess = simple_storage.sessions["s_101"]
        self.assertEqual(sess["task_mode"], "recording")
        self.assertEqual(sess["segments_count"], 3)
        self.assertIn("last_segment_at", sess)

    def test_get_session_idle_time_handles_valid_and_invalid_timestamps(self):
        simple_storage.SimpleSessionStorage.get_or_create_session("s_102", "user_1")
        # No last_segment_at initially
        self.assertIsNone(simple_storage.SimpleSessionStorage.get_session_idle_time("s_102"))

        # Set timestamp 10 seconds in the past
        ten_sec_ago = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
        simple_storage.sessions["s_102"]["last_segment_at"] = ten_sec_ago
        idle = simple_storage.SimpleSessionStorage.get_session_idle_time("s_102")
        self.assertIsNotNone(idle)
        self.assertGreaterEqual(idle, 9.0)

        # Malformed timestamp
        simple_storage.sessions["s_102"]["last_segment_at"] = "not-a-timestamp"
        self.assertIsNone(simple_storage.SimpleSessionStorage.get_session_idle_time("s_102"))

    def test_delete_session_removes_session_cleanly(self):
        simple_storage.SimpleSessionStorage.get_or_create_session("s_103", "user_1")
        self.assertIn("s_103", simple_storage.sessions)
        self.assertTrue(simple_storage.SimpleSessionStorage.delete_session("s_103"))
        self.assertNotIn("s_103", simple_storage.sessions)
        self.assertFalse(simple_storage.SimpleSessionStorage.delete_session("s_103"))

    def test_cleanup_old_sessions_evicts_stale_and_preserves_active(self):
        now = datetime.now(timezone.utc)
        # Fresh session: 5 seconds old
        fresh_time = (now - timedelta(seconds=5)).isoformat()
        simple_storage.sessions["fresh_sess"] = {
            "session_id": "fresh_sess", "last_segment_at": fresh_time
        }
        # Stale session: 4000 seconds old
        stale_time = (now - timedelta(seconds=4000)).isoformat()
        simple_storage.sessions["stale_sess"] = {
            "session_id": "stale_sess", "last_segment_at": stale_time
        }
        # Session without timestamp
        simple_storage.sessions["empty_sess"] = {
            "session_id": "empty_sess"
        }

        evicted = simple_storage.SimpleSessionStorage.cleanup_old_sessions(max_age_seconds=3600)
        self.assertEqual(evicted, 2)
        self.assertIn("fresh_sess", simple_storage.sessions)
        self.assertNotIn("stale_sess", simple_storage.sessions)
        self.assertNotIn("empty_sess", simple_storage.sessions)


class TaskDetectorTests(unittest.TestCase):
    def test_detect_trigger_identifies_all_known_phrases(self):
        detector = task_detector_mod.TaskDetector
        self.assertTrue(detector.detect_trigger("Please create clickup task write unit tests"))
        self.assertTrue(detector.detect_trigger("Hey add Click Up task fix login"))
        self.assertTrue(detector.detect_trigger("Create Click up Task review PR"))
        self.assertTrue(detector.detect_trigger("Add clickup task ship release"))
        self.assertFalse(detector.detect_trigger("Hello world this is not a task trigger"))

    def test_extract_task_content_extracts_text_after_trigger(self):
        detector = task_detector_mod.TaskDetector
        content = detector.extract_task_content("create clickup task fix bug in authentication")
        self.assertEqual(content, "fix bug in authentication")

        no_content = detector.extract_task_content("some random text")
        self.assertIsNone(no_content)

    def test_clean_content_strips_filler_words(self):
        detector = task_detector_mod.TaskDetector
        cleaned = detector.clean_content("um like please fix the server uh yeah")
        self.assertEqual(cleaned, "Please fix the server")

    def test_ai_extract_task_details_graceful_fallback_without_client(self):
        detector = task_detector_mod.TaskDetector
        # Malformed available_lists containing non-dict and missing keys
        malformed_lists = [{"name": "List 1", "id": "l1"}, "invalid", None, {}]
        malformed_members = [{"username": "alice", "id": "m1"}, None, 123]

        with patch.object(task_detector_mod, "get_openai_client", return_value=None):
            result = asyncio.run(detector.ai_extract_task_details(
                all_segments_text="fix the printer tomorrow",
                available_lists=malformed_lists,
                available_members=malformed_members
            ))

        list_id, list_name, task_name, description, priority, due_date, assignee_ids = result
        self.assertIsNone(list_id)
        self.assertIsNone(list_name)
        self.assertEqual(task_name, "fix the printer tomorrow")
        self.assertEqual(priority, 3)
        self.assertEqual(assignee_ids, [])

    def test_ai_match_list_graceful_fallback_without_client(self):
        detector = task_detector_mod.TaskDetector
        lists = [
            {"id": "l1", "name": "Engineering Tasks"},
            {"id": "l2", "name": "Bug Tracker"},
            "invalid_entry",
            None
        ]

        with patch.object(task_detector_mod, "get_openai_client", return_value=None):
            # Exact match (case insensitive)
            matched = asyncio.run(detector.ai_match_list("bug tracker", lists))
            self.assertIsNotNone(matched)
            self.assertEqual(matched["id"], "l2")

            # Non-existent match
            unmatched = asyncio.run(detector.ai_match_list("finance", lists))
            self.assertIsNone(unmatched)

            # Empty input
            self.assertIsNone(asyncio.run(detector.ai_match_list("", lists)))
            self.assertIsNone(asyncio.run(detector.ai_match_list("test", [])))


class SegmentExtractionTests(unittest.TestCase):
    def test_extract_segment_texts_handles_various_input_shapes(self):
        extract = main_mod._extract_segment_texts

        # Standard segment dicts
        standard = [{"text": "Hello"}, {"text": "world"}]
        self.assertEqual(extract(standard), ["Hello", "world"])

        # Mixed inputs (strings, whitespace, missing text, non-dicts)
        mixed = [
            {"text": "Create task"},
            "direct string segment",
            {"text": "   "},
            {"other_key": "ignored"},
            None,
            123,
            {"text": "finish reports"}
        ]
        self.assertEqual(extract(mixed), ["Create task", "direct string segment", "finish reports"])

        # Non-list inputs
        self.assertEqual(extract(None), [])
        self.assertEqual(extract("not a list"), [])
        self.assertEqual(extract({}), [])


if __name__ == "__main__":
    unittest.main()
