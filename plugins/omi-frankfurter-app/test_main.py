import math
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from main import _parse_amount, app


def test_parse_amount_valid():
    assert _parse_amount(50) == Decimal("50")
    assert _parse_amount("19.95") == Decimal("19.95")
    assert _parse_amount(0.01) == Decimal(str(0.01))


def test_parse_amount_zero_and_negative():
    with pytest.raises(ValueError, match="amount must be greater than 0"):
        _parse_amount(0)

    with pytest.raises(ValueError, match="amount must be greater than 0"):
        _parse_amount(-1)

    with pytest.raises(ValueError, match="amount must be greater than 0"):
        _parse_amount("-50.25")


def test_parse_amount_invalid_text():
    with pytest.raises(ValueError, match="amount must be a number"):
        _parse_amount("not-a-number")


def test_parse_amount_non_finite_rejected():
    non_finite_values = [
        "NaN",
        "nan",
        "sNaN",
        "-NaN",
        "Infinity",
        "+Infinity",
        "-Infinity",
        "inf",
        "-inf",
        float("nan"),
        float("inf"),
        float("-inf"),
    ]
    for val in non_finite_values:
        with pytest.raises(ValueError, match="amount must be a finite number"):
            _parse_amount(val)


def test_convert_currency_rejects_non_finite_amounts_without_500():
    client = TestClient(app)

    for bad_amount in ["NaN", "sNaN", "Infinity", "-Infinity"]:
        resp = client.post(
            "/tools/convert_currency",
            json={
                "amount": bad_amount,
                "from_currency": "USD",
                "to_currencies": ["EUR"],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["result"] is None
        assert "amount must be a finite number" in data["error"]


def test_convert_currency_valid_amount_success():
    client = TestClient(app)

    mock_rates = {
        "amount": 50.0,
        "base": "USD",
        "date": "2026-09-09",
        "rates": {"EUR": 45.5, "GBP": 39.2},
    }

    with patch("main._request_json", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = mock_rates
        resp = client.post(
            "/tools/convert_currency",
            json={
                "amount": 50,
                "from_currency": "USD",
                "to_currencies": ["EUR", "GBP"],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["error"] is None
        assert "50 USD on 2026-09-09:" in data["result"]
        assert "- EUR: 45.5" in data["result"]
        assert "- GBP: 39.2" in data["result"]
