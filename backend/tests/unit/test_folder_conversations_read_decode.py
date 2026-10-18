"""Tests for decoding, visibility filtering, and counting folder conversations (Issue #21833).

Verifies:
1. `folders_db.get_conversations_in_folder` runs `prepare_conversation_for_read` so compressed
   transcript segments, user titles, and user corrections are properly decoded.
2. Visibility filtering skips soft-deleted tombstones and dream duplicates.
3. Pagination refills pages via `start_after` when hidden rows appear in the window.
4. `update_folder_conversation_count` subtracts hidden rows via `conversation_visibility_counts.count_hidden`.
5. `routers.folders.get_folder_conversations` validates decoded conversations into `Conversation` models without dropping them.
"""

import copy
import json
import os
import sys
import zlib
from datetime import datetime, timezone
from unittest.mock import MagicMock

os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-real")
os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")


import pytest

# Defend against preceding test files that stubbed top-level packages without __file__
for _pkg in ["models", "database", "utils", "google"]:
    if _pkg in sys.modules and getattr(sys.modules[_pkg], "__file__", None) is None:
        del sys.modules[_pkg]
        for _sub in list(sys.modules):
            if _sub.startswith(f"{_pkg}."):
                del sys.modules[_sub]

from database import folders as folders_db
from models.conversation import Conversation, TranscriptSegment


@pytest.fixture(autouse=True)
def _stub_missing_modules(monkeypatch):
    for mod in ["pydub", "google.cloud.tasks_v2"]:
        if mod not in sys.modules:
            monkeypatch.setitem(sys.modules, mod, MagicMock())


NOW = datetime.now(timezone.utc)


class FakeDoc:
    def __init__(self, doc_id: str, data: dict, update_time=None):
        self.id = doc_id
        self._data = copy.deepcopy(data)
        self.update_time = update_time

    def to_dict(self):
        return copy.deepcopy(self._data)


class FakeQuery:
    def __init__(self, docs):
        self._docs = list(docs)
        self._offset = 0
        self._limit = None

    def where(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def offset(self, n):
        new_q = FakeQuery(self._docs)
        new_q._offset = n
        new_q._limit = self._limit
        return new_q

    def limit(self, n):
        new_q = FakeQuery(self._docs)
        new_q._offset = self._offset
        new_q._limit = n
        return new_q

    def start_after(self, doc):
        idx = -1
        for i, d in enumerate(self._docs):
            if d.id == doc.id:
                idx = i
                break
        remaining = self._docs[idx + 1 :] if idx >= 0 else []
        return FakeQuery(remaining)

    def stream(self):
        start = self._offset
        end = start + self._limit if self._limit is not None else len(self._docs)
        for doc in self._docs[start:end]:
            yield doc

    def count(self):
        query_self = self

        class CountAgg:
            def get(self):
                val = MagicMock()
                val.value = len(query_self._docs)
                return [[val]]

        return CountAgg()


def _make_compressed_segments(text="Hello world"):
    segments = [
        {
            "id": "seg-1",
            "text": text,
            "speaker": "SPEAKER_00",
            "is_user": True,
            "start": 0.0,
            "end": 1.5,
        }
    ]
    raw_json = json.dumps(segments).encode("utf-8")
    return zlib.compress(raw_json)


def test_get_conversations_in_folder_decodes_compressed_segments(monkeypatch):
    compressed_bytes = _make_compressed_segments("Folder conversation transcript")
    raw_conv = {
        "folder_id": "folder-123",
        "created_at": NOW,
        "discarded": False,
        "transcript_segments_compressed": True,
        "transcript_segments": compressed_bytes,
        "structured": {"title": "Original Title", "category": "work"},
        "user_title": "Custom Overridden Title",
    }
    doc = FakeDoc("conv-1", raw_conv)

    fake_ref = MagicMock()
    fake_ref.where.return_value = FakeQuery([doc])

    fake_user_doc = MagicMock()
    fake_user_doc.collection.return_value = fake_ref

    mock_db = MagicMock()
    mock_db.collection.return_value.document.return_value = fake_user_doc
    monkeypatch.setattr(folders_db, "db", mock_db)

    results = folders_db.get_conversations_in_folder("uid-1", "folder-123")
    assert len(results) == 1
    conv = results[0]
    assert conv["id"] == "conv-1"
    # Segments must be decoded into list of dicts, not raw bytes
    assert isinstance(conv["transcript_segments"], list)
    assert conv["transcript_segments"][0]["text"] == "Folder conversation transcript"
    # User title override must be applied to structured.title
    assert conv["structured"]["title"] == "Custom Overridden Title"


def test_get_conversations_in_folder_filters_hidden_and_refills_shortfall(monkeypatch):
    """When a hidden/deleted row causes a page shortfall, start_after refills the page."""
    docs = [
        FakeDoc(
            "conv-1",
            {
                "folder_id": "f1",
                "created_at": NOW,
                "discarded": False,
                "transcript_segments": [],
                "structured": {"title": "Visible 1"},
            },
        ),
        FakeDoc(
            "conv-hidden",
            {
                "folder_id": "f1",
                "created_at": NOW,
                "discarded": False,
                "deleted": True,  # Soft-deleted tombstone
                "transcript_segments": [],
                "structured": {"title": "Hidden Deleted"},
            },
        ),
        FakeDoc(
            "conv-2",
            {
                "folder_id": "f1",
                "created_at": NOW,
                "discarded": False,
                "transcript_segments": [],
                "structured": {"title": "Visible 2"},
            },
        ),
    ]

    fake_ref = MagicMock()
    fake_ref.where.return_value = FakeQuery(docs)

    fake_user_doc = MagicMock()
    fake_user_doc.collection.return_value = fake_ref

    mock_db = MagicMock()
    mock_db.collection.return_value.document.return_value = fake_user_doc
    monkeypatch.setattr(folders_db, "db", mock_db)

    # Ask for limit=2. The first window [conv-1, conv-hidden] has 1 hidden doc,
    # so refill via start_after must pull conv-2 to return full limit=2.
    results = folders_db.get_conversations_in_folder("uid-1", "f1", limit=2, offset=0)
    assert len(results) == 2
    ids = [c["id"] for c in results]
    assert ids == ["conv-1", "conv-2"]


def test_get_conversations_in_folder_include_discarded(monkeypatch):
    docs = [
        FakeDoc(
            "conv-active",
            {
                "folder_id": "f1",
                "created_at": NOW,
                "discarded": False,
                "transcript_segments": [],
                "structured": {"title": "Active"},
            },
        ),
        FakeDoc(
            "conv-discarded",
            {
                "folder_id": "f1",
                "created_at": NOW,
                "discarded": True,
                "transcript_segments": [],
                "structured": {"title": "Discarded"},
            },
        ),
    ]

    fake_ref = MagicMock()
    fake_ref.where.return_value = FakeQuery(docs)
    fake_user_doc = MagicMock()
    fake_user_doc.collection.return_value = fake_ref

    mock_db = MagicMock()
    mock_db.collection.return_value.document.return_value = fake_user_doc
    monkeypatch.setattr(folders_db, "db", mock_db)

    results = folders_db.get_conversations_in_folder("uid-1", "f1", limit=10, include_discarded=True)
    assert len(results) == 2
    assert {c["id"] for c in results} == {"conv-active", "conv-discarded"}


def test_update_folder_conversation_count_subtracts_hidden(monkeypatch):
    fake_ref = MagicMock()
    count_mock = MagicMock()
    count_mock.value = 10
    query_mock = MagicMock()
    query_mock.count.return_value.get.return_value = [[count_mock]]
    fake_ref.where.return_value.where.return_value = query_mock

    folder_doc_mock = MagicMock()
    fake_user_doc = MagicMock()
    fake_user_doc.collection.side_effect = lambda col: fake_ref if col == "conversations" else folder_doc_mock
    folder_doc_mock.document.return_value = folder_doc_mock

    monkeypatch.setattr(
        folders_db,
        "get_firestore_client",
        lambda: MagicMock(collection=lambda col: MagicMock(document=lambda uid: fake_user_doc)),
    )
    monkeypatch.setattr(folders_db.conversation_visibility_counts, "count_hidden", lambda *args, **kwargs: 4)

    final_count = folders_db.update_folder_conversation_count("uid-1", "folder-123")
    assert final_count == 6  # 10 - 4 = 6
    folder_doc_mock.update.assert_called_once_with({"conversation_count": 6})


def test_update_folder_conversation_count_clamps_at_zero(monkeypatch):
    fake_ref = MagicMock()
    count_mock = MagicMock()
    count_mock.value = 2
    query_mock = MagicMock()
    query_mock.count.return_value.get.return_value = [[count_mock]]
    fake_ref.where.return_value.where.return_value = query_mock

    folder_doc_mock = MagicMock()
    fake_user_doc = MagicMock()
    fake_user_doc.collection.side_effect = lambda col: fake_ref if col == "conversations" else folder_doc_mock
    folder_doc_mock.document.return_value = folder_doc_mock

    monkeypatch.setattr(
        folders_db,
        "get_firestore_client",
        lambda: MagicMock(collection=lambda col: MagicMock(document=lambda uid: fake_user_doc)),
    )
    monkeypatch.setattr(folders_db.conversation_visibility_counts, "count_hidden", lambda *args, **kwargs: 5)

    final_count = folders_db.update_folder_conversation_count("uid-1", "folder-123")
    assert final_count == 0  # max(0, 2 - 5)
    folder_doc_mock.update.assert_called_once_with({"conversation_count": 0})


def test_router_get_folder_conversations_validates_decoded_record(monkeypatch):
    from routers import folders as folders_router

    # Create a conversation with decoded transcript segments as returned by get_conversations_in_folder
    decoded_conv = {
        "id": "conv-test",
        "uid": "uid-1",
        "folder_id": "f-1",
        "created_at": NOW,
        "started_at": NOW,
        "finished_at": NOW,
        "discarded": False,
        "transcript_segments": [
            {
                "id": "seg-1",
                "text": "Valid transcript for endpoint",
                "speaker": "SPEAKER_00",
                "is_user": True,
                "start": 0.0,
                "end": 1.5,
            }
        ],
        "structured": {"title": "Endpoint Test", "category": "work"},
    }

    monkeypatch.setattr(folders_router.folders_db, "get_folder", lambda uid, fid: {"id": fid, "name": "Work"})
    monkeypatch.setattr(
        folders_router.folders_db, "get_conversations_in_folder", lambda *args, **kwargs: [decoded_conv]
    )
    monkeypatch.setattr(folders_router, "redact_conversations_for_list", lambda convs: None)

    conversations = folders_router.get_folder_conversations(folder_id="f-1", uid="uid-1")
    assert len(conversations) == 1
    assert isinstance(conversations[0], Conversation)
    assert conversations[0].id == "conv-test"
    assert len(conversations[0].transcript_segments) == 1
    assert conversations[0].transcript_segments[0].text == "Valid transcript for endpoint"
