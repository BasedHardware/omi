"""Unit tests for client device identity contract and registry."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from models.memories import Evidence
from utils.client_device import build_client_device_id, resolve_client_device


def test_build_client_device_id_matches_fcm_shape():
    assert build_client_device_id("ios", "abc12345") == "ios_abc12345"
    assert build_client_device_id("macos", "deadbeef") == "macos_deadbeef"


def test_build_client_device_id_null_when_missing():
    assert build_client_device_id(None, "abc") is None
    assert build_client_device_id("ios", None) is None
    assert build_client_device_id("ios", "default") is None


def test_resolve_client_device_from_headers():
    ctx = resolve_client_device(x_app_platform="macos", x_device_id_hash="a1b2c3d4", x_app_version="1.2.3")
    assert ctx.client_device_id == "macos_a1b2c3d4"
    assert ctx.platform == "macos"
    assert ctx.app_version == "1.2.3"


@patch("database.users.try_acquire_client_device_write_lock", return_value=True)
def test_record_client_device_upserts_and_throttles(mock_lock):
    from database import users as users_db

    mock_doc = MagicMock()
    mock_doc.get.return_value.exists = False
    mock_collection = MagicMock()
    mock_collection.document.return_value = mock_doc
    mock_user = MagicMock()
    mock_user.collection.return_value = mock_collection

    with patch.object(users_db, "db") as mock_db:
        mock_db.collection.return_value.document.return_value = mock_user
        users_db.record_client_device(
            "uid-1",
            client_device_id="macos_a1b2c3d4",
            platform="macos",
            app_version="1.0.0",
        )

    mock_lock.assert_called_once_with("uid-1", "macos_a1b2c3d4")
    mock_doc.set.assert_called_once()
    payload = mock_doc.set.call_args[0][0]
    assert payload["platform"] == "macos"
    assert payload["device_class"] == "desktop"
    assert "first_seen_at" in payload


def test_evidence_id_unchanged_when_client_device_absent():
    artifact = {"kind": "transcript_segments", "conversation_id": "conv-1"}
    without_device = Evidence.from_source(
        source_id="conv-1",
        source_type="conversation",
        source_signal="transcription",
        extractor_id="new_memories_extractor",
        extractor_version="v1",
        artifact_ref=artifact,
    )
    with_device = Evidence.from_source(
        source_id="conv-1",
        source_type="conversation",
        source_signal="transcription",
        extractor_id="new_memories_extractor",
        extractor_version="v1",
        artifact_ref=artifact,
        client_device_id="macos_abc",
    )
    assert without_device.evidence_id == with_device.evidence_id
    assert with_device.client_device_id == "macos_abc"


def test_transcript_artifact_ref_omits_device_from_hash_inputs():
    from models.conversation import Conversation
    from models.structured import Structured

    def _artifact_ref(conversation: Conversation) -> dict:
        segments = conversation.transcript_segments or []
        return {
            "kind": "transcript_segments",
            "conversation_id": conversation.id,
            "segment_ids": [segment.id for segment in segments if segment.id],
            "start": min((segment.start for segment in segments), default=None),
            "end": max((segment.end for segment in segments), default=None),
        }

    base = Conversation(
        id="c1",
        created_at=datetime.now(timezone.utc),
        started_at=datetime.now(timezone.utc),
        finished_at=datetime.now(timezone.utc),
        structured=Structured(),
    )
    with_device = base.model_copy(update={"client_device_id": "macos_abc12345"})

    assert _artifact_ref(base) == _artifact_ref(with_device)
