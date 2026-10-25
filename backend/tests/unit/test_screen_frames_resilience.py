"""Unit tests for screen frames resilience, path traversal sanitization, and input validation (#19826)."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, call, patch
import pytest

from database.screen_frames import (
    _clean_id,
    _conversation_ref,
    delete_conversation_screen_frame_doc,
    delete_conversation_screen_frame_docs,
    delete_screen_frame_cleanup,
    get_conversation_content_window_fields,
    get_conversation_screen_frames,
    get_conversation_screen_frames_adjudicated_at,
    get_conversation_screen_frames_marker,
    get_conversation_screen_frames_selection_fingerprint,
    list_screen_frame_cleanups,
    mark_conversation_screen_frames_adjudicated,
    record_screen_frame_cleanup,
    set_conversation_screenshot_sharing_enabled,
    store_conversation_screen_frames,
)


class TestCleanId:
    """Test suite for _clean_id validation helper."""

    @pytest.mark.parametrize(
        "valid_id,expected",
        [
            ("user123", "user123"),
            ("  conv_456  ", "conv_456"),
            ("bucket-name.prod_1", "bucket-name.prod_1"),
            ("frame-uuid-99", "frame-uuid-99"),
            ("a" * 128, "a" * 128),
        ],
    )
    def test_clean_id_valid(self, valid_id, expected):
        assert _clean_id(valid_id, "test_field") == expected

    @pytest.mark.parametrize(
        "invalid_id,match",
        [
            (None, "expected string"),
            (12345, "expected string"),
            ([], "expected string"),
            ({}, "expected string"),
            ("", "cannot be empty"),
            ("   ", "cannot be empty"),
            ("../traversal", "path traversal detected"),
            ("..\\traversal", "path traversal detected"),
            ("path/with/slash", "path traversal detected"),
            ("path\\with\\backslash", "path traversal detected"),
            ("foo/../bar", "path traversal detected"),
            ("a" * 129, "exceeds 128 characters"),
        ],
    )
    def test_clean_id_invalid(self, invalid_id, match):
        with pytest.raises(ValueError, match=match):
            _clean_id(invalid_id, "test_field")


class TestScreenFramesCRUDResilience:
    """Test Firestore operations defend against injection and respect custom firestore_client."""

    @pytest.fixture
    def mock_db(self):
        return MagicMock()

    def test_conversation_ref_sanitizes_and_uses_client(self, mock_db):
        ref = _conversation_ref("user-1", "conv-2", firestore_client=mock_db)
        mock_db.collection.assert_called_with("users")
        mock_db.collection().document.assert_called_with("user-1")

        with pytest.raises(ValueError, match="path traversal detected"):
            _conversation_ref("../../evil", "conv-2", firestore_client=mock_db)

        with pytest.raises(ValueError, match="path traversal detected"):
            _conversation_ref("user-1", "sub/conv", firestore_client=mock_db)

    def test_get_conversation_screen_frames(self, mock_db):
        doc1 = MagicMock()
        doc1.to_dict.return_value = {"id": "frame1", "data_protection_level": "standard"}
        mock_frames_ref = MagicMock()
        mock_frames_ref.stream.return_value = [doc1]

        mock_db.collection().document().collection().document().collection.return_value = mock_frames_ref

        res = get_conversation_screen_frames("user-1", "conv-1", firestore_client=mock_db)
        assert len(res) == 1
        assert res[0]["id"] == "frame1"

        with pytest.raises(ValueError, match="path traversal detected"):
            get_conversation_screen_frames("../user", "conv-1", firestore_client=mock_db)

    def test_store_conversation_screen_frames_validation(self, mock_db):
        mock_tx = MagicMock()
        mock_db.transaction.return_value = mock_tx

        conv_snap = MagicMock()
        conv_snap.exists = True
        conv_ref = MagicMock()
        conv_ref.get.return_value = conv_snap

        mock_db.collection().document().collection().document.return_value = conv_ref

        # Path traversal in frame ID
        with pytest.raises(ValueError, match="path traversal detected"):
            store_conversation_screen_frames(
                "user-1", "conv-1", [{"id": "../bad_id"}], firestore_client=mock_db
            )

        # Path traversal in uid
        with pytest.raises(ValueError, match="path traversal detected"):
            store_conversation_screen_frames(
                "../user", "conv-1", [{"id": "frame-1"}], firestore_client=mock_db
            )

        # Path traversal in conversation_id
        with pytest.raises(ValueError, match="path traversal detected"):
            store_conversation_screen_frames(
                "user-1", "conv/../1", [{"id": "frame-1"}], firestore_client=mock_db
            )

        # Valid write returns the processed frames (due to prepare_for_write wrapper)
        result = store_conversation_screen_frames(
            "user-1", "conv-1", [{"id": "frame-100", "bytes": 10}], firestore_client=mock_db
        )
        assert isinstance(result, list)
        assert result[0]["id"] == "frame-100"

    def test_delete_conversation_screen_frame_doc(self, mock_db):
        frame_doc = MagicMock()
        frame_doc.get.return_value.exists = True
        mock_db.collection().document().collection().document().collection().document.return_value = frame_doc

        success = delete_conversation_screen_frame_doc(
            "user-1", "conv-1", "frame-1", firestore_client=mock_db
        )
        assert success is True
        frame_doc.delete.assert_called_once()

        frame_doc.get.return_value.exists = False
        frame_doc.delete.reset_mock()
        missing = delete_conversation_screen_frame_doc(
            "user-1", "conv-1", "frame-1", firestore_client=mock_db
        )
        assert missing is False
        frame_doc.delete.assert_not_called()

        with pytest.raises(ValueError, match="path traversal detected"):
            delete_conversation_screen_frame_doc(
                "user-1", "conv-1", "path/traversal", firestore_client=mock_db
            )

    def test_delete_conversation_screen_frame_docs(self, mock_db):
        batch = MagicMock()
        mock_db.batch.return_value = batch

        d1 = MagicMock()
        d2 = MagicMock()

        mock_frames_coll = MagicMock()
        mock_frames_coll.stream.return_value = [d1, d2]
        mock_db.collection().document().collection().document().collection.return_value = mock_frames_coll

        deleted_count = delete_conversation_screen_frame_docs(
            "user-1", "conv-1", firestore_client=mock_db
        )
        assert deleted_count == 2
        batch.commit.assert_called_once()

        with pytest.raises(ValueError, match="path traversal detected"):
            delete_conversation_screen_frame_docs(
                "../user", "conv-1", firestore_client=mock_db
            )


class TestCleanupsResilience:
    """Test screen frame cleanup queue operations with input validation and limit clamping."""

    @pytest.fixture
    def mock_db(self):
        return MagicMock()

    def test_record_screen_frame_cleanup(self, mock_db):
        cleanups_coll = MagicMock()
        mock_db.collection.return_value = cleanups_coll

        record_screen_frame_cleanup(
            "bucket-a",
            "user-1",
            "conv-1",
            "frame-1",
            ["obj/1.jpg"],
            firestore_client=mock_db,
        )
        cleanups_coll.document.assert_called_once_with("bucket_a__frame-1")

        with pytest.raises(ValueError, match="path traversal detected"):
            record_screen_frame_cleanup(
                "../bucket", "user-1", "conv-1", "frame-1", ["obj/1.jpg"], firestore_client=mock_db
            )

    def test_list_screen_frame_cleanups_clamping(self, mock_db):
        cleanups_coll = MagicMock()
        query = MagicMock()
        cleanups_coll.where.return_value = query
        query.order_by.return_value = query
        query.limit.return_value = query
        query.stream.return_value = []
        mock_db.collection.return_value = cleanups_coll

        # Negative limit clamped to 1
        list_screen_frame_cleanups("bucket-a", limit=-5, firestore_client=mock_db)
        query.limit.assert_called_with(1)

        # Huge limit clamped to 1000
        list_screen_frame_cleanups("bucket-a", limit=5000, firestore_client=mock_db)
        query.limit.assert_called_with(1000)

        # In-range limit respected
        list_screen_frame_cleanups("bucket-a", limit=50, firestore_client=mock_db)
        query.limit.assert_called_with(50)

    def test_delete_screen_frame_cleanup(self, mock_db):
        doc_ref = MagicMock()
        mock_db.collection().document.return_value = doc_ref

        delete_screen_frame_cleanup("cleanup-123", firestore_client=mock_db)
        doc_ref.delete.assert_called_once()

        with pytest.raises(ValueError, match="path traversal detected"):
            delete_screen_frame_cleanup("../bad_id", firestore_client=mock_db)


class TestAdjudicationAndSettingsResilience:
    """Test adjudication state and screenshot sharing methods."""

    @pytest.fixture
    def mock_db(self):
        return MagicMock()

    def test_mark_and_get_adjudicated_at(self, mock_db):
        conv_doc = MagicMock()
        mock_db.collection().document().collection().document.return_value = conv_doc

        stamp = mark_conversation_screen_frames_adjudicated(
            "user-1",
            "conv-1",
            bucket="bucket-x",
            selection_fingerprint="fp-123",
            firestore_client=mock_db,
        )
        assert isinstance(stamp, datetime)
        assert stamp.tzinfo == timezone.utc
        conv_doc.set.assert_called_once()

        with pytest.raises(ValueError, match="path traversal detected"):
            mark_conversation_screen_frames_adjudicated(
                "user-1",
                "conv-1",
                bucket="../bucket",
                selection_fingerprint="fp-123",
                firestore_client=mock_db,
            )

    def test_set_conversation_screenshot_sharing_enabled(self, mock_db):
        conv_doc = MagicMock()
        mock_db.collection().document().collection().document.return_value = conv_doc

        set_conversation_screenshot_sharing_enabled(
            "user-1", "conv-1", True, firestore_client=mock_db
        )
        conv_doc.update.assert_called_once_with({"screenshot_sharing_enabled": True})

        with pytest.raises(ValueError, match="path traversal detected"):
            set_conversation_screenshot_sharing_enabled(
                "../user", "conv-1", True, firestore_client=mock_db
            )
