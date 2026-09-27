import os
import sys
import types
import unittest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

# Stub optional google cloud services
import google.cloud
for m in ["tasks_v2", "storage", "pubsub_v1", "logging"]:
    full = f"google.cloud.{m}"
    if full not in sys.modules:
        mod = MagicMock()
        sys.modules[full] = mod
        setattr(google.cloud, m, mod)

from fastapi import HTTPException
from fastapi.testclient import TestClient
from fastapi import FastAPI

import routers.folders as folders_router
from models.folder import CreateFolderRequest, UpdateFolderRequest, ReorderFoldersRequest, MoveConversationRequest, BulkMoveConversationsRequest

app = FastAPI()
app.include_router(folders_router.router)
app.dependency_overrides[folders_router.auth.get_current_user_uid] = lambda: "test-uid-123"

class TestFoldersRouter(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.uid = "test-uid-123"

    @patch("routers.folders.folders_db.get_folders")
    def test_get_folders_success(self, mock_get_folders):
        mock_get_folders.return_value = [
            {
                "id": "f1",
                "name": "Work",
                "description": None,
                "color": "#6B7280",
                "icon": "folder",
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
                "order": 0,
                "is_default": False,
                "is_system": False,
                "category_mapping": None,
                "conversation_count": 0,
            }
        ]
        res = self.client.get("/v1/folders")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.json()), 1)
        self.assertEqual(res.json()[0]["id"], "f1")

    @patch("routers.folders.folders_db.get_folders")
    def test_get_folders_database_error(self, mock_get_folders):
        mock_get_folders.side_effect = RuntimeError("Firestore unavailable")
        res = self.client.get("/v1/folders")
        self.assertEqual(res.status_code, 500)
        self.assertEqual(res.json()["detail"], "Failed to fetch folders")

    def test_create_folder_whitespace_name(self):
        res = self.client.post("/v1/folders", json={"name": "   "})
        self.assertEqual(res.status_code, 400)
        self.assertIn("cannot be empty or whitespace", res.json()["detail"])

    @patch("routers.folders.folders_db.get_folders")
    def test_create_folder_limit_reached(self, mock_get_folders):
        mock_get_folders.return_value = [{"id": f"f_{i}", "is_system": False} for i in range(50)]
        res = self.client.post("/v1/folders", json={"name": "Over Limit"})
        self.assertEqual(res.status_code, 400)
        self.assertIn("Maximum folder limit reached", res.json()["detail"])

    def test_get_folder_whitespace_id(self):
        res = self.client.get("/v1/folders/%20%20")
        self.assertEqual(res.status_code, 400)
        self.assertIn("folder_id cannot be empty or whitespace", res.json()["detail"])

    @patch("routers.folders.folders_db.get_folder", return_value=None)
    def test_get_folder_not_found(self, mock_get_folder):
        res = self.client.get("/v1/folders/nonexistent")
        self.assertEqual(res.status_code, 404)
        self.assertEqual(res.json()["detail"], "Folder not found")

    def test_update_folder_empty_payload(self):
        res = self.client.patch("/v1/folders/f1", json={})
        self.assertEqual(res.status_code, 400)
        self.assertIn("At least one field must be provided", res.json()["detail"])

    def test_update_folder_whitespace_name(self):
        res = self.client.patch("/v1/folders/f1", json={"name": "   "})
        self.assertEqual(res.status_code, 400)
        self.assertIn("cannot be empty or whitespace", res.json()["detail"])

    @patch("routers.folders.folders_db.get_folder")
    def test_delete_folder_system_prevented(self, mock_get_folder):
        mock_get_folder.return_value = {"id": "sys_f", "is_system": True}
        res = self.client.delete("/v1/folders/sys_f")
        self.assertEqual(res.status_code, 400)
        self.assertIn("Cannot delete system folder", res.json()["detail"])

    @patch("routers.folders.folders_db.get_folder")
    def test_delete_folder_same_target(self, mock_get_folder):
        mock_get_folder.return_value = {"id": "f1", "is_system": False}
        res = self.client.delete("/v1/folders/f1?move_to_folder_id=f1")
        self.assertEqual(res.status_code, 400)
        self.assertIn("Cannot move conversations to the folder being deleted", res.json()["detail"])

    def test_delete_folder_whitespace_move_to_id(self):
        res = self.client.delete("/v1/folders/f1?move_to_folder_id=%20%20")
        self.assertEqual(res.status_code, 400)
        self.assertIn("move_to_folder_id cannot be empty or whitespace", res.json()["detail"])

    @patch("routers.folders.conversations_db.get_conversation")
    def test_move_conversation_locked_conversation(self, mock_get_conv):
        mock_get_conv.return_value = {"id": "c1", "is_locked": True}
        res = self.client.patch("/v1/conversations/c1/folder", json={"folder_id": "f1"})
        self.assertEqual(res.status_code, 402)
        self.assertIn("A paid plan is required", res.json()["detail"])

    def test_bulk_move_whitespace_id_in_list(self):
        res = self.client.post("/v1/folders/f1/conversations/bulk-move", json={"conversation_ids": ["c1", "   "]})
        self.assertEqual(res.status_code, 400)
        self.assertIn("conversation_ids contains empty or whitespace ID", res.json()["detail"])


if __name__ == "__main__":
    unittest.main()