"""Regression: list_candidates skips a malformed candidate instead of 500ing the whole list.

CandidateRecord.from_storage is model_validate with extra='forbid', so a single legacy or
malformed candidate doc raised ValidationError and crashed the entire GET /v1/candidates list.
It is now skipped (and logged) so the rest of the user's candidates still return. No live services.
"""

import os
from unittest.mock import MagicMock, patch

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

import database.candidates as candidates_db  # noqa: E402


def test_list_candidates_skips_malformed(monkeypatch):
    good = MagicMock()
    good.id = "good"
    good.to_dict.return_value = {"ok": True}
    bad = MagicMock()
    bad.id = "bad"
    bad.to_dict.return_value = {"bad": True}

    fake_db = MagicMock()
    q = fake_db.collection.return_value.document.return_value.collection.return_value
    for method in ("where", "order_by", "offset", "limit"):
        getattr(q, method).return_value = q
    q.stream.return_value = [good, bad]

    def fake_from_storage(data):
        if data.get("bad"):
            raise ValueError("malformed candidate")
        return data  # stand-in for a parsed CandidateRecord

    monkeypatch.setattr(candidates_db, "_snapshot_dict", lambda snap: snap.to_dict())
    monkeypatch.setattr(candidates_db.CandidateRecord, "from_storage", staticmethod(fake_from_storage))

    with patch.object(candidates_db, "db", fake_db):
        result = candidates_db.list_candidates("u1")

    assert result == [{"ok": True}]  # malformed candidate skipped, good one kept
