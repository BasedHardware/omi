"""Regression: list_goal_progress_events skips a malformed event instead of 500ing the whole history.

Each event doc is parsed with GoalProgressEvent.model_validate, so a single legacy or malformed
progress-event doc raised ValidationError and crashed the entire history list. It is now skipped
(and logged) so the rest still return. No live services.
"""

import os
from unittest.mock import MagicMock

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

import database.goals as goals_db  # noqa: E402


def test_list_goal_progress_events_skips_malformed(monkeypatch):
    good = MagicMock()
    good.id = "good"
    good.to_dict.return_value = {"ok": True}
    bad = MagicMock()
    bad.id = "bad"
    bad.to_dict.return_value = {"bad": True}

    fake = MagicMock()  # self-chaining fake firestore_client
    for method in ("collection", "document", "where", "order_by", "limit"):
        getattr(fake, method).return_value = fake
    fake.stream.return_value = [good, bad]

    def fake_validate(data):
        if data.get("bad"):
            raise ValueError("malformed goal progress event")
        return data  # stand-in for a parsed GoalProgressEvent

    monkeypatch.setattr(goals_db, "_snapshot_dict", lambda snap: snap.to_dict())
    monkeypatch.setattr(goals_db.GoalProgressEvent, "model_validate", staticmethod(fake_validate))

    result = goals_db.list_goal_progress_events("u1", "g1", firestore_client=fake)

    assert result == [{"ok": True}]  # malformed event skipped, good one kept
