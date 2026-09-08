import sys
from pathlib import Path
from unittest import TestCase
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent))
from main import app


class FrankfurterToolTests(TestCase):
    def post_convert(self, amount):
        with TestClient(app) as client:
            return client.post(
                "/tools/convert_currency",
                json={
                    "amount": amount,
                    "from_currency": "USD",
                    "to_currencies": ["EUR"],
                },
            )

    def test_rejects_non_finite_amounts_without_calling_provider(self):
        for amount in ("NaN", "sNaN", "Infinity", "-Infinity"):
            with self.subTest(amount=amount), patch("main._request_json", new_callable=AsyncMock) as request_json:
                response = self.post_convert(amount)

            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                response.json(),
                {"result": None, "error": "currency conversion failed: amount must be a finite number"},
            )
            request_json.assert_not_awaited()

    def test_rejects_non_positive_amounts_without_calling_provider(self):
        for amount in (0, "-2.5"):
            with self.subTest(amount=amount), patch("main._request_json", new_callable=AsyncMock) as request_json:
                response = self.post_convert(amount)

            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                response.json(),
                {"result": None, "error": "currency conversion failed: amount must be greater than 0"},
            )
            request_json.assert_not_awaited()

    def test_converts_finite_positive_amount(self):
        with patch("main._request_json", new_callable=AsyncMock) as request_json:
            request_json.return_value = {"base": "USD", "date": "2026-09-08", "rates": {"EUR": 42.5}}
            response = self.post_convert("50")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"result": "50 USD on 2026-09-08:\n- EUR: 42.5", "error": None},
        )
        request_json.assert_awaited_once_with(
            "/latest",
            {"amount": "50", "from": "USD", "to": "EUR"},
        )

    def test_malformed_amount_uses_existing_tool_error_path(self):
        with patch("main._request_json", new_callable=AsyncMock) as request_json:
            response = self.post_convert("abc")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"result": None, "error": "currency conversion failed: amount must be a number"},
        )
        request_json.assert_not_awaited()
