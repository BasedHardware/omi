import sys
import types
import unittest
from unittest.mock import patch, MagicMock

# Hermetic module stubs for environments without requests/dotenv
if "dotenv" not in sys.modules:
    dotenv_stub = types.ModuleType("dotenv")
    dotenv_stub.load_dotenv = lambda *args, **kwargs: None
    sys.modules["dotenv"] = dotenv_stub

if "requests" not in sys.modules:
    requests_stub = types.ModuleType("requests")
    requests_stub.get = lambda *args, **kwargs: None
    requests_stub.post = lambda *args, **kwargs: None
    sys.modules["requests"] = requests_stub

import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import clickup_client
from clickup_client import ClickUpClient


class TestClickUpClient(unittest.TestCase):
    def setUp(self):
        self.client = ClickUpClient()
        self.token = "test-token"
        self.space_id = "space-1"
        self.team_id = "team-1"

    @patch("requests.get")
    def test_get_spaces(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "spaces": [
                {"id": "space-1", "name": "General", "private": False, "color": "#fff"}
            ]
        }
        mock_get.return_value = mock_resp

        spaces = self.client.get_spaces(self.token, self.team_id)
        self.assertEqual(len(spaces), 1)
        self.assertEqual(spaces[0]["id"], "space-1")
        self.assertEqual(spaces[0]["name"], "General")

    @patch("requests.get")
    def test_get_lists_folderless(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "lists": [
                {"id": "list-1", "name": "Inbox", "folder": None}
            ]
        }
        mock_get.return_value = mock_resp

        lists = self.client.get_lists(self.token, self.space_id)
        self.assertEqual(len(lists), 1)
        self.assertEqual(lists[0]["id"], "list-1")
        self.assertEqual(lists[0]["name"], "Inbox")
        self.assertIsNone(lists[0]["folder_id"])

    @patch("requests.get")
    def test_get_folders(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "folders": [
                {
                    "id": "folder-1",
                    "name": "Sprint 1",
                    "lists": [{"id": "list-2", "name": "Tasks"}]
                }
            ]
        }
        mock_get.return_value = mock_resp

        folders = self.client.get_folders(self.token, self.space_id)
        self.assertEqual(len(folders), 1)
        self.assertEqual(folders[0]["id"], "folder-1")
        self.assertEqual(len(folders[0]["lists"]), 1)

    @patch("requests.get")
    def test_get_folder_lists(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "lists": [
                {"id": "list-nested", "name": "Bugs"}
            ]
        }
        mock_get.return_value = mock_resp

        lists = self.client.get_folder_lists(self.token, "folder-99")
        self.assertEqual(len(lists), 1)
        self.assertEqual(lists[0]["id"], "list-nested")
        self.assertEqual(lists[0]["folder_id"], "folder-99")

    @patch.object(ClickUpClient, "get_spaces")
    @patch.object(ClickUpClient, "get_lists")
    @patch.object(ClickUpClient, "get_folders")
    def test_get_all_lists_includes_folderless_and_folder_lists(
        self, mock_get_folders, mock_get_lists, mock_get_spaces
    ):
        mock_get_spaces.return_value = [{"id": "space-1", "name": "Engineering"}]
        mock_get_lists.return_value = [
            {"id": "list-1", "name": "Backlog", "space_id": "space-1", "folder_id": None}
        ]
        mock_get_folders.return_value = [
            {
                "id": "folder-1",
                "name": "Current Sprint",
                "lists": [{"id": "list-2", "name": "Active Tasks"}]
            }
        ]

        all_lists = self.client.get_all_lists(self.token, self.team_id)

        self.assertEqual(len(all_lists), 2)
        # Check folderless list
        self.assertEqual(all_lists[0]["id"], "list-1")
        self.assertEqual(all_lists[0]["name"], "Backlog")
        self.assertEqual(all_lists[0]["space_name"], "Engineering")
        self.assertIsNone(all_lists[0]["folder_id"])

        # Check folder list
        self.assertEqual(all_lists[1]["id"], "list-2")
        self.assertEqual(all_lists[1]["name"], "Current Sprint / Active Tasks")
        self.assertEqual(all_lists[1]["space_name"], "Engineering")
        self.assertEqual(all_lists[1]["folder_id"], "folder-1")
        self.assertEqual(all_lists[1]["folder_name"], "Current Sprint")

    @patch("requests.get")
    def test_error_handling_fails_closed(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_get.return_value = mock_resp

        self.assertEqual(self.client.get_spaces(self.token, self.team_id), [])
        self.assertEqual(self.client.get_lists(self.token, self.space_id), [])
        self.assertEqual(self.client.get_folders(self.token, self.space_id), [])
        self.assertEqual(self.client.get_folder_lists(self.token, "folder-1"), [])


if __name__ == "__main__":
    unittest.main()
