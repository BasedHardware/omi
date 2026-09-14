import json
import unittest
from unittest.mock import patch

import clickup_client


class FakeResponse:
    def __init__(self, status_code, json_data):
        self.status_code = status_code
        self._json = json_data

    def json(self):
        return self._json


class TestClickUpClient(unittest.TestCase):
    def setUp(self):
        self.client = clickup_client.ClickUpClient()

    # --- pagination: get_lists (folderless) follows ClickUp pagination ---
    @patch("clickup_client.requests.get")
    def test_get_lists_paginates(self, mock_get):
        page1 = {"lists": [{"id": str(i), "name": f"L{i}"} for i in range(100)]}
        page2 = {"lists": [{"id": str(i), "name": f"L{i}"} for i in range(100, 150)]}
        mock_get.side_effect = [FakeResponse(200, page1), FakeResponse(200, page2)]
        lists = self.client.get_lists("tok", "space1")
        self.assertEqual(len(lists), 150)
        self.assertEqual(lists[0]["space_id"], "space1")
        self.assertIsNone(lists[0]["folder_id"])
        self.assertEqual(mock_get.call_count, 2)

    @patch("clickup_client.requests.get")
    def test_get_lists_stops_on_short_page(self, mock_get):
        page = {"lists": [{"id": "1", "name": "Only"}]}
        mock_get.return_value = FakeResponse(200, page)
        lists = self.client.get_lists("tok", "space1")
        self.assertEqual(len(lists), 1)
        self.assertEqual(mock_get.call_count, 1)

    # --- pagination: get_folders ---
    @patch("clickup_client.requests.get")
    def test_get_folders_paginates(self, mock_get):
        page1 = {"folders": [{"id": f"f{i}", "name": f"Fo{i}"} for i in range(100)]}
        page2 = {"folders": [{"id": f"f{i}", "name": f"Fo{i}"} for i in range(100, 120)]}
        mock_get.side_effect = [FakeResponse(200, page1), FakeResponse(200, page2)]
        folders = self.client.get_folders("tok", "space1")
        self.assertEqual(len(folders), 120)
        self.assertEqual(mock_get.call_count, 2)

    # --- pagination: get_folder_lists ---
    @patch("clickup_client.requests.get")
    def test_get_folder_lists_paginates(self, mock_get):
        page1 = {"lists": [{"id": str(i), "name": f"CL{i}"} for i in range(100)]}
        page2 = {"lists": [{"id": str(i), "name": f"CL{i}"} for i in range(100, 130)]}
        mock_get.side_effect = [FakeResponse(200, page1), FakeResponse(200, page2)]
        lists = self.client.get_folder_lists("tok", "folder1")
        self.assertEqual(len(lists), 130)
        self.assertEqual(lists[0]["folder_id"], "folder1")
        self.assertEqual(mock_get.call_count, 2)

    # --- aggregation: folderless + folder-contained ---
    @patch.object(clickup_client.ClickUpClient, "get_spaces",
                  return_value=[{"id": "sp1", "name": "Space1"}])
    @patch("clickup_client.requests.get")
    def test_get_all_lists_aggregates(self, mock_get, mock_spaces):
        folderless = {"lists": [{"id": "L1", "name": "FL1"}, {"id": "L2", "name": "FL2"}]}
        folders = {"folders": [{"id": "F1", "name": "Fo1"}]}
        folder_lists = {"lists": [{"id": "L3", "name": "CL1"}, {"id": "L4", "name": "CL2"}]}
        mock_get.side_effect = [
            FakeResponse(200, folderless),   # get_lists
            FakeResponse(200, folders),      # get_folders
            FakeResponse(200, folder_lists), # get_folder_lists(F1)
        ]
        result = self.client.get_all_lists("tok", "team1")
        self.assertEqual(len(result), 4)
        # folderless keep original name, folder-contained are prefixed
        names = {r["name"] for r in result}
        self.assertIn("FL1", names)
        self.assertIn("Fo1 / CL1", names)
        # folder-contained carries folder metadata
        cl1 = [r for r in result if r["name"] == "Fo1 / CL1"][0]
        self.assertEqual(cl1["folder_id"], "F1")
        self.assertEqual(cl1["space_name"], "Space1")

    # --- folder response embeds lists: no extra request ---
    @patch.object(clickup_client.ClickUpClient, "get_spaces",
                  return_value=[{"id": "sp1", "name": "Space1"}])
    @patch("clickup_client.requests.get")
    def test_get_all_lists_embedded_folder_lists(self, mock_get, mock_spaces):
        folderless = {"lists": []}
        folders = {"folders": [{"id": "F1", "name": "Fo1",
                                "lists": [{"id": "L9", "name": "CL9"}]}]}
        mock_get.side_effect = [
            FakeResponse(200, folderless),
            FakeResponse(200, folders),
        ]
        result = self.client.get_all_lists("tok", "team1")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "Fo1 / CL9")
        # exactly 2 requests: get_lists + get_folders (embedded lists => no 3rd call)
        self.assertEqual(mock_get.call_count, 2)

    # --- degraded failure modes never crash ---
    @patch("clickup_client.requests.get")
    def test_get_lists_api_error_returns_partial(self, mock_get):
        page1 = {"lists": [{"id": "1", "name": "A"}]}
        mock_get.side_effect = [FakeResponse(200, page1), FakeResponse(500, {})]
        lists = self.client.get_lists("tok", "space1")
        self.assertEqual(len(lists), 1)

    @patch.object(clickup_client.ClickUpClient, "get_spaces", return_value=[])
    @patch("clickup_client.requests.get")
    def test_get_all_lists_no_spaces_returns_empty(self, mock_get, mock_spaces):
        self.assertEqual(self.client.get_all_lists("tok", "team1"), [])


if __name__ == "__main__":
    unittest.main()
