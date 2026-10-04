import base64
import json
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from services.users import data_export


@pytest.fixture(autouse=True)
def _isolate_firestore_collection_iterators(monkeypatch):
    monkeypatch.setattr(data_export, "_iter_user_subcollection", MagicMock(return_value=iter([])))
    monkeypatch.setattr(data_export, "_iter_user_nested_subcollection", MagicMock(return_value=iter([])))
    monkeypatch.setattr(data_export.conversations_db, "iter_all_conversation_photos", MagicMock(return_value=[]))


def _stub_all_sections(monkeypatch, **overrides):
    now = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    memory_service = MagicMock()
    memory_service.iter_portability_export_memories.return_value = iter(
        [MagicMock(model_dump=MagicMock(return_value={"id": "mem1"}))]
    )
    seams = {
        "get_user_profile": MagicMock(return_value={"created_at": now}),
        "get_people": MagicMock(return_value=[{"id": "person1"}]),
        "iter_all_action_items": MagicMock(return_value=[{"id": "task1"}]),
    }
    for name, seam in seams.items():
        monkeypatch.setattr(data_export, name, overrides.get(name, seam))
    monkeypatch.setattr(
        data_export, "MemoryService", overrides.get("MemoryService", MagicMock(return_value=memory_service))
    )
    monkeypatch.setattr(
        data_export.conversations_db,
        "iter_all_conversations",
        overrides.get(
            "iter_all_conversations",
            MagicMock(return_value=iter([{"id": "conv1", "is_locked": True}, {"id": "conv2"}])),
        ),
    )
    monkeypatch.setattr(
        data_export.conversations_db,
        "iter_all_conversation_photos",
        overrides.get("iter_all_conversation_photos", MagicMock(return_value=[])),
    )
    monkeypatch.setattr(
        data_export.chat_db,
        "iter_all_messages",
        overrides.get("iter_all_messages", MagicMock(return_value=iter([{"id": "msg1", "created_at": now}]))),
    )
    return memory_service


def test_streaming_first_yield_performs_no_user_data_reads(monkeypatch):
    def _fail(*args, **kwargs):
        raise AssertionError("user data read before first yield")

    _stub_all_sections(
        monkeypatch,
        get_user_profile=_fail,
        get_people=_fail,
        iter_all_action_items=_fail,
        iter_all_conversations=_fail,
        iter_all_conversation_photos=_fail,
        iter_all_messages=_fail,
        MemoryService=MagicMock(return_value=MagicMock(iter_portability_export_memories=MagicMock(side_effect=_fail))),
    )
    monkeypatch.setattr(data_export, "_iter_user_subcollection", _fail)
    monkeypatch.setattr(data_export, "_iter_user_nested_subcollection", _fail)

    stream = data_export.iter_user_data_export_streaming("uid1")

    assert next(stream) == "{\n"
    stream.close()


def test_streaming_sections_match_legacy_export(monkeypatch):
    _stub_all_sections(monkeypatch)

    legacy = json.loads("".join(data_export.iter_user_data_export("uid1")))

    _stub_all_sections(monkeypatch)
    streamed = "".join(data_export.iter_user_data_export_streaming("uid1"))

    assert streamed.endswith(',\n  "export_complete": true\n}\n')
    payload = json.loads(streamed)
    assert payload.pop("export_complete") is True
    assert payload == legacy


def test_streaming_includes_inline_and_stored_photo_bytes(monkeypatch):
    inline = base64.b64encode(b"png-bytes").decode("ascii")
    stored = base64.b64encode(b"stored-bytes").decode("ascii")
    _stub_all_sections(
        monkeypatch,
        iter_all_conversation_photos=MagicMock(
            return_value=[
                ("conv1", {"id": "p1", "base64": inline}),
                ("conv1", {"id": "p2", "storage_id": "obj-2"}),
            ]
        ),
    )
    download = MagicMock(return_value=b"stored-bytes")
    monkeypatch.setattr(data_export, "download_frame_request_pixels", download)

    payload = json.loads("".join(data_export.iter_user_data_export_streaming("uid1")))

    manifest = payload["conversation_photo_manifest"]
    assert manifest[0]["bytes_base64"] == inline
    assert manifest[0]["bytes_available"] is True
    assert manifest[1]["bytes_base64"] == stored
    assert manifest[1]["bytes_available"] is True
    download.assert_called_once_with("uid1", "obj-2")


def test_streaming_omits_manifest_section_when_no_photos(monkeypatch):
    _stub_all_sections(monkeypatch)

    payload = json.loads("".join(data_export.iter_user_data_export_streaming("uid1")))

    assert "conversation_photo_manifest" not in payload


def test_streaming_retained_byte_failure_yields_no_completion_marker(monkeypatch):
    _stub_all_sections(
        monkeypatch,
        iter_all_conversation_photos=MagicMock(return_value=[("conv1", {"id": "p2", "storage_id": "obj-2"})]),
    )
    monkeypatch.setattr(data_export, "download_frame_request_pixels", MagicMock(return_value=b""))

    stream = data_export.iter_user_data_export_streaming("uid1")
    parts = []
    with pytest.raises(data_export.PortabilityExportIncomplete):
        for chunk in stream:
            parts.append(chunk)

    assert not "".join(parts).endswith(',\n  "export_complete": true\n}\n')


def test_streaming_non_finite_late_record_yields_no_completion_marker(monkeypatch):
    _stub_all_sections(
        monkeypatch,
        iter_all_messages=MagicMock(return_value=iter([{"id": "msg1", "score": float("nan")}])),
    )

    parts = []
    with pytest.raises(data_export.PortabilityExportIncomplete):
        for chunk in data_export.iter_user_data_export_streaming("uid1"):
            parts.append(chunk)

    assert not "".join(parts).endswith(',\n  "export_complete": true\n}\n')


def test_streaming_late_memory_iteration_failure_yields_no_completion_marker(monkeypatch):
    def _memories(_uid, *, include_archive=True):
        yield MagicMock(model_dump=MagicMock(return_value={"id": "mem-ok"}))
        raise RuntimeError("memory iteration failed")

    _stub_all_sections(
        monkeypatch,
        MemoryService=MagicMock(
            return_value=MagicMock(iter_portability_export_memories=MagicMock(side_effect=_memories))
        ),
    )

    parts = []
    with pytest.raises(RuntimeError, match="memory iteration failed"):
        for chunk in data_export.iter_user_data_export_streaming("uid1"):
            parts.append(chunk)

    assert not "".join(parts).endswith(',\n  "export_complete": true\n}\n')


def test_streaming_late_chat_iteration_failure_yields_no_completion_marker(monkeypatch):
    def _messages(_uid):
        yield {"id": "msg1"}
        raise RuntimeError("chat iteration failed")

    _stub_all_sections(
        monkeypatch,
        iter_all_messages=MagicMock(side_effect=_messages),
    )

    parts = []
    with pytest.raises(RuntimeError, match="chat iteration failed"):
        for chunk in data_export.iter_user_data_export_streaming("uid1"):
            parts.append(chunk)

    assert not "".join(parts).endswith(',\n  "export_complete": true\n}\n')


def test_streaming_iterator_close_closes_underlying_seams(monkeypatch):
    closed = []

    def _conversations(_uid, *, include_discarded=True):
        try:
            yield {"id": "conv1"}
        finally:
            closed.append("conversations")

    _stub_all_sections(
        monkeypatch,
        iter_all_conversations=MagicMock(side_effect=_conversations),
    )

    stream = data_export.iter_user_data_export_streaming("uid1")
    while next(stream) != "    " + json.dumps({"id": "conv1"}, indent=4):
        pass
    stream.close()

    assert closed == ["conversations"]


def test_streaming_iterator_close_closes_externally_held_source(monkeypatch):
    class _HeldSource:
        def __init__(self):
            self.closed = False

        def __iter__(self):
            return self

        def __next__(self):
            return {"id": "conv1"}

        def close(self):
            self.closed = True

    source = _HeldSource()
    _stub_all_sections(
        monkeypatch,
        iter_all_conversations=MagicMock(return_value=source),
    )

    stream = data_export.iter_user_data_export_streaming("uid1")
    while next(stream) != "    " + json.dumps({"id": "conv1"}, indent=4):
        pass
    stream.close()

    assert source.closed


def test_streaming_export_complete_marker_is_last_section_content(monkeypatch):
    _stub_all_sections(monkeypatch)

    body = "".join(data_export.iter_user_data_export_streaming("uid1"))
    payload = json.loads(body)

    assert list(payload) == [
        "profile",
        "conversations",
        "memories",
        "memory_review_data",
        "memory_ledger_data",
        "jit_data",
        "people",
        "action_items",
        "task_data",
        "chat_messages",
        "export_complete",
    ]
