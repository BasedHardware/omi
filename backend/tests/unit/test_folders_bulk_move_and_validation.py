"""Unit tests for folders router and database bulk move deduplication and ID bounds."""

import sys
from unittest.mock import MagicMock, patch
import pytest
from fastapi import HTTPException
from pydantic import BaseModel, ValidationError

from testing.import_isolation import AutoMockModule

# Ensure all external dependencies are stubbed
for mod in [
    "google",
    "google.api_core",
    "google.api_core.exceptions",
    "google.cloud",
    "google.cloud.firestore",
    "google.cloud.firestore_v1",
    "database._client",
    "database.document_ids",
    "database.firestore_transaction_retry",
    "database.conversations",
    "utils.conversations.render",
    "utils.other.endpoints",
]:
    sys.modules[mod] = AutoMockModule(mod)

# Define proper Pydantic models for Conversation so FastAPI routes compile
class MockConversation(BaseModel):
    id: str = "conv_1"
    deleted: bool = False
    is_locked: bool = False

class MockConversationMutationResponse(BaseModel):
    status: str = "ok"
    conversation: dict = None

mock_models_conv = AutoMockModule("models.conversation")
mock_models_conv.Conversation = MockConversation
mock_models_conv.ConversationMutationResponse = MockConversationMutationResponse
sys.modules["models.conversation"] = mock_models_conv

from models.folder import (
    BulkMoveConversationsRequest,
    CreateFolderRequest,
    UpdateFolderRequest,
    ReorderFoldersRequest,
)
import database.folders as folders_db
import routers.folders as folders_router


class TestFolderModelsValidation:
    """Test Pydantic model validation and bounds."""

    def test_bulk_move_request_deduplication_and_stripping(self):
        """BulkMoveConversationsRequest strips whitespace and deduplicates IDs."""
        req = BulkMoveConversationsRequest(conversation_ids=[" c1 ", "c2", "c1", " c2\t", "c3 "])
        assert req.conversation_ids == ["c1", "c2", "c3"]

    def test_bulk_move_request_rejects_empty_ids(self):
        """BulkMoveConversationsRequest rejects empty or whitespace-only IDs."""
        with pytest.raises(ValidationError):
            BulkMoveConversationsRequest(conversation_ids=[""])

        with pytest.raises(ValidationError):
            BulkMoveConversationsRequest(conversation_ids=["   "])

        with pytest.raises(ValidationError):
            BulkMoveConversationsRequest(conversation_ids=[])

    def test_bulk_move_request_bounds(self):
        """BulkMoveConversationsRequest enforces max_length=100."""
        too_many = [f"c_{i}" for i in range(101)]
        with pytest.raises(ValidationError):
            BulkMoveConversationsRequest(conversation_ids=too_many)

    def test_create_folder_name_validation(self):
        """CreateFolderRequest rejects whitespace-only name."""
        with pytest.raises(ValidationError):
            CreateFolderRequest(name="   ")

        req = CreateFolderRequest(name="  Projects  ")
        assert req.name == "Projects"

    def test_update_folder_name_validation(self):
        """UpdateFolderRequest rejects whitespace-only name."""
        with pytest.raises(ValidationError):
            UpdateFolderRequest(name="   ")

        req = UpdateFolderRequest(name="  Archive  ")
        assert req.name == "Archive"

    def test_reorder_folders_rejects_duplicates(self):
        """ReorderFoldersRequest rejects duplicate folder IDs."""
        with pytest.raises(ValidationError):
            ReorderFoldersRequest(folder_ids=["f1", "f2", "f1"])


class TestFoldersRouterBulkMove:
    """Test folders router endpoints with focus on bulk-move deduplication."""

    def test_bulk_move_invalid_folder_id(self):
        """Rejects empty or whitespace folder_id."""
        req = BulkMoveConversationsRequest(conversation_ids=["c1"])
        with pytest.raises(HTTPException) as exc_info:
            folders_router.bulk_move_conversations(folder_id="   ", request=req, uid="usr_1")
        assert exc_info.value.status_code == 400

    def test_bulk_move_folder_not_found(self):
        """Raises 404 when target folder does not exist."""
        req = BulkMoveConversationsRequest(conversation_ids=["c1"])
        with patch.object(folders_router.folders_db, "get_folder", return_value=None):
            with pytest.raises(HTTPException) as exc_info:
                folders_router.bulk_move_conversations(folder_id="f_missing", request=req, uid="usr_1")
            assert exc_info.value.status_code == 404

    def test_bulk_move_conversations_success_with_deduplication(self):
        """Deduplicates IDs and moves conversations successfully."""
        req = BulkMoveConversationsRequest(conversation_ids=["c1", "c2", "c1"])
        mock_folder = {"id": "f_target", "name": "Work"}

        mock_conv1 = {"id": "c1", "deleted": False, "is_locked": False}
        mock_conv2 = {"id": "c2", "deleted": False, "is_locked": False}

        def get_conv(uid, cid):
            if cid == "c1":
                return mock_conv1
            if cid == "c2":
                return mock_conv2
            return None

        with patch.object(folders_router.folders_db, "get_folder", return_value=mock_folder), \
             patch.object(folders_router.conversations_db, "get_conversation", side_effect=get_conv) as mock_get_c, \
             patch.object(folders_router.folders_db, "bulk_move_conversations_to_folder", return_value=2) as mock_db_move:

            res = folders_router.bulk_move_conversations(folder_id="f_target", request=req, uid="usr_1")
            assert res == {"status": "ok", "moved_count": 2}
            # Verify get_conversation was called only for unique IDs
            assert mock_get_c.call_count == 2
            mock_db_move.assert_called_once_with("usr_1", ["c1", "c2"], "f_target")

    def test_bulk_move_conversation_deleted_raises_404(self):
        """Raises 404 if any conversation is deleted or not found."""
        req = BulkMoveConversationsRequest(conversation_ids=["c1", "c_del"])
        mock_folder = {"id": "f_target", "name": "Work"}

        def get_conv(uid, cid):
            if cid == "c1":
                return {"id": "c1", "deleted": False}
            return {"id": "c_del", "deleted": True}

        with patch.object(folders_router.folders_db, "get_folder", return_value=mock_folder), \
             patch.object(folders_router.conversations_db, "get_conversation", side_effect=get_conv):

            with pytest.raises(HTTPException) as exc_info:
                folders_router.bulk_move_conversations(folder_id="f_target", request=req, uid="usr_1")
            assert exc_info.value.status_code == 404
            assert "c_del not found" in exc_info.value.detail

    def test_bulk_move_conversation_locked_raises_402(self):
        """Raises 402 if any conversation is locked."""
        req = BulkMoveConversationsRequest(conversation_ids=["c_locked"])
        mock_folder = {"id": "f_target", "name": "Work"}

        with patch.object(folders_router.folders_db, "get_folder", return_value=mock_folder), \
             patch.object(folders_router.conversations_db, "get_conversation", return_value={"id": "c_locked", "is_locked": True, "deleted": False}):

            with pytest.raises(HTTPException) as exc_info:
                folders_router.bulk_move_conversations(folder_id="f_target", request=req, uid="usr_1")
            assert exc_info.value.status_code == 402

    def test_database_bulk_move_deduplication(self):
        """Database function bulk_move_conversations_to_folder defensively deduplicates IDs."""
        mock_db = MagicMock()
        mock_batch = MagicMock()
        mock_db.batch.return_value = mock_batch

        mock_doc1 = MagicMock()
        mock_doc1.exists = True
        mock_doc1.to_dict.return_value = {"folder_id": "old_f"}
        mock_doc1.reference = "ref1"

        mock_doc2 = MagicMock()
        mock_doc2.exists = True
        mock_doc2.to_dict.return_value = {"folder_id": "old_f"}
        mock_doc2.reference = "ref2"

        mock_db.get_all.return_value = [mock_doc1, mock_doc2]

        with patch.object(folders_db, "db", mock_db), \
             patch.object(folders_db, "_typed_doc", side_effect=lambda doc: doc.to_dict()), \
             patch.object(folders_db, "update_folder_conversation_count"):

            # Pass duplicates in conversation_ids
            moved = folders_db.bulk_move_conversations_to_folder("usr_1", ["c1", "c2", "c1"], "target_f")
            assert moved == 2
            # Check db.get_all was passed exactly 2 unique refs, not 3
            assert len(mock_db.get_all.call_args[0][0]) == 2
