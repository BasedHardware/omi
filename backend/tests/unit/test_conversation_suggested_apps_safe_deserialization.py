"""Hermetic unit tests for safe App deserialization in get_conversation_suggested_apps.

Prevents HTTP 500 when legacy or malformed apps exist in suggested_summarization_apps.
"""

import os
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

from models.conversation import Conversation
from routers import conversations as conv_router


@pytest.fixture
def mock_conversation():
    c = MagicMock(spec=Conversation)
    c.suggested_summarization_apps = ["app_valid", "app_malformed"]
    return c


def test_suggested_apps_skips_malformed_app_records(monkeypatch, mock_conversation):
    monkeypatch.setattr(
        conv_router, "_get_valid_conversation_by_id", lambda uid, cid: {"id": cid}
    )
    monkeypatch.setattr(
        conv_router, "deserialize_conversation", lambda data: mock_conversation
    )

    valid_app_dict = {
        "id": "app_valid",
        "name": "Valid App",
        "category": "productivity",
        "author": "Author",
        "description": "A valid test app",
        "image": "https://example.com/icon.png",
        "capabilities": ["chat"],
        "uid": "user_1",
    }
    malformed_app_dict = {
        "id": "app_malformed",
        # Missing required category, name, author, description, image, capabilities, uid
    }

    def mock_get_available_app(app_id, uid):
        if app_id == "app_valid":
            return dict(valid_app_dict)
        elif app_id == "app_malformed":
            return dict(malformed_app_dict)
        return None

    with (
        patch(
            "utils.apps.get_available_app_by_id_with_reviews",
            side_effect=mock_get_available_app,
        ),
        patch("utils.apps.get_is_user_paid_app", return_value=False),
    ):
        res = conv_router.get_conversation_suggested_apps("conv_123", uid="test_uid")

    assert res["conversation_id"] == "conv_123"
    assert len(res["suggested_apps"]) == 1
    assert res["suggested_apps"][0]["id"] == "app_valid"
    assert res["suggested_apps"][0]["name"] == "Valid App"
