"""get_app_usage_history / get_app_money_made must skip a malformed usage doc, not 500 the enrichment.

Both functions built UsageHistoryItem(**x) per raw usage doc with no guard. UsageHistoryItem requires
uid/timestamp/type (enum), and the results are Redis/process-cached and shared, so one legacy or
malformed usage document (a bad type enum, a missing timestamp) raised ValidationError and 500'd the
whole app usage/earnings enrichment. _safe_usage_history_items skips such a record and logs the app id
plus offending field names, mirroring _safe_build_app in the same module. The helper is a pure
function, so the test imports and calls it directly (no monkeypatch, no sys.modules).
"""

import os

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

from datetime import datetime, timezone

import utils.apps as apps_utils  # noqa: E402
from models.app import UsageHistoryItem, UsageHistoryType  # noqa: E402


def _valid_usage_dict():
    return {
        'uid': 'u1',
        'timestamp': datetime(2026, 1, 1, tzinfo=timezone.utc),
        'type': UsageHistoryType.chat_message_sent.value,
    }


def test_safe_usage_history_items_returns_items_for_valid_records():
    items = apps_utils._safe_usage_history_items([_valid_usage_dict(), _valid_usage_dict()], 'app1')
    assert len(items) == 2
    assert all(isinstance(i, UsageHistoryItem) for i in items)


def test_safe_usage_history_items_skips_malformed_records():
    # A doc missing timestamp/type and a doc with an out-of-enum type are skipped, not raised.
    records = [
        _valid_usage_dict(),
        {'uid': 'u1'},  # missing required timestamp + type
        {**_valid_usage_dict(), 'type': 'not_a_real_type'},  # bad enum value
    ]
    items = apps_utils._safe_usage_history_items(records, 'app1')
    assert [i.uid for i in items] == ['u1']  # only the valid record survives, no 500


def test_safe_usage_history_items_empty():
    assert apps_utils._safe_usage_history_items([], 'app1') == []
