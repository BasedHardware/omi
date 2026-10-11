"""Regression: a malformed announcement sub-document must not 500 the announcements list.

models.announcement.Announcement.from_dict tolerates a bad top-level type/id/created_at, but built
the targeting/display sub-models with an unguarded Targeting(**...) / Display(**...). A stored sub-dict
with a bad enum or datetime raised pydantic ValidationError, and the database helpers loop from_dict
over documents with no per-item try/except, so one malformed sub-document 500s the whole public list.
from_dict now drops a malformed targeting/display sub-model and keeps the announcement.
"""

from models.announcement import Announcement, TriggerType


def test_malformed_targeting_is_dropped_but_the_announcement_is_kept():
    ann = Announcement.from_dict({"id": "a1", "type": "announcement", "targeting": {"trigger": "bogus-not-an-enum"}})
    assert ann.targeting is None  # malformed sub-doc dropped, no raise
    assert ann.id == "a1"  # announcement itself preserved


def test_malformed_display_is_dropped():
    ann = Announcement.from_dict({"id": "a2", "display": {"priority": "not-an-int", "start_at": "not-a-date"}})
    assert ann.display is None


def test_valid_targeting_and_display_are_kept():
    ann = Announcement.from_dict(
        {
            "id": "a3",
            "targeting": {"trigger": TriggerType.VERSION_UPGRADE.value, "device_models": ["Omi"]},
            "display": {"priority": 3, "dismissible": False},
        }
    )
    assert ann.targeting is not None
    assert ann.targeting.trigger == TriggerType.VERSION_UPGRADE
    assert ann.targeting.device_models == ["Omi"]
    assert ann.display is not None
    assert ann.display.priority == 3
    assert ann.display.dismissible is False


def test_missing_targeting_and_display_are_none():
    ann = Announcement.from_dict({"id": "a4"})
    assert ann.targeting is None
    assert ann.display is None


def test_general_and_pending_announcements_handle_naive_datetimes_and_doc_id_fallback():
    from datetime import datetime, timezone
    from types import SimpleNamespace
    from unittest.mock import MagicMock, patch
    import database.announcements as ann_db
    import routers.announcements as ann_router

    docs = [
        SimpleNamespace(
            id="doc-without-body-id",
            to_dict=lambda: {
                "type": "announcement",
                "created_at": datetime(2026, 9, 24, 12, 0, 0),  # naive
                "expires_at": datetime(2099, 1, 1, 0, 0, 0),  # naive
                "targeting": {"trigger": "immediate"},
                "display": {"show_once": True, "start_at": datetime(2020, 1, 1, 0, 0, 0)},
                "content": {"title": "Hello", "body": "World"},
            },
        )
    ]

    fake_db = MagicMock()
    fake_query = MagicMock()
    fake_query.where.return_value = fake_query
    fake_query.stream.return_value = iter(docs)
    fake_db.collection.return_value = fake_query

    with patch.object(ann_db, "db", fake_db):
        # Naive last_checked_at string via router should be normalized to UTC and not raise TypeError
        res = ann_router.get_announcements(last_checked_at="2026-09-24T10:00:00")
        assert len(res) == 1
        assert res[0].id == "doc-without-body-id"

    # When doc.id is in dismissed_ids, get_pending_announcements must suppress it even if body omitted 'id'
    fake_query.stream.return_value = iter(docs)
    with patch.object(ann_db, "db", fake_db), patch.object(
        ann_db, "get_dismissed_announcement_ids", return_value={"doc-without-body-id"}
    ):
        pending = ann_db.get_pending_announcements(uid="u1", app_version="1.0.0", platform="ios", trigger="app_launch")
        assert pending == []
