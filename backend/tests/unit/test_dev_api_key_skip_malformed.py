"""Regression: get_dev_keys_for_user skips a malformed key instead of 500ing the whole list.

Each key doc is parsed with DevApiKey.model_validate, so a single legacy or malformed key document
raised ValidationError and crashed the entire developer-API-keys list. It is now skipped (and
logged) so the rest of the user's keys still return. No live services.
"""

import os
from unittest.mock import MagicMock, patch

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

import database.dev_api_key as dev_api_key_db  # noqa: E402


def test_get_dev_keys_skips_malformed(monkeypatch):
    good = MagicMock()
    good.id = "good"
    good.to_dict.return_value = {"scopes": None, "ok": True}
    bad = MagicMock()
    bad.id = "bad"
    bad.to_dict.return_value = {"scopes": None, "bad": True}

    fake_db = MagicMock()
    q = fake_db.collection.return_value
    q.where.return_value = q
    q.order_by.return_value = q
    q.stream.return_value = [good, bad]

    def fake_validate(data):
        if data.get("bad"):
            raise ValueError("malformed developer API key")
        return data  # stand-in for a parsed DevApiKey

    monkeypatch.setattr(dev_api_key_db.DevApiKey, "model_validate", staticmethod(fake_validate))

    with patch.object(dev_api_key_db, "db", fake_db):
        result = dev_api_key_db.get_dev_keys_for_user("u1")

    assert result == [{"scopes": None, "ok": True}]  # malformed key skipped, good one kept
