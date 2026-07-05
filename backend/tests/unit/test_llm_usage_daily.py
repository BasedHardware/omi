"""Unit tests for GET /v1/users/me/llm-usage/daily.

routers.llm_usage imports cleanly, so the endpoint is tested directly with patch.object
on the llm_usage_db seam (no sys.modules mutation).
"""

import os

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key-not-real")

from unittest.mock import patch

import pytest
from fastapi import HTTPException

import database.llm_usage as llm_usage_db
from routers import llm_usage as llm_usage_router


def test_no_data_returns_zeros():
    with patch.object(llm_usage_db, "get_daily_usage", return_value={}):
        resp = llm_usage_router.get_daily_llm_usage(date="2026-07-05", uid="u1")
    assert resp["has_data"] is False
    assert resp["features"] == {}
    assert resp["total"] == {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "call_count": 0}
    assert resp["date"] == "2026-07-05"


def test_normalizes_features_and_totals():
    raw = {
        "date": "2026-07-05",
        "last_updated": "2026-07-05T12:00:00Z",
        "chat": {
            "gpt-4.1-mini": {"input_tokens": 100, "output_tokens": 50, "call_count": 2},
            "o4-mini": {"input_tokens": 10, "output_tokens": 5, "call_count": 1},
        },
        "memory": {"gpt-4.1-mini": {"input_tokens": 20, "output_tokens": 8, "call_count": 1}},
        "some_scalar": 5,  # non-dict feature -> skipped
    }
    with patch.object(llm_usage_db, "get_daily_usage", return_value=raw):
        resp = llm_usage_router.get_daily_llm_usage(date=None, uid="u1")  # default = today
    assert set(resp["features"].keys()) == {"chat", "memory"}
    assert resp["features"]["chat"] == {
        "input_tokens": 110,
        "output_tokens": 55,
        "total_tokens": 165,
        "call_count": 3,
    }
    assert resp["features"]["memory"] == {
        "input_tokens": 20,
        "output_tokens": 8,
        "total_tokens": 28,
        "call_count": 1,
    }
    assert resp["total"] == {"input_tokens": 130, "output_tokens": 63, "total_tokens": 193, "call_count": 4}
    assert resp["has_data"] is True


def test_skips_cost_only_and_zero_sum_buckets():
    raw = {
        "cost_only": {"gpt-4.1-mini": 0.05},  # inner value not a dict -> contributes nothing -> dropped
        "empty": {"m": {"input_tokens": 0, "output_tokens": 0, "call_count": 0}},  # zero-sum -> dropped
    }
    with patch.object(llm_usage_db, "get_daily_usage", return_value=raw):
        resp = llm_usage_router.get_daily_llm_usage(date="2026-07-05", uid="u1")
    assert resp["features"] == {}
    assert resp["has_data"] is False


def test_bad_date_raises_400_before_db():
    # Parse failure happens before any DB access; patching to explode proves the DB is not hit.
    with patch.object(llm_usage_db, "get_daily_usage", side_effect=AssertionError("db must not be called")):
        with pytest.raises(HTTPException) as exc:
            llm_usage_router.get_daily_llm_usage(date="2026/07/05", uid="u1")
    assert exc.value.status_code == 400
