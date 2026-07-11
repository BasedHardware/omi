"""Unit tests for GET /v1/folders/{folder_id}/conversations/count.

The endpoint validates folder ownership then delegates to the conversations
count() aggregation with a folder_id filter (the same predicate the folder
conversations list uses), so a client can show a per-folder badge without paging.
"""

import os
from unittest.mock import patch

import pytest
from fastapi import HTTPException

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)


def test_folder_conversations_count_returns_count():
    from routers import folders as folders_router

    with patch.object(folders_router.folders_db, "get_folder", return_value={"id": "f1"}), patch.object(
        folders_router.conversations_db, "get_conversations_count", return_value=7
    ) as count_mock:
        result = folders_router.get_folder_conversations_count(folder_id="f1", uid="u1")

    assert result == {"count": 7}
    # Counted with the folder_id filter, not a full scan.
    count_mock.assert_called_once_with("u1", folder_id="f1")


def test_folder_conversations_count_404_when_folder_missing():
    from routers import folders as folders_router

    with patch.object(folders_router.folders_db, "get_folder", return_value=None):
        with pytest.raises(HTTPException) as exc:
            folders_router.get_folder_conversations_count(folder_id="missing", uid="u1")

    assert exc.value.status_code == 404
