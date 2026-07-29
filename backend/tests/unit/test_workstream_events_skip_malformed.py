"""Regression: list_workstream_events skips a malformed event instead of 500ing the whole stream.

Each event doc is parsed with WorkstreamEvent.model_validate, so a single legacy or malformed event
doc raised ValidationError and crashed the entire event stream. It is now skipped (and logged) so the
rest still return. No live services.
"""

import os
from unittest.mock import MagicMock

from pydantic import BaseModel

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

import database.workstreams as workstreams_db  # noqa: E402


class _Probe(BaseModel):
    x: int


def test_list_workstream_events_skips_malformed(monkeypatch):
    good = MagicMock()
    good.id = "good"
    good.to_dict.return_value = {"ok": True}
    bad = MagicMock()
    bad.id = "bad"
    bad.to_dict.return_value = {"bad": True}

    class _FakeStore:  # storage-port stand-in whose query() returns the seeded event snapshots
        def query(self, collection, **kwargs):
            return [good, bad]

    def fake_validate(data):
        if data.get("bad"):
            _Probe.model_validate({})  # raises a genuine pydantic ValidationError
        return data  # stand-in for a parsed WorkstreamEvent

    monkeypatch.setattr(workstreams_db, "_store", lambda: _FakeStore())
    monkeypatch.setattr(workstreams_db, "_snapshot_dict", lambda snap: snap.to_dict())
    monkeypatch.setattr(workstreams_db.WorkstreamEvent, "model_validate", staticmethod(fake_validate))

    result = workstreams_db.list_workstream_events("u1", "w1")

    assert result == [{"ok": True}]  # malformed event skipped, good one kept
