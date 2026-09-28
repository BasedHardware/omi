import pytest
from unittest.mock import AsyncMock, patch
from fastapi import HTTPException
from backend.routers.folders import get_folders
from backend.routers.developer import get_user_folders
from backend.models import Folder, DeveloperFolder

@pytest.mark.asyncio
async def test_get_folders_with_corrupt_records():
    mock_docs = [
        {"id": "valid", "name": "Test", "created_at": "2023-01-01"},
        {"id": "missing_name", "created_at": "2023-01-01"},
        {"id": "missing_id", "name": "No ID", "created_at": "2023-01-01"},
        {"id": "invalid", "created_at": "2023-01-01"}  # Missing name
    ]

    with patch('backend.routers.folders.firestore.get_folders_collection', new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_docs
        folders = await get_folders()

        assert len(folders) == 1
        assert folders[0].name == "Test"

@pytest.mark.asyncio
async def test_get_user_folders_with_corrupt_records():
    mock_docs = [
        {"id": "valid", "name": "Dev Test", "created_at": "2023-01-01"},
        {"id": "missing_fields", "created_at": "2023-01-01"},
        {"id": "invalid", "name": "No Timestamp"}  # Missing created_at
    ]

    with patch('backend.routers.developer.firestore.get_user_folders_collection', new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_docs
        folders = await get_user_folders("test_user")

        assert len(folders) == 1
        assert folders[0].name == "Dev Test"