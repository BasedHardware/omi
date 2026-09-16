from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from main import FRANKFURTER_BASE_URL, _format_decimal, _parse_amount, app


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


# =========================================================================
# Regression tests for Issue #14161 (Redirect & Small Reference Rate Display)
# =========================================================================

def test_frankfurter_base_url_canonical_v1():
    """Verify endpoint is updated to canonical v1 to avoid 301 redirects."""
    assert FRANKFURTER_BASE_URL == "https://api.frankfurter.dev/v1"


def test_format_decimal_preserves_small_rates_precision():
    """Verify small reference rates (<0.0001) do not display as 0."""
    # Standard rates
    assert _format_decimal(50) == "50"
    assert _format_decimal("19.95") == "19.95"
    assert _format_decimal(1.23456) == "1.2346"

    # Small rates (e.g. 1 IDR = 0.000042 GBP)
    assert _format_decimal(0.000042) == "0.000042"
    assert _format_decimal("0.000042") == "0.000042"
    assert _format_decimal(0.00000123) == "0.00000123"


def test_get_latest_rates_small_reference_rate_display():
    """Verify get_latest_rates outputs precise small rates without truncating to 0."""
    client = TestClient(app)

    mock_payload = {
        "amount": 1.0,
        "base": "IDR",
        "date": "2026-09-15",
        "rates": {"GBP": 0.000042},
    }

    with patch("main._request_json", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = mock_payload
        resp = client.post(
            "/tools/get_latest_rates",
            json={"base_currency": "IDR", "to_currencies": ["GBP"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["error"] is None
        assert "1 IDR = 0.000042 GBP" in data["result"]
        assert "1 IDR = 0 GBP" not in data["result"]
