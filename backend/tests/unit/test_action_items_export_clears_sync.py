"""Regression test for the pending-sync starvation fixed in #21214.

A task exported through the single-item ``PATCH /v1/action-items/{id}`` route
went through ``update_action_item``, which never cleared ``sync_requested``.
Every device export left the flag set; once 50 settled rows led the
sync_requested==True limit-50 query, genuinely pending tasks starved with no
error. The route now clears ``sync_requested`` whenever ``exported`` becomes
True — matching ``batch_sync_update_action_items``.
"""

import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import database.action_items as action_items_db

UID = "u1"
ITEM_ID = "item-1"


def _install_fake_db(monkeypatch):
    """Capture the update payload the single-item route writes."""
    writes = []

    stored_row = {'sync_requested': True}
    doc_ref = MagicMock()
    doc_ref.get.return_value = SimpleNamespace(exists=True, to_dict=lambda: dict(stored_row))

    def update(data):
        writes.append(dict(data))
        stored_row.update(data)

    doc_ref.update.side_effect = update

    items_collection = MagicMock()
    items_collection.document.return_value = doc_ref

    user_doc = MagicMock()
    user_doc.collection.return_value = items_collection
    users = MagicMock()
    users.document.return_value = user_doc

    fake_db = MagicMock()
    fake_db.collection.return_value = users

    monkeypatch.setattr(action_items_db, "db", fake_db)
    monkeypatch.setattr(action_items_db, "bump_action_items_list_version", lambda uid: None)
    return writes, stored_row


def test_export_clears_sync_requested(monkeypatch):
    writes, _stored_row = _install_fake_db(monkeypatch)

    action_items_db.update_action_item(
        UID,
        ITEM_ID,
        {"exported": True, "export_platform": "apple_reminders", "apple_reminder_id": "r1"},
    )

    assert writes, "update_action_item should issue a doc update"
    assert writes[-1]["exported"] is True
    assert writes[-1]["sync_requested"] is False


def test_non_export_update_leaves_sync_requested_alone(monkeypatch):
    writes, _stored_row = _install_fake_db(monkeypatch)

    action_items_db.update_action_item(UID, ITEM_ID, {"description": "x"})

    assert "sync_requested" not in writes[-1]


def test_cloud_export_clears_stored_pending_sync_requested(monkeypatch):
    writes, stored_row = _install_fake_db(monkeypatch)

    action_items_db.update_action_item(
        UID,
        ITEM_ID,
        {"exported": True, "export_platform": "asana"},
    )

    assert writes[-1]["exported"] is True
    assert writes[-1]["export_platform"] == "asana"
    assert writes[-1]["sync_requested"] is False
    assert stored_row['sync_requested'] is False
    # The pending read filters on sync_requested == True before it applies
    # exported != True in Python, so this settled row no longer consumes a
    # slot in that limit-50 result.
