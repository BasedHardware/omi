"""Unit tests for GET /v1/trends/{category}.

routers.trends imports cleanly (only database.trends), so the endpoint is tested
directly with patch.object on the trends_db seam (no sys.modules mutation).
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

import database.trends as trends_db
from routers import trends as trends_router


def test_filters_to_the_requested_category():
    rows = [
        {"category": "ceo", "type": "best", "topics": [{"topic": "x", "memories_count": 3}]},
        {"category": "ceo", "type": "worst", "topics": []},
        {"category": "company", "type": "best", "topics": []},
    ]
    with patch.object(trends_db, "get_trends_data", return_value=rows):
        result = trends_router.get_trends_by_category(category="ceo")
    assert [r["type"] for r in result] == ["best", "worst"]
    assert all(r["category"] == "ceo" for r in result)


def test_unknown_category_returns_404_without_db_call():
    # The TrendEnum check runs before any DB access, so no patch is needed.
    with pytest.raises(HTTPException) as exc:
        trends_router.get_trends_by_category(category="not_a_category")
    assert exc.value.status_code == 404


def test_known_category_with_no_data_returns_404():
    with patch.object(
        trends_db, "get_trends_data", return_value=[{"category": "company", "type": "best", "topics": []}]
    ):
        with pytest.raises(HTTPException) as exc:
            trends_router.get_trends_by_category(category="ceo")
    assert exc.value.status_code == 404
