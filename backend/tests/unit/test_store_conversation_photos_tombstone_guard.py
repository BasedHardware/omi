"""Tests for tombstone safety in store_conversation_photos."""

import os

os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")

import pytest
from database import conversations as conversations_db
from models.conversation_photo import ConversationPhoto
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore

UID = "photo-test-user"
CONV_ID = "photo-conv-1"
CONV_PATH = ("users", UID, "conversations", CONV_ID)
PHOTO_PATH = ("users", UID, "conversations", CONV_ID, "photos", "p-1")


def sample_photo(photo_id="p-1"):
    return ConversationPhoto(id=photo_id, base64="dGVzdA==")


def test_store_conversation_photos_live_conversation():
    store = StrictFirestore()
    store.rows[CONV_PATH] = {"id": CONV_ID, "deleted": False, "data_protection_level": "standard"}

    success = conversations_db.store_conversation_photos(UID, CONV_ID, [sample_photo()], firestore_client=store)
    assert success is True
    assert PHOTO_PATH in store.rows
    assert store.rows[CONV_PATH].get("has_content") is True
    assert store.rows[CONV_PATH].get("has_photos") is True


def test_store_conversation_photos_missing_conversation():
    store = StrictFirestore()

    success = conversations_db.store_conversation_photos(UID, CONV_ID, [sample_photo()], firestore_client=store)
    assert success is False
    assert PHOTO_PATH not in store.rows


@pytest.mark.parametrize("deleted_val", [True, 1, "true"])
def test_store_conversation_photos_rejects_soft_deleted_tombstone(deleted_val):
    store = StrictFirestore()
    store.rows[CONV_PATH] = {
        "id": CONV_ID,
        "deleted": deleted_val,
        "has_content": False,
        "has_photos": False,
        "data_protection_level": "standard",
    }

    success = conversations_db.store_conversation_photos(UID, CONV_ID, [sample_photo()], firestore_client=store)
    # Must reject tombstone: return False, never create subcollection photo, never mutate parent doc
    assert success is False
    assert PHOTO_PATH not in store.rows
    assert store.rows[CONV_PATH].get("has_content") is False
    assert store.rows[CONV_PATH].get("has_photos") is False
