"""Unit tests for GET /v1/users/me/llm-usage/daily and get_daily_usage_summary.

Both routers.llm_usage and database.llm_usage import cleanly, so both the endpoint and the
db helpers are tested directly with patch.object (no sys.modules mutation). The per-feature
token aggregation is shared with get_usage_summary via _sum_model_tokens.
"""

import os

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key-not-real")

from datetime import date, datetime, timezone
from unittest.mock import patch

import database.llm_usage as llm_usage_db
from routers import llm_usage as llm_usage_router

_DAY = datetime(2026, 7, 5, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# shared aggregation helper
# ---------------------------------------------------------------------------
def test_sum_model_tokens_sums_and_skips_non_dicts():
    models = {
        "gpt-4.1-mini": {"input_tokens": 100, "output_tokens": 50, "call_count": 2},
        "o4-mini": {"input_tokens": 10, "output_tokens": 5, "call_count": 1},
        "cost_only": 0.05,  # non-dict -> skipped
    }
    assert llm_usage_db._sum_model_tokens(models) == (110, 55, 3)


def test_sum_feature_tokens_handles_nested_flat_and_aliases():
    # nested per-model feature -> summed across models
    nested = {"m1": {"input_tokens": 100, "output_tokens": 50, "call_count": 2}}
    assert llm_usage_db._sum_feature_tokens("chat", nested) == (100, 50, 2)
    # flat primary bucket -> token fields read directly off the feature dict
    flat = {"input_tokens": 30, "output_tokens": 12, "cache_read_tokens": 0, "total_tokens": 0, "call_count": 4}
    assert llm_usage_db._sum_feature_tokens("desktop_chat", flat) == (30, 12, 4)
    # per-account alias of a bucket -> skipped so it cannot double-count the primary
    assert llm_usage_db._sum_feature_tokens("desktop_chat_omi", flat) == (0, 0, 0)


# ---------------------------------------------------------------------------
# db: get_daily_usage_summary
# ---------------------------------------------------------------------------
def test_summary_normalizes_features_and_totals():
    raw = {
        "date": "2026-07-05",
        "last_updated": "x",
        "chat": {"m1": {"input_tokens": 100, "output_tokens": 50, "call_count": 2}},
        "memory": {"m1": {"input_tokens": 20, "output_tokens": 8, "call_count": 1}},
        "scalar": 5,  # non-dict feature -> skipped
    }
    with patch.object(llm_usage_db, "get_daily_usage", return_value=raw):
        out = llm_usage_db.get_daily_usage_summary("u1", _DAY)
    assert set(out["features"]) == {"chat", "memory"}
    assert out["features"]["chat"] == {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150, "call_count": 2}
    assert out["total"] == {"input_tokens": 120, "output_tokens": 58, "total_tokens": 178, "call_count": 3}
    assert out["date"] == "2026-07-05"
    assert out["has_data"] is True


def test_summary_no_data():
    with patch.object(llm_usage_db, "get_daily_usage", return_value={}):
        out = llm_usage_db.get_daily_usage_summary("u1", _DAY)
    assert out["has_data"] is False
    assert out["features"] == {}
    assert out["total"] == {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "call_count": 0}


def test_summary_includes_flat_bucket_and_skips_account_alias():
    # A real desktop day: a nested per-model feature plus the flat desktop_chat bucket written
    # by record_llm_usage_bucket, which also dual-writes a desktop_chat_omi per-account alias.
    raw = {
        "date": "2026-07-05",
        "last_updated": "x",
        "chat": {"m1": {"input_tokens": 100, "output_tokens": 50, "call_count": 2}},
        "desktop_chat": {
            "input_tokens": 30,
            "output_tokens": 12,
            "cache_read_tokens": 0,
            "total_tokens": 0,
            "cost_usd": 0.0,
            "call_count": 4,
        },
        "desktop_chat_omi": {  # per-account alias -> must not be counted again
            "input_tokens": 30,
            "output_tokens": 12,
            "cache_read_tokens": 0,
            "total_tokens": 0,
            "cost_usd": 0.0,
            "call_count": 4,
        },
    }
    with patch.object(llm_usage_db, "get_daily_usage", return_value=raw):
        out = llm_usage_db.get_daily_usage_summary("u1", _DAY)
    # bucket surfaces as its own feature; the alias is dropped
    assert set(out["features"]) == {"chat", "desktop_chat"}
    assert out["features"]["desktop_chat"] == {
        "input_tokens": 30,
        "output_tokens": 12,
        "total_tokens": 42,
        "call_count": 4,
    }
    # totals count chat + desktop_chat once each, not the alias
    assert out["total"] == {"input_tokens": 130, "output_tokens": 62, "total_tokens": 192, "call_count": 6}
    assert out["has_data"] is True


def test_summary_bucket_only_day_reports_data():
    # A desktop-only user whose day has just the bucket schema must not report has_data=false.
    raw = {"desktop_chat": {"input_tokens": 7, "output_tokens": 3, "total_tokens": 0, "call_count": 1}}
    with patch.object(llm_usage_db, "get_daily_usage", return_value=raw):
        out = llm_usage_db.get_daily_usage_summary("u1", _DAY)
    assert out["has_data"] is True
    assert set(out["features"]) == {"desktop_chat"}
    assert out["total"] == {"input_tokens": 7, "output_tokens": 3, "total_tokens": 10, "call_count": 1}


def test_summary_skips_cost_only_and_zero_sum_buckets():
    raw = {
        "cost_only": {"m": 0.05},  # inner value not a dict -> contributes nothing -> dropped
        "empty": {"m": {"input_tokens": 0, "output_tokens": 0, "call_count": 0}},  # zero-sum -> dropped
    }
    with patch.object(llm_usage_db, "get_daily_usage", return_value=raw):
        out = llm_usage_db.get_daily_usage_summary("u1", _DAY)
    assert out["features"] == {}
    assert out["has_data"] is False


# ---------------------------------------------------------------------------
# router: thin delegation + typed date
# ---------------------------------------------------------------------------
def test_endpoint_delegates_with_converted_datetime():
    sentinel = {"date": "2026-07-05", "features": {}, "total": {}, "has_data": False}
    with patch.object(llm_usage_db, "get_daily_usage_summary", return_value=sentinel) as m:
        resp = llm_usage_router.get_daily_llm_usage(date=date(2026, 7, 5), uid="u1")
    assert resp is sentinel
    uid_arg, day_arg = m.call_args[0]
    assert uid_arg == "u1"
    assert day_arg == _DAY  # date param converted to a UTC datetime


def test_endpoint_default_date_passes_none():
    with patch.object(llm_usage_db, "get_daily_usage_summary", return_value={}) as m:
        llm_usage_router.get_daily_llm_usage(date=None, uid="u1")
    assert m.call_args[0] == ("u1", None)
