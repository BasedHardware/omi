"""Comprehensive unit tests for Omi Solana Pay App."""

import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from main import app, _is_valid_base58_address


class TestOmiSolanaPay(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_base58_validation(self):
        # Valid addresses
        self.assertTrue(_is_valid_base58_address("FhthDcQ1UhdRetMXtEurj6YM24xiwTAZJc4WADmr9EB8"))
        self.assertTrue(_is_valid_base58_address("EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"))
        # Invalid addresses
        self.assertFalse(_is_valid_base58_address("0OIl"))  # invalid base58 chars
        self.assertFalse(_is_valid_base58_address("short"))
        self.assertFalse(_is_valid_base58_address(""))
        self.assertFalse(_is_valid_base58_address(None))

    def test_health_endpoint(self):
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["app"], "omi-solana-pay-app")

    def test_manifest_endpoint(self):
        resp = self.client.get("/.well-known/omi-tools.json")
        self.assertEqual(resp.status_code, 200)
        manifest = resp.json()
        self.assertIn("tools", manifest)
        tool_names = [t["name"] for t in manifest["tools"]]
        self.assertIn("check_solana_balance", tool_names)
        self.assertIn("parse_solana_pay_request", tool_names)
        self.assertIn("generate_payment_intent", tool_names)
        self.assertIn("verify_transaction_signature", tool_names)

    def test_parse_solana_pay_valid_sol(self):
        url = "solana:FhthDcQ1UhdRetMXtEurj6YM24xiwTAZJc4WADmr9EB8?amount=0.5&label=Blue%20Bottle%20Coffee&memo=Order%23104"
        resp = self.client.post("/tools/parse_solana_pay_request", json={"solana_pay_url": url})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIsNone(data["error"])
        self.assertEqual(data["data"]["amount"], 0.5)
        self.assertEqual(data["data"]["token"], "SOL")
        self.assertEqual(data["data"]["label"], "Blue Bottle Coffee")
        self.assertEqual(data["data"]["memo"], "Order#104")
        self.assertIn("Blue Bottle Coffee", data["data"]["voice_prompt"])

    def test_parse_solana_pay_usdc(self):
        url = (
            "solana:FhthDcQ1UhdRetMXtEurj6YM24xiwTAZJc4WADmr9EB8"
            "?amount=15.00&spl-token=EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v&label=Acme%20Store"
        )
        resp = self.client.post("/tools/parse_solana_pay_request", json={"solana_pay_url": url})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIsNone(data["error"])
        self.assertEqual(data["data"]["token"], "USDC")
        self.assertEqual(data["data"]["amount"], 15.0)

    def test_parse_solana_pay_invalid_scheme(self):
        resp = self.client.post("/tools/parse_solana_pay_request", json={"solana_pay_url": "ethereum:0x1234"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIsNotNone(data["error"])
        self.assertIn("scheme must begin with 'solana:'", data["error"])

    def test_parse_solana_pay_invalid_amount(self):
        resp = self.client.post(
            "/tools/parse_solana_pay_request",
            json={"solana_pay_url": "solana:FhthDcQ1UhdRetMXtEurj6YM24xiwTAZJc4WADmr9EB8?amount=-5"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIsNotNone(data["error"])
        self.assertIn("finite, non-negative number", data["error"])

    def test_parse_solana_pay_nan_and_inf(self):
        for bad_val in ["nan", "inf", "-inf"]:
            resp = self.client.post(
                "/tools/parse_solana_pay_request",
                json={"solana_pay_url": f"solana:FhthDcQ1UhdRetMXtEurj6YM24xiwTAZJc4WADmr9EB8?amount={bad_val}"},
            )
            self.assertEqual(resp.status_code, 200)
            self.assertIsNotNone(resp.json().get("error"))

    def test_parse_solana_pay_invalid_spl_token(self):
        resp = self.client.post(
            "/tools/parse_solana_pay_request",
            json={"solana_pay_url": "solana:FhthDcQ1UhdRetMXtEurj6YM24xiwTAZJc4WADmr9EB8?spl-token=invalid_mint_000"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Invalid spl-token mint address", resp.json().get("error", ""))

    def test_parse_solana_pay_control_char_sanitization(self):
        url = "solana:FhthDcQ1UhdRetMXtEurj6YM24xiwTAZJc4WADmr9EB8?amount=1.0&label=Shop%1b%07%00Name"
        resp = self.client.post("/tools/parse_solana_pay_request", json={"solana_pay_url": url})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIsNone(data["error"])
        self.assertEqual(data["data"]["label"], "ShopName")

    def test_generate_voice_intent(self):
        req = {
            "recipient": "Starbucks Coffee",
            "amount": 4.75,
            "currency": "USDC",
            "memo": "Venti Latte",
        }
        resp = self.client.post("/tools/generate_payment_intent", json=req)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIsNone(data["error"])
        self.assertIn("Starbucks Coffee", data["result"])
        self.assertIn("4.75 USDC", data["result"])
        self.assertIn("Confirm", data["result"])
        self.assertIn("Venti Latte", data["result"])

    def test_invalid_signature_verification(self):
        resp = self.client.post("/tools/verify_transaction_signature", json={"signature": "bad_sig"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIsNotNone(data["error"])
        self.assertIn("Invalid Solana signature", data["error"])

    def test_check_solana_balance_invalid_network(self):
        resp = self.client.post(
            "/tools/check_solana_balance",
            json={"wallet_address": "FhthDcQ1UhdRetMXtEurj6YM24xiwTAZJc4WADmr9EB8", "network": "testnet"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIsNotNone(data["error"])
        self.assertIn("Invalid network 'testnet'", data["error"])

    def test_verify_signature_invalid_network(self):
        valid_sig = "5Ver7CFvVTXZx12Q3pS8f2r4s81qT3G6x87p3h12984712093847102938471029384710293847102938471029"
        resp = self.client.post(
            "/tools/verify_transaction_signature",
            json={"signature": valid_sig, "network": "ropsten"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIsNotNone(data["error"])
        self.assertIn("Invalid network 'ropsten'", data["error"])


if __name__ == "__main__":
    unittest.main()

