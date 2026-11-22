"""Tests for tombstone safety in store_conversation_screen_frames."""

from copy import deepcopy
import os

os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")

import pytest
from database import screen_frames as screen_frames_db
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore, StrictFirestoreTransaction
from utils.screen_frames import store as store_util

UID = "frame-test-user"
CONV_ID = "frame-conv-1"
CONV_PATH = ("users", UID, "conversations", CONV_ID)
FRAME_ID = "frame-1"
FRAME_PATH = ("users", UID, "conversations", CONV_ID, "screen_frames", FRAME_ID)


class MergeStrictFirestoreTransaction(StrictFirestoreTransaction):
    def set(self, ref, data, merge=False):
        self._assert_reference_belongs(ref)
        self.has_written = True
        payload = deepcopy(data)
        self.sets.append((ref.path, payload))
        if merge and ref.path in self._database.rows:
            self._database.rows[ref.path].update(payload)
        else:
            self._database.rows[ref.path] = payload


class MergeStrictFirestore(StrictFirestore):
    def transaction(self, **kwargs):
        return MergeStrictFirestoreTransaction(self)


def sample_frame(frame_id=FRAME_ID):
    return {"id": frame_id, "caption": "test screen frame"}


def test_store_conversation_screen_frames_live_conversation():
    store = MergeStrictFirestore()
    store.rows[CONV_PATH] = {"id": CONV_ID, "deleted": False}

    success = screen_frames_db.store_conversation_screen_frames(UID, CONV_ID, [sample_frame()], firestore_client=store)
    assert success is True
    assert FRAME_PATH in store.rows
    assert store.rows[CONV_PATH].get("has_content") is True


def test_store_conversation_screen_frames_missing_conversation():
    store = MergeStrictFirestore()

    success = screen_frames_db.store_conversation_screen_frames(UID, CONV_ID, [sample_frame()], firestore_client=store)
    assert success is False
    assert FRAME_PATH not in store.rows


@pytest.mark.parametrize("deleted_val", [True, 1, "true"])
def test_store_conversation_screen_frames_rejects_soft_deleted_tombstone(deleted_val):
    store = MergeStrictFirestore()
    store.rows[CONV_PATH] = {
        "id": CONV_ID,
        "deleted": deleted_val,
        "has_content": False,
    }

    success = screen_frames_db.store_conversation_screen_frames(UID, CONV_ID, [sample_frame()], firestore_client=store)
    # Must reject tombstone: return False, never create subcollection frame, never mutate parent doc
    assert success is False
    assert FRAME_PATH not in store.rows
    assert store.rows[CONV_PATH].get("has_content") is False


def test_persist_screen_frame_docs_integration(monkeypatch):
    store = MergeStrictFirestore()
    store.rows[CONV_PATH] = {
        "id": CONV_ID,
        "deleted": True,
        "has_content": False,
    }
    monkeypatch.setattr(screen_frames_db, "get_firestore_client", lambda: store)

    persisted = store_util.persist_screen_frame_docs(UID, CONV_ID, [sample_frame()])
    assert persisted is False
    assert FRAME_PATH not in store.rows
    assert store.rows[CONV_PATH].get("has_content") is False
