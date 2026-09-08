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
