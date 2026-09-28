import os
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from fastapi import HTTPException

os.environ.setdefault("ENCRYPTION_SECRET", "0123456789abcdef0123456789abcdef")

from models.folder import Folder
from routers import folders as folders_router


@pytest.fixture
def now_utc():
    return datetime.now(timezone.utc)


@pytest.fixture
def valid_folder_dict(now_utc):
    return {
        "id": "folder-valid-1",
        "name": "Work Projects",
        "description": "Work and sprint discussions",
        "color": "#6B7280",
        "icon": "folder",
        "created_at": now_utc,
        "updated_at": now_utc,
        "order": 0,
        "is_default": False,
        "is_system": False,
        "conversation_count": 5,
    }


def test_get_folders_skips_corrupted_folders_and_logs_warning(
    valid_folder_dict, now_utc
):
    """GET /v1/folders skips malformed/corrupted folder documents instead of failing with 500."""
    corrupted_folder_missing_timestamps = {
        "id": "folder-corrupt-1",
        "name": "Corrupted Folder Missing Timestamps",
        # missing created_at and updated_at
    }
    corrupted_folder_empty_name = {
        "id": "folder-corrupt-2",
        "name": "",  # name requires min_length=1
        "created_at": now_utc,
        "updated_at": now_utc,
    }

    folders_data = [
        valid_folder_dict,
        corrupted_folder_missing_timestamps,
        corrupted_folder_empty_name,
    ]

    with (
        patch.object(
            folders_router.folders_db, "get_folders", return_value=folders_data
        ),
        patch.object(folders_router.logger, "warning") as mock_warning,
    ):
        result = folders_router.get_folders(uid="test-user-123")

        # Response must only contain the valid folder
        assert len(result) == 1
        assert isinstance(result[0], Folder)
        assert result[0].id == "folder-valid-1"
        assert result[0].name == "Work Projects"

        # Warnings should have been logged for both corrupted folders
        assert mock_warning.call_count == 2
        warning_calls = [call[0][0] for call in mock_warning.call_args_list]
        assert any("folder-corrupt-1" in msg for msg in warning_calls)
        assert any("folder-corrupt-2" in msg for msg in warning_calls)


def test_get_folder_valid_returns_model(valid_folder_dict):
    """GET /v1/folders/{folder_id} returns validated Folder model for valid document."""
    with patch.object(
        folders_router.folders_db, "get_folder", return_value=valid_folder_dict
    ):
        result = folders_router.get_folder(
            folder_id="folder-valid-1", uid="test-user-123"
        )
        assert isinstance(result, Folder)
        assert result.id == "folder-valid-1"
        assert result.name == "Work Projects"
        assert result.color == "#6B7280"


def test_get_folder_corrupt_raises_500_with_clean_detail():
    """GET /v1/folders/{folder_id} raises 500 with clean detail when stored document is corrupted."""
    corrupted_folder = {
        "id": "folder-corrupt-99",
        "name": "Missing Required Timestamps",
    }

    with (
        patch.object(
            folders_router.folders_db, "get_folder", return_value=corrupted_folder
        ),
        patch.object(folders_router.logger, "error") as mock_error,
    ):
        with pytest.raises(HTTPException) as exc_info:
            folders_router.get_folder(
                folder_id="folder-corrupt-99", uid="test-user-123"
            )

        assert exc_info.value.status_code == 500
        assert exc_info.value.detail == "Stored folder document is corrupted"
        mock_error.assert_called_once()
        assert "folder-corrupt-99" in mock_error.call_args[0][0]
        assert "test-user-123" in mock_error.call_args[0][0]


def test_get_folder_not_found_raises_404():
    """GET /v1/folders/{folder_id} raises 404 when folder does not exist."""
    with patch.object(folders_router.folders_db, "get_folder", return_value=None):
        with pytest.raises(HTTPException) as exc_info:
            folders_router.get_folder(
                folder_id="nonexistent-folder", uid="test-user-123"
            )

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "Folder not found"
