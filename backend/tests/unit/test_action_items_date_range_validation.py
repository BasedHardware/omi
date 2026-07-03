"""GET /v1/action-items must reject an inverted date range instead of silently returning nothing.

get_action_items accepts start_date/end_date (created_at) and due_start_date/due_end_date (due_at)
filters and forwards them straight to Firestore inequality filters. FastAPI Query() cannot validate
one parameter against another, so an inverted range (start > end) was passed through unguarded:
Firestore then applies conflicting `>=` and `<=` filters and returns an empty list, so the caller
gets "no action items" and cannot tell a bad request apart from a genuinely empty result. The
endpoint now validates start <= end for both pairs and returns 400 first.

The router imports pure (clients are lazy getters; conftest stubs redis/tiktoken), so the handler
module is imported directly at module scope -- no `sys.modules` stubbing required.
"""

import os
from datetime import datetime, timezone
from unittest.mock import patch

# The router transitively imports utils.encryption, which validates ENCRYPTION_SECRET length at
# import time. conftest sets a default via os.environ.setdefault, but that does not override a
# too-short value pre-set in the shell (e.g. the verification command's ENCRYPTION_SECRET=x). Write
# the canonical test secret directly so the import succeeds regardless of the incoming env.
os.environ['ENCRYPTION_SECRET'] = 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv'
os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')

import pytest
from fastapi import HTTPException

import routers.action_items as ai


def _call(**overrides):
    kwargs = dict(
        limit=50,
        offset=0,
        completed=None,
        conversation_id=None,
        start_date=None,
        end_date=None,
        due_start_date=None,
        due_end_date=None,
        uid='u1',
    )
    kwargs.update(overrides)
    return ai.get_action_items(**kwargs)


def test_inverted_created_date_range_returns_400():
    with pytest.raises(HTTPException) as exc:
        _call(start_date=datetime(2024, 12, 31), end_date=datetime(2024, 1, 1))
    assert exc.value.status_code == 400


def test_inverted_due_date_range_returns_400():
    with pytest.raises(HTTPException) as exc:
        _call(due_start_date=datetime(2024, 12, 31), due_end_date=datetime(2024, 1, 1))
    assert exc.value.status_code == 400


def test_equal_dates_are_allowed():
    # An inclusive range where start == end is valid and must not be rejected.
    same = datetime(2024, 6, 1)
    with patch.object(ai.action_items_db, 'get_action_items', return_value=[]):
        result = _call(start_date=same, end_date=same)
    assert result == {"action_items": [], "has_more": False}


def test_valid_range_passes_through():
    with patch.object(ai.action_items_db, 'get_action_items', return_value=[]):
        result = _call(start_date=datetime(2024, 1, 1), end_date=datetime(2024, 12, 31))
    assert result == {"action_items": [], "has_more": False}


def test_mixed_timezone_awareness_inverted_returns_400():
    # FastAPI parses one bound as naive and the other as timezone-aware when the client only adds an
    # offset to one of them. Comparing those directly raises TypeError (a 500); the endpoint must
    # normalize and still return a clean 400 for an inverted range.
    with pytest.raises(HTTPException) as exc:
        _call(start_date=datetime(2024, 12, 31), end_date=datetime(2024, 1, 1, tzinfo=timezone.utc))
    assert exc.value.status_code == 400


def test_mixed_timezone_awareness_valid_passes():
    # A valid range with mixed awareness must not raise TypeError either.
    with patch.object(ai.action_items_db, 'get_action_items', return_value=[]):
        result = _call(start_date=datetime(2024, 1, 1), end_date=datetime(2024, 12, 31, tzinfo=timezone.utc))
    assert result == {"action_items": [], "has_more": False}
