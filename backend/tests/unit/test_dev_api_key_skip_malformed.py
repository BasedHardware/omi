"""Regression: get_dev_keys_for_user skips a malformed key instead of 500ing the whole list.

Each key doc is parsed with DevApiKey.model_validate, so a single legacy or malformed key document
raised ValidationError and crashed the entire developer-API-keys list. It is now skipped (and logged)
so the rest of the user's keys still return. The catch is narrowed to ValidationError so an unexpected
runtime error on this security-sensitive path is not silently hidden as a skipped document. No live
services.
"""

import os
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

import database.dev_api_key as dev_api_key_db  # noqa: E402


def _fake_db(stream):
    fake_db = MagicMock()
    q = fake_db.collection.return_value
    q.where.return_value = q
    q.order_by.return_value = q
    q.stream.return_value = stream
    return fake_db


def test_get_dev_keys_skips_malformed():
    # good doc parses into a valid DevApiKey; bad doc is missing required fields, so the real
    # DevApiKey.model_validate raises a pydantic ValidationError (the narrow case we now skip).
    good = MagicMock()
    good.id = "good"
    good.to_dict.return_value = {
        "id": "good",
        "name": "primary key",
        "key_prefix": "omi_dev_ab12",
        "created_at": datetime.now(timezone.utc),
        "scopes": None,
    }
    bad = MagicMock()
    bad.id = "bad"
    bad.to_dict.return_value = {"legacy": True}  # missing id/name/key_prefix/created_at -> ValidationError

    with patch.object(dev_api_key_db, "db", _fake_db([good, bad])):
        result = dev_api_key_db.get_dev_keys_for_user("u1")

    assert [k.id for k in result] == ["good"]  # malformed key skipped, good one parsed and kept


def test_get_dev_keys_does_not_swallow_unexpected_error(monkeypatch):
    # An unexpected (non-validation) error on this security path must propagate, not be hidden as a
    # skipped "malformed" document. Verifies the catch is narrowed to ValidationError.
    good = MagicMock()
    good.id = "x"
    good.to_dict.return_value = {"scopes": None}

    def boom(_data):
        raise RuntimeError("unexpected parsing failure")

    monkeypatch.setattr(dev_api_key_db.DevApiKey, "model_validate", staticmethod(boom))
    with patch.object(dev_api_key_db, "db", _fake_db([good])):
        with pytest.raises(RuntimeError):
            dev_api_key_db.get_dev_keys_for_user("u1")
