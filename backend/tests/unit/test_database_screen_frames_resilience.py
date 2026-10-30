from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock, call

import pytest

from database.screen_frames import (
    bump_conversation_screen_frames_revision,
    delete_conversation_screen_frame_doc,
    delete_conversation_screen_frame_docs,
    delete_screen_frame_cleanup,
    get_conversation_content_window_fields,
    get_conversation_screen_frame_doc,
    get_conversation_screen_frames,
    get_conversation_screen_frames_adjudicated_at,
    get_conversation_screen_frames_marker,
    get_conversation_screen_frames_revision,
    get_conversation_screen_frames_selection_fingerprint,
    list_screen_frame_cleanups,
    mark_conversation_screen_frames_adjudicated,
    record_screen_frame_cleanup,
    set_conversation_screenshot_sharing_enabled,
    store_conversation_screen_frames,
)


class _MockDocSnapshot:
    def __init__(self, doc_id: str, data: dict[str, Any] | None, exists: bool = True):
        self.id = doc_id
        self._data = data or {}
        self.exists = exists
        self.reference = MagicMock()

    def to_dict(self) -> dict[str, Any]:
        return self._data


def _build_mock_client() -> MagicMock:
    client = MagicMock()
    users_col = MagicMock()
    user_doc = MagicMock()
    convs_col = MagicMock()
    conv_doc = MagicMock()
    frames_col = MagicMock()

    client.collection.return_value = users_col
    users_col.document.return_value = user_doc
    user_doc.collection.return_value = convs_col
    convs_col.document.return_value = conv_doc
    conv_doc.collection.return_value = frames_col

    return client


def test_screen_frames_input_validation_uid_and_conversation_id() -> None:
    client = _build_mock_client()

    invalid_ids = ["", "   ", "user/bad", "user\\bad", "user..bad", "user\x00bad", "a" * 150, 12345, None]

    for bad_id in invalid_ids:
        with pytest.raises((ValueError, TypeError)):
            get_conversation_screen_frames(bad_id, "conv1", firestore_client=client)  # type: ignore[arg-type]

        with pytest.raises(ValueError):
            get_conversation_screen_frames("u1", bad_id, firestore_client=client)  # type: ignore[arg-type]

        with pytest.raises(ValueError):
            delete_conversation_screen_frame_docs(bad_id, "conv1", firestore_client=client)  # type: ignore[arg-type]

        with pytest.raises(ValueError):
            bump_conversation_screen_frames_revision(
                bad_id, "conv1", bucket="bkt", firestore_client=client  # type: ignore[arg-type]
            )


def test_store_conversation_screen_frames_validates_frames_payload() -> None:
    client = _build_mock_client()

    # Non-list frames
    with pytest.raises(ValueError, match="frames must be a list"):
        store_conversation_screen_frames("u1", "conv1", "not-a-list", firestore_client=client)  # type: ignore[arg-type]

    # Non-dict frame item
    with pytest.raises(ValueError, match="each frame must be a dictionary"):
        store_conversation_screen_frames(
            "u1", "conv1", ["not-a-dict"], firestore_client=client  # type: ignore[arg-type]
        )

    # Frame with missing or invalid id
    with pytest.raises(ValueError, match="frame_id must be a non-empty string"):
        store_conversation_screen_frames("u1", "conv1", [{"id": ""}], firestore_client=client)

    with pytest.raises(ValueError, match="frame_id contains invalid characters"):
        store_conversation_screen_frames("u1", "conv1", [{"id": "bad/slash"}], firestore_client=client)


def test_delete_conversation_screen_frame_doc_validates_frame_id() -> None:
    client = _build_mock_client()

    with pytest.raises(ValueError):
        delete_conversation_screen_frame_doc("u1", "conv1", "", firestore_client=client)

    with pytest.raises(ValueError):
        delete_conversation_screen_frame_doc("u1", "conv1", "frame/bad", firestore_client=client)


def test_list_screen_frame_cleanups_clamps_and_validates_limit() -> None:
    client = MagicMock()
    col = MagicMock()
    where_mock = MagicMock()
    limit_mock = MagicMock()
    client.collection.return_value = col
    col.where.return_value = where_mock
    where_mock.limit.return_value = limit_mock
    limit_mock.stream.return_value = []

    # Invalid limits: bool, negative, zero
    with pytest.raises(ValueError, match="limit must be a positive integer"):
        list_screen_frame_cleanups("bkt", True, firestore_client=client)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="limit must be a positive integer"):
        list_screen_frame_cleanups("bkt", 0, firestore_client=client)

    with pytest.raises(ValueError, match="limit must be a positive integer"):
        list_screen_frame_cleanups("bkt", -10, firestore_client=client)

    # Upper clamp > 1000 clamped to 1000
    list_screen_frame_cleanups("bkt", 5000, firestore_client=client)
    where_mock.limit.assert_called_with(1000)

    # Valid within bound
    list_screen_frame_cleanups("bkt", 50, firestore_client=client)
    where_mock.limit.assert_called_with(50)


def test_delete_conversation_screen_frame_docs_batches_at_500() -> None:
    client = _build_mock_client()
    batch_mock1 = MagicMock()
    batch_mock2 = MagicMock()
    client.batch.side_effect = [batch_mock1, batch_mock2]

    # Return 505 mock frames
    frames_col = client.collection().document().collection().document().collection()
    mock_frames = [_MockDocSnapshot(f"f_{i}", {"id": f"f_{i}"}) for i in range(505)]
    frames_col.stream.return_value = mock_frames

    deleted = delete_conversation_screen_frame_docs("u1", "conv1", firestore_client=client)
    assert deleted == 505
    assert batch_mock1.commit.call_count == 1
    assert batch_mock2.commit.call_count == 1
    assert batch_mock1.delete.call_count == 500
    assert batch_mock2.delete.call_count == 5


def test_helpers_respect_injected_firestore_client() -> None:
    client = _build_mock_client()
    conv_doc = client.collection().document().collection().document()
    conv_doc.get.return_value = _MockDocSnapshot(
        "conv1", {"screen_frames_env_state": {"bkt": {"revision": 2}}}
    )

    rev = get_conversation_screen_frames_revision("u1", "conv1", bucket="bkt", firestore_client=client)
    assert rev == 2

    set_conversation_screenshot_sharing_enabled("u1", "conv1", False, firestore_client=client)
    conv_doc.update.assert_called_once_with({"screenshot_sharing_enabled": False})
